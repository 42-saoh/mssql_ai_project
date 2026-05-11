from __future__ import annotations

from dataclasses import replace
from typing import Any

from ai_agent_domain import ArtifactStatus, ArtifactType, JobStatus, WorkflowStepType

from api_app.auth import Actor, VerifiedIdentity, canonical_role_set
from api_app.contracts import approval_decision_mapping, validation_storage_result
from api_app.lifecycle import (
    artifact_status_after_approval,
    artifact_status_after_validation,
    bounded_artifact_records,
    ensure_artifact_can_change,
    ensure_job_transition,
)
from api_app.repositories import (
    AgentRunRecord,
    ApprovalRecordData,
    ArtifactRecord,
    AuditEventRecord,
    JobRecord,
    MetadataCollectionRecord,
    ValidationReportRecord,
    WorkRequestRecord,
    approval_audit_payload,
    prefixed_id,
    standardized_audit_payload,
    utc_now,
)


class MemoryWorkflowRepository:
    """In-memory WorkflowRepository adapter for fixture-first tests and local demos."""

    def __init__(self) -> None:
        self.requests: dict[str, WorkRequestRecord] = {}
        self.jobs: dict[str, JobRecord] = {}
        self.metadata_collections: dict[str, MetadataCollectionRecord] = {}
        self.agent_runs: dict[str, AgentRunRecord] = {}
        self.artifacts: dict[str, ArtifactRecord] = {}
        self.validation_reports: dict[str, ValidationReportRecord] = {}
        self.approvals: dict[str, ApprovalRecordData] = {}
        self.audit_events: list[AuditEventRecord] = []
        self.auth_actors: dict[str, Actor] = {}

    def add_auth_actor(
        self,
        *,
        subject: str,
        login: str,
        email: str | None = None,
        roles: tuple[str, ...] = ("USER",),
        display_name: str | None = None,
    ) -> Actor:
        actor = Actor(
            actor_id=subject,
            login=login,
            email=email,
            roles=canonical_role_set(roles),
            display_name=display_name,
        )
        for candidate in (subject, login, email):
            if candidate:
                self.auth_actors[candidate.strip().lower()] = actor
        return actor

    def resolve_actor_roles(self, identity: VerifiedIdentity) -> Actor | None:
        for candidate in identity.lookup_candidates:
            actor = self.auth_actors.get(candidate.strip().lower())
            if actor is not None:
                return actor
        return None

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
        record = WorkRequestRecord(
            request_id=prefixed_id("req"),
            db_profile_id=db_profile_id,
            target=target,
            outputs=outputs,
            options=options,
            request_hash=request_hash,
            correlation_id=correlation_id,
            idempotency_key=idempotency_key,
        )
        self.requests[record.request_id] = record
        self.record_audit_event(
            action="REQUEST_SUBMITTED",
            target_type="WORK_REQUEST",
            target_ref_id=record.request_id,
            payload={
                "dbProfileId": db_profile_id,
                "outputs": list(outputs),
                "tracking": {
                    "correlationId": correlation_id,
                    "idempotencyKey": idempotency_key,
                    "requestHash": request_hash,
                },
            },
            correlation_id=correlation_id,
        )
        return replace(record)

    def find_request_by_idempotency_key(
        self,
        idempotency_key: str,
    ) -> WorkRequestRecord | None:
        for request in self.requests.values():
            if request.idempotency_key == idempotency_key:
                return replace(request)
        return None

    def update_request_status(self, request_id: str, status: JobStatus) -> None:
        request = self.requests[request_id]
        request.status = status
        request.updated_at = utc_now()

    def create_job(self, request_id: str, *, correlation_id: str | None = None) -> JobRecord:
        record = JobRecord(
            job_id=prefixed_id("job"),
            request_id=request_id,
            correlation_id=correlation_id,
        )
        self.jobs[record.job_id] = record
        return replace(record)

    def find_job_by_request_id(self, request_id: str) -> JobRecord | None:
        for job in self.jobs.values():
            if job.request_id == request_id:
                return replace(job)
        return None

    def transition_job(
        self,
        job_id: str,
        *,
        status: JobStatus,
        current_step: WorkflowStepType | None,
    ) -> JobRecord:
        job = self.jobs[job_id]
        ensure_job_transition(job.status, status)
        job.status = status
        job.current_step = current_step
        job.updated_at = utc_now()
        job.transitions.append((status, current_step))
        self.update_request_status(job.request_id, status)
        self.record_audit_event(
            action="JOB_TRANSITIONED",
            target_type="JOB",
            target_ref_id=job_id,
            payload={
                "status": status.value,
                "currentStep": current_step.value if current_step else None,
            },
            correlation_id=job.correlation_id,
        )
        return replace(job)

    def fail_job(self, job_id: str, *, code: str, message: str) -> JobRecord:
        job = self.jobs[job_id]
        ensure_job_transition(job.status, JobStatus.FAILED)
        job.status = JobStatus.FAILED
        job.error_code = code
        job.error_message = message
        job.updated_at = utc_now()
        job.transitions.append((JobStatus.FAILED, job.current_step))
        self.update_request_status(job.request_id, JobStatus.FAILED)
        self.record_audit_event(
            action="JOB_FAILED",
            target_type="JOB",
            target_ref_id=job_id,
            payload={"code": code, "message": message},
            correlation_id=job.correlation_id,
        )
        return replace(job)

    def save_metadata_collection(
        self,
        *,
        job_id: str,
        status: str,
        payload: dict[str, Any],
    ) -> MetadataCollectionRecord:
        record = MetadataCollectionRecord(
            metadata_id=prefixed_id("meta"),
            job_id=job_id,
            status=status,
            payload=payload,
        )
        self.metadata_collections[record.metadata_id] = record
        job = self.jobs.get(job_id)
        self.record_audit_event(
            action="METADATA_COLLECTED",
            target_type="JOB",
            target_ref_id=job_id,
            payload={"status": status, "snapshotId": payload.get("snapshotId")},
            correlation_id=job.correlation_id if job else None,
        )
        return record

    def latest_metadata_for_job(self, job_id: str) -> MetadataCollectionRecord | None:
        records = [
            record for record in self.metadata_collections.values() if record.job_id == job_id
        ]
        return records[-1] if records else None

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
        record = AgentRunRecord(
            agent_run_id=prefixed_id("agent"),
            job_id=job_id,
            agent_type=agent_type,
            status=status,
            target_ref=target_ref,
            summary=summary,
            structured_output=structured_output,
            model_invocation=model_invocation,
        )
        self.agent_runs[record.agent_run_id] = record
        job = self.jobs.get(job_id)
        self.record_audit_event(
            action="AGENT_RUN_RECORDED",
            target_type="JOB",
            target_ref_id=job_id,
            payload={
                "agentRunId": record.agent_run_id,
                "agentType": agent_type,
                "status": status,
                "targetRef": target_ref,
                "modelInvocation": _public_model_invocation(model_invocation),
            },
            correlation_id=job.correlation_id if job else None,
        )
        return record

    def list_agent_runs(
        self,
        job_id: str,
        *,
        limit: int | None = None,
    ) -> list[AgentRunRecord] | None:
        if job_id not in self.jobs:
            return None
        runs = sorted(
            [record for record in self.agent_runs.values() if record.job_id == job_id],
            key=lambda record: (record.created_at, record.agent_run_id),
            reverse=True,
        )
        if limit is not None:
            runs = runs[: max(min(int(limit), 100), 1)]
        return runs

    def add_artifact(
        self,
        *,
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
        record = ArtifactRecord(
            artifact_id=prefixed_id("art"),
            job_id=job_id,
            type=artifact_type,
            status=ArtifactStatus.DRAFT,
            title=title,
            content=content,
            evidence_refs=evidence_refs,
            generator_version=generator_version,
            registry_refs=registry_refs,
            assumptions=assumptions,
            review_required=review_required,
            extra=extra or {},
        )
        self.artifacts[record.artifact_id] = record
        job = self.jobs.get(job_id)
        self.record_audit_event(
            action="ARTIFACT_CREATED",
            target_type="ARTIFACT",
            target_ref_id=record.artifact_id,
            payload={
                "artifactId": record.artifact_id,
                "jobId": job_id,
                "artifactType": artifact_type.value,
                "status": record.status.value,
            },
            correlation_id=job.correlation_id if job else None,
        )
        return record

    def get_job(self, job_id: str) -> JobRecord | None:
        return self.jobs.get(job_id)

    def list_jobs(self, *, limit: int | None = None) -> list[JobRecord]:
        jobs = sorted(
            self.jobs.values(),
            key=lambda job: (job.created_at, job.job_id),
            reverse=True,
        )
        if limit is not None:
            jobs = jobs[: max(min(int(limit), 100), 1)]
        return [replace(job) for job in jobs]

    def get_artifact(self, artifact_id: str) -> ArtifactRecord | None:
        return self.artifacts.get(artifact_id)

    def list_job_artifacts(
        self,
        job_id: str,
        *,
        limit: int | None = None,
    ) -> list[ArtifactRecord] | None:
        if job_id not in self.jobs:
            return None
        return bounded_artifact_records(
            [artifact for artifact in self.artifacts.values() if artifact.job_id == job_id],
            limit=limit,
        )

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
        artifact = self.artifacts[artifact_id]
        next_status = artifact_status_after_validation(status, artifact.status)
        ensure_artifact_can_change(artifact.status, next_status)
        record = ValidationReportRecord(
            validation_report_id=prefixed_id("val"),
            artifact_id=artifact_id,
            status=status,
            checks=checks,
            missing_evidence=missing_evidence,
            manual_review_points=manual_review_points,
            storage_result=validation_storage_result(status),
        )
        self.validation_reports[record.validation_report_id] = record
        artifact.latest_validation_report_id = record.validation_report_id
        artifact.latest_validation_status = record.status
        artifact.updated_at = utc_now()
        artifact.status = next_status
        self.record_audit_event(
            action="ARTIFACT_VALIDATED",
            target_type="ARTIFACT",
            target_ref_id=artifact_id,
            payload={
                "status": status,
                "storageResult": record.storage_result,
                "validationReportId": record.validation_report_id,
            },
            correlation_id=correlation_id or self.jobs[artifact.job_id].correlation_id,
            actor=actor,
        )
        return record

    def latest_validation_for(self, artifact_id: str) -> ValidationReportRecord | None:
        artifact = self.artifacts.get(artifact_id)
        if artifact is None or artifact.latest_validation_report_id is None:
            return None
        return self.validation_reports.get(artifact.latest_validation_report_id)

    def has_validation_report(self, validation_report_id: str) -> bool:
        return validation_report_id in self.validation_reports

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
        mapping = approval_decision_mapping(decision)
        artifact = self.artifacts[artifact_id]
        next_status = artifact_status_after_approval(decision)
        ensure_artifact_can_change(artifact.status, next_status)
        record = ApprovalRecordData(
            approval_id=prefixed_id("aprv"),
            artifact_id=artifact_id,
            decision=decision,
            reviewer=reviewer,
            comment=comment,
            validation_report_id=validation_report_id,
            storage_decision=mapping.storage_decision,
            persistence_note=mapping.persistence_note,
            reviewer_checklist=reviewer_checklist or [],
            validation_summary=validation_summary or {},
        )
        self.approvals[record.approval_id] = record
        artifact.latest_approval_id = record.approval_id
        artifact.updated_at = utc_now()
        artifact.status = next_status
        resolved_correlation_id = (
            correlation_id
            or (
                self.jobs[artifact.job_id].correlation_id
                if artifact.job_id in self.jobs
                else None
            )
        )
        self.record_audit_event(
            action="APPROVAL_DECISION_RECORDED",
            target_type="ARTIFACT",
            target_ref_id=artifact_id,
            payload=approval_audit_payload(
                artifact=artifact,
                approval=record,
                validation_report_id=validation_report_id,
                correlation_id=resolved_correlation_id,
            ),
            actor=reviewer,
            correlation_id=resolved_correlation_id,
        )
        return record

    def latest_approval_for(self, artifact_id: str) -> ApprovalRecordData | None:
        artifact = self.artifacts.get(artifact_id)
        if artifact is None or artifact.latest_approval_id is None:
            return None
        return self.approvals.get(artifact.latest_approval_id)

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
        audit_payload = standardized_audit_payload(
            action=action,
            target_type=target_type,
            target_ref_id=target_ref_id,
            payload=payload,
            actor=actor,
            correlation_id=correlation_id,
        )
        record = AuditEventRecord(
            audit_id=prefixed_id("audit"),
            action=action,
            target_type=target_type,
            target_ref_id=target_ref_id,
            payload=audit_payload,
            actor=actor,
            correlation_id=correlation_id,
        )
        self.audit_events.append(record)
        return record


def _public_model_invocation(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in payload.items()
        if key
        in {
            "provider",
            "model",
            "modelProfileId",
            "modelRegistryRef",
            "reasoningEffort",
            "promptVersion",
            "outputSchemaVersion",
            "inputHash",
            "promptHash",
            "outputHash",
            "status",
            "tokenUsage",
            "latencyMs",
            "componentInvocations",
        }
    }
