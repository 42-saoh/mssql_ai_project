from __future__ import annotations

from typing import Any

from ai_agent_domain import ArtifactStatus, JobStatus

DEFAULT_PAGE_LIMIT = 100
MAX_PAGE_LIMIT = 100


class WorkflowStateError(ValueError):
    """Raised when a workflow state change would violate the product lifecycle."""


ALLOWED_JOB_TRANSITIONS: dict[JobStatus, set[JobStatus]] = {
    JobStatus.SUBMITTED: {JobStatus.COLLECTING_METADATA},
    JobStatus.COLLECTING_METADATA: {JobStatus.ANALYZING},
    JobStatus.ANALYZING: {JobStatus.GENERATING},
    JobStatus.GENERATING: {JobStatus.VALIDATING},
    JobStatus.VALIDATING: {JobStatus.VALIDATION_COMPLETE, JobStatus.FAILED},
}

TERMINAL_JOB_STATUSES = {
    JobStatus.VALIDATION_COMPLETE,
    JobStatus.APPROVED,
    JobStatus.REJECTED,
    JobStatus.PUBLISHED,
    JobStatus.FAILED,
    JobStatus.CANCELED,
}


def ensure_job_transition(current: JobStatus, next_status: JobStatus) -> None:
    if current == next_status:
        return
    if next_status == JobStatus.FAILED and current != JobStatus.PUBLISHED:
        return
    if current in TERMINAL_JOB_STATUSES:
        raise WorkflowStateError(
            f"Cannot transition job from terminal status {current.value} to "
            f"{next_status.value}."
        )
    allowed = ALLOWED_JOB_TRANSITIONS.get(current, set())
    if next_status not in allowed:
        raise WorkflowStateError(
            f"Unsupported job transition: {current.value} -> {next_status.value}."
        )


def ensure_artifact_can_change(current: ArtifactStatus, next_status: ArtifactStatus) -> None:
    if current == ArtifactStatus.PUBLISHED or next_status == ArtifactStatus.PUBLISHED:
        raise WorkflowStateError("Artifact publish transitions are blocked in P09.")


def artifact_status_after_validation(status: str, current: ArtifactStatus) -> ArtifactStatus:
    if current in {ArtifactStatus.APPROVED, ArtifactStatus.REJECTED}:
        return current
    if status == "PASSED":
        return ArtifactStatus.VALIDATED
    if status == "REVIEW_REQUIRED":
        return current
    return current


def normalize_page_limit(limit: int | None) -> int:
    if limit is None:
        return DEFAULT_PAGE_LIMIT
    return min(max(int(limit), 1), MAX_PAGE_LIMIT)


def bounded_artifact_records(
    artifacts: list[Any],
    *,
    limit: int | None = None,
) -> list[Any]:
    page_limit = normalize_page_limit(limit)
    return sorted(artifacts, key=lambda item: (item.created_at, item.artifact_id))[:page_limit]
