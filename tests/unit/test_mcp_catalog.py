import yaml
from fastapi.testclient import TestClient
from mssql_mcp_app.catalog import TOOL_CATALOG
from mssql_mcp_app.main import app

PLANNED_P27_TOOLS = {
    "get_dependency_closure",
    "resolve_dependency_reference",
}


def test_mcp_health_and_catalog() -> None:
    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["mode"] == "read-only"

    catalog = client.get("/catalog/tools")
    assert catalog.status_code == 200
    names = {tool["name"] for tool in catalog.json()["tools"]}
    assert "check_database_exists" in names
    assert "list_procedures" in names
    assert "list_tables" in names
    assert "list_views" in names
    assert "list_functions" in names
    assert "search_metadata_objects" in names
    assert "get_procedure_definition" in names
    assert "get_dependency_closure" in names
    assert "resolve_dependency_reference" in names
    assert "find_similar_tables" in names
    for tool in catalog.json()["tools"]:
        assert tool["readOnly"] is True
        assert isinstance(tool["active"], bool)
        assert "input" in tool
        assert "password" not in tool
        assert "connectionString" not in tool
    planned_tools = {
        tool["name"]: tool
        for tool in catalog.json()["tools"]
        if tool["name"] in PLANNED_P27_TOOLS
    }
    assert set(planned_tools) == PLANNED_P27_TOOLS
    assert all(tool["active"] is False for tool in planned_tools.values())


def test_mcp_yaml_catalog_matches_service_catalog() -> None:
    catalog_path = "spec/mcp/mssql_metadata_tool_catalog.yaml"
    with open(catalog_path, encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)

    yaml_names = [tool["name"] for tool in payload["tools"]]
    service_names = [tool.name for tool in TOOL_CATALOG]

    assert payload["service"] == "mssqlMetadata"
    assert payload["readOnly"] is True
    assert payload["errorCodes"] == [
        "UNKNOWN_TOOL",
        "INVALID_ARGUMENTS",
        "PROFILE_NOT_FOUND",
        "OBJECT_NOT_FOUND",
        "READ_ONLY_VIOLATION",
        "LIVE_METADATA_UNAVAILABLE",
        "PPM_DB_NOT_FOUND",
        "PPM_DB_ACCESS_DENIED",
        "METADATA_READ_ONLY_PERMISSION_INSUFFICIENT",
        "SP_DEFINITION_ACCESS_DENIED",
        "DEPENDENCY_METADATA_INCOMPLETE",
        "INTERNAL_ERROR",
    ]
    assert yaml_names == service_names


def test_mcp_yaml_catalog_declares_active_read_only_tools() -> None:
    catalog_path = "spec/mcp/mssql_metadata_tool_catalog.yaml"
    with open(catalog_path, encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)

    assert payload["response"]["success"]["required"] == [
        "ok",
        "toolName",
        "dbProfileId",
        "snapshotId",
        "collectedAt",
        "evidenceRefs",
        "data",
    ]
    assert payload["response"]["standardData"]["required"] == [
        "sourceProfile",
        "sourceDatabase",
        "objectIdentity",
        "caveats",
        "reviewRequired",
    ]
    assert "SQL text" in payload["response"]["error"]["properties"]["error"]["properties"][
        "details"
    ]["description"]
    search_tool = next(
        tool for tool in payload["tools"] if tool["name"] == "search_metadata_objects"
    )
    assert search_tool["input"]["required"] == ["dbProfileId", "query"]
    assert search_tool["input"]["properties"]["objectTypes"]["items"]["enum"] == [
        "PROCEDURE",
        "TABLE",
        "VIEW",
        "FUNCTION",
    ]
    dependency_item = payload["response"]["dependencyItem"]
    assert dependency_item["required"] == [
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
    ]
    dependency_tool = next(
        tool for tool in payload["tools"] if tool["name"] == "get_procedure_dependencies"
    )
    assert dependency_tool["output"]["properties"]["dependencies"]["items"] == {
        "$ref": "#/response/dependencyItem"
    }
    assert {
        "resolutionConfidence",
        "resolutionEvidenceKind",
        "unresolvedReason",
        "resolutionChain",
    } <= set(dependency_item["properties"])
    planned_tools = {
        tool["name"]: tool
        for tool in payload["tools"]
        if tool["name"] in PLANNED_P27_TOOLS
    }
    assert set(planned_tools) == PLANNED_P27_TOOLS
    for tool in planned_tools.values():
        assert tool["active"] is False
        assert tool["readOnly"] is True
        assert tool["designStatus"] == "planned_p27_design_only"
    for tool in payload["tools"]:
        assert tool["readOnly"] is True
