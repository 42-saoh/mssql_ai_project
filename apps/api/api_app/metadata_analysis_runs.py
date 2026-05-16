from __future__ import annotations

import os
from datetime import UTC, datetime, timedelta

from mssql_mcp_app.errors import MetadataToolError

from api_app.errors import code_for_status
from api_app.metadata_analysis_service import MetadataAnalysisService
from api_app.metadata_service import MetadataSearchDependencyError
from api_app.repositories import (
    KnowledgePersistenceError,
    MetadataAnalysisRunPersistenceError,
    MetadataAnalysisRunRecord,
    WorkflowRepository,
    prefixed_id,
)
from api_app.schemas import (
    MetadataAnalysisRequest,
    MetadataAnalysisResponse,
    MetadataAnalysisRunError,
    MetadataAnalysisRunStatus,
)

DEFAULT_METADATA_ANALYSIS_RUN_STALE_SECONDS = 30 * 60
MIN_METADATA_ANALYSIS_RUN_STALE_SECONDS = 60
ACTIVE_METADATA_ANALYSIS_RUN_STATUSES = frozenset({"QUEUED", "RUNNING"})
TERMINAL_METADATA_ANALYSIS_RUN_STATUSES = frozenset({"SUCCEEDED", "FAILED"})


def create_metadata_analysis_run(
    *,
    repository: WorkflowRepository,
    request: MetadataAnalysisRequest,
) -> MetadataAnalysisRunStatus:
    record = repository.create_metadata_analysis_run(
        run_id=prefixed_id("metadata_run"),
        request=_model_payload(request),
    )
    return present_metadata_analysis_run(record)


def get_metadata_analysis_run(
    *,
    repository: WorkflowRepository,
    run_id: str,
) -> MetadataAnalysisRunStatus | None:
    record = repository.get_metadata_analysis_run(run_id)
    return present_metadata_analysis_run(record) if record else None


def execute_metadata_analysis_run(
    *,
    run_id: str,
    request: MetadataAnalysisRequest | None = None,
    service: MetadataAnalysisService,
    repository: WorkflowRepository,
) -> bool:
    claimed = repository.claim_metadata_analysis_run(
        run_id,
        stale_before=metadata_analysis_run_stale_before(),
    )
    if claimed is None:
        return False
    worker = MetadataAnalysisService(
        model_gateway=service.model_gateway,
        repository=repository,
    )
    try:
        analysis_request = request or MetadataAnalysisRequest.model_validate(claimed.request)
        analysis = worker.analyze(analysis_request)
        if not _metadata_analysis_run_is_terminal(repository, run_id):
            repository.mark_metadata_analysis_run_succeeded(
                run_id,
                analysis=_model_payload(analysis),
            )
    except Exception as exc:  # noqa: BLE001 - polling exposes structured run failure
        error = _metadata_analysis_run_error(exc)
        try:
            if not _metadata_analysis_run_is_terminal(repository, run_id):
                repository.mark_metadata_analysis_run_failed(
                    run_id,
                    error=_model_payload(error),
                )
        except Exception:  # noqa: BLE001 - persistence outage leaves prior status intact
            return True
    return True


def present_metadata_analysis_run(
    record: MetadataAnalysisRunRecord,
) -> MetadataAnalysisRunStatus:
    analysis = (
        MetadataAnalysisResponse.model_validate(record.analysis)
        if record.analysis is not None
        else None
    )
    error = (
        MetadataAnalysisRunError.model_validate(record.error)
        if record.error is not None
        else None
    )
    return MetadataAnalysisRunStatus(
        runId=record.run_id,
        status=record.status,
        submittedAt=record.submitted_at,
        startedAt=record.started_at,
        completedAt=record.completed_at,
        request=MetadataAnalysisRequest.model_validate(record.request),
        analysis=analysis,
        error=error,
    )


def _metadata_analysis_run_error(exc: Exception) -> MetadataAnalysisRunError:
    if isinstance(exc, MetadataSearchDependencyError):
        return MetadataAnalysisRunError(
            code=exc.code,
            message=str(exc.detail),
            statusCode=exc.status_code,
        )
    if isinstance(exc, MetadataToolError):
        return MetadataAnalysisRunError(
            code=exc.code,
            message=exc.message,
            statusCode=exc.http_status,
        )
    if isinstance(exc, (KnowledgePersistenceError, MetadataAnalysisRunPersistenceError)):
        return MetadataAnalysisRunError(
            code=exc.code,
            message=str(exc),
            statusCode=exc.status_code,
        )
    if isinstance(exc, ValueError):
        return MetadataAnalysisRunError(
            code="VALIDATION_ERROR",
            message=str(exc),
            statusCode=422,
        )
    status_code = 500
    return MetadataAnalysisRunError(
        code=code_for_status(status_code),
        message="Metadata analysis run failed.",
        statusCode=status_code,
    )


def _model_payload(
    value: MetadataAnalysisRequest | MetadataAnalysisResponse | MetadataAnalysisRunError,
) -> dict:
    return dict(value.model_dump(mode="json", by_alias=True))


def _metadata_analysis_run_is_terminal(
    repository: WorkflowRepository,
    run_id: str,
) -> bool:
    record = repository.get_metadata_analysis_run(run_id)
    return bool(record and record.status in TERMINAL_METADATA_ANALYSIS_RUN_STATUSES)


def metadata_analysis_run_stale_seconds() -> int:
    raw_value = os.getenv("METADATA_ANALYSIS_RUN_STALE_SECONDS", "").strip()
    if not raw_value:
        return DEFAULT_METADATA_ANALYSIS_RUN_STALE_SECONDS
    try:
        value = int(raw_value)
    except ValueError:
        return DEFAULT_METADATA_ANALYSIS_RUN_STALE_SECONDS
    return max(value, MIN_METADATA_ANALYSIS_RUN_STALE_SECONDS)


def metadata_analysis_run_stale_before(now: datetime | None = None) -> datetime:
    reference = now or _utc_now()
    return reference - timedelta(seconds=metadata_analysis_run_stale_seconds())


def _utc_now() -> datetime:
    return datetime.now(UTC)
