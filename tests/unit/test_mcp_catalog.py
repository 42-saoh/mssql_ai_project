from fastapi.testclient import TestClient

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
