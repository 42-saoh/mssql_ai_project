from __future__ import annotations

import pytest

import api_app.metadata_service as metadata_service
from api_app.metadata_service import (
    METADATA_SEARCH_MCP_TOOL_MISSING,
    PPM_MANIFEST_TEMPLATE_ONLY,
    MetadataSearchDependencyError,
    metadata_search_repository,
    normalize_metadata_search_limit,
    normalize_metadata_search_object_types,
    search_metadata_objects,
)
from mssql_mcp_app.profiles import DbProfile
from mssql_mcp_app.repositories import FixtureMetadataRepository, LiveMetadataRepository
from mssql_mcp_app.settings import LiveMetadataSettings


def _live_metadata_settings(*, enabled: bool) -> LiveMetadataSettings:
    return LiveMetadataSettings(
        live_metadata_enabled=enabled,
        metadata_host="127.0.0.1",
        metadata_port=1433,
        metadata_user="readonly_metadata_user",
        metadata_password="",
        metadata_db_fallback="master",
        default_profile_id="master",
        profile_file="config/mssql/local_docker_profiles.yaml",
        connect_timeout_seconds=5,
    )


def _metadata_profiles() -> list[DbProfile]:
    return [
        DbProfile(
            id="master",
            label="Server metadata (master)",
            database="master",
            purpose="server",
        )
    ]


def test_metadata_search_returns_read_only_fixture_identities() -> None:
    response = search_metadata_objects(
        db_profile_id="master",
        query="order",
        object_types=("PROCEDURE", "TABLE"),
        limit=5,
    )
    payload = response.to_response()

    assert payload["dbProfileId"] == "master"
    assert payload["sourceDatabase"] == "master"
    assert payload["results"]
    assert {item["objectIdentity"]["type"] for item in payload["results"]} <= {
        "PROCEDURE",
        "TABLE",
    }
    assert all(item["sourceProfile"] == "master" for item in payload["results"])
    assert all(item["sourceDatabase"] == "master" for item in payload["results"])
    assert all(item["evidenceRefs"] for item in payload["results"])

    serialized = str(payload).lower()
    for forbidden in ("rowdata", "row_data", "definition", "sqltext", "ddl", "dml"):
        assert forbidden not in serialized


def test_metadata_search_repository_boundary_selects_live_adapter_when_enabled() -> None:
    profiles = _metadata_profiles()

    fixture_repository = metadata_search_repository(
        _live_metadata_settings(enabled=False),
        profiles,
    )
    live_repository = metadata_search_repository(
        _live_metadata_settings(enabled=True),
        profiles,
    )

    assert isinstance(fixture_repository, FixtureMetadataRepository)
    assert isinstance(live_repository, LiveMetadataRepository)


def test_metadata_search_rejects_invalid_object_type_and_normalizes_limit() -> None:
    assert normalize_metadata_search_limit(500) == 100
    assert normalize_metadata_search_limit(0) == 1
    assert normalize_metadata_search_object_types(()) == (
        "PROCEDURE",
        "TABLE",
        "VIEW",
        "FUNCTION",
    )

    with pytest.raises(ValueError, match="Unsupported metadata objectTypes"):
        normalize_metadata_search_object_types(("TRIGGER",))

    with pytest.raises(ValueError, match="must not be blank"):
        search_metadata_objects(db_profile_id="master", query="   ")


def test_ppm_metadata_search_uses_ppm_without_plf_fallback() -> None:
    response = search_metadata_objects(
        db_profile_id="ppm",
        query="order",
        object_types=("PROCEDURE", "TABLE"),
        limit=5,
    )
    payload = response.to_response()

    assert payload["sourceProfile"] == "ppm"
    assert payload["sourceDatabase"] == "PPM"
    assert payload["sourceDatabase"] != "PLF"
    assert payload["results"]
    assert all(item["sourceProfile"] == "ppm" for item in payload["results"])
    assert all(item["sourceDatabase"] == "PPM" for item in payload["results"])


def test_ppm_template_only_manifest_returns_no_real_object_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(metadata_service, "ppm_manifest_selection_mode", lambda: "template_only")

    response = search_metadata_objects(
        db_profile_id="ppm",
        query="order",
        object_types=("PROCEDURE", "TABLE"),
        limit=5,
    )
    payload = response.to_response()

    assert payload["results"] == []
    assert payload["reviewRequired"] is True
    assert payload["blockers"][0]["code"] == PPM_MANIFEST_TEMPLATE_ONLY
    assert "TB_ORDER" not in str(payload)
    assert "usp_GetOrderSummary" not in str(payload)


def test_missing_mcp_inventory_capability_returns_search_blocker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        metadata_service,
        "METADATA_SEARCH_TOOLS",
        {"TABLE": ("missing_metadata_search_tool", "tables")},
    )

    with pytest.raises(MetadataSearchDependencyError) as exc_info:
        search_metadata_objects(
            db_profile_id="master",
            query="order",
            object_types=("TABLE",),
            limit=5,
        )

    assert exc_info.value.code == METADATA_SEARCH_MCP_TOOL_MISSING
