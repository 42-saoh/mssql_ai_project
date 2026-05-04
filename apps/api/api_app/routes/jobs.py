from typing import Annotated

from api_app.dependencies import get_repository
from api_app.presenters import present_job
from api_app.repositories import WorkflowRepository
from api_app.schemas import Job
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


@router.get("/{jobId}", response_model=Job)
def get_job(
    jobId: str,
    repository: Annotated[WorkflowRepository, Depends(get_repository)],
) -> Job:
    job = repository.get_job(jobId)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Unknown job: {jobId}")
    return present_job(job)
