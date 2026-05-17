const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const BASE_URL = "http://localhost:3035";
const timestamp = new Date().toISOString().replace(/[:.]/g, "-");
const outDir = path.join(process.cwd(), ".tmp", `playwright-metadata-knowledge-links-${timestamp}`);
let activeBrowser;

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

async function capture(page, fileName) {
  await page.screenshot({
    path: path.join(outDir, fileName),
    fullPage: true,
    caret: "initial",
  });
}

async function main() {
  fs.mkdirSync(outDir, { recursive: true });

  const forbiddenRequests = [];
  const directKnowledgeRequests = [];
  const consoleMessages = [];
  const pageErrors = [];
  const network = [];

  const browser = await chromium.launch({
    headless: true,
    executablePath: "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
  });
  activeBrowser = browser;
  const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } });

  page.on("request", (request) => {
    const url = request.url();
    network.push({ method: request.method(), url });
    let parsed;
    try {
      parsed = new URL(url);
    } catch {
      return;
    }
    if (["/publish", "/deploy", "/execute", "/approval-decisions"].some((part) => parsed.pathname.includes(part))) {
      forbiddenRequests.push(url);
    }
    if (parsed.origin === BASE_URL && parsed.pathname.startsWith("/api/v1/knowledge/")) {
      directKnowledgeRequests.push(url);
    }
  });
  page.on("console", (message) => {
    if (["warning", "error"].includes(message.type())) {
      consoleMessages.push({ type: message.type(), text: message.text() });
    }
  });
  page.on("pageerror", (error) => pageErrors.push(error.message));

  const searchUrl = `${BASE_URL}/metadata/search?dbProfileId=ppm&query=P&limit=5&objectTypes=PROCEDURE&objectTypes=TABLE`;
  await page.goto(searchUrl, { waitUntil: "domcontentloaded" });
  await page.waitForLoadState("networkidle");
  assert((await page.locator("body").innerText()).includes("Metadata"), "metadata search page did not render");
  await capture(page, "metadata-search-before-analyze.png");

  const analyzeButton = page.getByRole("button", { name: /Analyze metadata/i }).first();
  await analyzeButton.waitFor({ state: "visible", timeout: 15000 });
  await analyzeButton.click();

  const assetLinkLocator = page.getByRole("link", { name: "Asset" });
  const factLinkLocator = page.getByRole("link", { name: "Facts" });
  await assetLinkLocator.first().waitFor({ timeout: 180000 });
  await capture(page, "metadata-analysis-panel.png");
  const assetLinks = await assetLinkLocator.evaluateAll((links) =>
    links.map((link) => link.getAttribute("href")),
  );
  const factLinks = await factLinkLocator.evaluateAll((links) =>
    links.map((link) => link.getAttribute("href")),
  );
  assert(assetLinks.length > 0, "metadata analysis panel did not expose asset links");
  assert(factLinks.length > 0, "metadata analysis panel did not expose facts links");
  assert(assetLinks.every((href) => href && href.startsWith("/knowledge/assets/")), `bad asset hrefs: ${assetLinks.join(", ")}`);
  assert(factLinks.every((href) => href && href.startsWith("/knowledge/assets/")), `bad facts hrefs: ${factLinks.join(", ")}`);
  assert(!assetLinks.concat(factLinks).some((href) => href.includes("/api/v1/knowledge/")), "panel still links to Web-origin API knowledge routes");

  await Promise.all([
    page.waitForURL(/\/knowledge\/assets\/[^/]+$/, { timeout: 30000 }),
    assetLinkLocator.first().click(),
  ]);
  await page.waitForLoadState("domcontentloaded");
  await page.getByText(/Knowledge asset/i).first().waitFor({ timeout: 30000 });
  await capture(page, "knowledge-asset-detail.png");
  const assetText = await page.locator("body").innerText();
  const assetTextLower = assetText.toLowerCase();
  assert(assetTextLower.includes("knowledge asset"), "knowledge asset detail page did not render");
  assert(assetTextLower.includes("version history"), "knowledge asset detail page did not show version history");

  const factsLink = page.getByRole("link", { name: /Open current facts|Facts/i }).first();
  await Promise.all([
    page.waitForURL(/\/knowledge\/assets\/[^/]+\/versions\/[^/]+\/facts$/, { timeout: 30000 }),
    factsLink.click(),
  ]);
  await page.waitForLoadState("domcontentloaded");
  await page.getByText(/Sanitized fact rows/i).first().waitFor({ timeout: 30000 });
  await capture(page, "knowledge-facts.png");
  const factsText = await page.locator("body").innerText();
  const factsTextLower = factsText.toLowerCase();
  assert(factsTextLower.includes("sanitized fact rows"), "knowledge facts page did not render sanitized facts");
  assert(factsTextLower.includes("fact graph links"), "knowledge facts page did not render graph links");

  assert(forbiddenRequests.length === 0, `forbidden requests observed: ${forbiddenRequests.join(", ")}`);
  assert(directKnowledgeRequests.length === 0, `Web-origin direct knowledge API requests observed: ${directKnowledgeRequests.join(", ")}`);
  assert(pageErrors.length === 0, `page errors observed: ${pageErrors.join("; ")}`);

  const summary = {
    status: "pass",
    baseUrl: BASE_URL,
    assetLinks,
    factLinks,
    forbiddenRequests,
    directKnowledgeRequests,
    consoleMessages,
    pageErrors,
    screenshots: fs.readdirSync(outDir).filter((name) => name.endsWith(".png")),
    networkCount: network.length,
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
