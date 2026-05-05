from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import uuid4

from ai_agent_domain import ArtifactStatus, ArtifactType, JobStatus, WorkflowStepType

from api_app.lifecycle import bounded_artifact_records


def utc_now() -> datetime:
    return datetime.now(UTC)


def prefixed_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:10]}"


@dataclass
class WorkRequestRecord:
    request_id: str
    db_profile_id: str
    target: dict[str, Any]
    outputs: tuple[str, ...]
    options: dict[str, bool]
    request_hash: str
    correlation_id: str
    idempotency_key: str | None = None
    status: JobStatus = JobStatus.SUBMITTED
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass
class JobRecord:
    job_id: str
    request_id: str
    status: JobStatus = JobStatus.SUBMITTED
    current_step: WorkflowStepType | None = None
    correlation_id: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    error_code: str | None = None
    error_message: str | None = None
    transitions: list[tuple[JobStatus, WorkflowStepType | None]] = field(default_factory=list)


@dataclass
class MetadataCollectionRecord:
    metadata_id: str
    job_id: str
    status: str
    payload: dict[str, Any]
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class ArtifactRecord:
    artifact_id: str
    job_id: str
    type: ArtifactType
    status: ArtifactStatus
    title: str
    content: str
    evidence_refs: list[dict[str, Any]]
    generator_version: str
    registry_refs: tuple[str, ...]
    assumptions: tuple[str, ...]
    review_required: bool = True
    extra: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    latest_validation_report_id: str | None = None
    latest_validation_status: str | None = None
    latest_approval_id: str | None = None

    @property
    def evidence_coverage(self) -> float:
        return 1.0 if self.evidence_refs else 0.0

    def validation_payload(self) -> dict[str, Any]:
        return {
            "artifactType": self.type.value,
            "title": self.title,
            "content": self.content,
            "evidenceRefs": self.evidence_refs,
            "generatorVersion": self.generator_version,
            "registryRefs": list(self.registry_refs),
            "assumptions": list(self.assumptions),
            "reviewRequired": self.review_required,
            "status": self.status.value,
            "extra": dict(self.extra),
        }


@dataclass
class ValidationReportRecord:
    validation_report_id: str
    artifact_id: str
    status: str
    checks: list[dict[str, str]]
    missing_evidence: list[str]
    manual_review_points: list[str]
    storage_result: str
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class ApprovalRecordData:
    approval_id: str
    artifact_id: str
    decision: str
    reviewer: str
    comment: str
    validation_report_id: str | None
    storage_decision: str
    persistence_note: str
    decided_at: datetime = field(default_factory=utc_now)


@dataclass
class AuditEventRecord:
    audit_id: str
    action: str
    target_type: str
    target_ref_id: str
    payload: dict[str, Any]
    actor: str = "api-system"
    correlation_id: str | None = None
    created_at: datetime = field(default_factory=utc_now)


class WorkflowRepository(Protocol):
    def create_request(
        self,
        *,
        db_profile_id: str,
        target: dict[str, Any],
        outputs: tuple[str, ...],
        options: dict[str, bool],
        request_hash: str,
        correlation_id: str,
        idempotency_key: str | None,
    ) -> WorkRequestRecord:
        ...

    def find_request_by_idempotency_key(
        self,
        idempotency_key: str,
    ) -> WorkRequestRecord | None:
        ...

    def update_request_status(self, request_id: str, status: JobStatus) -> None:
        ...

    def create_job(self, request_id: str, *, correlation_id: str | None = None) -> JobRecord:
        ...

    def find_job_by_request_id(self, request_id: str) -> JobRecord | None:
        ...

    def transition_job(
        self,
        job_id: str,
        *,
        status: JobStatus,
        current_step: WorkflowStepType | None,
    ) -> JobRecord:
        ...

    def fail_job(self, job_id: str, *, code: str, message: str) -> JobRecord:
        ...

    def save_metadata_collection(
        self,
        *,
        job_id: str,
        status: str,
        payload: dict[str, Any],
    ) -> MetadataCollectionRecord:
        ...

    def latest_metadata_for_job(self, job_id: str) -> MetadataCollectionRecord | None:
        ...

    def add_artifact(
        self,
        job_id: str,
        artifact_type: ArtifactType,
        title: str,
        content: str,
        evidence_refs: list[dict[str, Any]],
        generator_version: str,
        registry_refs: tuple[str, ...],
        assumptions: tuple[str, ...],
        review_required: bool,
        extra: dict[str, Any] | None = None,
    ) -> ArtifactRecord:
        ...

    def get_job(self, job_id: str) -> JobRecord | None:
        ...

    def get_artifact(self, artifact_id: str) -> ArtifactRecord | None:
        ...

    def list_job_artifacts(
        self,
        job_id: str,
        *,
        limit: int | None = None,
    ) -> list[ArtifactRecord] | None:
        ...

    def save_validation_report(
        self,
        *,
        artifact_id: str,
        status: str,
        checks: list[dict[str, str]],
        missing_evidence: list[str],
        manual_review_points: list[str],
        correlation_id: str | None = None,
    ) -> ValidationReportRecord:
        ...

    def latest_validation_for(self, artifact_id: str) -> ValidationReportRecord | None:
        ...

    def has_validation_report(self, validation_report_id: str) -> bool:
        ...

    def add_approval(
        self,
        *,
        artifact_id: str,
        decision: str,
        reviewer: str,
        comment: str,
        validation_report_id: str | None,
        correlation_id: str | None = None,
    ) -> ApprovalRecordData:
        ...

    def latest_approval_for(self, artifact_id: str) -> ApprovalRecordData | None:
        ...

    def record_audit_event(
        self,
        *,
        action: str,
        target_type: str,
        target_ref_id: str,
        payload: dict[str, Any],
        actor: str = "api-system",
        correlation_id: str | None = None,
    ) -> AuditEventRecord:
        ...


def tracking_payload(
    *,
    correlation_id: str | None,
    idempotency_key: str | None = None,
    request_hash: str | None = None,
) -> dict[str, str]:
    payload: dict[str, str] = {}
    if correlation_id:
        payload["correlationId"] = correlation_id
    if idempotency_key:
        payload["idempotencyKey"] = idempotency_key
    if request_hash:
        payload["requestHash"] = request_hash
    return payload


def bounded_artifacts(
    artifacts: list[ArtifactRecord],
    *,
    limit: int | None = None,
) -> list[ArtifactRecord]:
    return bounded_artifact_records(artifacts, limit=limit)
