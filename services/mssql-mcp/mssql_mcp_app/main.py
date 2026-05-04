from __future__ import annotations

from typing import Any

from fastapi import Body, FastAPI, Response

from mssql_mcp_app.catalog import TOOL_CATALOG
from mssql_mcp_app.errors import MetadataToolError
from mssql_mcp_app.live_connection import MetadataConnectionError, probe_profile_connection
from mssql_mcp_app.profiles import get_default_profile, load_db_profiles
from mssql_mcp_app.registry import build_tool_registry, error_response
from mssql_mcp_app.repositories import FixtureMetadataRepository, LiveMetadataRepository
from mssql_mcp_app.settings import load_live_metadata_settings

app = FastAPI(
    title="MSSQL Metadata MCP Starter",
    version="0.1.0",
    description="Starter read-only metadata service for MSSQL agent platform.",
)


@app.get("/health")
def health() -> dict[str, Any]:
    settings = load_live_metadata_settings()
    profiles = load_db_profiles(settings)
    default_profile = get_default_profile(profiles)
    return {
        "status": "ok",
        "service": "mssql-mcp",
        "mode": "read-only",
        "liveMetadataEnabled": settings.live_metadata_enabled,
        "defaultProfileId": default_profile.id,
    }


@app.get("/health/ready")
def ready(response: Response) -> dict[str, Any]:
    settings = load_live_metadata_settings()
    profiles = load_db_profiles(settings)
    default_profile = get_default_profile(profiles)

    if not settings.live_metadata_enabled:
        return {
            "status": "ok",
            "service": "mssql-mcp",
            "mode": "read-only",
            "liveMetadataEnabled": False,
            "connection": "skipped",
            "profileId": default_profile.id,
            "database": default_profile.database,
        }

    try:
        probe = probe_profile_connection(default_profile, settings)
    except MetadataConnectionError as exc:
        response.status_code = 503
        return {
            "status": "not-ready",
            "service": "mssql-mcp",
            "mode": "read-only",
            "liveMetadataEnabled": True,
            "profileId": default_profile.id,
            "database": default_profile.database,
            "error": str(exc),
        }

    return {
        "status": "ok",
        "service": "mssql-mcp",
        "mode": "read-only",
        "liveMetadataEnabled": True,
        **probe,
    }


@app.get("/config/db-profiles")
def list_db_profiles() -> dict[str, Any]:
    settings = load_live_metadata_settings()
    profiles = load_db_profiles(settings)
    default_profile = get_default_profile(profiles)
    return {
        "defaultProfileId": default_profile.id,
        "profiles": [profile.to_public_dict() for profile in profiles],
    }


@app.get("/catalog/tools")
def list_tools() -> dict[str, list[dict[str, Any]]]:
    return {
        "tools": [
            {
                "name": item.name,
                "description": item.description,
                "readOnly": item.read_only,
                "active": item.active,
                "input": item.input_schema,
            }
            for item in TOOL_CATALOG
        ]
    }


@app.post("/tools/{tool_name}/invoke")
def invoke_tool(
    tool_name: str,
    response: Response,
    payload: dict[str, Any] | None = Body(default=None),
) -> dict[str, Any]:
    settings = load_live_metadata_settings()
    profiles = load_db_profiles(settings)
    repository = (
        LiveMetadataRepository()
        if settings.live_metadata_enabled
        else FixtureMetadataRepository()
    )
    registry = build_tool_registry(repository=repository, profiles=profiles)
    arguments = payload.get("arguments") if isinstance(payload, dict) else None

    try:
        return registry.invoke_payload(tool_name, payload)
    except MetadataToolError as exc:
        response.status_code = exc.http_status
        return error_response(tool_name, exc, arguments=arguments)
