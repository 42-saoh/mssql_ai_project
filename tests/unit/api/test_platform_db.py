from __future__ import annotations

from datetime import UTC, datetime, timedelta
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
    job_from_row,
    load_platform_db_settings,
    metadata_analysis_run_from_row,
    options_storage_payload,
    storage_uuid,
)
from api_app.repositories import (
    ArtifactRecord,
    MetadataAnalysisRunPersistenceError,
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


def test_platform_db_job_row_includes_request_context() -> None:
    row = (
        "job-storage-id",
        "job_public",
        "req_public",
        "VALIDATION_COMPLETE",
        "VALIDATE",
        None,
        None,
        "2026-05-16T00:00:00Z",
        "2026-05-16T00:01:00Z",
        '{"correlationId": "corr-job-context"}',
        "ppm",
        '{"type": "PROCEDURE", "schema": "dbo", "name": "GetInspItemsCd"}',
        '["SP_ANALYSIS_DOCUMENT", "DEPENDENCY_REPORT"]',
        "mssql:ppm:-:procedure:dbo.getinspitemscd",
    )

    job = job_from_row(row)

    assert job.job_id == "job_public"
    assert job.db_profile_id == "ppm"
    assert job.target == {
        "type": "PROCEDURE",
        "schema": "dbo",
        "name": "GetInspItemsCd",
    }
    assert job.outputs == ("SP_ANALYSIS_DOCUMENT", "DEPENDENCY_REPORT")
    assert job.target_key == "mssql:ppm:-:procedure:dbo.getinspitemscd"


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
    target_key = "mssql:plf:-:procedure:dbo.usp_demo"
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
    assert request.target_key == target_key
    assert job.target_key == target_key
    assert artifact.target_key == target_key
    assert repository.list_jobs(target_key=target_key)[0].job_id == job.job_id
    assert repository.list_jobs(target_key="mssql:plf:-:procedure:dbo.other") == []
    assert repository.artifacts[artifact.artifact_id].status == ArtifactStatus.VALIDATED
    assert repository.validation_reports[validation.validation_report_id].status == "PASSED"
    assert not any(event.action == "APPROVAL_DECISION_RECORDED" for event in repository.audit_events)
    assert repository.audit_events[0].correlation_id == "corr-platform-contract"


def test_workflow_repository_contract_claims_stale_job_and_finds_artifact_by_type() -> None:
    repository = MemoryWorkflowRepository()
    request = repository.create_request(
        db_profile_id="plf",
        target={"type": "PROCEDURE", "schema": "dbo", "name": "usp_demo"},
        outputs=("SP_ANALYSIS_DOCUMENT",),
        options={"includeEvidenceRefs": True},
        request_hash="hash-recovery-contract",
        correlation_id="corr-recovery-contract",
        idempotency_key="idem-recovery-contract",
    )
    job = repository.create_job(request.request_id, correlation_id=request.correlation_id)
    repository.transition_job(
        job.job_id,
        status=JobStatus.COLLECTING_METADATA,
        current_step=WorkflowStepType.COLLECT_METADATA,
    )
    repository.jobs[job.job_id].updated_at = datetime.now(UTC) - timedelta(seconds=120)
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

    restored_request = repository.get_request(request.request_id)
    claimed = repository.claim_stale_active_job(
        job.job_id,
        stale_before=datetime.now(UTC) - timedelta(seconds=60),
    )
    second_claim = repository.claim_stale_active_job(
        job.job_id,
        stale_before=datetime.now(UTC) - timedelta(seconds=60),
    )
    found_artifact = repository.find_job_artifact_by_type(
        job.job_id,
        ArtifactType.SP_ANALYSIS_DOC,
    )

    assert restored_request is not None
    assert restored_request.request_id == request.request_id
    assert restored_request.status == JobStatus.COLLECTING_METADATA
    assert restored_request.target == request.target
    assert restored_request.target_key == "mssql:plf:-:procedure:dbo.usp_demo"
    assert claimed is not None
    assert claimed.job_id == job.job_id
    assert second_claim is None
    assert found_artifact is not None
    assert found_artifact.artifact_id == artifact.artifact_id


def test_workflow_repository_contract_claims_submitted_job_once() -> None:
    repository = MemoryWorkflowRepository()
    request = repository.create_request(
        db_profile_id="plf",
        target={"type": "PROCEDURE", "schema": "dbo", "name": "usp_demo"},
        outputs=("SP_ANALYSIS_DOCUMENT",),
        options={"includeEvidenceRefs": True},
        request_hash="hash-submitted-claim",
        correlation_id="corr-submitted-claim",
        idempotency_key=None,
    )
    job = repository.create_job(request.request_id, correlation_id=request.correlation_id)

    claimed = repository.claim_submitted_job(job.job_id)
    second_claim = repository.claim_submitted_job(job.job_id)

    assert claimed is not None
    assert claimed.status == JobStatus.COLLECTING_METADATA
    assert claimed.current_step == WorkflowStepType.COLLECT_METADATA
    assert second_claim is None
    assert repository.requests[request.request_id].status == JobStatus.COLLECTING_METADATA


def test_workflow_repository_contract_persists_metadata_analysis_runs() -> None:
    repository = MemoryWorkflowRepository()

    created = repository.create_metadata_analysis_run(
        run_id="metadata_run_contract",
        request={
            "dbProfileId": "master",
            "target": {"schema": "dbo", "name": "TB_ORDER", "type": "TABLE"},
            "options": {"useLlmAnalysis": False},
        },
    )
    repository.mark_metadata_analysis_run_running(created.run_id)
    repository.mark_metadata_analysis_run_succeeded(
        created.run_id,
        analysis={
            "dbProfileId": "master",
            "mode": "TARGET",
            "target": {"schema": "dbo", "name": "TB_ORDER", "type": "TABLE"},
            "sourceProfile": "master",
            "sourceDatabase": "master",
            "summary": "Sanitized metadata profile.",
        },
    )

    record = repository.get_metadata_analysis_run(created.run_id)

    assert record is not None
    assert record.status == "SUCCEEDED"
    assert record.request["target"]["name"] == "TB_ORDER"
    assert record.analysis
    assert record.analysis["mode"] == "TARGET"
    assert record.error is None


def test_workflow_repository_claims_metadata_analysis_runs_once() -> None:
    repository = MemoryWorkflowRepository()
    stale_before = datetime.now(UTC) - timedelta(seconds=60)

    created = repository.create_metadata_analysis_run(
        run_id="metadata_run_claim",
        request={"dbProfileId": "master", "query": "order"},
    )

    assert repository.list_recoverable_metadata_analysis_runs(
        stale_before=stale_before,
        limit=5,
    )[0].run_id == created.run_id
    claimed = repository.claim_metadata_analysis_run(
        created.run_id,
        stale_before=stale_before,
    )

    assert claimed is not None
    assert claimed.status == "RUNNING"
    assert repository.claim_metadata_analysis_run(
        created.run_id,
        stale_before=stale_before,
    ) is None

    repository.mark_metadata_analysis_run_succeeded(
        created.run_id,
        analysis={"mode": "QUERY"},
    )
    assert repository.list_recoverable_metadata_analysis_runs(
        stale_before=datetime.now(UTC),
        limit=5,
    ) == []

    stale = repository.create_metadata_analysis_run(
        run_id="metadata_run_stale_running",
        request={"dbProfileId": "master", "query": "customer"},
    )
    repository.mark_metadata_analysis_run_running(stale.run_id)
    repository.metadata_analysis_runs[stale.run_id].started_at = (
        datetime.now(UTC) - timedelta(seconds=120)
    )

    reclaimed = repository.claim_metadata_analysis_run(
        stale.run_id,
        stale_before=datetime.now(UTC) - timedelta(seconds=60),
    )

    assert reclaimed is not None
    assert reclaimed.status == "RUNNING"
    assert reclaimed.completed_at is None
    assert reclaimed.error is None


def test_platform_db_metadata_analysis_run_row_mapping() -> None:
    row = (
        "metadata_run_row",
        "FAILED",
        '{"dbProfileId": "master", "query": "order"}',
        None,
        '{"code": "KNOWLEDGE_SCHEMA_REQUIRED", "message": "schema missing", "statusCode": 503}',
        "2026-05-16T00:00:00Z",
        "2026-05-16T00:00:01Z",
        "2026-05-16T00:00:02Z",
    )

    record = metadata_analysis_run_from_row(row)

    assert record.run_id == "metadata_run_row"
    assert record.status == "FAILED"
    assert record.request["query"] == "order"
    assert record.analysis is None
    assert record.error
    assert record.error["code"] == "KNOWLEDGE_SCHEMA_REQUIRED"


def test_platform_db_metadata_analysis_run_claim_is_atomic(
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
    captured: dict[str, object] = {}

    def fake_query_one(sql: str, params: tuple[object, ...]) -> None:
        captured["sql"] = sql
        captured["params"] = params
        return None

    monkeypatch.setattr(repository, "_require_metadata_analysis_run_schema", lambda: None)
    monkeypatch.setattr(repository, "_query_one", fake_query_one)

    result = repository.claim_metadata_analysis_run(
        "metadata_run_claim_sql",
        stale_before=datetime(2026, 5, 16, tzinfo=UTC),
    )

    sql = str(captured["sql"])
    params = captured["params"]
    assert result is None
    assert "UPDATE dbo.METADATA_ANALYSIS_RUNS" in sql
    assert "OUTPUT" in sql
    assert "STAT_CD = 'QUEUED'" in sql
    assert "STAT_CD = 'RUNNING'" in sql
    assert "COALESCE(START_DTM, SUBMITTED_DTM) <= %s" in sql
    assert params[2] == "metadata_run_claim_sql"


def test_platform_db_sp_recovery_contract_uses_conditional_claim_and_artifact_lookup(
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
    captured: list[tuple[str, tuple[object, ...]]] = []

    def fake_query_one(sql: str, params: tuple[object, ...]) -> None:
        captured.append((sql, params))
        return None

    monkeypatch.setattr(repository, "_query_one", fake_query_one)

    assert repository.get_request("req_recover") is None
    assert repository.claim_stale_active_job(
        "job_recover",
        stale_before=datetime(2026, 5, 16, tzinfo=UTC),
    ) is None
    assert repository.find_job_artifact_by_type(
        "job_recover",
        ArtifactType.SP_ANALYSIS_DOC,
    ) is None

    request_sql, request_params = captured[0]
    claim_sql, claim_params = captured[1]
    artifact_sql, artifact_params = captured[2]
    assert "FROM dbo.CORE_WORK_REQUESTS" in request_sql
    assert request_params == (storage_uuid("req_recover"), "req_recover")
    assert "UPDATE dbo.CORE_JOBS" in claim_sql
    assert "CUR_STAT_CD IN" in claim_sql
    assert "UPD_DTM <= %s" in claim_sql
    assert claim_params[1] == "job_recover"
    assert "ARTF_TP_CD = %s" in artifact_sql
    assert artifact_params == (storage_uuid("job_recover"), ArtifactType.SP_ANALYSIS_DOC.value)


def test_platform_db_submitted_job_claim_is_conditional(
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
    captured: dict[str, object] = {}

    def fake_query_one(sql: str, params: tuple[object, ...]) -> None:
        captured["sql"] = sql
        captured["params"] = params
        return None

    monkeypatch.setattr(repository, "_query_one", fake_query_one)

    assert repository.claim_submitted_job("job_submitted") is None

    claim_sql = str(captured["sql"])
    claim_params = captured["params"]
    assert "UPDATE dbo.CORE_JOBS" in claim_sql
    assert "CUR_STAT_CD = 'SUBMITTED'" in claim_sql
    assert "CUR_STAT_CD = 'COLLECTING_METADATA'" in claim_sql
    assert "CUR_STEP_TP_CD = 'COLLECT_METADATA'" in claim_sql
    assert claim_params[0] == "job_submitted"
    assert claim_params[2] == "job_submitted"


def test_platform_db_metadata_analysis_run_schema_gap_is_explicit() -> None:
    settings = PlatformDbSettings(
        host="127.0.0.1",
        port=1433,
        user="sa",
        password="do-not-echo",
        database="PLF",
        requester_login="codex-api-local",
    )
    repository = MssqlPlatformRepository(settings)

    with pytest.MonkeyPatch.context() as monkeypatch:
        monkeypatch.setattr(repository, "_query_all", lambda _sql, _params: [])
        with pytest.raises(MetadataAnalysisRunPersistenceError) as exc_info:
            repository.create_metadata_analysis_run(
                run_id="metadata_run_missing_schema",
                request={"dbProfileId": "master", "query": "order"},
            )

    assert exc_info.value.code == "METADATA_ANALYSIS_RUN_SCHEMA_REQUIRED"
    assert "METADATA_ANALYSIS_RUNS" in str(exc_info.value)
    assert "do-not-echo" not in str(exc_info.value)


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
    assert payload["__tracking"]["targetKey"] == "mssql:ppm:-:procedure:dbo.usp_demo"
    assert payload["__tracking"]["requestHash"] == "hash-storage-payload"


def test_platform_db_list_jobs_supports_exact_target_key_filter(
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
    captured: dict[str, object] = {}

    def fake_query_all(sql: str, params: tuple[object, ...]) -> list[tuple[object, ...]]:
        captured["sql"] = sql
        captured["params"] = params
        return []

    monkeypatch.setattr(repository, "_query_all", fake_query_all)

    assert repository.list_jobs(
        limit=25,
        target_key="mssql:ppm:-:procedure:dbo.getinspitemscd",
    ) == []

    sql = str(captured["sql"])
    assert "CANON_TRGT_KEY_TXT" in sql
    assert "JSON_VALUE(r.OPTN_PAYLD_JSON, '$.__tracking.targetKey')" in sql
    assert "WHERE COALESCE" in sql
    assert captured["params"] == ("mssql:ppm:-:procedure:dbo.getinspitemscd",)


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
