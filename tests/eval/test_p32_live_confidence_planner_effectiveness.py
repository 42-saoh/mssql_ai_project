from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
import yaml
from ai_agent_runtime import FakeModelGateway, build_planner_metrics
from api_app.metadata_analysis_service import MetadataAnalysisService
from api_app.schemas import MetadataAnalysisRequest
from mssql_mcp_app.profiles import load_db_profiles
from mssql_mcp_app.settings import load_live_metadata_settings

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "fixtures" / "eval" / "live_confidence_planner_effectiveness_p32_v1.yaml"
PILOT_MANIFEST = ROOT / "fixtures" / "pilot" / "ppm_object_selection_v1" / "selected_objects.yaml"
P32_LIVE_BLOCKER = "P32_LIVE_CONFIDENCE_REQUIRED"


class PlannerEffectivenessRegistry:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def invoke_payload(self, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((tool_name, payload))
        data_by_tool = {
            "get_table_schema": {
                "schema": "dbo",
                "tableName": "TB_ORDER",
                "description": "Order header.",
                "columns": [
                    {
                        "name": "ORDER_ID",
                        "dataType": "INT",
                        "isNullable": False,
                        "isPrimaryKey": True,
                        "description": "Primary key.",
                    },
                    {
                        "name": "STATUS_CD",
                        "dataType": "VARCHAR(30)",
                        "isNullable": False,
                        "descriptionStatus": "REVIEW_REQUIRED",
                    },
                ],
                "definition": "CREATE PROCEDURE dbo.usp_leak AS SELECT 1",
                "rowData": [{"ORDER_ID": 1}],
                "secret": "do-not-return",
            },
            "get_table_constraints": {
                "schema": "dbo",
                "tableName": "TB_ORDER",
                "constraints": [
                    {
                        "name": "PK_TB_ORDER",
                        "constraintType": "PK",
                        "columns": ["ORDER_ID"],
                    }
                ],
            },
            "get_table_indexes": {
                "schema": "dbo",
                "tableName": "TB_ORDER",
                "indexes": [
                    {
                        "name": "IX_TB_ORDER_STATUS",
                        "indexType": "NONCLUSTERED",
                        "keyColumns": ["STATUS_CD"],
                    }
                ],
            },
            "get_extended_properties": {
                "schema": "dbo",
                "objectName": "TB_ORDER",
                "objectType": "TABLE",
                "extendedProperties": [
                    {"name": "MS_Description", "value": "Order header.", "level": "OBJECT"}
                ],
            },
            "get_related_db_objects": {
                "schema": "dbo",
                "objectName": "TB_ORDER",
                "objectType": "TABLE",
                "relatedObjects": [
                    {
                        "schema": "dbo",
                        "name": "TB_CUSTOMER",
                        "objectType": "TABLE",
                        "dependencyType": "FK",
                        "reviewStatus": "CONFIRMED",
                    }
                ],
            },
        }
        return {
            "ok": True,
            "toolName": tool_name,
            "dbProfileId": payload["arguments"]["dbProfileId"],
            "snapshotId": "p32-eval-snapshot-1",
            "collectedAt": "2026-05-12T00:00:00Z",
            "evidenceRefs": [
                {
                    "id": f"p32_{tool_name}",
                    "source": "fixture",
                    "path": (
                        "fixtures/eval/live_confidence_planner_effectiveness_p32_v1.yaml"
                        f"#{tool_name}"
                    ),
                    "objectType": "TABLE",
                    "objectName": "dbo.TB_ORDER",
                }
            ],
            "data": data_by_tool[tool_name],
        }


@pytest.fixture(autouse=True)
def fixture_metadata_env(monkeypatch: pytest.MonkeyPatch) -> None:
    if os.getenv("P32_LIVE_CONFIDENCE_GATE", "").strip() == "1":
        return
    monkeypatch.setenv("P21_LIVE_PORTAL_GATE", "0")
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")
    monkeypatch.setenv("LLM_ENABLE_REMOTE", "0")


def test_p32_fixture_contract() -> None:
    fixture = _fixture()

    assert fixture["production_ready"] is False
    assert fixture["status"] == "authored_p32"
    assert fixture["live_confidence"]["default_status"] == "NOT_RUN_CONFIDENCE_ONLY"
    assert {scenario["fixture_id"] for scenario in fixture["scenarios"]} == {
        "p32_effective_metadata_planner_metrics",
        "p32_adversarial_planner_blocked",
        "p32_under_utilized_evidence",
    }


def test_p32_effective_metadata_planner_metrics(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = PlannerEffectivenessRegistry()
    monkeypatch.setattr(
        "api_app.metadata_analysis_service._build_internal_registry",
        lambda _db_profile_id: registry,
    )
    scenario = _scenario("p32_effective_metadata_planner_metrics")
    response = MetadataAnalysisService(
        model_gateway=FakeModelGateway(
            tool_plan_by_target_ref={"dbo.TB_ORDER": scenario["planner_output"]}
        )
    ).analyze(MetadataAnalysisRequest.model_validate(scenario["request"]))
    payload = response.to_response()
    metrics = payload["aiToolEvidence"]["plannerMetrics"]

    assert [call[0] for call in registry.calls] == [
        "get_table_schema",
        "get_table_constraints",
        "get_table_indexes",
        "get_extended_properties",
        "get_related_db_objects",
    ]
    assert metrics["executedToolCallCount"] == scenario["expected"]["executedToolCallCount"]
    assert metrics["dedupedRequestCount"] >= scenario["expected"]["dedupedRequestCountMin"]
    assert metrics["evidenceUtilization"] >= scenario["expected"]["evidenceUtilizationMin"]
    assert metrics["claimAnalysisAvailable"] is True
    serialized = json.dumps(payload, sort_keys=True)
    for fragment in scenario["expected"]["forbiddenFragments"]:
        assert fragment.lower() not in serialized.lower()


def test_p32_adversarial_planner_blocked(monkeypatch: pytest.MonkeyPatch) -> None:
    registry = PlannerEffectivenessRegistry()
    monkeypatch.setattr(
        "api_app.metadata_analysis_service._build_internal_registry",
        lambda _db_profile_id: registry,
    )
    scenario = _scenario("p32_adversarial_planner_blocked")
    response = MetadataAnalysisService(
        model_gateway=FakeModelGateway(
            tool_plan_by_target_ref={"dbo.TB_ORDER": scenario["planner_output"]}
        )
    ).analyze(MetadataAnalysisRequest.model_validate(scenario["request"]))
    payload = response.to_response()
    metrics = payload["aiToolEvidence"]["plannerMetrics"]

    assert registry.calls == []
    blocked_codes = {
        item["code"] for item in payload["aiToolEvidence"].get("blockedRequests", [])
    }
    assert scenario["expected"]["requiredBlockedCode"] in blocked_codes
    assert metrics["blockedRequestCount"] >= 1
    assert metrics["status"] == scenario["expected"]["plannerStatus"]
    serialized = json.dumps(payload, sort_keys=True)
    for fragment in scenario["expected"]["forbiddenFragments"]:
        assert fragment.lower() not in serialized.lower()


def test_p32_under_utilized_evidence_is_review_required() -> None:
    scenario = _scenario("p32_under_utilized_evidence")
    metric_input = scenario["metric_input"]

    metrics = build_planner_metrics(
        ai_tool_evidence=metric_input["aiToolEvidence"],
        deterministic_facts=metric_input["deterministicFacts"],
        component_invocations=metric_input["componentInvocations"],
        structured_output=metric_input["structuredOutput"],
    )

    assert metrics["status"] == scenario["expected"]["plannerStatus"]
    assert metrics["evidenceUtilization"] == scenario["expected"]["evidenceUtilization"]
    assert metrics["claimSupportRate"] == scenario["expected"]["claimSupportRate"]


def test_p32_live_metadata_planner_confidence_gate() -> None:
    if os.getenv("P32_LIVE_CONFIDENCE_GATE", "").strip() != "1":
        assert _fixture()["live_confidence"]["default_status"] == "NOT_RUN_CONFIDENCE_ONLY"
        return

    _require_live_confidence_prerequisites()
    target = _selected_live_table_target(_pilot_manifest())
    response = MetadataAnalysisService().analyze(
        MetadataAnalysisRequest.model_validate(
            {
                "dbProfileId": "ppm",
                "target": {
                    "schema": target["schema"],
                    "name": target["name"],
                    "type": "TABLE",
                },
                "options": {
                    "llmProfileId": "openai_sp_semantic_analysis",
                    "maxTargets": 1,
                },
            }
        )
    )
    payload = response.to_response()
    metrics = payload["aiToolEvidence"]["plannerMetrics"]

    assert metrics["executedToolCallCount"] >= 1
    assert metrics["evidenceFactCount"] >= 1
    assert metrics["evidenceUtilization"] >= _fixture()["quality_thresholds"][
        "evidence_utilization_min"
    ]
    assert payload["sourceDatabase"] == "PPM"
    assert "PLF" not in json.dumps(payload.get("aiToolEvidence", {}), sort_keys=True)
    serialized = json.dumps(payload, sort_keys=True).lower()
    for fragment in ("create procedure", "rowdata", "row_data", "connectionstring"):
        assert fragment not in serialized


def _require_live_confidence_prerequisites() -> None:
    missing = [
        name
        for name in ("LLM_LIVE_GATE", "LLM_ENABLE_REMOTE", "MSSQL_ENABLE_LIVE_METADATA")
        if os.getenv(name, "").strip() != "1"
    ]
    if not os.getenv("OPENAI_API_KEY", "").strip():
        missing.append("OPENAI_API_KEY")
    if missing:
        pytest.fail(f"{P32_LIVE_BLOCKER}: missing env flag(s): {', '.join(missing)}")

    settings = load_live_metadata_settings()
    if not settings.live_metadata_enabled:
        pytest.fail(f"{P32_LIVE_BLOCKER}: requires MSSQL_ENABLE_LIVE_METADATA=1.")
    profiles = load_db_profiles(settings, repo_root=ROOT)
    ppm_profile = next((profile for profile in profiles if profile.id == "ppm"), None)
    if ppm_profile is None or ppm_profile.database != "PPM":
        pytest.fail(f"{P32_LIVE_BLOCKER}: metadata profile registry must include ppm -> PPM.")


def _selected_live_table_target(manifest: dict[str, Any]) -> dict[str, str]:
    if manifest.get("selection_mode") != "live_metadata":
        pytest.fail(f"{P32_LIVE_BLOCKER}: selected_objects.yaml must be live_metadata.")
    for procedure in manifest.get("stored_procedures", []):
        for table in procedure.get("dependency_summary", {}).get("tables", []):
            if (
                table.get("database") == "PPM"
                and table.get("review_status") == "CONFIRMED"
                and table.get("resolution_status") == "CONFIRMED"
            ):
                return {"schema": table["schema"], "name": table["name"]}
    pytest.fail(f"{P32_LIVE_BLOCKER}: selected manifest must include a confirmed PPM table.")


def _fixture() -> dict[str, Any]:
    return yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))


def _pilot_manifest() -> dict[str, Any]:
    return yaml.safe_load(PILOT_MANIFEST.read_text(encoding="utf-8"))


def _scenario(fixture_id: str) -> dict[str, Any]:
    for scenario in _fixture()["scenarios"]:
        if scenario["fixture_id"] == fixture_id:
            return scenario
    raise AssertionError(f"missing scenario: {fixture_id}")
