from enum import StrEnum

from pydantic import BaseModel, Field


class JobStatus(StrEnum):
    SUBMITTED = "SUBMITTED"
    COLLECTING_METADATA = "COLLECTING_METADATA"
    ANALYZING = "ANALYZING"
    GENERATING = "GENERATING"
    VALIDATING = "VALIDATING"
    VALIDATION_COMPLETE = "VALIDATION_COMPLETE"
    REVIEW_PENDING = "REVIEW_PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"
    CANCELED = "CANCELED"


class WorkflowStepType(StrEnum):
    COLLECT_METADATA = "COLLECT_METADATA"
    ANALYZE = "ANALYZE"
    GENERATE = "GENERATE"
    VALIDATE = "VALIDATE"
    REVIEW = "REVIEW"
    PUBLISH = "PUBLISH"


class JobStepStatus(StrEnum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class ArtifactType(StrEnum):
    SP_ANALYSIS_DOC = "SP_ANALYSIS_DOC"
    DEPENDENCY_REPORT = "DEPENDENCY_REPORT"
    METADATA_QUERY_RESULT = "METADATA_QUERY_RESULT"
    SCHEMA_ENRICHMENT_RESULT = "SCHEMA_ENRICHMENT_RESULT"
    MAPPER_XML = "MAPPER_XML"
    MAPPER_INTERFACE = "MAPPER_INTERFACE"
    SERVICE_DRAFT = "SERVICE_DRAFT"
    DTO_DRAFT = "DTO_DRAFT"
    VALIDATION_REPORT = "VALIDATION_REPORT"
    APPROVAL_LOG = "APPROVAL_LOG"


class ArtifactStatus(StrEnum):
    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    REVIEW_PENDING = "REVIEW_PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PUBLISHED = "PUBLISHED"
    ARCHIVED = "ARCHIVED"


class RequestedOutputType(StrEnum):
    SP_ANALYSIS_DOCUMENT = "SP_ANALYSIS_DOCUMENT"
    DEPENDENCY_REPORT = "DEPENDENCY_REPORT"
    TABLE_COLUMN_METADATA = "TABLE_COLUMN_METADATA"
    JAVA_MYBATIS_DRAFT = "JAVA_MYBATIS_DRAFT"


REQUESTED_OUTPUT_ARTIFACT_TYPES: dict[RequestedOutputType, tuple[ArtifactType, ...]] = {
    RequestedOutputType.SP_ANALYSIS_DOCUMENT: (ArtifactType.SP_ANALYSIS_DOC,),
    RequestedOutputType.DEPENDENCY_REPORT: (ArtifactType.DEPENDENCY_REPORT,),
    RequestedOutputType.TABLE_COLUMN_METADATA: (ArtifactType.METADATA_QUERY_RESULT,),
    RequestedOutputType.JAVA_MYBATIS_DRAFT: (
        ArtifactType.DTO_DRAFT,
        ArtifactType.SERVICE_DRAFT,
        ArtifactType.MAPPER_INTERFACE,
        ArtifactType.MAPPER_XML,
    ),
}


class JobSummary(BaseModel):
    job_id: str
    status: JobStatus
    request_id: str


CANONICAL_ANALYSIS_MODEL_SCHEMA_VERSION = "CanonicalAnalysisModel.v2"
SP_OPERATION_MODEL_SCHEMA_VERSION = "SpOperationModel.v0.1"


class CanonicalEvidenceStatus(StrEnum):
    OBSERVED = "OBSERVED"
    INFERRED_DESCRIPTION = "INFERRED_DESCRIPTION"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class CanonicalObjectType(StrEnum):
    PROCEDURE = "PROCEDURE"
    SYSTEM_PROCEDURE = "SYSTEM_PROCEDURE"
    TABLE = "TABLE"
    VIEW = "VIEW"
    FUNCTION = "FUNCTION"
    TEMP_TABLE = "TEMP_TABLE"


class CanonicalDependencyOperation(StrEnum):
    READ = "READ"
    WRITE = "WRITE"
    EXECUTE = "EXECUTE"
    DECLARE = "DECLARE"
    UNKNOWN = "UNKNOWN"


class CanonicalParameterDirection(StrEnum):
    INPUT = "INPUT"
    OUTPUT = "OUTPUT"
    INPUT_OUTPUT = "INPUT_OUTPUT"


class CanonicalEvidenceRef(BaseModel):
    source: str
    line: int | None = None
    snippet: str
    status: CanonicalEvidenceStatus = CanonicalEvidenceStatus.OBSERVED


class CanonicalRegistryVersionRef(BaseModel):
    registry_type: str
    version: str
    active: bool = True


class CanonicalReviewMarker(BaseModel):
    code: str
    message: str
    status: CanonicalEvidenceStatus = CanonicalEvidenceStatus.REVIEW_REQUIRED
    evidence: list[CanonicalEvidenceRef] = Field(default_factory=list)


class CanonicalTodoItem(BaseModel):
    code: str
    message: str
    status: CanonicalEvidenceStatus = CanonicalEvidenceStatus.REVIEW_REQUIRED
    evidence: list[CanonicalEvidenceRef] = Field(default_factory=list)


class CanonicalConfidenceScore(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    status: CanonicalEvidenceStatus
    rationale: str
    factors: list[str] = Field(default_factory=list)


class CanonicalEvidenceAssessment(BaseModel):
    status: CanonicalEvidenceStatus = CanonicalEvidenceStatus.OBSERVED
    review_required: bool = False
    evidence_ref_count: int = 0
    observed_ref_count: int = 0
    review_required_ref_count: int = 0
    todo_count: int = 0
    notes: list[str] = Field(default_factory=list)


class CanonicalProcedureIdentifier(BaseModel):
    schema_name: str | None = None
    procedure_name: str
    full_name: str


class CanonicalProcedureParameter(BaseModel):
    name: str
    data_type: str
    default: str | None = None
    direction: CanonicalParameterDirection = CanonicalParameterDirection.INPUT
    evidence: list[CanonicalEvidenceRef] = Field(default_factory=list)


class CanonicalProcedureSignature(BaseModel):
    identifier: CanonicalProcedureIdentifier
    parameters: list[CanonicalProcedureParameter] = Field(default_factory=list)
    evidence: list[CanonicalEvidenceRef] = Field(default_factory=list)


class CanonicalObjectReference(BaseModel):
    schema_name: str | None = None
    object_name: str
    full_name: str
    object_type: CanonicalObjectType
    operation: CanonicalDependencyOperation
    status: CanonicalEvidenceStatus = CanonicalEvidenceStatus.OBSERVED
    evidence: list[CanonicalEvidenceRef] = Field(default_factory=list)


class CanonicalProcedureCall(BaseModel):
    schema_name: str | None = None
    procedure_name: str
    full_name: str
    object_type: CanonicalObjectType = CanonicalObjectType.PROCEDURE
    operation: CanonicalDependencyOperation = CanonicalDependencyOperation.EXECUTE
    is_dynamic_sql_executor: bool = False
    status: CanonicalEvidenceStatus = CanonicalEvidenceStatus.OBSERVED
    evidence: list[CanonicalEvidenceRef] = Field(default_factory=list)
    review_notes: list[str] = Field(default_factory=list)


class CanonicalTempTableFinding(BaseModel):
    name: str
    columns: list[str] = Field(default_factory=list)
    operation: CanonicalDependencyOperation = CanonicalDependencyOperation.DECLARE
    status: CanonicalEvidenceStatus = CanonicalEvidenceStatus.OBSERVED
    evidence: list[CanonicalEvidenceRef] = Field(default_factory=list)


class CanonicalDependencySummary(BaseModel):
    table_references: list[CanonicalObjectReference] = Field(default_factory=list)
    view_references: list[CanonicalObjectReference] = Field(default_factory=list)
    function_references: list[CanonicalObjectReference] = Field(default_factory=list)
    called_procedures: list[CanonicalProcedureCall] = Field(default_factory=list)
    temp_tables: list[CanonicalTempTableFinding] = Field(default_factory=list)


class CanonicalPatternFinding(BaseModel):
    name: str
    detected: bool
    status: CanonicalEvidenceStatus = CanonicalEvidenceStatus.OBSERVED
    evidence: list[CanonicalEvidenceRef] = Field(default_factory=list)
    details: dict[str, object] = Field(default_factory=dict)


class CanonicalPatternSummary(BaseModel):
    transaction: CanonicalPatternFinding
    try_catch: CanonicalPatternFinding
    dynamic_sql: CanonicalPatternFinding
    temp_table: CanonicalPatternFinding
    cursor: CanonicalPatternFinding
    multi_result_set: CanonicalPatternFinding


class CanonicalResultSetColumnHint(BaseModel):
    name: str | None = None
    expression: str
    status: CanonicalEvidenceStatus = CanonicalEvidenceStatus.OBSERVED
    evidence: list[CanonicalEvidenceRef] = Field(default_factory=list)
    review_notes: list[str] = Field(default_factory=list)


class CanonicalResultSetHint(BaseModel):
    ordinal: int
    source: str = "STATIC_SELECT"
    columns: list[CanonicalResultSetColumnHint] = Field(default_factory=list)
    status: CanonicalEvidenceStatus = CanonicalEvidenceStatus.OBSERVED
    evidence: list[CanonicalEvidenceRef] = Field(default_factory=list)
    review_notes: list[str] = Field(default_factory=list)


class CanonicalCallGraphEdge(BaseModel):
    caller: str
    callee: str
    operation: CanonicalDependencyOperation = CanonicalDependencyOperation.EXECUTE
    status: CanonicalEvidenceStatus = CanonicalEvidenceStatus.OBSERVED
    evidence: list[CanonicalEvidenceRef] = Field(default_factory=list)
    review_notes: list[str] = Field(default_factory=list)


class CanonicalBusinessRuleSummary(BaseModel):
    category: str
    summary: str
    status: CanonicalEvidenceStatus = CanonicalEvidenceStatus.OBSERVED
    evidence: list[CanonicalEvidenceRef] = Field(default_factory=list)
    inferred_from: list[str] = Field(default_factory=list)


class CanonicalModernizationPoint(BaseModel):
    code: str
    summary: str
    status: CanonicalEvidenceStatus = CanonicalEvidenceStatus.REVIEW_REQUIRED
    evidence: list[CanonicalEvidenceRef] = Field(default_factory=list)
    inferred_from: list[str] = Field(default_factory=list)


class CanonicalAnalysisSubject(BaseModel):
    object_type: CanonicalObjectType = Field(alias="objectType")
    schema_name: str | None = Field(default=None, alias="schema")
    name: str
    full_name: str = Field(alias="fullName")


class CanonicalMetadataProfile(BaseModel):
    object_ref: str = Field(alias="objectRef")
    object_type: str = Field(alias="objectType")
    metrics: dict[str, object] = Field(default_factory=dict)
    evidence_refs: list[str] = Field(default_factory=list, alias="evidenceRefs")
    source_fact_ids: list[str] = Field(default_factory=list, alias="sourceFactIds")


class CanonicalDependencyEvidence(BaseModel):
    fact_id: str | None = Field(default=None, alias="factId")
    object_ref: str = Field(alias="objectRef")
    dependency_type: str = Field(default="DEPENDS_ON", alias="dependencyType")
    status: CanonicalEvidenceStatus = CanonicalEvidenceStatus.REVIEW_REQUIRED
    evidence_refs: list[str] = Field(default_factory=list, alias="evidenceRefs")
    payload: dict[str, object] = Field(default_factory=dict)


class CanonicalDtoReadiness(BaseModel):
    object_ref: str = Field(alias="objectRef")
    status: str = "REVIEW_REQUIRED"
    field_count: int = Field(default=0, alias="fieldCount")
    review_reasons: list[str] = Field(default_factory=list, alias="reviewReasons")
    evidence_refs: list[str] = Field(default_factory=list, alias="evidenceRefs")


class CanonicalFactNode(BaseModel):
    fact_id: str = Field(alias="factId")
    fact_type: str = Field(alias="factType")
    object_ref: str = Field(alias="objectRef")
    status: CanonicalEvidenceStatus = CanonicalEvidenceStatus.REVIEW_REQUIRED
    evidence_refs: list[str] = Field(default_factory=list, alias="evidenceRefs")


class CanonicalFactEdge(BaseModel):
    edge_id: str = Field(alias="edgeId")
    from_fact_id: str = Field(alias="fromFactId")
    to_fact_id: str = Field(alias="toFactId")
    edge_type: str = Field(alias="edgeType")
    evidence_refs: list[str] = Field(default_factory=list, alias="evidenceRefs")


class CanonicalFactGraph(BaseModel):
    nodes: list[CanonicalFactNode] = Field(default_factory=list)
    edges: list[CanonicalFactEdge] = Field(default_factory=list)


class CanonicalKnowledgeAssetRef(BaseModel):
    asset_id: str = Field(alias="assetId")
    version_id: str | None = Field(default=None, alias="versionId")
    asset_kind: str = Field(alias="assetKind")
    content_hash: str | None = Field(default=None, alias="contentHash")


class SpStatementOperation(StrEnum):
    SELECT = "SELECT"
    INSERT = "INSERT"
    UPDATE = "UPDATE"
    DELETE = "DELETE"
    EXECUTE = "EXECUTE"
    COMPUTE = "COMPUTE"
    VALIDATE = "VALIDATE"


class SpDtoBlueprintRole(StrEnum):
    QUERY = "QUERY"
    RESULT = "RESULT"
    COMMAND = "COMMAND"
    BATCH_ITEM = "BATCH_ITEM"
    CALL_REQUEST = "CALL_REQUEST"
    CALL_RESULT = "CALL_RESULT"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class SpOperationCondition(BaseModel):
    expression: str
    variables: list[str] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list, alias="evidenceRefs")
    status: CanonicalEvidenceStatus = CanonicalEvidenceStatus.REVIEW_REQUIRED


class SpStatementContract(BaseModel):
    statement_id: str = Field(alias="statementId")
    operation: SpStatementOperation
    target_ref: str = Field(alias="targetRef")
    phase: str
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    writes: list[str] = Field(default_factory=list)
    cross_database: bool = Field(default=False, alias="crossDatabase")
    review_markers: list[str] = Field(default_factory=list, alias="reviewMarkers")
    evidence_refs: list[str] = Field(default_factory=list, alias="evidenceRefs")
    status: CanonicalEvidenceStatus = CanonicalEvidenceStatus.REVIEW_REQUIRED


class SpDtoFieldBlueprint(BaseModel):
    name: str
    db_type: str = Field(alias="dbType")
    source: str
    required: bool = False
    evidence_refs: list[str] = Field(default_factory=list, alias="evidenceRefs")


class SpDtoBlueprint(BaseModel):
    name: str
    role: SpDtoBlueprintRole
    operation_ids: list[str] = Field(default_factory=list, alias="operationIds")
    fields: list[SpDtoFieldBlueprint] = Field(default_factory=list)
    evidence_refs: list[str] = Field(default_factory=list, alias="evidenceRefs")
    review_markers: list[str] = Field(default_factory=list, alias="reviewMarkers")


class SpOperationContract(BaseModel):
    operation_id: str = Field(alias="operationId")
    crud_flag: str = Field(alias="crudFlag")
    title: str
    summary: str
    branch_condition: SpOperationCondition = Field(alias="branchCondition")
    statement_refs: list[str] = Field(default_factory=list, alias="statementRefs")
    dto_blueprint_refs: list[str] = Field(default_factory=list, alias="dtoBlueprintRefs")
    state_transitions: list[str] = Field(default_factory=list, alias="stateTransitions")
    risk_markers: list[str] = Field(default_factory=list, alias="riskMarkers")
    evidence_refs: list[str] = Field(default_factory=list, alias="evidenceRefs")
    status: CanonicalEvidenceStatus = CanonicalEvidenceStatus.REVIEW_REQUIRED


class SpOperationModel(BaseModel):
    schema_version: str = Field(
        default=SP_OPERATION_MODEL_SCHEMA_VERSION,
        alias="schemaVersion",
    )
    contract_target: str = Field(default="SpOperationModel", alias="contractTarget")
    target_ref: str = Field(alias="targetRef")
    source_policy: str = Field(default="sanitized_facts_only", alias="sourcePolicy")
    production_ready: bool = Field(default=False, alias="productionReady")
    operations: list[SpOperationContract] = Field(min_length=1)
    statement_evidence: list[SpStatementContract] = Field(
        default_factory=list,
        alias="statementEvidence",
    )
    dto_blueprints: list[SpDtoBlueprint] = Field(default_factory=list, alias="dtoBlueprints")
    review_markers: list[str] = Field(default_factory=list, alias="reviewMarkers")
    evidence_refs: list[str] = Field(default_factory=list, alias="evidenceRefs")
    assumptions: list[str] = Field(default_factory=list)


class CanonicalAnalysisModel(BaseModel):
    schema_version: str = CANONICAL_ANALYSIS_MODEL_SCHEMA_VERSION
    analysis_version: str
    contract_target: str = "CanonicalAnalysisModel"
    snapshot_id: str
    registry_version_refs: list[CanonicalRegistryVersionRef] = Field(min_length=1)
    procedure: CanonicalProcedureSignature
    dependencies: CanonicalDependencySummary
    patterns: CanonicalPatternSummary
    result_sets: list[CanonicalResultSetHint] = Field(default_factory=list)
    call_graph: list[CanonicalCallGraphEdge] = Field(default_factory=list)
    business_rules: list[CanonicalBusinessRuleSummary] = Field(default_factory=list)
    modernization_points: list[CanonicalModernizationPoint] = Field(default_factory=list)
    evidence_refs: list[CanonicalEvidenceRef] = Field(min_length=1)
    review_markers: list[CanonicalReviewMarker] = Field(default_factory=list)
    todos: list[CanonicalTodoItem] = Field(default_factory=list)
    evidence_assessment: CanonicalEvidenceAssessment
    overall_confidence: CanonicalConfidenceScore
    analysis_subject: CanonicalAnalysisSubject | None = Field(
        default=None,
        alias="analysisSubject",
    )
    metadata_profiles: list[CanonicalMetadataProfile] = Field(
        default_factory=list,
        alias="metadataProfiles",
    )
    dependency_evidence: list[CanonicalDependencyEvidence] = Field(
        default_factory=list,
        alias="dependencyEvidence",
    )
    dto_readiness: list[CanonicalDtoReadiness] = Field(
        default_factory=list,
        alias="dtoReadiness",
    )
    fact_graph: CanonicalFactGraph = Field(default_factory=CanonicalFactGraph, alias="factGraph")
    knowledge_asset_refs: list[CanonicalKnowledgeAssetRef] = Field(
        default_factory=list,
        alias="knowledgeAssetRefs",
    )
