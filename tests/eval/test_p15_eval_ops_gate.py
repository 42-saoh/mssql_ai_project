from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import pytest
import yaml
from api_app.schemas import SPAnalysisRequest
from api_app.workflow import WorkflowService
from mssql_mcp_app.errors import MetadataToolError
from mssql_mcp_app.profiles import DbProfile, load_db_profiles
from mssql_mcp_app.registry import build_tool_registry
from mssql_mcp_app.repositories import LiveMetadataRepository
from mssql_mcp_app.settings import load_live_metadata_settings

from tests.unit.api.fake_repository import MemoryWorkflowRepository

ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = ROOT / "fixtures" / "eval"
PILOT_MANIFEST = ROOT / "fixtures" / "pilot" / "ppm_object_selection_v1" / "selected_objects.yaml"


def test_p15_hard_live_fixture_contract_matches_manifest() -> None:
    fixture = _yaml_fixture("eval_observability_security_ops_p15_v1.yaml")
    manifest = _pilot_manifest()

    assert fixture["gate_mode"] == "hard_live"
    assert fixture["activation"] == {
        "explicit_env_flag": "P15_HARD_LIVE_GATE",
        "required_value": "1",
        "live_metadata_env_flag": "MSSQL_ENABLE_LIVE_METADATA",
        "live_metadata_required_value": "1",
    }
    assert fixture["source_manifest"] == str(
        Path("fixtures") / "pilot" / "ppm_object_selection_v1" / "selected_objects.yaml"
    )
    assert fixture["selection_mode_required"] == "live_metadata"
    assert manifest["selection_mode"] == "live_metadata"
    assert manifest["source_db"] == "PPM"
    assert manifest["platform_db_context"] == "PLF"

    profile_policy = fixture["profile_policy"]
    assert profile_policy["analysis_db_profile_id"] == "ppm"
    assert profile_policy["source_database"] == "PPM"
    assert profile_policy["platform_db_context"] == "PLF"
    assert profile_policy["live_metadata_required"] is True
    assert profile_policy["plf_fallback_allowed"] is False
    assert profile_policy["metadata_only"] is True
    assert profile_policy["row_data_allowed"] is False
    assert profile_policy["procedure_execution_allowed"] is False
    assert profile_policy["ddl_dml_allowed"] is False

    assert "DEPENDENCY_METADATA_INCOMPLETE" in fixture["active_blockers_to_carry_forward"]
    assert "DEPENDENCY_METADATA_INCOMPLETE" in {
        blocker["code"] for blocker in manifest["active_blockers"]
    }
    assert {
        "LIVE_PPM_EVAL_REQUIRED",
        "LIVE_METADATA_UNAVAILABLE",
        "PPM_DB_NOT_FOUND",
        "PPM_DB_ACCESS_DENIED",
        "METADATA_READ_ONLY_PERMISSION_INSUFFICIENT",
        "DEPENDENCY_METADATA_INCOMPLETE",
        "LATENCY_INSTRUMENTATION_OUT_OF_SCOPE",
    }.issubset(set(fixture["hard_fail_blockers"]))

    serialized = yaml.safe_dump(fixture, sort_keys=True).lower()
    for forbidden_sql_shape in (
        "create procedure",
        "alter procedure",
        "exec ",
        "execute ",
        "select *",
        "top n",
    ):
        assert forbidden_sql_shape not in serialized


def test_p15_quality_observability_and_permission_contracts_are_complete() -> None:
    fixture = _yaml_fixture("eval_observability_security_ops_p15_v1.yaml")

    assert set(fixture["quality_metrics"]) == {
        "evidence_coverage",
        "review_required_ratio",
        "validation_pass_rate",
        "generation_reproducibility",
        "draft_artifact_completeness",
    }
    for metric in fixture["quality_metrics"].values():
        assert metric["formula"]
        assert metric["product_target"]
        assert metric["current_live_gate"]

    assert set(fixture["latency_budgets"]) == {
        "ppm_readiness",
        "metadata_inventory_smoke",
        "fixture_workflow_smoke",
    }
    for budget in fixture["latency_budgets"].values():
        assert budget["product_target"]["max_ms"] > 0
        assert budget["current_live_gate"]["max_ms"] >= budget["product_target"]["max_ms"]

    observability = fixture["observability_contract"]
    assert observability["correlation_id"]["request_header"] == "X-Correlation-ID"
    assert observability["correlation_id"]["response_header"] == "X-Correlation-ID"
    assert observability["audit_stages"] == [
        "REQUEST",
        "JOB",
        "METADATA",
        "ARTIFACT",
        "VALIDATION",
        "APPROVAL",
    ]
    assert {"correlation_id", "db_profile_id", "snapshot_id", "blocker_code"} <= set(
        observability["log_context_fields"]
    )
    assert {"latency_ms", "evidence_coverage_ratio", "audit_stage"} <= set(
        observability["monitoring_signals"]
    )

    redaction = fixture["redaction_policy"]
    assert redaction["replacement"] == "REDACTED"
    assert {"password", "token", "api_key", "connection_string"} <= set(
        redaction["sensitive_value_markers"]
    )
    assert {"raw_definition_text", "row_data", "connection_strings"} <= set(
        redaction["must_not_log"]
    )

    permission_checks = fixture["read_only_permission_checks"]
    assert permission_checks["required"] is True
    assert {check["tool"] for check in permission_checks["checks"]} >= {
        "check_database_exists",
        "list_procedures",
        "list_tables",
        "get_procedure_dependencies",
        "get_table_schema",
    }
    assert all(check["dbProfileId"] == "ppm" for check in permission_checks["checks"])


def test_p15_hard_live_ppm_metadata_gate_enforced() -> None:
    fixture = _yaml_fixture("eval_observability_security_ops_p15_v1.yaml")
    manifest = _pilot_manifest()
    _require_live_manifest(fixture, manifest)

    if not _hard_live_gate_enabled():
        pytest.skip(
            "P15 hard-live metadata gate requires P15_HARD_LIVE_GATE=1. "
            "Default eval remains fixture-first and does not call live PPM."
        )

    settings = load_live_metadata_settings()
    if not settings.live_metadata_enabled:
        pytest.fail(
            "LIVE_PPM_EVAL_REQUIRED: P15 hard gate requires "
            "MSSQL_ENABLE_LIVE_METADATA=1 with read-only PPM metadata access."
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
            "LIVE_PPM_EVAL_REQUIRED: missing live metadata setting(s): "
            + ", ".join(missing_settings)
        )

    profiles = load_db_profiles(settings, repo_root=ROOT)
    ppm_profile = _profile_by_id(profiles, "ppm")
    if ppm_profile is None:
        pytest.fail("LIVE_PPM_EVAL_REQUIRED: metadata profile registry must include ppm.")
    if ppm_profile.database != "PPM":
        pytest.fail("LIVE_PPM_EVAL_REQUIRED: ppm profile must point to source database PPM.")

    repository = LiveMetadataRepository(settings=settings, profiles=profiles)
    registry = build_tool_registry(repository=repository, profiles=profiles)
    simple_procedure = _selected_procedure(manifest, "simple")
    selected_table = manifest["tables"][0]

    responses: list[dict[str, Any]] = []
    durations_ms: dict[str, float] = {}

    calls = [
        (
            "check_database_exists",
            {"dbProfileId": "ppm", "databaseName": "PPM"},
        ),
        ("list_procedures", {"dbProfileId": "ppm", "schema": "dbo", "topK": 5}),
        ("list_tables", {"dbProfileId": "ppm", "schema": "dbo", "topK": 5}),
        ("list_views", {"dbProfileId": "ppm", "schema": "dbo", "topK": 5}),
        ("list_functions", {"dbProfileId": "ppm", "schema": "dbo", "topK": 5}),
        (
            "get_procedure_dependencies",
            {
                "dbProfileId": "ppm",
                "schema": simple_procedure["schema"],
                "procedureName": simple_procedure["name"],
            },
        ),
        (
            "get_table_schema",
            {
                "dbProfileId": "ppm",
                "schema": selected_table["schema"],
                "tableName": selected_table["name"],
            },
        ),
    ]

    for tool_name, arguments in calls:
        response, elapsed_ms = _invoke_live_metadata_tool(
            registry,
            tool_name,
            arguments,
        )
        responses.append(response)
        durations_ms[tool_name] = durations_ms.get(tool_name, 0.0) + elapsed_ms

    readiness_budget = fixture["latency_budgets"]["ppm_readiness"]["current_live_gate"][
        "max_ms"
    ]
    metadata_budget = fixture["latency_budgets"]["metadata_inventory_smoke"][
        "current_live_gate"
    ]["max_ms"]
    assert durations_ms["check_database_exists"] <= readiness_budget
    assert sum(
        duration for name, duration in durations_ms.items() if name != "check_database_exists"
    ) <= metadata_budget

    for response in responses:
        assert response["ok"] is True
        assert response["dbProfileId"] == "ppm"
        assert response["snapshotId"].startswith("live:ppm:")
        assert response["evidenceRefs"], response["toolName"]
        assert response["data"]["sourceProfile"] == "ppm"
        assert response["data"]["sourceDatabase"] == "PPM"
        assert _raw_definition_text_paths(response) == []
        assert _forbidden_payload_paths(response) == []

    evidence_coverage = sum(bool(response["evidenceRefs"]) for response in responses) / len(
        responses
    )
    assert evidence_coverage >= fixture["quality_metrics"]["evidence_coverage"][
        "current_live_gate"
    ]["minimum"]

    review_required_ratio = _review_required_ratio(manifest["stored_procedures"])
    assert review_required_ratio <= fixture["quality_metrics"]["review_required_ratio"][
        "current_live_gate"
    ]["maximum"]
    if review_required_ratio > fixture["quality_metrics"]["review_required_ratio"][
        "product_target"
    ]["maximum"]:
        assert "DEPENDENCY_METADATA_INCOMPLETE" in {
            blocker["code"] for blocker in manifest["active_blockers"]
        }


def test_p15_fixture_workflow_latency_reproducibility_and_draft_completeness(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")
    fixture = _yaml_fixture("eval_observability_security_ops_p15_v1.yaml")
    expectations = _json_fixture("artifact_payloads.json")

    started = time.perf_counter()
    first = _workflow_summary()
    elapsed_ms = (time.perf_counter() - started) * 1000
    second = _workflow_summary()

    workflow_budget = fixture["latency_budgets"]["fixture_workflow_smoke"][
        "current_live_gate"
    ]["max_ms"]
    assert elapsed_ms <= workflow_budget
    assert first == second

    assert first["jobStatus"] == expectations["workflow"]["jobStatus"]
    assert first["currentStep"] == expectations["workflow"]["currentStep"]
    assert first["artifactTypes"] == expectations["workflow"]["artifactTypes"]
    assert "PUBLISHED" not in first["artifactStatuses"]

    complete_artifacts = [
        artifact
        for artifact in first["artifacts"]
        if artifact["status"] == "REVIEW_PENDING"
        and artifact["latestValidationStatus"] == "REVIEW_REQUIRED"
        and artifact["generatorVersion"]
        and artifact["registryRefs"]
        and artifact["reviewRequired"] is True
    ]
    completeness = len(complete_artifacts) / len(first["artifacts"])
    assert completeness >= fixture["quality_metrics"]["draft_artifact_completeness"][
        "current_live_gate"
    ]["minimum"]

    validation_statuses = first["validationStatuses"]
    pass_rate = validation_statuses.count("PASSED") / len(validation_statuses)
    assert pass_rate >= fixture["quality_metrics"]["validation_pass_rate"][
        "current_live_gate"
    ]["minimum"]
    assert "REVIEW_REQUIRED" in validation_statuses


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


def _workflow_summary() -> dict[str, Any]:
    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)
    request_fixture = _json_fixture("request.json")
    _request_record, job = service.submit_sp_analysis(
        SPAnalysisRequest.model_validate(request_fixture["request"])
    )
    artifacts = list(repository.artifacts.values())
    return {
        "jobStatus": job.status.value,
        "currentStep": job.current_step.value,
        "artifactTypes": [artifact.type.value for artifact in artifacts],
        "artifactStatuses": [artifact.status.value for artifact in artifacts],
        "validationStatuses": [
            artifact.latest_validation_status for artifact in artifacts
        ],
        "artifacts": [
            {
                "type": artifact.type.value,
                "status": artifact.status.value,
                "latestValidationStatus": artifact.latest_validation_status,
                "generatorVersion": artifact.generator_version,
                "registryRefs": artifact.registry_refs,
                "reviewRequired": artifact.review_required,
                "assumptions": artifact.assumptions,
                "evidenceRefCount": len(artifact.evidence_refs),
                "content": artifact.content,
            }
            for artifact in artifacts
        ],
    }


def _require_live_manifest(fixture: dict[str, Any], manifest: dict[str, Any]) -> None:
    assert manifest["selection_mode"] == fixture["selection_mode_required"]
    assert manifest["connection_profile_used"]["profile_id"] == "ppm"
    assert manifest["connection_profile_used"]["database"] == "PPM"
    assert manifest["connection_profile_used"]["live_connection_verified"] is True
    assert {item["complexity"] for item in manifest["stored_procedures"]} == {
        "simple",
        "medium",
        "complex",
    }
    assert len(manifest["tables"]) >= 3
    assert len(manifest["views"]) >= 1
    assert len(manifest["functions"]) >= 1


def _selected_procedure(manifest: dict[str, Any], complexity: str) -> dict[str, Any]:
    for procedure in manifest["stored_procedures"]:
        if procedure["complexity"] == complexity:
            return procedure
    raise AssertionError(f"missing selected {complexity} procedure")


def _review_required_ratio(items: list[dict[str, Any]]) -> float:
    assert items
    return sum(bool(item.get("review_required")) for item in items) / len(items)


def _profile_by_id(profiles: list[DbProfile], profile_id: str) -> DbProfile | None:
    return next((profile for profile in profiles if profile.id == profile_id), None)


def _hard_live_gate_enabled() -> bool:
    return os.getenv("P15_HARD_LIVE_GATE", "").strip() == "1"


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


def _json_fixture(name: str) -> dict[str, Any]:
    return json.loads((EVAL_DIR / name).read_text(encoding="utf-8"))


def _yaml_fixture(name: str) -> dict[str, Any]:
    return yaml.safe_load((EVAL_DIR / name).read_text(encoding="utf-8"))


def _pilot_manifest() -> dict[str, Any]:
    return yaml.safe_load(PILOT_MANIFEST.read_text(encoding="utf-8"))
