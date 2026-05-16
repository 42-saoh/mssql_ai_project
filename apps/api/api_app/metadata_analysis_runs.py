from __future__ import annotations

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
    request: MetadataAnalysisRequest,
    service: MetadataAnalysisService,
    repository: WorkflowRepository,
) -> None:
    worker = MetadataAnalysisService(
        model_gateway=service.model_gateway,
        repository=repository,
    )
    try:
        repository.mark_metadata_analysis_run_running(run_id)
        analysis = worker.analyze(request)
        repository.mark_metadata_analysis_run_succeeded(
            run_id,
            analysis=_model_payload(analysis),
        )
    except Exception as exc:  # noqa: BLE001 - polling exposes structured run failure
        error = _metadata_analysis_run_error(exc)
        try:
            repository.mark_metadata_analysis_run_failed(
                run_id,
                error=_model_payload(error),
            )
        except Exception:  # noqa: BLE001 - persistence outage leaves prior status intact
            return


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
