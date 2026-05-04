from typing import Annotated

from api_app.dependencies import get_workflow_service
from api_app.schemas import SPAnalysisRequest, SubmitRequestResponse
from api_app.workflow import WorkflowService
from fastapi import APIRouter, Depends, HTTPException, status

router = APIRouter(prefix="/api/v1/requests", tags=["requests"])


@router.post(
    "/sp-analysis",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=SubmitRequestResponse,
)
def create_sp_analysis(
    req: SPAnalysisRequest,
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> SubmitRequestResponse:
    try:
        request_record, job = service.submit_sp_analysis(req)
    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
            headers={"X-Error-Code": "BAD_REQUEST"},
        ) from exc
    return SubmitRequestResponse(
        requestId=request_record.request_id,
        jobId=job.job_id,
        status=job.status,
        echo=req.to_response(),
    )
