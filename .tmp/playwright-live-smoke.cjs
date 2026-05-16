const fs = require('fs');
const path = require('path');
const { chromium } = require('playwright');

const baseUrl = 'http://localhost:3035';
const screenshotDir = path.join('D:/wt/p35/.tmp', 'playwright-live-smoke-' + new Date().toISOString().replace(/[:.]/g, '-'));
fs.mkdirSync(screenshotDir, { recursive: true });

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
  created: {},
};
const forbiddenPathFragments = ['/publish', '/deploy', '/execute', '/approval-decisions'];
const forbiddenControlRe = /^(publish|deploy|execute|approval decision|approve|reject|apply ddl|apply dml|run sql|row data|raw prompt|raw sp definition|raw sql|배포|실행|승인|반려|적용)$/i;

function addCheck(name, pass, details = '') {
  summary.checks.push({ name, pass: Boolean(pass), details: String(details ?? '') });
}
function classifyError(name, error) {
  const message = String(error && error.stack ? error.stack : error);
  const lower = message.toLowerCase();
  let classification = 'ui regression';
  if (/econnrefused|err_connection|timeout|timed out/.test(lower)) classification = 'app unreachable or timeout';
  if (/dependency|plf|ppm|openai|schema|required|unavailable|blocked/.test(lower)) classification = 'api/plf/ppm prerequisite blocker';
  summary.blockers.push({ name, classification, message: message.slice(0, 2000) });
  addCheck(name, false, message.slice(0, 500));
}
async function bodyText(page) {
  return await page.locator('body').innerText({ timeout: 15000 }).catch(error => 'BODY_ERROR: ' + error.message);
}
async function screenshot(page, name) {
  const file = path.join(screenshotDir, `${String(summary.screenshots.length).padStart(2, '0')}-${name}.png`);
  await page.screenshot({ path: file, fullPage: true, timeout: 60000 });
  summary.screenshots.push(file);
  return file;
}
async function goto(page, route, options = {}) {
  const response = await page.goto(baseUrl + route, { waitUntil: 'domcontentloaded', timeout: options.timeout ?? 120000 });
  await page.waitForTimeout(options.settle ?? 2000);
  return response;
}
async function assertNoForbiddenControls(page, label) {
  const controls = await page.locator('a,button,input[type="submit"]').evaluateAll((els) => els.map((el) => {
    return (el.innerText || el.value || el.getAttribute('aria-label') || '').trim();
  }).filter(Boolean));
  const forbidden = controls.filter((text) => forbiddenControlRe.test(text));
  addCheck(`${label}: no forbidden action controls`, forbidden.length === 0, forbidden.join(', '));
}
function installWatchers(page, viewport = 'desktop') {
  page.on('request', req => {
    const item = { method: req.method(), url: req.url(), viewport };
    summary.observedRequests.push(item);
    try {
      const url = new URL(req.url());
      if (forbiddenPathFragments.some(fragment => url.pathname.includes(fragment))) {
        summary.forbiddenRequests.push(item);
      }
    } catch {}
  });
  page.on('console', msg => {
    const text = msg.text();
    if (['error','warning'].includes(msg.type()) && !/favicon|404 \(Not Found\)/i.test(text)) {
      summary.consoleMessages.push({ type: msg.type(), text, viewport });
    }
  });
  page.on('pageerror', err => summary.pageErrors.push(String(err && err.stack ? err.stack : err)));
}

(async () => {
  let browser;
  try {
    browser = await chromium.launch({ headless: true, executablePath: 'C:/Program Files/Google/Chrome/Application/chrome.exe' });
    const context = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
    const page = await context.newPage();
    page.setDefaultTimeout(60000);
    installWatchers(page);

    try {
      const response = await goto(page, '/');
      const text = await bodyText(page);
      await screenshot(page, 'home-dashboard');
      addCheck('home loads', response && response.status() < 500, `status=${response?.status()}`);
      addCheck('home not unconfigured', !text.includes('Portal API is not configured'), 'Portal API configured');
      addCheck('home dashboard content', /Analyze and validate/.test(text) && /Registry bindings|Active versions/.test(text) && /Metadata search/.test(text), text.slice(0, 300));
      await assertNoForbiddenControls(page, 'home');
    } catch (error) { classifyError('home preflight', error); }

    let submittedJobUrl = null;
    let selectedSchema = 'dbo';
    let selectedName = 'GetInspItemsCd';
    try {
      await goto(page, '/requests/new');
      await screenshot(page, 'request-form-before-submit');
      const text = await bodyText(page);
      selectedSchema = await page.locator('form').first().locator('input[name="schema"]').inputValue().catch(() => selectedSchema);
      selectedName = await page.locator('form').first().locator('input[name="name"]').inputValue().catch(() => selectedName);
      summary.created.selectedTarget = `${selectedSchema}.${selectedName}`;
      addCheck('request page renders form', /Stored procedure analysis request/.test(text) && /Submit request/.test(text) && /Submit batch/.test(text), text.slice(0, 300));
      addCheck('request page renders LLM/source options', /LLM profile/.test(text) && /Source context/.test(text) && /Dependency analysis/.test(text), 'workflow options visible');
      await assertNoForbiddenControls(page, 'request page');
      await page.getByRole('button', { name: 'Submit request' }).first().click({ timeout: 30000 });
      await page.waitForURL(/\/jobs\/[^/?#]+/, { timeout: 900000 });
      await page.waitForLoadState('domcontentloaded', { timeout: 120000 }).catch(() => {});
      await page.waitForTimeout(3000);
      submittedJobUrl = page.url();
      summary.created.jobUrl = submittedJobUrl;
      summary.created.jobId = submittedJobUrl.match(/\/jobs\/([^/?#]+)/)?.[1] ?? null;
      await screenshot(page, 'job-detail-after-submit');
      const jobText = await bodyText(page);
      addCheck('single submit redirects to job', /\/jobs\//.test(submittedJobUrl), submittedJobUrl);
      addCheck('job page has workflow status', /Workflow job/.test(jobText) && /Validation flow/.test(jobText), jobText.slice(0, 500));
      addCheck('job page has draft artifact list', /Draft artifacts/.test(jobText) && /Preview/.test(jobText), jobText.slice(0, 800));
      await assertNoForbiddenControls(page, 'job page');
    } catch (error) { classifyError('single request submit/job detail', error); }

    let artifactUrl = null;
    try {
      if (submittedJobUrl) {
        const previewLink = page.getByRole('link', { name: 'Preview' }).first();
        if (await previewLink.count()) {
          await previewLink.click({ timeout: 30000 });
          await page.waitForURL(/\/artifacts\/[^/?#]+/, { timeout: 120000 });
          await page.waitForLoadState('domcontentloaded', { timeout: 120000 }).catch(() => {});
          await page.waitForTimeout(2000);
          artifactUrl = page.url();
          summary.created.artifactUrl = artifactUrl;
          let artifactText = await bodyText(page);
          addCheck('artifact preview loads', /Artifact preview/.test(artifactText) && /Draft artifact content/.test(artifactText), artifactText.slice(0, 500));
          addCheck('artifact evidence refs visible', /Evidence refs|Trace points/.test(artifactText), artifactText.slice(0, 800));
          const runValidation = page.getByRole('button', { name: 'Run validation' });
          if (await runValidation.count()) {
            await runValidation.first().click({ timeout: 30000 });
            await page.waitForLoadState('domcontentloaded', { timeout: 300000 }).catch(() => {});
            await page.waitForTimeout(3000);
          }
          await screenshot(page, 'artifact-preview-after-validation');
          artifactText = await bodyText(page);
          addCheck('artifact validation visible', /Validation/.test(artifactText) && /(PASSED|REVIEW_REQUIRED|Quality caveats|Missing evidence|Evidence and policy checks)/.test(artifactText), artifactText.slice(0, 1000));
          await assertNoForbiddenControls(page, 'artifact page');
        } else {
          summary.blockers.push({ name: 'artifact preview', classification: 'live-data limitation', message: 'No Preview link was available on the submitted job.' });
          addCheck('artifact preview link exists', false, 'No Preview link');
        }
      }
    } catch (error) { classifyError('artifact preview/validation', error); }

    try {
      await goto(page, '/requests/new');
      await page.getByRole('button', { name: 'Submit batch' }).click({ timeout: 30000 });
      await page.waitForURL(/\/requests\/new\?.*batchStatus=/, { timeout: 600000 });
      await page.waitForTimeout(2000);
      const batchText = await bodyText(page);
      addCheck('batch submit shows result summary', /Batch result/.test(batchText) && /Accepted/.test(batchText) && /Rejected/.test(batchText), batchText.slice(0, 800));
    } catch (error) { classifyError('batch request submit', error); }

    try {
      await goto(page, '/metadata/search?dbProfileId=ppm&query=P&limit=5&objectTypes=PROCEDURE&objectTypes=TABLE&analyze=1', { timeout: 900000, settle: 3000 });
      await screenshot(page, 'metadata-analysis-panel');
      const metadataText = await bodyText(page);
      addCheck('metadata search renders results or blocker', /Metadata search/.test(metadataText) && (/Search results/.test(metadataText) || /dependency is unavailable|blocked|unavailable/i.test(metadataText)), metadataText.slice(0, 800));
      addCheck('metadata analysis renders evidence or blocker', /AI-MCP metadata analysis|Metadata analysis is unavailable|AI_METADATA_ANALYSIS_BLOCKED/.test(metadataText), metadataText.slice(0, 1000));
      if (/AI-MCP metadata analysis/.test(metadataText)) {
        addCheck('metadata analysis includes deep sections', /Facts/.test(metadataText) && /Tools/.test(metadataText) && /(Object|Dependency graph|DTO|insights)/i.test(metadataText), metadataText.slice(0, 1200));
      }
      await assertNoForbiddenControls(page, 'metadata search');
    } catch (error) { classifyError('metadata search/analyze', error); }

    try {
      const closureUrl = `/metadata/dependencies?mode=closure&dbProfileId=ppm&schema=${encodeURIComponent(selectedSchema)}&objectName=${encodeURIComponent(selectedName)}&objectType=PROCEDURE&maxDepth=2`;
      await goto(page, closureUrl, { timeout: 300000, settle: 3000 });
      await screenshot(page, 'dependency-diagnostics-closure');
      const depText = await bodyText(page);
      addCheck('dependency closure renders tool summary', /Dependency diagnostics/.test(depText) && /get_dependency_closure/.test(depText), depText.slice(0, 800));
      addCheck('dependency closure renders evidence or blocker', /Evidence refs|Nodes|Edges|Unresolved|Dependency evidence tool failed|DEPENDENCY_EVIDENCE_BLOCKED/.test(depText), depText.slice(0, 1200));
      await assertNoForbiddenControls(page, 'dependency closure');
      let resolverCandidate = null;
      try { resolverCandidate = await page.locator('h2:has-text("Edges")').locator('xpath=following::article[1]//h3').innerText({ timeout: 5000 }); } catch {}
      if (resolverCandidate && resolverCandidate.includes('.')) {
        const parts = resolverCandidate.split('.');
        const referencedSchema = parts[parts.length - 2];
        const referencedName = parts[parts.length - 1];
        await goto(page, `/metadata/dependencies?mode=resolver&dbProfileId=ppm&sourceSchema=${encodeURIComponent(selectedSchema)}&sourceName=${encodeURIComponent(selectedName)}&sourceObjectType=PROCEDURE&referencedSchema=${encodeURIComponent(referencedSchema)}&referencedName=${encodeURIComponent(referencedName)}`, { timeout: 300000, settle: 2000 });
        const resolverText = await bodyText(page);
        addCheck('dependency resolver renders candidate result', /Resolve reference/.test(resolverText) && /(Selected resolution|Candidates|Dependency evidence tool failed)/.test(resolverText), resolverText.slice(0, 1000));
      } else {
        summary.blockers.push({ name: 'dependency resolver', classification: 'live-data limitation', message: 'No dependency edge candidate was visible from closure results; resolver not counted as UI failure.' });
        addCheck('dependency resolver candidate available', true, 'No visible edge candidate; live-data-blocked by plan rule');
      }
    } catch (error) { classifyError('dependency diagnostics', error); }

    try {
      const response404 = await goto(page, '/review/decision', { timeout: 120000, settle: 1000 });
      const removedText = await bodyText(page);
      addCheck('review decision route removed', response404?.status() === 404 || /404|not found/i.test(removedText), `status=${response404?.status()} text=${removedText.slice(0, 200)}`);
    } catch (error) { classifyError('removed review route', error); }

    try {
      const mobileContext = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true });
      const mobilePage = await mobileContext.newPage();
      installWatchers(mobilePage, 'mobile');
      const mobileRoutes = [
        ['mobile home', '/', /Analyze and validate/],
        ['mobile request', '/requests/new', /Stored procedure analysis request/],
        ['mobile job', summary.created.jobId ? `/jobs/${summary.created.jobId}` : '/', /Workflow job|Analyze and validate/],
        ['mobile artifact', artifactUrl ? new URL(artifactUrl).pathname : '/', /Artifact preview|Analyze and validate/],
      ];
      for (const [label, route, marker] of mobileRoutes) {
        await mobilePage.goto(baseUrl + route, { waitUntil: 'domcontentloaded', timeout: 120000 });
        await mobilePage.waitForTimeout(1500);
        const text = await bodyText(mobilePage);
        addCheck(label + ' usable', marker.test(text), text.slice(0, 300));
      }
      const mobileShot = path.join(screenshotDir, 'mobile-smoke-final.png');
      await mobilePage.screenshot({ path: mobileShot, fullPage: true });
      summary.screenshots.push(mobileShot);
      await mobileContext.close();
    } catch (error) { classifyError('mobile smoke', error); }

    addCheck('no forbidden network paths', summary.forbiddenRequests.length === 0, JSON.stringify(summary.forbiddenRequests.slice(0, 5)));
    addCheck('no page errors', summary.pageErrors.length === 0, summary.pageErrors.join('\n').slice(0, 500));
  } catch (error) {
    classifyError('smoke runner', error);
  } finally {
    if (browser) await browser.close();
  }
  summary.pass = summary.checks.every(c => c.pass) && summary.forbiddenRequests.length === 0 && summary.pageErrors.length === 0;
  summary.failedChecks = summary.checks.filter(c => !c.pass);
  summary.requestCount = summary.observedRequests.length;
  fs.writeFileSync(path.join(screenshotDir, 'summary.json'), JSON.stringify(summary, null, 2));
  console.log(JSON.stringify(summary, null, 2));
})().catch((error) => {
  console.error(error && error.stack ? error.stack : error);
  process.exit(1);
});
