from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from ai_agent_runtime import (
    OPENAI_AGENTS_TRACE_ENV_LOCKS,
    P44_OPENAI_AGENTS_LIVE_GATE,
    openai_agents_live_gate_enabled,
    openai_agents_live_gate_missing_requirements,
)

ROOT = Path(__file__).resolve().parents[2]
P44_CONTRACT = ROOT / "spec" / "eval" / "p44_framework_runtime_adoption_contract.yaml"
P46_DECISION = ROOT / "spec" / "eval" / "p46_rollback_removal_decision.yaml"
ENV_EXAMPLE = ROOT / ".env.example"
DOCKER_COMPOSE = ROOT / "docker" / "test" / "docker-compose.yml"
TOOLS = ROOT / "TOOLS.md"
EVAL_SPEC = ROOT / "EVAL_SPEC.md"
TEST_GATE_HISTORY = ROOT / "docs" / "test-gate-history.md"


def _yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_p45_live_gate_contract_is_optional_and_policy_locked() -> None:
    live_gate = _yaml(P44_CONTRACT)["live_gate"]

    assert live_gate["phase"] == "P45"
    assert live_gate["name"] == P44_OPENAI_AGENTS_LIVE_GATE
    assert live_gate["default_enabled"] is False
    assert live_gate["test"] == "tests/eval/test_p45_openai_agents_live_gate.py"
    assert live_gate["live_ppm_required"] is False
    assert live_gate["live_ppm_row_data_allowed"] is False
    assert live_gate["live_procedure_execution_allowed"] is False
    assert live_gate["persisted_evidence"] == "sanitized_invocation_summary_only"
    for key, value in OPENAI_AGENTS_TRACE_ENV_LOCKS.items():
        assert f"{key}={value}" in live_gate["required_env"]


def test_p45_live_gate_env_helper_is_strict_but_disabled_by_default() -> None:
    assert openai_agents_live_gate_enabled({}) is False
    assert openai_agents_live_gate_missing_requirements({}) == []

    missing = openai_agents_live_gate_missing_requirements(
        {
            P44_OPENAI_AGENTS_LIVE_GATE: "1",
            "LLM_ENABLE_REMOTE": "1",
            "LLM_REMOTE_PROVIDER": "openai",
            "OPENAI_AGENTS_DISABLE_TRACING": "1",
            "OPENAI_AGENTS_TRACE_INCLUDE_SENSITIVE_DATA": "0",
            "OPENAI_AGENTS_DONT_LOG_MODEL_DATA": "1",
            "OPENAI_AGENTS_DONT_LOG_TOOL_DATA": "1",
        }
    )

    assert missing == ["OPENAI_API_KEY"]


def test_p45_env_assets_forward_live_gate_and_trace_locks() -> None:
    env_text = ENV_EXAMPLE.read_text(encoding="utf-8")
    compose_text = DOCKER_COMPOSE.read_text(encoding="utf-8")

    assert "P44_OPENAI_AGENTS_LIVE_GATE=0" in env_text
    assert "P44_OPENAI_AGENTS_LIVE_GATE" in compose_text
    for key, value in OPENAI_AGENTS_TRACE_ENV_LOCKS.items():
        assert f"{key}={value}" in env_text
        assert key in compose_text


def test_p46_decision_keeps_openai_default_on_agents_and_limited_rollback() -> None:
    p44 = _yaml(P44_CONTRACT)
    p46 = _yaml(P46_DECISION)

    assert p44["rollback_decision"]["decision_record"] == p46["contract_id"]
    assert p44["rollback_decision"]["decision_pending"] is False
    assert p44["rollback_decision"]["decision"] == (
        "retain_limited_rollback_not_active_default"
    )
    assert p46["decision"] == "retain_limited_rollback_not_active_default"
    assert p46["runtime_default"]["openai_remote_generation_runtime"] == (
        "openai_agents_sdk"
    )
    assert p46["runtime_default"]["openai_remote_orchestrator"] == "langgraph"
    assert p46["rollback_status"]["responses_httpx_active_default_for_openai"] is False
    assert p46["rollback_status"]["responses_httpx_retained_for_pgpt"] is True
    assert p46["rollback_status"]["responses_httpx_retained_for_emergency_rollback"] is True
    assert p46["rollback_status"]["deletion_approved"] is False
    assert p46["rationale"]["generated_artifacts_production_ready"] is False


def test_p45_p46_docs_include_live_gate_and_rollback_decision() -> None:
    docs = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (TOOLS, EVAL_SPEC, TEST_GATE_HISTORY)
    )

    assert "P44_OPENAI_AGENTS_LIVE_GATE" in docs
    assert "P45" in docs
    assert "P46" in docs
    assert "responses_httpx" in docs
    assert "emergency rollback" in docs
    assert "P-GPT" in docs
    assert "production_ready: false" in docs
    assert "procedure execution" in docs
    assert "row data" in docs or "row-data" in docs
