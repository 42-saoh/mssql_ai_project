from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from api_app.schemas import MetadataProfile, MetadataToolSummary


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def list_safe_metadata_profiles() -> tuple[str, list[MetadataProfile]]:
    try:
        from mssql_mcp_app.profiles import get_default_profile, load_db_profiles
        from mssql_mcp_app.settings import load_live_metadata_settings

        settings = load_live_metadata_settings()
        profiles = load_db_profiles(settings, repo_root=repo_root())
        default_profile = get_default_profile(profiles)
        return default_profile.id, [
            MetadataProfile(
                id=profile.id,
                database=profile.database,
                description=f"{profile.label} ({profile.purpose})",
                readOnly=True,
            )
            for profile in profiles
        ]
    except ModuleNotFoundError:
        return _profiles_from_yaml()


def list_safe_metadata_tools() -> list[MetadataToolSummary]:
    try:
        from mssql_mcp_app.catalog import load_tool_catalog

        tools = load_tool_catalog()
        return [
            MetadataToolSummary(
                name=tool.name,
                description=tool.description,
                readOnly=True,
            )
            for tool in tools
            if tool.active and tool.read_only
        ]
    except ModuleNotFoundError:
        return _tools_from_yaml()


def _profiles_from_yaml() -> tuple[str, list[MetadataProfile]]:
    path = repo_root() / "config" / "mssql" / "local_docker_profiles.yaml"
    payload: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    default_profile_id = str(payload.get("defaultProfileId", "plf"))
    profiles = [
        MetadataProfile(
            id=str(item["id"]),
            database=str(item["database"]),
            description=f"{item.get('label', item['id'])} ({item.get('purpose', 'metadata')})",
            readOnly=True,
        )
        for item in payload.get("profiles", [])
    ]
    return default_profile_id, profiles


def _tools_from_yaml() -> list[MetadataToolSummary]:
    path = repo_root() / "spec" / "mcp" / "mssql_metadata_tool_catalog.yaml"
    payload: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [
        MetadataToolSummary(
            name=str(item["name"]),
            description=str(item.get("description", "")),
            readOnly=True,
        )
        for item in payload.get("tools", [])
        if item.get("active", True) and item.get("readOnly", payload.get("readOnly")) is True
    ]
