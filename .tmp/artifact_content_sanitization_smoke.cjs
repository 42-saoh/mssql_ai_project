const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");

const ts = new Date().toISOString().replace(/[:.]/g, "-");
const outDir = path.join(process.cwd(), ".tmp", `playwright-artifact-content-sanitize-${ts}`);
fs.mkdirSync(outDir, { recursive: true });

const summary = {
  status: "running",
  outDir,
  forbiddenRequests: [],
  pageErrors: [],
  consoleMessages: [],
  screenshots: [],
};
const forbidden = [/\/publish\b/i, /\/deploy\b/i, /\/execute\b/i, /\/approval-decisions\b/i];

function assertState(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

async function launchBrowser() {
  try {
    return await chromium.launch({ headless: true, channel: "chrome" });
  } catch {
    return chromium.launch({ headless: true });
  }
}

(async () => {
  let browser;
  try {
    browser = await launchBrowser();
    const context = await browser.newContext({ acceptDownloads: true, viewport: { width: 1440, height: 1000 } });
    await context.grantPermissions(["clipboard-read", "clipboard-write"], {
      origin: "http://localhost:3035",
    });
    const page = await context.newPage();
    page.on("request", (request) => {
      if (forbidden.some((pattern) => pattern.test(request.url()))) {
        summary.forbiddenRequests.push({ method: request.method(), url: request.url() });
      }
    });
    page.on("pageerror", (error) => summary.pageErrors.push({ message: error.message }));
    page.on("console", (message) => {
      if (["warning", "error"].includes(message.type())) {
        summary.consoleMessages.push({ type: message.type(), text: message.text().slice(0, 500) });
      }
    });

    await page.goto("http://localhost:3035/artifacts/art_1d85d34240", {
      waitUntil: "networkidle",
      timeout: 30000,
    });
    const previewText = await page.locator(".content-preview").innerText();
    assertState(previewText.includes("Evidence caveat"), "Artifact preview does not show evidence caveat wording.");
    assertState(!previewText.includes("REVIEW_REQUIRED"), "Artifact preview still shows REVIEW_REQUIRED.");
    assertState(!/review\s+marker/i.test(previewText), "Artifact preview still shows review marker wording.");

    await page.getByRole("button", { name: "Copy content" }).click();
    await page.waitForTimeout(500);
    const copied = await page.evaluate(() => navigator.clipboard.readText());
    assertState(copied.includes("Evidence caveat"), "Copied content does not include sanitized caveat wording.");
    assertState(!copied.includes("REVIEW_REQUIRED"), "Copied content still includes REVIEW_REQUIRED.");

    const singleDownloadPromise = page.waitForEvent("download", { timeout: 30000 });
    await page.getByRole("link", { name: "Download draft file" }).click();
    const download = await singleDownloadPromise;
    const singlePath = path.join(outDir, await download.suggestedFilename());
    await download.saveAs(singlePath);
    const singleContent = fs.readFileSync(singlePath, "utf8");
    assertState(singleContent.includes("Evidence caveat"), "Downloaded file does not include sanitized caveat wording.");
    assertState(!singleContent.includes("REVIEW_REQUIRED"), "Downloaded file still includes REVIEW_REQUIRED.");

    const shot = path.join(outDir, "artifact-content-sanitized.png");
    await page.screenshot({ path: shot, fullPage: true });
    summary.screenshots.push({ name: "artifact content sanitized", path: shot });
    summary.singleDownload = {
      filename: path.basename(singlePath),
      size: Buffer.byteLength(singleContent),
    };

    summary.status =
      summary.forbiddenRequests.length === 0 &&
      summary.pageErrors.length === 0 &&
      summary.consoleMessages.length === 0
        ? "pass"
        : "fail";
    await context.close();
  } catch (error) {
    summary.status = "fail";
    summary.error = { message: error.message, stack: String(error.stack || "").slice(0, 2000) };
  } finally {
    if (browser) {
      await browser.close().catch(() => {});
    }
    fs.writeFileSync(path.join(outDir, "summary.json"), JSON.stringify(summary, null, 2));
    console.log(JSON.stringify(summary, null, 2));
  }
})();
