from typing import Annotated

from api_app.dependencies import get_repository
from api_app.errors import api_http_exception
from api_app.knowledge_service import present_knowledge_asset
from api_app.presenters import present_agent_run, present_job
from api_app.repositories import KnowledgePersistenceError, WorkflowRepository
from api_app.schemas import AgentRunSummary, Job, KnowledgeAssetSummary
from fastapi import APIRouter, Depends, Query

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])


@router.get("")
def list_jobs(
    repository: Annotated[WorkflowRepository, Depends(get_repository)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict[str, list[Job]]:
    return {"jobs": [present_job(job) for job in repository.list_jobs(limit=limit)]}


@router.get("/{jobId}", response_model=Job)
def get_job(
    jobId: str,
    repository: Annotated[WorkflowRepository, Depends(get_repository)],
) -> Job:
    job = repository.get_job(jobId)
    if job is None:
        raise api_http_exception(
            status_code=404,
            detail=f"Unknown job: {jobId}",
            code="RESOURCE_NOT_FOUND",
        )
    return present_job(job)


@router.get("/{jobId}/agent-runs")
def list_job_agent_runs(
    jobId: str,
    repository: Annotated[WorkflowRepository, Depends(get_repository)],
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> dict[str, str | list[AgentRunSummary]]:
    runs = repository.list_agent_runs(jobId, limit=limit)
    if runs is None:
        raise api_http_exception(
            status_code=404,
            detail=f"Unknown job: {jobId}",
            code="RESOURCE_NOT_FOUND",
        )
    return {"jobId": jobId, "agentRuns": [present_agent_run(run) for run in runs]}


@router.get("/{jobId}/knowledge-assets")
def list_job_knowledge_assets(
    jobId: str,
    repository: Annotated[WorkflowRepository, Depends(get_repository)],
) -> dict[str, str | list[KnowledgeAssetSummary]]:
    try:
        assets = repository.list_job_knowledge_assets(jobId)
    except KnowledgePersistenceError as exc:
        raise api_http_exception(
            status_code=exc.status_code,
            detail=str(exc),
            code=exc.code,
        ) from exc
    if assets is None:
        raise api_http_exception(
            status_code=404,
            detail=f"Unknown job: {jobId}",
            code="RESOURCE_NOT_FOUND",
        )
    return {"jobId": jobId, "knowledgeAssets": [present_knowledge_asset(asset) for asset in assets]}
