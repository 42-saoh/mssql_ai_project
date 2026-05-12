from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from ai_agent_domain import (
    ArtifactStatus,
    ArtifactType,
    JobStatus,
    RequestedOutputType,
    WorkflowStepType,
)
from pydantic import BaseModel, ConfigDict, Field, model_validator


class ApiModel(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    def to_response(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, mode="json", exclude_none=True)


class TargetObject(ApiModel):
    type: Literal["PROCEDURE", "TABLE", "VIEW", "FUNCTION"]
    schema_name: str = Field(alias="schema")
    name: str

    @property
    def full_name(self) -> str:
        return f"{self.schema_name}.{self.name}"


class SPAnalysisOptions(ApiModel):
    include_evidence_refs: bool = Field(default=True, alias="includeEvidenceRefs")
    include_modernization_hints: bool = Field(
        default=True,
        alias="includeModernizationHints",
    )
    use_llm_analysis: bool = Field(default=True, alias="useLlmAnalysis")
    llm_profile_id: Literal[
        "openai_sp_semantic_analysis",
        "openai_fast_test",
    ] = Field(default="openai_sp_semantic_analysis", alias="llmProfileId")
    allow_sp_definition_to_model: bool = Field(
        default=True,
        alias="allowSpDefinitionToModel",
    )
    use_ai_tool_orchestration: bool = Field(
        default=True,
        alias="useAiToolOrchestration",
    )


class SPAnalysisRequest(ApiModel):
    db_profile_id: str = Field(alias="dbProfileId")
    target: TargetObject
    outputs: list[RequestedOutputType] = Field(min_length=1)
    options: SPAnalysisOptions = Field(default_factory=SPAnalysisOptions)


class SubmitRequestResponse(ApiModel):
    request_id: str = Field(alias="requestId")
    job_id: str = Field(alias="jobId")
    status: JobStatus
    echo: dict[str, Any] | None = None


class Job(ApiModel):
    job_id: str = Field(alias="jobId")
    request_id: str = Field(alias="requestId")
    status: JobStatus
    current_step: WorkflowStepType | None = Field(default=None, alias="currentStep")
    created_at: datetime | None = Field(default=None, alias="createdAt")
    updated_at: datetime | None = Field(default=None, alias="updatedAt")
    progress: float | None = None
    blockers: list[dict[str, str]] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    failure_reason: str | None = Field(default=None, alias="failureReason")


class EvidenceRef(ApiModel):
    type: Literal[
        "MSSQL_METADATA",
        "STATIC_ANALYSIS",
        "LLM_INFERENCE",
        "POLICY",
        "TEMPLATE",
        "USER_INPUT",
    ]
    object_ref: str = Field(alias="objectRef")
    locator: str
    snapshot_id: str | None = Field(default=None, alias="snapshotId")


class ArtifactSummary(ApiModel):
    artifact_id: str = Field(alias="artifactId")
    job_id: str | None = Field(default=None, alias="jobId")
    type: ArtifactType
    status: ArtifactStatus
    title: str | None = None
    evidence_coverage: float | None = Field(default=None, alias="evidenceCoverage")


class Artifact(ArtifactSummary):
    content: str
    evidence_refs: list[EvidenceRef] = Field(alias="evidenceRefs")
    generator_version: str = Field(alias="generatorVersion")
    registry_refs: list[str] = Field(alias="registryRefs")
    assumptions: list[str] = Field(default_factory=list)
    review_required: bool = Field(default=True, alias="reviewRequired")


class ValidationCheck(ApiModel):
    rule_id: str = Field(alias="ruleId")
    severity: Literal["INFO", "WARNING", "ERROR", "BLOCKER"]
    result: Literal["PASS", "FAIL", "REVIEW_REQUIRED"]
    message: str | None = None


class ValidationReport(ApiModel):
    validation_report_id: str | None = Field(default=None, alias="validationReportId")
    artifact_id: str = Field(alias="artifactId")
    status: Literal["PASSED", "FAILED", "REVIEW_REQUIRED"]
    checks: list[ValidationCheck]
    missing_evidence: list[str] = Field(default_factory=list, alias="missingEvidence")
    manual_review_points: list[str] = Field(
        default_factory=list,
        alias="manualReviewPoints",
    )


class ModelInvocationSummary(ApiModel):
    provider: str
    model: str
    model_profile_id: str = Field(alias="modelProfileId")
    model_registry_ref: str | None = Field(default=None, alias="modelRegistryRef")
    reasoning_effort: str | None = Field(default=None, alias="reasoningEffort")
    prompt_version: str = Field(alias="promptVersion")
    output_schema_version: str = Field(alias="outputSchemaVersion")
    input_hash: str = Field(alias="inputHash")
    prompt_hash: str = Field(alias="promptHash")
    output_hash: str = Field(alias="outputHash")
    status: Literal["SUCCEEDED", "FAILED", "SKIPPED"]
    token_usage: dict[str, int] = Field(default_factory=dict, alias="tokenUsage")
    latency_ms: int | None = Field(default=None, alias="latencyMs")
    component_invocations: list[dict[str, Any]] = Field(
        default_factory=list,
        alias="componentInvocations",
    )


class AgentRunSummary(ApiModel):
    agent_run_id: str = Field(alias="agentRunId")
    job_id: str = Field(alias="jobId")
    agent_type: str = Field(alias="agentType")
    status: Literal["SUCCEEDED", "FAILED", "SKIPPED"]
    target_ref: str = Field(alias="targetRef")
    summary: str
    structured_output: dict[str, Any] = Field(alias="structuredOutput")
    model_invocation: ModelInvocationSummary = Field(alias="modelInvocation")
    created_at: datetime | None = Field(default=None, alias="createdAt")


class ApprovalDecisionRequest(ApiModel):
    decision: Literal["APPROVE", "REJECT", "REQUEST_CHANGES"]
    reviewer: str
    comment: str
    validation_report_id: str | None = Field(default=None, alias="validationReportId")


class ApprovalRecord(ApiModel):
    approval_id: str = Field(alias="approvalId")
    artifact_id: str = Field(alias="artifactId")
    decision: Literal["APPROVE", "REJECT", "REQUEST_CHANGES"]
    reviewer: str
    comment: str | None = None
    decided_at: datetime = Field(alias="decidedAt")


class MetadataProfile(ApiModel):
    id: str
    database: str
    description: str | None = None
    read_only: Literal[True] = Field(default=True, alias="readOnly")


class MetadataToolSummary(ApiModel):
    name: str
    description: str
    read_only: Literal[True] = Field(default=True, alias="readOnly")
    invokable: bool = False


class MetadataToolInvokeRequest(ApiModel):
    model_config = ConfigDict(populate_by_name=True, extra="forbid")

    arguments: dict[str, Any]


class MetadataToolInvokeResponse(ApiModel):
    ok: Literal[True]
    tool_name: str = Field(alias="toolName")
    db_profile_id: str = Field(alias="dbProfileId")
    snapshot_id: str = Field(alias="snapshotId")
    collected_at: str = Field(alias="collectedAt")
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list, alias="evidenceRefs")
    data: dict[str, Any]


class MetadataSearchBlocker(ApiModel):
    code: str
    message: str


class MetadataObjectIdentity(ApiModel):
    schema_name: str = Field(alias="schema")
    name: str
    type: Literal["PROCEDURE", "TABLE", "VIEW", "FUNCTION"]


class MetadataSearchResult(ApiModel):
    object_identity: MetadataObjectIdentity = Field(alias="objectIdentity")
    source_profile: str = Field(alias="sourceProfile")
    source_database: str = Field(alias="sourceDatabase")
    snapshot_id: str | None = Field(default=None, alias="snapshotId")
    evidence_refs: list[EvidenceRef] = Field(default_factory=list, alias="evidenceRefs")
    caveats: list[str] = Field(default_factory=list)
    review_required: bool = Field(default=False, alias="reviewRequired")
    blockers: list[MetadataSearchBlocker] = Field(default_factory=list)


class MetadataSearchResponse(ApiModel):
    db_profile_id: str = Field(alias="dbProfileId")
    query: str
    object_types: list[Literal["PROCEDURE", "TABLE", "VIEW", "FUNCTION"]] = Field(
        alias="objectTypes"
    )
    limit: int
    source_profile: str = Field(alias="sourceProfile")
    source_database: str = Field(alias="sourceDatabase")
    snapshot_id: str | None = Field(default=None, alias="snapshotId")
    collected_at: str | None = Field(default=None, alias="collectedAt")
    results: list[MetadataSearchResult] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    review_required: bool = Field(default=False, alias="reviewRequired")
    blockers: list[MetadataSearchBlocker] = Field(default_factory=list)


class MetadataAnalysisOptions(ApiModel):
    use_llm_analysis: bool = Field(default=True, alias="useLlmAnalysis")
    use_ai_tool_orchestration: bool = Field(
        default=True,
        alias="useAiToolOrchestration",
    )
    llm_profile_id: Literal[
        "openai_sp_semantic_analysis",
        "openai_fast_test",
    ] = Field(default="openai_sp_semantic_analysis", alias="llmProfileId")
    max_targets: int = Field(default=3, ge=1, le=5, alias="maxTargets")


class MetadataAnalysisRequest(ApiModel):
    db_profile_id: str = Field(alias="dbProfileId", min_length=1)
    query: str | None = Field(default=None, min_length=1)
    target: MetadataObjectIdentity | None = None
    object_types: list[Literal["PROCEDURE", "TABLE", "VIEW", "FUNCTION"]] = Field(
        default_factory=list,
        alias="objectTypes",
    )
    options: MetadataAnalysisOptions = Field(default_factory=MetadataAnalysisOptions)

    @model_validator(mode="after")
    def validate_query_or_target(self) -> MetadataAnalysisRequest:
        has_query = bool((self.query or "").strip())
        has_target = self.target is not None
        if has_query == has_target:
            raise ValueError(
                "metadata analysis request must provide exactly one of query or target."
            )
        return self


class MetadataAnalysisInsight(ApiModel):
    code: str
    object_ref: str = Field(alias="objectRef")
    summary: str
    status: Literal["INFERRED_DESCRIPTION", "REVIEW_REQUIRED"] = "REVIEW_REQUIRED"
    evidence_refs: list[str] = Field(default_factory=list, alias="evidenceRefs")


MetadataInsightCategory = Literal[
    "COLUMN_RISK",
    "RELATIONSHIP",
    "INDEX",
    "CONSTRAINT",
    "DOCUMENTATION_GAP",
    "DTO_READINESS",
    "DEPENDENCY",
]


class MetadataObjectProfile(ApiModel):
    object_ref: str = Field(alias="objectRef")
    object_type: str = Field(alias="objectType")
    column_count: int = Field(default=0, alias="columnCount")
    primary_key_count: int = Field(default=0, alias="primaryKeyCount")
    foreign_key_count: int = Field(default=0, alias="foreignKeyCount")
    index_count: int = Field(default=0, alias="indexCount")
    constraint_count: int = Field(default=0, alias="constraintCount")
    description_coverage: float = Field(default=0.0, ge=0.0, le=1.0, alias="descriptionCoverage")
    review_required: bool = Field(default=False, alias="reviewRequired")
    evidence_refs: list[str] = Field(default_factory=list, alias="evidenceRefs")
    source_fact_ids: list[str] = Field(default_factory=list, alias="sourceFactIds")


class MetadataInsightGroup(ApiModel):
    category: MetadataInsightCategory
    insights: list[MetadataAnalysisInsight] = Field(default_factory=list)


class MetadataDependencyGraphNode(ApiModel):
    id: str
    object_ref: str = Field(alias="objectRef")
    object_type: str = Field(alias="objectType")
    status: Literal["CONFIRMED", "REVIEW_REQUIRED"] = "CONFIRMED"
    evidence_refs: list[str] = Field(default_factory=list, alias="evidenceRefs")


class MetadataDependencyGraphEdge(ApiModel):
    from_object_ref: str = Field(alias="from")
    to_object_ref: str = Field(alias="to")
    relationship_type: str = Field(alias="relationshipType")
    status: Literal["CONFIRMED", "REVIEW_REQUIRED"] = "CONFIRMED"
    evidence_refs: list[str] = Field(default_factory=list, alias="evidenceRefs")


class MetadataDependencyGraph(ApiModel):
    nodes: list[MetadataDependencyGraphNode] = Field(default_factory=list)
    edges: list[MetadataDependencyGraphEdge] = Field(default_factory=list)
    unresolved: list[dict[str, Any]] = Field(default_factory=list)


class MetadataDtoReadiness(ApiModel):
    object_ref: str = Field(alias="objectRef")
    status: Literal["READY", "PARTIAL", "REVIEW_REQUIRED"] = "REVIEW_REQUIRED"
    field_count: int = Field(default=0, alias="fieldCount")
    review_reasons: list[str] = Field(default_factory=list, alias="reviewReasons")
    evidence_refs: list[str] = Field(default_factory=list, alias="evidenceRefs")


class MetadataAnalysisReviewMarker(ApiModel):
    code: str
    message: str
    status: Literal["REVIEW_REQUIRED"] = "REVIEW_REQUIRED"
    evidence_refs: list[str] = Field(default_factory=list, alias="evidenceRefs")


class MetadataAnalysisResponse(ApiModel):
    db_profile_id: str = Field(alias="dbProfileId")
    mode: Literal["QUERY", "TARGET"]
    query: str | None = None
    target: MetadataObjectIdentity | None = None
    object_types: list[Literal["PROCEDURE", "TABLE", "VIEW", "FUNCTION"]] = Field(
        default_factory=list,
        alias="objectTypes",
    )
    source_profile: str = Field(alias="sourceProfile")
    source_database: str = Field(alias="sourceDatabase")
    snapshot_id: str | None = Field(default=None, alias="snapshotId")
    collected_at: str | None = Field(default=None, alias="collectedAt")
    targets: list[MetadataSearchResult] = Field(default_factory=list)
    summary: str
    object_insights: list[MetadataAnalysisInsight] = Field(
        default_factory=list,
        alias="objectInsights",
    )
    object_profiles: list[MetadataObjectProfile] = Field(
        default_factory=list,
        alias="objectProfiles",
    )
    insight_groups: list[MetadataInsightGroup] = Field(
        default_factory=list,
        alias="insightGroups",
    )
    dependency_graph: MetadataDependencyGraph = Field(
        default_factory=MetadataDependencyGraph,
        alias="dependencyGraph",
    )
    dto_readiness: list[MetadataDtoReadiness] = Field(
        default_factory=list,
        alias="dtoReadiness",
    )
    ai_tool_evidence: dict[str, Any] = Field(default_factory=dict, alias="aiToolEvidence")
    deterministic_facts: list[dict[str, Any]] = Field(
        default_factory=list,
        alias="deterministicFacts",
    )
    review_markers: list[MetadataAnalysisReviewMarker] = Field(
        default_factory=list,
        alias="reviewMarkers",
    )
    assumptions: list[str] = Field(default_factory=list)
    caveats: list[str] = Field(default_factory=list)
    review_required: bool = Field(default=True, alias="reviewRequired")
    blockers: list[MetadataSearchBlocker] = Field(default_factory=list)
    model_invocation: ModelInvocationSummary | None = Field(
        default=None,
        alias="modelInvocation",
    )
    component_invocations: list[dict[str, Any]] = Field(
        default_factory=list,
        alias="componentInvocations",
    )


class RegistryVersion(ApiModel):
    registry_type: Literal[
        "PROMPT",
        "TEMPLATE",
        "POLICY",
        "DB_PROFILE",
        "GENERATOR",
        "MODEL",
        "SCHEMA",
    ] = Field(alias="registryType")
    version: str
    active: bool = True
