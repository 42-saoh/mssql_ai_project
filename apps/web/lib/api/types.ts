export type TargetObjectType = "PROCEDURE" | "TABLE" | "VIEW" | "FUNCTION";

export type RequestedOutputType =
  | "SP_ANALYSIS_DOCUMENT"
  | "DEPENDENCY_REPORT"
  | "TABLE_COLUMN_METADATA"
  | "JAVA_MYBATIS_DRAFT";

export type JobStatus =
  | "SUBMITTED"
  | "COLLECTING_METADATA"
  | "ANALYZING"
  | "GENERATING"
  | "VALIDATING"
  | "VALIDATION_COMPLETE"
  | "FAILED"
  | "CANCELED";

export type WorkflowStepType =
  | "COLLECT_METADATA"
  | "ANALYZE"
  | "GENERATE"
  | "VALIDATE";

export type ArtifactType =
  | "SP_ANALYSIS_DOC"
  | "DEPENDENCY_REPORT"
  | "METADATA_QUERY_RESULT"
  | "SCHEMA_ENRICHMENT_RESULT"
  | "MAPPER_XML"
  | "MAPPER_INTERFACE"
  | "SERVICE_DRAFT"
  | "DTO_DRAFT"
  | "VALIDATION_REPORT";

export type ArtifactStatus =
  | "DRAFT"
  | "VALIDATED"
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

export type RegistryType =
  | "PROMPT"
  | "TEMPLATE"
  | "POLICY"
  | "DB_PROFILE"
  | "GENERATOR"
  | "MODEL"
  | "SCHEMA";

export type MetadataSearchObjectType = TargetObjectType | "COLUMN";

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

export interface SPAnalysisBatchRequest {
  dbProfileId: string;
  targets: TargetObject[];
  outputs: RequestedOutputType[];
  options?: SPAnalysisOptions;
}

export interface SPAnalysisOptions {
  includeEvidenceRefs?: boolean;
  includeModernizationHints?: boolean;
  useLlmAnalysis?: boolean;
  llmProfileId?: "openai_sp_semantic_analysis" | "openai_fast_test";
  allowSpDefinitionToModel?: boolean;
  sourceContextMode?: "NONE" | "RETRIEVED_SPANS";
  sourceDependencyMode?: "NONE" | "CONFIRMED_PROCEDURES";
  useAiToolOrchestration?: boolean;
  usePlatformToolOrchestration?: boolean;
  persistKnowledge?: boolean;
}

export interface SubmitRequestResponse {
  requestId: string;
  jobId: string;
  status: JobStatus;
  echo?: Record<string, unknown>;
}

export interface SPAnalysisBatchAcceptedItem {
  target: TargetObject;
  requestId: string;
  jobId: string;
  status: JobStatus;
}

export interface SPAnalysisBatchRejectedItem {
  target: TargetObject;
  code: string;
  message: string;
}

export interface SPAnalysisBatchResponse {
  batchId: string;
  status: "ACCEPTED" | "PARTIAL" | "REJECTED";
  accepted: SPAnalysisBatchAcceptedItem[];
  rejected: SPAnalysisBatchRejectedItem[];
  limits: Record<string, number>;
}

export interface Job {
  jobId: string;
  requestId: string;
  status: JobStatus;
  dbProfileId?: string;
  target?: TargetObject;
  targetKey?: string | null;
  outputs?: RequestedOutputType[];
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
  analysisCoverage?: Record<string, unknown>;
  sourceContextSummary?: Record<string, unknown>;
  componentInvocations?: Record<string, unknown>[];
}

export interface AgentRunSummary {
  agentRunId: string;
  jobId: string;
  agentType: string;
  status: "SUCCEEDED" | "FAILED" | "SKIPPED";
  targetRef: string;
  targetKey?: string | null;
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
  targetKey?: string | null;
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
  qualityCaveats?: string[];
}

export interface MetadataProfile {
  id: string;
  database: string;
  description?: string;
  readOnly: true;
}

export type MetadataToolName = "get_dependency_closure" | "resolve_dependency_reference";

export interface MetadataToolSummary {
  name: string;
  description: string;
  readOnly: true;
  invokable: boolean;
}

export interface MetadataToolInvokeRequest {
  arguments: Record<string, unknown>;
}

export interface MetadataToolInvokeResponse {
  ok: true;
  toolName: MetadataToolName;
  dbProfileId: string;
  snapshotId: string;
  collectedAt: string;
  evidenceRefs: Record<string, unknown>[];
  data: Record<string, unknown>;
}

export interface MetadataSearchBlocker {
  code: string;
  message: string;
}

export interface MetadataObjectIdentity {
  schema: string;
  name: string;
  type: TargetObjectType;
}

export interface MetadataSearchObjectIdentity {
  schema: string;
  name: string;
  type: MetadataSearchObjectType;
}

export interface MetadataSearchResult {
  objectIdentity: MetadataSearchObjectIdentity;
  targetKey?: string | null;
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

export interface MetadataSearchRequest {
  dbProfileId: string;
  query: string;
  objectTypes?: MetadataSearchObjectType[];
  limit?: number;
}

export interface MetadataAnalysisOptions {
  useLlmAnalysis?: boolean;
  useAiToolOrchestration?: boolean;
  llmProfileId?: "openai_sp_semantic_analysis" | "openai_fast_test";
  maxTargets?: number;
  persistKnowledge?: boolean;
  generateDtoDrafts?: boolean;
}

export interface MetadataAnalysisRequest {
  dbProfileId: string;
  query?: string;
  target?: MetadataObjectIdentity;
  objectTypes?: TargetObjectType[];
  options?: MetadataAnalysisOptions;
}

export interface MetadataAnalysisInsight {
  code: string;
  objectRef: string;
  summary: string;
  status: "INFERRED_DESCRIPTION" | "REVIEW_REQUIRED";
  evidenceRefs: string[];
}

export type MetadataInsightCategory =
  | "COLUMN_RISK"
  | "RELATIONSHIP"
  | "INDEX"
  | "CONSTRAINT"
  | "DOCUMENTATION_GAP"
  | "DTO_READINESS"
  | "DEPENDENCY";

export interface MetadataObjectProfile {
  objectRef: string;
  targetKey?: string | null;
  objectType: string;
  columnCount: number;
  primaryKeyCount: number;
  foreignKeyCount: number;
  indexCount: number;
  constraintCount: number;
  descriptionCoverage: number;
  reviewRequired: boolean;
  evidenceRefs: string[];
  sourceFactIds: string[];
}

export interface MetadataInsightGroup {
  category: MetadataInsightCategory;
  insights: MetadataAnalysisInsight[];
}

export interface MetadataDependencyGraphNode {
  id: string;
  objectRef: string;
  targetKey?: string | null;
  objectType: string;
  status: "CONFIRMED" | "REVIEW_REQUIRED";
  evidenceRefs: string[];
}

export interface MetadataDependencyGraphEdge {
  from: string;
  to: string;
  relationshipType: string;
  status: "CONFIRMED" | "REVIEW_REQUIRED";
  evidenceRefs: string[];
}

export interface MetadataDependencyGraph {
  nodes: MetadataDependencyGraphNode[];
  edges: MetadataDependencyGraphEdge[];
  unresolved: Record<string, unknown>[];
}

export interface MetadataDtoReadiness {
  objectRef: string;
  targetKey?: string | null;
  status: "READY" | "PARTIAL" | "REVIEW_REQUIRED";
  fieldCount: number;
  reviewReasons: string[];
  evidenceRefs: string[];
}

export interface MetadataGeneratedDraft {
  artifactType: "DTO_DRAFT";
  objectRef: string;
  targetKey?: string | null;
  fileName: string;
  language: "java";
  content: string;
  evidenceRefs: string[];
  reviewRequired: boolean;
  reviewReasons: string[];
}

export interface MetadataAnalysisReviewMarker {
  code: string;
  message: string;
  status: "REVIEW_REQUIRED";
  evidenceRefs: string[];
}

export type KnowledgeAssetKind =
  | "SP_ANALYSIS"
  | "DEPENDENCY_EVIDENCE"
  | "METADATA_PROFILE"
  | "DTO_READINESS"
  | "CANONICAL_ANALYSIS";

export interface KnowledgeAssetSummary {
  assetId: string;
  assetKind: KnowledgeAssetKind;
  dbProfileId: string;
  targetType: string;
  targetSchema: string;
  targetName: string;
  targetKey?: string | null;
  logicalKey: string;
  currentVersionId?: string | null;
  currentVersionNo: number;
  contentHash?: string | null;
  sourceJobId?: string | null;
  createdAt?: string;
  updatedAt?: string;
}

export interface KnowledgeAssetVersion {
  versionId: string;
  assetId: string;
  versionNo: number;
  contentHash: string;
  payload: Record<string, unknown>;
  factCount: number;
  edgeCount: number;
  sourceJobId?: string | null;
  createdAt?: string;
}

export interface KnowledgeFact {
  factId: string;
  versionId: string;
  assetId: string;
  factType: string;
  objectRef: string;
  summary: string;
  status: "OBSERVED" | "INFERRED_DESCRIPTION" | "REVIEW_REQUIRED";
  evidenceRefs: string[];
  payload: Record<string, unknown>;
  contentHash: string;
  createdAt?: string;
}

export interface KnowledgeEdge {
  edgeId: string;
  versionId: string;
  assetId: string;
  fromFactId: string;
  toFactId: string;
  edgeType:
    | "DEPENDS_ON"
    | "DERIVED_FROM"
    | "SUPPORTS"
    | "READS"
    | "WRITES"
    | "CALLS"
    | "FK_TO"
    | "DTO_FIELD_OF";
  evidenceRefs: string[];
  payload: Record<string, unknown>;
  createdAt?: string;
}

export interface KnowledgeFactGraph {
  assetId: string;
  versionId: string;
  facts: KnowledgeFact[];
  edges: KnowledgeEdge[];
}

export interface KnowledgeExportRequest {
  assetIds: string[];
  format: "JSONL" | "GRAPH_JSON";
  versionIds?: string[];
}

export interface KnowledgeExportResponse {
  exportId: string;
  format: "JSONL" | "GRAPH_JSON";
  contentType: string;
  content: string;
  contentHash: string;
  assetIds: string[];
  createdAt?: string;
}

export interface PlannerMetrics {
  status?: string;
  plannedRequestCount?: number;
  executedToolCallCount?: number;
  blockedRequestCount?: number;
  failedToolCallCount?: number;
  dedupedRequestCount?: number;
  budgetExhausted?: boolean;
  cacheHitCount?: number;
  cacheMissCount?: number;
  evidenceFactCount?: number;
  citedEvidenceFactCount?: number;
  evidenceUtilization?: number;
  claimCount?: number;
  supportedClaimCount?: number;
  claimSupportRate?: number;
  claimAnalysisAvailable?: boolean;
  validFactPrefixes?: string[];
}

export interface AiToolEvidenceSummary {
  status?: string;
  toolCallCount?: number;
  blockedRequests?: Record<string, unknown>[];
  reviewMarkers?: Record<string, unknown>[];
  caveats?: string[];
  plannerMetrics?: PlannerMetrics;
  [key: string]: unknown;
}

export interface MetadataAnalysisResponse {
  dbProfileId: string;
  mode: "QUERY" | "TARGET";
  query?: string;
  target?: MetadataObjectIdentity;
  objectTypes: TargetObjectType[];
  sourceProfile: string;
  sourceDatabase: string;
  snapshotId?: string;
  collectedAt?: string;
  targets: MetadataSearchResult[];
  summary: string;
  objectInsights: MetadataAnalysisInsight[];
  objectProfiles: MetadataObjectProfile[];
  insightGroups: MetadataInsightGroup[];
  dependencyGraph: MetadataDependencyGraph;
  dtoReadiness: MetadataDtoReadiness[];
  generatedDrafts: MetadataGeneratedDraft[];
  aiToolEvidence: AiToolEvidenceSummary;
  deterministicFacts: Record<string, unknown>[];
  reviewMarkers: MetadataAnalysisReviewMarker[];
  assumptions: string[];
  caveats: string[];
  reviewRequired: boolean;
  blockers: MetadataSearchBlocker[];
  modelInvocation?: ModelInvocationSummary | null;
  componentInvocations: Record<string, unknown>[];
  knowledgeAssets: KnowledgeAssetSummary[];
}

export type MetadataAnalysisRunStatusValue = "QUEUED" | "RUNNING" | "SUCCEEDED" | "FAILED";

export interface MetadataAnalysisRunError {
  code: string;
  message: string;
  statusCode: number;
}

export interface MetadataAnalysisRunStatus {
  runId: string;
  status: MetadataAnalysisRunStatusValue;
  submittedAt: string;
  startedAt?: string | null;
  completedAt?: string | null;
  request: MetadataAnalysisRequest;
  analysis?: MetadataAnalysisResponse | null;
  error?: MetadataAnalysisRunError | null;
}

export interface MetadataDesignFieldInput {
  name?: string | null;
  description?: string | null;
  dbType?: string | null;
  nullable?: boolean | null;
}

export interface MetadataDesignInputs {
  tableNameHint?: string | null;
  tableDescription?: string | null;
  fields?: MetadataDesignFieldInput[];
}

export interface MetadataDesignOptions {
  useLlmAnalysis?: boolean;
  useAiToolOrchestration?: boolean;
  llmProfileId?: "openai_sp_semantic_analysis" | "openai_fast_test";
  maxCandidates?: number;
  generateDtoDraft?: boolean;
  conversationMode?: "NEW_DESIGN" | "REFINE_CURRENT";
}

export interface MetadataDesignRunRequest {
  dbProfileId: string;
  message: string;
  conversationId?: string | null;
  designInputs?: MetadataDesignInputs;
  options?: MetadataDesignOptions;
}

export interface MetadataRelatedMetadata {
  kind: "TABLE" | "COLUMN" | "SIMILAR_TABLE" | "TABLE_SCHEMA";
  objectRef: string;
  score: number;
  summary: string;
  evidenceRefs: string[];
  payload: Record<string, unknown>;
}

export interface MetadataStandardizationMapping {
  inputName?: string | null;
  inputDescription?: string | null;
  proposedName: string;
  proposedType: string;
  source: "METADATA" | "STANDARD_POLICY" | "REVIEW_REQUIRED";
  evidenceRefs: string[];
  reviewRequired: boolean;
  reviewReasons: string[];
}

export interface MetadataTableProposalColumn {
  name: string;
  dataType: string;
  nullable: boolean;
  description?: string | null;
  source: "METADATA" | "STANDARD_POLICY" | "USER_INPUT" | "REVIEW_REQUIRED";
  evidenceRefs: string[];
  reviewRequired: boolean;
  reviewReasons: string[];
}

export interface MetadataTableProposal {
  schema: string;
  tableName: string;
  tableDescription?: string | null;
  columns: MetadataTableProposalColumn[];
  createTableScriptPreview: string;
  evidenceRefs: string[];
  reviewRequired: boolean;
  reviewReasons: string[];
}

export interface MetadataDesignIntentChange {
  action:
    | "ADD_FIELD"
    | "REMOVE_FIELD"
    | "RENAME_FIELD"
    | "CHANGE_TYPE"
    | "CHANGE_NULLABILITY"
    | "SET_TABLE_NAME"
    | "SET_TABLE_DESCRIPTION"
    | "REVIEW_REQUIRED";
  target?: string | null;
  value?: string | null;
  summary: string;
  reviewRequired: boolean;
  reviewReasons: string[];
}

export interface MetadataDesignInterpretedIntent {
  intent: "CREATE_TABLE" | "REFINE_TABLE" | "UNKNOWN";
  tableNameCandidate?: string | null;
  tableDescription?: string | null;
  fields: MetadataDesignFieldInput[];
  modifications: MetadataDesignIntentChange[];
  confidence: number;
  reviewRequired: boolean;
  reviewReasons: string[];
}

export interface MetadataDesignAppliedChange {
  action: string;
  target?: string | null;
  summary: string;
  reviewRequired: boolean;
  reviewReasons: string[];
}

export interface MetadataDesignResult {
  assistantMessage: string;
  interpretedIntent: MetadataDesignInterpretedIntent;
  appliedChanges: MetadataDesignAppliedChange[];
  relatedMetadata: MetadataRelatedMetadata[];
  standardizationMappings: MetadataStandardizationMapping[];
  tableProposal: MetadataTableProposal;
  dtoDraft?: MetadataGeneratedDraft | null;
  aiToolEvidence: Record<string, unknown>;
  deterministicFacts: Record<string, unknown>[];
  reviewMarkers: MetadataAnalysisReviewMarker[];
  caveats: string[];
  reviewRequired: boolean;
  modelInvocation?: ModelInvocationSummary | null;
  componentInvocations: Record<string, unknown>[];
}

export interface MetadataDesignRunError {
  code: string;
  message: string;
  statusCode: number;
}

export interface MetadataDesignRunStatus {
  runId: string;
  conversationId: string;
  status: MetadataAnalysisRunStatusValue;
  submittedAt: string;
  startedAt?: string | null;
  completedAt?: string | null;
  request: MetadataDesignRunRequest;
  result?: MetadataDesignResult | null;
  error?: MetadataDesignRunError | null;
}

export interface MetadataDesignConversation {
  conversationId: string;
  runs: MetadataDesignRunStatus[];
}

export interface RegistryVersion {
  registryType: RegistryType;
  version: string;
  active?: boolean;
}
