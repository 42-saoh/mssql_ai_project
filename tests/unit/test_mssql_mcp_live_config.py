from pathlib import Path

from fastapi.testclient import TestClient

from mssql_mcp_app.main import app
from mssql_mcp_app.profiles import get_default_profile, load_db_profiles
from mssql_mcp_app.settings import load_live_metadata_settings


def test_profile_registry_file_exposes_master_default() -> None:
    settings = load_live_metadata_settings()
    profiles = load_db_profiles(settings, repo_root=Path.cwd())
    default_profile = get_default_profile(profiles)

    assert default_profile.id == "master"
    assert default_profile.database == "master"
    assert {profile.id for profile in profiles} >= {"plf", "master"}


def test_ready_endpoint_skips_live_check_when_disabled(monkeypatch) -> None:
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")
    client = TestClient(app)

    response = client.get("/health/ready")
    assert response.status_code == 200
    payload = response.json()
    assert payload["connection"] == "skipped"
    assert payload["profileId"] == "master"


def test_ready_endpoint_reports_success_when_probe_succeeds(monkeypatch) -> None:
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "1")
    monkeypatch.setenv("MSSQL_METADATA_HOST", "127.0.0.1")
    monkeypatch.setenv("MSSQL_METADATA_USER", "readonly_user")
    monkeypatch.setenv("MSSQL_METADATA_PASSWORD", "secret")

    def fake_probe(*_args, **_kwargs):
        return {
            "checked": True,
            "connection": "ok",
            "profileId": "master",
            "database": "master",
            "host": "127.0.0.1",
            "port": 1433,
            "readOnlyRequested": True,
        }

    monkeypatch.setattr("mssql_mcp_app.main.probe_profile_connection", fake_probe)

    client = TestClient(app)
    response = client.get("/health/ready")
    assert response.status_code == 200
    payload = response.json()
    assert payload["connection"] == "ok"
    assert payload["database"] == "master"


def test_db_profiles_endpoint_returns_public_registry() -> None:
    client = TestClient(app)
    response = client.get("/config/db-profiles")
    assert response.status_code == 200
    payload = response.json()
    assert payload["defaultProfileId"] == "master"
    assert any(profile["database"] == "master" for profile in payload["profiles"])
    assert any(profile["database"] == "PLF" for profile in payload["profiles"])
    for profile in payload["profiles"]:
        assert "password" not in profile
        assert "connectionString" not in profile
        assert "metadata_password" not in profile
