from enum import StrEnum

from pydantic import BaseModel


class JobStatus(StrEnum):
    SUBMITTED = "SUBMITTED"
    COLLECTING_METADATA = "COLLECTING_METADATA"
    ANALYZING = "ANALYZING"
    GENERATING = "GENERATING"
    VALIDATING = "VALIDATING"
    REVIEW_PENDING = "REVIEW_PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PUBLISHED = "PUBLISHED"
    FAILED = "FAILED"


class ArtifactStatus(StrEnum):
    DRAFT = "DRAFT"
    VALIDATED = "VALIDATED"
    REVIEW_PENDING = "REVIEW_PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"
    PUBLISHED = "PUBLISHED"


class JobSummary(BaseModel):
    job_id: str
    status: JobStatus
    request_id: str
