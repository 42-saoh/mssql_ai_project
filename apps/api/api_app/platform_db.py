from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from datetime import datetime
from typing import Any
from uuid import UUID, uuid5

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
from api_app.live_gate import (
    P21_LIVE_PLF_UNAVAILABLE,
    P21_LIVE_PORTAL_REQUIRED_ENV_MISSING,
    p21_live_portal_enabled,
)
from api_app.repositories import (
    AgentRunRecord,
    ApprovalRecordData,
    ArtifactRecord,
    AuditEventRecord,
    JobRecord,
    KnowledgeAssetRecord,
    KnowledgeAssetVersionRecord,
    KnowledgeEdgeRecord,
    KnowledgeExportRecord,
    KnowledgeFactRecord,
    KnowledgePersistenceError,
    MetadataCollectionRecord,
    ValidationReportRecord,
    WorkflowRepository,
    WorkRequestRecord,
    approval_audit_payload,
    audit_correlation_id,
    prefixed_id,
    standardized_audit_payload,
    tracking_payload,
    utc_now,
)

STORAGE_NAMESPACE = UUID("a8e6e20c-0158-5d6f-8a39-a97f7325c6a2")


class PlatformPersistenceError(RuntimeError):
    """Raised when platform DB persistence cannot safely continue."""

    def __init__(self, message: str, *, code: str = "DEPENDENCY_BLOCKED") -> None:
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class PlatformDbSettings:
    host: str
    port: int
    user: str
    password: str
    database: str
    requester_login: str
    connect_timeout_seconds: int = 5

    @property
    def configured(self) -> bool:
        return bool(self.host and self.user and self.password and self.database)

    @property
    def safe_summary(self) -> dict[str, str | int | bool]:
        return {
            "host": self.host,
            "port": self.port,
            "database": self.database,
            "userConfigured": bool(self.user),
            "passwordConfigured": bool(self.password),
            "requesterLogin": self.requester_login,
        }


def load_platform_db_settings() -> PlatformDbSettings:
    return PlatformDbSettings(
        host=os.getenv("PLATFORM_DB_HOST", "").strip(),
        port=_env_int("PLATFORM_DB_PORT", 1433),
        user=os.getenv("PLATFORM_DB_USER", "").strip(),
        password=os.getenv("PLATFORM_DB_PASSWORD", ""),
        database=os.getenv("PLATFORM_DB_NAME", "").strip(),
        requester_login=os.getenv("PLATFORM_DB_REQUESTER_LOGIN", "codex-api-local").strip()
        or "codex-api-local",
        connect_timeout_seconds=_env_int("PLATFORM_DB_CONNECT_TIMEOUT_SECONDS", 5),
    )


def build_platform_repository() -> WorkflowRepository:
    settings = load_platform_db_settings()
    if not settings.configured:
        raise platform_missing_env_error()
    return MssqlPlatformRepository(settings)


def platform_missing_env_error() -> PlatformPersistenceError:
    return PlatformPersistenceError(
        "Platform MSSQL repository requires PLATFORM_DB_HOST, PLATFORM_DB_USER, "
        "PLATFORM_DB_PASSWORD, and PLATFORM_DB_NAME.",
        code=(
            P21_LIVE_PORTAL_REQUIRED_ENV_MISSING
            if p21_live_portal_enabled()
            else "DEPENDENCY_BLOCKED"
        ),
    )


def platform_unavailable_error(message: str) -> PlatformPersistenceError:
    return PlatformPersistenceError(
        message,
        code=P21_LIVE_PLF_UNAVAILABLE if p21_live_portal_enabled() else "DEPENDENCY_BLOCKED",
    )


class MssqlPlatformRepository:
    def __init__(self, settings: PlatformDbSettings) -> None:
        self.settings = settings

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
        requester_id = self._resolve_user_id(self.settings.requester_login)
        storage_profile_id = self._resolve_db_profile_id(db_profile_id)
        self._execute(
            """
            INSERT INTO dbo.CORE_WORK_REQUESTS(
                REQ_ID, REQ_TP_CD, REQR_USR_ID, DB_PRFL_ID, TRGT_PAYLD_JSON,
                DESIRED_RSLT_JSON, OPTN_PAYLD_JSON, CUR_STAT_CD, TRC_ID,
                SUBMITTED_DTM, UPD_DTM
            )
            VALUES (%s, 'SP_ANALYSIS', %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                storage_uuid(record.request_id),
                requester_id,
                storage_profile_id,
                json_text(record.target),
                json_text(list(record.outputs)),
                json_text(options_storage_payload(record)),
                record.status.value,
                record.request_id,
                record.created_at,
                record.updated_at,
            ),
        )
        self.record_audit_event(
            action="REQUEST_SUBMITTED",
            target_type="WORK_REQUEST",
            target_ref_id=record.request_id,
            payload={
                "dbProfileId": db_profile_id,
                "outputs": list(outputs),
                "tracking": tracking_payload(
                    correlation_id=correlation_id,
                    idempotency_key=idempotency_key,
                    request_hash=request_hash,
                ),
            },
            correlation_id=correlation_id,
        )
        return record

    def find_request_by_idempotency_key(
        self,
        idempotency_key: str,
    ) -> WorkRequestRecord | None:
        row = self._query_one(
            """
            SELECT TOP (1)
                COALESCE(TRC_ID, CONVERT(NVARCHAR(36), REQ_ID)),
                TRGT_PAYLD_JSON,
                DESIRED_RSLT_JSON,
                OPTN_PAYLD_JSON,
                CUR_STAT_CD,
                SUBMITTED_DTM,
                UPD_DTM
            FROM dbo.CORE_WORK_REQUESTS
            WHERE JSON_VALUE(OPTN_PAYLD_JSON, '$.__tracking.idempotencyKey') = %s
            ORDER BY SUBMITTED_DTM DESC
            """,
            (idempotency_key,),
        )
        if row is None:
            return None
        options_payload = parse_json(row[3], {})
        tracking = dict(options_payload.get("__tracking") or {})
        options_payload.pop("__tracking", None)
        return WorkRequestRecord(
            request_id=str(row[0]),
            db_profile_id=str(tracking.get("dbProfileId") or ""),
            target=dict(parse_json(row[1], {})),
            outputs=tuple(parse_json(row[2], [])),
            options=dict(options_payload),
            request_hash=str(tracking.get("requestHash") or ""),
            correlation_id=str(tracking.get("correlationId") or ""),
            idempotency_key=str(tracking.get("idempotencyKey") or idempotency_key),
            status=JobStatus(str(row[4])),
            created_at=as_datetime(row[5]),
            updated_at=as_datetime(row[6]),
        )

    def update_request_status(self, request_id: str, status: JobStatus) -> None:
        self._execute(
            """
            UPDATE dbo.CORE_WORK_REQUESTS
            SET CUR_STAT_CD = %s, UPD_DTM = SYSUTCDATETIME()
            WHERE REQ_ID = %s OR TRC_ID = %s
            """,
            (status.value, storage_uuid(request_id), request_id),
        )

    def create_job(self, request_id: str, *, correlation_id: str | None = None) -> JobRecord:
        record = JobRecord(
            job_id=prefixed_id("job"),
            request_id=request_id,
            correlation_id=correlation_id,
        )
        self._execute(
            """
            INSERT INTO dbo.CORE_JOBS(
                JOB_ID, REQ_ID, CUR_STAT_CD, START_DTM, CUR_STEP_TP_CD,
                RGST_BINDING_JSON, WRKR_REF_ID, ERR_CD, ERR_CNTNT, CRE_DTM, UPD_DTM
            )
            VALUES (%s, %s, %s, %s, NULL, %s, %s, NULL, NULL, %s, %s)
            """,
            (
                storage_uuid(record.job_id),
                storage_uuid(request_id),
                record.status.value,
                record.created_at,
                json_text(
                    {
                        "source": "api-workflow",
                        "publicJobId": record.job_id,
                        "correlationId": correlation_id,
                    }
                ),
                record.job_id,
                record.created_at,
                record.updated_at,
            ),
        )
        return record

    def find_job_by_request_id(self, request_id: str) -> JobRecord | None:
        row = self._query_one(
            """
            SELECT TOP (1)
                CONVERT(NVARCHAR(36), j.JOB_ID),
                COALESCE(j.WRKR_REF_ID, CONVERT(NVARCHAR(36), j.JOB_ID)),
                COALESCE(r.TRC_ID, CONVERT(NVARCHAR(36), j.REQ_ID)),
                j.CUR_STAT_CD,
                j.CUR_STEP_TP_CD,
                j.ERR_CD,
                j.ERR_CNTNT,
                j.CRE_DTM,
                j.UPD_DTM,
                j.RGST_BINDING_JSON
            FROM dbo.CORE_JOBS j
            JOIN dbo.CORE_WORK_REQUESTS r ON r.REQ_ID = j.REQ_ID
            WHERE r.TRC_ID = %s OR r.REQ_ID = %s
            ORDER BY j.CRE_DTM DESC
            """,
            (request_id, storage_uuid(request_id)),
        )
        return job_from_row(row) if row else None

    def transition_job(
        self,
        job_id: str,
        *,
        status: JobStatus,
        current_step: WorkflowStepType | None,
    ) -> JobRecord:
        job = self.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        ensure_job_transition(job.status, status)
        job.status = status
        job.current_step = current_step
        job.updated_at = utc_now()
        job.transitions.append((status, current_step))
        self._execute(
            """
            UPDATE dbo.CORE_JOBS
            SET CUR_STAT_CD = %s,
                CUR_STEP_TP_CD = %s,
                WRKR_REF_ID = %s,
                UPD_DTM = SYSUTCDATETIME()
            WHERE JOB_ID = %s OR WRKR_REF_ID = %s
            """,
            (
                status.value,
                current_step.value if current_step else None,
                job.job_id,
                storage_uuid(job.job_id),
                job.job_id,
            ),
        )
        self.update_request_status(job.request_id, status)
        self._insert_job_step(job.job_id, current_step, status)
        self.record_audit_event(
            action="JOB_TRANSITIONED",
            target_type="JOB",
            target_ref_id=job.job_id,
            payload={
                "status": status.value,
                "currentStep": current_step.value if current_step else None,
            },
            correlation_id=job.correlation_id,
        )
        return job

    def fail_job(self, job_id: str, *, code: str, message: str) -> JobRecord:
        job = self.get_job(job_id)
        if job is None:
            raise KeyError(job_id)
        job.status = JobStatus.FAILED
        job.error_code = code
        job.error_message = message
        job.updated_at = utc_now()
        self._execute(
            """
            UPDATE dbo.CORE_JOBS
            SET CUR_STAT_CD = 'FAILED',
                ERR_CD = %s,
                ERR_CNTNT = %s,
                UPD_DTM = SYSUTCDATETIME()
            WHERE JOB_ID = %s OR WRKR_REF_ID = %s
            """,
            (code, message[:2000], storage_uuid(job.job_id), job.job_id),
        )
        self.update_request_status(job.request_id, JobStatus.FAILED)
        self._insert_job_step(job.job_id, job.current_step, JobStatus.FAILED)
        self.record_audit_event(
            action="JOB_FAILED",
            target_type="JOB",
            target_ref_id=job.job_id,
            payload={"code": code, "message": message},
            correlation_id=job.correlation_id,
        )
        return job

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
        self._execute(
            """
            INSERT INTO dbo.METADATA_SNAPSHOTS(
                SNAP_ID, DB_PRFL_ID, SNAP_SCOPE_CD, OBJ_SCOPE_JSON, SRC_HASH_VAL,
                CAPTURED_DTM, CAPTURED_JOB_ID, REM_CNTNT
            )
            VALUES (%s, %s, 'JOB_BOUND', %s, %s, %s, %s, %s)
            """,
            (
                storage_uuid(record.metadata_id),
                self._resolve_db_profile_id(str(payload.get("dbProfileId", ""))),
                json_text(payload.get("objectRef")),
                str(payload.get("snapshotId") or "")[:128],
                record.created_at,
                storage_uuid(job_id),
                status,
            ),
        )
        job = self.get_job(job_id)
        self.record_audit_event(
            action="METADATA_COLLECTED",
            target_type="JOB",
            target_ref_id=job_id,
            payload={"status": status, "snapshotId": payload.get("snapshotId")},
            correlation_id=job.correlation_id if job else None,
        )
        return record

    def latest_metadata_for_job(self, job_id: str) -> MetadataCollectionRecord | None:
        row = self._query_one(
            """
            SELECT TOP (1)
                CONVERT(NVARCHAR(36), SNAP_ID),
                OBJ_SCOPE_JSON,
                SRC_HASH_VAL,
                REM_CNTNT,
                CAPTURED_DTM
            FROM dbo.METADATA_SNAPSHOTS
            WHERE CAPTURED_JOB_ID = %s
            ORDER BY CAPTURED_DTM DESC
            """,
            (storage_uuid(job_id),),
        )
        if row is None:
            return None
        payload = {
            "objectRef": parse_json(row[1], None),
            "snapshotId": row[2],
            "status": row[3],
        }
        return MetadataCollectionRecord(
            metadata_id=str(row[0]),
            job_id=job_id,
            status=str(row[3] or "COLLECTED"),
            payload=payload,
            created_at=as_datetime(row[4]),
        )

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
        self._execute(
            """
            INSERT INTO dbo.AGENT_RUNS(
                AGNT_RUN_ID, JOB_ID, AGNT_TP_CD, STAT_CD, TRGT_REF_TXT,
                SMRY_TXT, STRUCTURED_OUTPUT_JSON, MODEL_INVOCATION_JSON, CRE_DTM
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                storage_uuid(record.agent_run_id),
                storage_uuid(job_id),
                agent_type,
                status,
                target_ref,
                summary,
                json_text(structured_output),
                json_text(model_invocation),
                record.created_at,
            ),
        )
        self._execute(
            """
            INSERT INTO dbo.MODEL_INVOCATIONS(
                MDL_INVC_ID, AGNT_RUN_ID, PRVDR_NM, MDL_NM, MDL_PRFL_ID,
                RSNG_EFFORT_CD, PROMPT_VER_REF, OUTPUT_SCHEMA_VER_REF,
                INPUT_HASH_SHA256_VAL, PROMPT_HASH_SHA256_VAL, OUTPUT_HASH_SHA256_VAL,
                TOKEN_USAGE_JSON, LATENCY_MS, STAT_CD, CRE_DTM
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                storage_uuid(f"{record.agent_run_id}:model:1"),
                storage_uuid(record.agent_run_id),
                str(model_invocation.get("provider") or ""),
                str(model_invocation.get("model") or ""),
                str(model_invocation.get("modelProfileId") or ""),
                model_invocation.get("reasoningEffort"),
                str(model_invocation.get("promptVersion") or ""),
                str(model_invocation.get("outputSchemaVersion") or ""),
                str(model_invocation.get("inputHash") or ""),
                str(model_invocation.get("promptHash") or ""),
                str(model_invocation.get("outputHash") or ""),
                json_text(model_invocation.get("tokenUsage") or {}),
                model_invocation.get("latencyMs"),
                status,
                record.created_at,
            ),
        )
        job = self.get_job(job_id)
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
        if self.get_job(job_id) is None:
            return None
        normalized_limit = normalize_list_limit(limit)
        rows = self._query_all(
            f"""
            SELECT TOP ({normalized_limit})
                CONVERT(NVARCHAR(36), AGNT_RUN_ID),
                AGNT_TP_CD,
                STAT_CD,
                TRGT_REF_TXT,
                SMRY_TXT,
                STRUCTURED_OUTPUT_JSON,
                MODEL_INVOCATION_JSON,
                CRE_DTM
            FROM dbo.AGENT_RUNS
            WHERE JOB_ID = %s
            ORDER BY CRE_DTM DESC, AGNT_RUN_ID DESC
            """,
            (storage_uuid(job_id),),
        )
        return [agent_run_from_row(row, job_id) for row in rows]

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
        self._save_artifact(record)
        job = self.get_job(job_id)
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
        row = self._query_one(
            """
            SELECT
                CONVERT(NVARCHAR(36), j.JOB_ID),
                COALESCE(j.WRKR_REF_ID, CONVERT(NVARCHAR(36), j.JOB_ID)),
                COALESCE(r.TRC_ID, CONVERT(NVARCHAR(36), j.REQ_ID)),
                j.CUR_STAT_CD,
                j.CUR_STEP_TP_CD,
                j.ERR_CD,
                j.ERR_CNTNT,
                j.CRE_DTM,
                j.UPD_DTM,
                j.RGST_BINDING_JSON
            FROM dbo.CORE_JOBS j
            JOIN dbo.CORE_WORK_REQUESTS r ON r.REQ_ID = j.REQ_ID
            WHERE j.JOB_ID = %s OR j.WRKR_REF_ID = %s
            """,
            (storage_uuid(job_id), job_id),
        )
        return job_from_row(row) if row else None

    def list_jobs(self, *, limit: int | None = None) -> list[JobRecord]:
        normalized_limit = normalize_list_limit(limit)
        rows = self._query_all(
            f"""
            SELECT TOP ({normalized_limit})
                CONVERT(NVARCHAR(36), j.JOB_ID),
                COALESCE(j.WRKR_REF_ID, CONVERT(NVARCHAR(36), j.JOB_ID)),
                COALESCE(r.TRC_ID, CONVERT(NVARCHAR(36), j.REQ_ID)),
                j.CUR_STAT_CD,
                j.CUR_STEP_TP_CD,
                j.ERR_CD,
                j.ERR_CNTNT,
                j.CRE_DTM,
                j.UPD_DTM,
                j.RGST_BINDING_JSON
            FROM dbo.CORE_JOBS j
            JOIN dbo.CORE_WORK_REQUESTS r ON r.REQ_ID = j.REQ_ID
            ORDER BY j.CRE_DTM DESC, j.JOB_ID DESC
            """,
            (),
        )
        return [job_from_row(row) for row in rows]

    def get_artifact(self, artifact_id: str) -> ArtifactRecord | None:
        row = self._query_one(
            (
                f"{artifact_select_sql()} "
                "WHERE a.ARTF_ID = %s OR CONVERT(NVARCHAR(36), a.ARTF_ID) = %s"
            ),
            (storage_uuid(artifact_id), artifact_id),
        )
        return self._artifact_from_row(row) if row else None

    def list_job_artifacts(
        self,
        job_id: str,
        *,
        limit: int | None = None,
    ) -> list[ArtifactRecord] | None:
        if self.get_job(job_id) is None:
            return None
        rows = self._query_all(
            f"{artifact_select_sql()} WHERE a.JOB_ID = %s ORDER BY a.CRE_DTM, a.ARTF_ID",
            (storage_uuid(job_id),),
        )
        return bounded_artifact_records(
            [artifact for row in rows if (artifact := self._artifact_from_row(row))],
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
        artifact = self.get_artifact(artifact_id)
        if artifact is None:
            raise KeyError(artifact_id)
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
        self._execute(
            """
            INSERT INTO dbo.ARTIFACT_VALIDATION_REPORTS(
                VLDT_RSLT_ID, ARTF_VER_ID, VLDT_PRFL_NM, VLDT_RSLT_CD,
                RSLT_JSON, MISSING_EVDC_JSON, MANUAL_RVWR_POINTS_JSON, CRE_DTM,
                CRE_USR_ID
            )
            VALUES (%s, %s, 'api-workflow', %s, %s, %s, %s, %s, %s)
            """,
            (
                storage_uuid(record.validation_report_id),
                storage_uuid(f"{artifact_id}:v1"),
                record.storage_result,
                json_text(
                    {
                        "validationReportId": record.validation_report_id,
                        "artifactId": artifact_id,
                        "status": record.status,
                        "checks": record.checks,
                    }
                ),
                json_text(record.missing_evidence),
                json_text(record.manual_review_points),
                record.created_at,
                self._try_resolve_user_id(actor),
            ),
        )
        artifact.latest_validation_report_id = record.validation_report_id
        artifact.latest_validation_status = record.status
        artifact.updated_at = utc_now()
        artifact.status = next_status
        self._save_artifact(artifact)
        self.record_audit_event(
            action="ARTIFACT_VALIDATED",
            target_type="ARTIFACT",
            target_ref_id=artifact_id,
            payload={
                "status": status,
                "storageResult": record.storage_result,
                "validationReportId": record.validation_report_id,
            },
            correlation_id=correlation_id or self._correlation_for_artifact(artifact),
            actor=actor,
        )
        return record

    def latest_validation_for(self, artifact_id: str) -> ValidationReportRecord | None:
        row = self._query_one(
            """
            SELECT TOP (1)
                CONVERT(NVARCHAR(36), VLDT_RSLT_ID),
                VLDT_RSLT_CD,
                RSLT_JSON,
                MISSING_EVDC_JSON,
                MANUAL_RVWR_POINTS_JSON,
                CRE_DTM
            FROM dbo.ARTIFACT_VALIDATION_REPORTS
            WHERE ARTF_VER_ID = %s
            ORDER BY CRE_DTM DESC
            """,
            (storage_uuid(f"{artifact_id}:v1"),),
        )
        return validation_from_row(row, artifact_id) if row else None

    def has_validation_report(self, validation_report_id: str) -> bool:
        return bool(
            self._query_one(
                """
                SELECT 1
                FROM dbo.ARTIFACT_VALIDATION_REPORTS
                WHERE VLDT_RSLT_ID = %s
                   OR CONVERT(NVARCHAR(36), VLDT_RSLT_ID) = %s
                """,
                (storage_uuid(validation_report_id), validation_report_id),
            )
        )

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
        artifact = self.get_artifact(artifact_id)
        if artifact is None:
            raise KeyError(artifact_id)
        mapping = approval_decision_mapping(decision)
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
        self._execute(
            """
            INSERT INTO dbo.ARTIFACT_APPROVAL_RECORDS(
                APRV_ID, ARTF_VER_ID, RVWR_USR_ID, DCISN_CD, RVWR_CNTNT,
                CHKLST_RSLT_JSON, APRV_DTM
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                storage_uuid(record.approval_id),
                storage_uuid(f"{artifact_id}:v1"),
                self._resolve_user_id(reviewer),
                record.storage_decision,
                comment,
                json_text(
                    {
                        "approvalId": record.approval_id,
                        "artifactId": artifact_id,
                        "apiDecision": decision,
                        "validationReportId": validation_report_id,
                        "persistenceNote": record.persistence_note,
                        "reviewerChecklist": record.reviewer_checklist,
                        "validationSummary": record.validation_summary,
                    }
                ),
                record.decided_at,
            ),
        )
        artifact.latest_approval_id = record.approval_id
        artifact.updated_at = utc_now()
        artifact.status = next_status
        self._save_artifact(artifact)
        resolved_correlation_id = correlation_id or self._correlation_for_artifact(artifact)
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
        row = self._query_one(
            """
            SELECT TOP (1)
                CONVERT(NVARCHAR(36), a.APRV_ID),
                a.DCISN_CD,
                a.RVWR_CNTNT,
                a.CHKLST_RSLT_JSON,
                a.APRV_DTM,
                COALESCE(u.EML_ADR, u.LGN_ID)
            FROM dbo.ARTIFACT_APPROVAL_RECORDS a
            JOIN dbo.AUTH_USERS u ON u.USR_ID = a.RVWR_USR_ID
            WHERE a.ARTF_VER_ID = %s
            ORDER BY a.APRV_DTM DESC
            """,
            (storage_uuid(f"{artifact_id}:v1"),),
        )
        return approval_from_row(row, artifact_id) if row else None

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
        trace_id = audit_correlation_id(audit_payload)
        record = AuditEventRecord(
            audit_id=prefixed_id("audit"),
            action=action,
            target_type=target_type,
            target_ref_id=target_ref_id,
            payload=audit_payload,
            actor=actor,
            correlation_id=trace_id,
        )
        self._execute(
            """
            INSERT INTO dbo.AUDIT_EVENTS(
                AUDT_ID, ACTR_USR_ID, ACTION_CD, TRGT_TP_CD, TRGT_REF_ID,
                TRC_ID, PAYLD_JSON, AUDT_DTM
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """,
            (
                storage_uuid(record.audit_id),
                self._try_resolve_user_id(actor),
                action,
                target_type,
                target_ref_id[:100],
                trace_id[:100] if trace_id else None,
                json_text(audit_payload),
                record.created_at,
            ),
        )
        return record

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
        self._require_knowledge_schema()
        target_type = str(target.get("type") or "OBJECT")
        target_schema = str(target.get("schema") or "")
        target_name = str(target.get("name") or "")
        logical_key = "|".join(
            [db_profile_id, asset_kind, target_type, target_schema, target_name]
        ).lower()
        asset = self._knowledge_asset_by_logical_key(logical_key)
        now = utc_now()
        if asset is None:
            asset = KnowledgeAssetRecord(
                asset_id=prefixed_id("know"),
                asset_kind=asset_kind,
                db_profile_id=db_profile_id,
                target_type=target_type,
                target_schema=target_schema,
                target_name=target_name,
                logical_key=logical_key,
                source_job_id=job_id,
                created_at=now,
                updated_at=now,
            )
            self._execute(
                """
                INSERT INTO dbo.KNOWLEDGE_ASSETS(
                    ASST_ID, ASST_KIND_CD, DB_PRFL_REF_TXT, TRGT_TP_CD,
                    TRGT_SCHM_NM, TRGT_OBJ_NM, LOGICAL_KEY_TXT, CUR_VER_ID,
                    CUR_VER_NO, CNTNT_HASH_SHA256_VAL, SRC_JOB_ID, CRE_DTM, UPD_DTM
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, NULL, 0, NULL, %s, %s, %s)
                """,
                (
                    asset.asset_id,
                    asset_kind,
                    db_profile_id,
                    target_type,
                    target_schema,
                    target_name,
                    logical_key,
                    job_id,
                    now,
                    now,
                ),
            )
        if asset.content_hash == content_hash and asset.current_version_id:
            existing = self.get_knowledge_asset_version(
                asset.asset_id,
                asset.current_version_id,
            )
            if existing is not None:
                return existing
        version_no = asset.current_version_no + 1
        version_id = prefixed_id("knowv")
        self._execute(
            """
            INSERT INTO dbo.KNOWLEDGE_ASSET_VERSIONS(
                ASST_VER_ID, ASST_ID, VER_SEQ_NO, CNTNT_HASH_SHA256_VAL,
                PAYLD_JSON, SRC_JOB_ID, CRE_DTM
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                version_id,
                asset.asset_id,
                version_no,
                content_hash,
                json_text(payload),
                job_id,
                now,
            ),
        )
        fact_records = []
        for fact in facts:
            record = KnowledgeFactRecord(
                fact_id=str(fact.get("factId") or fact.get("id") or prefixed_id("fact")),
                version_id=version_id,
                asset_id=asset.asset_id,
                fact_type=str(fact.get("factType") or fact.get("type") or asset_kind),
                object_ref=str(fact.get("objectRef") or ""),
                summary=str(fact.get("summary") or ""),
                status=str(fact.get("status") or "REVIEW_REQUIRED"),
                evidence_refs=[str(ref) for ref in fact.get("evidenceRefs", [])],
                payload=dict(fact.get("payload") or {}),
                content_hash=str(fact.get("contentHash") or content_hash),
                created_at=now,
            )
            fact_records.append(record)
            self._execute(
                """
                INSERT INTO dbo.KNOWLEDGE_FACTS(
                    FACT_ID, ASST_VER_ID, ASST_ID, FACT_TP_CD, OBJ_REF_TXT,
                    SMRY_TXT, STAT_CD, EVDC_REFS_JSON, PAYLD_JSON,
                    CNTNT_HASH_SHA256_VAL, CRE_DTM
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    record.fact_id,
                    version_id,
                    asset.asset_id,
                    record.fact_type,
                    record.object_ref,
                    record.summary[:1000],
                    record.status,
                    json_text(record.evidence_refs),
                    json_text(record.payload),
                    record.content_hash,
                    now,
                ),
            )
        edge_records = []
        for edge in edges:
            record = KnowledgeEdgeRecord(
                edge_id=str(edge.get("edgeId") or prefixed_id("edge")),
                version_id=version_id,
                asset_id=asset.asset_id,
                from_fact_id=str(edge.get("fromFactId") or edge.get("from") or ""),
                to_fact_id=str(edge.get("toFactId") or edge.get("to") or ""),
                edge_type=str(edge.get("edgeType") or edge.get("type") or "DERIVED_FROM"),
                evidence_refs=[str(ref) for ref in edge.get("evidenceRefs", [])],
                payload=dict(edge.get("payload") or {}),
                created_at=now,
            )
            edge_records.append(record)
            self._execute(
                """
                INSERT INTO dbo.KNOWLEDGE_FACT_EDGES(
                    EDGE_ID, ASST_VER_ID, ASST_ID, FROM_FACT_ID, TO_FACT_ID,
                    EDGE_TP_CD, EVDC_REFS_JSON, PAYLD_JSON, CRE_DTM
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    record.edge_id,
                    version_id,
                    asset.asset_id,
                    record.from_fact_id,
                    record.to_fact_id,
                    record.edge_type,
                    json_text(record.evidence_refs),
                    json_text(record.payload),
                    now,
                ),
            )
        self._execute(
            """
            UPDATE dbo.KNOWLEDGE_ASSETS
            SET CUR_VER_ID = %s,
                CUR_VER_NO = %s,
                CNTNT_HASH_SHA256_VAL = %s,
                SRC_JOB_ID = COALESCE(%s, SRC_JOB_ID),
                UPD_DTM = SYSUTCDATETIME()
            WHERE ASST_ID = %s
            """,
            (version_id, version_no, content_hash, job_id, asset.asset_id),
        )
        source_job = self.get_job(job_id) if job_id else None
        self.record_audit_event(
            action="KNOWLEDGE_ASSET_VERSIONED",
            target_type="KNOWLEDGE_ASSET",
            target_ref_id=asset.asset_id,
            payload={
                "assetKind": asset_kind,
                "versionId": version_id,
                "versionNo": version_no,
                "contentHash": content_hash,
                "sourceJobId": job_id,
            },
            correlation_id=source_job.correlation_id if source_job else None,
        )
        return KnowledgeAssetVersionRecord(
            version_id=version_id,
            asset_id=asset.asset_id,
            version_no=version_no,
            content_hash=content_hash,
            payload=payload,
            facts=fact_records,
            edges=edge_records,
            source_job_id=job_id,
            created_at=now,
        )

    def list_job_knowledge_assets(self, job_id: str) -> list[KnowledgeAssetRecord] | None:
        self._require_knowledge_schema()
        if self.get_job(job_id) is None:
            return None
        rows = self._query_all(
            """
            SELECT ASST_ID, ASST_KIND_CD, DB_PRFL_REF_TXT, TRGT_TP_CD,
                   TRGT_SCHM_NM, TRGT_OBJ_NM, LOGICAL_KEY_TXT, CUR_VER_ID,
                   CUR_VER_NO, CNTNT_HASH_SHA256_VAL, SRC_JOB_ID, CRE_DTM, UPD_DTM
            FROM dbo.KNOWLEDGE_ASSETS
            WHERE SRC_JOB_ID = %s
            ORDER BY UPD_DTM DESC, ASST_ID DESC
            """,
            (job_id,),
        )
        return [knowledge_asset_from_row(row) for row in rows]

    def get_knowledge_asset(self, asset_id: str) -> KnowledgeAssetRecord | None:
        self._require_knowledge_schema()
        row = self._query_one(
            """
            SELECT ASST_ID, ASST_KIND_CD, DB_PRFL_REF_TXT, TRGT_TP_CD,
                   TRGT_SCHM_NM, TRGT_OBJ_NM, LOGICAL_KEY_TXT, CUR_VER_ID,
                   CUR_VER_NO, CNTNT_HASH_SHA256_VAL, SRC_JOB_ID, CRE_DTM, UPD_DTM
            FROM dbo.KNOWLEDGE_ASSETS
            WHERE ASST_ID = %s
            """,
            (asset_id,),
        )
        return knowledge_asset_from_row(row) if row else None

    def list_knowledge_asset_versions(
        self,
        asset_id: str,
    ) -> list[KnowledgeAssetVersionRecord] | None:
        self._require_knowledge_schema()
        if self.get_knowledge_asset(asset_id) is None:
            return None
        rows = self._query_all(
            """
            SELECT ASST_VER_ID, ASST_ID, VER_SEQ_NO, CNTNT_HASH_SHA256_VAL,
                   PAYLD_JSON, SRC_JOB_ID, CRE_DTM
            FROM dbo.KNOWLEDGE_ASSET_VERSIONS
            WHERE ASST_ID = %s
            ORDER BY VER_SEQ_NO DESC
            """,
            (asset_id,),
        )
        return [self._knowledge_version_from_row(row) for row in rows]

    def get_knowledge_asset_version(
        self,
        asset_id: str,
        version_id: str,
    ) -> KnowledgeAssetVersionRecord | None:
        self._require_knowledge_schema()
        row = self._query_one(
            """
            SELECT ASST_VER_ID, ASST_ID, VER_SEQ_NO, CNTNT_HASH_SHA256_VAL,
                   PAYLD_JSON, SRC_JOB_ID, CRE_DTM
            FROM dbo.KNOWLEDGE_ASSET_VERSIONS
            WHERE ASST_ID = %s AND ASST_VER_ID = %s
            """,
            (asset_id, version_id),
        )
        return self._knowledge_version_from_row(row) if row else None

    def list_knowledge_facts(
        self,
        asset_id: str,
        version_id: str,
    ) -> tuple[list[KnowledgeFactRecord], list[KnowledgeEdgeRecord]] | None:
        self._require_knowledge_schema()
        if self.get_knowledge_asset_version(asset_id, version_id) is None:
            return None
        return (
            self._knowledge_facts(asset_id, version_id),
            self._knowledge_edges(asset_id, version_id),
        )

    def save_knowledge_export(
        self,
        *,
        export_format: str,
        content_type: str,
        content: str,
        content_hash: str,
        asset_ids: list[str],
    ) -> KnowledgeExportRecord:
        self._require_knowledge_schema()
        record = KnowledgeExportRecord(
            export_id=prefixed_id("kexp"),
            format=export_format,
            content_type=content_type,
            content=content,
            content_hash=content_hash,
            asset_ids=asset_ids,
        )
        self._execute(
            """
            INSERT INTO dbo.KNOWLEDGE_EXPORTS(
                EXPRT_ID, FMT_CD, CNTNT_TP_TXT, CNTNT_TXT,
                CNTNT_HASH_SHA256_VAL, ASST_IDS_JSON, CRE_DTM
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                record.export_id,
                export_format,
                content_type,
                content,
                content_hash,
                json_text(asset_ids),
                record.created_at,
            ),
        )
        self.record_audit_event(
            action="KNOWLEDGE_EXPORTED",
            target_type="KNOWLEDGE_EXPORT",
            target_ref_id=record.export_id,
            payload={
                "format": export_format,
                "contentHash": content_hash,
                "assetIds": asset_ids,
            },
        )
        return record

    def _correlation_for_artifact(self, artifact: ArtifactRecord) -> str | None:
        job = self.get_job(artifact.job_id)
        return job.correlation_id if job else None

    def resolve_actor_roles(self, identity: VerifiedIdentity) -> Actor | None:
        candidates = identity.lookup_candidates[:3]
        if not candidates:
            return None
        padded_candidates = candidates + ("",) * (3 - len(candidates))
        rows = self._query_all(
            """
            SELECT
                CONVERT(NVARCHAR(36), u.USR_ID),
                u.LGN_ID,
                u.EML_ADR,
                u.USR_NM,
                r.AUTH_GRP_NM
            FROM dbo.AUTH_USERS u
            JOIN dbo.AUTH_USER_ROLES ur ON ur.USR_ID = u.USR_ID
            JOIN dbo.AUTH_ROLES r ON r.AUTH_GRP_ID = ur.AUTH_GRP_ID
            WHERE u.STAT_CD = 'ACTIVE'
              AND (
                  u.LGN_ID IN (%s, %s, %s)
                  OR u.EML_ADR IN (%s, %s, %s)
              )
            """,
            (*padded_candidates, *padded_candidates),
        )
        if not rows:
            return None
        user_ids = {str(row[0]) for row in rows}
        if len(user_ids) != 1:
            return None
        first = rows[0]
        roles = canonical_role_set([str(row[4]) for row in rows])
        if not roles:
            return None
        return Actor(
            actor_id=identity.subject,
            login=str(first[1] or ""),
            email=str(first[2]) if first[2] else None,
            display_name=str(first[3]) if first[3] else identity.name,
            roles=roles,
        )

    def _save_artifact(self, record: ArtifactRecord) -> None:
        artifact_id = storage_uuid(record.artifact_id)
        artifact_version_id = storage_uuid(f"{record.artifact_id}:v1")
        if not self._exists("dbo.ARTIFACTS", "ARTF_ID", artifact_id):
            self._execute(
                """
                INSERT INTO dbo.ARTIFACTS(
                    ARTF_ID, JOB_ID, ARTF_TP_CD, CUR_STAT_CD, TITL, CRE_DTM, UPD_DTM
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    artifact_id,
                    storage_uuid(record.job_id),
                    record.type.value,
                    record.status.value,
                    record.title,
                    record.created_at,
                    record.updated_at,
                ),
            )
        binding = artifact_binding(record)
        if not self._exists("dbo.ARTIFACT_VERSIONS", "ARTF_VER_ID", artifact_version_id):
            self._execute(
                """
                INSERT INTO dbo.ARTIFACT_VERSIONS(
                    ARTF_VER_ID, ARTF_ID, VER_SEQ_NO, CNTNT_TP_CD, CNTNT_TXT,
                    CHK_SUM_SHA256_VAL, RGST_BINDING_JSON, EVDC_JSON, CRE_DTM
                )
                VALUES (%s, %s, 1, %s, %s, %s, %s, %s, %s)
                """,
                (
                    artifact_version_id,
                    artifact_id,
                    content_type_for_artifact(record),
                    record.content,
                    sha256_hex(record.content),
                    json_text(binding),
                    json_text(record.evidence_refs),
                    record.created_at,
                ),
            )
        else:
            self._execute(
                """
                UPDATE dbo.ARTIFACT_VERSIONS
                SET RGST_BINDING_JSON = %s,
                    EVDC_JSON = %s
                WHERE ARTF_VER_ID = %s
                """,
                (json_text(binding), json_text(record.evidence_refs), artifact_version_id),
            )
        self._execute(
            """
            UPDATE dbo.ARTIFACTS
            SET CUR_STAT_CD = %s,
                CUR_ARTF_VER_ID = %s,
                UPD_DTM = SYSUTCDATETIME()
            WHERE ARTF_ID = %s
            """,
            (record.status.value, artifact_version_id, artifact_id),
        )

    def _artifact_from_row(self, row: tuple[Any, ...] | None) -> ArtifactRecord | None:
        if row is None:
            return None
        binding = parse_json(row[8], {})
        evidence_refs = parse_json(row[9], [])
        public_artifact_id = str(binding.get("publicArtifactId") or row[0])
        public_job_id = str(binding.get("publicJobId") or row[10] or row[1])
        latest_validation = self.latest_validation_for(public_artifact_id)
        latest_approval = self.latest_approval_for(public_artifact_id)
        return ArtifactRecord(
            artifact_id=public_artifact_id,
            job_id=public_job_id,
            type=ArtifactType(str(row[2])),
            status=ArtifactStatus(str(row[3])),
            title=str(row[4] or ""),
            content=str(row[7] or ""),
            evidence_refs=evidence_refs if isinstance(evidence_refs, list) else [],
            generator_version=str(binding.get("generatorVersion") or "unknown"),
            registry_refs=tuple(binding.get("registryRefs") or ()),
            assumptions=tuple(binding.get("assumptions") or ()),
            review_required=bool(binding.get("reviewRequired", True)),
            extra=dict(binding.get("extra") or {}),
            created_at=as_datetime(row[5]),
            updated_at=as_datetime(row[6]),
            latest_validation_report_id=(
                latest_validation.validation_report_id if latest_validation else None
            ),
            latest_validation_status=latest_validation.status if latest_validation else None,
            latest_approval_id=latest_approval.approval_id if latest_approval else None,
        )

    def _insert_job_step(
        self,
        job_id: str,
        current_step: WorkflowStepType | None,
        status: JobStatus,
    ) -> None:
        if current_step is None:
            return
        now = utc_now()
        self._execute(
            """
            INSERT INTO dbo.CORE_JOB_STEPS(
                JOB_ID, STEP_TP_CD, STAT_CD, START_DTM, END_DTM, STEP_JSON, CRE_DTM
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            """,
            (
                storage_uuid(job_id),
                current_step.value,
                "FAILED" if status == JobStatus.FAILED else "SUCCEEDED",
                now,
                now,
                json_text({"jobStatus": status.value}),
                now,
            ),
        )

    def _resolve_user_id(self, login_or_email: str) -> str:
        user_id = self._try_resolve_user_id(login_or_email)
        if user_id is None:
            raise platform_unavailable_error(
                "Platform DB repository requires a matching AUTH_USERS row. "
                "Seed the local platform DB manually first."
            )
        return user_id

    def _try_resolve_user_id(self, login_or_email: str) -> str | None:
        if not login_or_email or login_or_email == "api-system":
            return None
        return self._fetch_value(
            """
            SELECT TOP (1) CONVERT(NVARCHAR(36), USR_ID)
            FROM dbo.AUTH_USERS
            WHERE LGN_ID = %s OR EML_ADR = %s
            """,
            (login_or_email, login_or_email),
        )

    def _resolve_db_profile_id(self, profile_id_or_name: str) -> str:
        db_profile_id = self._fetch_value(
            """
            SELECT TOP (1) CONVERT(NVARCHAR(36), DB_PRFL_ID)
            FROM dbo.CORE_DB_PROFILES
            WHERE DB_PRFL_NM = %s OR DB_NM = %s
            """,
            (profile_id_or_name, profile_id_or_name),
        )
        if db_profile_id is None:
            raise platform_unavailable_error(
                "Platform DB repository requires a matching CORE_DB_PROFILES row. "
                "Seed the local platform DB manually first."
            )
        return db_profile_id

    def _exists(self, table: str, key_column: str, value: str) -> bool:
        return bool(
            self._fetch_value(
                f"SELECT 1 FROM {table} WHERE {key_column} = %s",
                (value,),
            )
        )

    def _require_knowledge_schema(self) -> None:
        row = self._query_one(
            """
            SELECT 1
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = 'dbo'
              AND TABLE_NAME = 'KNOWLEDGE_ASSETS'
            """,
            (),
        )
        if row is None:
            raise KnowledgePersistenceError(
                "Knowledge assetization requires v5 platform schema tables.",
                code="KNOWLEDGE_SCHEMA_REQUIRED",
                status_code=503,
            )

    def _knowledge_asset_by_logical_key(
        self,
        logical_key: str,
    ) -> KnowledgeAssetRecord | None:
        row = self._query_one(
            """
            SELECT ASST_ID, ASST_KIND_CD, DB_PRFL_REF_TXT, TRGT_TP_CD,
                   TRGT_SCHM_NM, TRGT_OBJ_NM, LOGICAL_KEY_TXT, CUR_VER_ID,
                   CUR_VER_NO, CNTNT_HASH_SHA256_VAL, SRC_JOB_ID, CRE_DTM, UPD_DTM
            FROM dbo.KNOWLEDGE_ASSETS
            WHERE LOGICAL_KEY_TXT = %s
            """,
            (logical_key,),
        )
        return knowledge_asset_from_row(row) if row else None

    def _knowledge_version_from_row(
        self,
        row: tuple[Any, ...] | None,
    ) -> KnowledgeAssetVersionRecord | None:
        if row is None:
            return None
        asset_id = str(row[1])
        version_id = str(row[0])
        return KnowledgeAssetVersionRecord(
            version_id=version_id,
            asset_id=asset_id,
            version_no=int(row[2] or 0),
            content_hash=str(row[3] or ""),
            payload=dict(parse_json(row[4], {})),
            facts=self._knowledge_facts(asset_id, version_id),
            edges=self._knowledge_edges(asset_id, version_id),
            source_job_id=str(row[5]) if row[5] else None,
            created_at=as_datetime(row[6]),
        )

    def _knowledge_facts(
        self,
        asset_id: str,
        version_id: str,
    ) -> list[KnowledgeFactRecord]:
        rows = self._query_all(
            """
            SELECT FACT_ID, ASST_VER_ID, ASST_ID, FACT_TP_CD, OBJ_REF_TXT,
                   SMRY_TXT, STAT_CD, EVDC_REFS_JSON, PAYLD_JSON,
                   CNTNT_HASH_SHA256_VAL, CRE_DTM
            FROM dbo.KNOWLEDGE_FACTS
            WHERE ASST_ID = %s AND ASST_VER_ID = %s
            ORDER BY FACT_ID
            """,
            (asset_id, version_id),
        )
        return [
            KnowledgeFactRecord(
                fact_id=str(row[0]),
                version_id=str(row[1]),
                asset_id=str(row[2]),
                fact_type=str(row[3] or ""),
                object_ref=str(row[4] or ""),
                summary=str(row[5] or ""),
                status=str(row[6] or "REVIEW_REQUIRED"),
                evidence_refs=[str(item) for item in parse_json(row[7], [])],
                payload=dict(parse_json(row[8], {})),
                content_hash=str(row[9] or ""),
                created_at=as_datetime(row[10]),
            )
            for row in rows
        ]

    def _knowledge_edges(
        self,
        asset_id: str,
        version_id: str,
    ) -> list[KnowledgeEdgeRecord]:
        rows = self._query_all(
            """
            SELECT EDGE_ID, ASST_VER_ID, ASST_ID, FROM_FACT_ID, TO_FACT_ID,
                   EDGE_TP_CD, EVDC_REFS_JSON, PAYLD_JSON, CRE_DTM
            FROM dbo.KNOWLEDGE_FACT_EDGES
            WHERE ASST_ID = %s AND ASST_VER_ID = %s
            ORDER BY EDGE_ID
            """,
            (asset_id, version_id),
        )
        return [
            KnowledgeEdgeRecord(
                edge_id=str(row[0]),
                version_id=str(row[1]),
                asset_id=str(row[2]),
                from_fact_id=str(row[3] or ""),
                to_fact_id=str(row[4] or ""),
                edge_type=str(row[5] or "DERIVED_FROM"),
                evidence_refs=[str(item) for item in parse_json(row[6], [])],
                payload=dict(parse_json(row[7], {})),
                created_at=as_datetime(row[8]),
            )
            for row in rows
        ]

    def _fetch_value(self, sql: str, params: tuple[Any, ...]) -> str | None:
        row = self._query_one(sql, params)
        if row is None:
            return None
        return str(row[0])

    def _query_one(self, sql: str, params: tuple[Any, ...]) -> tuple[Any, ...] | None:
        rows = self._query_all(sql, params)
        return rows[0] if rows else None

    def _query_all(self, sql: str, params: tuple[Any, ...]) -> list[tuple[Any, ...]]:
        connection = self._connect()
        try:
            cursor = connection.cursor()
            cursor.execute(sql, params)
            return list(cursor.fetchall())
        except PlatformPersistenceError:
            raise
        except Exception:  # pragma: no cover - requires live SQL Server
            raise platform_unavailable_error(
                "Platform DB operation failed. Check schema and seed prerequisites."
            ) from None
        finally:
            connection.close()

    def _execute(self, sql: str, params: tuple[Any, ...]) -> None:
        connection = self._connect()
        try:
            cursor = connection.cursor()
            cursor.execute(sql, params)
        except PlatformPersistenceError:
            raise
        except Exception:  # pragma: no cover - requires live SQL Server
            raise platform_unavailable_error(
                "Platform DB operation failed. Check schema and seed prerequisites."
            ) from None
        finally:
            connection.close()

    def _connect(self):
        if not self.settings.configured:
            raise platform_missing_env_error()
        try:
            import pytds
        except Exception:  # pragma: no cover - dependency/runtime issue
            raise platform_unavailable_error(
                "python-tds is required for platform DB persistence."
            ) from None
        try:
            return pytds.connect(
                dsn=self.settings.host,
                port=self.settings.port,
                database=self.settings.database,
                user=self.settings.user,
                password=self.settings.password,
                login_timeout=self.settings.connect_timeout_seconds,
                timeout=self.settings.connect_timeout_seconds,
                autocommit=True,
                appname="ai-agent-api-platform-repository",
                use_mars=False,
            )
        except Exception:  # pragma: no cover - requires live SQL Server
            raise platform_unavailable_error(
                "Could not connect to platform DB. Check PLATFORM_DB_* settings and "
                "external DB readiness."
            ) from None


def artifact_select_sql() -> str:
    return """
        SELECT
            CONVERT(NVARCHAR(36), a.ARTF_ID),
            CONVERT(NVARCHAR(36), a.JOB_ID),
            a.ARTF_TP_CD,
            a.CUR_STAT_CD,
            a.TITL,
            a.CRE_DTM,
            a.UPD_DTM,
            v.CNTNT_TXT,
            v.RGST_BINDING_JSON,
            v.EVDC_JSON,
            j.WRKR_REF_ID
        FROM dbo.ARTIFACTS a
        JOIN dbo.CORE_JOBS j ON j.JOB_ID = a.JOB_ID
        LEFT JOIN dbo.ARTIFACT_VERSIONS v ON v.ARTF_VER_ID = a.CUR_ARTF_VER_ID
    """


def job_from_row(row: tuple[Any, ...]) -> JobRecord:
    current_step = WorkflowStepType(str(row[4])) if row[4] else None
    binding = parse_json(row[9] if len(row) > 9 else None, {})
    correlation_id = str(binding.get("correlationId") or "") or None
    return JobRecord(
        job_id=str(row[1]),
        request_id=str(row[2]),
        status=JobStatus(str(row[3])),
        current_step=current_step,
        correlation_id=correlation_id,
        error_code=str(row[5]) if row[5] else None,
        error_message=str(row[6]) if row[6] else None,
        created_at=as_datetime(row[7]),
        updated_at=as_datetime(row[8]),
    )


def validation_from_row(
    row: tuple[Any, ...],
    artifact_id: str,
) -> ValidationReportRecord:
    payload = parse_json(row[2], {})
    status = str(payload.get("status") or storage_validation_to_api(str(row[1])))
    return ValidationReportRecord(
        validation_report_id=str(payload.get("validationReportId") or row[0]),
        artifact_id=str(payload.get("artifactId") or artifact_id),
        status=status,
        checks=list(payload.get("checks") or []),
        missing_evidence=list(parse_json(row[3], [])),
        manual_review_points=list(parse_json(row[4], [])),
        storage_result=str(row[1]),
        created_at=as_datetime(row[5]),
    )


def approval_from_row(
    row: tuple[Any, ...],
    artifact_id: str,
) -> ApprovalRecordData:
    payload = parse_json(row[3], {})
    decision = str(payload.get("apiDecision") or storage_approval_to_api(str(row[1])))
    return ApprovalRecordData(
        approval_id=str(payload.get("approvalId") or row[0]),
        artifact_id=str(payload.get("artifactId") or artifact_id),
        decision=decision,
        reviewer=str(row[5] or ""),
        comment=str(row[2] or ""),
        validation_report_id=payload.get("validationReportId"),
        storage_decision=str(row[1]),
        persistence_note=str(payload.get("persistenceNote") or ""),
        reviewer_checklist=list(payload.get("reviewerChecklist") or []),
        validation_summary=dict(payload.get("validationSummary") or {}),
        decided_at=as_datetime(row[4]),
    )


def agent_run_from_row(row: tuple[Any, ...], job_id: str) -> AgentRunRecord:
    return AgentRunRecord(
        agent_run_id=str(row[0]),
        job_id=job_id,
        agent_type=str(row[1]),
        status=str(row[2]),
        target_ref=str(row[3] or ""),
        summary=str(row[4] or ""),
        structured_output=dict(parse_json(row[5], {})),
        model_invocation=dict(parse_json(row[6], {})),
        created_at=as_datetime(row[7]),
    )


def knowledge_asset_from_row(row: tuple[Any, ...]) -> KnowledgeAssetRecord:
    return KnowledgeAssetRecord(
        asset_id=str(row[0]),
        asset_kind=str(row[1]),
        db_profile_id=str(row[2]),
        target_type=str(row[3]),
        target_schema=str(row[4] or ""),
        target_name=str(row[5] or ""),
        logical_key=str(row[6]),
        current_version_id=str(row[7]) if row[7] else None,
        current_version_no=int(row[8] or 0),
        content_hash=str(row[9]) if row[9] else None,
        source_job_id=str(row[10]) if row[10] else None,
        created_at=as_datetime(row[11]),
        updated_at=as_datetime(row[12]),
    )


def artifact_binding(record: ArtifactRecord) -> dict[str, Any]:
    return {
        "publicArtifactId": record.artifact_id,
        "publicJobId": record.job_id,
        "generatorVersion": record.generator_version,
        "registryRefs": list(record.registry_refs),
        "assumptions": list(record.assumptions),
        "reviewRequired": record.review_required,
        "extra": dict(record.extra),
    }


def storage_uuid(public_id: str) -> str:
    return str(uuid5(STORAGE_NAMESPACE, public_id))


def json_text(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)


def options_storage_payload(record: WorkRequestRecord) -> dict[str, Any]:
    payload: dict[str, Any] = dict(record.options)
    payload["__tracking"] = {
        "dbProfileId": record.db_profile_id,
        "correlationId": record.correlation_id,
        "idempotencyKey": record.idempotency_key,
        "requestHash": record.request_hash,
    }
    return payload


def parse_json(value: Any, default: Any) -> Any:
    if value is None or value == "":
        return default
    if isinstance(value, dict | list):
        return value
    try:
        return json.loads(str(value))
    except json.JSONDecodeError:
        return default


def sha256_hex(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def content_type_for_artifact(record: ArtifactRecord) -> str:
    if record.type.value == "MAPPER_XML":
        return "XML"
    if record.type.value in {
        "MAPPER_INTERFACE",
        "SERVICE_DRAFT",
        "DTO_DRAFT",
        "VO_DRAFT",
        "MODEL_DRAFT",
    }:
        return "JAVA"
    if record.type.value == "DDL_DRAFT":
        return "SQL"
    if record.type.value in {"METADATA_QUERY_RESULT", "SCHEMA_ENRICHMENT_RESULT"}:
        return "JSON"
    return "MARKDOWN"


def storage_validation_to_api(value: str) -> str:
    return "PASSED" if value == "PASS" else "FAILED"


def storage_approval_to_api(value: str) -> str:
    return "APPROVE" if value == "APPROVED" else "REJECT"


def normalize_list_limit(limit: int | None, *, default: int = 20) -> int:
    if limit is None:
        return default
    return min(max(int(limit), 1), 100)


def as_datetime(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value
    return utc_now()


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return int(value)


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
