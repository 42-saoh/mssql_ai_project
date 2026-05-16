const crypto = require("crypto");
const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const baseUrl = process.env.WEB_BASE_URL || "http://localhost:3035";
const screenshotDir = path.join(
  "D:/wt/p35/.tmp",
  "playwright-mock-audit-" + new Date().toISOString().replace(/[:.]/g, "-")
);
fs.mkdirSync(screenshotDir, { recursive: true });

const chromeExecutable =
  process.env.CHROME_EXECUTABLE_PATH ||
  "C:/Program Files/Google/Chrome/Application/chrome.exe";

const forbiddenPathFragments = ["/publish", "/deploy", "/execute", "/approval-decisions"];
const staticRequestRe = /\/(?:_next\/static|_nextjs_font|favicon\.ico|__nextjs|webpack|turbopack)/i;

const summary = {
  baseUrl,
  screenshotDir,
  startedAt: new Date().toISOString(),
  auditedControls: [],
  inventory: [],
  screenshots: [],
  observedRequests: [],
  observedResponses: [],
  forbiddenRequests: [],
  consoleMessages: [],
  pageErrors: [],
  emptyMocks: [],
  expectedStaticSelfLinks: [],
  blockers: [],
  created: {},
  routeStatus: {},
  mobile: {},
  acceptancePass: false,
};

function sha(text) {
  return crypto.createHash("sha1").update(String(text || "")).digest("hex");
}

function short(text, max = 400) {
  return String(text || "").replace(/\s+/g, " ").trim().slice(0, max);
}

function classifyError(name, error) {
  const message = String(error && error.stack ? error.stack : error);
  const lower = message.toLowerCase();
  let classification = "UI regression";
  if (/econnrefused|err_connection|timeout|timed out/.test(lower)) {
    classification = "app unreachable";
  } else if (/auth|login|unauthorized|forbidden|session/.test(lower)) {
    classification = "auth/session blocker";
  } else if (/dependency|plf|ppm|mssql|metadata|unavailable|blocked/.test(lower)) {
    classification = "API/PLF/PPM prerequisite blocker";
  } else if (/openai|schema|required|structured output|llm/.test(lower)) {
    classification = "API/LLM prerequisite blocker";
  }
  summary.blockers.push({ name, classification, message: short(message, 1200) });
}

async function bodyText(page) {
  return await page.locator("body").innerText({ timeout: 30000 }).catch((error) => {
    return "BODY_ERROR: " + error.message;
  });
}

async function snapshot(page) {
  const text = await bodyText(page);
  return {
    url: page.url(),
    bodyHash: sha(text),
    bodyLength: text.length,
    bodySample: short(text),
    requestCount: summary.observedRequests.length,
    meaningfulRequestCount: summary.observedRequests.filter((item) => !staticRequestRe.test(item.url))
      .length,
  };
}

function requestDelta(before) {
  const delta = summary.observedRequests.slice(before.requestCount);
  return {
    total: delta.length,
    meaningful: delta.filter((item) => !staticRequestRe.test(item.url)).length,
    urls: delta.filter((item) => !staticRequestRe.test(item.url)).slice(0, 8),
  };
}

function recordControl(record) {
  const normalized = {
    route: record.route,
    kind: record.kind,
    name: record.name,
    selector: record.selector,
    classification: record.classification,
    notes: short(record.notes, 800),
    before: record.before
      ? {
          url: record.before.url,
          bodyHash: record.before.bodyHash,
          bodyLength: record.before.bodyLength,
        }
      : null,
    after: record.after
      ? {
          url: record.after.url,
          bodyHash: record.after.bodyHash,
          bodyLength: record.after.bodyLength,
        }
      : null,
    signal: record.signal || {},
    networkDelta: record.networkDelta || { total: 0, meaningful: 0, urls: [] },
  };
  summary.auditedControls.push(normalized);
  if (normalized.classification === "empty mock") {
    summary.emptyMocks.push(normalized);
  }
  if (normalized.classification === "expected static/self-link") {
    summary.expectedStaticSelfLinks.push(normalized);
  }
}

function hasMeaningfulChange(before, after, signal = {}, network = { meaningful: 0 }) {
  return Boolean(
    signal.stateChanged ||
      signal.visibleResult ||
      signal.responseOk ||
      signal.blockerVisible ||
      before.url !== after.url ||
      before.bodyHash !== after.bodyHash ||
      network.meaningful > 0
  );
}

async function screenshot(page, name) {
  const file = path.join(
    screenshotDir,
    `${String(summary.screenshots.length).padStart(2, "0")}-${name}.png`
  );
  await page.screenshot({ path: file, fullPage: true, timeout: 60000 });
  summary.screenshots.push(file);
  return file;
}

async function goto(page, routeOrUrl, options = {}) {
  const url = routeOrUrl.startsWith("http") ? routeOrUrl : baseUrl + routeOrUrl;
  const response = await page.goto(url, {
    waitUntil: "domcontentloaded",
    timeout: options.timeout || 180000,
  });
  await page.waitForTimeout(options.settle || 1200);
  summary.routeStatus[routeOrUrl] = response ? response.status() : null;
  return response;
}

function installWatchers(page, viewport) {
  page.on("request", (req) => {
    const item = { method: req.method(), url: req.url(), viewport };
    summary.observedRequests.push(item);
    try {
      const parsed = new URL(req.url());
      if (forbiddenPathFragments.some((fragment) => parsed.pathname.includes(fragment))) {
        summary.forbiddenRequests.push(item);
      }
    } catch {}
  });
  page.on("response", (res) => {
    const url = res.url();
    if (!staticRequestRe.test(url)) {
      summary.observedResponses.push({
        status: res.status(),
        url,
        viewport,
      });
    }
  });
  page.on("console", (msg) => {
    const text = msg.text();
    if (["error", "warning"].includes(msg.type()) && !/favicon|404 \(Not Found\)/i.test(text)) {
      summary.consoleMessages.push({ type: msg.type(), text: short(text, 1200), viewport });
    }
  });
  page.on("pageerror", (err) => {
    summary.pageErrors.push(short(String(err && err.stack ? err.stack : err), 1200));
  });
}

async function inventoryControls(page, route) {
  const controls = await page.locator("a,button,input,select,textarea").evaluateAll((els) =>
    els
      .map((el, index) => {
        const style = window.getComputedStyle(el);
        const rect = el.getBoundingClientRect();
        const visible =
          style.visibility !== "hidden" &&
          style.display !== "none" &&
          rect.width > 0 &&
          rect.height > 0;
        if (!visible) return null;
        const tag = el.tagName.toLowerCase();
        return {
          index,
          tag,
          type: el.getAttribute("type") || "",
          name: el.getAttribute("name") || "",
          text: (el.innerText || el.value || el.getAttribute("aria-label") || "").trim(),
          href: el.getAttribute("href") || "",
          disabled: Boolean(el.disabled || el.getAttribute("aria-disabled") === "true"),
        };
      })
      .filter(Boolean)
  );
  summary.inventory.push({ route, count: controls.length, controls });
}

async function auditClick(page, locator, meta, options = {}) {
  const before = await snapshot(page);
  const startRequests = summary.observedRequests.length;
  let signal = {};
  let clickError = null;
  try {
    await locator.click({ timeout: options.timeout || 60000 });
    if (options.waitForUrl) {
      await page.waitForURL(options.waitForUrl, { timeout: options.waitTimeout || 180000 });
    }
    if (options.waitForText) {
      await page.getByText(options.waitForText, { exact: false }).first().waitFor({
        timeout: options.waitTimeout || 180000,
      });
    }
    await page.waitForLoadState("domcontentloaded", { timeout: 60000 }).catch(() => {});
    await page.waitForTimeout(options.settle || 1500);
  } catch (error) {
    clickError = error;
    signal.blockerVisible = true;
  }
  const after = await snapshot(page);
  const network = requestDelta({ requestCount: startRequests });
  let classification = "pass";
  let notes = "";
  if (clickError) {
    classification = "UI regression";
    notes = clickError.message;
  } else if (options.expectedStatic && before.url === after.url && before.bodyHash === after.bodyHash) {
    classification = "expected static/self-link";
    notes = "Valid current-page or static control; no navigation expected.";
  } else if (!hasMeaningfulChange(before, after, signal, network)) {
    classification = "empty mock";
    notes = "No URL, DOM/body, state, or meaningful network/server signal changed.";
  } else {
    signal.visibleResult = before.bodyHash !== after.bodyHash || before.url !== after.url;
  }
  recordControl({ ...meta, before, after, signal, networkDelta: network, classification, notes });
}

async function auditStateChange(page, locator, meta, action) {
  const before = await snapshot(page);
  const startRequests = summary.observedRequests.length;
  let beforeValue = null;
  let afterValue = null;
  let error = null;
  try {
    beforeValue = await locator.evaluate((el) => {
      if (el.type === "checkbox" || el.type === "radio") return Boolean(el.checked);
      return el.value;
    });
    await action(locator);
    await page.waitForTimeout(400);
    afterValue = await locator.evaluate((el) => {
      if (el.type === "checkbox" || el.type === "radio") return Boolean(el.checked);
      return el.value;
    });
  } catch (err) {
    error = err;
  }
  const after = await snapshot(page);
  const network = requestDelta({ requestCount: startRequests });
  const stateChanged = beforeValue !== afterValue;
  recordControl({
    ...meta,
    before,
    after,
    signal: { stateChanged, beforeValue, afterValue },
    networkDelta: network,
    classification: error ? "UI regression" : stateChanged ? "pass" : "empty mock",
    notes: error ? error.message : stateChanged ? "Local control value changed." : "Value did not change.",
  });
}

async function auditUrl(page, route, meta, options = {}) {
  const before = await snapshot(page);
  const startRequests = summary.observedRequests.length;
  let response = null;
  let error = null;
  try {
    response = await goto(page, route, options);
  } catch (err) {
    error = err;
  }
  const after = await snapshot(page);
  const network = requestDelta({ requestCount: startRequests });
  const responseOk = response ? response.status() < 500 : false;
  const visibleResult =
    responseOk &&
    after.bodyLength > 0 &&
    !/Portal API is not configured/i.test(after.bodySample);
  recordControl({
    ...meta,
    before,
    after,
    signal: { responseOk, visibleResult, responseStatus: response ? response.status() : null },
    networkDelta: network,
    classification: error
      ? "UI regression"
      : responseOk && visibleResult
        ? "pass"
        : "API/PLF/PPM prerequisite blocker",
    notes: error ? error.message : after.bodySample,
  });
}

async function waitForJobOutcome(page, maxMs = 900000) {
  const started = Date.now();
  let text = "";
  while (Date.now() - started < maxMs) {
    text = await bodyText(page);
    const previewCount = await page.getByRole("link", { name: "Preview" }).count();
    if (previewCount > 0) return { status: "artifact_available", text };
    if (/Failed/i.test(text)) return { status: "failed", text };
    if (/Validation complete|VALIDATION_COMPLETE|Completed/i.test(text)) {
      return { status: "completed_without_preview", text };
    }
    await page.waitForTimeout(10000);
    await page.reload({ waitUntil: "domcontentloaded", timeout: 120000 }).catch(() => {});
    await page.waitForTimeout(1200);
  }
  return { status: "timeout", text };
}

async function auditRequestLocalControls(page) {
  await goto(page, "/requests/new?sample=dbo.GetInspItemsCd");
  await inventoryControls(page, "/requests/new");
  await screenshot(page, "request-form-before-submit");

  await auditClick(
    page,
    page.getByRole("link", { name: /dbo\.PAD_GET_BAT_LIST_PRC/ }).first(),
    {
      route: "/requests/new",
      kind: "sample link",
      name: "dbo.PAD_GET_BAT_LIST_PRC sample",
      selector: 'link[name*="dbo.PAD_GET_BAT_LIST_PRC"]',
    },
    { waitForUrl: /sample=dbo\.PAD_GET_BAT_LIST_PRC/ }
  );
  await goto(page, "/requests/new?sample=dbo.GetInspItemsCd");

  await auditStateChange(page, page.locator('input[name="name"]').first(), {
    route: "/requests/new",
    kind: "text input",
    name: "Procedure name",
    selector: 'input[name="name"]',
  }, async (control) => control.fill("GetInspItemsCdAudit"));
  await goto(page, "/requests/new?sample=dbo.GetInspItemsCd");

  await auditStateChange(page, page.locator('input[name="outputs"]').first(), {
    route: "/requests/new",
    kind: "checkbox",
    name: "Requested output checkbox",
    selector: 'input[name="outputs"]',
  }, async (control) => control.click());

  await auditStateChange(page, page.locator('input[name="includeModernizationHints"]').first(), {
    route: "/requests/new",
    kind: "checkbox",
    name: "Include modernization hints",
    selector: 'input[name="includeModernizationHints"]',
  }, async (control) => control.click());

  await auditStateChange(page, page.locator('select[name="llmProfileId"]').first(), {
    route: "/requests/new",
    kind: "select",
    name: "LLM profile",
    selector: 'select[name="llmProfileId"]',
  }, async (control) => control.selectOption("openai_fast_test"));

  await auditStateChange(page, page.locator('textarea[name="batchTargets"]').first(), {
    route: "/requests/new",
    kind: "textarea",
    name: "Batch targets",
    selector: 'textarea[name="batchTargets"]',
  }, async (control) => control.fill("dbo.GetInspItemsCd\ndbo.PAD_GET_BAT_LIST_PRC"));
}

async function submitSingleRequest(page, sampleId) {
  await goto(page, `/requests/new?sample=${encodeURIComponent(sampleId)}`);
  const schema = await page.locator('input[name="schema"]').first().inputValue().catch(() => "dbo");
  const name = await page.locator('input[name="name"]').first().inputValue().catch(() => sampleId.replace(/^dbo\./, ""));
  const before = await snapshot(page);
  const startRequests = summary.observedRequests.length;
  await page.getByRole("button", { name: "Submit request" }).first().click({ timeout: 30000 });
  await page.waitForURL(/\/jobs\/[^/?#]+/, { timeout: 900000 });
  await page.waitForLoadState("domcontentloaded", { timeout: 120000 }).catch(() => {});
  await page.waitForTimeout(1500);
  const outcome = await waitForJobOutcome(page);
  const after = await snapshot(page);
  const network = requestDelta({ requestCount: startRequests });
  const jobId = page.url().match(/\/jobs\/([^/?#]+)/)?.[1] || null;
  summary.created.jobId = jobId;
  summary.created.jobUrl = page.url();
  summary.created.jobOutcome = outcome.status;
  summary.created.jobTarget = `${schema}.${name}`;
  await screenshot(page, "job-detail");
  recordControl({
    route: "/requests/new",
    kind: "form submit",
    name: "Submit request",
    selector: 'button[name="Submit request"]',
    before,
    after,
    signal: {
      visibleResult: /Workflow job|Draft artifacts|Validation flow/i.test(outcome.text),
      responseOk: true,
      jobId,
      outcome: outcome.status,
    },
    networkDelta: network,
    classification: /\/jobs\//.test(after.url) ? "pass" : "empty mock",
    notes: short(outcome.text, 800),
  });
  return { jobId, outcome, text: outcome.text };
}

async function submitBatch(page) {
  await goto(page, "/requests/new?sample=dbo.GetInspItemsCd");
  const before = await snapshot(page);
  const startRequests = summary.observedRequests.length;
  await page.getByRole("button", { name: "Submit batch" }).click({ timeout: 30000 });
  await page.waitForURL(/batchStatus=/, { timeout: 180000 });
  await page.waitForLoadState("domcontentloaded", { timeout: 60000 }).catch(() => {});
  await page.waitForTimeout(1500);
  const after = await snapshot(page);
  const network = requestDelta({ requestCount: startRequests });
  recordControl({
    route: "/requests/new",
    kind: "form submit",
    name: "Submit batch",
    selector: 'button[name="Submit batch"]',
    before,
    after,
    signal: {
      visibleResult: /Batch result|Accepted|Rejected/i.test(after.bodySample),
      responseOk: true,
    },
    networkDelta: network,
    classification: /batchStatus=/.test(after.url) && /Batch result/i.test(after.bodySample)
      ? "pass"
      : "empty mock",
    notes: after.bodySample,
  });
}

async function auditJobAndArtifact(page) {
  await goto(page, summary.created.jobUrl);
  await inventoryControls(page, "/jobs/[jobId]");
  const firstPreview = page.getByRole("link", { name: "Preview" }).first();
  if ((await firstPreview.count()) === 0) {
    summary.blockers.push({
      name: "artifact preview",
      classification: "API/LLM prerequisite blocker",
      message: "Created job did not expose a Preview link.",
    });
    return;
  }

  const assetLinks = page.locator('a[href^="/api/v1/knowledge/assets/"]');
  const assetCount = await assetLinks.count();
  if (assetCount > 0) {
    const href = await assetLinks.first().getAttribute("href");
    await auditUrl(page, href, {
      route: "/jobs/[jobId]",
      kind: "api link",
      name: "Knowledge asset/facts link",
      selector: 'a[href^="/api/v1/knowledge/assets/"]',
    });
    await goto(page, summary.created.jobUrl);
  }

  const before = await snapshot(page);
  const startRequests = summary.observedRequests.length;
  await firstPreview.click({ timeout: 30000 });
  await page.waitForURL(/\/artifacts\/[^/?#]+/, { timeout: 120000 });
  await page.waitForLoadState("domcontentloaded", { timeout: 60000 }).catch(() => {});
  await page.waitForTimeout(1200);
  const after = await snapshot(page);
  const network = requestDelta({ requestCount: startRequests });
  const artifactId = page.url().match(/\/artifacts\/([^/?#]+)/)?.[1] || null;
  summary.created.artifactId = artifactId;
  summary.created.artifactUrl = page.url();
  recordControl({
    route: "/jobs/[jobId]",
    kind: "link",
    name: "Artifact Preview",
    selector: 'link[name="Preview"]',
    before,
    after,
    signal: { visibleResult: /Artifact preview|Draft artifact content/i.test(after.bodySample), artifactId },
    networkDelta: network,
    classification: /\/artifacts\//.test(after.url) ? "pass" : "empty mock",
    notes: after.bodySample,
  });

  await inventoryControls(page, "/artifacts/[artifactId]");
  await screenshot(page, "artifact-before-validation");

  const validateButton = page.getByRole("button", { name: "Run validation" });
  if ((await validateButton.count()) > 0) {
    const validateBefore = await snapshot(page);
    const validateStart = summary.observedRequests.length;
    await validateButton.click({ timeout: 30000 });
    await page.waitForLoadState("domcontentloaded", { timeout: 120000 }).catch(() => {});
    await page.waitForTimeout(2000);
    const validateAfter = await snapshot(page);
    const validateNetwork = requestDelta({ requestCount: validateStart });
    const validationVisible = /Validation|Evidence and policy checks|PASSED|Evidence caveat|REVIEW_REQUIRED/i.test(
      validateAfter.bodySample
    );
    summary.created.validationVisible = validationVisible;
    recordControl({
      route: "/artifacts/[artifactId]",
      kind: "form submit",
      name: "Run validation",
      selector: 'button[name="Run validation"]',
      before: validateBefore,
      after: validateAfter,
      signal: { visibleResult: validationVisible, responseOk: validateNetwork.meaningful > 0 },
      networkDelta: validateNetwork,
    classification: validationVisible || validateNetwork.meaningful > 0 ? "pass" : "empty mock",
      notes: validateAfter.bodySample,
    });
    await screenshot(page, "artifact-after-validation");
  }

  const backLink = page.getByRole("link", { name: "Back to job" });
  if ((await backLink.count()) > 0) {
    await auditClick(
      page,
      backLink,
      {
        route: "/artifacts/[artifactId]",
        kind: "link",
        name: "Back to job",
        selector: 'link[name="Back to job"]',
      },
      { waitForUrl: /\/jobs\// }
    );
  }
}

async function auditMetadataSearch(page) {
  await goto(page, "/metadata/search?dbProfileId=ppm&query=P&limit=5&objectTypes=PROCEDURE&objectTypes=TABLE");
  await inventoryControls(page, "/metadata/search");
  await screenshot(page, "metadata-search");

  await auditStateChange(page, page.locator('input[name="query"]').first(), {
    route: "/metadata/search",
    kind: "text input",
    name: "Search query",
    selector: 'input[name="query"]',
  }, async (control) => control.fill("PA"));

  await goto(page, "/metadata/search?dbProfileId=ppm&query=P&limit=5&objectTypes=PROCEDURE&objectTypes=TABLE");
  await auditClick(
    page,
    page.getByRole("button", { name: "Search metadata" }),
    {
      route: "/metadata/search",
      kind: "GET form submit",
      name: "Search metadata",
      selector: 'button[name="Search metadata"]',
    },
    { waitForText: "Search results", waitTimeout: 180000 }
  );

  await goto(page, "/metadata/search?dbProfileId=ppm&query=P&limit=5&objectTypes=PROCEDURE&objectTypes=TABLE");
  const before = await snapshot(page);
  const startRequests = summary.observedRequests.length;
    await page.getByRole("button", { name: "Analyze metadata" }).click({
      timeout: 60000,
      noWaitAfter: true,
    });
    await page.waitForURL(/analyze=1/, { timeout: 240000 }).catch(() => {});
  await page.waitForLoadState("domcontentloaded", { timeout: 240000 }).catch(() => {});
  await page.waitForTimeout(2000);
  const after = await snapshot(page);
  const network = requestDelta({ requestCount: startRequests });
  const analysisVisible = /AI-MCP metadata analysis|Facts|Tools|Object|Dependency graph|DTO/i.test(
    after.bodySample
  );
  recordControl({
    route: "/metadata/search",
    kind: "GET form submit",
    name: "Analyze metadata",
    selector: 'button[name="Analyze metadata"]',
    before,
    after,
    signal: { visibleResult: analysisVisible, responseOk: network.meaningful > 0 },
    networkDelta: network,
    classification: analysisVisible
      ? "pass"
      : /unavailable|blocked|failed/i.test(after.bodySample)
        ? "API/PLF/PPM prerequisite blocker"
        : "empty mock",
    notes: after.bodySample,
  });
  await screenshot(page, "metadata-analysis");
}

function dependencyCandidateFromText(text) {
  const matches = [...String(text || "").matchAll(/\bdbo\.[A-Za-z0-9_]+\b/g)].map((match) => match[0]);
  return matches.find((value) => !/GetInspItemsCd$/i.test(value)) || null;
}

async function auditDependencies(page) {
  const closureRoute =
    "/metadata/dependencies?mode=closure&dbProfileId=ppm&schema=dbo&objectName=GetInspItemsCd&objectType=PROCEDURE&maxDepth=2";
  await goto(page, closureRoute, { timeout: 240000 });
  await inventoryControls(page, "/metadata/dependencies?mode=closure");
  await screenshot(page, "dependency-closure");

  await auditStateChange(page, page.locator('input[name="includeReviewRequired"]').first(), {
    route: "/metadata/dependencies",
    kind: "checkbox",
    name: "Include evidence-caveated graph items",
    selector: 'input[name="includeReviewRequired"]',
  }, async (control) => control.click());

  await auditClick(
    page,
    page.getByRole("button", { name: "Invoke closure" }),
    {
      route: "/metadata/dependencies",
      kind: "GET form submit",
      name: "Invoke closure",
      selector: 'button[name="Invoke closure"]',
    },
    { waitForText: "Evidence refs", waitTimeout: 240000 }
  );
  const closureText = await bodyText(page);
  const candidate = dependencyCandidateFromText(closureText);
  summary.created.dependencyCandidate = candidate;

  await auditClick(
    page,
    page.getByRole("link", { name: "Resolve reference" }),
    {
      route: "/metadata/dependencies",
      kind: "tab link",
      name: "Resolve reference",
      selector: 'link[name="Resolve reference"]',
    },
    { waitForUrl: /mode=resolver/ }
  );

  if (!candidate) {
    summary.blockers.push({
      name: "dependency resolver candidate",
      classification: "live-data limitation",
      message: "Closure rendered, but no dependency candidate could be parsed for resolver mode.",
    });
    return;
  }
  const [referencedSchema, referencedName] = candidate.split(".", 2);
  const resolverRoute =
    `/metadata/dependencies?mode=resolver&dbProfileId=ppm&sourceSchema=dbo&sourceName=GetInspItemsCd&sourceObjectType=PROCEDURE&referencedSchema=${encodeURIComponent(referencedSchema)}&referencedName=${encodeURIComponent(referencedName)}`;
  await goto(page, resolverRoute, { timeout: 240000 });
  await screenshot(page, "dependency-resolver");
  await auditClick(
    page,
    page.getByRole("button", { name: "Invoke resolver" }),
    {
      route: "/metadata/dependencies",
      kind: "GET form submit",
      name: "Invoke resolver",
      selector: 'button[name="Invoke resolver"]',
    },
    { waitForText: "Evidence refs", waitTimeout: 240000 }
  );
}

async function auditHome(page) {
  const response = await goto(page, "/");
  await inventoryControls(page, "/");
  await screenshot(page, "home-inventory");
  const text = await bodyText(page);
  if (!response || response.status() >= 500) {
    summary.blockers.push({
      name: "home",
      classification: "app unreachable",
      message: `status=${response ? response.status() : "no response"}`,
    });
  }
  if (/Portal API is not configured/i.test(text)) {
    summary.blockers.push({
      name: "home configuration",
      classification: "API/PLF/PPM prerequisite blocker",
      message: "Portal API is not configured is visible.",
    });
  }
  for (const item of [
    { name: "New request", url: /\/requests\/new/ },
    { name: "Metadata search", url: /\/metadata\/search/ },
    { name: "Dependency diagnostics", url: /\/metadata\/dependencies/ },
  ]) {
    await goto(page, "/");
    await auditClick(
      page,
      page.getByRole("link", { name: item.name }).first(),
      { route: "/", kind: "nav link", name: item.name, selector: `link[name="${item.name}"]` },
      { waitForUrl: item.url }
    );
  }
}

async function noOverflow(page, route) {
  const result = await page.evaluate(() => ({
    innerWidth: window.innerWidth,
    scrollWidth: document.documentElement.scrollWidth,
    bodyScrollWidth: document.body ? document.body.scrollWidth : 0,
  }));
  const maxScroll = Math.max(result.scrollWidth, result.bodyScrollWidth);
  const before = await snapshot(page);
  recordControl({
    route,
    kind: "mobile layout",
    name: "No horizontal overflow",
    selector: "document",
    before,
    after: before,
    signal: { stateChanged: maxScroll <= result.innerWidth + 2, result },
    classification: maxScroll <= result.innerWidth + 2 ? "pass" : "UI regression",
    notes: JSON.stringify(result),
  });
}

async function auditMobile(browser) {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    ignoreHTTPSErrors: true,
  });
  const page = await context.newPage();
  installWatchers(page, "mobile");
  for (const [route, name] of [
    ["/", "mobile-home"],
    ["/requests/new?sample=dbo.GetInspItemsCd", "mobile-request"],
    [summary.created.jobUrl || "/", "mobile-job"],
    [summary.created.artifactUrl || "/", "mobile-artifact"],
  ]) {
    await goto(page, route, { timeout: 180000 });
    await inventoryControls(page, route);
    await noOverflow(page, route);
    await screenshot(page, name);
  }
  summary.mobile.checked = true;
  await context.close();
}

async function main() {
  let browser;
  try {
    browser = await chromium.launch({
      headless: true,
      executablePath: chromeExecutable,
      args: ["--no-sandbox", "--disable-dev-shm-usage"],
    });
    const context = await browser.newContext({
      viewport: { width: 1440, height: 1000 },
      ignoreHTTPSErrors: true,
    });
    const page = await context.newPage();
    installWatchers(page, "desktop");

    await auditHome(page);
    await auditRequestLocalControls(page);
    const primary = await submitSingleRequest(page, "dbo.GetInspItemsCd");
    if (primary.outcome.status !== "artifact_available") {
      summary.blockers.push({
        name: "primary request artifact",
        classification: "API/LLM prerequisite blocker",
        message: `Primary job outcome was ${primary.outcome.status}; artifact audit may be limited.`,
      });
      await submitSingleRequest(page, "dbo.PAD_GET_BAT_LIST_PRC").catch((error) =>
        classifyError("fallback request", error)
      );
    }
    await auditJobAndArtifact(page);
    await submitBatch(page).catch((error) => classifyError("batch submit", error));
    await auditMetadataSearch(page).catch((error) => classifyError("metadata search/analyze", error));
    await auditDependencies(page).catch((error) => classifyError("dependency diagnostics", error));
    await auditUrl(page, "/review/decision", {
      route: "/review/decision",
      kind: "removed route",
      name: "Review decision route",
      selector: "direct URL",
    });
    await context.close();
    await auditMobile(browser);
  } catch (error) {
    classifyError("audit runner", error);
  } finally {
    if (browser) await browser.close().catch(() => {});
    summary.finishedAt = new Date().toISOString();
    summary.acceptancePass =
      summary.emptyMocks.length === 0 &&
      summary.forbiddenRequests.length === 0 &&
      summary.pageErrors.length === 0 &&
      !summary.auditedControls.some((control) => control.classification === "UI regression") &&
      !summary.blockers.some((blocker) =>
        ["app unreachable", "auth/session blocker", "UI regression"].includes(blocker.classification)
      );
    const file = path.join(screenshotDir, "summary.json");
    fs.writeFileSync(file, JSON.stringify(summary, null, 2));
    console.log(
      JSON.stringify(
        {
          summaryPath: file,
          acceptancePass: summary.acceptancePass,
          auditedControls: summary.auditedControls.length,
          inventoryRoutes: summary.inventory.length,
          emptyMocks: summary.emptyMocks.length,
          expectedStaticSelfLinks: summary.expectedStaticSelfLinks.length,
          forbiddenRequests: summary.forbiddenRequests.length,
          consoleMessages: summary.consoleMessages.length,
          pageErrors: summary.pageErrors.length,
          blockers: summary.blockers,
          created: summary.created,
        },
        null,
        2
      )
    );
  }
}

main();
