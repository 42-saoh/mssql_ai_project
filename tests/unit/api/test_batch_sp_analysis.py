from __future__ import annotations

from collections.abc import Iterator

import pytest
from api_app.dependencies import get_repository, get_workflow_service, reset_application_state
from api_app.main import app
from api_app.workflow import WorkflowService
from fastapi.testclient import TestClient

import api_app.backpressure as workflow_backpressure
from tests.unit.api.fake_repository import MemoryWorkflowRepository


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("P21_LIVE_PORTAL_GATE", "0")
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")
    monkeypatch.setenv("LLM_ENABLE_REMOTE", "0")
    monkeypatch.setenv("WORKFLOW_MAX_ACTIVE_JOBS", "4")
    monkeypatch.setenv("BACKPRESSURE_WAIT_MS", "0")
    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)
    app.dependency_overrides[get_repository] = lambda: repository
    app.dependency_overrides[get_workflow_service] = lambda: service
    try:
        yield TestClient(app)
    finally:
        app.dependency_overrides.clear()
        reset_application_state()
        with workflow_backpressure._WORKFLOW_ADMISSION.condition:
            workflow_backpressure._WORKFLOW_ADMISSION.active = 0


def _batch_payload() -> dict:
    return {
        "dbProfileId": "master",
        "targets": [
            {"type": "PROCEDURE", "schema": "dbo", "name": "usp_GetOrderSummary"},
            {"type": "PROCEDURE", "schema": "dbo", "name": "usp_GetOrderSummary"},
            {"type": "PROCEDURE", "schema": "dbo", "name": "usp_OrderRequest_Select"},
        ],
        "outputs": ["SP_ANALYSIS_DOCUMENT"],
        "options": {
            "includeEvidenceRefs": True,
            "useLlmAnalysis": False,
            "useAiToolOrchestration": True,
        },
    }


def test_batch_sp_analysis_accepts_targets_and_skips_duplicates(client: TestClient) -> None:
    response = client.post("/api/v1/requests/sp-analysis/batch", json=_batch_payload())

    assert response.status_code == 202
    payload = response.json()
    assert payload["batchId"].startswith("batch_")
    assert payload["status"] == "PARTIAL"
    assert len(payload["accepted"]) == 2
    assert len(payload["rejected"]) == 1
    assert payload["rejected"][0]["code"] == "DUPLICATE_TARGET_SKIPPED"
    assert payload["limits"]["maxTargets"] >= 2
    assert payload["limits"]["maxConcurrentJobs"] >= 1
    assert all(item["jobId"].startswith("job_") for item in payload["accepted"])


def test_batch_sp_analysis_rejects_target_limit(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("SP_BATCH_MAX_TARGETS", "1")

    response = client.post("/api/v1/requests/sp-analysis/batch", json=_batch_payload())

    assert response.status_code == 400
    assert response.json()["code"] == "BATCH_TARGET_LIMIT_EXCEEDED"


def test_single_sp_analysis_returns_workflow_backpressure(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("WORKFLOW_MAX_ACTIVE_JOBS", "1")
    monkeypatch.setenv("BACKPRESSURE_WAIT_MS", "0")
    with workflow_backpressure._WORKFLOW_ADMISSION.condition:
        workflow_backpressure._WORKFLOW_ADMISSION.active = 1

    response = client.post(
        "/api/v1/requests/sp-analysis",
        json={
            "dbProfileId": "master",
            "target": {"type": "PROCEDURE", "schema": "dbo", "name": "usp_GetOrderSummary"},
            "outputs": ["SP_ANALYSIS_DOCUMENT"],
            "options": {"includeEvidenceRefs": True, "useLlmAnalysis": False},
        },
    )

    assert response.status_code == 429
    assert response.json()["code"] == "WORKFLOW_BACKPRESSURE"
