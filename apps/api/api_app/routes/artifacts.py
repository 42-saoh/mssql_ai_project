from __future__ import annotations

from typing import Annotated

from api_app.auth import Actor
from api_app.dependencies import (
    get_repository,
    get_workflow_service,
    require_artifact_review_actor,
)
from api_app.errors import api_http_exception
from api_app.presenters import (
    present_artifact,
    present_artifact_summary,
    present_validation_report,
)
from api_app.repositories import WorkflowRepository
from api_app.schemas import Artifact, ArtifactSummary, ValidationReport
from api_app.tracking import tracking_context_from_request
from api_app.workflow import WorkflowService
from fastapi import APIRouter, Depends, Request

router = APIRouter(tags=["artifacts"])


@router.get("/api/v1/jobs/{jobId}/artifacts")
def list_job_artifacts(
    jobId: str,
    repository: Annotated[WorkflowRepository, Depends(get_repository)],
) -> dict[str, str | list[ArtifactSummary]]:
    artifacts = repository.list_job_artifacts(jobId)
    if artifacts is None:
        raise api_http_exception(
            status_code=404,
            detail=f"Unknown job: {jobId}",
            code="RESOURCE_NOT_FOUND",
        )
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
        raise api_http_exception(
            status_code=404,
            detail=f"Unknown artifact: {artifactId}",
            code="RESOURCE_NOT_FOUND",
        )
    return present_artifact(artifact)


@router.post("/api/v1/artifacts/{artifactId}/validation", response_model=ValidationReport)
def validate_artifact(
    artifactId: str,
    request: Request,
    service: Annotated[WorkflowService, Depends(get_workflow_service)],
    actor: Annotated[Actor | None, Depends(require_artifact_review_actor)],
) -> ValidationReport:
    try:
        report = service.validate_artifact(
            artifactId,
            correlation_id=tracking_context_from_request(request).correlation_id,
            actor=actor.reviewer_id if actor else None,
        )
    except KeyError as exc:
        raise api_http_exception(
            status_code=404,
            detail=f"Unknown artifact: {artifactId}",
            code="RESOURCE_NOT_FOUND",
        ) from exc
    return present_validation_report(report)


@router.get(
    "/api/v1/artifacts/{artifactId}/validation/latest",
    response_model=ValidationReport,
)
def get_latest_validation(
    artifactId: str,
    repository: Annotated[WorkflowRepository, Depends(get_repository)],
) -> ValidationReport:
    artifact = repository.get_artifact(artifactId)
    if artifact is None:
        raise api_http_exception(
            status_code=404,
            detail=f"Unknown artifact: {artifactId}",
            code="RESOURCE_NOT_FOUND",
        )
    report = repository.latest_validation_for(artifactId)
    if report is None:
        raise api_http_exception(
            status_code=404,
            detail=f"No validation report recorded for artifact: {artifactId}",
            code="RESOURCE_NOT_FOUND",
        )
    return present_validation_report(report)
