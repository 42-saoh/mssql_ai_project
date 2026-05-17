const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const BASE_URL = "http://localhost:3035";
const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
const outDir = path.join(process.cwd(), ".tmp", `playwright-request-procedure-selector-${timestamp}`);
let activeBrowser;

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

async function capture(page, name) {
  await assertNoHorizontalOverflow(page, name);
  await page.screenshot({
    path: path.join(outDir, name),
    fullPage: true,
    caret: "initial",
  });
}

async function assertNoHorizontalOverflow(page, label) {
  const metrics = await page.evaluate(() => ({
    clientWidth: document.documentElement.clientWidth,
    scrollWidth: document.documentElement.scrollWidth,
  }));
  assert(
    metrics.scrollWidth <= metrics.clientWidth + 1,
    `${label} has horizontal overflow: ${metrics.scrollWidth} > ${metrics.clientWidth}`,
  );
}

async function chooseProcedure(page, placeholder, query, expectedText) {
  const input = page.getByPlaceholder(placeholder).first();
  await input.fill(query);
  const candidate = page.getByRole("option", { name: new RegExp(expectedText, "i") }).first();
  await candidate.waitFor({ state: "visible", timeout: 30000 });
  await candidate.click();
}

async function main() {
  fs.mkdirSync(outDir, { recursive: true });
  const forbiddenRequests = [];
  const consoleMessages = [];
  const pageErrors = [];

  const browser = await chromium.launch({
    headless: true,
    executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  });
  activeBrowser = browser;
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });
  page.on("request", (request) => {
    const url = request.url();
    const pathname = new URL(url).pathname;
    if (["/publish", "/deploy", "/execute", "/approval-decisions"].some((part) => pathname.includes(part))) {
      forbiddenRequests.push(url);
    }
  });
  page.on("console", (message) => {
    if (["warning", "error"].includes(message.type())) {
      consoleMessages.push({ type: message.type(), text: message.text() });
    }
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));

  await page.goto(`${BASE_URL}/requests/new`, { waitUntil: "networkidle" });
  const requestText = await page.locator("body").innerText();
  assert(!requestText.includes("Sample request target"), "sample target section is still visible");
  assert(!requestText.includes("PPM pilot samples"), "PPM sample section is still visible");
  assert(await page.getByPlaceholder("Search procedure name").count() === 1, "single procedure combobox missing");
  await capture(page, "new-request-empty-selector.png");

  await chooseProcedure(page, "Search procedure name", "GetInsp", "dbo.GetInspItemsCd");
  await capture(page, "new-request-procedure-selected.png");
  await Promise.all([
    page.waitForURL(/\/jobs\/[^/]+$/, { timeout: 45000 }),
    page.getByRole("button", { name: "Submit request" }).click(),
  ]);
  const jobUrl = page.url();
  assert(/\/jobs\/[^/]+$/.test(jobUrl), `single submit did not redirect to job detail: ${jobUrl}`);
  await page.getByText(/Estimated progress|Workflow timeline/i).first().waitFor({ timeout: 30000 });
  await capture(page, "single-job-detail.png");

  await page.goto(`${BASE_URL}/requests/new`, { waitUntil: "networkidle" });
  await chooseProcedure(page, "Search procedure to add", "PAD_GET", "dbo.PAD_GET_BAT_LIST_PRC");
  await page.getByRole("button", { name: "Add to batch" }).click();
  const batchTargets = await page.locator("textarea[name='batchTargets']").inputValue();
  assert(batchTargets.includes("dbo.PAD_GET_BAT_LIST_PRC"), "batch helper did not add selected procedure");
  const batchForm = page.locator("form").nth(1);
  for (const label of [
    "Dependency report",
    "Java/MyBatis draft",
    "Run high-quality LLM semantic analysis",
    "Use bounded AI metadata tools",
    "Use platform context tools",
    "Allow transient SP definition in model input",
  ]) {
    const checkbox = batchForm.getByLabel(label);
    if ((await checkbox.count()) > 0 && (await checkbox.isChecked())) {
      await checkbox.uncheck();
    }
  }
  await capture(page, "batch-target-added.png");
  await Promise.all([
    page.waitForURL(/\/requests\/new\?.*batchStatus=/, { timeout: 180000 }),
    batchForm.getByRole("button", { name: "Submit batch" }).click(),
  ]);
  await page.getByText(/Batch result/i).waitFor({ timeout: 30000 });
  await capture(page, "batch-result.png");

  assert(forbiddenRequests.length === 0, `forbidden requests observed: ${forbiddenRequests.join(", ")}`);
  assert(pageErrors.length === 0, `page errors observed: ${pageErrors.join("; ")}`);
  assert(consoleMessages.length === 0, `console errors observed: ${consoleMessages.map((item) => item.text).join("; ")}`);

  const summary = {
    status: "pass",
    baseUrl: BASE_URL,
    jobUrl,
    batchUrl: page.url(),
    forbiddenRequests,
    consoleMessages,
    pageErrors,
    screenshots: fs.readdirSync(outDir).filter((name) => name.endsWith(".png")),
  };
  fs.writeFileSync(path.join(outDir, "summary.json"), JSON.stringify(summary, null, 2));
  console.log(JSON.stringify(summary, null, 2));
  await browser.close();
}

main().catch((error) => {
  fs.mkdirSync(outDir, { recursive: true });
  fs.writeFileSync(
    path.join(outDir, "summary.json"),
    JSON.stringify({ status: "fail", error: error.message, stack: error.stack }, null, 2),
  );
  console.error(error);
  if (activeBrowser) {
    activeBrowser.close().catch(() => undefined);
  }
  process.exitCode = 1;
});
