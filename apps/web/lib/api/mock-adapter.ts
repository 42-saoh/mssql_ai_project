import type { PortalApi } from "./portal-api";
import { getPilotManifestSummary } from "@/lib/pilot-manifest";
import type {
  Artifact,
  ArtifactStatus,
  ArtifactSummary,
  Job,
  JobStatus,
  MetadataSearchObjectType,
  MetadataSearchRequest,
  MetadataSearchResponse,
  MetadataProfile,
  RegistryVersion,
  SPAnalysisRequest,
  SubmitRequestResponse,
  ValidationReport,
  WorkflowStepType,
} from "./types";

const createdAt = "2026-05-04T00:15:00.000Z";
const updatedAt = "2026-05-04T00:28:00.000Z";
const pilotManifest = getPilotManifestSummary();
const demoProcedure = pilotManifest.procedureSamples[1] ?? pilotManifest.procedureSamples[0];
const demoTarget = demoProcedure
  ? {
      database: demoProcedure.sourceDatabase,
      schema: demoProcedure.schema,
      name: demoProcedure.name,
      snapshotId: demoProcedure.snapshotId,
      locator: demoProcedure.evidenceLocator,
    }
  : {
      database: "fixture",
      schema: "dbo",
      name: "template_procedure",
      snapshotId: "snap_template_only",
      locator: "template-only-demo-target",
    };
const demoTargetRef = `${demoTarget.database}.${demoTarget.schema}.${demoTarget.name}`;

const metadataProfiles: MetadataProfile[] = [
  {
    id: "ppm",
    database: "PPM",
    description: "Pilot analysis target profile. Never falls back to PLF in mock or HTTP mode.",
    readOnly: true,
  },
  {
    id: "master",
    database: "master",
    description: "Default read-only metadata profile from local profile registry.",
    readOnly: true,
  },
  {
    id: "plf",
    database: "PLF",
    description: "Sample platform database profile for portal shell previews.",
    readOnly: true,
  },
];

const registryVersions: RegistryVersion[] = [
  { registryType: "PROMPT", version: "prompt.sp-analysis.v0", active: true },
  { registryType: "TEMPLATE", version: "template.mybatis-draft.v0", active: true },
  { registryType: "POLICY", version: "policy.approval-gate.v0", active: true },
  { registryType: "GENERATOR", version: "generator.portal-mock.v0", active: true },
];

interface MockJobScenario {
  status: JobStatus;
  currentStep: WorkflowStepType | null;
  label: string;
  summary: string;
  progress: number;
  blockers?: { code: string; message: string }[];
  caveats?: string[];
  failureReason?: string;
}

const jobScenarios: Record<string, MockJobScenario> = {
  job_demo_draft: {
    status: "SUBMITTED",
    currentStep: null,
    label: "draft",
    summary: "Request has been composed as a draft-only workflow preview.",
    progress: 0.08,
  },
  job_demo_validating: {
    status: "VALIDATING",
    currentStep: "VALIDATE",
    label: "validating",
    summary: "Generated artifacts are passing through policy and evidence checks.",
    progress: 0.72,
    caveats: ["Validation is checking evidence coverage and draft-only policy markers."],
  },
  job_demo_review_pending: {
    status: "REVIEW_PENDING",
    currentStep: "REVIEW",
    label: "review_pending",
    summary: "Validation requires a human reviewer before approval can be recorded.",
    progress: 0.84,
    blockers: [
      {
        code: "DEPENDENCY_METADATA_INCOMPLETE",
        message:
          "PPM dependency metadata is incomplete; table links remain review-required.",
      },
    ],
    caveats: ["Stored procedure to table linkage must not be treated as confirmed."],
  },
  job_demo_approved: {
    status: "APPROVED",
    currentStep: "REVIEW",
    label: "approved",
    summary: "Reviewer accepted this draft artifact version. No publish call is available here.",
    progress: 0.94,
    caveats: ["Approval is recorded for review only; publish is outside this shell."],
  },
  job_demo_rejected: {
    status: "REJECTED",
    currentStep: "REVIEW",
    label: "rejected",
    summary: "Reviewer rejected this draft and requested changes before any downstream use.",
    progress: 0.9,
  },
  job_demo_failed_blocker: {
    status: "FAILED",
    currentStep: "COLLECT_METADATA",
    label: "failed_blocker",
    summary: "PPM metadata collection is blocked and cannot fall back to PLF.",
    progress: 0.18,
    blockers: [
      {
        code: "PPM_DB_ACCESS_DENIED",
        message:
          "The pilot analysis target profile is unavailable. PLF fallback is not allowed.",
      },
    ],
    caveats: ["Retry only after the external PPM metadata profile is restored."],
    failureReason: "Read-only metadata dependency unavailable.",
  },
};

const defaultJobId = "job_demo_review_pending";

const artifactSummaries: ArtifactSummary[] = [
  {
    artifactId: "art_demo_sp_analysis",
    type: "SP_ANALYSIS_DOC",
    status: "REVIEW_PENDING",
    title: "SP analysis document",
    evidenceCoverage: 0.86,
    reviewRequired: true,
    blockers: [
      {
        code: "DEPENDENCY_METADATA_INCOMPLETE",
        message: "Dependency evidence is present but incomplete for table linkage.",
      },
    ],
    caveats: ["PPM dependency links stay review-required."],
  },
  {
    artifactId: "art_demo_dependency",
    type: "DEPENDENCY_REPORT",
    status: "VALIDATED",
    title: "Dependency report",
    evidenceCoverage: 0.94,
    reviewRequired: true,
    blockers: [
      {
        code: "DEPENDENCY_METADATA_INCOMPLETE",
        message: "Unresolved dependency refs are carried forward from the PPM manifest.",
      },
    ],
    caveats: ["Report is evidence-rich but does not confirm SP-to-table links."],
  },
  {
    artifactId: "art_demo_mapper",
    type: "MAPPER_XML",
    status: "DRAFT",
    title: "Java/MyBatis mapper draft",
    evidenceCoverage: 0.72,
    reviewRequired: true,
    caveats: ["Generated mapper content is a draft preview only."],
  },
];

const baseEvidenceRefs = [
  {
    type: "USER_INPUT" as const,
    objectRef: demoTargetRef,
    locator: "request.target",
    snapshotId: demoTarget.snapshotId,
  },
  {
    type: "MSSQL_METADATA" as const,
    objectRef: demoTargetRef,
    locator: demoTarget.locator,
    snapshotId: demoTarget.snapshotId,
  },
  {
    type: "STATIC_ANALYSIS" as const,
    objectRef: demoTargetRef,
    locator: "analysis.dependencies[0]",
    snapshotId: demoTarget.snapshotId,
  },
  {
    type: "POLICY" as const,
    objectRef: "POLICY.md",
    locator: "approval-gated",
  },
];

const artifacts: Record<string, Artifact> = {
  art_demo_sp_analysis: {
    ...artifactSummaries[0],
    content: [
      "# Stored procedure analysis draft",
      "",
      `Target: ${demoTargetRef}`,
      "",
      "Observed intent: summarize batch information for review. REVIEW_REQUIRED: business meaning must be confirmed by the owning team.",
      "",
      "Detected concerns:",
      "- PPM dependency metadata is incomplete for table linkage.",
      "- Result set mapping should be checked against metadata evidence before approval.",
      "- This artifact is draft-only and has no publish path.",
    ].join("\n"),
    evidenceRefs: baseEvidenceRefs,
    generatorVersion: "generator.portal-mock.v0",
    registryRefs: ["prompt.sp-analysis.v0", "template.analysis-doc.v0", "policy.approval-gate.v0"],
    assumptions: [
      "No live database was queried by the web shell.",
      "The PPM object identity comes from the pilot manifest; dependency interpretation remains review-required.",
    ],
    todos: ["Confirm procedure owner and business semantics.", "Review unresolved dependency refs."],
  },
  art_demo_dependency: {
    ...artifactSummaries[1],
    content: [
      "# Dependency report draft",
      "",
      "| Object | Relationship | Evidence |",
      "| --- | --- | --- |",
      "| unresolved dependency refs | review-required | PPM pilot manifest |",
      "| metadata-rich table candidates | not confirmed as SP-linked | PPM pilot manifest |",
      "",
      "REVIEW_REQUIRED: sys.sql_expression_dependencies was readable, but table links remain incomplete.",
    ].join("\n"),
    evidenceRefs: baseEvidenceRefs.slice(1, 4),
    generatorVersion: "generator.portal-mock.v0",
    registryRefs: ["template.dependency-report.v0", "policy.evidence-first.v0"],
    assumptions: ["Relationship cardinality is not inferred in the mock adapter."],
    todos: ["Do not treat unresolved refs as confirmed table dependencies."],
  },
  art_demo_mapper: {
    ...artifactSummaries[2],
    content: [
      "<!-- Draft only: generated mapper preview -->",
      "<select id=\"selectBatchList\" resultType=\"BatchListDto\">",
      "  <!-- SQL body omitted until metadata validation and review are complete -->",
      "  <!-- No generated source is applied by this portal UI. -->",
      "</select>",
    ].join("\n"),
    evidenceRefs: baseEvidenceRefs,
    generatorVersion: "generator.portal-mock.v0",
    registryRefs: ["template.mybatis-draft.v0", "policy.draft-artifact.v0"],
    assumptions: [
      "DTO field names require reviewer confirmation.",
      "SQL body is intentionally omitted; procedure execution and row-data access are forbidden.",
    ],
    todos: ["Bind DTO fields only after validation passes and review resolves TODOs."],
  },
};

const validationReports: Record<string, ValidationReport> = {
  art_demo_sp_analysis: {
    artifactId: "art_demo_sp_analysis",
    status: "REVIEW_REQUIRED",
    checks: [
      {
        ruleId: "VAL-EVIDENCE-001",
        severity: "WARNING",
        result: "REVIEW_REQUIRED",
        message: "Evidence refs are present, but result set interpretation needs reviewer confirmation.",
      },
      {
        ruleId: "POLICY-PUBLISH-001",
        severity: "BLOCKER",
        result: "PASS",
        message: "No publish or automatic DDL action is exposed by the portal shell.",
      },
    ],
    missingEvidence: ["Confirmed business owner for modernization notes"],
    manualReviewPoints: [
      "Confirm procedure intent and output semantics.",
      "Confirm whether generated Java/MyBatis draft should be requested in the next step.",
    ],
  },
  art_demo_dependency: {
    artifactId: "art_demo_dependency",
    status: "PASSED",
    checks: [
      {
        ruleId: "VAL-EVIDENCE-001",
        severity: "INFO",
        result: "PASS",
        message: "Every listed dependency has at least one evidence reference.",
      },
    ],
    missingEvidence: [],
    manualReviewPoints: ["Review dependency direction before approving generated code drafts."],
  },
  art_demo_mapper: {
    artifactId: "art_demo_mapper",
    status: "REVIEW_REQUIRED",
    checks: [
      {
        ruleId: "VAL-CODE-001",
        severity: "WARNING",
        result: "REVIEW_REQUIRED",
        message: "Mapper preview is intentionally incomplete until API-backed metadata arrives.",
      },
      {
        ruleId: "POLICY-DDL-001",
        severity: "BLOCKER",
        result: "PASS",
        message: "No DDL execution path exists in this screen.",
      },
    ],
    missingEvidence: ["Validated result set columns", "DTO naming registry binding"],
    manualReviewPoints: ["Check MyBatis parameter naming against team conventions."],
  },
};

function resolveJobScenario(jobId: string): MockJobScenario {
  return jobScenarios[jobId] ?? jobScenarios[defaultJobId];
}

function toJob(jobId: string): Job {
  const scenario = resolveJobScenario(jobId);

  return {
    jobId,
    requestId: "req_demo_001",
    status: scenario.status,
    currentStep: scenario.currentStep,
    createdAt,
    updatedAt,
    progress: scenario.progress,
    blockers: scenario.blockers,
    caveats: scenario.caveats,
    failureReason: scenario.failureReason,
  };
}

function artifactStatusForJob(status: JobStatus, artifact: ArtifactSummary): ArtifactStatus {
  if (status === "APPROVED") {
    return "APPROVED";
  }

  if (status === "REJECTED") {
    return artifact.artifactId === "art_demo_mapper" ? "REJECTED" : artifact.status;
  }

  if (status === "VALIDATING") {
    return artifact.artifactId === "art_demo_mapper" ? "DRAFT" : "VALIDATED";
  }

  if (status === "SUBMITTED" || status === "COLLECTING_METADATA" || status === "ANALYZING") {
    return "DRAFT";
  }

  return artifact.status;
}

const defaultMetadataObjectTypes: MetadataSearchObjectType[] = [
  "PROCEDURE",
  "TABLE",
  "VIEW",
  "FUNCTION",
];

function normalizeObjectTypes(objectTypes?: MetadataSearchObjectType[]): MetadataSearchObjectType[] {
  return objectTypes?.length ? objectTypes : defaultMetadataObjectTypes;
}

function normalizeLimit(limit?: number): number {
  if (limit === undefined || Number.isNaN(limit)) {
    return 20;
  }

  return Math.max(1, Math.min(100, Math.trunc(limit)));
}

function matchesSearchTerm(schema: string, name: string, query: string): boolean {
  const normalized = query.trim().toLowerCase();
  return `${schema}.${name}`.toLowerCase().includes(normalized);
}

function masterSearchResponse(request: MetadataSearchRequest): MetadataSearchResponse {
  const objectTypes = normalizeObjectTypes(request.objectTypes);
  const limit = normalizeLimit(request.limit);
  const query = request.query.trim();
  const results = [
    {
      objectIdentity: { schema: "dbo", name: "usp_OrderRequest_Select", type: "PROCEDURE" as const },
      sourceProfile: "master",
      sourceDatabase: "master",
      snapshotId: "snap_demo_master_001",
      evidenceRefs: [
        {
          type: "MSSQL_METADATA" as const,
          objectRef: "master.dbo.usp_OrderRequest_Select",
          locator: "fixtures/mcp/metadata_snapshot.json#/procedures/0",
          snapshotId: "snap_demo_master_001",
        },
      ],
      caveats: ["Synthetic fixture identity for adapter smoke only."],
      reviewRequired: true,
      blockers: [],
    },
    {
      objectIdentity: { schema: "dbo", name: "OrderRequest", type: "TABLE" as const },
      sourceProfile: "master",
      sourceDatabase: "master",
      snapshotId: "snap_demo_master_001",
      evidenceRefs: [
        {
          type: "MSSQL_METADATA" as const,
          objectRef: "master.dbo.OrderRequest",
          locator: "fixtures/mcp/metadata_snapshot.json#/tables/0",
          snapshotId: "snap_demo_master_001",
        },
      ],
      caveats: ["Synthetic metadata shape; no row data is included."],
      reviewRequired: false,
      blockers: [],
    },
  ]
    .filter((item) => objectTypes.includes(item.objectIdentity.type))
    .filter((item) => matchesSearchTerm(item.objectIdentity.schema, item.objectIdentity.name, query))
    .slice(0, limit);

  return {
    dbProfileId: request.dbProfileId,
    query,
    objectTypes,
    limit,
    sourceProfile: "master",
    sourceDatabase: "master",
    snapshotId: "snap_demo_master_001",
    collectedAt: updatedAt,
    results,
    caveats: ["Mock adapter response; API adapter uses the same interface."],
    reviewRequired: results.some((item) => item.reviewRequired),
    blockers: [],
  };
}

function ppmSearchResponse(request: MetadataSearchRequest): MetadataSearchResponse {
  const pilotManifest = getPilotManifestSummary();
  const objectTypes = normalizeObjectTypes(request.objectTypes);
  const limit = normalizeLimit(request.limit);
  const query = request.query.trim();

  if (pilotManifest.selectionMode !== "live_metadata") {
    return {
      dbProfileId: request.dbProfileId,
      query,
      objectTypes,
      limit,
      sourceProfile: "ppm",
      sourceDatabase: "PPM",
      results: [],
      caveats: ["PPM sample identities are hidden while the pilot manifest is template-only."],
      reviewRequired: true,
      blockers: pilotManifest.activeBlockers,
    };
  }

  const results = pilotManifest.metadataObjects
    .filter((item) => objectTypes.includes(item.type))
    .filter((item) => matchesSearchTerm(item.schema, item.name, query))
    .slice(0, limit)
    .map((item) => ({
      objectIdentity: {
        schema: item.schema,
        name: item.name,
        type: item.type,
      },
      sourceProfile: item.sourceProfile,
      sourceDatabase: item.sourceDatabase,
      snapshotId: item.snapshotId,
      evidenceRefs: [
        {
          type: "MSSQL_METADATA" as const,
          objectRef: `${item.sourceDatabase}.${item.schema}.${item.name}`,
          locator: item.evidenceLocator,
          snapshotId: item.snapshotId,
        },
      ],
      caveats: item.caveats,
      reviewRequired: item.reviewRequired,
      blockers: item.blockers,
    }));

  return {
    dbProfileId: request.dbProfileId,
    query,
    objectTypes,
    limit,
    sourceProfile: "ppm",
    sourceDatabase: "PPM",
    snapshotId: results[0]?.snapshotId,
    collectedAt: pilotManifest.generatedAt,
    results,
    caveats: [
      "PPM metadata search is identity/evidence-only and never falls back to PLF.",
      ...pilotManifest.activeBlockers.map((blocker) => blocker.code),
    ],
    reviewRequired: pilotManifest.activeBlockers.length > 0 || results.some((item) => item.reviewRequired),
    blockers: pilotManifest.activeBlockers,
  };
}

export function createMockPortalApi(): PortalApi {
  return {
    async createSPAnalysisRequest(request: SPAnalysisRequest): Promise<SubmitRequestResponse> {
      return {
        requestId: "req_demo_001",
        jobId: defaultJobId,
        status: "REVIEW_PENDING",
        echo: { request },
      };
    },

    async getJob(jobId: string): Promise<Job> {
      return toJob(jobId);
    },

    async listJobArtifacts(jobId: string) {
      const job = toJob(jobId);
      return {
        jobId,
        artifacts: artifactSummaries.map((artifact) => ({
          ...artifact,
          status: artifactStatusForJob(job.status, artifact),
        })),
      };
    },

    async getArtifact(artifactId: string): Promise<Artifact> {
      return artifacts[artifactId] ?? artifacts.art_demo_sp_analysis;
    },

    async validateArtifact(artifactId: string): Promise<ValidationReport> {
      return validationReports[artifactId] ?? validationReports.art_demo_sp_analysis;
    },

    async createApprovalDecision(artifactId, request) {
      return {
        approvalId: "approval_demo_001",
        artifactId,
        decision: request.decision,
        reviewer: request.reviewer,
        comment: request.comment,
        decidedAt: updatedAt,
      };
    },

    async listMetadataProfiles() {
      return {
        defaultProfileId: "ppm",
        profiles: metadataProfiles,
      };
    },

    async searchMetadataObjects(request) {
      if (request.dbProfileId === "ppm") {
        return ppmSearchResponse(request);
      }

      return masterSearchResponse(request);
    },

    async listRegistryVersions() {
      return {
        versions: registryVersions,
      };
    },
  };
}
