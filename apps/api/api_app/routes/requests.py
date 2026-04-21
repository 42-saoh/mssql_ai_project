from uuid import uuid4

from fastapi import APIRouter
from pydantic import BaseModel, Field

router = APIRouter(prefix="/api/v1/requests", tags=["requests"])


class TargetObject(BaseModel):
    type: str = Field(examples=["PROCEDURE"])
    schema_name: str = Field(alias="schema")
    name: str

    model_config = {"populate_by_name": True}


class SPAnalysisRequest(BaseModel):
    dbProfileId: str
    target: TargetObject
    outputs: list[str]
    options: dict[str, bool] = Field(default_factory=dict)


@router.post("/sp-analysis")
def create_sp_analysis(req: SPAnalysisRequest) -> dict:
    request_id = f"req_{uuid4().hex[:10]}"
    job_id = f"job_{uuid4().hex[:10]}"
    return {
        "requestId": request_id,
        "jobId": job_id,
        "status": "SUBMITTED",
        "echo": req.model_dump(),
    }
