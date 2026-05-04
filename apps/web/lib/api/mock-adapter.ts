import type { PortalApi } from "./portal-api";
import type {
  Artifact,
  ArtifactStatus,
  ArtifactSummary,
  Job,
  JobStatus,
  MetadataProfile,
  RegistryVersion,
  SPAnalysisRequest,
  SubmitRequestResponse,
  ValidationReport,
  WorkflowStepType,
} from "./types";

const createdAt = "2026-05-04T00:15:00.000Z";
const updatedAt = "2026-05-04T00:28:00.000Z";

const metadataProfiles: MetadataProfile[] = [
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
}

const jobScenarios: Record<string, MockJobScenario> = {
  job_demo_draft: {
    status: "SUBMITTED",
    currentStep: null,
    label: "draft",
    summary: "Request has been composed as a draft-only workflow preview.",
  },
  job_demo_validating: {
    status: "VALIDATING",
    currentStep: "VALIDATE",
    label: "validating",
    summary: "Generated artifacts are passing through policy and evidence checks.",
  },
  job_demo_review_pending: {
    status: "REVIEW_PENDING",
    currentStep: "REVIEW",
    label: "review_pending",
    summary: "Validation requires a human reviewer before approval can be recorded.",
  },
  job_demo_approved: {
    status: "APPROVED",
    currentStep: "REVIEW",
    label: "approved",
    summary: "Reviewer accepted this draft artifact version. No publish call is available here.",
  },
  job_demo_rejected: {
    status: "REJECTED",
    currentStep: "REVIEW",
    label: "rejected",
    summary: "Reviewer rejected this draft and requested changes before any downstream use.",
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
  },
  {
    artifactId: "art_demo_dependency",
    type: "DEPENDENCY_REPORT",
    status: "VALIDATED",
    title: "Dependency report",
    evidenceCoverage: 0.94,
  },
  {
    artifactId: "art_demo_mapper",
    type: "MAPPER_XML",
    status: "DRAFT",
    title: "Java/MyBatis mapper draft",
    evidenceCoverage: 0.72,
  },
];

const baseEvidenceRefs = [
  {
    type: "USER_INPUT" as const,
    objectRef: "master.dbo.usp_OrderRequest_Select",
    locator: "request.target",
    snapshotId: "snap_demo_20260504_001",
  },
  {
    type: "MSSQL_METADATA" as const,
    objectRef: "master.dbo.usp_OrderRequest_Select",
    locator: "mcp.procedure.get_definition",
    snapshotId: "snap_demo_20260504_001",
  },
  {
    type: "STATIC_ANALYSIS" as const,
    objectRef: "master.dbo.usp_OrderRequest_Select",
    locator: "analysis.dependencies[0]",
    snapshotId: "snap_demo_20260504_001",
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
      "Target: master.dbo.usp_OrderRequest_Select",
      "",
      "Observed intent: retrieve order request records for review. REVIEW_REQUIRED: business meaning must be confirmed by the owning team.",
      "",
      "Detected concerns:",
      "- Transaction behavior requires manual confirmation.",
      "- Dynamic SQL usage is not asserted in this mock shell.",
      "- Result set mapping should be checked against metadata evidence before approval.",
    ].join("\n"),
    evidenceRefs: baseEvidenceRefs,
    generatorVersion: "generator.portal-mock.v0",
    registryRefs: ["prompt.sp-analysis.v0", "template.analysis-doc.v0", "policy.approval-gate.v0"],
    assumptions: [
      "No live database was queried by the web shell.",
      "The content is synthetic and marked review-required where evidence is incomplete.",
    ],
    reviewRequired: true,
  },
  art_demo_dependency: {
    ...artifactSummaries[1],
    content: [
      "# Dependency report draft",
      "",
      "| Object | Relationship | Evidence |",
      "| --- | --- | --- |",
      "| dbo.OrderRequest | reads | mcp.table.get_columns |",
      "| dbo.Customer | joins | static-analysis.join-scan |",
      "",
      "The report is a preview of the evidence layout P05 can hydrate from the API.",
    ].join("\n"),
    evidenceRefs: baseEvidenceRefs.slice(1, 4),
    generatorVersion: "generator.portal-mock.v0",
    registryRefs: ["template.dependency-report.v0", "policy.evidence-first.v0"],
    assumptions: ["Relationship cardinality is not inferred in the mock adapter."],
    reviewRequired: false,
  },
  art_demo_mapper: {
    ...artifactSummaries[2],
    content: [
      "<!-- Draft only: generated mapper preview -->",
      "<select id=\"selectOrderRequests\" resultType=\"OrderRequestDto\">",
      "  SELECT /* columns omitted until metadata validation passes */",
      "  FROM dbo.OrderRequest",
      "  WHERE Status = #{status}",
      "</select>",
    ].join("\n"),
    evidenceRefs: baseEvidenceRefs,
    generatorVersion: "generator.portal-mock.v0",
    registryRefs: ["template.mybatis-draft.v0", "policy.draft-artifact.v0"],
    assumptions: [
      "DTO field names require reviewer confirmation.",
      "SQL text is illustrative and must not be applied without validation.",
    ],
    reviewRequired: true,
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
        defaultProfileId: "master",
        profiles: metadataProfiles,
      };
    },

    async listRegistryVersions() {
      return {
        versions: registryVersions,
      };
    },
  };
}
