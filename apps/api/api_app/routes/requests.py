from typing import Annotated

from api_app.dependencies import get_workflow_service
from api_app.errors import api_http_exception
from api_app.schemas import SPAnalysisRequest, SubmitRequestResponse
from api_app.tracking import IdempotencyConflictError, tracking_context_from_request
from api_app.workflow import WorkflowService
from fastapi import APIRouter, Depends, Request, status

router = APIRouter(prefix="/api/v1/requests", tags=["requests"])


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
