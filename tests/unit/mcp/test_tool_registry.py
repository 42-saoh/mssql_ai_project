from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from mssql_mcp_app.catalog import TOOL_CATALOG
from mssql_mcp_app.errors import MetadataToolError
from mssql_mcp_app.main import app
from mssql_mcp_app.profiles import DbProfile, load_db_profiles
from mssql_mcp_app.registry import build_tool_registry
from mssql_mcp_app.repositories import FixtureMetadataRepository, LiveMetadataRepository
from mssql_mcp_app.settings import LiveMetadataSettings, load_live_metadata_settings


DEFINITION_TOOL_CASES = [
    (
        "get_procedure_definition",
        {"dbProfileId": "master", "schema": "dbo", "procedureName": "usp_GetOrderSummary"},
    ),
    (
        "get_view_definition",
        {"dbProfileId": "master", "schema": "dbo", "viewName": "VW_ORDER_SUMMARY"},
    ),
    (
        "get_function_definition",
        {"dbProfileId": "master", "schema": "dbo", "functionName": "fn_NormalizeOrderStatus"},
    ),
]


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


@pytest.mark.parametrize("tool_name, arguments", DEFINITION_TOOL_CASES)
def test_fixture_definition_tools_return_standard_definition_metadata(
    tool_name: str,
    arguments: dict[str, Any],
) -> None:
    settings = load_live_metadata_settings()
    profiles = load_db_profiles(settings, repo_root=Path.cwd())
    registry = build_tool_registry(repository=FixtureMetadataRepository(), profiles=profiles)

    payload = registry.invoke_payload(tool_name, {"arguments": arguments})
    data = payload["data"]

    assert payload["ok"] is True
    assert isinstance(data["definition"], str)
    assert data["definitionHash"]
    assert isinstance(data["definitionLength"], int)
    assert data["definitionLength"] == len(data["definition"])
    assert isinstance(data["detectedPatterns"], list)
    assert data["hasDefinitionAccess"] is True
    assert isinstance(data["caveats"], list)
    assert isinstance(data["reviewRequired"], bool)
    assert data["sourceProfile"] == arguments["dbProfileId"]
    assert data["objectIdentity"]["database"] == "master"


def test_fixture_inventory_tools_do_not_return_definition_text() -> None:
    settings = load_live_metadata_settings()
    profiles = load_db_profiles(settings, repo_root=Path.cwd())
    registry = build_tool_registry(repository=FixtureMetadataRepository(), profiles=profiles)

    procedure_inventory = registry.invoke_payload(
        "list_procedures",
        {"arguments": {"dbProfileId": "master", "schema": "dbo", "topK": 10}},
    )
    view_inventory = registry.invoke_payload(
        "list_views",
        {"arguments": {"dbProfileId": "master", "schema": "dbo", "topK": 10}},
    )
    function_inventory = registry.invoke_payload(
        "list_functions",
        {"arguments": {"dbProfileId": "master", "schema": "dbo", "topK": 10}},
    )

    inventories = [procedure_inventory, view_inventory, function_inventory]
    assert "CREATE PROCEDURE" not in str(inventories)
    assert "CREATE VIEW" not in str(inventories)
    assert "CREATE FUNCTION" not in str(inventories)
    assert procedure_inventory["data"]["procedures"][0]["definition"]["hash"]
    assert view_inventory["data"]["views"][0]["definition"]["hash"]
    assert function_inventory["data"]["functions"][0]["definition"]["hash"]


def test_fixture_metadata_object_search_returns_identity_only_results() -> None:
    settings = load_live_metadata_settings()
    profiles = load_db_profiles(settings, repo_root=Path.cwd())
    registry = build_tool_registry(repository=FixtureMetadataRepository(), profiles=profiles)

    payload = registry.invoke_payload(
        "search_metadata_objects",
        {
            "arguments": {
                "dbProfileId": "master",
                "query": "order",
                "objectTypes": ["PROCEDURE", "TABLE", "VIEW", "FUNCTION"],
                "limit": 10,
            }
        },
    )

    assert payload["ok"] is True
    data = payload["data"]
    result_types = {result["objectIdentity"]["type"] for result in data["results"]}
    assert {"PROCEDURE", "TABLE", "VIEW", "FUNCTION"} <= result_types
    assert data["blockers"][0]["code"] == "DEPENDENCY_METADATA_INCOMPLETE"
    assert all(result["evidenceRefs"] for result in data["results"])

    serialized = str(data).lower()
    for forbidden in ("rowdata", "row_data", "create procedure", "create view", "create function"):
        assert forbidden not in serialized


def test_fixture_metadata_object_search_uses_ppm_without_plf_fallback() -> None:
    settings = load_live_metadata_settings()
    profiles = load_db_profiles(settings, repo_root=Path.cwd())
    registry = build_tool_registry(repository=FixtureMetadataRepository(), profiles=profiles)

    payload = registry.invoke_payload(
        "search_metadata_objects",
        {
            "arguments": {
                "dbProfileId": "ppm",
                "query": "order",
                "objectTypes": ["TABLE"],
                "limit": 5,
            }
        },
    )

    assert payload["data"]["sourceProfile"] == "ppm"
    assert payload["data"]["sourceDatabase"] == "PPM"
    assert payload["data"]["sourceDatabase"] != "PLF"
    assert payload["data"]["results"]
    assert all(result["sourceDatabase"] == "PPM" for result in payload["data"]["results"])


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


def test_check_database_exists_allows_master_to_probe_ppm(monkeypatch) -> None:
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")
    client = TestClient(app)

    response = client.post(
        "/tools/check_database_exists/invoke",
        json={"arguments": {"dbProfileId": "master", "databaseName": "PPM"}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["databaseName"] == "PPM"
    assert payload["data"]["sourceProfile"] == "master"


@pytest.mark.parametrize(
    "db_profile_id, database_name, expected_database",
    [
        ("ppm", "PLF", "PPM"),
        ("plf", "PPM", "PLF"),
    ],
)
def test_check_database_exists_rejects_cross_profile_database_probe(
    db_profile_id: str,
    database_name: str,
    expected_database: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")
    client = TestClient(app)

    response = client.post(
        "/tools/check_database_exists/invoke",
        json={"arguments": {"dbProfileId": db_profile_id, "databaseName": database_name}},
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["ok"] is False
    assert payload["collectedAt"]
    assert payload["error"]["code"] == "INVALID_ARGUMENTS"
    assert payload["error"]["details"]["requestedDatabase"] == database_name
    assert payload["error"]["details"]["expectedDatabase"] == expected_database


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


class SearchLiveMetadataRepository(LiveMetadataRepository):
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
        assert tool_name == "search_metadata_objects"
        assert "sys.objects" in sql
        assert "sys.sql_modules" not in sql
        return [
            {
                "object_id": 42,
                "object_type": "P",
                "schema_name": "dbo",
                "object_name": "usp_OrderSearch",
                "description": None,
                "dep_schema_name": None,
                "dep_object_name": None,
                "dep_referenced_type": None,
                "referenced_class_desc": None,
                "is_ambiguous": None,
            }
        ]


def test_live_metadata_object_search_queries_ppm_only_without_definition_text() -> None:
    repository = SearchLiveMetadataRepository()
    registry = build_tool_registry(repository=repository, profiles=repository.profiles or [])

    payload = registry.invoke_payload(
        "search_metadata_objects",
        {
            "arguments": {
                "dbProfileId": "ppm",
                "query": "Order",
                "objectTypes": ["PROCEDURE"],
                "limit": 5,
            }
        },
    )

    assert repository.queried_databases == ["PPM"]
    assert payload["data"]["sourceDatabase"] == "PPM"
    assert payload["data"]["results"][0]["objectIdentity"] == {
        "schema": "dbo",
        "name": "usp_OrderSearch",
        "type": "PROCEDURE",
    }
    assert payload["data"]["results"][0]["sourceDatabase"] == "PPM"
    assert "definition" not in str(payload).lower()


class DefinitionShapeLiveMetadataRepository(LiveMetadataRepository):
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
                    id="master",
                    label="Server metadata (master)",
                    database="master",
                    purpose="server",
                    is_default=True,
                )
            ],
        )

    def _query(self, database, sql, params, *, tool_name, profile):  # noqa: ANN001
        if "sys.sql_expression_dependencies" in sql:
            return []
        if tool_name == "get_procedure_definition":
            return [
                {
                    "schema_name": params[0],
                    "object_name": params[1],
                    "is_encrypted": 0,
                    "definition": (
                        "CREATE PROCEDURE dbo.usp_GetOrderSummary AS "
                        "BEGIN SELECT ORDER_ID FROM dbo.TB_ORDER END"
                    ),
                }
            ]
        if tool_name == "get_view_definition":
            return [
                {
                    "schema_name": params[0],
                    "object_name": params[1],
                    "object_id": 101,
                    "definition": (
                        "CREATE VIEW dbo.VW_ORDER_SUMMARY AS "
                        "SELECT ORDER_ID FROM dbo.TB_ORDER"
                    ),
                }
            ]
        if tool_name == "get_function_definition":
            return [
                {
                    "schema_name": params[0],
                    "object_name": params[1],
                    "object_id": 102,
                    "definition": (
                        "CREATE FUNCTION dbo.fn_NormalizeOrderStatus() "
                        "RETURNS INT AS BEGIN RETURN 1 END"
                    ),
                }
            ]
        return []


@pytest.mark.parametrize("tool_name, arguments", DEFINITION_TOOL_CASES)
def test_live_definition_tools_match_fixture_definition_metadata_shape(
    tool_name: str,
    arguments: dict[str, Any],
) -> None:
    settings = load_live_metadata_settings()
    profiles = load_db_profiles(settings, repo_root=Path.cwd())
    fixture_registry = build_tool_registry(
        repository=FixtureMetadataRepository(),
        profiles=profiles,
    )
    live_repository = DefinitionShapeLiveMetadataRepository()
    live_registry = build_tool_registry(
        repository=live_repository,
        profiles=live_repository.profiles or [],
    )

    fixture_data = fixture_registry.invoke_payload(tool_name, {"arguments": arguments})["data"]
    live_data = live_registry.invoke_payload(tool_name, {"arguments": arguments})["data"]

    expected_keys = {
        "definition",
        "definitionHash",
        "definitionLength",
        "detectedPatterns",
        "hasDefinitionAccess",
        "caveats",
        "reviewRequired",
        "sourceProfile",
        "sourceDatabase",
        "objectIdentity",
        "snapshotMode",
    }
    assert expected_keys <= set(fixture_data)
    assert expected_keys <= set(live_data)
    assert isinstance(fixture_data["definitionLength"], int)
    assert isinstance(live_data["definitionLength"], int)
    assert isinstance(fixture_data["detectedPatterns"], list)
    assert isinstance(live_data["detectedPatterns"], list)
    assert isinstance(fixture_data["hasDefinitionAccess"], bool)
    assert isinstance(live_data["hasDefinitionAccess"], bool)
