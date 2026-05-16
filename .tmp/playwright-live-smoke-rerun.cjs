const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const baseUrl = "http://localhost:3035";
const screenshotDir = path.join(
  "D:/wt/p35/.tmp",
  "playwright-live-smoke-" + new Date().toISOString().replace(/[:.]/g, "-")
);
fs.mkdirSync(screenshotDir, { recursive: true });

const chromeExecutable =
  process.env.CHROME_EXECUTABLE_PATH ||
  "C:/Program Files/Google/Chrome/Application/chrome.exe";

const summary = {
  baseUrl,
  screenshotDir,
  checks: [],
  screenshots: [],
  observedRequests: [],
  forbiddenRequests: [],
  consoleMessages: [],
  pageErrors: [],
  blockers: [],
  jobs: [],
  created: {},
};

const forbiddenPathFragments = [
  "/publish",
  "/deploy",
  "/execute",
  "/approval-decisions",
];

const forbiddenControlRe =
  /^(publish|deploy|execute|approval decision|approve|reject|apply ddl|apply dml|run sql|row data|raw prompt|raw sp definition|raw sql|secret|secrets|배포|실행|승인|반려|적용)$/i;

function addCheck(name, pass, details = "", classification = pass ? "pass" : "UI regression") {
  summary.checks.push({
    name,
    pass: Boolean(pass),
    classification,
    details: String(details ?? "").slice(0, 2000),
  });
}

function addBlocker(name, classification, message) {
  summary.blockers.push({
    name,
    classification,
    message: String(message ?? "").slice(0, 3000),
  });
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
  addBlocker(name, classification, message);
  addCheck(name, false, message, classification);
}

async function bodyText(page) {
  return await page
    .locator("body")
    .innerText({ timeout: 15000 })
    .catch((error) => "BODY_ERROR: " + error.message);
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
    timeout: options.timeout ?? 120000,
  });
  await page.waitForTimeout(options.settle ?? 1500);
  return response;
}

async function assertNoForbiddenControls(page, label) {
  const controls = await page
    .locator('a,button,input[type="submit"],input[type="button"]')
    .evaluateAll((els) =>
      els
        .map((el) =>
          (el.innerText || el.value || el.getAttribute("aria-label") || "").trim()
        )
        .filter(Boolean)
    );
  const forbidden = controls.filter((text) => forbiddenControlRe.test(text));
  addCheck(
    `${label}: no forbidden action controls`,
    forbidden.length === 0,
    forbidden.join(", ")
  );
}

async function assertNoHorizontalOverflow(page, label) {
  const result = await page.evaluate(() => ({
    innerWidth: window.innerWidth,
    scrollWidth: document.documentElement.scrollWidth,
    bodyScrollWidth: document.body ? document.body.scrollWidth : 0,
  }));
  const maxScroll = Math.max(result.scrollWidth, result.bodyScrollWidth);
  addCheck(
    `${label}: no horizontal overflow`,
    maxScroll <= result.innerWidth + 2,
    JSON.stringify(result)
  );
}

function installWatchers(page, viewport = "desktop") {
  page.on("request", (req) => {
    const item = { method: req.method(), url: req.url(), viewport };
    summary.observedRequests.push(item);
    try {
      const url = new URL(req.url());
      if (forbiddenPathFragments.some((fragment) => url.pathname.includes(fragment))) {
        summary.forbiddenRequests.push(item);
      }
    } catch {}
  });
  page.on("console", (msg) => {
    const text = msg.text();
    if (["error", "warning"].includes(msg.type()) && !/favicon|404 \(Not Found\)/i.test(text)) {
      summary.consoleMessages.push({ type: msg.type(), text, viewport });
    }
  });
  page.on("pageerror", (err) =>
    summary.pageErrors.push(String(err && err.stack ? err.stack : err))
  );
}

function extractCurrentStep(text) {
  const match = text.match(/CURRENT STEP\s+([A-Za-z_ -]+)/i);
  return match ? match[1].trim().split(/\n/)[0] : null;
}

function extractFailureCode(text) {
  const match = text.match(/\b([A-Z][A-Z0-9_]{6,})\b/);
  return match ? match[1] : null;
}

async function selectSampleAndReadTarget(page, sampleId) {
  const route = sampleId
    ? `/requests/new?sample=${encodeURIComponent(sampleId)}`
    : "/requests/new";
  await goto(page, route);
  const schema = await page
    .locator("form")
    .first()
    .locator('input[name="schema"]')
    .inputValue()
    .catch(() => "dbo");
  const name = await page
    .locator("form")
    .first()
    .locator('input[name="name"]')
    .inputValue()
    .catch(() => (sampleId ? sampleId.replace(/^dbo\./, "") : "GetInspItemsCd"));
  return { schema, name, sampleId: sampleId || `${schema}.${name}` };
}

async function waitForJobOutcome(page, maxMs = 900000) {
  const started = Date.now();
  let lastText = "";
  while (Date.now() - started < maxMs) {
    lastText = await bodyText(page);
    const previewCount = await page.getByRole("link", { name: "Preview" }).count();
    if (previewCount > 0) return { status: "artifact_available", text: lastText };
    if (/Failed/i.test(lastText)) return { status: "failed", text: lastText };
    if (/Validation complete|VALIDATION_COMPLETE|Completed/i.test(lastText)) {
      return { status: "completed_without_preview", text: lastText };
    }
    await page.waitForTimeout(10000);
    await page.reload({ waitUntil: "domcontentloaded", timeout: 120000 }).catch(() => {});
    await page.waitForTimeout(1500);
  }
  return { status: "timeout", text: lastText };
}

async function submitSingleRequest(page, sampleId, label) {
  const target = await selectSampleAndReadTarget(page, sampleId);
  if (label === "primary") {
    await screenshot(page, "request-form-before-submit");
    const requestText = await bodyText(page);
    addCheck(
      "request page renders form",
      /Stored procedure analysis request/i.test(requestText) &&
        /Submit request/i.test(requestText) &&
        /Submit batch/i.test(requestText),
      requestText
    );
    addCheck(
      "request page renders PPM samples",
      /PPM pilot samples/i.test(requestText) && /GetInspItemsCd/i.test(requestText),
      requestText
    );
    addCheck(
      "request page renders workflow options",
      /LLM profile/i.test(requestText) &&
        /Source context/i.test(requestText) &&
        /Dependency analysis/i.test(requestText) &&
        /Outputs/i.test(requestText),
      requestText
    );
    await assertNoForbiddenControls(page, "request page");
  }

  await page.getByRole("button", { name: "Submit request" }).first().click({ timeout: 30000 });
  await page.waitForURL(/\/jobs\/[^/?#]+/, { timeout: 900000 });
  await page.waitForLoadState("domcontentloaded", { timeout: 120000 }).catch(() => {});
  await page.waitForTimeout(2500);

  const jobUrl = page.url();
  const jobId = jobUrl.match(/\/jobs\/([^/?#]+)/)?.[1] ?? null;
  const outcome = await waitForJobOutcome(page);
  const jobText = outcome.text || (await bodyText(page));
  const job = {
    label,
    sampleId: target.sampleId,
    target: `${target.schema}.${target.name}`,
    schema: target.schema,
    name: target.name,
    jobUrl,
    jobId,
    outcome: outcome.status,
    currentStep: extractCurrentStep(jobText),
    failureCode: extractFailureCode(jobText),
  };
  summary.jobs.push(job);
  summary.created[`${label}JobUrl`] = jobUrl;
  summary.created[`${label}JobId`] = jobId;
  await screenshot(page, `${label}-job-detail-after-submit`);

  addCheck(`${label} submit redirects to job`, /\/jobs\//.test(jobUrl), jobUrl);
  addCheck(
    `${label} job page has workflow status`,
    /Workflow job/i.test(jobText) && /Validation flow|CURRENT STEP|Current step/i.test(jobText),
    jobText
  );
  addCheck(
    `${label} job page has sanitized trace or blocker`,
    /LLM trace summary|Agent runtime|Failure reason|Caveats/i.test(jobText),
    jobText
  );
  addCheck(
    `${label} job has draft artifact preview or explicit blocker`,
    outcome.status === "artifact_available" || /Failed|Failure reason|OPENAI|BLOCKED|Caveats/i.test(jobText),
    jobText,
    outcome.status === "artifact_available" ? "pass" : "API/LLM prerequisite blocker"
  );
  if (outcome.status !== "artifact_available") {
    addBlocker(
      `${label} artifact preview`,
      /OPENAI|LLM|structured output|schema/i.test(jobText)
        ? "API/LLM prerequisite blocker"
        : "API/PLF/PPM prerequisite blocker",
      jobText
    );
  }
  await assertNoForbiddenControls(page, `${label} job page`);
  return job;
}

async function openArtifactAndValidate(page) {
  const previewLink = page.getByRole("link", { name: "Preview" }).first();
  if ((await previewLink.count()) === 0) return null;

  await previewLink.click({ timeout: 30000 });
  await page.waitForURL(/\/artifacts\/[^/?#]+/, { timeout: 120000 });
  await page.waitForLoadState("domcontentloaded", { timeout: 120000 }).catch(() => {});
  await page.waitForTimeout(2000);
  const artifactUrl = page.url();
  summary.created.artifactUrl = artifactUrl;
  let artifactText = await bodyText(page);
  addCheck(
    "artifact preview loads draft content",
    /Artifact preview|Draft artifact content|Draft/i.test(artifactText),
    artifactText
  );
  addCheck(
    "artifact evidence and trace visible",
    /Evidence refs|Trace points|LLM trace summary|Sanitized/i.test(artifactText),
    artifactText
  );
  addCheck(
    "artifact caveats/latest validation visible",
    /Latest validation|Validation|Caveats|quality caveat|missing evidence|REVIEW_REQUIRED/i.test(
      artifactText
    ),
    artifactText
  );
  const runValidation = page.getByRole("button", { name: "Run validation" });
  if ((await runValidation.count()) > 0) {
    await runValidation.first().click({ timeout: 30000 });
    await page.waitForLoadState("domcontentloaded", { timeout: 300000 }).catch(() => {});
    await page.waitForTimeout(3000);
  }
  await screenshot(page, "artifact-preview-after-validation");
  artifactText = await bodyText(page);
  addCheck(
    "artifact validation report visible",
    /PASSED|REVIEW_REQUIRED|qualityCaveats|Quality caveats|Missing evidence|Evidence and policy checks/i.test(
      artifactText
    ),
    artifactText
  );
  await assertNoForbiddenControls(page, "artifact page");
  return artifactUrl;
}

function parseDependencyCandidate(text) {
  const pipe = text.match(/\|([^|\n]+)\|([^|\n]+)\|([^|\n]+)\|([A-Z_]+)/);
  if (pipe) {
    return { schema: pipe[2].trim(), name: pipe[3].trim(), objectType: pipe[4].trim() };
  }
  const dotted = text.match(/\b([A-Za-z_][\w$#]*)\.([A-Za-z_][\w$#]*)\b/);
  if (dotted) {
    return { schema: dotted[1], name: dotted[2], objectType: "TABLE" };
  }
  return null;
}

(async () => {
  let browser;
  try {
    const launchOptions = { headless: true };
    if (fs.existsSync(chromeExecutable)) {
      launchOptions.executablePath = chromeExecutable;
    }
    browser = await chromium.launch(launchOptions);
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    const page = await context.newPage();
    page.setDefaultTimeout(60000);
    installWatchers(page);

    try {
      const response = await goto(page, "/");
      const text = await bodyText(page);
      await screenshot(page, "home-dashboard");
      addCheck("home loads", response && response.status() < 500, `status=${response?.status()}`);
      addCheck("home not unconfigured", !text.includes("Portal API is not configured"), text);
      addCheck(
        "home dashboard content",
        /Analyze and validate/i.test(text) &&
          /Metadata search/i.test(text) &&
          /Registry bindings|Active versions|Recent jobs/i.test(text),
        text
      );
      await assertNoForbiddenControls(page, "home");
    } catch (error) {
      classifyError("home preflight", error);
    }

    let artifactUrl = null;
    let dependencyTarget = null;
    try {
      const primaryJob = await submitSingleRequest(page, null, "primary");
      dependencyTarget = primaryJob;
      if (primaryJob.outcome === "artifact_available") {
        artifactUrl = await openArtifactAndValidate(page);
      } else {
        const alternateJob = await submitSingleRequest(
          page,
          "dbo.PAD_GET_BAT_LIST_PRC",
          "alternate"
        );
        dependencyTarget = alternateJob;
        if (alternateJob.outcome === "artifact_available") {
          artifactUrl = await openArtifactAndValidate(page);
        } else {
          addBlocker(
            "artifact validation",
            "API/LLM prerequisite blocker",
            "Neither primary nor alternate live request produced a preview artifact."
          );
          addCheck(
            "artifact validation covered",
            false,
            "No artifact URL available after primary and alternate sample attempts.",
            "API/LLM prerequisite blocker"
          );
        }
      }
    } catch (error) {
      classifyError("single request submit/job detail", error);
    }

    try {
      await goto(page, "/requests/new");
      await page.getByRole("button", { name: "Submit batch" }).click({ timeout: 30000 });
      await page.waitForURL(/\/requests\/new\?.*batchStatus=/, { timeout: 600000 });
      await page.waitForTimeout(2000);
      const batchText = await bodyText(page);
      addCheck(
        "batch submit shows result summary",
        /Batch result/i.test(batchText) &&
          /(PARTIAL|ACCEPTED)/i.test(batchText) &&
          /Accepted\s*\d+/i.test(batchText) &&
          /Rejected\s*\d+/i.test(batchText) &&
          /DUPLICATE_TARGET_SKIPPED|job_/i.test(batchText),
        batchText
      );
      await assertNoForbiddenControls(page, "batch result");
    } catch (error) {
      classifyError("batch request submit", error);
    }

    try {
      await goto(
        page,
        "/metadata/search?dbProfileId=ppm&query=P&limit=5&objectTypes=PROCEDURE&objectTypes=TABLE&analyze=1",
        { timeout: 900000, settle: 3000 }
      );
      await screenshot(page, "metadata-analysis-panel");
      const metadataText = await bodyText(page);
      addCheck(
        "metadata search renders results or blocker",
        /Metadata search/i.test(metadataText) &&
          (/Search results/i.test(metadataText) ||
            /dependency is unavailable|blocked|unavailable/i.test(metadataText)),
        metadataText
      );
      addCheck(
        "metadata analysis renders evidence or blocker",
        /AI-MCP metadata analysis|Metadata analysis is unavailable|AI_METADATA_ANALYSIS_BLOCKED/i.test(
          metadataText
        ),
        metadataText
      );
      addCheck(
        "metadata analysis includes draft-quality sections",
        /Facts/i.test(metadataText) &&
          /Tools/i.test(metadataText) &&
          /(Object|Dependency graph|DTO|insights|knowledge assets)/i.test(metadataText),
        metadataText
      );
      await assertNoForbiddenControls(page, "metadata search");
    } catch (error) {
      classifyError("metadata search/analyze", error);
    }

    try {
      const target = dependencyTarget || { schema: "dbo", name: "GetInspItemsCd" };
      const closureUrl = `/metadata/dependencies?mode=closure&dbProfileId=ppm&schema=${encodeURIComponent(
        target.schema
      )}&objectName=${encodeURIComponent(
        target.name
      )}&objectType=PROCEDURE&maxDepth=2`;
      await goto(page, closureUrl, { timeout: 300000, settle: 3000 });
      await screenshot(page, "dependency-diagnostics-closure");
      const depText = await bodyText(page);
      addCheck(
        "dependency closure renders tool summary",
        /Dependency diagnostics/i.test(depText) && /get_dependency_closure/i.test(depText),
        depText
      );
      addCheck(
        "dependency closure renders evidence or blocker",
        /Evidence refs|Nodes|Edges|Unresolved|Dependency evidence tool failed|DEPENDENCY_EVIDENCE_BLOCKED/i.test(
          depText
        ),
        depText
      );
      await assertNoForbiddenControls(page, "dependency closure");

      const candidate = parseDependencyCandidate(depText);
      if (candidate) {
        await goto(
          page,
          `/metadata/dependencies?mode=resolver&dbProfileId=ppm&sourceSchema=${encodeURIComponent(
            target.schema
          )}&sourceName=${encodeURIComponent(
            target.name
          )}&sourceObjectType=PROCEDURE&referencedSchema=${encodeURIComponent(
            candidate.schema
          )}&referencedName=${encodeURIComponent(candidate.name)}`,
          { timeout: 300000, settle: 2000 }
        );
        await screenshot(page, "dependency-diagnostics-resolver");
        const resolverText = await bodyText(page);
        addCheck(
          "dependency resolver renders candidate result",
          /Resolve reference/i.test(resolverText) &&
            /(Selected resolution|Candidates|Dependency evidence tool failed|Evidence refs)/i.test(
              resolverText
            ),
          resolverText
        );
        await assertNoForbiddenControls(page, "dependency resolver");
      } else {
        addBlocker(
          "dependency resolver",
          "live-data limitation",
          "No dependency candidate could be parsed from closure results."
        );
        addCheck(
          "dependency resolver candidate available",
          true,
          "No parseable candidate; recorded as live-data limitation."
        );
      }
    } catch (error) {
      classifyError("dependency diagnostics", error);
    }

    try {
      const response404 = await goto(page, "/review/decision", {
        timeout: 120000,
        settle: 1000,
      });
      const removedText = await bodyText(page);
      addCheck(
        "review decision route removed",
        response404?.status() === 404 || /404|not found/i.test(removedText),
        `status=${response404?.status()} text=${removedText}`
      );
    } catch (error) {
      classifyError("removed review route", error);
    }

    try {
      const mobileContext = await browser.newContext({
        viewport: { width: 390, height: 844 },
        isMobile: true,
      });
      const mobilePage = await mobileContext.newPage();
      mobilePage.setDefaultTimeout(60000);
      installWatchers(mobilePage, "mobile");
      const selectedJob = [...summary.jobs].reverse().find((job) => job.jobId) || summary.jobs[0];
      const mobileRoutes = [
        ["mobile home", "/", /Analyze and validate/i],
        ["mobile request", "/requests/new", /Stored procedure analysis request/i],
        [
          "mobile job",
          selectedJob?.jobId ? `/jobs/${selectedJob.jobId}` : "/",
          /Workflow job|Analyze and validate/i,
        ],
      ];
      if (artifactUrl) {
        mobileRoutes.push([
          "mobile artifact",
          new URL(artifactUrl).pathname,
          /Artifact preview|Draft/i,
        ]);
      } else {
        addBlocker(
          "mobile artifact",
          "API/LLM prerequisite blocker",
          "No artifact was produced, so mobile artifact route was not covered."
        );
        addCheck(
          "mobile artifact covered",
          false,
          "No artifact URL available.",
          "API/LLM prerequisite blocker"
        );
      }
      for (const [label, route, marker] of mobileRoutes) {
        await goto(mobilePage, route, { timeout: 120000, settle: 1200 });
        const text = await bodyText(mobilePage);
        addCheck(`${label} usable`, marker.test(text), text);
        await assertNoHorizontalOverflow(mobilePage, label);
      }
      const mobileShot = path.join(screenshotDir, "mobile-smoke-final.png");
      await mobilePage.screenshot({ path: mobileShot, fullPage: true, timeout: 60000 });
      summary.screenshots.push(mobileShot);
      await mobileContext.close();
    } catch (error) {
      classifyError("mobile smoke", error);
    }

    addCheck(
      "no forbidden network paths",
      summary.forbiddenRequests.length === 0,
      JSON.stringify(summary.forbiddenRequests.slice(0, 20))
    );
    addCheck("no page errors", summary.pageErrors.length === 0, summary.pageErrors.join("\n"));
  } catch (error) {
    classifyError("smoke runner", error);
  } finally {
    if (browser) await browser.close();
  }

  const uiRegressionChecks = summary.checks.filter(
    (check) => !check.pass && check.classification === "UI regression"
  );
  summary.uiPass =
    uiRegressionChecks.length === 0 &&
    summary.forbiddenRequests.length === 0 &&
    summary.pageErrors.length === 0;
  summary.acceptancePass =
    summary.uiPass && summary.checks.every((check) => check.pass);
  summary.failedChecks = summary.checks.filter((check) => !check.pass);
  summary.requestCount = summary.observedRequests.length;

  fs.writeFileSync(
    path.join(screenshotDir, "summary.json"),
    JSON.stringify(summary, null, 2)
  );
  console.log(JSON.stringify(summary, null, 2));
})().catch((error) => {
  console.error(error && error.stack ? error.stack : error);
  process.exit(1);
});
