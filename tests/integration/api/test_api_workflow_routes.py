from __future__ import annotations

import pytest
from api_app.dependencies import get_repository, get_workflow_service, reset_application_state
from api_app.main import app
from api_app.workflow import WorkflowService
from fastapi.testclient import TestClient

from tests.unit.api.fake_repository import MemoryWorkflowRepository


@pytest.fixture
def client() -> TestClient:
    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)
    app.dependency_overrides[get_repository] = lambda: repository
    app.dependency_overrides[get_workflow_service] = lambda: service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        reset_application_state()


def test_sp_analysis_request_to_artifact_review_flow(client: TestClient) -> None:
    submit = client.post(
        "/api/v1/requests/sp-analysis",
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
    submitted = submit.json()
    assert submitted["requestId"].startswith("req_")
    assert submitted["jobId"].startswith("job_")
    assert submitted["status"] == "REVIEW_PENDING"

    job = client.get(f"/api/v1/jobs/{submitted['jobId']}")
    assert job.status_code == 200
    assert job.json()["currentStep"] == "VALIDATE"

    listed = client.get(f"/api/v1/jobs/{submitted['jobId']}/artifacts")
    assert listed.status_code == 200
    artifacts = listed.json()["artifacts"]
    artifact_types = {artifact["type"] for artifact in artifacts}
    assert "SP_ANALYSIS_DOC" in artifact_types
    assert "DEPENDENCY_REPORT" in artifact_types
    assert "DTO_DRAFT" in artifact_types
    assert "JAVA_MYBATIS_DRAFT" not in artifact_types

    artifact_id = artifacts[0]["artifactId"]
    preview = client.get(f"/api/v1/artifacts/{artifact_id}")
    assert preview.status_code == 200
    assert preview.json()["reviewRequired"] is True
    assert "generatorVersion" in preview.json()

    validation = client.post(f"/api/v1/artifacts/{artifact_id}/validation")
    assert validation.status_code == 200
    assert validation.json()["artifactId"] == artifact_id
    assert validation.json()["status"] in {"PASSED", "REVIEW_REQUIRED"}

    approval = client.post(
        f"/api/v1/artifacts/{artifact_id}/approval-decisions",
        json={
            "decision": "APPROVE",
            "reviewer": "reviewer@example.com",
            "comment": "API skeleton decision recording only",
        },
    )
    assert approval.status_code == 201
    assert approval.json()["artifactId"] == artifact_id
    assert approval.json()["decision"] == "APPROVE"


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


def test_unknown_resources_return_not_found(client: TestClient) -> None:
    assert client.get("/api/v1/jobs/job_missing").status_code == 404
    assert client.get("/api/v1/artifacts/art_missing").status_code == 404
    assert client.post("/api/v1/artifacts/art_missing/validation").status_code == 404
