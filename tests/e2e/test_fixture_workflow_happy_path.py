from __future__ import annotations

from collections.abc import Iterator

import pytest
from api_app.dependencies import get_repository, get_workflow_service, reset_application_state
from api_app.main import app
from api_app.workflow import WorkflowService
from fastapi.testclient import TestClient

from tests.unit.api.fake_repository import MemoryWorkflowRepository


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


def test_fixture_backed_request_to_validation_complete_happy_path(
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
                "name": "usp_GetOrderSummary",
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
    assert submitted["status"] == "VALIDATION_COMPLETE"
    assert submitted["echo"]["dbProfileId"] == "master"

    job = client.get(f"/api/v1/jobs/{submitted['jobId']}")
    assert job.status_code == 200
    assert job.json()["status"] == "VALIDATION_COMPLETE"
    assert job.json()["currentStep"] == "VALIDATE"

    listed = client.get(f"/api/v1/jobs/{submitted['jobId']}/artifacts")
    assert listed.status_code == 200
    artifacts = listed.json()["artifacts"]
    artifact_types = {artifact["type"] for artifact in artifacts}
    assert artifact_types == {
        "SP_ANALYSIS_DOC",
        "DEPENDENCY_REPORT",
        "DTO_DRAFT",
        "SERVICE_DRAFT",
        "MAPPER_INTERFACE",
        "MAPPER_XML",
    }
    assert "JAVA_MYBATIS_DRAFT" not in artifact_types

    analysis_artifact_id = next(
        artifact["artifactId"] for artifact in artifacts if artifact["type"] == "SP_ANALYSIS_DOC"
    )
    dependency_artifact_id = next(
        artifact["artifactId"] for artifact in artifacts if artifact["type"] == "DEPENDENCY_REPORT"
    )
    preview = client.get(f"/api/v1/artifacts/{analysis_artifact_id}")
    assert preview.status_code == 200
    preview_payload = preview.json()
    assert preview_payload["reviewRequired"] is True
    assert preview_payload["generatorVersion"]
    assert preview_payload["registryRefs"]
    assert {ref["type"] for ref in preview_payload["evidenceRefs"]} >= {
        "MSSQL_METADATA",
        "LLM_INFERENCE",
    }
    assert {ref["objectRef"] for ref in preview_payload["evidenceRefs"]} >= {
        "dbo.usp_GetOrderSummary",
        "dbo.TB_ORDER",
    }
    assert "dbo.TB_ORDER" in preview_payload["content"]
    assert "REVIEW_REQUIRED" in preview_payload["content"]

    dependency_preview = client.get(f"/api/v1/artifacts/{dependency_artifact_id}")
    assert dependency_preview.status_code == 200
    assert "dependency_closure_evidence" in dependency_preview.json()["content"]

    validation = client.post(f"/api/v1/artifacts/{analysis_artifact_id}/validation")
    assert validation.status_code == 200
    validation_payload = validation.json()
    assert validation_payload["artifactId"] == analysis_artifact_id
    assert validation_payload["status"] == "REVIEW_REQUIRED"
    assert validation_payload["qualityCaveats"]

    validated_preview = client.get(f"/api/v1/artifacts/{analysis_artifact_id}")
    assert validated_preview.status_code == 200
    assert validated_preview.json()["status"] == "DRAFT"

    assert {artifact.status.value for artifact in repository.artifacts.values()} <= {
        "DRAFT",
        "VALIDATED",
    }
    assert "PUBLISHED" not in {artifact.status.value for artifact in repository.artifacts.values()}
    assert "PUBLISH_GATE_EVALUATED" not in {event.action for event in repository.audit_events}
