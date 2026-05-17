const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");

const ts = new Date().toISOString().replace(/[:.]/g, "-");
const outDir = path.join(process.cwd(), ".tmp", `playwright-validation-caveat-${ts}`);
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
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
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
    const validationPanel = page.locator("section.panel").filter({
      hasText: "Evidence and policy checks",
    });
    const validationText = await validationPanel.innerText();
    assertState(validationText.includes("Passed required check"), "Pass checks are not explained as passed required checks.");
    assertState(validationText.includes("Evidence caveat"), "Evidence caveat status is missing.");
    assertState(validationText.includes("Rule level: Advisory"), "Non-pass caveat rule level is missing.");
    assertState(!/\bERROR\b/.test(validationText), "Validation panel still shows ERROR as a current state.");
    const artifactShot = path.join(outDir, "artifact-validation-caveats.png");
    await page.screenshot({ path: artifactShot, fullPage: true });
    summary.screenshots.push({ name: "artifact validation caveats", path: artifactShot });

    await page.goto(
      "http://localhost:3035/metadata/search?dbProfileId=ppm&query=P&limit=5&objectTypes=PROCEDURE&objectTypes=TABLE",
      { waitUntil: "networkidle", timeout: 30000 },
    );
    const searchPanel = page.locator("section.panel").filter({ hasText: "Search results" });
    const searchText = await searchPanel.innerText();
    assertState(searchText.includes("Evidence caveats"), "Metadata evidence caveat callout is missing.");
    assertState(searchText.includes("의존성 링크 일부는 근거 보강 필요 상태입니다"), "Metadata caveat copy was not localized.");
    assertState(!searchText.includes("Dependency metadata is incomplete"), "Old dependency metadata copy is still visible.");
    const blockerListCount = await searchPanel.locator(".blocker-list").count();
    assertState(blockerListCount === 0, "Dependency metadata caveat is still rendered as a blocker list.");
    const metadataShot = path.join(outDir, "metadata-search-caveats.png");
    await page.screenshot({ path: metadataShot, fullPage: true });
    summary.screenshots.push({ name: "metadata search caveats", path: metadataShot });

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
