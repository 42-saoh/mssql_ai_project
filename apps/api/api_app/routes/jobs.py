from fastapi import APIRouter, HTTPException

router = APIRouter(prefix="/api/v1/jobs", tags=["jobs"])

_JOBS = {
    "job_demo_001": {
        "jobId": "job_demo_001",
        "status": "REVIEW_PENDING",
        "requestId": "req_demo_001",
        "currentStep": "VALIDATING",
    }
}


@router.get("/{job_id}")
def get_job(job_id: str) -> dict:
    job = _JOBS.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Unknown job: {job_id}")
    return job
