const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const baseUrl = process.env.WEB_BASE_URL || "http://localhost:3035";
const outDir = path.join(
  "D:/wt/p35/.tmp",
  "playwright-history-smoke-" + new Date().toISOString().replace(/[:.]/g, "-"),
);
fs.mkdirSync(outDir, { recursive: true });

const forbiddenFragments = ["/publish", "/deploy", "/execute", "/approval-decisions"];
const chromeExecutable =
  process.env.CHROME_EXECUTABLE_PATH ||
  "C:/Program Files/Google/Chrome/Application/chrome.exe";

const summary = {
  baseUrl,
  outDir,
  startedAt: new Date().toISOString(),
  status: "pass",
  routes: {},
  screenshots: [],
  forbiddenRequests: [],
  pageErrors: [],
  consoleMessages: [],
  checks: [],
};

function addCheck(name, passed, details = {}) {
  summary.checks.push({ name, passed, ...details });
  if (!passed && summary.status === "pass") {
    summary.status = "UI regression";
  }
}

function short(value, max = 500) {
  return String(value || "").replace(/\s+/g, " ").trim().slice(0, max);
}

async function text(page) {
  return page.locator("body").innerText({ timeout: 15000 });
}

async function shot(page, name) {
  const file = path.join(outDir, `${name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  summary.screenshots.push(file);
}

async function noHorizontalOverflow(page, name) {
  const result = await page.evaluate(() => ({
    innerWidth: window.innerWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  addCheck(name, result.scrollWidth <= result.innerWidth + 1, result);
}

(async () => {
  let browser;
  try {
    browser = await chromium.launch({
      headless: true,
      executablePath: fs.existsSync(chromeExecutable) ? chromeExecutable : undefined,
    });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    const page = await context.newPage();
    page.on("request", (request) => {
      const url = request.url();
      if (forbiddenFragments.some((fragment) => url.includes(fragment))) {
        summary.forbiddenRequests.push(url);
      }
    });
    page.on("pageerror", (error) => summary.pageErrors.push(short(error.stack || error.message)));
    page.on("console", (message) => {
      if (["error", "warning"].includes(message.type())) {
        summary.consoleMessages.push({ type: message.type(), text: short(message.text()) });
      }
    });

    let response = await page.goto(baseUrl + "/", {
      waitUntil: "domcontentloaded",
      timeout: 25000,
    });
    summary.routes.home = response ? response.status() : null;
    await page.waitForLoadState("networkidle", { timeout: 15000 }).catch(() => {});
    const homeText = await text(page);
    await shot(page, "home-history");
    addCheck("home renders recent analyses", /Recent analyses/i.test(homeText));
    addCheck("home exposes history link", /View all analysis history/i.test(homeText));
    addCheck("home shows multiple job actions", (homeText.match(/Open job/g) || []).length >= 2, {
      count: (homeText.match(/Open job/g) || []).length,
    });

    response = await page.goto(baseUrl + "/jobs", {
      waitUntil: "domcontentloaded",
      timeout: 25000,
    });
    summary.routes.jobs = response ? response.status() : null;
    await page.waitForLoadState("networkidle", { timeout: 15000 }).catch(() => {});
    const jobsText = await text(page);
    await shot(page, "jobs-history");
    addCheck("jobs route loads", response && response.status() < 500, {
      status: response ? response.status() : null,
    });
    addCheck("jobs route renders filters", /Target or job search/i.test(jobsText) && /All statuses/i.test(jobsText));
    addCheck("jobs route renders job rows", (jobsText.match(/Open job/g) || []).length >= 2, {
      count: (jobsText.match(/Open job/g) || []).length,
    });
    addCheck("jobs route exposes artifact links", /Draft -|초안/.test(jobsText));

    const mobile = await browser.newContext({ viewport: { width: 390, height: 844 } });
    const mobilePage = await mobile.newPage();
    await mobilePage.goto(baseUrl + "/", { waitUntil: "domcontentloaded", timeout: 25000 });
    await mobilePage.waitForLoadState("networkidle", { timeout: 15000 }).catch(() => {});
    await shot(mobilePage, "mobile-home-history");
    await noHorizontalOverflow(mobilePage, "mobile home has no horizontal overflow");
    await mobilePage.goto(baseUrl + "/jobs", { waitUntil: "domcontentloaded", timeout: 25000 });
    await mobilePage.waitForLoadState("networkidle", { timeout: 15000 }).catch(() => {});
    await shot(mobilePage, "mobile-jobs-history");
    await noHorizontalOverflow(mobilePage, "mobile jobs has no horizontal overflow");
    await mobile.close();

    addCheck("no forbidden network calls", summary.forbiddenRequests.length === 0, {
      count: summary.forbiddenRequests.length,
    });
    addCheck("no page errors", summary.pageErrors.length === 0, { count: summary.pageErrors.length });
  } catch (error) {
    const message = short(error.stack || error.message || error, 1200);
    summary.status = /ERR_CONNECTION|ECONNREFUSED|timeout/i.test(message)
      ? "app unreachable"
      : "UI regression";
    summary.error = message;
  } finally {
    summary.finishedAt = new Date().toISOString();
    fs.writeFileSync(path.join(outDir, "summary.json"), JSON.stringify(summary, null, 2));
    if (browser) {
      await browser.close().catch(() => {});
    }
    console.log(JSON.stringify(summary, null, 2));
    if (summary.status !== "pass") {
      process.exitCode = 1;
    }
  }
})();
