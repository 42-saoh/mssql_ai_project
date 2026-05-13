from __future__ import annotations

from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from ai_agent_domain import ArtifactType
from ai_agent_runtime.gateway import model_profile_from_env
from api_app.dependencies import get_repository, get_workflow_service, reset_application_state
from api_app.main import app
from api_app.repositories import ValidationReportRecord
from api_app.workflow import WorkflowService
from fastapi.testclient import TestClient

from tests.unit.api.fake_repository import MemoryWorkflowRepository


class CountingValidationRepository(MemoryWorkflowRepository):
    def __init__(self) -> None:
        super().__init__()
        self.validation_write_count = 0

    def save_validation_report(self, **kwargs: Any) -> ValidationReportRecord:
        self.validation_write_count += 1
        return super().save_validation_report(**kwargs)


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

    job = client.get(f"/api/v1/jobs/{submitted['jobId']}")
    assert job.status_code == 200
    assert job.headers["X-Correlation-ID"].startswith("corr_")
    assert job.json()["currentStep"] == "VALIDATE"

    recent_jobs = client.get("/api/v1/jobs", params={"limit": 10})
    assert recent_jobs.status_code == 200
    assert submitted["jobId"] in {item["jobId"] for item in recent_jobs.json()["jobs"]}

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


def test_approve_without_passed_validation_returns_workflow_conflict(
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

    approval = client.post(
        f"/api/v1/artifacts/{artifact_id}/approval-decisions",
        headers=headers,
        json={
            "decision": "APPROVE",
            "reviewer": "reviewer@example.com",
            "comment": "approval must wait for passed validation",
        },
    )

    assert approval.status_code == 400
    assert approval.headers["X-Correlation-ID"] == "corr-approve-conflict"
    assert approval.json()["code"] == "WORKFLOW_STATE_CONFLICT"
    assert "PASSED" in approval.json()["detail"]

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
    assert run["modelInvocation"]["promptVersion"] == "prompt:sp_semantic_analysis@0.3.0"
    assert run["modelInvocation"]["componentInvocations"]
    assert "structuredOutput" in run
    assert "CREATE PROCEDURE" not in str(payload)


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
                "## review_checklist",
                "- [x] validation package passed.",
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
        json={
            "decision": "APPROVE",
            "reviewer": "human.reviewer@example.com",
            "comment": "route-level approval binding coverage",
            "validationReportId": validation.validation_report_id,
        },
    )

    assert approval.status_code == 201
    assert approval.headers["X-Correlation-ID"] == "corr-route-p17c-approval"
    assert approval.json()["decision"] == "APPROVE"
    assert set(approval.json()) == {
        "approvalId",
        "artifactId",
        "decision",
        "reviewer",
        "comment",
        "decidedAt",
    }

    audit = [
        event
        for event in repository.audit_events
        if event.action == "APPROVAL_DECISION_RECORDED"
    ][-1]
    assert audit.correlation_id == "corr-route-p17c-approval"
    assert audit.payload["correlationId"] == "corr-route-p17c-approval"
    assert audit.payload["artifactVersion"] == "2026-05-06.p17b.v1"
    assert audit.payload["artifactRef"]["artifactId"] == artifact.artifact_id
    assert audit.payload["validationRef"]["validationReportId"] == (
        validation.validation_report_id
    )
    assert audit.payload["approvalRef"]["approvalId"] == approval.json()["approvalId"]
    assert audit.payload["selectedObjectRefs"] == ["PROCEDURE:dbo.GetInspItemsCd"]
    assert audit.payload["evidenceRefs"] == artifact.evidence_refs


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
        "schema:mssql_metadata_analysis@0.1.0"
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
