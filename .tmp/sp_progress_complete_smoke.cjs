const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");

const jobId = process.argv[2] || "job_bf27659ae6";
const ts = new Date().toISOString().replace(/[:.]/g, "-");
const outDir = path.join(process.cwd(), ".tmp", `playwright-sp-progress-complete-${ts}`);
fs.mkdirSync(outDir, { recursive: true });

const summary = {
  jobId,
  outDir,
  screenshots: [],
  forbiddenRequests: [],
  pageErrors: [],
  consoleMessages: [],
  status: "running",
};

const forbidden = [/\/publish\b/i, /\/deploy\b/i, /\/execute\b/i, /\/approval-decisions\b/i];

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
    page.on("pageerror", (err) => summary.pageErrors.push({ message: err.message }));
    page.on("console", (msg) => {
      if (["warning", "error"].includes(msg.type())) {
        summary.consoleMessages.push({ type: msg.type(), text: msg.text().slice(0, 500) });
      }
    });
    page.on("request", (req) => {
      if (forbidden.some((re) => re.test(req.url()))) {
        summary.forbiddenRequests.push({ method: req.method(), url: req.url() });
      }
    });

    await page.goto(`http://localhost:3035/jobs/${jobId}`, {
      waitUntil: "domcontentloaded",
      timeout: 30000,
    });
    await page.waitForSelector("[role=\"progressbar\"]", { timeout: 30000 });
    await page.waitForTimeout(1500);

    const body = await page.locator("body").innerText();
    const pb = page.locator("[role=\"progressbar\"]").first();
    summary.jobDetail = {
      url: page.url(),
      hasEstimatedProgress: body.includes("Estimated progress"),
      progressNow: await pb.getAttribute("aria-valuenow").catch(() => null),
      progressMin: await pb.getAttribute("aria-valuemin").catch(() => null),
      progressMax: await pb.getAttribute("aria-valuemax").catch(() => null),
      hasValidationComplete: body.includes("VALIDATION_COMPLETE") || body.includes("Validation complete"),
      hasTargetKey: body.includes("mssql:ppm:-:procedure:dbo.getinspitemscd"),
      previewLinks: await page
        .locator("a", { hasText: "Preview" })
        .evaluateAll((links) => links.map((a) => ({ text: a.innerText.trim(), href: a.getAttribute("href") }))),
      forbiddenControls: await page
        .locator("button, a, input, select, textarea")
        .evaluateAll((controls) =>
          controls
            .map((el) => ({
              tag: el.tagName,
              type: el.getAttribute("type"),
              text: (el.innerText || el.value || el.getAttribute("aria-label") || "").trim(),
              href: el.getAttribute("href"),
            }))
            .filter((item) => /publish|deploy|execute|approval|apply|row data/i.test(`${item.text} ${item.href || ""}`)),
        ),
    };

    const jobShot = path.join(outDir, "job-progress-complete.png");
    await page.screenshot({ path: jobShot, fullPage: true });
    summary.screenshots.push({ name: "completed job detail", path: jobShot });

    if (summary.jobDetail.previewLinks.length > 0) {
      await page.locator("a", { hasText: "Preview" }).first().click();
      await page.waitForURL(/\/artifacts\//, { timeout: 30000 });
      await page.waitForTimeout(1500);
      const artBody = await page.locator("body").innerText();
      summary.artifact = {
        url: page.url(),
        hasEvidenceRefs: /Evidence|evidence|근거/.test(artBody),
        hasCaveats: /caveat|근거 보강|품질/.test(artBody),
        hasTargetKey: artBody.includes("mssql:ppm:-:procedure:dbo.getinspitemscd"),
        hasValidationPanel: /validation|Validation|검증/.test(artBody),
        forbiddenControls: await page
          .locator("button, a, input, select, textarea")
          .evaluateAll((controls) =>
            controls
              .map((el) => ({
                tag: el.tagName,
                type: el.getAttribute("type"),
                text: (el.innerText || el.value || el.getAttribute("aria-label") || "").trim(),
                href: el.getAttribute("href"),
              }))
              .filter((item) => /publish|deploy|execute|approval|apply|row data/i.test(`${item.text} ${item.href || ""}`)),
          ),
      };
      const artifactShot = path.join(outDir, "artifact-preview-complete.png");
      await page.screenshot({ path: artifactShot, fullPage: true });
      summary.screenshots.push({ name: "completed artifact preview", path: artifactShot });
    }

    summary.status =
      summary.forbiddenRequests.length === 0 &&
      summary.pageErrors.length === 0 &&
      summary.jobDetail.hasEstimatedProgress &&
      summary.jobDetail.hasValidationComplete &&
      summary.jobDetail.progressNow === "100" &&
      summary.jobDetail.forbiddenControls.length === 0 &&
      (!summary.artifact || summary.artifact.forbiddenControls.length === 0)
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
