const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");

const jobId = process.argv[2] || "job_7f1635c8de";
const ts = new Date().toISOString().replace(/[:.]/g, "-");
const outDir = path.join(process.cwd(), ".tmp", `playwright-knowledge-download-${ts}`);
fs.mkdirSync(outDir, { recursive: true });

const summary = {
  jobId,
  outDir,
  status: "running",
  screenshots: [],
  forbiddenRequests: [],
  pageErrors: [],
  consoleMessages: [],
};

const forbidden = [/\/publish\b/i, /\/deploy\b/i, /\/execute\b/i, /\/approval-decisions\b/i];

async function launchBrowser() {
  try {
    return await chromium.launch({ headless: true, channel: "chrome" });
  } catch {
    return chromium.launch({ headless: true });
  }
}

function assertState(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

(async () => {
  let browser;
  try {
    browser = await launchBrowser();
    const context = await browser.newContext({
      acceptDownloads: true,
      viewport: { width: 1440, height: 1000 },
    });
    await context.grantPermissions(["clipboard-read", "clipboard-write"], {
      origin: "http://localhost:3035",
    });
    const page = await context.newPage();
    page.on("pageerror", (err) => summary.pageErrors.push({ message: err.message }));
    page.on("console", (msg) => {
      if (["warning", "error"].includes(msg.type())) {
        summary.consoleMessages.push({ type: msg.type(), text: msg.text().slice(0, 500) });
      }
    });
    page.on("request", (request) => {
      if (forbidden.some((pattern) => pattern.test(request.url()))) {
        summary.forbiddenRequests.push({ method: request.method(), url: request.url() });
      }
    });

    await page.goto(`http://localhost:3035/jobs/${jobId}`, {
      waitUntil: "networkidle",
      timeout: 30000,
    });
    const jobBody = await page.locator("body").innerText();
    assertState(/knowledge assets/i.test(jobBody), "Job page did not render knowledge assets.");
    assertState(/download all draft artifacts/i.test(jobBody), "Job page lacks bundle download.");
    assertState(!jobBody.includes("localhost:3035/api/v1/knowledge/assets"), "Job page still exposes web-origin API knowledge links.");
    const jobShot = path.join(outDir, "job-knowledge-download.png");
    await page.screenshot({ path: jobShot, fullPage: true });
    summary.screenshots.push({ name: "job knowledge and downloads", path: jobShot });

    const bundleDownloadPromise = page.waitForEvent("download", { timeout: 30000 });
    await page.getByRole("link", { name: "Download all draft artifacts" }).click();
    const bundleDownload = await bundleDownloadPromise;
    const bundlePath = path.join(outDir, await bundleDownload.suggestedFilename());
    await bundleDownload.saveAs(bundlePath);
    const bundleBytes = fs.readFileSync(bundlePath);
    summary.bundleDownload = {
      filename: path.basename(bundlePath),
      size: bundleBytes.length,
      zipMagic: bundleBytes.slice(0, 4).toString("hex"),
    };
    assertState(summary.bundleDownload.zipMagic === "504b0304", "Bundle download is not a ZIP.");

    await page.getByRole("link", { name: /^Open$/ }).first().click();
    await page.waitForURL(/\/knowledge\/assets\/[^/]+$/, { timeout: 30000 });
    await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});
    const assetBody = await page.locator("body").innerText();
    assertState(/knowledge asset/i.test(assetBody), "Knowledge asset page did not load.");
    assertState(/version history/i.test(assetBody), "Knowledge asset page lacks version history.");
    const assetShot = path.join(outDir, "knowledge-asset.png");
    await page.screenshot({ path: assetShot, fullPage: true });
    summary.screenshots.push({ name: "knowledge asset", path: assetShot });

    await page.getByRole("link", { name: /Open current facts|Facts/ }).first().click();
    await page.waitForURL(/\/knowledge\/assets\/[^/]+\/versions\/[^/]+\/facts$/, {
      timeout: 30000,
    });
    await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});
    const factsBody = await page.locator("body").innerText();
    assertState(/sanitized fact rows/i.test(factsBody), "Facts page lacks facts table.");
    assertState(/fact graph links/i.test(factsBody), "Facts page lacks edges section.");
    assertState(!factsBody.includes("raw_sp_definition"), "Facts page exposed raw SP marker.");
    const factsShot = path.join(outDir, "knowledge-facts.png");
    await page.screenshot({ path: factsShot, fullPage: true });
    summary.screenshots.push({ name: "knowledge facts", path: factsShot });

    await page.goto(`http://localhost:3035/jobs/${jobId}`, {
      waitUntil: "networkidle",
      timeout: 30000,
    });
    const singleDownloadPromise = page.waitForEvent("download", { timeout: 30000 });
    await page.getByRole("link", { name: /^Download$/ }).first().click();
    const singleDownload = await singleDownloadPromise;
    const singlePath = path.join(outDir, await singleDownload.suggestedFilename());
    await singleDownload.saveAs(singlePath);
    const singleContent = fs.readFileSync(singlePath, "utf8");
    summary.singleDownload = {
      filename: path.basename(singlePath),
      size: Buffer.byteLength(singleContent),
      hasDraftContent: singleContent.length > 20,
    };
    assertState(summary.singleDownload.hasDraftContent, "Single artifact download is empty.");

    await page.getByRole("link", { name: "Preview" }).first().click();
    await page.waitForURL(/\/artifacts\/[^/]+$/, { timeout: 30000 });
    await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});
    await page.getByRole("button", { name: "Copy content" }).click();
    await page.waitForTimeout(500);
    const copied = await page.evaluate(() => navigator.clipboard.readText());
    assertState(copied.length > 20, "Clipboard copy did not capture artifact content.");
    assertState(await page.getByRole("link", { name: "Download draft file" }).isVisible(), "Artifact preview lacks draft download link.");
    const artifactShot = path.join(outDir, "artifact-copy-download.png");
    await page.screenshot({ path: artifactShot, fullPage: true });
    summary.screenshots.push({ name: "artifact copy download", path: artifactShot });

    summary.status =
      summary.forbiddenRequests.length === 0 &&
      summary.pageErrors.length === 0 &&
      summary.singleDownload.hasDraftContent &&
      summary.bundleDownload.zipMagic === "504b0304"
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
