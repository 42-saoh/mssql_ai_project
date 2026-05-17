const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const baseURL = process.env.BASE_URL || "http://localhost:3035";
const apiBaseURL = process.env.API_BASE_URL || "http://localhost:8035";
const expectedTargetKey = process.env.TARGET_KEY || "mssql:ppm:-:procedure:dbo.getinspitemscd";
const jobIdFromEnv = process.env.JOB_ID || "";
const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
const outDir = path.join(process.cwd(), ".tmp", `playwright-live-targetkey-artifact-${timestamp}`);
fs.mkdirSync(outDir, { recursive: true });

const summary = {
  baseURL,
  apiBaseURL,
  startedAt: new Date().toISOString(),
  targetKey: expectedTargetKey,
  jobId: null,
  artifactId: null,
  artifactType: null,
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

async function apiJson(route) {
  const response = await fetch(new URL(route, apiBaseURL).toString());
  const text = await response.text();
  if (!response.ok) {
    throw new Error(`${route} returned HTTP ${response.status}: ${text.slice(0, 500)}`);
  }
  return JSON.parse(text);
}

async function findArtifact() {
  const candidateJobs = jobIdFromEnv
    ? [{ jobId: jobIdFromEnv }]
    : (await apiJson(`/api/v1/jobs?targetKey=${encodeURIComponent(expectedTargetKey)}&limit=10`)).jobs || [];
  for (const job of candidateJobs) {
    const jobId = job.jobId || job.id;
    if (!jobId) {
      continue;
    }
    const artifactsPayload = await apiJson(`/api/v1/jobs/${encodeURIComponent(jobId)}/artifacts`);
    const artifacts = artifactsPayload.artifacts || [];
    const artifact = artifacts.find((item) => item.targetKey === expectedTargetKey) || artifacts[0];
    if (artifact) {
      return { jobId, artifact };
    }
  }
  throw new Error("No artifact found for targetKey-filtered jobs.");
}

async function pageText(page) {
  return await page.locator("body").innerText({ timeout: 30000 });
}

async function main() {
  const { jobId, artifact } = await findArtifact();
  summary.jobId = jobId;
  summary.artifactId = artifact.artifactId;
  summary.artifactType = artifact.artifactType;
  record("artifact discovery", "pass", `using ${artifact.artifactId} from ${jobId}`, {
    artifactType: artifact.artifactType,
  });

  const browser = await launchBrowser();
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  installWatchers(page);

  try {
    const url = new URL(`/artifacts/${encodeURIComponent(artifact.artifactId)}`, baseURL).toString();
    const response = await page.goto(url, { waitUntil: "domcontentloaded", timeout: 60000 });
    const status = response ? response.status() : 0;
    if (status >= 500) {
      throw new Error(`artifact page returned HTTP ${status}`);
    }
    await page.waitForLoadState("networkidle", { timeout: 60000 }).catch(() => {});
    const before = await pageText(page);
    await screenshot(page, "artifact-focused-before-validation");

    const missing = [];
    if (!before.includes(expectedTargetKey)) {
      missing.push("targetKey");
    }
    if (!new RegExp(artifact.artifactId, "i").test(before)) {
      missing.push("artifact id");
    }
    if (!/Evidence|근거|evidence/i.test(before)) {
      missing.push("evidence copy");
    }
    if (!/validation|검증/i.test(before)) {
      missing.push("validation copy");
    }
    if (missing.length > 0) {
      summary.blockers.push({
        code: "ARTIFACT_PAGE_EXPECTED_COPY_MISSING",
        message: `Missing visible artifact signals: ${missing.join(", ")}`,
      });
      record("artifact page", "fail", `missing ${missing.join(", ")}`);
    } else {
      record("artifact page", "pass", "targetKey, artifact id, evidence and validation copy visible");
    }

    const validationButton = page.getByRole("button", { name: /Run validation|검증/i });
    if ((await validationButton.count()) > 0) {
      await validationButton.first().click();
      await page.waitForLoadState("networkidle", { timeout: 60000 }).catch(() => {});
      await page.waitForTimeout(1000);
    }
    const after = await pageText(page);
    const statusMatch =
      after.match(/\b(PASSED|REVIEW_REQUIRED|FAILED)\b/) ||
      after.match(/\b(Passed|Evidence caveat|Failed)\b/i);
    summary.validationStatus = statusMatch ? statusMatch[1] : null;
    await screenshot(page, "artifact-focused-after-validation");
    if (summary.validationStatus) {
      record("artifact validation", "pass", `visible validation status ${summary.validationStatus}`);
    } else {
      summary.blockers.push({
        code: "VALIDATION_STATUS_NOT_VISIBLE",
        message:
          "Artifact validation action did not expose PASSED, REVIEW_REQUIRED, FAILED, or mapped evidence-caveat copy.",
      });
      record("artifact validation", "fail", "no visible validation status");
    }

    await page.setViewportSize({ width: 390, height: 844 });
    await page.goto(url, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.waitForLoadState("networkidle", { timeout: 60000 }).catch(() => {});
    const overflow = await page.evaluate(
      () => document.documentElement.scrollWidth > document.documentElement.clientWidth + 2,
    );
    await screenshot(page, "artifact-focused-mobile");
    if (overflow) {
      summary.blockers.push({
        code: "MOBILE_ARTIFACT_HORIZONTAL_OVERFLOW",
        message: "Mobile artifact preview has horizontal overflow.",
      });
      record("mobile artifact", "fail", "horizontal overflow detected");
    } else {
      record("mobile artifact", "pass", "no horizontal overflow detected");
    }
  } catch (error) {
    summary.blockers.push({
      code: "ARTIFACT_FOCUSED_SMOKE_FAILED",
      message: String(error.message || error),
    });
    record("artifact focused smoke", "fail", String(error.message || error));
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
