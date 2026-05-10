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
from pydantic import BaseModel, ConfigDict, Field


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
    use_llm_analysis: bool = Field(default=False, alias="useLlmAnalysis")
    llm_profile_id: Literal[
        "openai_sp_semantic_analysis",
        "openai_fast_test",
    ] = Field(default="openai_sp_semantic_analysis", alias="llmProfileId")
    allow_sp_definition_to_model: bool = Field(
        default=False,
        alias="allowSpDefinitionToModel",
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
