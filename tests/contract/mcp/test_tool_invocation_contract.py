from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml
from fastapi.testclient import TestClient
from mssql_mcp_app.main import app

REPO_ROOT = Path(__file__).resolve().parents[3]

P27_DEPENDENCY_TOOL_NAMES = {
    "get_dependency_closure",
    "resolve_dependency_reference",
}
P27_DEFAULT_VERIFY = (
    'make test PYTEST_ARGS="tests/unit/test_mcp_catalog.py '
    "tests/unit/mcp/test_tool_registry.py "
    "tests/contract/mcp/test_tool_invocation_contract.py "
    "tests/contract/test_p27_dependency_evidence_tooling_prompt_assets.py "
    "tests/unit/api/test_metadata_service.py "
    "tests/unit/api/test_metadata_gateway.py "
    "tests/unit/api/test_workflow_service.py "
    "tests/unit/api/test_route_surface.py "
    "tests/unit/web/test_p14_product_ui_static.py "
    "tests/integration/api/test_api_workflow_routes.py "
    "tests/e2e/test_fixture_workflow_happy_path.py "
    'tests/contract/test_openapi_and_env_sample_assets.py"'
)
P27_HARD_LIVE_VERIFY = (
    "P27_HARD_LIVE_GATE=1 MSSQL_ENABLE_LIVE_METADATA=1 make test "
    'PYTEST_ARGS="tests/eval/test_p27_dependency_evidence_hard_live_gate.py"'
)

P27_OPTIONAL_RESOLUTION_FIELDS = {
    "resolutionConfidence",
    "resolutionEvidenceKind",
    "unresolvedReason",
    "resolutionChain",
}

FORBIDDEN_DEPENDENCY_INPUT_FIELDS = {
    "query",
    "sql",
    "rawSql",
    "statement",
    "whereClause",
    "definition",
    "procedureDefinition",
    "rowData",
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
    "get_dependency_closure": {
        "dbProfileId": "master",
        "schema": "dbo",
        "objectName": "usp_GetOrderSummary",
        "objectType": "PROCEDURE",
        "maxDepth": 2,
        "includeReviewRequired": True,
    },
    "resolve_dependency_reference": {
        "dbProfileId": "master",
        "sourceObject": {
            "schema": "dbo",
            "name": "usp_GetOrderSummary",
            "objectType": "PROCEDURE",
        },
        "referencedSchema": "dbo",
        "referencedName": "TB_ORDER",
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


def _schema_property_names(schema: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    properties = schema.get("properties", {})
    if isinstance(properties, dict):
        names.update(properties)
        for child in properties.values():
            if isinstance(child, dict):
                names.update(_schema_property_names(child))
    items = schema.get("items")
    if isinstance(items, dict):
        names.update(_schema_property_names(items))
    return names


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
    assert active_tool_names == set(TOOL_INVOCATIONS)
    assert all(tool["readOnly"] is True for tool in payload["tools"])


def test_p27_dependency_evidence_tools_are_active_read_only_contract_tools() -> None:
    payload = yaml.safe_load(
        (REPO_ROOT / "spec" / "mcp" / "mssql_metadata_tool_catalog.yaml").read_text(
            encoding="utf-8"
        )
    )
    tools = {tool["name"]: tool for tool in payload["tools"]}
    for tool_name in P27_DEPENDENCY_TOOL_NAMES:
        tool = tools[tool_name]
        assert tool["active"] is True
        assert tool["readOnly"] is True
        assert tool["implementationStatus"] == "fixture_first_hardened_with_explicit_live_gate"
        assert tool["input"]["type"] == "object"
        input_fields = _schema_property_names(tool["input"])
        assert not FORBIDDEN_DEPENDENCY_INPUT_FIELDS.intersection(input_fields)
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
    assert P27_OPTIONAL_RESOLUTION_FIELDS <= set(edge_item["properties"])
    assert not P27_OPTIONAL_RESOLUTION_FIELDS.intersection(edge_item["required"])

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
    assert P27_OPTIONAL_RESOLUTION_FIELDS <= set(resolver_tool["output"]["properties"])
    assert not P27_OPTIONAL_RESOLUTION_FIELDS.intersection(resolver_tool["output"]["required"])

    dependency_item = payload["response"]["dependencyItem"]
    assert P27_OPTIONAL_RESOLUTION_FIELDS <= set(dependency_item["properties"])
    assert not P27_OPTIONAL_RESOLUTION_FIELDS.intersection(dependency_item["required"])


def test_p27_dependency_closure_excludes_review_required_edges_when_requested(
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
                "maxDepth": 2,
                "includeReviewRequired": False,
            }
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    data = payload["data"]
    assert data["unresolved"]
    assert data["reviewRequired"] is True
    assert all(edge["resolutionStatus"] == "CONFIRMED" for edge in data["edges"])
    assert all(node["reviewStatus"] == "CONFIRMED" for node in data["nodes"])


def test_p27_dependency_reference_resolver_selects_only_unique_confirmed_candidate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")
    client = TestClient(app)

    confirmed = client.post(
        "/tools/resolve_dependency_reference/invoke",
        json={
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
    review = client.post(
        "/tools/resolve_dependency_reference/invoke",
        json={
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

    assert confirmed.status_code == 200
    confirmed_data = confirmed.json()["data"]
    assert confirmed_data["resolutionStatus"] == "CONFIRMED"
    assert confirmed_data["selectedResolution"]["name"] == "TB_ORDER"
    assert confirmed_data["selectedResolution"]["resolutionConfidence"] == "HIGH"
    assert confirmed_data["reviewRequired"] is False

    assert review.status_code == 200
    review_data = review.json()["data"]
    assert review_data["resolutionStatus"] == "REVIEW_REQUIRED"
    assert review_data["selectedResolution"] is None
    assert review_data["reviewRequired"] is True


def test_p27_dependency_evidence_eval_contract_matches_mcp_catalog() -> None:
    contract = yaml.safe_load(
        (
            REPO_ROOT
            / "spec"
            / "eval"
            / "p27_dependency_evidence_tooling_contract.yaml"
        ).read_text(encoding="utf-8")
    )
    assert contract["contract_id"] == "p27_dependency_evidence_tooling@0.3.0"
    assert contract["status"] == "fixture_first_hardened_with_explicit_live_gate"
    assert contract["production_ready"] is False
    assert contract["scope"]["excluded"] == [
        "persisted artifact type changes",
        "default live metadata or OpenAI gate requirements",
        "DB schema changes",
    ]
    assert contract["api_invocation_route"]["path"] == (
        "/api/v1/metadata/tools/{toolName}/invoke"
    )
    assert contract["api_invocation_route"]["allowlisted_tools"] == [
        "get_dependency_closure",
        "resolve_dependency_reference",
    ]
    assert contract["api_invocation_route"]["excluded"] == [
        "input schema exposure through /api/v1/metadata/tools",
        "persisted artifact type changes",
        "DB schema changes",
    ]
    assert contract["web_diagnostic_ui"]["route"] == "/metadata/dependencies"
    assert contract["web_diagnostic_ui"]["status"] == "p29_fixture_first_enabled"
    assert contract["workflow_evidence_wiring"]["automatic_tool"] == [
        "get_dependency_closure",
    ]
    assert contract["workflow_evidence_wiring"]["manual_only_tools"] == [
        "resolve_dependency_reference",
    ]
    assert contract["p29b_deferred_boundary"] == {
        "status": "confirmed_deferred",
        "db_migration": "deferred",
        "persisted_artifact_type": "deferred",
        "workflow_state_transition": "deferred",
        "live_ppm_hard_gate": "explicit_env_only",
        "storage_shape": [
            "Existing metadata collection payload carries sanitized dependencyEvidence only.",
            "Existing draft artifacts reuse evidence refs and rendered dependency closure sections.",
            (
                "No raw definition, raw prompt, raw provider response, row data, "
                "SQL text, or secret is persisted."
            ),
        ],
        "workflow_shape": [
            (
                "Default workflow transitions remain COLLECTING_METADATA, ANALYZING, "
                "GENERATING, VALIDATING, VALIDATION_COMPLETE."
            ),
            (
                "resolve_dependency_reference remains manual-only through the Web "
                "diagnostic UI and P28 safe API route."
            ),
        ],
        "verification_boundary": [
            "Default verification remains fixture-first.",
            (
                "Hard-live PPM verification runs only with P27_HARD_LIVE_GATE=1 and "
                "MSSQL_ENABLE_LIVE_METADATA=1 plus live PPM prerequisites."
            ),
        ],
    }
    assert contract["invariants"]["read_only"] is True
    assert contract["invariants"]["structured_input_only"] is True
    assert contract["invariants"]["ppm_to_plf_fallback_allowed"] is False
    assert contract["invariants"]["row_data_allowed"] is False
    assert contract["invariants"]["procedure_execution_allowed"] is False
    assert contract["invariants"]["business_db_ddl_dml_allowed"] is False
    assert contract["implemented_tools"]["get_dependency_closure"]["active"] is True
    assert contract["implemented_tools"]["resolve_dependency_reference"]["active"] is True
    assert set(contract["implemented_tools"]) == P27_DEPENDENCY_TOOL_NAMES
    assert contract["dependency_resolution_contract"]["added_fields"] == [
        "resolutionConfidence",
        "resolutionEvidenceKind",
        "unresolvedReason",
        "resolutionChain",
    ]
    assert contract["verification"]["default"] == [
        P27_DEFAULT_VERIFY,
        "git diff --check",
    ]
    assert contract["verification"]["hard_live"] == [
        P27_HARD_LIVE_VERIFY,
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
