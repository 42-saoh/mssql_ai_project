from __future__ import annotations

import api_app.metadata_gateway as metadata_gateway
import api_app.metadata_service as metadata_service
import pytest
from api_app.live_gate import P21_LIVE_PPM_REQUIRED
from api_app.metadata_gateway import McpMetadataGateway, P21LivePortalPrerequisiteError
from mssql_mcp_app.errors import PPM_DB_ACCESS_DENIED, MetadataToolError
from mssql_mcp_app.profiles import DbProfile


def test_mcp_metadata_gateway_collects_fixture_metadata_through_registry() -> None:
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
    assert metadata.evidence_refs


def test_mcp_metadata_gateway_returns_review_required_fallback_for_missing_fixture() -> None:
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
