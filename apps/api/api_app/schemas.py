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


class SPAnalysisRequest(ApiModel):
    db_profile_id: str = Field(alias="dbProfileId")
    target: TargetObject
    outputs: list[RequestedOutputType] = Field(min_length=1)
    options: dict[str, bool] = Field(default_factory=dict)


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


class EvidenceRef(ApiModel):
    type: Literal["MSSQL_METADATA", "STATIC_ANALYSIS", "POLICY", "TEMPLATE", "USER_INPUT"]
    object_ref: str = Field(alias="objectRef")
    locator: str
    snapshot_id: str | None = Field(default=None, alias="snapshotId")


class ArtifactSummary(ApiModel):
    artifact_id: str = Field(alias="artifactId")
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
    artifact_id: str = Field(alias="artifactId")
    status: Literal["PASSED", "FAILED", "REVIEW_REQUIRED"]
    checks: list[ValidationCheck]
    missing_evidence: list[str] = Field(default_factory=list, alias="missingEvidence")
    manual_review_points: list[str] = Field(
        default_factory=list,
        alias="manualReviewPoints",
    )


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


class RegistryVersion(ApiModel):
    registry_type: Literal["PROMPT", "TEMPLATE", "POLICY", "DB_PROFILE", "GENERATOR"] = Field(
        alias="registryType"
    )
    version: str
    active: bool = True
