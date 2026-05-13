from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from ai_agent_runtime import FakeModelGateway
from api_app.ai_tool_orchestrator import effective_ai_tool_budget
from api_app.metadata_analysis_service import MetadataAnalysisService
from api_app.schemas import MetadataAnalysisRequest
from mssql_mcp_app.tool_cache import clear_metadata_tool_result_cache

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "fixtures" / "eval" / "performance_scale_p33_v1.yaml"


@pytest.fixture(autouse=True)
def fixture_env(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_metadata_tool_result_cache()
    monkeypatch.setenv("P21_LIVE_PORTAL_GATE", "0")
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")
    monkeypatch.setenv("LLM_ENABLE_REMOTE", "0")
    monkeypatch.setenv("MCP_TOOL_RESULT_CACHE_ENABLED", "1")
    monkeypatch.setenv("MCP_TOOL_RESULT_CACHE_TTL_SECONDS", "300")
    monkeypatch.setenv("MCP_TOOL_RESULT_CACHE_MAX_ENTRIES", "1024")


def test_p33_fixture_declares_performance_scale_scenarios() -> None:
    fixture = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))

    assert fixture["id"] == "P33"
    assert fixture["production_ready"] is False
    scenario_ids = {item["id"] for item in fixture["scenarios"]}
    assert {
        "cache_hit_reuse",
        "stable_fact_hash_reuse",
        "batch_duplicate_dedupe",
        "batch_limit_rejection",
        "planner_live_round_reduction",
        "backpressure_marker",
        "no_raw_leakage",
    } <= scenario_ids


def test_p33_metadata_analyze_cache_hit_reuses_stable_fact_id() -> None:
    service = MetadataAnalysisService(
        model_gateway=FakeModelGateway(
            tool_plan_by_target_ref={
                "dbo.TB_ORDER": {
                    "toolRequests": [
                        {
                            "toolName": "get_table_schema",
                            "arguments": {
                                "dbProfileId": "master",
                                "schema": "dbo",
                                "tableName": "TB_ORDER",
                            },
                            "reason": "Need table schema for P33 cache reuse.",
                            "expectedEvidenceUse": "Anchor metadata analysis fact id.",
                        }
                    ],
                    "assumptions": [],
                    "reviewMarkers": [],
                }
            }
        )
    )
    request = MetadataAnalysisRequest.model_validate(
        {
            "dbProfileId": "master",
            "target": {"schema": "dbo", "name": "TB_ORDER", "type": "TABLE"},
            "options": {"llmProfileId": "openai_fast_test"},
        }
    )

    first = service.analyze(request).to_response()
    second = service.analyze(request).to_response()

    first_result = first["aiToolEvidence"]["toolResults"][0]
    second_result = second["aiToolEvidence"]["toolResults"][0]
    assert first_result["factId"] == second_result["factId"]
    assert first_result["contentHash"] == second_result["contentHash"]
    assert first_result["outputHash"] == second_result["outputHash"]
    assert first["aiToolEvidence"]["plannerMetrics"]["cacheMissCount"] >= 1
    assert second["aiToolEvidence"]["plannerMetrics"]["cacheHitCount"] >= 1
    serialized = str(second).lower()
    assert "create procedure" not in serialized
    assert "rowdata" not in serialized
    assert "do-not-return" not in serialized


def test_p33_live_ppm_budget_reduces_planning_rounds(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "1")
    monkeypatch.setenv("AI_TOOL_MAX_CALLS", "5")
    monkeypatch.setenv("AI_TOOL_MAX_ROUNDS", "2")
    monkeypatch.setenv("AI_TOOL_LIVE_MAX_ROUNDS", "1")

    calls, rounds, reduced = effective_ai_tool_budget("ppm")

    assert calls == 5
    assert rounds == 1
    assert reduced is True
