from __future__ import annotations

from api_app.main import app


def test_openapi_skeleton_routes_are_registered() -> None:
    routes = {
        route.path
        for route in app.routes
        if hasattr(route, "methods") and not route.path.startswith("/docs")
    }

    assert "/health" in routes
    assert "/api/v1/requests/sp-analysis" in routes
    assert "/api/v1/jobs/{jobId}" in routes
    assert "/api/v1/jobs/{jobId}/artifacts" in routes
    assert "/api/v1/artifacts/{artifactId}" in routes
    assert "/api/v1/artifacts/{artifactId}/validation" in routes
    assert "/api/v1/artifacts/{artifactId}/approval-decisions" in routes
    assert "/api/v1/metadata/db-profiles" in routes
    assert "/api/v1/metadata/tools" in routes
    assert "/api/v1/metadata/search" in routes
    assert "/api/v1/registry/versions" in routes
