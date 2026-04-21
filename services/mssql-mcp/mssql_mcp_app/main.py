from fastapi import FastAPI

from mssql_mcp_app.catalog import TOOL_CATALOG

app = FastAPI(
    title="MSSQL Metadata MCP Starter",
    version="0.1.0",
    description="Starter read-only metadata service for MSSQL agent platform.",
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "mssql-mcp", "mode": "read-only"}


@app.get("/catalog/tools")
def list_tools() -> dict[str, list[dict[str, str | bool]]]:
    return {
        "tools": [
            {
                "name": item.name,
                "description": item.description,
                "readOnly": item.read_only,
            }
            for item in TOOL_CATALOG
        ]
    }
