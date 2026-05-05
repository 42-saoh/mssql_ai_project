from __future__ import annotations

import pytest
from api_app.dependencies import get_repository, get_workflow_service, reset_application_state
from api_app.main import app
from api_app.workflow import WorkflowService
from fastapi.testclient import TestClient

from tests.unit.api.fake_repository import MemoryWorkflowRepository


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")
    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)
    app.dependency_overrides[get_repository] = lambda: repository
    app.dependency_overrides[get_workflow_service] = lambda: service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        reset_application_state()


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


def test_sp_analysis_request_to_artifact_review_flow(client: TestClient) -> None:
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
    assert submitted["status"] == "REVIEW_PENDING"

    job = client.get(f"/api/v1/jobs/{submitted['jobId']}")
    assert job.status_code == 200
    assert job.headers["X-Correlation-ID"].startswith("corr_")
    assert job.json()["currentStep"] == "VALIDATE"

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

    approval = client.post(
        f"/api/v1/artifacts/{artifact_id}/approval-decisions",
        headers=headers,
        json={
            "decision": "REQUEST_CHANGES",
            "reviewer": "reviewer@example.com",
            "comment": "API skeleton decision recording only",
        },
    )
    assert approval.status_code == 201
    assert approval.headers["X-Correlation-ID"] == "corr-route-flow"
    assert approval.json()["artifactId"] == artifact_id
    assert approval.json()["decision"] == "REQUEST_CHANGES"
    assert "validationReportId" not in approval.json()
    assert "reviewerChecklist" not in approval.json()


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
    assert "get_table_schema" in {tool["name"] for tool in tools.json()["tools"]}
    assert all(tool["readOnly"] is True for tool in tools.json()["tools"])

    registry = client.get("/api/v1/registry/versions")
    assert registry.status_code == 200
    registry_types = {item["registryType"] for item in registry.json()["versions"]}
    assert {"PROMPT", "TEMPLATE", "POLICY", "DB_PROFILE", "GENERATOR"}.issubset(
        registry_types
    )


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


def test_unknown_resources_return_not_found(client: TestClient) -> None:
    job = client.get("/api/v1/jobs/job_missing")
    artifact = client.get("/api/v1/artifacts/art_missing")
    validation = client.post("/api/v1/artifacts/art_missing/validation")

    assert job.status_code == 404
    assert set(job.json()) == {"detail", "code"}
    assert job.json()["code"] == "RESOURCE_NOT_FOUND"
    assert artifact.status_code == 404
    assert set(artifact.json()) == {"detail", "code"}
    assert artifact.json()["code"] == "RESOURCE_NOT_FOUND"
    assert validation.status_code == 404
    assert set(validation.json()) == {"detail", "code"}
    assert validation.json()["code"] == "RESOURCE_NOT_FOUND"
