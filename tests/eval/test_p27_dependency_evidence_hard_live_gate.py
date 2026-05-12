from __future__ import annotations

import os
import time
from pathlib import Path
from typing import Any

import pytest
import yaml
from mssql_mcp_app.errors import MetadataToolError
from mssql_mcp_app.profiles import DbProfile, load_db_profiles
from mssql_mcp_app.registry import build_tool_registry
from mssql_mcp_app.repositories import LiveMetadataRepository
from mssql_mcp_app.settings import load_live_metadata_settings

ROOT = Path(__file__).resolve().parents[2]
PILOT_MANIFEST = ROOT / "fixtures" / "pilot" / "ppm_object_selection_v1" / "selected_objects.yaml"
P27_LIVE_BLOCKER = "P27_LIVE_PPM_DEPENDENCY_EVIDENCE_REQUIRED"


def test_p27_hard_live_dependency_evidence_gate() -> None:
    if os.getenv("P27_HARD_LIVE_GATE", "").strip() != "1":
        pytest.skip(
            "P27 hard-live dependency evidence gate requires P27_HARD_LIVE_GATE=1. "
            "Default eval remains fixture-first and does not call live PPM."
        )

    manifest = _pilot_manifest()
    _require_live_manifest(manifest)

    settings = load_live_metadata_settings()
    if not settings.live_metadata_enabled:
        pytest.fail(
            f"{P27_LIVE_BLOCKER}: requires MSSQL_ENABLE_LIVE_METADATA=1 with "
            "read-only PPM metadata access."
        )
    missing_settings = [
        name
        for name, value in (
            ("MSSQL_METADATA_HOST", settings.metadata_host),
            ("MSSQL_METADATA_USER", settings.metadata_user),
            ("MSSQL_METADATA_PASSWORD", settings.metadata_password),
        )
        if not value
    ]
    if missing_settings:
        pytest.fail(
            f"{P27_LIVE_BLOCKER}: missing live metadata setting(s): "
            + ", ".join(missing_settings)
        )

    profiles = load_db_profiles(settings, repo_root=ROOT)
    ppm_profile = _profile_by_id(profiles, "ppm")
    if ppm_profile is None:
        pytest.fail(f"{P27_LIVE_BLOCKER}: metadata profile registry must include ppm.")
    if ppm_profile.database != "PPM":
        pytest.fail(f"{P27_LIVE_BLOCKER}: ppm profile must point to source database PPM.")

    registry = build_tool_registry(
        repository=LiveMetadataRepository(settings=settings, profiles=profiles),
        profiles=profiles,
    )

    for procedure in _selected_procedures(manifest):
        closure, _elapsed_ms = _invoke_live_metadata_tool(
            registry,
            "get_dependency_closure",
            {
                "dbProfileId": "ppm",
                "schema": procedure["schema"],
                "objectName": procedure["name"],
                "objectType": procedure["object_type"],
                "maxDepth": 1,
                "includeReviewRequired": True,
            },
        )
        _assert_safe_live_response(closure, "get_dependency_closure")
        assert closure["data"]["rootObject"]["name"] == procedure["name"]
        assert closure["data"]["summary"]["maxDepth"] == 1

        for dependency in _confirmed_dependencies(procedure):
            resolution, _elapsed_ms = _invoke_live_metadata_tool(
                registry,
                "resolve_dependency_reference",
                _resolver_arguments(procedure, dependency),
            )
            _assert_safe_live_response(resolution, "resolve_dependency_reference")
            data = resolution["data"]
            assert data["resolutionStatus"] == "CONFIRMED", dependency
            assert data["selectedResolution"] is not None, dependency
            assert data["selectedResolution"]["resolutionConfidence"] == "HIGH"
            assert data["selectedResolution"]["name"].lower() == dependency["name"].lower()
            assert data["reviewRequired"] is False

        for dependency in _residual_review_dependencies(procedure):
            resolution, _elapsed_ms = _invoke_live_metadata_tool(
                registry,
                "resolve_dependency_reference",
                _resolver_arguments(procedure, dependency),
            )
            _assert_safe_live_response(resolution, "resolve_dependency_reference")
            assert resolution["data"]["resolutionStatus"] == "REVIEW_REQUIRED"
            assert resolution["data"]["selectedResolution"] is None
            assert resolution["data"]["reviewRequired"] is True


def _invoke_live_metadata_tool(
    registry: Any,
    tool_name: str,
    arguments: dict[str, Any],
) -> tuple[dict[str, Any], float]:
    started = time.perf_counter()
    try:
        response = registry.invoke_payload(tool_name, {"arguments": arguments})
    except MetadataToolError as exc:
        pytest.fail(
            f"{exc.code}: {exc.message} "
            f"(tool={tool_name}, dbProfileId={arguments.get('dbProfileId')})"
        )
    return response, (time.perf_counter() - started) * 1000


def _assert_safe_live_response(response: dict[str, Any], tool_name: str) -> None:
    assert response["ok"] is True
    assert response["toolName"] == tool_name
    assert response["dbProfileId"] == "ppm"
    assert response["snapshotId"].startswith("live:ppm:")
    assert response["evidenceRefs"]
    assert response["data"]["sourceProfile"] == "ppm"
    assert response["data"]["sourceDatabase"] == "PPM"
    assert response["data"]["sourceDatabase"] != "PLF"
    assert _raw_definition_text_paths(response) == []
    assert _forbidden_payload_paths(response) == []
    assert "CREATE PROCEDURE" not in str(response).upper()


def _resolver_arguments(
    procedure: dict[str, Any],
    dependency: dict[str, Any],
) -> dict[str, Any]:
    arguments: dict[str, Any] = {
        "dbProfileId": "ppm",
        "sourceObject": {
            "schema": procedure["schema"],
            "name": procedure["name"],
            "objectType": procedure["object_type"],
        },
        "referencedName": dependency["name"],
    }
    if dependency.get("schema"):
        arguments["referencedSchema"] = dependency["schema"]
    if dependency.get("database"):
        arguments["referencedDatabase"] = dependency["database"]
    if dependency.get("server"):
        arguments["referencedServer"] = dependency["server"]
    return arguments


def _confirmed_dependencies(procedure: dict[str, Any]) -> list[dict[str, Any]]:
    summary = procedure.get("dependency_summary", {})
    dependencies: list[dict[str, Any]] = []
    for key in ("tables", "views", "functions", "procedures"):
        for dependency in summary.get(key, []):
            if (
                dependency.get("review_status") == "CONFIRMED"
                and dependency.get("resolution_status") == "CONFIRMED"
            ):
                dependencies.append(dependency)
    return dependencies


def _residual_review_dependencies(procedure: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        dependency
        for dependency in procedure.get("dependency_summary", {}).get("residual_review", [])
        if dependency.get("review_status") == "REVIEW_REQUIRED"
        and dependency.get("resolution_status") == "REVIEW_REQUIRED"
    ]


def _selected_procedures(manifest: dict[str, Any]) -> list[dict[str, Any]]:
    selected = []
    for complexity in ("simple", "medium", "complex"):
        selected.append(_selected_procedure(manifest, complexity))
    return selected


def _selected_procedure(manifest: dict[str, Any], complexity: str) -> dict[str, Any]:
    for procedure in manifest["stored_procedures"]:
        if procedure["complexity"] == complexity:
            return procedure
    raise AssertionError(f"missing selected {complexity} procedure")


def _require_live_manifest(manifest: dict[str, Any]) -> None:
    if manifest.get("selection_mode") != "live_metadata":
        pytest.fail(f"{P27_LIVE_BLOCKER}: selected_objects.yaml must be live_metadata.")
    if manifest.get("source_db") != "PPM":
        pytest.fail(f"{P27_LIVE_BLOCKER}: source_db must be PPM.")
    if manifest.get("platform_db_context") != "PLF":
        pytest.fail(f"{P27_LIVE_BLOCKER}: platform_db_context must be PLF.")
    if manifest.get("connection_profile_used", {}).get("profile_id") != "ppm":
        pytest.fail(f"{P27_LIVE_BLOCKER}: selected manifest must use dbProfileId=ppm.")
    if not manifest.get("connection_profile_used", {}).get("live_connection_verified"):
        pytest.fail(f"{P27_LIVE_BLOCKER}: selected manifest must record live connection.")
    if {item["complexity"] for item in manifest.get("stored_procedures", [])} < {
        "simple",
        "medium",
        "complex",
    }:
        pytest.fail(f"{P27_LIVE_BLOCKER}: selected manifest needs simple/medium/complex SPs.")


def _profile_by_id(profiles: list[DbProfile], profile_id: str) -> DbProfile | None:
    return next((profile for profile in profiles if profile.id == profile_id), None)


def _raw_definition_text_paths(payload: Any, path: str = "$") -> list[str]:
    paths: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            nested_path = f"{path}.{key}"
            if key == "definition" and isinstance(value, str) and value.strip():
                paths.append(nested_path)
            paths.extend(_raw_definition_text_paths(value, nested_path))
    elif isinstance(payload, list):
        for index, item in enumerate(payload):
            paths.extend(_raw_definition_text_paths(item, f"{path}[{index}]"))
    return paths


def _forbidden_payload_paths(payload: Any, path: str = "$") -> list[str]:
    forbidden_keys = {
        "rowdata",
        "samplerows",
        "sampledata",
        "procedureexecution",
        "definitiontext",
        "sqltext",
        "connectionstring",
    }
    paths: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            nested_path = f"{path}.{key}"
            if str(key).replace("_", "").lower() in forbidden_keys:
                paths.append(nested_path)
            paths.extend(_forbidden_payload_paths(value, nested_path))
    elif isinstance(payload, list):
        for index, item in enumerate(payload):
            paths.extend(_forbidden_payload_paths(item, f"{path}[{index}]"))
    return paths


def _pilot_manifest() -> dict[str, Any]:
    return yaml.safe_load(PILOT_MANIFEST.read_text(encoding="utf-8"))
