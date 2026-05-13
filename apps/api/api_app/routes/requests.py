import os
from typing import Annotated

from api_app.backpressure import (
    WORKFLOW_BACKPRESSURE,
    WorkflowBackpressureError,
    workflow_limit_summary,
)
from api_app.dependencies import get_workflow_service
from api_app.errors import api_http_exception
from api_app.repositories import prefixed_id
from api_app.schemas import (
    SPAnalysisBatchAcceptedItem,
    SPAnalysisBatchRejectedItem,
    SPAnalysisBatchRequest,
    SPAnalysisBatchResponse,
    SPAnalysisRequest,
    SubmitRequestResponse,
)
from api_app.tracking import (
    IdempotencyConflictError,
    RequestTrackingContext,
    tracking_context_from_request,
)
from api_app.workflow import WorkflowService
from fastapi import APIRouter, Depends, Request, status

router = APIRouter(prefix="/api/v1/requests", tags=["requests"])

BATCH_TARGET_LIMIT_EXCEEDED = "BATCH_TARGET_LIMIT_EXCEEDED"
DUPLICATE_TARGET_SKIPPED = "DUPLICATE_TARGET_SKIPPED"


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        return int(value)
    except ValueError:
        return default


@router.post(
    "/sp-analysis",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=SubmitRequestResponse,
)
def create_sp_analysis(
    req: SPAnalysisRequest,
    request: Request,
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> SubmitRequestResponse:
    try:
        tracking = tracking_context_from_request(request)
        request_record, job = service.submit_sp_analysis(req, tracking=tracking)
    except WorkflowBackpressureError as exc:
        raise api_http_exception(
            status_code=429,
            detail=str(exc),
            code=WORKFLOW_BACKPRESSURE,
        ) from exc
    except IdempotencyConflictError as exc:
        raise api_http_exception(
            status_code=409,
            detail=str(exc),
            code="IDEMPOTENCY_CONFLICT",
        ) from exc
    except ValueError as exc:
        raise api_http_exception(status_code=400, detail=str(exc), code="BAD_REQUEST") from exc
    return SubmitRequestResponse(
        requestId=request_record.request_id,
        jobId=job.job_id,
        status=job.status,
        echo=req.to_response(),
    )


@router.post(
    "/sp-analysis/batch",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=SPAnalysisBatchResponse,
)
def create_sp_analysis_batch(
    req: SPAnalysisBatchRequest,
    request: Request,
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> SPAnalysisBatchResponse:
    max_targets = _env_int("SP_BATCH_MAX_TARGETS", 20)
    max_concurrent_jobs = _env_int("SP_BATCH_MAX_CONCURRENT_JOBS", 2)
    limits = {
        "maxTargets": max_targets,
        "maxConcurrentJobs": max_concurrent_jobs,
        **workflow_limit_summary(),
    }
    if len(req.targets) > max_targets:
        raise api_http_exception(
            status_code=400,
            detail=f"Batch target count exceeds SP_BATCH_MAX_TARGETS={max_targets}.",
            code=BATCH_TARGET_LIMIT_EXCEEDED,
        )

    tracking = tracking_context_from_request(request)
    batch_id = prefixed_id("batch")
    accepted: list[SPAnalysisBatchAcceptedItem] = []
    rejected: list[SPAnalysisBatchRejectedItem] = []
    seen_targets: set[tuple[str, str, str]] = set()

    for target in req.targets:
        key = (
            target.type,
            target.schema_name.strip().lower(),
            target.name.strip().lower(),
        )
        if key in seen_targets:
            rejected.append(
                SPAnalysisBatchRejectedItem(
                    target=target,
                    code=DUPLICATE_TARGET_SKIPPED,
                    message="Duplicate target in the same batch was skipped.",
                )
            )
            continue
        seen_targets.add(key)
        child_request = SPAnalysisRequest(
            dbProfileId=req.db_profile_id,
            target=target,
            outputs=req.outputs,
            options=req.options,
        )
        child_tracking = RequestTrackingContext(
            correlation_id=tracking.correlation_id,
            idempotency_key=None,
        )
        try:
            request_record, job = service.submit_sp_analysis(
                child_request,
                tracking=child_tracking,
            )
        except WorkflowBackpressureError as exc:
            raise api_http_exception(
                status_code=429,
                detail=str(exc),
                code=WORKFLOW_BACKPRESSURE,
            ) from exc
        except (IdempotencyConflictError, ValueError) as exc:
            rejected.append(
                SPAnalysisBatchRejectedItem(
                    target=target,
                    code=getattr(exc, "code", "BAD_REQUEST"),
                    message=str(exc),
                )
            )
            continue
        accepted.append(
            SPAnalysisBatchAcceptedItem(
                target=target,
                requestId=request_record.request_id,
                jobId=job.job_id,
                status=job.status,
            )
        )

    batch_status = "ACCEPTED" if accepted and not rejected else "PARTIAL"
    if not accepted:
        batch_status = "REJECTED"
    return SPAnalysisBatchResponse(
        batchId=batch_id,
        status=batch_status,
        accepted=accepted,
        rejected=rejected,
        limits=limits,
    )
