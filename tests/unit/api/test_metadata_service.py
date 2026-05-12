from __future__ import annotations

import pytest
from api_app.metadata_service import (
    MetadataSearchDependencyError,
    list_safe_metadata_profiles,
    list_safe_metadata_tools,
    search_metadata_objects,
)


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
    assert not any("input" in tool for tool in tools)


def test_p21_live_gate_requires_live_ppm_metadata(monkeypatch) -> None:
    monkeypatch.setenv("P21_LIVE_PORTAL_GATE", "1")
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")

    with pytest.raises(MetadataSearchDependencyError) as exc_info:
        search_metadata_objects(db_profile_id="ppm", query="order")

    assert exc_info.value.code == "P21_LIVE_PPM_REQUIRED"
