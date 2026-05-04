from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from mssql_mcp_app.main import app
from mssql_mcp_app.profiles import load_db_profiles
from mssql_mcp_app.registry import build_tool_registry
from mssql_mcp_app.repositories import FixtureMetadataRepository
from mssql_mcp_app.settings import load_live_metadata_settings


def test_fixture_repository_returns_table_schema() -> None:
    settings = load_live_metadata_settings()
    profiles = load_db_profiles(settings, repo_root=Path.cwd())
    registry = build_tool_registry(repository=FixtureMetadataRepository(), profiles=profiles)

    payload = registry.invoke_payload(
        "get_table_schema",
        {"arguments": {"dbProfileId": "master", "schema": "dbo", "tableName": "TB_ORDER"}},
    )

    assert payload["ok"] is True
    assert payload["data"]["tableName"] == "TB_ORDER"
    assert payload["data"]["columns"][0]["name"] == "ORDER_ID"
    assert payload["evidenceRefs"][0]["source"] == "fixture"


def test_tool_invocation_rejects_free_form_sql_argument(monkeypatch) -> None:
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")
    client = TestClient(app)

    response = client.post(
        "/tools/get_table_schema/invoke",
        json={
            "arguments": {
                "dbProfileId": "master",
                "schema": "dbo",
                "tableName": "TB_ORDER",
                "sql": "SELECT * FROM dbo.TB_ORDER",
            }
        },
    )

    assert response.status_code == 403
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "READ_ONLY_VIOLATION"


def test_extended_properties_support_column_object_name(monkeypatch) -> None:
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")
    client = TestClient(app)

    response = client.post(
        "/tools/get_extended_properties/invoke",
        json={
            "arguments": {
                "dbProfileId": "master",
                "schema": "dbo",
                "objectName": "TB_ORDER.ORDER_ID",
                "objectType": "COLUMN",
            }
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["objectType"] == "COLUMN"
    assert payload["data"]["extendedProperties"][0]["level"] == "COLUMN"


def test_tool_invocation_rejects_unknown_tool(monkeypatch) -> None:
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")
    client = TestClient(app)

    response = client.post("/tools/run_sql/invoke", json={"arguments": {"dbProfileId": "master"}})

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "UNKNOWN_TOOL"


def test_tool_invocation_rejects_missing_required_argument(monkeypatch) -> None:
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")
    client = TestClient(app)

    response = client.post(
        "/tools/get_table_schema/invoke",
        json={"arguments": {"dbProfileId": "master", "schema": "dbo"}},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "INVALID_ARGUMENTS"


def test_tool_invocation_validation_error_does_not_echo_secret_like_values(monkeypatch) -> None:
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")
    client = TestClient(app)

    response = client.post(
        "/tools/get_table_schema/invoke",
        json={
            "arguments": {"dbProfileId": "master", "schema": "dbo", "tableName": "TB_ORDER"},
            "password": "do-not-echo",
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_ARGUMENTS"
    assert "do-not-echo" not in response.text


def test_tool_invocation_rejects_unknown_profile_id(monkeypatch) -> None:
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")
    client = TestClient(app)

    response = client.post(
        "/tools/get_table_schema/invoke",
        json={"arguments": {"dbProfileId": "PLF", "schema": "dbo", "tableName": "TB_ORDER"}},
    )

    assert response.status_code == 404
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "PROFILE_NOT_FOUND"


def test_live_tool_execution_stays_behind_env_gated_boundary(monkeypatch) -> None:
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "1")
    client = TestClient(app)

    response = client.post(
        "/tools/get_table_schema/invoke",
        json={"arguments": {"dbProfileId": "master", "schema": "dbo", "tableName": "TB_ORDER"}},
    )

    assert response.status_code == 503
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "LIVE_METADATA_UNAVAILABLE"
