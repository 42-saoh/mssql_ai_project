from __future__ import annotations

from api_app.dependencies import reset_application_state
from api_app.live_gate import P21_LIVE_PORTAL_REQUIRED_ENV_MISSING
from api_app.main import app
from fastapi.testclient import TestClient


def test_openapi_skeleton_routes_are_registered() -> None:
    routes = {
        route.path
        for route in app.routes
        if hasattr(route, "methods") and not route.path.startswith("/docs")
    }

    assert "/health" in routes
    assert "/api/v1/requests/sp-analysis" in routes
    assert "/api/v1/jobs" in routes
    assert "/api/v1/jobs/{jobId}" in routes
    assert "/api/v1/jobs/{jobId}/agent-runs" in routes
    assert "/api/v1/jobs/{jobId}/artifacts" in routes
    assert "/api/v1/jobs/{jobId}/knowledge-assets" in routes
    assert "/api/v1/artifacts/{artifactId}" in routes
    assert "/api/v1/artifacts/{artifactId}/validation" in routes
    assert "/api/v1/artifacts/{artifactId}/validation/latest" in routes
    assert "/api/v1/artifacts/{artifactId}/approval-decisions" in routes
    assert "/api/v1/metadata/db-profiles" in routes
    assert "/api/v1/metadata/tools" in routes
    assert "/api/v1/metadata/tools/{toolName}/invoke" in routes
    assert "/api/v1/metadata/search" in routes
    assert "/api/v1/metadata/analyze" in routes
    assert "/api/v1/knowledge/assets/{assetId}" in routes
    assert "/api/v1/knowledge/assets/{assetId}/versions" in routes
    assert "/api/v1/knowledge/assets/{assetId}/versions/{versionId}/facts" in routes
    assert "/api/v1/knowledge/exports" in routes
    assert "/api/v1/registry/versions" in routes


def test_p21_live_jobs_route_reports_missing_plf_as_redacted_blocker(monkeypatch) -> None:
    for name in (
        "PLATFORM_DB_HOST",
        "PLATFORM_DB_PORT",
        "PLATFORM_DB_USER",
        "PLATFORM_DB_PASSWORD",
        "PLATFORM_DB_NAME",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("P21_LIVE_PORTAL_GATE", "1")
    reset_application_state()
    app.dependency_overrides.clear()
    try:
        response = TestClient(app).get("/api/v1/jobs")
    finally:
        reset_application_state()

    assert response.status_code == 503
    assert response.json()["code"] == P21_LIVE_PORTAL_REQUIRED_ENV_MISSING
    assert "password=" not in response.text.lower()
