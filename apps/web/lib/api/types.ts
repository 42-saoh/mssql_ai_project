export type TargetObjectType = "PROCEDURE" | "TABLE" | "VIEW" | "FUNCTION";

export type RequestedOutputType =
  | "SP_ANALYSIS_DOCUMENT"
  | "DEPENDENCY_REPORT"
  | "TABLE_COLUMN_METADATA"
  | "JAVA_MYBATIS_DRAFT"
  | "DTO_MODEL_DRAFT"
  | "DDL_DRAFT";

export type JobStatus =
  | "SUBMITTED"
  | "COLLECTING_METADATA"
  | "ANALYZING"
  | "GENERATING"
  | "VALIDATING"
  | "VALIDATION_COMPLETE"
  | "REVIEW_PENDING"
  | "APPROVED"
  | "REJECTED"
  | "PUBLISHED"
  | "FAILED"
  | "CANCELED";

export type WorkflowStepType =
  | "COLLECT_METADATA"
  | "ANALYZE"
  | "GENERATE"
  | "VALIDATE"
  | "REVIEW"
  | "PUBLISH";

export type ArtifactType =
  | "SP_ANALYSIS_DOC"
  | "DEPENDENCY_REPORT"
  | "METADATA_QUERY_RESULT"
  | "SCHEMA_ENRICHMENT_RESULT"
  | "MAPPER_XML"
  | "MAPPER_INTERFACE"
  | "SERVICE_DRAFT"
  | "DTO_DRAFT"
  | "VO_DRAFT"
  | "MODEL_DRAFT"
  | "DDL_DRAFT"
  | "VALIDATION_REPORT"
  | "APPROVAL_LOG";

export type ArtifactStatus =
  | "DRAFT"
  | "VALIDATED"
  | "REVIEW_PENDING"
  | "APPROVED"
  | "REJECTED"
  | "PUBLISHED"
  | "ARCHIVED";

export type EvidenceRefType =
  | "MSSQL_METADATA"
  | "STATIC_ANALYSIS"
  | "LLM_INFERENCE"
  | "POLICY"
  | "TEMPLATE"
  | "USER_INPUT";

export type ValidationStatus = "PASSED" | "FAILED" | "REVIEW_REQUIRED";
export type ValidationSeverity = "INFO" | "WARNING" | "ERROR" | "BLOCKER";
export type ValidationResult = "PASS" | "FAIL" | "REVIEW_REQUIRED";
export type ApprovalDecision = "APPROVE" | "REJECT" | "REQUEST_CHANGES";

export type RegistryType =
  | "PROMPT"
  | "TEMPLATE"
  | "POLICY"
  | "DB_PROFILE"
  | "GENERATOR"
  | "MODEL"
  | "SCHEMA";

export type MetadataSearchObjectType = TargetObjectType;

export interface TargetObject {
  type: TargetObjectType;
  schema: string;
  name: string;
}

export interface SPAnalysisRequest {
  dbProfileId: string;
  target: TargetObject;
  outputs: RequestedOutputType[];
  options?: SPAnalysisOptions;
}

export interface SPAnalysisOptions {
  includeEvidenceRefs?: boolean;
  includeModernizationHints?: boolean;
  useLlmAnalysis?: boolean;
  llmProfileId?: "openai_sp_semantic_analysis" | "openai_fast_test";
  allowSpDefinitionToModel?: boolean;
}

export interface SubmitRequestResponse {
  requestId: string;
  jobId: string;
  status: JobStatus;
  echo?: Record<string, unknown>;
}

export interface Job {
  jobId: string;
  requestId: string;
  status: JobStatus;
  currentStep?: WorkflowStepType | null;
  createdAt?: string;
  updatedAt?: string;
  progress?: number;
  blockers?: MetadataSearchBlocker[];
  caveats?: string[];
  failureReason?: string;
}

export interface ModelInvocationSummary {
  provider: string;
  model: string;
  modelProfileId: string;
  modelRegistryRef?: string;
  reasoningEffort?: string;
  promptVersion: string;
  outputSchemaVersion: string;
  inputHash: string;
  promptHash: string;
  outputHash: string;
  status: "SUCCEEDED" | "FAILED" | "SKIPPED";
  tokenUsage?: Record<string, number>;
  latencyMs?: number | null;
}

export interface AgentRunSummary {
  agentRunId: string;
  jobId: string;
  agentType: string;
  status: "SUCCEEDED" | "FAILED" | "SKIPPED";
  targetRef: string;
  summary: string;
  structuredOutput: Record<string, unknown>;
  modelInvocation: ModelInvocationSummary;
  createdAt?: string;
}

export interface ArtifactSummary {
  artifactId: string;
  jobId?: string;
  type: ArtifactType;
  status: ArtifactStatus;
  title?: string;
  evidenceCoverage?: number;
  reviewRequired?: boolean;
  blockers?: MetadataSearchBlocker[];
  caveats?: string[];
}

export interface EvidenceRef {
  type: EvidenceRefType;
  objectRef: string;
  locator: string;
  snapshotId?: string;
}

export interface Artifact extends ArtifactSummary {
  content: string;
  evidenceRefs: EvidenceRef[];
  generatorVersion: string;
  registryRefs: string[];
  assumptions?: string[];
  todos?: string[];
}

export interface ValidationCheck {
  ruleId: string;
  severity: ValidationSeverity;
  result: ValidationResult;
  message?: string;
}

export interface ValidationReport {
  validationReportId?: string;
  artifactId: string;
  status: ValidationStatus;
  checks: ValidationCheck[];
  missingEvidence?: string[];
  manualReviewPoints?: string[];
}

export interface MetadataProfile {
  id: string;
  database: string;
  description?: string;
  readOnly: true;
}

export interface MetadataSearchBlocker {
  code: string;
  message: string;
}

export interface MetadataObjectIdentity {
  schema: string;
  name: string;
  type: MetadataSearchObjectType;
}

export interface MetadataSearchRequest {
  dbProfileId: string;
  query: string;
  objectTypes?: MetadataSearchObjectType[];
  limit?: number;
}

export interface MetadataSearchResult {
  objectIdentity: MetadataObjectIdentity;
  sourceProfile: string;
  sourceDatabase: string;
  snapshotId?: string;
  evidenceRefs: EvidenceRef[];
  caveats: string[];
  reviewRequired: boolean;
  blockers: MetadataSearchBlocker[];
}

export interface MetadataSearchResponse {
  dbProfileId: string;
  query: string;
  objectTypes: MetadataSearchObjectType[];
  limit: number;
  sourceProfile: string;
  sourceDatabase: string;
  snapshotId?: string;
  collectedAt?: string;
  results: MetadataSearchResult[];
  caveats: string[];
  reviewRequired: boolean;
  blockers: MetadataSearchBlocker[];
}

export interface RegistryVersion {
  registryType: RegistryType;
  version: string;
  active?: boolean;
}

export interface ApprovalDecisionRequest {
  decision: ApprovalDecision;
  reviewer: string;
  comment: string;
  validationReportId?: string;
}

export interface ApprovalRecord {
  approvalId: string;
  artifactId: string;
  decision: ApprovalDecision;
  reviewer: string;
  comment?: string;
  decidedAt: string;
}
