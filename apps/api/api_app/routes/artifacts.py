from __future__ import annotations

from typing import Annotated

from api_app.dependencies import get_repository, get_workflow_service
from api_app.presenters import (
    present_artifact,
    present_artifact_summary,
    present_validation_report,
)
from api_app.repositories import WorkflowRepository
from api_app.schemas import Artifact, ArtifactSummary, ValidationReport
from api_app.workflow import WorkflowService
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter(tags=["artifacts"])


@router.get("/api/v1/jobs/{jobId}/artifacts")
def list_job_artifacts(
    jobId: str,
    repository: Annotated[WorkflowRepository, Depends(get_repository)],
) -> dict[str, str | list[ArtifactSummary]]:
    artifacts = repository.list_job_artifacts(jobId)
    if artifacts is None:
        raise HTTPException(status_code=404, detail=f"Unknown job: {jobId}")
    return {
        "jobId": jobId,
        "artifacts": [present_artifact_summary(artifact) for artifact in artifacts],
    }


@router.get("/api/v1/artifacts/{artifactId}", response_model=Artifact)
def get_artifact(
    artifactId: str,
    repository: Annotated[WorkflowRepository, Depends(get_repository)],
) -> Artifact:
    artifact = repository.get_artifact(artifactId)
    if artifact is None:
        raise HTTPException(status_code=404, detail=f"Unknown artifact: {artifactId}")
    return present_artifact(artifact)


@router.post("/api/v1/artifacts/{artifactId}/validation", response_model=ValidationReport)
def validate_artifact(
    artifactId: str,
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
) -> ValidationReport:
    try:
        report = service.validate_artifact(artifactId)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Unknown artifact: {artifactId}") from exc
    return present_validation_report(report)
