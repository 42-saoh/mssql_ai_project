from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import pytest
import yaml
from ai_agent_runtime import (
    SemanticAnalysisTask,
    build_model_gateway_from_env,
    build_semantic_analysis_runs,
    evaluate_p23_semantic_quality,
)
from ai_agent_runtime.gateway import model_profile_from_env

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "fixtures" / "eval" / "llm_sp_analysis_quality_p23_v1.yaml"


def test_p23_openai_quality_live_gate() -> None:
    if os.getenv("LLM_LIVE_GATE") != "1":
        pytest.skip("LLM_LIVE_GATE is not enabled; no external OpenAI API call attempted.")
    missing = [
        name
        for name in ("LLM_ENABLE_REMOTE", "LLM_ALLOW_SP_TEXT", "OPENAI_API_KEY")
        if not os.getenv(name)
    ]
    if missing:
        pytest.fail(f"Missing P23 OpenAI live gate env: {', '.join(missing)}")

    fixture = _fixture()
    gateway = build_model_gateway_from_env()
    profile_id = "openai_sp_semantic_analysis"
    expected_model = model_profile_from_env(profile_id).model
    failures: list[str] = []
    scenarios = list(fixture["scenarios"])
    runs = build_semantic_analysis_runs(
        tasks=[
            SemanticAnalysisTask(
                target_ref=scenario["target_ref"],
                metadata={
                    "dbContext": scenario["db_context"],
                    "deterministicFacts": scenario["deterministic_facts"],
                },
                static_analysis=scenario["transient_model_input"]["static_analysis"],
                procedure_definition=scenario["transient_model_input"]["procedure_definition"],
            )
            for scenario in scenarios
        ],
        model_gateway=gateway,
        profile_id=profile_id,
    )
    for scenario, run in zip(scenarios, runs, strict=True):
        report = evaluate_p23_semantic_quality(
            scenario=scenario,
            run=run,
            thresholds=fixture["quality_thresholds"],
        )
        serialized_report = json.dumps(report, ensure_ascii=False, sort_keys=True)
        assert scenario["transient_model_input"]["procedure_definition"] not in serialized_report
        assert "CREATE OR ALTER PROCEDURE" not in serialized_report
        assert "raw_prompt" not in serialized_report
        assert "raw_sp_definition" not in serialized_report
        assert "raw_openai_response_text" not in serialized_report
        assert run.model_invocation.provider == _expected_remote_provider()
        assert run.model_invocation.model == expected_model
        if report["status"] != "PASSED":
            failures.append(_sanitized_failure(scenario, report))

    if failures:
        pytest.fail(
            "P23 live quality confidence gate failed; production_ready remains false: "
            + ", ".join(failures)
        )


def _fixture() -> dict[str, Any]:
    return yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))


def _expected_remote_provider() -> str:
    provider = os.getenv("LLM_REMOTE_PROVIDER", "openai").strip().lower()
    if provider in {"pgpt", "p-gpt", "private-gpt"}:
        return "pgpt"
    return "openai"


def _sanitized_failure(scenario: dict[str, Any], report: dict[str, Any]) -> str:
    scores = report["scores"]
    return (
        f"{scenario['fixture_id']} status={report['status']} "
        f"semanticRecall={scores['semanticRecall']} "
        f"guideConversionRecall={scores['guideConversionRecall']} "
        f"evidenceDiscipline={scores['evidenceDiscipline']} "
        f"unreviewedOverclaims={scores['unreviewedOverclaims']} "
        f"storageSafetyFindings={scores['storageSafetyFindings']}"
    )
