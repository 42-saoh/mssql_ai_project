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
    options: dict[str, Any]
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
class AgentRunRecord:
    agent_run_id: str
    job_id: str
    agent_type: str
    status: str
    target_ref: str
    summary: str
    structured_output: dict[str, Any]
    model_invocation: dict[str, Any]
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
    reviewer_checklist: list[dict[str, Any]] = field(default_factory=list)
    validation_summary: dict[str, Any] = field(default_factory=dict)
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


class KnowledgePersistenceError(RuntimeError):
    def __init__(
        self,
        message: str,
        *,
        code: str = "KNOWLEDGE_PERSISTENCE_FAILED",
        status_code: int = 503,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.status_code = status_code


@dataclass
class KnowledgeAssetRecord:
    asset_id: str
    asset_kind: str
    db_profile_id: str
    target_type: str
    target_schema: str
    target_name: str
    logical_key: str
    current_version_id: str | None = None
    current_version_no: int = 0
    content_hash: str | None = None
    source_job_id: str | None = None
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)


@dataclass
class KnowledgeFactRecord:
    fact_id: str
    version_id: str
    asset_id: str
    fact_type: str
    object_ref: str
    summary: str
    status: str
    evidence_refs: list[str]
    payload: dict[str, Any]
    content_hash: str
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class KnowledgeEdgeRecord:
    edge_id: str
    version_id: str
    asset_id: str
    from_fact_id: str
    to_fact_id: str
    edge_type: str
    evidence_refs: list[str]
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class KnowledgeAssetVersionRecord:
    version_id: str
    asset_id: str
    version_no: int
    content_hash: str
    payload: dict[str, Any]
    facts: list[KnowledgeFactRecord]
    edges: list[KnowledgeEdgeRecord]
    source_job_id: str | None = None
    created_at: datetime = field(default_factory=utc_now)


@dataclass
class KnowledgeExportRecord:
    export_id: str
    format: str
    content_type: str
    content: str
    content_hash: str
    asset_ids: list[str]
    created_at: datetime = field(default_factory=utc_now)


class WorkflowRepository(Protocol):
    def create_request(
        self,
        *,
        db_profile_id: str,
        target: dict[str, Any],
        outputs: tuple[str, ...],
        options: dict[str, Any],
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

    def save_agent_run(
        self,
        *,
        job_id: str,
        agent_type: str,
        status: str,
        target_ref: str,
        summary: str,
        structured_output: dict[str, Any],
        model_invocation: dict[str, Any],
    ) -> AgentRunRecord:
        ...

    def list_agent_runs(
        self,
        job_id: str,
        *,
        limit: int | None = None,
    ) -> list[AgentRunRecord] | None:
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

    def list_jobs(self, *, limit: int | None = None) -> list[JobRecord]:
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
        actor: str = "api-system",
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
        reviewer_checklist: list[dict[str, Any]] | None = None,
        validation_summary: dict[str, Any] | None = None,
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

    def upsert_knowledge_asset(
        self,
        *,
        job_id: str | None,
        db_profile_id: str,
        asset_kind: str,
        target: dict[str, str],
        payload: dict[str, Any],
        facts: list[dict[str, Any]],
        edges: list[dict[str, Any]],
        content_hash: str,
    ) -> KnowledgeAssetVersionRecord:
        ...

    def list_job_knowledge_assets(self, job_id: str) -> list[KnowledgeAssetRecord] | None:
        ...

    def get_knowledge_asset(self, asset_id: str) -> KnowledgeAssetRecord | None:
        ...

    def list_knowledge_asset_versions(
        self,
        asset_id: str,
    ) -> list[KnowledgeAssetVersionRecord] | None:
        ...

    def get_knowledge_asset_version(
        self,
        asset_id: str,
        version_id: str,
    ) -> KnowledgeAssetVersionRecord | None:
        ...

    def list_knowledge_facts(
        self,
        asset_id: str,
        version_id: str,
    ) -> tuple[list[KnowledgeFactRecord], list[KnowledgeEdgeRecord]] | None:
        ...

    def save_knowledge_export(
        self,
        *,
        export_format: str,
        content_type: str,
        content: str,
        content_hash: str,
        asset_ids: list[str],
    ) -> KnowledgeExportRecord:
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


AUDIT_STAGE_BY_ACTION: dict[str, str] = {
    "REQUEST_SUBMITTED": "REQUEST",
    "IDEMPOTENT_REQUEST_REPLAYED": "REQUEST",
    "JOB_TRANSITIONED": "JOB",
    "JOB_FAILED": "JOB",
    "METADATA_COLLECTED": "METADATA",
    "AGENT_RUN_RECORDED": "AGENT_RUNTIME",
    "ARTIFACT_CREATED": "ARTIFACT",
    "ARTIFACT_VALIDATED": "VALIDATION",
    "APPROVAL_DECISION_RECORDED": "APPROVAL",
    "PUBLISH_GATE_EVALUATED": "APPROVAL_GATE",
    "KNOWLEDGE_ASSET_VERSIONED": "KNOWLEDGE",
    "KNOWLEDGE_EXPORTED": "KNOWLEDGE",
}


def standardized_audit_payload(
    *,
    action: str,
    target_type: str,
    target_ref_id: str,
    payload: dict[str, Any],
    actor: str,
    correlation_id: str | None,
) -> dict[str, Any]:
    audit_payload = dict(payload)
    if correlation_id:
        current_tracking = dict(audit_payload.get("tracking") or {})
        current_tracking["correlationId"] = correlation_id
        audit_payload["tracking"] = current_tracking
        audit_payload["correlationId"] = correlation_id
    audit_payload.setdefault("stage", audit_stage(action, target_type))
    audit_payload.setdefault("actor", actor)
    audit_payload.setdefault(
        "targetRef",
        {
            "type": target_type,
            "id": target_ref_id,
        },
    )
    refs = dict(audit_payload.get("refs") or {})
    for key in (
        "requestId",
        "jobId",
        "metadataId",
        "artifactId",
        "validationReportId",
        "approvalId",
    ):
        value = audit_payload.get(key)
        if value is not None:
            refs[key] = str(value)[:128]
    if refs:
        audit_payload["refs"] = refs
    return audit_payload


def approval_audit_payload(
    *,
    artifact: ArtifactRecord,
    approval: ApprovalRecordData,
    validation_report_id: str | None,
    correlation_id: str | None,
) -> dict[str, Any]:
    artifact_version = artifact_version_ref(artifact)
    selected_object_refs = selected_object_refs_for_artifact(artifact)
    refs = {
        "artifactId": artifact.artifact_id,
        "artifactVersion": artifact_version,
        "approvalId": approval.approval_id,
    }
    if validation_report_id:
        refs["validationReportId"] = validation_report_id
    payload: dict[str, Any] = {
        "decision": approval.decision,
        "storageDecision": approval.storage_decision,
        "artifactId": artifact.artifact_id,
        "artifactVersion": artifact_version,
        "artifactRef": {
            "artifactId": artifact.artifact_id,
            "artifactVersion": artifact_version,
            "artifactType": artifact.type.value,
        },
        "validationReportId": validation_report_id,
        "validationRef": {
            "validationReportId": validation_report_id,
            "artifactId": artifact.artifact_id,
            "artifactVersion": artifact_version,
            "validationStatus": approval.validation_summary.get("status"),
        },
        "approvalId": approval.approval_id,
        "approvalRef": {
            "approvalId": approval.approval_id,
            "decision": approval.decision,
            "storageDecision": approval.storage_decision,
        },
        "selectedObjectRefs": selected_object_refs,
        "evidenceRefs": list(artifact.evidence_refs),
        "timestamp": approval.decided_at.isoformat(),
        "actor": approval.reviewer,
        "reviewerChecklist": approval.reviewer_checklist,
        "refs": refs,
    }
    if correlation_id:
        payload["correlationId"] = correlation_id
    return payload


def artifact_version_ref(artifact: ArtifactRecord) -> str:
    for key in ("artifactVersion", "artifact_version", "version"):
        value = artifact.extra.get(key)
        if value:
            return str(value)
    return "v1"


def selected_object_refs_for_artifact(artifact: ArtifactRecord) -> list[str]:
    value = artifact.extra.get("selectedObjectRefs")
    if value is None:
        value = artifact.extra.get("selected_object_refs")
    if value is None:
        return []
    if isinstance(value, str):
        cleaned = value.strip()
        return [cleaned] if cleaned else []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item).strip()]
    return []


def audit_stage(action: str, target_type: str) -> str:
    if action in AUDIT_STAGE_BY_ACTION:
        return AUDIT_STAGE_BY_ACTION[action]
    return target_type.replace("-", "_").replace(" ", "_").upper()


def audit_correlation_id(payload: dict[str, Any]) -> str | None:
    direct = payload.get("correlationId")
    if direct:
        return str(direct)
    tracking = payload.get("tracking")
    if isinstance(tracking, dict) and tracking.get("correlationId"):
        return str(tracking["correlationId"])
    return None


def bounded_artifacts(
    artifacts: list[ArtifactRecord],
    *,
    limit: int | None = None,
) -> list[ArtifactRecord]:
    return bounded_artifact_records(artifacts, limit=limit)
