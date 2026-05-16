from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest
from ai_agent_domain import ArtifactStatus, ArtifactType, JobStatus, WorkflowStepType
from api_app.live_gate import (
    P21_LIVE_PLF_UNAVAILABLE,
    P21_LIVE_PORTAL_REQUIRED_ENV_MISSING,
)
from api_app.platform_db import (
    MssqlPlatformRepository,
    PlatformDbSettings,
    PlatformPersistenceError,
    build_platform_repository,
    content_type_for_artifact,
    load_platform_db_settings,
    options_storage_payload,
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


def test_p21_platform_db_missing_env_uses_live_prerequisite_blocker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("P21_LIVE_PORTAL_GATE", "1")
    for name in (
        "PLATFORM_DB_HOST",
        "PLATFORM_DB_USER",
        "PLATFORM_DB_PASSWORD",
        "PLATFORM_DB_NAME",
    ):
        monkeypatch.delenv(name, raising=False)

    with pytest.raises(PlatformPersistenceError) as exc_info:
        build_platform_repository()

    assert exc_info.value.code == P21_LIVE_PORTAL_REQUIRED_ENV_MISSING
    assert "password=" not in str(exc_info.value).lower()


def test_p21_platform_db_schema_or_seed_gap_uses_plf_blocker() -> None:
    settings = PlatformDbSettings(
        host="127.0.0.1",
        port=1433,
        user="sa",
        password="do-not-echo",
        database="PLF",
        requester_login="missing-user",
    )
    repository = MssqlPlatformRepository(settings)

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setenv("P21_LIVE_PORTAL_GATE", "1")
        monkeypatch.setattr(repository, "_try_resolve_user_id", lambda _login: None)
        with pytest.raises(PlatformPersistenceError) as exc_info:
            repository._resolve_user_id("missing-user")

    assert exc_info.value.code == P21_LIVE_PLF_UNAVAILABLE
    assert "do-not-echo" not in str(exc_info.value)


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


def test_platform_db_connect_uses_pytds_dsn_keyword(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = PlatformDbSettings(
        host="127.0.0.1",
        port=1433,
        user="sa",
        password="do-not-echo",
        database="PLF",
        requester_login="codex-api-local",
    )
    repository = MssqlPlatformRepository(settings)
    captured: dict[str, object] = {}
    fake_connection = object()

    def fake_connect(**kwargs: object) -> object:
        captured.update(kwargs)
        return fake_connection

    monkeypatch.setitem(sys.modules, "pytds", SimpleNamespace(connect=fake_connect))

    assert repository._connect() is fake_connection
    assert captured["dsn"] == "127.0.0.1"
    assert captured["port"] == 1433
    assert "server" not in captured
    assert captured["database"] == "PLF"


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


def test_platform_audit_event_persists_trace_id_without_schema_change(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    settings = PlatformDbSettings(
        host="127.0.0.1",
        port=1433,
        user="sa",
        password="do-not-echo",
        database="PLF",
        requester_login="codex-api-local",
    )
    repository = MssqlPlatformRepository(settings)
    executed: list[tuple[str, tuple[object, ...]]] = []

    monkeypatch.setattr(repository, "_try_resolve_user_id", lambda _actor: None)
    monkeypatch.setattr(
        repository,
        "_execute",
        lambda sql, params: executed.append((sql, params)),
    )

    event = repository.record_audit_event(
        action="ARTIFACT_VALIDATED",
        target_type="ARTIFACT",
        target_ref_id="art_p13_trace",
        payload={"validationReportId": "val_p13_trace"},
        correlation_id="corr-p13-trace",
    )

    assert event.correlation_id == "corr-p13-trace"
    assert event.payload["stage"] == "VALIDATION"
    assert event.payload["targetRef"] == {"type": "ARTIFACT", "id": "art_p13_trace"}
    assert event.payload["refs"]["validationReportId"] == "val_p13_trace"
    assert "TRC_ID" in executed[0][0]
    assert "corr-p13-trace" in executed[0][1]


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
        request_hash="hash-platform-contract",
        correlation_id="corr-platform-contract",
        idempotency_key="idem-platform-contract",
    )
    job = repository.create_job(
        request.request_id,
        correlation_id=request.correlation_id,
    )
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
        assumptions=("evidence caveat",),
        review_required=True,
    )
    validation = repository.save_validation_report(
        artifact_id=artifact.artifact_id,
        status="PASSED",
        checks=[{"ruleId": "test", "status": "PASSED"}],
        missing_evidence=[],
        manual_review_points=[],
    )
    assert repository.requests[request.request_id].status == JobStatus.COLLECTING_METADATA
    assert repository.jobs[job.job_id].status == JobStatus.COLLECTING_METADATA
    assert repository.artifacts[artifact.artifact_id].status == ArtifactStatus.VALIDATED
    assert repository.validation_reports[validation.validation_report_id].status == "PASSED"
    assert not any(event.action == "APPROVAL_DECISION_RECORDED" for event in repository.audit_events)
    assert repository.audit_events[0].correlation_id == "corr-platform-contract"


def test_workflow_repository_lists_artifacts_with_stable_internal_bound() -> None:
    repository = MemoryWorkflowRepository()
    request = repository.create_request(
        db_profile_id="plf",
        target={"type": "PROCEDURE", "schema": "dbo", "name": "usp_demo"},
        outputs=("SP_ANALYSIS_DOCUMENT",),
        options={},
        request_hash="hash-bounded-list",
        correlation_id="corr-bounded-list",
        idempotency_key=None,
    )
    job = repository.create_job(request.request_id, correlation_id=request.correlation_id)
    for index in range(105):
        repository.add_artifact(
            job_id=job.job_id,
            artifact_type=ArtifactType.SP_ANALYSIS_DOC,
            title=f"Analysis {index:03d}",
            content="# Analysis",
            evidence_refs=[{"type": "MSSQL_METADATA", "locator": "fixture"}],
            generator_version="test",
            registry_refs=("prompt@test",),
            assumptions=("evidence caveat",),
            review_required=True,
        )

    listed = repository.list_job_artifacts(job.job_id, limit=200)

    assert listed is not None
    assert len(listed) == 100
    assert listed == sorted(listed, key=lambda item: (item.created_at, item.artifact_id))


def test_options_storage_payload_keeps_tracking_out_of_public_options() -> None:
    repository = MemoryWorkflowRepository()
    request = repository.create_request(
        db_profile_id="ppm",
        target={"type": "PROCEDURE", "schema": "dbo", "name": "usp_demo"},
        outputs=("SP_ANALYSIS_DOCUMENT",),
        options={"includeEvidenceRefs": True},
        request_hash="hash-storage-payload",
        correlation_id="corr-storage-payload",
        idempotency_key="idem-storage-payload",
    )

    payload = options_storage_payload(request)

    assert request.options == {"includeEvidenceRefs": True}
    assert payload["includeEvidenceRefs"] is True
    assert payload["__tracking"]["dbProfileId"] == "ppm"
    assert payload["__tracking"]["requestHash"] == "hash-storage-payload"


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
