from __future__ import annotations

from typing import Annotated

from api_app.dependencies import get_workflow_service
from api_app.presenters import present_approval_record
from api_app.schemas import ApprovalDecisionRequest, ApprovalRecord
from api_app.workflow import WorkflowService
from fastapi import APIRouter, Depends, HTTPException, status

router = APIRouter(prefix="/api/v1/artifacts", tags=["approvals"])


@router.post(
    "/{artifactId}/approval-decisions",
    status_code=status.HTTP_201_CREATED,
    response_model=ApprovalRecord,
)
def create_approval_decision(
    artifactId: str,
    req: ApprovalDecisionRequest,
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> ApprovalRecord:
    try:
        record = service.record_approval_decision(
            artifact_id=artifactId,
            decision=req.decision,
            reviewer=req.reviewer,
            comment=req.comment,
            validation_report_id=req.validation_report_id,
        )
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown artifact: {artifactId}") from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return present_approval_record(record)
