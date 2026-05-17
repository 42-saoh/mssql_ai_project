from __future__ import annotations

import pytest
from ai_agent_domain import ArtifactStatus, JobStatus, WorkflowStepType
from api_app.contracts import (
    registry_storage_type,
    validation_storage_result,
)
from api_app.lifecycle import artifact_status_after_validation
from api_app.presenters import present_job
from api_app.repositories import JobRecord


def test_validation_status_mapping_to_storage_result() -> None:
    assert validation_storage_result("PASSED") == "PASS"
    assert validation_storage_result("FAILED") == "FAIL"
    assert validation_storage_result("REVIEW_REQUIRED") == "FAIL"
    assert (
        artifact_status_after_validation("REVIEW_REQUIRED", ArtifactStatus.DRAFT)
        == ArtifactStatus.DRAFT
    )


def test_registry_type_mapping_to_storage_contract() -> None:
    assert registry_storage_type("PROMPT") == "PROMPT"
    assert registry_storage_type("TEMPLATE") == "TEMPLATE"
    assert registry_storage_type("POLICY") == "MODEL_POLICY"
    assert registry_storage_type("DB_PROFILE") == "DB_PROFILE_POLICY"
    assert registry_storage_type("GENERATOR") == "MODEL_POLICY"


def test_unknown_mapping_value_is_explicit_error() -> None:
    with pytest.raises(ValueError):
        validation_storage_result("PASS")
    with pytest.raises(ValueError):
        registry_storage_type("MODEL_POLICY")


def test_job_presenter_omits_malformed_optional_history_context() -> None:
    job = JobRecord(
        job_id="job_bad_context",
        request_id="req_bad_context",
        status=JobStatus.VALIDATION_COMPLETE,
        db_profile_id="ppm",
        target={"schema": "dbo", "name": ""},
        outputs=("SP_ANALYSIS_DOCUMENT", "LEGACY_OUTPUT"),
    )

    response = present_job(job).to_response()

    assert response["dbProfileId"] == "ppm"
    assert "target" not in response
    assert response["outputs"] == ["SP_ANALYSIS_DOCUMENT"]
    assert response["progress"] == 1.0


@pytest.mark.parametrize(
    ("status", "current_step", "expected_progress"),
    [
        (JobStatus.SUBMITTED, None, 0.05),
        (JobStatus.COLLECTING_METADATA, WorkflowStepType.COLLECT_METADATA, 0.20),
        (JobStatus.ANALYZING, WorkflowStepType.ANALYZE, 0.45),
        (JobStatus.GENERATING, WorkflowStepType.GENERATE, 0.72),
        (JobStatus.VALIDATING, WorkflowStepType.VALIDATE, 0.90),
        (JobStatus.VALIDATION_COMPLETE, WorkflowStepType.VALIDATE, 1.0),
        (JobStatus.FAILED, WorkflowStepType.GENERATE, 0.72),
        (JobStatus.CANCELED, None, 1.0),
    ],
)
def test_job_presenter_progress_is_status_based_estimate(
    status: JobStatus,
    current_step: WorkflowStepType | None,
    expected_progress: float,
) -> None:
    response = present_job(
        JobRecord(
            job_id=f"job_{status.value.lower()}",
            request_id="req_progress",
            status=status,
            current_step=current_step,
        )
    ).to_response()

    assert response["progress"] == expected_progress
