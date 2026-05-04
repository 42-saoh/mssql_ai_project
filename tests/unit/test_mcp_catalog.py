import yaml
from fastapi.testclient import TestClient

from mssql_mcp_app.catalog import TOOL_CATALOG
from mssql_mcp_app.main import app


def test_mcp_health_and_catalog() -> None:
    client = TestClient(app)

    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["mode"] == "read-only"

    catalog = client.get("/catalog/tools")
    assert catalog.status_code == 200
    names = {tool["name"] for tool in catalog.json()["tools"]}
    assert "get_procedure_definition" in names
    assert "find_similar_tables" in names


def test_mcp_yaml_catalog_matches_service_catalog() -> None:
    catalog_path = "spec/mcp/mssql_metadata_tool_catalog.yaml"
    with open(catalog_path, encoding="utf-8") as handle:
        payload = yaml.safe_load(handle)

    yaml_names = [tool["name"] for tool in payload["tools"]]
    service_names = [tool.name for tool in TOOL_CATALOG]

    assert payload["service"] == "mssqlMetadata"
    assert payload["readOnly"] is True
    assert yaml_names == service_names
