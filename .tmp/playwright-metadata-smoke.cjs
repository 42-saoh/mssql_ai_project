const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");

const baseUrl = "http://localhost:3035";
const outDir = path.join(
  process.cwd(),
  ".tmp",
  `playwright-metadata-smoke-${new Date().toISOString().replace(/[:.]/g, "-")}`,
);
fs.mkdirSync(outDir, { recursive: true });

const summary = {
  status: "pass",
  baseUrl,
  outDir,
  forbiddenRequests: [],
  consoleMessages: [],
  pageErrors: [],
  checks: [],
  screenshots: [],
};

function record(name, classification, notes = {}) {
  summary.checks.push({ name, classification, ...notes });
  if (classification !== "pass" && summary.status === "pass") {
    summary.status = classification;
  }
}

async function screenshot(page, name) {
  const file = path.join(outDir, `${name}.png`);
  await page.screenshot({ path: file, fullPage: true, caret: "initial" });
  summary.screenshots.push(file);
}

async function expectNoPortalConfig(page, route) {
  const body = await page.locator("body").innerText({ timeout: 10_000 });
  if (body.includes("Portal API is not configured")) {
    throw new Error(`${route} showed Portal API is not configured`);
  }
}

async function assertNoHorizontalOverflow(page, route) {
  const metrics = await page.evaluate(() => ({
    innerWidth: window.innerWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  if (metrics.scrollWidth > metrics.innerWidth + 2) {
    throw new Error(
      `${route} has horizontal overflow: ${metrics.scrollWidth} > ${metrics.innerWidth}`,
    );
  }
}

async function main() {
  let browser;
  try {
    browser = await chromium.launch({ headless: true });
  } catch {
    browser = await chromium.launch({ channel: "chrome", headless: true });
  }
  const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const page = await context.newPage();

  page.on("pageerror", (error) => summary.pageErrors.push(error.message));
  page.on("console", (message) => {
    if (["warning", "error"].includes(message.type())) {
      summary.consoleMessages.push({ type: message.type(), text: message.text() });
    }
  });
  page.on("request", (request) => {
    const url = request.url();
    if (
      ["/publish", "/deploy", "/execute", "/approval-decisions"].some((fragment) =>
        url.includes(fragment),
      )
    ) {
      summary.forbiddenRequests.push({ method: request.method(), url });
    }
  });

  try {
    await page.goto(`${baseUrl}/`, { waitUntil: "domcontentloaded", timeout: 15_000 });
    await expectNoPortalConfig(page, "/");
    await page.getByText("Metadata search", { exact: false }).first().waitFor({ timeout: 10_000 });
    await screenshot(page, "home");
    record("home reachable", "pass");

    const searchUrl =
      `${baseUrl}/metadata/search?dbProfileId=ppm&query=P&limit=5` +
      "&objectTypes=PROCEDURE&objectTypes=TABLE";
    await page.goto(searchUrl, { waitUntil: "domcontentloaded", timeout: 20_000 });
    await expectNoPortalConfig(page, "/metadata/search");
    await page.getByRole("heading", { name: "Metadata search" }).waitFor({ timeout: 10_000 });
    const resultRows = await page.locator(".metadata-result-row").count();
    const evidenceRefs = await page.locator("code").count();
    if (resultRows < 5 || evidenceRefs === 0) {
      throw new Error(`metadata search expected >=5 rows and evidence refs, got ${resultRows}/${evidenceRefs}`);
    }
    await screenshot(page, "metadata-search");
    record("metadata search renders results", "pass", { resultRows, evidenceRefs });

    const beforeAnalyzeUrl = page.url();
    await page.getByRole("button", { name: "Analyze metadata" }).click();
    await Promise.race([
      page.getByText("분석 중", { exact: false }).first().waitFor({ timeout: 1_000 }),
      page.locator("button:disabled").waitFor({ timeout: 1_000 }),
    ]);
    if (page.url() !== beforeAnalyzeUrl) {
      throw new Error(`Analyze metadata navigated from ${beforeAnalyzeUrl} to ${page.url()}`);
    }
    record("metadata analyze shows immediate loading without navigation", "pass");

    const analysisOutcome = await Promise.race([
      page.getByText("Planner effectiveness", { exact: false }).waitFor({ timeout: 120_000 }).then(() => "panel"),
      page.locator(".metadata-analyze-panel .blocker-row").waitFor({ timeout: 120_000 }).then(() => "blocker"),
    ]);
    const analysisBody = await page.locator("body").innerText();
    if (analysisBody.includes("REVIEW_REQUIRED")) {
      throw new Error("Metadata analysis body exposed raw REVIEW_REQUIRED copy");
    }
    await screenshot(page, "metadata-analysis");
    record("metadata analyze completes on same page", "pass", { outcome: analysisOutcome });

    await page.goto(`${baseUrl}/metadata/dependencies`, {
      waitUntil: "domcontentloaded",
      timeout: 30_000,
    });
    await expectNoPortalConfig(page, "/metadata/dependencies");
    await page.getByRole("heading", { name: "Dependency diagnostics" }).waitFor({ timeout: 10_000 });
    const closureText = await page.locator("body").innerText();
    if (closureText.includes("P21_LIVE_PPM_REQUIRED")) {
      throw new Error("Default dependency closure still shows P21_LIVE_PPM_REQUIRED");
    }
    const closureName = await page.locator('input[name="objectName"]').inputValue();
    const closureProfile = await page.locator('select[name="dbProfileId"]').inputValue();
    if (closureProfile !== "ppm" || closureName !== "GetInspItemsCd") {
      throw new Error(`Unexpected closure defaults: ${closureProfile}/${closureName}`);
    }
    await screenshot(page, "dependency-closure");
    record("dependency closure defaults render without P21 blocker", "pass", {
      profile: closureProfile,
      objectName: closureName,
    });

    await page.goto(`${baseUrl}/metadata/dependencies?mode=resolver`, {
      waitUntil: "domcontentloaded",
      timeout: 30_000,
    });
    await expectNoPortalConfig(page, "/metadata/dependencies?mode=resolver");
    const resolverText = await page.locator("body").innerText();
    if (resolverText.includes("P21_LIVE_PPM_REQUIRED")) {
      throw new Error("Default dependency resolver still shows P21_LIVE_PPM_REQUIRED");
    }
    const referencedName = await page.locator('input[name="referencedName"]').inputValue();
    if (referencedName !== "PEX_INSP_ITEMS") {
      throw new Error(`Unexpected resolver referencedName default: ${referencedName}`);
    }
    await screenshot(page, "dependency-resolver");
    record("dependency resolver defaults render without P21 blocker", "pass", { referencedName });

    await page.setViewportSize({ width: 390, height: 844 });
    for (const route of [
      "/metadata/search?dbProfileId=ppm&query=P&limit=5&objectTypes=PROCEDURE&objectTypes=TABLE",
      "/metadata/dependencies",
      "/metadata/dependencies?mode=resolver",
    ]) {
      await page.goto(`${baseUrl}${route}`, { waitUntil: "domcontentloaded", timeout: 30_000 });
      await expectNoPortalConfig(page, route);
      await assertNoHorizontalOverflow(page, route);
    }
    await screenshot(page, "mobile-final");
    record("mobile metadata routes have no horizontal overflow", "pass");
  } catch (error) {
    record("live metadata smoke", "UI regression", { error: error.message });
  } finally {
    if (summary.forbiddenRequests.length > 0) {
      summary.status = "UI regression";
    }
    if (summary.pageErrors.length > 0) {
      summary.status = "UI regression";
    }
    fs.writeFileSync(path.join(outDir, "summary.json"), JSON.stringify(summary, null, 2));
    await browser.close();
  }

  if (summary.status !== "pass") {
    throw new Error(`metadata smoke failed: ${summary.status}; see ${outDir}`);
  }
  console.log(JSON.stringify(summary, null, 2));
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
