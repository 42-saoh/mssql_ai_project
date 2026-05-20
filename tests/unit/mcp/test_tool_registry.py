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
                "objectTypes": ["PROCEDURE", "TABLE", "COLUMN", "VIEW", "FUNCTION"],
                "limit": 20,
            }
        },
    )

    assert payload["ok"] is True
    data = payload["data"]
    result_types = {result["objectIdentity"]["type"] for result in data["results"]}
    assert {"PROCEDURE", "TABLE", "COLUMN", "VIEW", "FUNCTION"} <= result_types
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


def test_fixture_dependency_closure_collects_confirmed_and_review_required_edges() -> None:
    settings = load_live_metadata_settings()
    profiles = load_db_profiles(settings, repo_root=Path.cwd())
    registry = build_tool_registry(repository=FixtureMetadataRepository(), profiles=profiles)

    payload = registry.invoke_payload(
        "get_dependency_closure",
        {
            "arguments": {
                "dbProfileId": "master",
                "schema": "dbo",
                "objectName": "usp_ProcessOrderBatch",
                "objectType": "PROCEDURE",
                "maxDepth": 2,
                "includeReviewRequired": True,
            }
        },
    )

    data = payload["data"]
    node_names = {node["name"] for node in data["nodes"]}
    assert {"usp_ProcessOrderBatch", "usp_GetOrderSummary", "TB_ORDER"} <= node_names
    assert any(edge["resolutionStatus"] == "CONFIRMED" for edge in data["edges"])
    assert data["unresolved"]
    assert data["summary"]["maxDepth"] == 2
    assert data["reviewRequired"] is True


def test_fixture_dependency_closure_can_hide_review_required_graph_items() -> None:
    settings = load_live_metadata_settings()
    profiles = load_db_profiles(settings, repo_root=Path.cwd())
    registry = build_tool_registry(repository=FixtureMetadataRepository(), profiles=profiles)

    payload = registry.invoke_payload(
        "get_dependency_closure",
        {
            "arguments": {
                "dbProfileId": "master",
                "schema": "dbo",
                "objectName": "usp_ProcessOrderBatch",
                "objectType": "PROCEDURE",
                "maxDepth": 2,
                "includeReviewRequired": False,
            }
        },
    )

    data = payload["data"]
    assert data["unresolved"]
    assert all(edge["resolutionStatus"] == "CONFIRMED" for edge in data["edges"])
    assert all(node["reviewStatus"] == "CONFIRMED" for node in data["nodes"])


def test_fixture_dependency_reference_resolver_selects_confirmed_only() -> None:
    settings = load_live_metadata_settings()
    profiles = load_db_profiles(settings, repo_root=Path.cwd())
    registry = build_tool_registry(repository=FixtureMetadataRepository(), profiles=profiles)

    confirmed = registry.invoke_payload(
        "resolve_dependency_reference",
        {
            "arguments": {
                "dbProfileId": "master",
                "sourceObject": {
                    "schema": "dbo",
                    "name": "usp_GetOrderSummary",
                    "objectType": "PROCEDURE",
                },
                "referencedSchema": "dbo",
                "referencedName": "TB_ORDER",
            }
        },
    )
    review = registry.invoke_payload(
        "resolve_dependency_reference",
        {
            "arguments": {
                "dbProfileId": "master",
                "sourceObject": {
                    "schema": "dbo",
                    "name": "usp_GetOrderSummary",
                    "objectType": "PROCEDURE",
                },
                "referencedSchema": "dbo",
                "referencedName": "TB_ORDER_LINE",
            }
        },
    )

    assert confirmed["data"]["resolutionStatus"] == "CONFIRMED"
    assert confirmed["data"]["selectedResolution"]["name"] == "TB_ORDER"
    assert confirmed["data"]["selectedResolution"]["resolutionConfidence"] == "HIGH"
    assert confirmed["data"]["reviewRequired"] is False

    assert review["data"]["resolutionStatus"] == "REVIEW_REQUIRED"
    assert review["data"]["selectedResolution"] is None
    assert review["data"]["reviewRequired"] is True


@pytest.mark.parametrize(
    ("referenced_name", "referenced_schema", "expected_strategy"),
    [
        ("SYN_ORDER_ARCHIVE", "dbo", "AMBIGUOUS_OR_UNCONFIRMED_CANDIDATES"),
        ("usp_LateBoundOrderHook", None, "AMBIGUOUS_OR_UNCONFIRMED_CANDIDATES"),
        ("TB_REMOTE_ORDER", "dbo", "AMBIGUOUS_OR_UNCONFIRMED_CANDIDATES"),
        ("MissingOrderTarget", "dbo", "AMBIGUOUS_OR_UNCONFIRMED_CANDIDATES"),
    ],
)
def test_fixture_dependency_reference_resolver_keeps_uncertain_targets_review_required(
    referenced_name: str,
    referenced_schema: str | None,
    expected_strategy: str,
) -> None:
    settings = load_live_metadata_settings()
    profiles = load_db_profiles(settings, repo_root=Path.cwd())
    registry = build_tool_registry(repository=FixtureMetadataRepository(), profiles=profiles)
    arguments: dict[str, Any] = {
        "dbProfileId": "master",
        "sourceObject": {
            "schema": "dbo",
            "name": "usp_ProcessOrderBatch",
            "objectType": "PROCEDURE",
        },
        "referencedName": referenced_name,
    }
    if referenced_schema is not None:
        arguments["referencedSchema"] = referenced_schema

    payload = registry.invoke_payload(
        "resolve_dependency_reference",
        {"arguments": arguments},
    )

    data = payload["data"]
    assert data["candidates"]
    assert data["resolutionStatus"] == "REVIEW_REQUIRED"
    assert data["resolutionStrategy"] == expected_strategy
    assert data["selectedResolution"] is None
    assert data["reviewRequired"] is True


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


def test_tool_invocation_rejects_dependency_closure_depth_above_contract_max(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")
    client = TestClient(app)

    response = client.post(
        "/tools/get_dependency_closure/invoke",
        json={
            "arguments": {
                "dbProfileId": "master",
                "schema": "dbo",
                "objectName": "usp_ProcessOrderBatch",
                "objectType": "PROCEDURE",
                "maxDepth": 4,
            }
        },
    )

    assert response.status_code == 400
    payload = response.json()
    assert payload["ok"] is False
    assert payload["error"]["code"] == "INVALID_ARGUMENTS"
    assert payload["error"]["details"] == {
        "arguments.maxDepth": "must be less than or equal to 3"
    }


def test_tool_invocation_rejects_non_boolean_dependency_closure_flag(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")
    client = TestClient(app)

    response = client.post(
        "/tools/get_dependency_closure/invoke",
        json={
            "arguments": {
                "dbProfileId": "master",
                "schema": "dbo",
                "objectName": "usp_ProcessOrderBatch",
                "objectType": "PROCEDURE",
                "includeReviewRequired": "false",
            }
        },
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_ARGUMENTS"
    assert response.json()["error"]["details"] == {
        "arguments.includeReviewRequired": "must be a boolean"
    }


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
        self.queried_databases: list[str] = []

    def _query(  # noqa: ANN001
        self,
        database,
        sql,
        params,
        *,
        tool_name,
        profile,
        lock_timeout_ms=None,
    ):
        self.queried_databases.append(database)
        if "FROM sys.databases" in sql:
            assert lock_timeout_ms == 1000
            return [{"name": params[0], "state_desc": "ONLINE"}]
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


def test_fixture_procedure_definition_supports_confirmed_cross_database_dependency() -> None:
    settings = load_live_metadata_settings()
    profiles = load_db_profiles(settings, repo_root=Path.cwd())
    registry = build_tool_registry(repository=FixtureMetadataRepository(), profiles=profiles)

    payload = registry.invoke_payload(
        "get_procedure_definition",
        {
            "arguments": {
                "dbProfileId": "master",
                "schema": "dbo",
                "procedureName": "usp_CrossDbOrderAudit",
                "referencedDatabase": "OtherDB",
            }
        },
    )

    assert payload["data"]["database"] == "OtherDB"
    assert payload["data"]["referencedDatabase"] == "OtherDB"
    assert payload["data"]["sourceScope"] == "SAME_SERVER_CROSS_DATABASE"
    assert payload["data"]["objectIdentity"]["database"] == "OtherDB"
    assert "CREATE PROCEDURE" in payload["data"]["definition"]


def test_live_procedure_definition_queries_confirmed_cross_database_target() -> None:
    repository = DefinitionShapeLiveMetadataRepository()
    registry = build_tool_registry(repository=repository, profiles=repository.profiles or [])

    payload = registry.invoke_payload(
        "get_procedure_definition",
        {
            "arguments": {
                "dbProfileId": "master",
                "schema": "dbo",
                "procedureName": "usp_CrossDbOrderAudit",
                "referencedDatabase": "OtherDB",
            }
        },
    )

    assert payload["data"]["database"] == "OtherDB"
    assert payload["data"]["referencedDatabase"] == "OtherDB"
    assert payload["data"]["sourceScope"] == "SAME_SERVER_CROSS_DATABASE"
    assert payload["data"]["objectIdentity"]["database"] == "OtherDB"
    assert repository.queried_databases == ["master", "OtherDB"]


def _dependency_row(**overrides: Any) -> dict[str, Any]:
    row = {
        "object_id": 900,
        "referenced_id": None,
        "referenced_server_name": None,
        "referenced_database_name": None,
        "referenced_schema_name": "dbo",
        "referenced_entity_name": "TB_ORDER",
        "referenced_class_desc": "OBJECT_OR_COLUMN",
        "is_ambiguous": 0,
        "is_caller_dependent": 0,
        "direct_schema_name": None,
        "direct_object_name": None,
        "direct_object_type": None,
        "catalog_match_count": 0,
        "matched_schema_name": None,
        "matched_object_name": None,
        "matched_object_type": None,
        "synonym_schema_name": None,
        "synonym_name": None,
        "synonym_base_object_name": None,
    }
    row.update(overrides)
    return row


class ProcedureDependencyLiveMetadataRepository(LiveMetadataRepository):
    def __init__(
        self,
        *,
        dependency_rows: list[dict[str, Any]],
        module_rows: list[dict[str, Any]] | None = None,
        external_database_rows: list[dict[str, Any]] | None = None,
        external_catalog_rows: list[dict[str, Any]] | None = None,
        external_catalog_error: MetadataToolError | None = None,
    ) -> None:
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
        self.dependency_rows = dependency_rows
        self.module_rows = module_rows or [
            {
                "definition_hash": "ABCDEF",
                "definition_length": 256,
                "has_definition_access": 1,
                "has_dynamic_sql": 0,
                "has_temp_table": 0,
            }
        ]
        self.external_database_rows = external_database_rows or []
        self.external_catalog_rows = external_catalog_rows or []
        self.external_catalog_error = external_catalog_error
        self.queried_databases: list[str] = []

    def _query(  # noqa: ANN001
        self,
        database,
        sql,
        params,
        *,
        tool_name,
        profile,
        lock_timeout_ms=None,
    ):
        self.queried_databases.append(database)
        assert tool_name in {
            "get_procedure_dependencies",
            "get_dependency_closure",
            "resolve_dependency_reference",
        }
        if "FROM sys.sql_modules AS m" in sql:
            assert "LIKE '%" not in sql
            assert "%sp_executesql%" not in sql
            assert "%#%" not in sql
            return self.module_rows
        if "FROM sys.sql_expression_dependencies AS dep" in sql:
            return self.dependency_rows
        if "FROM sys.databases" in sql:
            assert database == "PPM"
            assert lock_timeout_ms == 1000
            return self.external_database_rows
        if ".sys.objects AS candidate" in sql:
            assert database == "PPM"
            assert lock_timeout_ms == 1000
            assert "[OtherDB].sys.objects" in sql
            assert "OtherDB.sys.objects" not in sql
            assert params == ["TB_ORDER", "dbo", "dbo"]
            if self.external_catalog_error is not None:
                raise self.external_catalog_error
            return self.external_catalog_rows
        if "FROM sys.objects AS o" in sql:
            return [{"object_id": 900}]
        return []


@pytest.mark.parametrize(
    "dependency_row, expected",
    [
        (
            _dependency_row(
                referenced_id=101,
                direct_schema_name="dbo",
                direct_object_name="TB_ORDER",
                direct_object_type="U ",
            ),
            {
                "objectType": "TABLE",
                "schema": "dbo",
                "name": "TB_ORDER",
                "resolutionStatus": "CONFIRMED",
                "resolutionStrategy": "REFERENCED_ID",
                "reviewStatus": "CONFIRMED",
                "isAmbiguous": False,
            },
        ),
        (
            _dependency_row(
                catalog_match_count=1,
                matched_schema_name="dbo",
                matched_object_name="TB_ORDER",
                matched_object_type="U",
            ),
            {
                "objectType": "TABLE",
                "schema": "dbo",
                "name": "TB_ORDER",
                "resolutionStatus": "CONFIRMED",
                "resolutionStrategy": "SAME_DATABASE_SCHEMA_NAME",
                "reviewStatus": "CONFIRMED",
                "isAmbiguous": False,
            },
        ),
        (
            _dependency_row(
                referenced_schema_name=None,
                referenced_entity_name="TB_UNIQUE",
                catalog_match_count=1,
                matched_schema_name="audit",
                matched_object_name="TB_UNIQUE",
                matched_object_type="U",
            ),
            {
                "objectType": "TABLE",
                "schema": "audit",
                "name": "TB_UNIQUE",
                "resolutionStatus": "CONFIRMED",
                "resolutionStrategy": "SAME_DATABASE_UNIQUE_NAME",
                "reviewStatus": "CONFIRMED",
                "isAmbiguous": False,
            },
        ),
        (
            _dependency_row(referenced_schema_name=None, catalog_match_count=2),
            {
                "objectType": "UNKNOWN",
                "schema": None,
                "name": "TB_ORDER",
                "resolutionStatus": "REVIEW_REQUIRED",
                "resolutionStrategy": "AMBIGUOUS_CATALOG_NAME",
                "reviewStatus": "REVIEW_REQUIRED",
                "isAmbiguous": True,
            },
        ),
        (
            _dependency_row(
                referenced_server_name="LinkedServer",
                referenced_database_name="OtherDB",
            ),
            {
                "objectType": "UNKNOWN",
                "schema": "dbo",
                "name": "TB_ORDER",
                "resolutionStatus": "REVIEW_REQUIRED",
                "resolutionStrategy": "CROSS_SERVER_REFERENCE",
                "sourceScope": None,
                "reviewStatus": "REVIEW_REQUIRED",
                "isAmbiguous": False,
            },
        ),
        (
            _dependency_row(
                referenced_id=202,
                direct_schema_name="dbo",
                direct_object_name="SYN_ORDER",
                direct_object_type="SN",
                synonym_schema_name="dbo",
                synonym_name="SYN_ORDER",
                synonym_base_object_name="[OtherDB].[dbo].[TB_ORDER]",
            ),
            {
                "objectType": "SYNONYM",
                "schema": "dbo",
                "name": "SYN_ORDER",
                "resolutionStatus": "REVIEW_REQUIRED",
                "resolutionStrategy": "SYNONYM_TARGET_REVIEW_REQUIRED",
                "reviewStatus": "REVIEW_REQUIRED",
                "isAmbiguous": True,
            },
        ),
        (
            _dependency_row(),
            {
                "objectType": "UNKNOWN",
                "schema": "dbo",
                "name": "TB_ORDER",
                "resolutionStatus": "REVIEW_REQUIRED",
                "resolutionStrategy": "UNRESOLVED",
                "reviewStatus": "REVIEW_REQUIRED",
                "isAmbiguous": False,
            },
        ),
    ],
)
def test_live_procedure_dependency_resolver_statuses(
    dependency_row: dict[str, Any],
    expected: dict[str, Any],
) -> None:
    repository = ProcedureDependencyLiveMetadataRepository(dependency_rows=[dependency_row])
    registry = build_tool_registry(repository=repository, profiles=repository.profiles or [])

    payload = registry.invoke_payload(
        "get_procedure_dependencies",
        {
            "arguments": {
                "dbProfileId": "ppm",
                "schema": "dbo",
                "procedureName": "usp_Selected",
            }
        },
    )

    dependency = payload["data"]["dependencies"][0]
    assert {key: dependency[key] for key in expected} == expected
    assert {
        "database",
        "server",
        "referencedDatabase",
        "referencedServer",
        "sourceScope",
    } <= set(dependency)
    assert dependency["dependencyType"] == "REFERENCE"
    assert dependency["evidenceRefs"]
    assert payload["data"]["definitionMetadata"] == {
        "hash": "abcdef",
        "length": 256,
        "detectedPatterns": [],
        "hasDefinitionAccess": True,
    }
    if dependency_row.get("referenced_database_name") and not dependency_row.get(
        "referenced_server_name"
    ):
        assert repository.queried_databases == ["PPM", "PPM", "PPM", "PPM"]
    else:
        assert repository.queried_databases == ["PPM", "PPM", "PPM"]


def test_live_procedure_dependency_resolver_confirms_same_server_cross_database_catalog() -> None:
    repository = ProcedureDependencyLiveMetadataRepository(
        dependency_rows=[_dependency_row(referenced_database_name="OtherDB")],
        external_database_rows=[{"name": "OtherDB", "state_desc": "ONLINE"}],
        external_catalog_rows=[
            {
                "external_catalog_match_count": 1,
                "external_matched_schema_name": "dbo",
                "external_matched_object_name": "TB_ORDER",
                "external_matched_object_type": "U ",
                "external_synonym_schema_name": None,
                "external_synonym_name": None,
                "external_synonym_base_object_name": None,
            }
        ],
    )
    registry = build_tool_registry(repository=repository, profiles=repository.profiles or [])

    payload = registry.invoke_payload(
        "get_procedure_dependencies",
        {
            "arguments": {
                "dbProfileId": "ppm",
                "schema": "dbo",
                "procedureName": "usp_Selected",
            }
        },
    )

    dependency = payload["data"]["dependencies"][0]
    assert dependency["objectType"] == "TABLE"
    assert dependency["database"] == "OtherDB"
    assert dependency["referencedDatabase"] == "OtherDB"
    assert dependency["referencedServer"] is None
    assert dependency["sourceScope"] == "SAME_SERVER_CROSS_DATABASE"
    assert dependency["resolutionStatus"] == "CONFIRMED"
    assert dependency["resolutionStrategy"] == "SAME_SERVER_CROSS_DATABASE_CATALOG"
    assert dependency["reviewStatus"] == "CONFIRMED"
    assert payload["data"]["caveats"] == []
    assert payload["data"]["reviewRequired"] is False
    assert repository.queried_databases == ["PPM", "PPM", "PPM", "PPM", "PPM"]


def test_live_procedure_dependency_resolver_marks_ambiguous_external_catalog_review() -> None:
    repository = ProcedureDependencyLiveMetadataRepository(
        dependency_rows=[_dependency_row(referenced_database_name="OtherDB")],
        external_database_rows=[{"name": "OtherDB", "state_desc": "ONLINE"}],
        external_catalog_rows=[
            {
                "external_catalog_match_count": 2,
                "external_matched_schema_name": None,
                "external_matched_object_name": None,
                "external_matched_object_type": None,
                "external_synonym_schema_name": None,
                "external_synonym_name": None,
                "external_synonym_base_object_name": None,
            }
        ],
    )
    registry = build_tool_registry(repository=repository, profiles=repository.profiles or [])

    payload = registry.invoke_payload(
        "get_procedure_dependencies",
        {
            "arguments": {
                "dbProfileId": "ppm",
                "schema": "dbo",
                "procedureName": "usp_Selected",
            }
        },
    )

    dependency = payload["data"]["dependencies"][0]
    assert dependency["resolutionStatus"] == "REVIEW_REQUIRED"
    assert dependency["resolutionStrategy"] == "AMBIGUOUS_CROSS_DATABASE_CATALOG_NAME"
    assert dependency["isAmbiguous"] is True
    assert payload["data"]["caveats"] == ["DEPENDENCY_METADATA_INCOMPLETE"]


def test_live_procedure_dependency_resolver_fails_inaccessible_external_catalog() -> None:
    repository = ProcedureDependencyLiveMetadataRepository(
        dependency_rows=[_dependency_row(referenced_database_name="OtherDB")],
        external_database_rows=[{"name": "OtherDB", "state_desc": "ONLINE"}],
        external_catalog_error=MetadataToolError(
            "METADATA_READ_ONLY_PERMISSION_INSUFFICIENT",
            "External catalog denied.",
            {"database": "OtherDB"},
        ),
    )
    registry = build_tool_registry(repository=repository, profiles=repository.profiles or [])

    with pytest.raises(MetadataToolError) as exc_info:
        registry.invoke_payload(
            "get_procedure_dependencies",
            {
                "arguments": {
                    "dbProfileId": "ppm",
                    "schema": "dbo",
                    "procedureName": "usp_Selected",
                }
            },
        )

    assert exc_info.value.code == "METADATA_READ_ONLY_PERMISSION_INSUFFICIENT"
    assert exc_info.value.details["database"] == "PPM"
    assert exc_info.value.details["externalDatabase"] == "OtherDB"
    assert exc_info.value.details["externalCatalogStage"] == "object_lookup"


def test_live_procedure_dependency_resolver_fails_unavailable_external_catalog() -> None:
    repository = ProcedureDependencyLiveMetadataRepository(
        dependency_rows=[_dependency_row(referenced_database_name="OtherDB")],
        external_database_rows=[{"name": "OtherDB", "state_desc": "ONLINE"}],
        external_catalog_error=MetadataToolError(
            "LIVE_METADATA_UNAVAILABLE",
            "External catalog timeout.",
            {"database": "OtherDB", "errorClass": "TimeoutError"},
        ),
    )
    registry = build_tool_registry(repository=repository, profiles=repository.profiles or [])

    with pytest.raises(MetadataToolError) as exc_info:
        registry.invoke_payload(
            "get_procedure_dependencies",
            {
                "arguments": {
                    "dbProfileId": "ppm",
                    "schema": "dbo",
                    "procedureName": "usp_Selected",
                }
            },
        )

    assert exc_info.value.code == "LIVE_METADATA_UNAVAILABLE"
    assert exc_info.value.details["database"] == "PPM"
    assert exc_info.value.details["externalDatabase"] == "OtherDB"
    assert exc_info.value.details["externalCatalogStage"] == "object_lookup"
    assert exc_info.value.details["errorClass"] == "TimeoutError"


def test_live_procedure_dependency_resolver_fails_missing_external_database() -> None:
    repository = ProcedureDependencyLiveMetadataRepository(
        dependency_rows=[_dependency_row(referenced_database_name="OtherDB")],
        external_database_rows=[],
    )
    registry = build_tool_registry(repository=repository, profiles=repository.profiles or [])

    with pytest.raises(MetadataToolError) as exc_info:
        registry.invoke_payload(
            "get_procedure_dependencies",
            {
                "arguments": {
                    "dbProfileId": "ppm",
                    "schema": "dbo",
                    "procedureName": "usp_Selected",
                }
            },
        )

    assert exc_info.value.code == "LIVE_METADATA_UNAVAILABLE"
    assert exc_info.value.details["database"] == "PPM"
    assert exc_info.value.details["externalDatabase"] == "OtherDB"
    assert exc_info.value.details["externalCatalogStage"] == "database_lookup"
    assert exc_info.value.details["externalCatalogReason"] == "not_found"
    assert repository.queried_databases == ["PPM", "PPM", "PPM"]


@pytest.mark.parametrize(
    "sql_type, expected_type",
    [
        ("U ", "TABLE"),
        ("V ", "VIEW"),
        ("P ", "PROCEDURE"),
    ],
)
def test_live_procedure_dependency_resolver_trims_padded_object_type_codes(
    sql_type: str,
    expected_type: str,
) -> None:
    repository = ProcedureDependencyLiveMetadataRepository(
        dependency_rows=[
            _dependency_row(
                referenced_id=101,
                direct_schema_name="dbo",
                direct_object_name="ResolvedObject",
                direct_object_type=sql_type,
            )
        ]
    )
    registry = build_tool_registry(repository=repository, profiles=repository.profiles or [])

    payload = registry.invoke_payload(
        "get_procedure_dependencies",
        {
            "arguments": {
                "dbProfileId": "ppm",
                "schema": "dbo",
                "procedureName": "usp_Selected",
            }
        },
    )

    assert payload["data"]["dependencies"][0]["objectType"] == expected_type


def test_live_procedure_dependency_resolver_marks_dynamic_sql_review_required() -> None:
    repository = ProcedureDependencyLiveMetadataRepository(
        dependency_rows=[],
        module_rows=[
            {
                "definition_hash": "012345",
                "definition_length": 512,
                "has_definition_access": 1,
                "has_dynamic_sql": 1,
                "has_temp_table": 0,
            }
        ],
    )
    registry = build_tool_registry(repository=repository, profiles=repository.profiles or [])

    payload = registry.invoke_payload(
        "get_procedure_dependencies",
        {
            "arguments": {
                "dbProfileId": "ppm",
                "schema": "dbo",
                "procedureName": "usp_Dynamic",
            }
        },
    )

    dependency = payload["data"]["dependencies"][0]
    assert dependency["dependencyType"] == "DYNAMIC_SQL"
    assert dependency["resolutionStrategy"] == "DYNAMIC_SQL_PATTERN"
    assert dependency["reviewStatus"] == "REVIEW_REQUIRED"
    assert payload["data"]["caveats"] == ["DEPENDENCY_METADATA_INCOMPLETE"]
    assert payload["data"]["reviewRequired"] is True


def test_live_dependency_closure_collects_same_database_confirmed_dependency() -> None:
    repository = ProcedureDependencyLiveMetadataRepository(
        dependency_rows=[
            _dependency_row(
                referenced_id=101,
                direct_schema_name="dbo",
                direct_object_name="TB_ORDER",
                direct_object_type="U ",
            )
        ]
    )
    registry = build_tool_registry(repository=repository, profiles=repository.profiles or [])

    payload = registry.invoke_payload(
        "get_dependency_closure",
        {
            "arguments": {
                "dbProfileId": "ppm",
                "schema": "dbo",
                "objectName": "usp_Selected",
                "objectType": "PROCEDURE",
                "maxDepth": 2,
                "includeReviewRequired": True,
            }
        },
    )

    data = payload["data"]
    assert data["rootObject"]["name"] == "usp_Selected"
    assert data["summary"]["maxDepth"] == 2
    assert data["summary"]["edgeCount"] == 1
    assert data["edges"][0]["resolutionStatus"] == "CONFIRMED"
    assert data["nodes"][1]["name"] == "TB_ORDER"
    assert data["unresolved"] == []
    assert data["reviewRequired"] is False


def test_live_dependency_closure_keeps_review_required_unresolved_when_hidden() -> None:
    repository = ProcedureDependencyLiveMetadataRepository(
        dependency_rows=[
            _dependency_row(referenced_schema_name=None, catalog_match_count=2),
        ]
    )
    registry = build_tool_registry(repository=repository, profiles=repository.profiles or [])

    payload = registry.invoke_payload(
        "get_dependency_closure",
        {
            "arguments": {
                "dbProfileId": "ppm",
                "schema": "dbo",
                "objectName": "usp_Selected",
                "objectType": "PROCEDURE",
                "includeReviewRequired": False,
            }
        },
    )

    data = payload["data"]
    assert data["unresolved"]
    assert data["edges"] == []
    assert [node["name"] for node in data["nodes"]] == ["usp_Selected"]
    assert data["reviewRequired"] is True


def test_live_dependency_reference_resolver_selects_same_database_confirmed_dependency() -> None:
    repository = ProcedureDependencyLiveMetadataRepository(
        dependency_rows=[
            _dependency_row(
                referenced_id=101,
                direct_schema_name="dbo",
                direct_object_name="TB_ORDER",
                direct_object_type="U ",
            )
        ]
    )
    registry = build_tool_registry(repository=repository, profiles=repository.profiles or [])

    payload = registry.invoke_payload(
        "resolve_dependency_reference",
        {
            "arguments": {
                "dbProfileId": "ppm",
                "sourceObject": {
                    "schema": "dbo",
                    "name": "usp_Selected",
                    "objectType": "PROCEDURE",
                },
                "referencedSchema": "dbo",
                "referencedName": "TB_ORDER",
            }
        },
    )

    data = payload["data"]
    assert data["resolutionStatus"] == "CONFIRMED"
    assert data["selectedResolution"]["name"] == "TB_ORDER"
    assert data["selectedResolution"]["resolutionConfidence"] == "HIGH"
    assert data["reviewRequired"] is False


def test_live_dependency_reference_resolver_confirms_same_server_cross_database_catalog() -> None:
    repository = ProcedureDependencyLiveMetadataRepository(
        dependency_rows=[_dependency_row(referenced_database_name="OtherDB")],
        external_database_rows=[{"name": "OtherDB", "state_desc": "ONLINE"}],
        external_catalog_rows=[
            {
                "external_catalog_match_count": 1,
                "external_matched_schema_name": "dbo",
                "external_matched_object_name": "TB_ORDER",
                "external_matched_object_type": "U ",
                "external_synonym_schema_name": None,
                "external_synonym_name": None,
                "external_synonym_base_object_name": None,
            }
        ],
    )
    registry = build_tool_registry(repository=repository, profiles=repository.profiles or [])

    payload = registry.invoke_payload(
        "resolve_dependency_reference",
        {
            "arguments": {
                "dbProfileId": "ppm",
                "sourceObject": {
                    "schema": "dbo",
                    "name": "usp_Selected",
                    "objectType": "PROCEDURE",
                },
                "referencedDatabase": "OtherDB",
                "referencedSchema": "dbo",
                "referencedName": "TB_ORDER",
            }
        },
    )

    data = payload["data"]
    assert data["resolutionStatus"] == "CONFIRMED"
    assert data["selectedResolution"]["database"] == "OtherDB"
    assert data["selectedResolution"]["sourceScope"] == "SAME_SERVER_CROSS_DATABASE"
    assert data["reviewRequired"] is False


@pytest.mark.parametrize(
    "dependency_rows,module_rows,reference",
    [
        (
            [_dependency_row(referenced_schema_name=None, catalog_match_count=2)],
            None,
            {"referencedName": "TB_ORDER"},
        ),
        (
            [
                _dependency_row(
                    referenced_server_name="LinkedServer",
                    referenced_database_name="OtherDB",
                )
            ],
            None,
            {"referencedSchema": "dbo", "referencedName": "TB_ORDER"},
        ),
        (
            [
                _dependency_row(
                    referenced_id=202,
                    direct_schema_name="dbo",
                    direct_object_name="SYN_ORDER",
                    direct_object_type="SN",
                    synonym_schema_name="dbo",
                    synonym_name="SYN_ORDER",
                    synonym_base_object_name="[OtherDB].[dbo].[TB_ORDER]",
                )
            ],
            None,
            {"referencedSchema": "dbo", "referencedName": "SYN_ORDER"},
        ),
        (
            [
                _dependency_row(
                    referenced_schema_name=None,
                    referenced_entity_name="usp_LateBound",
                    is_caller_dependent=1,
                )
            ],
            None,
            {"referencedName": "usp_LateBound"},
        ),
        (
            [_dependency_row(referenced_entity_name="MissingThing")],
            None,
            {"referencedSchema": "dbo", "referencedName": "MissingThing"},
        ),
        (
            [],
            [
                {
                    "definition_hash": "012345",
                    "definition_length": 512,
                    "has_definition_access": 1,
                    "has_dynamic_sql": 1,
                    "has_temp_table": 0,
                }
            ],
            {"referencedSchema": "dbo", "referencedName": "TB_ORDER"},
        ),
    ],
)
def test_live_dependency_reference_resolver_keeps_uncertain_references_review_required(
    dependency_rows: list[dict[str, Any]],
    module_rows: list[dict[str, Any]] | None,
    reference: dict[str, str],
) -> None:
    repository = ProcedureDependencyLiveMetadataRepository(
        dependency_rows=dependency_rows,
        module_rows=module_rows,
    )
    registry = build_tool_registry(repository=repository, profiles=repository.profiles or [])

    arguments = {
        "dbProfileId": "ppm",
        "sourceObject": {
            "schema": "dbo",
            "name": "usp_Selected",
            "objectType": "PROCEDURE",
        },
        **reference,
    }

    payload = registry.invoke_payload(
        "resolve_dependency_reference",
        {"arguments": arguments},
    )

    data = payload["data"]
    assert data["resolutionStatus"] == "REVIEW_REQUIRED"
    assert data["selectedResolution"] is None
    assert data["reviewRequired"] is True


def test_live_dependency_reference_resolver_refuses_confirmed_candidate_when_review_candidate_matches() -> None:
    repository = ProcedureDependencyLiveMetadataRepository(
        dependency_rows=[
            _dependency_row(
                referenced_id=101,
                direct_schema_name="dbo",
                direct_object_name="TB_ORDER",
                direct_object_type="U ",
            ),
            _dependency_row(
                referenced_server_name="LinkedServer",
                referenced_database_name="OtherDB",
            ),
        ],
    )
    registry = build_tool_registry(repository=repository, profiles=repository.profiles or [])

    payload = registry.invoke_payload(
        "resolve_dependency_reference",
        {
            "arguments": {
                "dbProfileId": "ppm",
                "sourceObject": {
                    "schema": "dbo",
                    "name": "usp_Selected",
                    "objectType": "PROCEDURE",
                },
                "referencedSchema": "dbo",
                "referencedName": "TB_ORDER",
            }
        },
    )

    data = payload["data"]
    assert len(data["candidates"]) == 2
    assert data["resolutionStatus"] == "REVIEW_REQUIRED"
    assert data["selectedResolution"] is None
    assert data["reviewRequired"] is True
