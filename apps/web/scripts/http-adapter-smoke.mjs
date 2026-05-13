#!/usr/bin/env node

import { createHttpPortalApi } from "../lib/api/http-client.ts";

const positionalArgs = process.argv.slice(2).filter((arg) => arg !== "--");
const baseUrl = positionalArgs[0] ?? process.env.PORTAL_API_BASE_URL;

if (!baseUrl) {
  throw new Error("Usage: pnpm --dir apps/web run smoke:http-adapter -- <baseUrl>");
}

const observedRequests = [];

function normalizePath(input) {
  const url = new URL(String(input));
  return `${url.pathname}${url.search}`;
}

async function instrumentedFetch(input, init = {}) {
  const method = (init.method ?? "GET").toUpperCase();
  const path = normalizePath(input);
  observedRequests.push({ method, path });
  return fetch(input, init);
}

function assert(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function assertObserved(label, predicate) {
  assert(
    observedRequests.some(predicate),
    `Missing HTTP adapter smoke path: ${label}`,
  );
}

function assertNoForbiddenPath() {
  const forbiddenFragments = ["/publish", "/export", "/deploy", "/execute", "/approval-decisions"];
  const forbidden = observedRequests.find(({ path }) =>
    forbiddenFragments.some((fragment) => path.includes(fragment)) &&
    !path.includes("/api/v1/knowledge/exports"),
  );
  assert(!forbidden, `Forbidden HTTP adapter path observed: ${forbidden?.method} ${forbidden?.path}`);
}

function assertNoForbiddenPayload(value, label, path = "$") {
  const forbiddenKeys = new Set([
    "connectionstring",
    "definition",
    "password",
    "rawdefinitiontext",
    "rowdata",
    "row_data",
    "sample_rows",
    "secret",
    "sqltext",
    "token",
  ]);
  const forbiddenStringFragments = [
    "count(*)",
    "password:",
    "procedure_execution",
    "raw_definition_text",
    "row_data",
    "sample_rows",
    "select *",
  ];

  if (Array.isArray(value)) {
    value.forEach((item, index) => assertNoForbiddenPayload(item, label, `${path}[${index}]`));
    return;
  }

  if (value && typeof value === "object") {
    for (const [key, child] of Object.entries(value)) {
      const normalizedKey = key.replaceAll("_", "").toLowerCase();
      assert(
        !forbiddenKeys.has(normalizedKey),
        `${label} contains forbidden payload key at ${path}.${key}`,
      );
      assertNoForbiddenPayload(child, label, `${path}.${key}`);
    }
    return;
  }

  if (typeof value === "string") {
    const normalizedValue = value.toLowerCase();
    const forbidden = forbiddenStringFragments.find((fragment) =>
      normalizedValue.includes(fragment),
    );
    assert(!forbidden, `${label} contains forbidden payload text at ${path}: ${forbidden}`);
  }
}

function assertNoPublishedState(artifacts, artifact) {
  const publishedSummary = artifacts.find((item) => item.status === "PUBLISHED");
  assert(!publishedSummary, `HTTP smoke returned published artifact ${publishedSummary?.artifactId}`);
  assert(artifact.status !== "PUBLISHED", `HTTP smoke preview returned published artifact ${artifact.artifactId}`);
}

const api = createHttpPortalApi({ baseUrl, fetcher: instrumentedFetch });

const submitted = await api.createSPAnalysisRequest({
  dbProfileId: "master",
  target: {
    type: "PROCEDURE",
    schema: "dbo",
    name: "usp_GetOrderSummary",
  },
  outputs: ["SP_ANALYSIS_DOCUMENT", "DEPENDENCY_REPORT", "JAVA_MYBATIS_DRAFT"],
  options: { includeEvidenceRefs: true },
});

const job = await api.getJob(submitted.jobId);
const jobs = await api.listJobs(5);
const listed = await api.listJobArtifacts(submitted.jobId);
const knowledgeAssets = await api.listJobKnowledgeAssets(submitted.jobId);
const analysisSummary = listed.artifacts.find((artifact) => artifact.type === "SP_ANALYSIS_DOC");
assert(analysisSummary, "HTTP smoke could not find SP_ANALYSIS_DOC artifact summary");

const artifact = await api.getArtifact(analysisSummary.artifactId);
const validation = await api.validateArtifact(analysisSummary.artifactId);
const latestValidation = await api.getLatestValidation(analysisSummary.artifactId);
const profiles = await api.listMetadataProfiles();
const metadataTools = await api.listMetadataTools();
const dependencyClosure = await api.invokeMetadataTool("get_dependency_closure", {
  arguments: {
    dbProfileId: "master",
    schema: "dbo",
    objectName: "usp_ProcessOrderBatch",
    objectType: "PROCEDURE",
    maxDepth: 2,
    includeReviewRequired: false,
  },
});
const dependencyResolution = await api.invokeMetadataTool("resolve_dependency_reference", {
  arguments: {
    dbProfileId: "master",
    sourceObject: {
      schema: "dbo",
      name: "usp_GetOrderSummary",
      objectType: "PROCEDURE",
    },
    referencedSchema: "dbo",
    referencedName: "TB_ORDER",
  },
});
const metadataSearch = await api.searchMetadataObjects({
  dbProfileId: "master",
  query: "order",
  objectTypes: ["PROCEDURE", "TABLE"],
  limit: 5,
});
const metadataAnalysis = await api.analyzeMetadata({
  dbProfileId: "master",
  query: "order",
  objectTypes: ["PROCEDURE", "TABLE"],
  options: {
    useLlmAnalysis: true,
    useAiToolOrchestration: true,
    llmProfileId: "openai_fast_test",
    maxTargets: 3,
  },
});
const exportCandidate = knowledgeAssets.knowledgeAssets[0] ?? metadataAnalysis.knowledgeAssets[0];
const knowledgeExport = exportCandidate
  ? await api.createKnowledgeExport({
      assetIds: [exportCandidate.assetId],
      format: "GRAPH_JSON",
    })
  : null;
const registry = await api.listRegistryVersions();

assert(submitted.status === "VALIDATION_COMPLETE", `Unexpected submit status: ${submitted.status}`);
assert(job.currentStep === "VALIDATE", `Unexpected job current step: ${job.currentStep}`);
assert(jobs.jobs.some((item) => item.jobId === job.jobId), "Recent jobs did not include submitted job");
assert(listed.artifacts.length > 0, "HTTP smoke returned no artifacts");
assert(knowledgeAssets.knowledgeAssets.length > 0, "HTTP smoke returned no knowledge assets");
assert(artifact.evidenceRefs.length > 0, "HTTP smoke artifact has no evidence refs");
assert(validation.status === "PASSED" || validation.status === "REVIEW_REQUIRED", `Unexpected validation status: ${validation.status}`);
assert(latestValidation.validationReportId === validation.validationReportId, "Latest validation did not match explicit validation");
assert(profiles.profiles.every((profile) => profile.readOnly === true), "Metadata profiles must be read-only");
assert(metadataTools.tools.some((tool) => tool.name === "get_dependency_closure" && tool.invokable === true), "Dependency closure tool must be invokable");
assert(metadataTools.tools.every((tool) => !("input" in tool)), "Metadata tool summary must not expose input schema");
assert(dependencyClosure.toolName === "get_dependency_closure", "Dependency closure invocation returned the wrong tool");
assert(dependencyClosure.data.unresolved?.length > 0, "Dependency closure must preserve unresolved review-required evidence");
assert(dependencyClosure.data.edges.every((edge) => edge.resolutionStatus === "CONFIRMED"), "Closure graph must hide review-required edges when requested");
assert(dependencyResolution.toolName === "resolve_dependency_reference", "Dependency resolver invocation returned the wrong tool");
assert(dependencyResolution.data.selectedResolution?.name === "TB_ORDER", "Dependency resolver did not select the confirmed table");
assert(metadataSearch.sourceProfile === "master", `Unexpected metadata source profile: ${metadataSearch.sourceProfile}`);
assert(metadataSearch.sourceDatabase === "master", `Unexpected metadata source database: ${metadataSearch.sourceDatabase}`);
assert(metadataAnalysis.sourceProfile === "master", `Unexpected analysis source profile: ${metadataAnalysis.sourceProfile}`);
assert(metadataAnalysis.deterministicFacts.length > 0, "Metadata analysis must include deterministic facts");
assert(Array.isArray(metadataAnalysis.objectProfiles), "Metadata analysis must include objectProfiles");
assert(Array.isArray(metadataAnalysis.insightGroups), "Metadata analysis must include insightGroups");
assert(metadataAnalysis.dependencyGraph?.nodes, "Metadata analysis must include dependencyGraph");
assert(Array.isArray(metadataAnalysis.dtoReadiness), "Metadata analysis must include dtoReadiness");
assert(metadataAnalysis.aiToolEvidence?.plannerMetrics, "Metadata analysis must include planner metrics");
assert(Array.isArray(metadataAnalysis.knowledgeAssets), "Metadata analysis must include knowledgeAssets");
assert(metadataAnalysis.summary.length > 0, "Metadata analysis summary is empty");
assert(!knowledgeExport || knowledgeExport.format === "GRAPH_JSON", "Knowledge export must return GRAPH_JSON");
assert(registry.versions.length > 0, "Registry versions response is empty");

assertNoPublishedState(listed.artifacts, artifact);
assertNoForbiddenPath();

for (const [label, payload] of Object.entries({
  submitted,
  job,
  jobs,
  listed,
  knowledgeAssets,
  artifact,
  validation,
  latestValidation,
  profiles,
  metadataTools,
  dependencyClosure,
  dependencyResolution,
  metadataSearch,
  metadataAnalysis,
  knowledgeExport,
  registry,
})) {
  assertNoForbiddenPayload(payload, label);
}

assertObserved("POST /api/v1/requests/sp-analysis", ({ method, path }) =>
  method === "POST" && path === "/api/v1/requests/sp-analysis",
);
assertObserved("GET /api/v1/jobs/{jobId}", ({ method, path }) =>
  method === "GET" && /^\/api\/v1\/jobs\/[^/]+$/.test(path),
);
assertObserved("GET /api/v1/jobs", ({ method, path }) =>
  method === "GET" && path.startsWith("/api/v1/jobs?"),
);
assertObserved("GET /api/v1/jobs/{jobId}/artifacts", ({ method, path }) =>
  method === "GET" && /^\/api\/v1\/jobs\/[^/]+\/artifacts$/.test(path),
);
assertObserved("GET /api/v1/jobs/{jobId}/knowledge-assets", ({ method, path }) =>
  method === "GET" && /^\/api\/v1\/jobs\/[^/]+\/knowledge-assets$/.test(path),
);
assertObserved("GET /api/v1/artifacts/{artifactId}", ({ method, path }) =>
  method === "GET" && /^\/api\/v1\/artifacts\/[^/]+$/.test(path),
);
assertObserved("POST /api/v1/artifacts/{artifactId}/validation", ({ method, path }) =>
  method === "POST" && /^\/api\/v1\/artifacts\/[^/]+\/validation$/.test(path),
);
assertObserved("GET /api/v1/artifacts/{artifactId}/validation/latest", ({ method, path }) =>
  method === "GET" && /^\/api\/v1\/artifacts\/[^/]+\/validation\/latest$/.test(path),
);
assertObserved("GET /api/v1/metadata/db-profiles", ({ method, path }) =>
  method === "GET" && path === "/api/v1/metadata/db-profiles",
);
assertObserved("GET /api/v1/metadata/tools", ({ method, path }) =>
  method === "GET" && path === "/api/v1/metadata/tools",
);
assertObserved("POST /api/v1/metadata/tools/get_dependency_closure/invoke", ({ method, path }) =>
  method === "POST" && path === "/api/v1/metadata/tools/get_dependency_closure/invoke",
);
assertObserved("POST /api/v1/metadata/tools/resolve_dependency_reference/invoke", ({ method, path }) =>
  method === "POST" && path === "/api/v1/metadata/tools/resolve_dependency_reference/invoke",
);
assertObserved("GET /api/v1/metadata/search", ({ method, path }) =>
  method === "GET" && path.startsWith("/api/v1/metadata/search?"),
);
assertObserved("POST /api/v1/metadata/analyze", ({ method, path }) =>
  method === "POST" && path === "/api/v1/metadata/analyze",
);
assertObserved("POST /api/v1/knowledge/exports", ({ method, path }) =>
  method === "POST" && path === "/api/v1/knowledge/exports",
);
assertObserved("GET /api/v1/registry/versions", ({ method, path }) =>
  method === "GET" && path === "/api/v1/registry/versions",
);

console.log(
  JSON.stringify(
    {
      status: "pass",
      adapter: "apps/web/lib/api/http-client.ts",
      baseUrl,
      jobStatus: job.status,
      validationStatus: validation.status,
      observedRequests,
      deferredProductizationItem: "AUTH_RBAC_LIVE_IDP_PLF_WIRING_UNVERIFIED",
    },
    null,
    2,
  ),
);
