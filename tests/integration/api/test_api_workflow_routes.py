from __future__ import annotations

from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from ai_agent_domain import ArtifactType, JobStatus, WorkflowStepType
from ai_agent_runtime.gateway import model_profile_from_env
from api_app.dependencies import (
    get_metadata_analysis_service,
    get_repository,
    get_workflow_service,
    reset_application_state,
)
from api_app.main import app
from api_app.metadata_analysis_runs import execute_metadata_analysis_run
from api_app.metadata_analysis_service import MetadataAnalysisService
from api_app.recovery_worker import run_recovery_once
from api_app.repositories import KnowledgePersistenceError, ValidationReportRecord
from api_app.workflow import SP_WORKFLOW_RECOVERY_BLOCKED, WorkflowService
from fastapi.testclient import TestClient

from tests.unit.api.fake_repository import MemoryWorkflowRepository


class CountingValidationRepository(MemoryWorkflowRepository):
    def __init__(self) -> None:
        super().__init__()
        self.validation_write_count = 0

    def save_validation_report(self, **kwargs: Any) -> ValidationReportRecord:
        self.validation_write_count += 1
        return super().save_validation_report(**kwargs)


class KnowledgeSchemaRequiredRepository(MemoryWorkflowRepository):
    def upsert_knowledge_asset(self, **_kwargs: Any):
        raise KnowledgePersistenceError(
            "Knowledge assetization requires v5 platform schema tables.",
            code="KNOWLEDGE_SCHEMA_REQUIRED",
            status_code=503,
        )

    def list_knowledge_assets(self, **_kwargs: Any):
        raise KnowledgePersistenceError(
            "Knowledge assetization requires v5 platform schema objects.",
            code="KNOWLEDGE_SCHEMA_REQUIRED",
            status_code=503,
        )

    def search_knowledge_facts(self, **_kwargs: Any):
        raise KnowledgePersistenceError(
            "Knowledge assetization requires v5 platform schema objects.",
            code="KNOWLEDGE_SCHEMA_REQUIRED",
            status_code=503,
        )


class ExplodingMetadataAnalysisService(MetadataAnalysisService):
    def __init__(self) -> None:
        super().__init__()
        self.analyze_calls = 0

    def analyze(self, request):  # type: ignore[override]
        self.analyze_calls += 1
        raise AssertionError("analyze should not run without a metadata run claim")


@pytest.fixture
def client_and_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[tuple[TestClient, MemoryWorkflowRepository]]:
    monkeypatch.setenv("P21_LIVE_PORTAL_GATE", "0")
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")
    monkeypatch.setenv("LLM_ENABLE_REMOTE", "0")
    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)
    app.dependency_overrides[get_repository] = lambda: repository
    app.dependency_overrides[get_workflow_service] = lambda: service
    try:
        yield TestClient(app), repository
    finally:
        app.dependency_overrides.clear()
        reset_application_state()


@pytest.fixture
def client(
    client_and_repository: tuple[TestClient, MemoryWorkflowRepository],
) -> TestClient:
    return client_and_repository[0]


def _sp_analysis_payload(outputs: list[str] | None = None) -> dict:
    return {
        "dbProfileId": "master",
        "target": {
            "type": "PROCEDURE",
            "schema": "dbo",
            "name": "usp_OrderRequest_Select",
        },
        "outputs": outputs or ["SP_ANALYSIS_DOCUMENT"],
        "options": {"includeEvidenceRefs": True},
    }


def _normalized_response_keys(value: Any) -> set[str]:
    keys: set[str] = set()
    if isinstance(value, dict):
        for key, nested in value.items():
            keys.add(str(key).replace("_", "").lower())
            keys.update(_normalized_response_keys(nested))
    elif isinstance(value, list):
        for item in value:
            keys.update(_normalized_response_keys(item))
    return keys


def _sp_analysis_llm_payload(outputs: list[str] | None = None) -> dict:
    payload = _sp_analysis_payload(outputs or ["SP_ANALYSIS_DOCUMENT", "DEPENDENCY_REPORT"])
    payload["target"] = {
        "type": "PROCEDURE",
        "schema": "dbo",
        "name": "usp_GetOrderSummary",
    }
    payload["options"] = {
        "includeEvidenceRefs": True,
        "useLlmAnalysis": True,
        "llmProfileId": "openai_fast_test",
        "allowSpDefinitionToModel": True,
    }
    return payload


def test_sp_analysis_request_to_validation_complete_flow(client: TestClient) -> None:
    headers = {"X-Correlation-ID": "corr-route-flow"}
    submit = client.post(
        "/api/v1/requests/sp-analysis",
        headers=headers,
        json={
            "dbProfileId": "master",
            "target": {
                "type": "PROCEDURE",
                "schema": "dbo",
                "name": "usp_OrderRequest_Select",
            },
            "outputs": [
                "SP_ANALYSIS_DOCUMENT",
                "DEPENDENCY_REPORT",
                "JAVA_MYBATIS_DRAFT",
            ],
            "options": {"includeEvidenceRefs": True},
        },
    )

    assert submit.status_code == 202
    assert submit.headers["X-Correlation-ID"] == "corr-route-flow"
    submitted = submit.json()
    assert submitted["requestId"].startswith("req_")
    assert submitted["jobId"].startswith("job_")

    assert submitted["status"] == "VALIDATION_COMPLETE"

    knowledge = client.get(f"/api/v1/jobs/{submitted['jobId']}/knowledge-assets")
    assert knowledge.status_code == 200
    knowledge_payload = knowledge.json()
    assert {asset["assetKind"] for asset in knowledge_payload["knowledgeAssets"]} == {
        "SP_ANALYSIS",
        "DEPENDENCY_EVIDENCE",
        "METADATA_PROFILE",
        "DTO_READINESS",
        "CANONICAL_ANALYSIS",
    }
    sp_knowledge = next(
        asset
        for asset in knowledge_payload["knowledgeAssets"]
        if asset["assetKind"] == "SP_ANALYSIS"
    )
    assert sp_knowledge["lifecycleStatus"] == "DRAFT"

    asset_search = client.get(
        "/api/v1/knowledge/assets",
        params={"assetKind": "SP_ANALYSIS", "targetName": "usp_OrderRequest_Select"},
    )
    empty_fact_search = client.get("/api/v1/knowledge/facts/search")
    fact_search = client.get(
        "/api/v1/knowledge/facts/search",
        params={"objectRef": "usp_OrderRequest_Select"},
    )
    review = client.post(
        (
            "/api/v1/knowledge/assets/"
            f"{sp_knowledge['assetId']}/versions/{sp_knowledge['currentVersionId']}/review"
        ),
        json={"status": "REVIEW_REQUIRED"},
    )
    reviews = client.get(
        f"/api/v1/knowledge/assets/{sp_knowledge['assetId']}/reviews",
        params={"versionId": sp_knowledge["currentVersionId"]},
    )

    assert asset_search.status_code == 200
    assert sp_knowledge["assetId"] in {
        asset["assetId"] for asset in asset_search.json()["assets"]
    }
    assert empty_fact_search.status_code == 422
    assert empty_fact_search.json()["code"] == "KNOWLEDGE_SEARCH_FILTER_REQUIRED"
    assert fact_search.status_code == 200
    assert fact_search.json()["facts"]
    assert review.status_code == 404
    assert reviews.status_code == 404

    job = client.get(f"/api/v1/jobs/{submitted['jobId']}")
    assert job.status_code == 200
    assert job.headers["X-Correlation-ID"].startswith("corr_")
    assert job.json()["currentStep"] == "VALIDATE"
    assert job.json()["dbProfileId"] == "master"
    assert job.json()["target"] == {
        "type": "PROCEDURE",
        "schema": "dbo",
        "name": "usp_OrderRequest_Select",
    }
    assert "SP_ANALYSIS_DOCUMENT" in job.json()["outputs"]

    recent_jobs = client.get("/api/v1/jobs", params={"limit": 10})
    assert recent_jobs.status_code == 200
    assert submitted["jobId"] in {item["jobId"] for item in recent_jobs.json()["jobs"]}
    recent_job = next(
        item for item in recent_jobs.json()["jobs"] if item["jobId"] == submitted["jobId"]
    )
    assert recent_job["target"]["name"] == "usp_OrderRequest_Select"
    assert recent_job["dbProfileId"] == "master"

    listed = client.get(f"/api/v1/jobs/{submitted['jobId']}/artifacts")
    assert listed.status_code == 200
    artifacts = listed.json()["artifacts"]
    artifact_types = {artifact["type"] for artifact in artifacts}
    assert "SP_ANALYSIS_DOC" in artifact_types
    assert "DEPENDENCY_REPORT" in artifact_types
    assert "DTO_DRAFT" in artifact_types
    assert "JAVA_MYBATIS_DRAFT" not in artifact_types
    assert all(artifact["status"] != "PUBLISHED" for artifact in artifacts)

    artifact_id = artifacts[0]["artifactId"]
    preview = client.get(f"/api/v1/artifacts/{artifact_id}", headers=headers)
    assert preview.status_code == 200
    assert preview.headers["X-Correlation-ID"] == "corr-route-flow"
    assert preview.json()["reviewRequired"] is True
    assert "generatorVersion" in preview.json()

    validation = client.post(f"/api/v1/artifacts/{artifact_id}/validation", headers=headers)
    assert validation.status_code == 200
    assert validation.headers["X-Correlation-ID"] == "corr-route-flow"
    assert validation.json()["artifactId"] == artifact_id
    assert validation.json()["status"] in {"PASSED", "REVIEW_REQUIRED"}
    assert validation.json()["validationReportId"].startswith("val_")

    latest_validation = client.get(
        f"/api/v1/artifacts/{artifact_id}/validation/latest",
        headers=headers,
    )
    assert latest_validation.status_code == 200
    assert latest_validation.headers["X-Correlation-ID"] == "corr-route-flow"
    assert latest_validation.json()["artifactId"] == artifact_id
    assert latest_validation.json()["validationReportId"] == validation.json()["validationReportId"]


def test_sp_analysis_request_can_return_before_background_workflow_completes(
    client: TestClient,
) -> None:
    submit = client.post(
        "/api/v1/requests/sp-analysis",
        params={"runAsync": "true"},
        json=_sp_analysis_payload(["SP_ANALYSIS_DOCUMENT"]),
    )

    assert submit.status_code == 202
    submitted = submit.json()
    assert submitted["status"] == "SUBMITTED"
    assert submitted["requestId"].startswith("req_")
    assert submitted["jobId"].startswith("job_")

    job = client.get(f"/api/v1/jobs/{submitted['jobId']}")

    assert job.status_code == 200
    assert job.json()["status"] == "VALIDATION_COMPLETE"
    assert job.json()["progress"] == 1.0
    assert job.json()["currentStep"] == "VALIDATE"


def test_sp_analysis_batch_route_returns_accepted_and_duplicate_rejections(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/requests/sp-analysis/batch",
        json={
            "dbProfileId": "master",
            "targets": [
                {"type": "PROCEDURE", "schema": "dbo", "name": "usp_GetOrderSummary"},
                {"type": "PROCEDURE", "schema": "dbo", "name": "usp_GetOrderSummary"},
            ],
            "outputs": ["SP_ANALYSIS_DOCUMENT"],
            "options": {"includeEvidenceRefs": True, "useLlmAnalysis": False},
        },
    )

    assert response.status_code == 202
    payload = response.json()
    assert payload["batchId"].startswith("batch_")
    assert payload["status"] == "PARTIAL"
    assert len(payload["accepted"]) == 1
    assert payload["accepted"][0]["jobId"].startswith("job_")
    assert payload["rejected"][0]["code"] == "DUPLICATE_TARGET_SKIPPED"


def test_workflow_binds_dependency_closure_evidence_to_metadata_and_artifacts(
    client_and_repository: tuple[TestClient, MemoryWorkflowRepository],
) -> None:
    client, repository = client_and_repository

    submit = client.post(
        "/api/v1/requests/sp-analysis",
        json={
            "dbProfileId": "master",
            "target": {
                "type": "PROCEDURE",
                "schema": "dbo",
                "name": "usp_ProcessOrderBatch",
            },
            "outputs": ["DEPENDENCY_REPORT"],
            "options": {"includeEvidenceRefs": True},
        },
    )

    assert submit.status_code == 202
    assert submit.json()["status"] == "VALIDATION_COMPLETE"
    metadata = next(iter(repository.metadata_collections.values()))
    dependency_evidence = metadata.payload["dependencyEvidence"]
    assert dependency_evidence["toolName"] == "get_dependency_closure"
    assert dependency_evidence["summary"]["reviewRequiredCount"] >= 1
    assert dependency_evidence["unresolved"]
    assert all(edge["resolutionStatus"] == "CONFIRMED" for edge in dependency_evidence["edges"])
    assert "resolve_dependency_reference" not in str(metadata.payload)

    artifact = next(iter(repository.artifacts.values()))
    assert artifact.type == ArtifactType.DEPENDENCY_REPORT
    assert "dependency_closure_evidence" in artifact.content
    assert "raw_definition" not in artifact.content.lower()
    assert "row_data" not in artifact.content.lower()
    assert "select *" not in artifact.content.lower()
    assert "ddl/dml" not in artifact.content.lower()
    assert any("dependencies" in ref["locator"] for ref in artifact.evidence_refs)


def test_workflow_blocks_ppm_template_only_without_plf_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("P21_LIVE_PORTAL_GATE", "0")
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")
    monkeypatch.setenv("LLM_ENABLE_REMOTE", "0")
    monkeypatch.setattr(
        "api_app.metadata_service.ppm_manifest_selection_mode",
        lambda: "template_only",
    )
    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)
    app.dependency_overrides[get_repository] = lambda: repository
    app.dependency_overrides[get_workflow_service] = lambda: service
    try:
        client = TestClient(app)
        submit = client.post(
            "/api/v1/requests/sp-analysis",
            json={
                "dbProfileId": "ppm",
                "target": {
                    "type": "PROCEDURE",
                    "schema": "dbo",
                    "name": "usp_GetOrderSummary",
                },
                "outputs": ["DEPENDENCY_REPORT"],
                "options": {"includeEvidenceRefs": True},
            },
        )
        job_id = submit.json()["jobId"]
        job = client.get(f"/api/v1/jobs/{job_id}")
    finally:
        app.dependency_overrides.clear()
        reset_application_state()

    assert submit.status_code == 202
    assert submit.json()["status"] == "FAILED"
    assert job.status_code == 200
    assert job.json()["status"] == "FAILED"
    assert job.json()["failureReason"]
    assert "PPM pilot manifest is template_only" in job.json()["failureReason"]
    assert "PLF" not in submit.text
    assert "PLF" not in job.text


def test_jobs_route_lists_recent_jobs_with_bounded_response_shape(
    client_and_repository: tuple[TestClient, MemoryWorkflowRepository],
) -> None:
    client, repository = client_and_repository
    created_job_ids: list[str] = []
    for index in range(3):
        request = repository.create_request(
            db_profile_id="master",
            target={"type": "PROCEDURE", "schema": "dbo", "name": f"usp_demo_{index}"},
            outputs=("SP_ANALYSIS_DOCUMENT",),
            options={"includeEvidenceRefs": True},
            request_hash=f"hash-jobs-{index}",
            correlation_id=f"corr-jobs-{index}",
            idempotency_key=None,
        )
        job = repository.create_job(request.request_id, correlation_id=request.correlation_id)
        repository.jobs[job.job_id].created_at = job.created_at + timedelta(
            milliseconds=index,
        )
        created_job_ids.append(job.job_id)

    response = client.get("/api/v1/jobs", params={"limit": 2})

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {"jobs"}
    assert [item["jobId"] for item in payload["jobs"]] == list(reversed(created_job_ids[-2:]))
    assert all(item["dbProfileId"] == "master" for item in payload["jobs"])
    assert all(item["target"]["schema"] == "dbo" for item in payload["jobs"])
    assert all(item["outputs"] == ["SP_ANALYSIS_DOCUMENT"] for item in payload["jobs"])


def test_latest_validation_route_does_not_create_validation_write(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("P21_LIVE_PORTAL_GATE", "0")
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")
    monkeypatch.setenv("LLM_ENABLE_REMOTE", "0")
    repository = CountingValidationRepository()
    service = WorkflowService(repository)
    app.dependency_overrides[get_repository] = lambda: repository
    app.dependency_overrides[get_workflow_service] = lambda: service
    try:
        client = TestClient(app)
        submit = client.post("/api/v1/requests/sp-analysis", json=_sp_analysis_payload())
        assert submit.status_code == 202
        artifact_id = client.get(
            f"/api/v1/jobs/{submit.json()['jobId']}/artifacts"
        ).json()["artifacts"][0]["artifactId"]
        before = repository.validation_write_count

        response = client.get(f"/api/v1/artifacts/{artifact_id}/validation/latest")

        assert response.status_code == 200
        assert repository.validation_write_count == before
    finally:
        app.dependency_overrides.clear()
        reset_application_state()


def test_sp_analysis_submit_idempotency_replays_or_conflicts(client: TestClient) -> None:
    payload = _sp_analysis_payload()
    headers = {
        "Idempotency-Key": "idem-route-p09",
        "X-Correlation-ID": "corr-idempotent-submit",
    }

    first = client.post("/api/v1/requests/sp-analysis", headers=headers, json=payload)
    replay = client.post("/api/v1/requests/sp-analysis", headers=headers, json=payload)

    assert first.status_code == 202
    assert replay.status_code == 202
    assert replay.json()["requestId"] == first.json()["requestId"]
    assert replay.json()["jobId"] == first.json()["jobId"]
    assert replay.headers["X-Correlation-ID"] == "corr-idempotent-submit"

    conflict_payload = {**payload, "outputs": ["DEPENDENCY_REPORT"]}
    conflict = client.post(
        "/api/v1/requests/sp-analysis",
        headers=headers,
        json=conflict_payload,
    )

    assert conflict.status_code == 409
    assert set(conflict.json()) == {"detail", "code"}
    assert conflict.json()["code"] == "IDEMPOTENCY_CONFLICT"


def test_routes_generate_correlation_id_when_header_is_missing(client: TestClient) -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["X-Correlation-ID"].startswith("corr_")


def test_invalid_request_returns_validation_error_shape(client: TestClient) -> None:
    response = client.post(
        "/api/v1/requests/sp-analysis",
        json={"dbProfileId": "master", "outputs": ["SP_ANALYSIS_DOCUMENT"]},
    )

    assert response.status_code == 422
    assert response.headers["X-Correlation-ID"].startswith("corr_")
    assert response.json() == {
        "detail": "Request validation failed.",
        "code": "VALIDATION_ERROR",
    }


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("name", ""),
        ("name", "   "),
        ("schema", ""),
    ],
)
def test_blank_sp_analysis_target_fields_return_validation_error_without_job(
    client_and_repository: tuple[TestClient, MemoryWorkflowRepository],
    field: str,
    value: str,
) -> None:
    client, repository = client_and_repository
    payload = _sp_analysis_payload()
    payload["target"] = {**payload["target"], field: value}

    response = client.post("/api/v1/requests/sp-analysis", json=payload)

    assert response.status_code == 422
    assert response.json() == {
        "detail": "Request validation failed.",
        "code": "VALIDATION_ERROR",
    }
    assert repository.requests == {}
    assert repository.jobs == {}


def test_approval_route_is_absent(
    client: TestClient,
) -> None:
    headers = {"X-Correlation-ID": "corr-approve-conflict"}
    submit = client.post(
        "/api/v1/requests/sp-analysis",
        headers=headers,
        json=_sp_analysis_payload(),
    )
    assert submit.status_code == 202
    artifacts = client.get(f"/api/v1/jobs/{submit.json()['jobId']}/artifacts").json()[
        "artifacts"
    ]
    artifact_id = artifacts[0]["artifactId"]

    response = client.post(
        f"/api/v1/artifacts/{artifact_id}/approval-decisions",
        headers=headers,
        json={"decision": "APPROVE"},
    )

    assert response.status_code == 404

    preview = client.get(f"/api/v1/artifacts/{artifact_id}", headers=headers)
    assert preview.status_code == 200
    assert preview.json()["status"] != "PUBLISHED"


def test_llm_request_exposes_sanitized_agent_runs_route(client: TestClient) -> None:
    submit = client.post("/api/v1/requests/sp-analysis", json=_sp_analysis_llm_payload())

    assert submit.status_code == 202
    job_id = submit.json()["jobId"]
    response = client.get(f"/api/v1/jobs/{job_id}/agent-runs")

    assert response.status_code == 200
    payload = response.json()
    assert payload["jobId"] == job_id
    assert len(payload["agentRuns"]) == 1
    run = payload["agentRuns"][0]
    assert run["modelInvocation"]["model"] == model_profile_from_env("openai_fast_test").model
    assert run["modelInvocation"]["promptVersion"] == "prompt:sp_semantic_analysis@0.4.1"
    assert run["modelInvocation"]["componentInvocations"]
    assert any(
        component["stage"] == "platform_tool_execution"
        for component in run["modelInvocation"]["componentInvocations"]
    )
    assert "structuredOutput" in run
    assert "CREATE PROCEDURE" not in str(payload)


def test_multi_sp_llm_request_exposes_dependency_child_agent_runs_sanitized(
    client: TestClient,
) -> None:
    request_payload = _sp_analysis_llm_payload(
        ["SP_ANALYSIS_DOCUMENT", "DEPENDENCY_REPORT", "JAVA_MYBATIS_DRAFT"]
    )
    request_payload["target"] = {
        "type": "PROCEDURE",
        "schema": "dbo",
        "name": "usp_ProcessOrderBatch",
    }

    submit = client.post("/api/v1/requests/sp-analysis", json=request_payload)

    assert submit.status_code == 202
    job_id = submit.json()["jobId"]
    response = client.get(f"/api/v1/jobs/{job_id}/agent-runs")

    assert response.status_code == 200
    payload = response.json()
    runs = payload["agentRuns"]
    root_runs = [run for run in runs if run["agentType"] == "LLM_SEMANTIC_ANALYST"]
    child_runs = [
        run for run in runs if run["agentType"] == "LLM_SEMANTIC_ANALYST_DEPENDENCY"
    ]
    assert len(root_runs) == 1
    assert {run["targetRef"] for run in child_runs} == {
        "OtherDB.dbo.usp_CrossDbOrderAudit",
        "dbo.usp_GetOrderSummary",
    }

    dependency_summary = root_runs[0]["modelInvocation"]["sourceContextSummary"][
        "dependencyAnalysis"
    ]
    assert dependency_summary["mode"] == "CONFIRMED_PROCEDURES"
    assert dependency_summary["requestedDepth"] == 2
    assert dependency_summary["analyzedCount"] == len(child_runs)
    assert dependency_summary["childRunCount"] == len(child_runs)
    assert dependency_summary["skippedCount"] >= 1
    analyzed_refs = {item["targetRef"] for item in dependency_summary["analyzedTargets"]}
    assert analyzed_refs == {
        "OtherDB.dbo.usp_CrossDbOrderAudit",
        "dbo.usp_GetOrderSummary",
    }
    assert "sourceContextSummary" in dependency_summary["analyzedTargets"][0]
    cross_db_target = next(
        item
        for item in dependency_summary["analyzedTargets"]
        if item["targetRef"] == "OtherDB.dbo.usp_CrossDbOrderAudit"
    )
    assert cross_db_target["database"] == "OtherDB"
    assert cross_db_target["sourceScope"] == "SAME_SERVER_CROSS_DATABASE"
    assert dependency_summary["skippedTargets"]
    assert "CREATE PROCEDURE" not in str(payload)
    normalized_keys = _normalized_response_keys(payload)
    assert "proceduredefinition" not in normalized_keys
    assert "selectedspans" not in normalized_keys
    assert "providerresponse" not in normalized_keys


def test_approval_route_records_enriched_audit_payload_for_passed_validation(
    client_and_repository: tuple[TestClient, MemoryWorkflowRepository],
) -> None:
    client, repository = client_and_repository
    request = repository.create_request(
        db_profile_id="ppm",
        target={"type": "PROCEDURE", "schema": "dbo", "name": "GetInspItemsCd"},
        outputs=("SP_ANALYSIS_DOCUMENT",),
        options={"includeEvidenceRefs": True},
        request_hash="hash-route-p17c-approval",
        correlation_id="corr-route-p17c-approval",
        idempotency_key=None,
    )
    job = repository.create_job(request.request_id, correlation_id=request.correlation_id)
    artifact = repository.add_artifact(
        job_id=job.job_id,
        artifact_type=ArtifactType.SP_ANALYSIS_DOC,
        title="P17B Passed Analysis",
        content="\n".join(
            [
                "# Analysis",
                "",
                "## input_interpretation",
                "dbo.GetInspItemsCd",
                "",
                "## analysis_summary",
                "metadata-only approval route fixture",
                "",
                "## procedure_signature",
                "dbo.GetInspItemsCd()",
                "",
                "## evidence_summary",
                "metadata evidence bound",
                "",
                "## assumptions_and_todo",
                "None.",
                "",
                "## quality_summary",
                "- validation package passed.",
                "",
                "## evidence_map",
                "- MSSQL_METADATA fixture evidence bound",
                "",
                "## known_caveats",
                "- none",
                "",
                "## next_evidence_to_collect",
                "- none",
                "",
                "## draft_readiness",
                "- draft only",
                "",
            ]
        ),
        evidence_refs=[
            {
                "type": "MSSQL_METADATA",
                "objectRef": "PROCEDURE:dbo.GetInspItemsCd",
                "locator": "fixtures/eval/live_pilot_artifact_validation_p17_v1.yaml",
                "snapshotId": "live:ppm:2026-05-06T12:52:24Z",
            }
        ],
        generator_version="live-pilot-artifact-manifest-0.1.0",
        registry_refs=("fixture:live_pilot_artifacts_p17_v1",),
        assumptions=(),
        review_required=False,
        extra={
            "artifactVersion": "2026-05-06.p17b.v1",
            "selectedObjectRefs": ["PROCEDURE:dbo.GetInspItemsCd"],
        },
    )
    validation = repository.save_validation_report(
        artifact_id=artifact.artifact_id,
        status="PASSED",
        checks=[
            {
                "ruleId": "p17c.route.validation_passed",
                "severity": "INFO",
                "result": "PASS",
                "message": "P17B validation package passed.",
            }
        ],
        missing_evidence=[],
        manual_review_points=[],
        correlation_id="corr-route-p17c-approval",
    )

    approval = client.post(
        f"/api/v1/artifacts/{artifact.artifact_id}/approval-decisions",
        headers={"X-Correlation-ID": "corr-route-p17c-approval"},
        json={"decision": "APPROVE", "validationReportId": validation.validation_report_id},
    )

    assert approval.status_code == 404
    assert not any(event.action == "APPROVAL_DECISION_RECORDED" for event in repository.audit_events)


def test_publish_and_export_routes_are_not_exposed(client: TestClient) -> None:
    submit = client.post("/api/v1/requests/sp-analysis", json=_sp_analysis_payload())
    assert submit.status_code == 202
    artifacts = client.get(f"/api/v1/jobs/{submit.json()['jobId']}/artifacts").json()[
        "artifacts"
    ]
    artifact_id = artifacts[0]["artifactId"]

    publish = client.post(f"/api/v1/artifacts/{artifact_id}/publish")
    export = client.post(f"/api/v1/artifacts/{artifact_id}/export")

    assert publish.status_code == 404
    assert export.status_code == 404
    preview = client.get(f"/api/v1/artifacts/{artifact_id}")
    assert preview.status_code == 200
    assert preview.json()["status"] != "PUBLISHED"


def test_metadata_and_registry_routes_are_safe_skeletons(client: TestClient) -> None:
    profiles = client.get("/api/v1/metadata/db-profiles")
    assert profiles.status_code == 200
    profile_payload = profiles.json()
    assert profile_payload["defaultProfileId"]
    assert profile_payload["profiles"]
    assert all(profile["readOnly"] is True for profile in profile_payload["profiles"])
    assert "password" not in profiles.text.lower()
    assert "connection" not in profiles.text.lower()

    tools = client.get("/api/v1/metadata/tools")
    assert tools.status_code == 200
    tool_names = {tool["name"] for tool in tools.json()["tools"]}
    assert "get_table_schema" in tool_names
    assert "get_dependency_closure" in tool_names
    assert "resolve_dependency_reference" in tool_names
    assert all(tool["readOnly"] is True for tool in tools.json()["tools"])
    invokable_by_name = {tool["name"]: tool["invokable"] for tool in tools.json()["tools"]}
    assert invokable_by_name["get_dependency_closure"] is True
    assert invokable_by_name["resolve_dependency_reference"] is True
    assert invokable_by_name["get_table_schema"] is False
    assert not any("input" in tool for tool in tools.json()["tools"])

    registry = client.get("/api/v1/registry/versions")
    assert registry.status_code == 200
    registry_types = {item["registryType"] for item in registry.json()["versions"]}
    assert {"PROMPT", "TEMPLATE", "POLICY", "DB_PROFILE", "GENERATOR"}.issubset(
        registry_types
    )


def test_metadata_tool_invocation_route_returns_safe_dependency_closure(
    client: TestClient,
) -> None:
    response = client.post(
        "/api/v1/metadata/tools/get_dependency_closure/invoke",
        json={
            "arguments": {
                "dbProfileId": "master",
                "schema": "dbo",
                "objectName": "usp_ProcessOrderBatch",
                "objectType": "PROCEDURE",
                "maxDepth": 2,
                "includeReviewRequired": False,
            }
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert set(payload) == {
        "ok",
        "toolName",
        "dbProfileId",
        "snapshotId",
        "collectedAt",
        "evidenceRefs",
        "data",
    }
    assert payload["ok"] is True
    assert payload["toolName"] == "get_dependency_closure"
    assert payload["dbProfileId"] == "master"
    assert payload["evidenceRefs"]
    assert payload["data"]["unresolved"]
    assert payload["data"]["reviewRequired"] is True
    assert all(edge["resolutionStatus"] == "CONFIRMED" for edge in payload["data"]["edges"])

    forbidden_keys = {
        "rowdata",
        "rawdefinition",
        "definitiontext",
        "sqltext",
        "ddl",
        "dml",
        "execute",
        "procedureexecution",
    }
    assert forbidden_keys.isdisjoint(_normalized_response_keys(payload))


def test_metadata_tool_invocation_route_resolves_unique_reference(client: TestClient) -> None:
    response = client.post(
        "/api/v1/metadata/tools/resolve_dependency_reference/invoke",
        json={
            "arguments": {
                "dbProfileId": "master",
                "sourceObject": {
                    "schema": "dbo",
                    "name": "usp_GetOrderSummary",
                    "objectType": "PROCEDURE",
                },
                "referencedSchema": "dbo",
                "referencedName": "TB_ORDER",
            }
        },
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["resolutionStatus"] == "CONFIRMED"
    assert data["selectedResolution"]["name"] == "TB_ORDER"
    assert data["selectedResolution"]["resolutionConfidence"] == "HIGH"
    assert data["reviewRequired"] is False


def test_metadata_tool_invocation_route_rejects_disallowed_and_invalid_inputs(
    client: TestClient,
) -> None:
    disallowed = client.post(
        "/api/v1/metadata/tools/get_table_schema/invoke",
        json={
            "arguments": {
                "dbProfileId": "master",
                "schema": "dbo",
                "tableName": "TB_ORDER",
            }
        },
    )
    invalid_depth = client.post(
        "/api/v1/metadata/tools/get_dependency_closure/invoke",
        json={
            "arguments": {
                "dbProfileId": "master",
                "schema": "dbo",
                "objectName": "usp_ProcessOrderBatch",
                "objectType": "PROCEDURE",
                "maxDepth": 4,
                "secretToken": "do-not-echo",
            }
        },
    )
    free_form_sql = client.post(
        "/api/v1/metadata/tools/get_dependency_closure/invoke",
        json={
            "arguments": {
                "dbProfileId": "master",
                "schema": "dbo",
                "objectName": "usp_ProcessOrderBatch",
                "objectType": "PROCEDURE",
                "sql": "select * from TB_ORDER",
            }
        },
    )

    assert disallowed.status_code == 403
    assert disallowed.json()["code"] == "METADATA_TOOL_INVOCATION_NOT_ALLOWED"
    assert invalid_depth.status_code == 400
    assert invalid_depth.json()["code"] == "INVALID_ARGUMENTS"
    assert "do-not-echo" not in invalid_depth.text
    assert free_form_sql.status_code == 403
    assert free_form_sql.json()["code"] == "READ_ONLY_VIOLATION"
    assert "select * from" not in free_form_sql.text.lower()


def test_metadata_tool_invocation_route_blocks_ppm_template_only_without_plf_fallback(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "api_app.metadata_service.ppm_manifest_selection_mode",
        lambda: "template_only",
    )

    response = client.post(
        "/api/v1/metadata/tools/get_dependency_closure/invoke",
        json={
            "arguments": {
                "dbProfileId": "ppm",
                "schema": "dbo",
                "objectName": "usp_ProcessOrderBatch",
                "objectType": "PROCEDURE",
            }
        },
    )

    assert response.status_code == 503
    assert response.json()["code"] == "PPM_MANIFEST_TEMPLATE_ONLY"
    assert "PLF" not in response.text


def test_metadata_search_returns_read_only_identity_response(client: TestClient) -> None:
    response = client.get(
        "/api/v1/metadata/search",
        params=[
            ("dbProfileId", "master"),
            ("query", "order"),
            ("objectTypes", "PROCEDURE"),
            ("objectTypes", "TABLE"),
            ("limit", "5"),
        ],
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["dbProfileId"] == "master"
    assert payload["sourceProfile"] == "master"
    assert payload["sourceDatabase"] == "master"
    assert payload["snapshotId"] == "mcp-fixture-snapshot-0001"
    assert payload["results"]
    result = payload["results"][0]
    assert set(result["objectIdentity"]) == {"schema", "name", "type"}
    assert result["objectIdentity"]["type"] in {"PROCEDURE", "TABLE"}
    assert result["evidenceRefs"]
    assert "blockers" in result

    serialized = str(payload).lower()
    forbidden_fields = ("rowdata", "row_data", "definition", "sqltext", "ddl", "dml")
    assert not any(field in serialized for field in forbidden_fields)


def test_metadata_search_validation_and_dependency_error_shapes(client: TestClient) -> None:
    invalid_type = client.get(
        "/api/v1/metadata/search",
        params={
            "dbProfileId": "master",
            "query": "order",
            "objectTypes": "TRIGGER",
        },
    )
    blank_query = client.get(
        "/api/v1/metadata/search",
        params={
            "dbProfileId": "master",
            "query": "   ",
            "objectTypes": "TABLE",
        },
    )
    missing_profile = client.get(
        "/api/v1/metadata/search",
        params={
            "dbProfileId": "missing",
            "query": "order",
            "objectTypes": "TABLE",
        },
    )

    assert invalid_type.status_code == 422
    assert invalid_type.json()["code"] == "VALIDATION_ERROR"
    assert blank_query.status_code == 422
    assert blank_query.json()["code"] == "VALIDATION_ERROR"
    assert missing_profile.status_code == 404
    assert missing_profile.json()["code"] == "PROFILE_NOT_FOUND"
    assert set(missing_profile.json()) == {"detail", "code"}


def test_metadata_analysis_route_supports_query_and_target_modes(
    client: TestClient,
) -> None:
    query_response = client.post(
        "/api/v1/metadata/analyze",
        json={
            "dbProfileId": "master",
            "query": "order",
            "objectTypes": ["TABLE"],
            "options": {"llmProfileId": "openai_fast_test", "maxTargets": 2},
        },
    )
    target_response = client.post(
        "/api/v1/metadata/analyze",
        json={
            "dbProfileId": "master",
            "target": {"schema": "dbo", "name": "TB_ORDER", "type": "TABLE"},
            "options": {"useLlmAnalysis": False, "useAiToolOrchestration": True},
        },
    )

    assert query_response.status_code == 200
    query_payload = query_response.json()
    assert query_payload["mode"] == "QUERY"
    assert query_payload["targets"]
    assert query_payload["deterministicFacts"]
    assert "objectProfiles" in query_payload
    assert "insightGroups" in query_payload
    assert "dependencyGraph" in query_payload
    assert "dtoReadiness" in query_payload
    assert "knowledgeAssets" in query_payload
    assert {asset["assetKind"] for asset in query_payload["knowledgeAssets"]} >= {
        "METADATA_PROFILE",
        "DEPENDENCY_EVIDENCE",
        "DTO_READINESS",
    }
    assert query_payload["modelInvocation"]["outputSchemaVersion"] == (
        "schema:mssql_metadata_analysis@0.1.1"
    )
    assert query_payload["aiToolEvidence"]["status"] in {"SUCCEEDED", "REVIEW_REQUIRED"}
    assert query_payload["aiToolEvidence"]["plannerMetrics"]["claimAnalysisAvailable"] is True

    assert target_response.status_code == 200
    target_payload = target_response.json()
    assert target_payload["mode"] == "TARGET"
    assert target_payload["modelInvocation"] is None
    assert target_payload["aiToolEvidence"]["plannerMetrics"]["status"] == "SKIPPED"
    assert any(
        marker["code"] == "AI_METADATA_ANALYSIS_SKIPPED"
        for marker in target_payload["reviewMarkers"]
    )

    serialized = f"{query_response.text} {target_response.text}".lower()
    forbidden_fields = ("rowdata", "row_data", "definition", "sqltext", "ddl", "dml")
    assert not any(field in serialized for field in forbidden_fields)


def test_metadata_analysis_run_submit_and_poll(client: TestClient) -> None:
    submit_response = client.post(
        "/api/v1/metadata/analysis-runs",
        json={
            "dbProfileId": "master",
            "target": {"schema": "dbo", "name": "TB_ORDER", "type": "TABLE"},
            "options": {"useLlmAnalysis": False, "useAiToolOrchestration": True},
        },
    )

    assert submit_response.status_code == 202
    submitted = submit_response.json()
    assert submitted["runId"].startswith("metadata_run_")
    assert submitted["status"] in {"QUEUED", "RUNNING", "SUCCEEDED"}
    assert submitted["request"]["dbProfileId"] == "master"
    assert submitted["analysis"] is None
    assert submitted["error"] is None

    poll_response = client.get(f"/api/v1/metadata/analysis-runs/{submitted['runId']}")

    assert poll_response.status_code == 200
    polled = poll_response.json()
    assert polled["runId"] == submitted["runId"]
    assert polled["status"] == "SUCCEEDED"
    assert polled["startedAt"]
    assert polled["completedAt"]
    assert polled["analysis"]["mode"] == "TARGET"
    assert polled["analysis"]["target"]["name"] == "TB_ORDER"
    assert polled["analysis"]["deterministicFacts"]
    assert any(
        marker["code"] == "AI_METADATA_ANALYSIS_SKIPPED"
        for marker in polled["analysis"]["reviewMarkers"]
    )
    forbidden_keys = {
        "rowdata",
        "rawdefinition",
        "definitiontext",
        "sqltext",
        "ddl",
        "dml",
        "execute",
        "procedureexecution",
    }
    assert forbidden_keys.isdisjoint(_normalized_response_keys(submitted))
    assert forbidden_keys.isdisjoint(_normalized_response_keys(polled))


def test_metadata_analysis_run_poll_missing_id_returns_404(client: TestClient) -> None:
    response = client.get("/api/v1/metadata/analysis-runs/missing")

    assert response.status_code == 404
    assert response.json()["code"] == "METADATA_ANALYSIS_RUN_NOT_FOUND"


def test_metadata_analysis_run_poll_leaves_active_run_for_worker(
    client_and_repository: tuple[TestClient, MemoryWorkflowRepository],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, repository = client_and_repository
    monkeypatch.setenv("METADATA_ANALYSIS_RUN_STALE_SECONDS", "60")
    created = repository.create_metadata_analysis_run(
        run_id="metadata_run_stale",
        request={
            "dbProfileId": "master",
            "query": "order",
            "objectTypes": ["TABLE"],
            "options": {"useLlmAnalysis": False, "useAiToolOrchestration": False},
        },
    )
    repository.mark_metadata_analysis_run_running(created.run_id)
    stored = repository.metadata_analysis_runs[created.run_id]
    stored.submitted_at = datetime.now(UTC) - timedelta(seconds=180)
    stored.started_at = datetime.now(UTC) - timedelta(seconds=120)

    response = client.get(f"/api/v1/metadata/analysis-runs/{created.run_id}")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "RUNNING"
    assert payload["error"] is None


def test_metadata_analysis_run_execute_skips_non_stale_running_claim(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("METADATA_ANALYSIS_RUN_STALE_SECONDS", "60")
    repository = MemoryWorkflowRepository()
    service = ExplodingMetadataAnalysisService()
    created = repository.create_metadata_analysis_run(
        run_id="metadata_run_claimed_elsewhere",
        request={
            "dbProfileId": "master",
            "query": "order",
            "objectTypes": ["TABLE"],
            "options": {"useLlmAnalysis": False, "useAiToolOrchestration": False},
        },
    )
    repository.mark_metadata_analysis_run_running(created.run_id)

    claimed = execute_metadata_analysis_run(
        run_id=created.run_id,
        request=None,
        service=service,
        repository=repository,
    )

    assert claimed is False
    assert service.analyze_calls == 0
    assert repository.get_metadata_analysis_run(created.run_id).status == "RUNNING"


def test_recovery_worker_processes_queued_metadata_run(
    client_and_repository: tuple[TestClient, MemoryWorkflowRepository],
) -> None:
    _client, repository = client_and_repository
    created = repository.create_metadata_analysis_run(
        run_id="metadata_run_worker_queued",
        request={
            "dbProfileId": "master",
            "target": {"schema": "dbo", "name": "TB_ORDER", "type": "TABLE"},
            "options": {"useLlmAnalysis": False, "useAiToolOrchestration": False},
        },
    )

    report = run_recovery_once(
        repository=repository,
        metadata_service=MetadataAnalysisService(),
        batch_size=5,
    )
    record = repository.get_metadata_analysis_run(created.run_id)

    assert report.metadata_runs_claimed == 1
    assert report.errors == ()
    assert record is not None
    assert record.status == "SUCCEEDED"
    assert record.analysis
    assert record.analysis["target"]["name"] == "TB_ORDER"


def test_recovery_worker_recovers_stale_sp_workflow_same_job(
    client_and_repository: tuple[TestClient, MemoryWorkflowRepository],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _client, repository = client_and_repository
    monkeypatch.setenv("SP_WORKFLOW_STALE_SECONDS", "60")
    request = repository.create_request(
        db_profile_id="master",
        target={"type": "PROCEDURE", "schema": "dbo", "name": "usp_OrderRequest_Select"},
        outputs=("SP_ANALYSIS_DOCUMENT",),
        options={"includeEvidenceRefs": True},
        request_hash="hash-stale-sp",
        correlation_id="corr-stale-sp",
        idempotency_key=None,
    )
    job = repository.create_job(request.request_id, correlation_id=request.correlation_id)
    repository.transition_job(
        job.job_id,
        status=JobStatus.COLLECTING_METADATA,
        current_step=WorkflowStepType.COLLECT_METADATA,
    )
    repository.jobs[job.job_id].updated_at = datetime.now(UTC) - timedelta(seconds=120)

    report = run_recovery_once(
        repository=repository,
        metadata_service=MetadataAnalysisService(),
        batch_size=5,
    )
    recovered = repository.get_job(job.job_id)
    artifacts = repository.list_job_artifacts(job.job_id)

    assert report.sp_jobs_recovered == 1
    assert report.sp_jobs_failed == 0
    assert recovered is not None
    assert recovered.job_id == job.job_id
    assert recovered.status == JobStatus.VALIDATION_COMPLETE
    assert artifacts is not None
    assert len(artifacts) == 1
    assert repository.latest_validation_for(artifacts[0].artifact_id) is not None


def test_recovery_worker_reuses_existing_artifact_and_generates_missing_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SP_WORKFLOW_STALE_SECONDS", "60")
    repository = MemoryWorkflowRepository()
    request = repository.create_request(
        db_profile_id="master",
        target={"type": "PROCEDURE", "schema": "dbo", "name": "usp_OrderRequest_Select"},
        outputs=("SP_ANALYSIS_DOCUMENT", "DEPENDENCY_REPORT"),
        options={"includeEvidenceRefs": True},
        request_hash="hash-generating-recovery",
        correlation_id="corr-generating-recovery",
        idempotency_key=None,
    )
    job = repository.create_job(request.request_id, correlation_id=request.correlation_id)
    repository.transition_job(
        job.job_id,
        status=JobStatus.COLLECTING_METADATA,
        current_step=WorkflowStepType.COLLECT_METADATA,
    )
    repository.transition_job(
        job.job_id,
        status=JobStatus.ANALYZING,
        current_step=WorkflowStepType.ANALYZE,
    )
    repository.transition_job(
        job.job_id,
        status=JobStatus.GENERATING,
        current_step=WorkflowStepType.GENERATE,
    )
    service = WorkflowService(repository)
    metadata = service._collect_metadata(job.job_id, request)
    generated = service._generate_artifacts(job.job_id, request, metadata)
    existing = next(artifact for artifact in generated if artifact.type == ArtifactType.SP_ANALYSIS_DOC)
    for artifact in generated:
        if artifact.type != ArtifactType.SP_ANALYSIS_DOC:
            del repository.artifacts[artifact.artifact_id]
    repository.jobs[job.job_id].updated_at = datetime.now(UTC) - timedelta(seconds=120)

    report = run_recovery_once(
        repository=repository,
        metadata_service=MetadataAnalysisService(),
        workflow_service=service,
        batch_size=5,
    )
    artifacts = repository.list_job_artifacts(job.job_id)

    assert report.sp_jobs_recovered == 1
    assert repository.get_job(job.job_id).status == JobStatus.VALIDATION_COMPLETE
    assert artifacts is not None
    assert [artifact.type for artifact in artifacts].count(ArtifactType.SP_ANALYSIS_DOC) == 1
    assert any(artifact.artifact_id == existing.artifact_id for artifact in artifacts)
    assert any(artifact.type == ArtifactType.DEPENDENCY_REPORT for artifact in artifacts)


def test_recovery_worker_reuses_existing_validation_reports(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SP_WORKFLOW_STALE_SECONDS", "60")
    repository = CountingValidationRepository()
    request = repository.create_request(
        db_profile_id="master",
        target={"type": "PROCEDURE", "schema": "dbo", "name": "usp_OrderRequest_Select"},
        outputs=("SP_ANALYSIS_DOCUMENT", "DEPENDENCY_REPORT"),
        options={"includeEvidenceRefs": True},
        request_hash="hash-validating-recovery",
        correlation_id="corr-validating-recovery",
        idempotency_key=None,
    )
    job = repository.create_job(request.request_id, correlation_id=request.correlation_id)
    for status, step in (
        (JobStatus.COLLECTING_METADATA, WorkflowStepType.COLLECT_METADATA),
        (JobStatus.ANALYZING, WorkflowStepType.ANALYZE),
        (JobStatus.GENERATING, WorkflowStepType.GENERATE),
        (JobStatus.VALIDATING, WorkflowStepType.VALIDATE),
    ):
        repository.transition_job(job.job_id, status=status, current_step=step)
    service = WorkflowService(repository)
    metadata = service._collect_metadata(job.job_id, request)
    artifacts = service._generate_artifacts(job.job_id, request, metadata)
    first = next(artifact for artifact in artifacts if artifact.type == ArtifactType.SP_ANALYSIS_DOC)
    second = next(artifact for artifact in artifacts if artifact.type == ArtifactType.DEPENDENCY_REPORT)
    existing_report = repository.save_validation_report(
        artifact_id=first.artifact_id,
        status="PASSED",
        checks=[{"ruleId": "preseed", "status": "PASSED"}],
        missing_evidence=[],
        manual_review_points=[],
    )
    repository.jobs[job.job_id].updated_at = datetime.now(UTC) - timedelta(seconds=120)

    report = run_recovery_once(
        repository=repository,
        metadata_service=MetadataAnalysisService(),
        workflow_service=service,
        batch_size=5,
    )

    assert report.sp_jobs_recovered == 1
    assert repository.get_job(job.job_id).status == JobStatus.VALIDATION_COMPLETE
    assert repository.validation_write_count == 2
    assert repository.latest_validation_for(first.artifact_id) == existing_report
    assert repository.latest_validation_for(second.artifact_id) is not None


def test_recovery_worker_blocks_sp_workflow_when_original_request_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SP_WORKFLOW_STALE_SECONDS", "60")
    repository = MemoryWorkflowRepository()
    request = repository.create_request(
        db_profile_id="master",
        target={"type": "PROCEDURE", "schema": "dbo", "name": "usp_OrderRequest_Select"},
        outputs=("SP_ANALYSIS_DOCUMENT",),
        options={"includeEvidenceRefs": True},
        request_hash="hash-missing-request",
        correlation_id="corr-missing-request",
        idempotency_key=None,
    )
    job = repository.create_job(request.request_id, correlation_id=request.correlation_id)
    repository.transition_job(
        job.job_id,
        status=JobStatus.COLLECTING_METADATA,
        current_step=WorkflowStepType.COLLECT_METADATA,
    )
    del repository.requests[request.request_id]
    repository.jobs[job.job_id].updated_at = datetime.now(UTC) - timedelta(seconds=120)

    report = run_recovery_once(
        repository=repository,
        metadata_service=MetadataAnalysisService(),
        workflow_service=WorkflowService(repository),
        batch_size=5,
    )
    failed = repository.get_job(job.job_id)

    assert report.sp_jobs_failed == 1
    assert failed is not None
    assert failed.status == JobStatus.FAILED
    assert failed.error_code == SP_WORKFLOW_RECOVERY_BLOCKED


def test_metadata_analysis_run_preserves_dependency_error_in_status(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("P21_LIVE_PORTAL_GATE", "0")
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")
    monkeypatch.setenv("LLM_ENABLE_REMOTE", "0")
    repository = KnowledgeSchemaRequiredRepository()
    service = WorkflowService(repository)
    metadata_service = MetadataAnalysisService()
    app.dependency_overrides[get_repository] = lambda: repository
    app.dependency_overrides[get_workflow_service] = lambda: service
    app.dependency_overrides[get_metadata_analysis_service] = lambda: metadata_service
    try:
        client = TestClient(app)
        submit_response = client.post(
            "/api/v1/metadata/analysis-runs",
            json={
                "dbProfileId": "master",
                "query": "order",
                "objectTypes": ["TABLE"],
                "options": {"useLlmAnalysis": False, "useAiToolOrchestration": False},
            },
        )
        poll_response = client.get(
            f"/api/v1/metadata/analysis-runs/{submit_response.json()['runId']}"
        )
    finally:
        app.dependency_overrides.clear()
        reset_application_state()

    assert submit_response.status_code == 202
    assert poll_response.status_code == 200
    polled = poll_response.json()
    assert polled["status"] == "FAILED"
    assert polled["analysis"] is None
    assert polled["error"]["code"] == "KNOWLEDGE_SCHEMA_REQUIRED"
    assert polled["error"]["statusCode"] == 503


def test_metadata_analysis_maps_knowledge_schema_required_to_dependency_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("P21_LIVE_PORTAL_GATE", "0")
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")
    monkeypatch.setenv("LLM_ENABLE_REMOTE", "0")
    repository = KnowledgeSchemaRequiredRepository()
    service = WorkflowService(repository)
    metadata_service = MetadataAnalysisService()
    app.dependency_overrides[get_repository] = lambda: repository
    app.dependency_overrides[get_workflow_service] = lambda: service
    app.dependency_overrides[get_metadata_analysis_service] = lambda: metadata_service
    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/metadata/analyze",
            json={
                "dbProfileId": "master",
                "query": "order",
                "objectTypes": ["TABLE"],
                "options": {"useLlmAnalysis": False, "useAiToolOrchestration": False},
            },
        )
    finally:
        app.dependency_overrides.clear()
        reset_application_state()

    assert response.status_code == 503
    assert response.json()["code"] == "KNOWLEDGE_SCHEMA_REQUIRED"


def test_sp_workflow_preserves_knowledge_schema_required_failure_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("P21_LIVE_PORTAL_GATE", "0")
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")
    monkeypatch.setenv("LLM_ENABLE_REMOTE", "0")
    repository = KnowledgeSchemaRequiredRepository()
    service = WorkflowService(repository)
    app.dependency_overrides[get_repository] = lambda: repository
    app.dependency_overrides[get_workflow_service] = lambda: service
    try:
        client = TestClient(app)
        response = client.post(
            "/api/v1/requests/sp-analysis",
            json=_sp_analysis_payload(),
        )
    finally:
        app.dependency_overrides.clear()
        reset_application_state()

    assert response.status_code == 202
    payload = response.json()
    assert payload["status"] == "FAILED"
    job = repository.get_job(payload["jobId"])
    assert job is not None
    assert job.error_code == "KNOWLEDGE_SCHEMA_REQUIRED"


def test_knowledge_routes_map_schema_required_to_503_and_review_route_absent(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("P21_LIVE_PORTAL_GATE", "0")
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")
    monkeypatch.setenv("LLM_ENABLE_REMOTE", "0")
    repository = KnowledgeSchemaRequiredRepository()
    service = WorkflowService(repository)
    app.dependency_overrides[get_repository] = lambda: repository
    app.dependency_overrides[get_workflow_service] = lambda: service
    try:
        client = TestClient(app)
        assets = client.get("/api/v1/knowledge/assets")
        facts = client.get("/api/v1/knowledge/facts/search", params={"objectRef": "dbo"})
        review = client.post(
            "/api/v1/knowledge/assets/know_1/versions/knowv_1/review",
            json={"status": "REVIEW_REQUIRED"},
        )
    finally:
        app.dependency_overrides.clear()
        reset_application_state()

    assert assets.status_code == 503
    assert assets.json()["code"] == "KNOWLEDGE_SCHEMA_REQUIRED"
    assert facts.status_code == 503
    assert facts.json()["code"] == "KNOWLEDGE_SCHEMA_REQUIRED"
    assert review.status_code == 404


def test_unknown_resources_return_not_found(client: TestClient) -> None:
    job = client.get("/api/v1/jobs/job_missing")
    artifact = client.get("/api/v1/artifacts/art_missing")
    latest_validation = client.get("/api/v1/artifacts/art_missing/validation/latest")
    validation = client.post("/api/v1/artifacts/art_missing/validation")

    assert job.status_code == 404
    assert set(job.json()) == {"detail", "code"}
    assert job.json()["code"] == "RESOURCE_NOT_FOUND"
    assert artifact.status_code == 404
    assert set(artifact.json()) == {"detail", "code"}
    assert artifact.json()["code"] == "RESOURCE_NOT_FOUND"
    assert latest_validation.status_code == 404
    assert set(latest_validation.json()) == {"detail", "code"}
    assert latest_validation.json()["code"] == "RESOURCE_NOT_FOUND"
    assert validation.status_code == 404
    assert set(validation.json()) == {"detail", "code"}
    assert validation.json()["code"] == "RESOURCE_NOT_FOUND"
