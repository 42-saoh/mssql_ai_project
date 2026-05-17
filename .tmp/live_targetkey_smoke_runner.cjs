const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const baseURL = process.env.BASE_URL || "http://localhost:3035";
const expectedTargetKey = "mssql:ppm:-:procedure:dbo.getinspitemscd";
const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
const outDir = path.join(process.cwd(), ".tmp", `playwright-live-targetkey-${timestamp}`);
fs.mkdirSync(outDir, { recursive: true });

const summary = {
  baseURL,
  startedAt: new Date().toISOString(),
  targetKey: expectedTargetKey,
  jobs: [],
  artifactId: null,
  validationStatus: null,
  steps: [],
  screenshots: {},
  forbiddenRequests: [],
  consoleMessages: [],
  pageErrors: [],
  blockers: [],
};

function record(name, status, notes, extra = {}) {
  summary.steps.push({ name, status, notes, ...extra });
  console.log(`${status.toUpperCase()} ${name}: ${notes}`);
}

async function screenshot(page, name) {
  const file = path.join(outDir, `${name}.png`);
  await page.screenshot({ path: file, fullPage: true });
  summary.screenshots[name] = file;
}

async function launchBrowser() {
  const attempts = [
    { channel: "chrome", headless: true },
    { channel: "msedge", headless: true },
    { headless: true },
  ];
  let lastError;
  for (const options of attempts) {
    try {
      return await chromium.launch(options);
    } catch (error) {
      lastError = error;
    }
  }
  throw lastError;
}

function installWatchers(page) {
  page.on("request", (request) => {
    const url = request.url();
    if (/\/(publish|deploy|execute|approval-decisions)(\/|\?|$)/i.test(url)) {
      summary.forbiddenRequests.push({ method: request.method(), url });
    }
  });
  page.on("console", (message) => {
    if (["error", "warning"].includes(message.type())) {
      summary.consoleMessages.push({
        type: message.type(),
        text: message.text().slice(0, 500),
      });
    }
  });
  page.on("pageerror", (error) => {
    summary.pageErrors.push(String(error.message || error).slice(0, 500));
  });
}

async function pageText(page) {
  return await page.locator("body").innerText({ timeout: 30000 });
}

async function goto(page, route, name) {
  const response = await page.goto(new URL(route, baseURL).toString(), {
    waitUntil: "domcontentloaded",
    timeout: 60000,
  });
  const status = response ? response.status() : 0;
  if (status >= 500) {
    throw new Error(`${name} returned HTTP ${status}`);
  }
  await page.waitForLoadState("networkidle", { timeout: 30000 }).catch(() => {});
  return status;
}

async function configureSingleRequest(page) {
  await page.locator('select[name="dbProfileId"]').first().selectOption("ppm").catch(() => {});
  await page.locator('select[name="targetType"]').first().selectOption("PROCEDURE").catch(() => {});
  await page.locator('input[name="schema"]').first().fill("dbo");
  await page.locator('input[name="name"]').first().fill("GetInspItemsCd");
  await page.locator('select[name="llmProfileId"]').first().selectOption("openai_fast_test").catch(() => {});
}

async function submitSingleRequest(page, label) {
  await goto(page, "/requests/new", `${label} request form`);
  await configureSingleRequest(page);
  await screenshot(page, `${label}-request-form`);
  const waitForJobUrl = page.waitForURL(/\/jobs\/[^/?#]+/, { timeout: 180000 });
  await page.getByRole("button", { name: "Submit request" }).click();
  await waitForJobUrl;
  await page.waitForLoadState("networkidle", { timeout: 60000 }).catch(() => {});
  const jobId = new URL(page.url()).pathname.split("/").filter(Boolean).pop();
  const text = await pageText(page);
  summary.jobs.push({ label, jobId, detailUrl: page.url() });
  await screenshot(page, `${label}-job-detail`);
  if (!text.includes(expectedTargetKey)) {
    summary.blockers.push({
      code: "TARGET_KEY_NOT_VISIBLE_ON_JOB",
      message: `${label} job detail did not render ${expectedTargetKey}`,
      jobId,
    });
    record(`${label} job targetKey`, "fail", "targetKey not visible on job detail", { jobId });
  } else {
    record(`${label} job targetKey`, "pass", "targetKey visible on job detail", { jobId });
  }
  return jobId;
}

async function waitForPreviewLink(page, jobId) {
  for (let attempt = 0; attempt < 24; attempt += 1) {
    await goto(page, `/jobs/${encodeURIComponent(jobId)}`, `job ${jobId} artifact poll`);
    const previewCount = await page.getByRole("link", { name: /Preview/i }).count();
    if (previewCount > 0) {
      return true;
    }
    const text = await pageText(page);
    if (/FAILED|Failure reason/i.test(text)) {
      summary.blockers.push({
        code: "API_OR_LLM_PREREQUISITE_BLOCKER",
        message: `Job ${jobId} failed before artifact preview became available.`,
      });
      return false;
    }
    await page.waitForTimeout(5000);
  }
  summary.blockers.push({
    code: "LIVE_DATA_LIMITATION",
    message: `Job ${jobId} did not expose an artifact preview within 120 seconds.`,
  });
  return false;
}

async function verifyArtifact(page, jobId) {
  const hasPreview = await waitForPreviewLink(page, jobId);
  if (!hasPreview) {
    record("artifact preview", "live-data limitation", "no preview link available before timeout");
    return;
  }
  await Promise.all([
    page.waitForURL(/\/artifacts\/[^/?#]+/, { timeout: 60000 }),
    page.getByRole("link", { name: /Preview/i }).first().click(),
  ]);
  await page.waitForLoadState("networkidle", { timeout: 60000 }).catch(() => {});
  const artifactId = new URL(page.url()).pathname.split("/").filter(Boolean).pop();
  summary.artifactId = artifactId;
  const text = await pageText(page);
  await screenshot(page, "artifact-preview");
  if (!text.includes(expectedTargetKey)) {
    summary.blockers.push({
      code: "TARGET_KEY_NOT_VISIBLE_ON_ARTIFACT",
      message: `Artifact ${artifactId} did not render ${expectedTargetKey}`,
    });
    record("artifact targetKey", "fail", "targetKey not visible on artifact preview", {
      artifactId,
    });
  } else {
    record("artifact targetKey", "pass", "targetKey visible on artifact preview", {
      artifactId,
    });
  }
  const validationButton = page.getByRole("button", { name: /Run validation|검증/i });
  if ((await validationButton.count()) > 0) {
    await validationButton.first().click();
    await page.waitForLoadState("networkidle", { timeout: 60000 }).catch(() => {});
    const after = await pageText(page);
    const match =
      after.match(/\b(PASSED|REVIEW_REQUIRED|FAILED)\b/) ||
      after.match(/\b(Passed|Evidence caveat|Failed)\b/i);
    summary.validationStatus = match ? match[1] : null;
    await screenshot(page, "artifact-after-validation");
    record(
      "artifact validation",
      summary.validationStatus ? "pass" : "live-data limitation",
      summary.validationStatus
        ? `visible validation status ${summary.validationStatus}`
        : "validation returned without a visible status",
    );
  }
}

async function main() {
  const browser = await launchBrowser();
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  installWatchers(page);

  try {
    const homeStatus = await goto(page, "/", "home");
    const homeText = await pageText(page);
    await screenshot(page, "home");
    if (homeText.includes("Portal API is not configured")) {
      throw new Error("Portal API is not configured");
    }
    record("preflight", "pass", `home loaded with HTTP ${homeStatus}`);

    await goto(page, "/requests/new", "request form");
    const requestText = await pageText(page);
    if (!requestText.includes("Submit request")) {
      throw new Error("request form missing Submit request");
    }
    record("request form", "pass", "single request controls visible");

    const firstJobId = await submitSingleRequest(page, "first");
    const secondJobId = await submitSingleRequest(page, "second");

    await goto(page, `/jobs?targetKey=${encodeURIComponent(expectedTargetKey)}`, "target history");
    const historyText = await pageText(page);
    await screenshot(page, "target-history");
    const hasFirst = historyText.includes(firstJobId);
    const hasSecond = historyText.includes(secondJobId);
    if (!hasFirst || !hasSecond) {
      summary.blockers.push({
        code: "TARGET_KEY_HISTORY_FILTER_FAILED",
        message: "Target-key filtered history did not show both disposable jobs.",
        firstJobId,
        secondJobId,
        hasFirst,
        hasSecond,
      });
      record("targetKey history filter", "fail", "filtered history did not show both jobs", {
        firstJobId,
        secondJobId,
        hasFirst,
        hasSecond,
      });
    } else {
      record("targetKey history filter", "pass", "filtered history shows both jobs", {
        firstJobId,
        secondJobId,
      });
    }

    await verifyArtifact(page, firstJobId);

    await page.setViewportSize({ width: 390, height: 844 });
    await goto(page, `/jobs?targetKey=${encodeURIComponent(expectedTargetKey)}`, "mobile history");
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 2,
    );
    await screenshot(page, "mobile-target-history");
    record(
      "mobile target history",
      overflow ? "fail" : "pass",
      overflow ? "horizontal overflow detected" : "no horizontal overflow detected",
    );
    if (overflow) {
      summary.blockers.push({
        code: "MOBILE_HORIZONTAL_OVERFLOW",
        message: "Mobile target history has horizontal overflow.",
      });
    }
  } catch (error) {
    summary.blockers.push({
      code: "LIVE_PLAYWRIGHT_SMOKE_FAILED",
      message: String(error.message || error),
    });
    record("smoke run", "fail", String(error.message || error));
  } finally {
    await browser.close();
    summary.completedAt = new Date().toISOString();
    summary.status =
      summary.forbiddenRequests.length === 0 &&
      summary.pageErrors.length === 0 &&
      summary.blockers.length === 0
        ? "pass"
        : "fail";
    const summaryPath = path.join(outDir, "summary.json");
    fs.writeFileSync(summaryPath, JSON.stringify(summary, null, 2), "utf8");
    console.log(`SUMMARY ${summaryPath}`);
    if (summary.status !== "pass") {
      process.exitCode = 1;
    }
  }
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
