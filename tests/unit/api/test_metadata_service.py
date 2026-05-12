from __future__ import annotations

import pytest
from api_app.metadata_service import (
    METADATA_TOOL_INVOCATION_NOT_ALLOWED,
    PPM_MANIFEST_TEMPLATE_ONLY,
    MetadataSearchDependencyError,
    invoke_metadata_tool,
    list_safe_metadata_profiles,
    list_safe_metadata_tools,
    search_metadata_objects,
)


@pytest.fixture(autouse=True)
def fixture_metadata_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("P21_LIVE_PORTAL_GATE", "0")
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")


def test_metadata_profiles_return_public_fields_only(monkeypatch) -> None:
    monkeypatch.setenv("MSSQL_METADATA_PASSWORD", "do-not-return")

    default_profile_id, profiles = list_safe_metadata_profiles()
    payloads = [profile.to_response() for profile in profiles]

    assert default_profile_id
    assert payloads
    assert all(profile["readOnly"] is True for profile in payloads)
    assert all("database" in profile for profile in payloads)
    forbidden_keys = {"host", "port", "user", "password", "connectionString", "secret"}
    assert not any(forbidden_keys.intersection(profile) for profile in payloads)
    assert "do-not-return" not in str(payloads)


def test_metadata_tools_return_read_only_catalog_summary() -> None:
    tools = [tool.to_response() for tool in list_safe_metadata_tools()]

    assert tools
    assert all(tool["readOnly"] is True for tool in tools)
    names = {tool["name"] for tool in tools}
    assert "get_table_schema" in names
    assert "get_dependency_closure" in names
    assert "resolve_dependency_reference" in names
    invokable_by_name = {tool["name"]: tool["invokable"] for tool in tools}
    assert invokable_by_name["get_dependency_closure"] is True
    assert invokable_by_name["resolve_dependency_reference"] is True
    assert invokable_by_name["get_table_schema"] is False
    assert not any("input" in tool for tool in tools)


def test_metadata_tool_invocation_runs_public_p27_closure(monkeypatch) -> None:
    response = invoke_metadata_tool(
        tool_name="get_dependency_closure",
        arguments={
            "dbProfileId": "master",
            "schema": "dbo",
            "objectName": "usp_ProcessOrderBatch",
            "objectType": "PROCEDURE",
            "maxDepth": 2,
            "includeReviewRequired": False,
        },
    ).to_response()

    assert response["ok"] is True
    assert response["toolName"] == "get_dependency_closure"
    assert response["dbProfileId"] == "master"
    assert response["snapshotId"] == "mcp-fixture-snapshot-0001"
    assert response["evidenceRefs"]
    assert response["data"]["unresolved"]
    assert response["data"]["reviewRequired"] is True
    assert all(edge["resolutionStatus"] == "CONFIRMED" for edge in response["data"]["edges"])


def test_metadata_tool_invocation_rejects_non_public_tools(monkeypatch) -> None:
    with pytest.raises(MetadataSearchDependencyError) as exc_info:
        invoke_metadata_tool(
            tool_name="get_table_schema",
            arguments={
                "dbProfileId": "master",
                "schema": "dbo",
                "tableName": "TB_ORDER",
            },
        )

    assert exc_info.value.code == METADATA_TOOL_INVOCATION_NOT_ALLOWED
    assert exc_info.value.status_code == 403


def test_ppm_template_only_manifest_blocks_public_tool_invocation(monkeypatch) -> None:
    monkeypatch.setattr(
        "api_app.metadata_service.ppm_manifest_selection_mode",
        lambda: "template_only",
    )

    with pytest.raises(MetadataSearchDependencyError) as exc_info:
        invoke_metadata_tool(
            tool_name="get_dependency_closure",
            arguments={
                "dbProfileId": "ppm",
                "schema": "dbo",
                "objectName": "usp_ProcessOrderBatch",
                "objectType": "PROCEDURE",
            },
        )

    assert exc_info.value.code == PPM_MANIFEST_TEMPLATE_ONLY


def test_p21_live_gate_requires_live_ppm_metadata(monkeypatch) -> None:
    monkeypatch.setenv("P21_LIVE_PORTAL_GATE", "1")
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")

    with pytest.raises(MetadataSearchDependencyError) as exc_info:
        search_metadata_objects(db_profile_id="ppm", query="order")

    assert exc_info.value.code == "P21_LIVE_PPM_REQUIRED"
