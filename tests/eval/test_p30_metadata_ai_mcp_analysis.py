from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from ai_agent_runtime import FakeModelGateway
from api_app.metadata_analysis_service import MetadataAnalysisService
from api_app.schemas import MetadataAnalysisRequest

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "fixtures" / "eval" / "metadata_ai_mcp_analysis_p30_v1.yaml"


class EvalRegistry:
    def invoke_payload(self, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "ok": True,
            "toolName": tool_name,
            "dbProfileId": payload["arguments"]["dbProfileId"],
            "snapshotId": "p30-eval-snapshot-1",
            "collectedAt": "2026-05-12T00:00:00Z",
            "evidenceRefs": [
                {
                    "id": "p30_table_schema",
                    "source": "fixture",
                    "path": "fixtures/mcp/metadata_snapshot.json#/tables/0",
                    "objectType": "TABLE",
                    "objectName": "dbo.TB_ORDER",
                }
            ],
            "data": {
                "schema": "dbo",
                "tableName": "TB_ORDER",
                "columns": [{"name": "ORDER_ID", "dataType": "int"}],
                "definition": "CREATE PROCEDURE dbo.leak AS SELECT 1",
                "rowData": [{"ORDER_ID": 1}],
                "secret": "do-not-return",
            },
        }


@pytest.fixture(autouse=True)
def fixture_metadata_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("P21_LIVE_PORTAL_GATE", "0")
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")
    monkeypatch.setenv("LLM_ENABLE_REMOTE", "0")


def test_p30_metadata_ai_mcp_fixture_contract() -> None:
    fixture = _fixture()

    assert fixture["production_ready"] is False
    assert fixture["status"] == "authored_p30"
    assert {scenario["fixture_id"] for scenario in fixture["scenarios"]} == {
        "p30_query_table_schema_tool_evidence",
        "p30_adversarial_planner_blocked",
    }


def test_p30_metadata_ai_mcp_analysis_uses_sanitized_mcp_fact_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "api_app.metadata_analysis_service._build_internal_registry",
        lambda _db_profile_id: EvalRegistry(),
    )
    scenario = _scenario("p30_query_table_schema_tool_evidence")
    gateway = FakeModelGateway(
        tool_plan_by_target_ref={"metadata.search:order": scenario["planner_output"]}
    )
    response = MetadataAnalysisService(model_gateway=gateway).analyze(
        MetadataAnalysisRequest.model_validate(scenario["request"])
    )
    payload = response.to_response()

    assert any(
        str(fact["id"]).startswith(scenario["expected"]["requiredFactIdPrefix"])
        for fact in payload["deterministicFacts"]
    )
    assert payload["objectInsights"][0]["evidenceRefs"][0].startswith(
        scenario["expected"]["requiredFactIdPrefix"]
    )
    serialized = json.dumps(payload, sort_keys=True)
    for fragment in scenario["expected"]["forbiddenFragments"]:
        assert fragment.lower() not in serialized.lower()


def test_p30_metadata_ai_mcp_analysis_blocks_adversarial_planner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "api_app.metadata_analysis_service._build_internal_registry",
        lambda _db_profile_id: EvalRegistry(),
    )
    scenario = _scenario("p30_adversarial_planner_blocked")
    gateway = FakeModelGateway(tool_plan_by_target_ref={"dbo.TB_ORDER": scenario["planner_output"]})
    response = MetadataAnalysisService(model_gateway=gateway).analyze(
        MetadataAnalysisRequest.model_validate(scenario["request"])
    )
    payload = response.to_response()

    blocked_codes = {
        item["code"] for item in payload["aiToolEvidence"].get("blockedRequests", [])
    }
    assert scenario["expected"]["requiredBlockedCode"] in blocked_codes
    serialized = json.dumps(payload, sort_keys=True)
    for fragment in scenario["expected"]["forbiddenFragments"]:
        assert fragment.lower() not in serialized.lower()


def _fixture() -> dict[str, Any]:
    return yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))


def _scenario(fixture_id: str) -> dict[str, Any]:
    for scenario in _fixture()["scenarios"]:
        if scenario["fixture_id"] == fixture_id:
            return scenario
    raise AssertionError(f"missing scenario: {fixture_id}")
