from __future__ import annotations

import api_app.metadata_gateway as metadata_gateway
import api_app.metadata_service as metadata_service
import pytest
from api_app.live_gate import P21_LIVE_PPM_REQUIRED
from api_app.metadata_gateway import McpMetadataGateway, P21LivePortalPrerequisiteError
from mssql_mcp_app.errors import PPM_DB_ACCESS_DENIED, MetadataToolError
from mssql_mcp_app.profiles import DbProfile


def test_mcp_metadata_gateway_collects_fixture_metadata_through_registry(
    monkeypatch,
) -> None:
    monkeypatch.setenv("P21_LIVE_PORTAL_GATE", "0")
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")

    metadata = McpMetadataGateway().collect_procedure_metadata(
        db_profile_id="master",
        schema="dbo",
        procedure_name="usp_GetOrderSummary",
    )

    assert metadata.status == "COLLECTED"
    assert metadata.snapshot_id == "mcp-fixture-snapshot-0001"
    assert metadata.primary_table is not None
    assert metadata.primary_table["tableName"] == "TB_ORDER"
    assert metadata.procedure_parameters is not None
    assert metadata.procedure_parameters["parameters"][0]["name"] == "@OrderId"
    assert metadata.dependency_evidence is not None
    assert metadata.dependency_evidence["toolName"] == "get_dependency_closure"
    assert metadata.dependency_evidence["summary"]["reviewRequiredCount"] >= 1
    assert metadata.dependency_evidence["unresolved"]
    assert metadata.evidence_refs


def test_mcp_metadata_gateway_uses_closure_without_auto_resolver(monkeypatch) -> None:
    monkeypatch.setenv("P21_LIVE_PORTAL_GATE", "0")
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")
    calls: list[str] = []

    class SpyRegistry:
        def invoke_payload(self, tool_name: str, payload: dict) -> dict:
            calls.append(tool_name)
            arguments = payload["arguments"]
            base = {
                "ok": True,
                "toolName": tool_name,
                "dbProfileId": arguments["dbProfileId"],
                "snapshotId": "fixture:spy",
                "collectedAt": "2026-05-12T00:00:00Z",
                "evidenceRefs": [
                    {
                        "objectName": "dbo.usp_Spy",
                        "path": f"fixtures/mcp/metadata_snapshot.json#/{tool_name}",
                    }
                ],
            }
            if tool_name == "get_dependency_closure":
                return {
                    **base,
                    "data": {
                        "rootObject": {
                            "database": "master",
                            "schema": arguments["schema"],
                            "name": arguments["objectName"],
                            "objectType": arguments["objectType"],
                        },
                        "nodes": [],
                        "edges": [],
                        "unresolved": [
                            {
                                "objectType": "UNKNOWN",
                                "schema": None,
                                "name": None,
                                "dependencyType": "DYNAMIC_SQL",
                                "reviewStatus": "REVIEW_REQUIRED",
                                "resolutionStatus": "REVIEW_REQUIRED",
                                "resolutionStrategy": "DYNAMIC_SQL_PATTERN",
                                "evidenceRefs": [
                                    {
                                        "objectName": "unresolved",
                                        "path": "fixtures/mcp/metadata_snapshot.json#/spy",
                                    }
                                ],
                            }
                        ],
                        "summary": {
                            "maxDepth": arguments["maxDepth"],
                            "nodeCount": 1,
                            "edgeCount": 0,
                            "reviewRequiredCount": 1,
                        },
                        "caveats": ["DEPENDENCY_METADATA_INCOMPLETE"],
                        "reviewRequired": True,
                    },
                }
            data_by_tool = {
                "get_procedure_definition": {
                    "schema": arguments["schema"],
                    "procedureName": arguments["procedureName"],
                    "definition": None,
                    "definitionHash": "hash",
                    "definitionLength": 0,
                    "detectedPatterns": [],
                    "isEncrypted": False,
                    "hasDefinitionAccess": False,
                    "caveats": ["definition_unavailable"],
                    "reviewRequired": True,
                },
                "get_procedure_parameters": {
                    "schema": arguments["schema"],
                    "procedureName": arguments["procedureName"],
                    "parameters": [],
                },
                "get_procedure_dependencies": {
                    "schema": arguments["schema"],
                    "procedureName": arguments["procedureName"],
                    "dependencies": [],
                    "dependencySummary": {},
                    "caveats": [],
                    "reviewRequired": False,
                },
                "get_dependency_closure": {
                    "rootObject": {},
                    "nodes": [],
                    "edges": [],
                    "unresolved": [],
                    "summary": {},
                },
            }
            return {**base, "data": data_by_tool[tool_name]}

    monkeypatch.setattr(
        metadata_gateway,
        "build_tool_registry",
        lambda **_kwargs: SpyRegistry(),
    )

    metadata = McpMetadataGateway().collect_procedure_metadata(
        db_profile_id="master",
        schema="dbo",
        procedure_name="usp_Spy",
    )

    assert calls == [
        "get_procedure_definition",
        "get_procedure_parameters",
        "get_procedure_dependencies",
        "get_dependency_closure",
    ]
    assert "resolve_dependency_reference" not in calls
    assert metadata.dependency_evidence is not None
    assert metadata.dependency_evidence["unresolved"][0]["resolutionStatus"] == "REVIEW_REQUIRED"


def test_mcp_metadata_gateway_returns_review_required_fallback_for_missing_fixture(
    monkeypatch,
) -> None:
    monkeypatch.setenv("P21_LIVE_PORTAL_GATE", "0")
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")

    metadata = McpMetadataGateway().collect_procedure_metadata(
        db_profile_id="master",
        schema="dbo",
        procedure_name="usp_NotInFixture",
    )

    assert metadata.status == "REVIEW_REQUIRED"
    assert metadata.snapshot_id is None
    assert metadata.errors
    assert metadata.evidence_refs == (
        {
            "type": "USER_INPUT",
            "objectRef": "dbo.usp_NotInFixture",
            "locator": "request.target",
        },
    )


def test_p21_live_gate_blocks_fixture_metadata_gateway_fallback(monkeypatch) -> None:
    monkeypatch.setenv("P21_LIVE_PORTAL_GATE", "1")
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")

    with pytest.raises(P21LivePortalPrerequisiteError) as exc_info:
        McpMetadataGateway().collect_procedure_metadata(
            db_profile_id="ppm",
            schema="dbo",
            procedure_name="usp_GetOrderSummary",
        )

    assert exc_info.value.code == "P21_LIVE_PPM_REQUIRED"


def test_p21_live_gateway_rejects_ppm_profile_not_mapped_to_ppm(monkeypatch) -> None:
    monkeypatch.setenv("P21_LIVE_PORTAL_GATE", "1")
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "1")
    monkeypatch.setattr(metadata_service, "ppm_manifest_selection_mode", lambda: "live_metadata")
    monkeypatch.setattr(
        metadata_service,
        "load_db_profiles",
        lambda _settings, *, repo_root: [
            DbProfile(
                id="ppm",
                label="Misconfigured PPM",
                database="PLF",
                purpose="pilot-analysis-target",
            )
        ],
    )

    with pytest.raises(P21LivePortalPrerequisiteError) as exc_info:
        McpMetadataGateway().collect_procedure_metadata(
            db_profile_id="ppm",
            schema="dbo",
            procedure_name="usp_GetOrderSummary",
        )

    assert exc_info.value.code == P21_LIVE_PPM_REQUIRED


def test_ppm_template_only_blocks_workflow_metadata_without_plf_fallback(monkeypatch) -> None:
    monkeypatch.setenv("P21_LIVE_PORTAL_GATE", "0")
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")
    monkeypatch.setattr(metadata_service, "ppm_manifest_selection_mode", lambda: "template_only")

    with pytest.raises(P21LivePortalPrerequisiteError) as exc_info:
        McpMetadataGateway().collect_procedure_metadata(
            db_profile_id="ppm",
            schema="dbo",
            procedure_name="usp_GetOrderSummary",
        )

    assert exc_info.value.code == "PPM_MANIFEST_TEMPLATE_ONLY"
    assert "PLF" not in str(exc_info.value)


def test_p21_live_gateway_required_procedure_metadata_failure_preserves_code(
    monkeypatch,
) -> None:
    class DeniedRegistry:
        def invoke_payload(self, _tool_name: str, _payload: dict) -> dict:
            raise MetadataToolError(
                PPM_DB_ACCESS_DENIED,
                "Live metadata connection could not be established.",
                {"dbProfileId": "ppm", "database": "PPM"},
            )

    monkeypatch.setenv("P21_LIVE_PORTAL_GATE", "1")
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "1")
    monkeypatch.setattr(metadata_service, "ppm_manifest_selection_mode", lambda: "live_metadata")
    monkeypatch.setattr(
        metadata_gateway,
        "build_tool_registry",
        lambda **_kwargs: DeniedRegistry(),
    )

    with pytest.raises(P21LivePortalPrerequisiteError) as exc_info:
        McpMetadataGateway().collect_procedure_metadata(
            db_profile_id="ppm",
            schema="dbo",
            procedure_name="usp_GetOrderSummary",
        )

    assert exc_info.value.code == PPM_DB_ACCESS_DENIED


def test_p21_live_gateway_allows_optional_table_metadata_review_required(
    monkeypatch,
) -> None:
    class OptionalTableFailureRegistry:
        def invoke_payload(self, tool_name: str, payload: dict) -> dict:
            arguments = payload["arguments"]
            if tool_name == "get_table_schema":
                raise MetadataToolError(
                    "OBJECT_NOT_FOUND",
                    "Requested metadata object was not found.",
                    {"objectType": "TABLE"},
                )
            if tool_name == "get_dependency_closure":
                return {
                    "snapshotId": "live:ppm:test",
                    "collectedAt": "2026-05-10T00:00:00Z",
                    "evidenceRefs": [
                        {
                            "objectName": "dbo.usp_GetOrderSummary",
                            "path": "sys.objects",
                        }
                    ],
                    "data": {
                        "rootObject": {
                            "database": "PPM",
                            "schema": arguments["schema"],
                            "name": arguments["objectName"],
                            "objectType": arguments["objectType"],
                        },
                        "nodes": [],
                        "edges": [],
                        "unresolved": [],
                        "summary": {
                            "maxDepth": arguments["maxDepth"],
                            "nodeCount": 1,
                            "edgeCount": 0,
                            "reviewRequiredCount": 0,
                        },
                        "caveats": [],
                        "reviewRequired": False,
                    },
                }
            data_by_tool = {
                "get_procedure_definition": {
                    "schema": arguments["schema"],
                    "procedureName": arguments["procedureName"],
                    "definition": None,
                    "definitionHash": "hash",
                    "definitionLength": 10,
                    "detectedPatterns": [],
                    "isEncrypted": False,
                    "hasDefinitionAccess": True,
                    "caveats": [],
                    "reviewRequired": False,
                },
                "get_procedure_parameters": {
                    "schema": arguments["schema"],
                    "procedureName": arguments["procedureName"],
                    "parameters": [],
                },
                "get_procedure_dependencies": {
                    "schema": arguments["schema"],
                    "procedureName": arguments["procedureName"],
                    "dependencies": [
                        {
                            "objectType": "TABLE",
                            "schema": "dbo",
                            "name": "MissingTable",
                        }
                    ],
                    "dependencySummary": {},
                    "caveats": [],
                    "reviewRequired": False,
                },
                "get_dependency_closure": {
                    "rootObject": {},
                    "nodes": [],
                    "edges": [],
                    "unresolved": [],
                    "summary": {},
                },
            }
            return {
                "snapshotId": "live:ppm:test",
                "collectedAt": "2026-05-10T00:00:00Z",
                "evidenceRefs": [
                    {
                        "objectName": "dbo.usp_GetOrderSummary",
                        "path": "sys.objects",
                    }
                ],
                "data": data_by_tool[tool_name],
            }

    monkeypatch.setenv("P21_LIVE_PORTAL_GATE", "1")
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "1")
    monkeypatch.setattr(metadata_service, "ppm_manifest_selection_mode", lambda: "live_metadata")
    monkeypatch.setattr(
        metadata_gateway,
        "build_tool_registry",
        lambda **_kwargs: OptionalTableFailureRegistry(),
    )

    metadata = McpMetadataGateway().collect_procedure_metadata(
        db_profile_id="ppm",
        schema="dbo",
        procedure_name="usp_GetOrderSummary",
    )

    assert metadata.status == "REVIEW_REQUIRED"
    assert metadata.snapshot_id == "live:ppm:test"
    assert metadata.table_schemas == ()
    assert metadata.errors[0]["toolName"] == "get_table_schema"
