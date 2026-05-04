from __future__ import annotations

from api_app.metadata_service import list_safe_metadata_profiles, list_safe_metadata_tools


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
    assert "get_table_schema" in {tool["name"] for tool in tools}
    assert not any("input" in tool for tool in tools)
