from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient
from mssql_mcp_app.main import app

REPO_ROOT = Path(__file__).resolve().parents[3]

PLANNED_TOOL_NAMES = {
    "get_dependency_closure",
    "resolve_dependency_reference",
}

TOOL_INVOCATIONS: dict[str, dict[str, Any]] = {
    "check_database_exists": {
        "dbProfileId": "master",
        "databaseName": "PPM",
    },
    "list_procedures": {
        "dbProfileId": "master",
        "schema": "dbo",
        "topK": 10,
    },
    "list_tables": {
        "dbProfileId": "master",
        "schema": "dbo",
        "topK": 10,
    },
    "list_views": {
        "dbProfileId": "master",
        "schema": "dbo",
        "topK": 10,
    },
    "list_functions": {
        "dbProfileId": "master",
        "schema": "dbo",
        "topK": 10,
    },
    "search_metadata_objects": {
        "dbProfileId": "master",
        "query": "order",
        "objectTypes": ["PROCEDURE", "TABLE", "VIEW", "FUNCTION"],
        "limit": 4,
    },
    "get_procedure_definition": {
        "dbProfileId": "master",
        "schema": "dbo",
        "procedureName": "usp_GetOrderSummary",
    },
    "get_procedure_parameters": {
        "dbProfileId": "master",
        "schema": "dbo",
        "procedureName": "usp_GetOrderSummary",
    },
    "get_procedure_dependencies": {
        "dbProfileId": "master",
        "schema": "dbo",
        "procedureName": "usp_GetOrderSummary",
    },
    "get_related_db_objects": {
        "dbProfileId": "master",
        "schema": "dbo",
        "objectName": "usp_GetOrderSummary",
        "objectType": "PROCEDURE",
        "topK": 5,
    },
    "get_table_schema": {
        "dbProfileId": "master",
        "schema": "dbo",
        "tableName": "TB_ORDER",
    },
    "get_table_constraints": {
        "dbProfileId": "master",
        "schema": "dbo",
        "tableName": "TB_ORDER",
    },
    "get_table_indexes": {
        "dbProfileId": "master",
        "schema": "dbo",
        "tableName": "TB_ORDER",
    },
    "get_extended_properties": {
        "dbProfileId": "master",
        "schema": "dbo",
        "objectName": "TB_ORDER",
        "objectType": "TABLE",
    },
    "get_view_definition": {
        "dbProfileId": "master",
        "schema": "dbo",
        "viewName": "VW_ORDER_SUMMARY",
    },
    "get_function_definition": {
        "dbProfileId": "master",
        "schema": "dbo",
        "functionName": "fn_NormalizeOrderStatus",
    },
    "search_tables": {
        "dbProfileId": "master",
        "physicalName": "ORDER",
        "columns": ["ORDER_ID", "CUSTOMER_ID"],
        "topK": 3,
    },
    "search_columns": {
        "dbProfileId": "master",
        "physicalName": "ORDER_ID",
        "topK": 3,
    },
    "find_similar_tables": {
        "dbProfileId": "master",
        "description": "order",
        "columns": [
            {"name": "ORDER_ID", "type": "INT"},
            {"name": "CUSTOMER_ID", "type": "INT"},
        ],
        "topK": 3,
    },
}


def test_catalog_contract_declares_all_active_tool_invocations() -> None:
    payload = yaml.safe_load(
        (REPO_ROOT / "spec" / "mcp" / "mssql_metadata_tool_catalog.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert payload["service"] == "mssqlMetadata"
    assert payload["readOnly"] is True
    active_tool_names = {
        tool["name"] for tool in payload["tools"] if tool["active"] is True
    }
    planned_tool_names = {
        tool["name"] for tool in payload["tools"] if tool["active"] is False
    }
    assert active_tool_names == set(TOOL_INVOCATIONS)
    assert PLANNED_TOOL_NAMES <= planned_tool_names
    assert all(tool["readOnly"] is True for tool in payload["tools"])


def test_p27_dependency_evidence_design_tools_are_contract_only() -> None:
    payload = yaml.safe_load(
        (REPO_ROOT / "spec" / "mcp" / "mssql_metadata_tool_catalog.yaml").read_text(
            encoding="utf-8"
        )
    )
    tools = {tool["name"]: tool for tool in payload["tools"]}
    for tool_name in PLANNED_TOOL_NAMES:
        tool = tools[tool_name]
        assert tool["active"] is False
        assert tool["readOnly"] is True
        assert tool["designStatus"] == "planned_p27_design_only"
        assert tool["input"]["type"] == "object"
        assert "query" not in tool["input"]["properties"]
        assert "sql" not in tool["input"]["properties"]
        assert "snapshotId" in payload["response"]["success"]["required"]
        assert "collectedAt" in payload["response"]["success"]["required"]
        assert "evidenceRefs" in payload["response"]["success"]["required"]

    closure_tool = tools["get_dependency_closure"]
    assert closure_tool["input"]["properties"]["maxDepth"] == {
        "type": "integer",
        "default": 2,
        "maximum": 3,
    }
    assert closure_tool["input"]["properties"]["includeReviewRequired"] == {
        "type": "boolean",
        "default": True,
    }
    edge_item = closure_tool["output"]["properties"]["edges"]["items"]
    assert {
        "dependencyType",
        "resolutionStatus",
        "resolutionStrategy",
        "evidenceRefs",
    } <= set(edge_item["required"])
    assert {
        "resolutionConfidence",
        "resolutionEvidenceKind",
        "unresolvedReason",
        "resolutionChain",
    } <= set(edge_item["properties"])

    resolver_tool = tools["resolve_dependency_reference"]
    assert resolver_tool["input"]["required"] == [
        "dbProfileId",
        "sourceObject",
        "referencedName",
    ]
    assert resolver_tool["output"]["required"] == [
        "candidates",
        "selectedResolution",
        "resolutionStatus",
        "resolutionStrategy",
        "evidenceRefs",
        "caveats",
    ]
    assert {
        "resolutionConfidence",
        "resolutionEvidenceKind",
        "unresolvedReason",
        "resolutionChain",
    } <= set(resolver_tool["output"]["properties"])

    dependency_item = payload["response"]["dependencyItem"]
    assert {
        "resolutionConfidence",
        "resolutionEvidenceKind",
        "unresolvedReason",
        "resolutionChain",
    } <= set(dependency_item["properties"])


def test_p27_dependency_evidence_eval_contract_matches_mcp_catalog() -> None:
    contract = yaml.safe_load(
        (
            REPO_ROOT
            / "spec"
            / "eval"
            / "p27_dependency_evidence_tooling_contract.yaml"
        ).read_text(encoding="utf-8")
    )
    assert contract["contract_id"] == "p27_dependency_evidence_tooling_design@0.1.0"
    assert contract["production_ready"] is False
    assert contract["scope"]["excluded"] == [
        "MCP handler implementation",
        "API or Web wiring",
        "persisted artifact type changes",
        "fixture suite expansion beyond contract checks",
        "live metadata gate requirements",
    ]
    assert contract["invariants"]["read_only"] is True
    assert contract["invariants"]["structured_input_only"] is True
    assert contract["invariants"]["ppm_to_plf_fallback_allowed"] is False
    assert contract["invariants"]["row_data_allowed"] is False
    assert contract["invariants"]["procedure_execution_allowed"] is False
    assert contract["invariants"]["business_db_ddl_dml_allowed"] is False
    assert contract["planned_tools"]["get_dependency_closure"]["active"] is False
    assert contract["planned_tools"]["resolve_dependency_reference"]["active"] is False
    assert set(contract["planned_tools"]) == PLANNED_TOOL_NAMES
    assert contract["dependency_resolution_contract"]["added_fields"] == [
        "resolutionConfidence",
        "resolutionEvidenceKind",
        "unresolvedReason",
        "resolutionChain",
    ]


@pytest.mark.parametrize("tool_name, arguments", TOOL_INVOCATIONS.items())
def test_fixture_backed_tool_contract(
    tool_name: str,
    arguments: dict[str, Any],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")
    client = TestClient(app)

    response = client.post(f"/tools/{tool_name}/invoke", json={"arguments": arguments})

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["toolName"] == tool_name
    assert payload["dbProfileId"] == "master"
    assert payload["snapshotId"] == "mcp-fixture-snapshot-0001"
    assert payload["collectedAt"] == "2026-01-15T00:00:00Z"
    assert payload["evidenceRefs"]
    assert payload["data"]
    assert payload["data"]["sourceProfile"] == arguments["dbProfileId"]
    assert payload["data"]["sourceDatabase"] == "master"
    assert payload["data"]["objectIdentity"]["database"]
    assert payload["data"]["objectIdentity"]["objectType"]
    assert isinstance(payload["data"]["caveats"], list)
    assert isinstance(payload["data"]["reviewRequired"], bool)
    assert "error" not in payload
    for evidence_ref in payload["evidenceRefs"]:
        assert evidence_ref["source"] == "fixture"
        assert evidence_ref["path"].startswith("fixtures/mcp/")


def test_fixture_metadata_object_search_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")
    client = TestClient(app)

    response = client.post(
        "/tools/search_metadata_objects/invoke",
        json={
            "arguments": {
                "dbProfileId": "master",
                "query": "order",
                "objectTypes": ["PROCEDURE", "TABLE", "VIEW", "FUNCTION"],
                "limit": 4,
            }
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["results"]
    assert len(payload["data"]["results"]) <= 4
    assert payload["data"]["blockers"]
    for result in payload["data"]["results"]:
        assert set(result["objectIdentity"]) == {"schema", "name", "type"}
        assert result["objectIdentity"]["type"] in {"PROCEDURE", "TABLE", "VIEW", "FUNCTION"}
        assert result["sourceProfile"] == "master"
        assert result["sourceDatabase"] == "master"
        assert result["snapshotId"] == "mcp-fixture-snapshot-0001"
        assert result["evidenceRefs"]
        assert isinstance(result["caveats"], list)
        assert isinstance(result["reviewRequired"], bool)
        assert isinstance(result["blockers"], list)

    serialized = str(payload).lower()
    forbidden = ("rowdata", "row_data", "create procedure", "create view", "create function")
    assert not any(value in serialized for value in forbidden)


def test_procedure_dependency_contract_exposes_resolution_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")
    client = TestClient(app)

    response = client.post(
        "/tools/get_procedure_dependencies/invoke",
        json={
            "arguments": {
                "dbProfileId": "master",
                "schema": "dbo",
                "procedureName": "usp_GetOrderSummary",
            }
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["data"]["dependencies"]
    for dependency in payload["data"]["dependencies"]:
        assert {
            "objectType",
            "database",
            "server",
            "schema",
            "name",
            "referencedDatabase",
            "referencedServer",
            "sourceScope",
            "dependencyType",
            "isAmbiguous",
            "reviewStatus",
            "resolutionStatus",
            "resolutionStrategy",
            "evidenceRefs",
        } <= set(dependency)
        assert dependency["reviewStatus"] in {"CONFIRMED", "REVIEW_REQUIRED"}
        assert dependency["resolutionStatus"] in {"CONFIRMED", "REVIEW_REQUIRED"}
        assert dependency["evidenceRefs"]

    serialized = response.text.lower()
    forbidden = ("create procedure", "rowdata", "row_data", "connectionstring", "password")
    assert not any(value in serialized for value in forbidden)


def test_tool_error_response_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")
    client = TestClient(app)

    response = client.post(
        "/tools/get_table_schema/invoke",
        json={"arguments": {"dbProfileId": "master", "schema": "dbo", "tableName": "NOPE"}},
    )

    assert response.status_code == 404
    payload = response.json()
    assert payload["ok"] is False
    assert payload["toolName"] == "get_table_schema"
    assert payload["dbProfileId"] == "master"
    assert payload["collectedAt"]
    assert payload["error"]["code"] == "OBJECT_NOT_FOUND"
    assert "data" not in payload
