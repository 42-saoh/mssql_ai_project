from __future__ import annotations

import pytest
from ai_agent_domain import ArtifactStatus, ArtifactType, JobStatus, WorkflowStepType
from api_app.platform_db import (
    MssqlPlatformRepository,
    PlatformDbSettings,
    PlatformPersistenceError,
    build_platform_repository,
    content_type_for_artifact,
    load_platform_db_settings,
    storage_uuid,
)
from api_app.repositories import (
    ArtifactRecord,
)

from tests.unit.api.fake_repository import MemoryWorkflowRepository


def test_platform_db_repository_requires_configured_connection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "PLATFORM_DB_HOST",
        "PLATFORM_DB_USER",
        "PLATFORM_DB_PASSWORD",
        "PLATFORM_DB_NAME",
    ):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(PlatformPersistenceError, match="requires PLATFORM_DB_HOST"):
        build_platform_repository()


def test_platform_db_repository_builds_from_env_without_connecting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("PLATFORM_DB_HOST", "127.0.0.1")
    monkeypatch.setenv("PLATFORM_DB_PORT", "1433")
    monkeypatch.setenv("PLATFORM_DB_USER", "sa")
    monkeypatch.setenv("PLATFORM_DB_PASSWORD", "do-not-echo")
    monkeypatch.setenv("PLATFORM_DB_NAME", "PLF")

    settings = load_platform_db_settings()
    repository = build_platform_repository()

    assert settings.configured is True
    assert isinstance(repository, MssqlPlatformRepository)


def test_platform_db_safe_summary_never_contains_password() -> None:
    settings = PlatformDbSettings(
        host="127.0.0.1",
        port=1433,
        user="sa",
        password="do-not-echo",
        database="PLF",
        requester_login="codex-api-local",
    )

    summary = settings.safe_summary

    assert summary["passwordConfigured"] is True
    assert "do-not-echo" not in repr(summary)


def test_storage_id_and_artifact_content_type_mapping() -> None:
    markdown = _artifact(ArtifactType.SP_ANALYSIS_DOC)
    mapper = _artifact(ArtifactType.MAPPER_XML)
    service = _artifact(ArtifactType.SERVICE_DRAFT)

    assert storage_uuid("req_abc") == storage_uuid("req_abc")
    assert storage_uuid("req_abc") != storage_uuid("req_other")
    assert content_type_for_artifact(markdown) == "MARKDOWN"
    assert content_type_for_artifact(mapper) == "XML"
    assert content_type_for_artifact(service) == "JAVA"


def test_workflow_repository_contract_records_state_changes() -> None:
    repository = MemoryWorkflowRepository()

    request = repository.create_request(
        db_profile_id="plf",
        target={"type": "PROCEDURE", "schema": "dbo", "name": "usp_demo"},
        outputs=("SP_ANALYSIS_DOCUMENT",),
        options={"includeEvidenceRefs": True},
    )
    job = repository.create_job(request.request_id)
    repository.transition_job(
        job.job_id,
        status=JobStatus.COLLECTING_METADATA,
        current_step=WorkflowStepType.COLLECT_METADATA,
    )
    artifact = repository.add_artifact(
        job_id=job.job_id,
        artifact_type=ArtifactType.SP_ANALYSIS_DOC,
        title="Analysis",
        content="# Analysis",
        evidence_refs=[{"type": "MCP_TOOL", "locator": "fixture"}],
        generator_version="test",
        registry_refs=("prompt@test",),
        assumptions=("review required",),
        review_required=True,
    )
    validation = repository.save_validation_report(
        artifact_id=artifact.artifact_id,
        status="PASSED",
        checks=[{"ruleId": "test", "status": "PASSED"}],
        missing_evidence=[],
        manual_review_points=[],
    )
    approval = repository.add_approval(
        artifact_id=artifact.artifact_id,
        decision="APPROVE",
        reviewer="reviewer@example.com",
        comment="ok",
        validation_report_id=validation.validation_report_id,
    )

    assert repository.requests[request.request_id].status == JobStatus.COLLECTING_METADATA
    assert repository.jobs[job.job_id].status == JobStatus.COLLECTING_METADATA
    assert repository.artifacts[artifact.artifact_id].status == ArtifactStatus.APPROVED
    assert repository.validation_reports[validation.validation_report_id].status == "PASSED"
    assert repository.approvals[approval.approval_id].storage_decision == "APPROVED"


def _artifact(artifact_type: ArtifactType) -> ArtifactRecord:
    return ArtifactRecord(
        artifact_id=f"art_{artifact_type.value}",
        job_id="job_1",
        type=artifact_type,
        status=ArtifactStatus.DRAFT,
        title=artifact_type.value,
        content="content",
        evidence_refs=[],
        generator_version="test",
        registry_refs=(),
        assumptions=(),
    )
