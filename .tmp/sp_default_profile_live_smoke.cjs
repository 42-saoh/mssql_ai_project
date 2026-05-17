const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");

const ts = new Date().toISOString().replace(/[:.]/g, "-");
const outDir = path.join(process.cwd(), ".tmp", `playwright-sp-default-profile-${ts}`);
fs.mkdirSync(outDir, { recursive: true });

const summary = {
  outDir,
  status: "running",
  baseUrl: "http://localhost:3035",
  screenshots: [],
  forbiddenRequests: [],
  pageErrors: [],
  consoleMessages: [],
  jobId: null,
  redirectElapsedMs: null,
  terminalStatus: null,
  jobApi: null,
};

const forbidden = [/\/publish\b/i, /\/deploy\b/i, /\/execute\b/i, /\/approval-decisions\b/i];
const terminalStatuses = new Set(["VALIDATION_COMPLETE", "FAILED", "CANCELED"]);

async function launchBrowser() {
  try {
    return await chromium.launch({ headless: true, channel: "chrome" });
  } catch {
    return chromium.launch({ headless: true });
  }
}

async function fetchJson(url) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`${url} returned ${response.status}`);
  }
  return response.json();
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

    await page.goto("http://localhost:3035/requests/new", {
      waitUntil: "networkidle",
      timeout: 30000,
    });
    const requestShot = path.join(outDir, "request-default-before-submit.png");
    await page.screenshot({ path: requestShot, fullPage: true });
    summary.screenshots.push({ name: "default request before submit", path: requestShot });

    const start = Date.now();
    await Promise.all([
      page.waitForURL(/\/jobs\/[A-Za-z0-9_-]+/, { timeout: 45000 }),
      page.getByRole("button", { name: "Submit request" }).click(),
    ]);
    summary.redirectElapsedMs = Date.now() - start;
    summary.jobId = new URL(page.url()).pathname.split("/").filter(Boolean).pop();
    await page.waitForSelector("[role=\"progressbar\"]", { timeout: 30000 });
    const initialShot = path.join(outDir, "job-default-initial.png");
    await page.screenshot({ path: initialShot, fullPage: true });
    summary.screenshots.push({ name: "default job initial", path: initialShot });

    const deadline = Date.now() + 540000;
    while (Date.now() < deadline) {
      const job = await fetchJson(`http://localhost:8035/api/v1/jobs/${summary.jobId}`);
      summary.jobApi = job;
      if (terminalStatuses.has(job.status)) {
        summary.terminalStatus = job.status;
        break;
      }
      await page.waitForTimeout(5000);
    }

    await page.goto(`http://localhost:3035/jobs/${summary.jobId}`, {
      waitUntil: "domcontentloaded",
      timeout: 30000,
    });
    await page.waitForSelector("[role=\"progressbar\"]", { timeout: 30000 });
    const body = await page.locator("body").innerText();
    const progress = await page.locator("[role=\"progressbar\"]").first().getAttribute("aria-valuenow");
    summary.ui = {
      url: page.url(),
      progress,
      hasEstimatedProgress: body.includes("Estimated progress"),
      hasTargetKey: body.includes("mssql:ppm:-:procedure:dbo.getinspitemscd"),
      previewCount: await page.locator("a", { hasText: "Preview" }).count(),
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
    const finalShot = path.join(outDir, "job-default-final.png");
    await page.screenshot({ path: finalShot, fullPage: true });
    summary.screenshots.push({ name: "default job final", path: finalShot });

    summary.status =
      summary.forbiddenRequests.length === 0 &&
      summary.pageErrors.length === 0 &&
      summary.ui.hasEstimatedProgress &&
      summary.ui.forbiddenControls.length === 0 &&
      summary.terminalStatus === "VALIDATION_COMPLETE"
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
