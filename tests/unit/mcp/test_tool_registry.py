from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from mssql_mcp_app.catalog import TOOL_CATALOG
from mssql_mcp_app.errors import MetadataToolError
from mssql_mcp_app.main import app
from mssql_mcp_app.profiles import DbProfile, load_db_profiles
from mssql_mcp_app.registry import build_tool_registry
from mssql_mcp_app.repositories import FixtureMetadataRepository, LiveMetadataRepository
from mssql_mcp_app.settings import LiveMetadataSettings, load_live_metadata_settings


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
    assert payload["data"]["sourceProfile"] == "master"
    assert payload["data"]["sourceDatabase"] == "master"
    assert payload["data"]["objectIdentity"] == {
        "database": "master",
        "schema": "dbo",
        "name": "TB_ORDER",
        "objectType": "TABLE",
    }
    assert isinstance(payload["data"]["caveats"], list)
    assert isinstance(payload["data"]["reviewRequired"], bool)
    assert payload["evidenceRefs"][0]["source"] == "fixture"


def test_fixture_repository_returns_ppm_discovery_inventory() -> None:
    settings = load_live_metadata_settings()
    profiles = load_db_profiles(settings, repo_root=Path.cwd())
    registry = build_tool_registry(repository=FixtureMetadataRepository(), profiles=profiles)

    database = registry.invoke_payload(
        "check_database_exists",
        {"arguments": {"dbProfileId": "ppm", "databaseName": "PPM"}},
    )
    procedures = registry.invoke_payload(
        "list_procedures",
        {"arguments": {"dbProfileId": "ppm", "schema": "dbo", "topK": 10}},
    )
    tables = registry.invoke_payload(
        "list_tables",
        {"arguments": {"dbProfileId": "ppm", "schema": "dbo", "topK": 10}},
    )
    table_schema = registry.invoke_payload(
        "get_table_schema",
        {"arguments": {"dbProfileId": "ppm", "schema": "dbo", "tableName": "TB_ORDER"}},
    )

    assert database["data"]["sourceProfile"] == "ppm"
    assert database["data"]["sourceDatabase"] == "PPM"
    assert database["data"]["exists"] is True
    assert database["data"]["accessible"] is True

    procedure_items = procedures["data"]["procedures"]
    assert procedures["data"]["sourceProfile"] == "ppm"
    assert procedures["data"]["sourceDatabase"] == "PPM"
    assert {item["complexity"] for item in procedure_items} == {"simple", "medium", "complex"}
    assert all("hash" in item["definition"] for item in procedure_items)
    assert "CREATE PROCEDURE" not in str(procedure_items)

    table_items = tables["data"]["tables"]
    assert len(table_items) >= 3
    assert all("keyIndexConstraintSummary" in item for item in table_items)
    assert any(item["relatedProcedures"] for item in table_items)
    assert table_schema["data"]["sourceDatabase"] == "PPM"
    assert table_schema["data"]["objectIdentity"]["database"] == "PPM"
    assert table_schema["data"]["objectIdentity"]["name"] == "TB_ORDER"
    assert table_schema["data"]["sourceDatabase"] != "PLF"


def test_fixture_repository_returns_view_and_function_inventory() -> None:
    settings = load_live_metadata_settings()
    profiles = load_db_profiles(settings, repo_root=Path.cwd())
    registry = build_tool_registry(repository=FixtureMetadataRepository(), profiles=profiles)

    views = registry.invoke_payload(
        "list_views",
        {"arguments": {"dbProfileId": "ppm", "schema": "dbo", "topK": 10}},
    )
    functions = registry.invoke_payload(
        "list_functions",
        {"arguments": {"dbProfileId": "ppm", "schema": "dbo", "topK": 10}},
    )

    assert views["data"]["views"][0]["objectType"] == "VIEW"
    assert views["data"]["views"][0]["definition"]["available"] is True
    assert functions["data"]["functions"][0]["objectType"] == "FUNCTION"
    assert functions["data"]["functions"][0]["definition"]["available"] is True


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


def test_tool_invocation_rejects_nested_free_form_sql_argument(monkeypatch) -> None:
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")
    client = TestClient(app)

    response = client.post(
        "/tools/find_similar_tables/invoke",
        json={
            "arguments": {
                "dbProfileId": "master",
                "columns": [
                    {
                        "name": "ORDER_ID",
                        "type": "INT",
                        "query": "SELECT * FROM dbo.TB_ORDER",
                    }
                ],
            }
        },
    )

    assert response.status_code == 403
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "READ_ONLY_VIOLATION"
    assert payload["error"]["details"]["argumentPath"] == "arguments.columns[0].query"


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


def test_live_repository_has_handlers_for_active_catalog_tools() -> None:
    missing = [
        tool.name
        for tool in TOOL_CATALOG
        if tool.active
        and tool.read_only
        and not hasattr(LiveMetadataRepository, f"_handle_{tool.name}")
    ]

    assert missing == []


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
    monkeypatch.delenv("MSSQL_METADATA_HOST", raising=False)
    monkeypatch.delenv("MSSQL_METADATA_USER", raising=False)
    monkeypatch.delenv("MSSQL_METADATA_PASSWORD", raising=False)
    client = TestClient(app)

    response = client.post(
        "/tools/get_table_schema/invoke",
        json={"arguments": {"dbProfileId": "master", "schema": "dbo", "tableName": "TB_ORDER"}},
    )

    assert response.status_code == 503
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "LIVE_METADATA_UNAVAILABLE"
    details = payload["error"]["details"]
    assert details["dbProfileId"] == "master"
    assert details["database"] == "master"
    assert details["attempt"] == 1
    assert isinstance(details["timeoutSeconds"], int)
    assert "SELECT" not in response.text.upper()
    assert "PASSWORD" not in response.text.upper()


class EmptyLiveMetadataRepository(LiveMetadataRepository):
    def __init__(self) -> None:
        super().__init__(
            settings=LiveMetadataSettings(
                live_metadata_enabled=True,
                metadata_host="127.0.0.1",
                metadata_port=1433,
                metadata_user="readonly_user",
                metadata_password="secret",
                metadata_db_fallback="master",
                default_profile_id="master",
                profile_file="config/mssql/local_docker_profiles.yaml",
                connect_timeout_seconds=7,
            ),
            profiles=[
                DbProfile(
                    id="ppm",
                    label="Pilot Analysis Target DB (PPM)",
                    database="PPM",
                    purpose="pilot-analysis-target",
                )
            ],
        )
        self.queried_databases: list[str] = []

    def _query(self, database, sql, params, *, tool_name, profile):  # noqa: ANN001
        self.queried_databases.append(database)
        return []


def test_live_missing_table_metadata_reports_not_found_without_plf_fallback() -> None:
    repository = EmptyLiveMetadataRepository()

    with pytest.raises(MetadataToolError) as exc_info:
        repository.invoke(
            "get_table_indexes",
            {"dbProfileId": "ppm", "schema": "dbo", "tableName": "MISSING_TABLE"},
        )

    assert exc_info.value.code == "OBJECT_NOT_FOUND"
    assert exc_info.value.details["objectType"] == "TABLE"
    assert repository.queried_databases == ["PPM"]
