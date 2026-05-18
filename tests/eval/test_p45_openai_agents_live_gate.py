from __future__ import annotations

import json
import os

import pytest
from ai_agent_runtime import (
    FakeModelGateway,
    LangGraphAiDraftPackOrchestrator,
    ModelGatewayError,
    OpenAIAgentsFrameworkAdapter,
    openai_agents_live_gate_enabled,
    openai_agents_live_gate_missing_requirements,
)
from ai_agent_validation import validate_ai_java_mybatis_draft_pack_quality
from ai_agent_validation.models import ValidationStatus
from api_app.workflow import (
    ai_draft_pack_allowed_evidence_refs,
    ai_draft_pack_context,
    ai_draft_pack_expected_inventory,
    ai_draft_pack_quality_gates,
)

from tests.eval.test_p43_framework_adapter_replay import (
    _assert_no_collapsed_or_fallback_pack,
    _assert_no_raw_trace_leakage,
    _pack_from_inventory,
    _synthetic_generation_context,
)

LIVE_GATE_ENV = "P44_OPENAI_AGENTS_LIVE_GATE"


def test_p45_gate_disabled_does_not_require_openai_or_framework_trace_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        LIVE_GATE_ENV,
        "LLM_ENABLE_REMOTE",
        "LLM_REMOTE_PROVIDER",
        "OPENAI_API_KEY",
        "OPENAI_AGENTS_DISABLE_TRACING",
        "OPENAI_AGENTS_TRACE_INCLUDE_SENSITIVE_DATA",
        "OPENAI_AGENTS_DONT_LOG_MODEL_DATA",
        "OPENAI_AGENTS_DONT_LOG_TOOL_DATA",
    ):
        monkeypatch.delenv(name, raising=False)

    assert openai_agents_live_gate_enabled() is False
    assert openai_agents_live_gate_missing_requirements() == []


def test_p45_gate_enabled_missing_prerequisites_returns_sanitized_blockers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (
        "LLM_ENABLE_REMOTE",
        "LLM_REMOTE_PROVIDER",
        "OPENAI_API_KEY",
        "OPENAI_AGENTS_DISABLE_TRACING",
        "OPENAI_AGENTS_TRACE_INCLUDE_SENSITIVE_DATA",
        "OPENAI_AGENTS_DONT_LOG_MODEL_DATA",
        "OPENAI_AGENTS_DONT_LOG_TOOL_DATA",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(LIVE_GATE_ENV, "1")

    missing = openai_agents_live_gate_missing_requirements()

    assert "LLM_ENABLE_REMOTE=1" in missing
    assert "LLM_REMOTE_PROVIDER=openai" in missing
    assert "OPENAI_API_KEY" in missing
    assert "OPENAI_AGENTS_DISABLE_TRACING=1" in missing
    assert "OPENAI_AGENTS_TRACE_INCLUDE_SENSITIVE_DATA=0" in missing
    assert "OPENAI_AGENTS_DONT_LOG_MODEL_DATA=1" in missing
    assert "OPENAI_AGENTS_DONT_LOG_TOOL_DATA=1" in missing
    assert not any("sk-" in item.lower() for item in missing)


def test_p45_openai_agents_live_gate() -> None:
    if os.getenv(LIVE_GATE_ENV, "").strip() != "1":
        pytest.skip(
            "P45 OpenAI Agents live gate requires P44_OPENAI_AGENTS_LIVE_GATE=1. "
            "Default eval remains fixture-first and does not call OpenAI, PPM, or PLF."
        )
    missing = openai_agents_live_gate_missing_requirements()
    if missing:
        pytest.fail(
            "Missing P45 OpenAI Agents live gate env; production_ready remains false: "
            + ", ".join(missing)
        )

    context = _synthetic_generation_context()
    expected_inventory = ai_draft_pack_expected_inventory(context)
    quality_gates = ai_draft_pack_quality_gates(context, expected_inventory)
    target_ref = _pack_from_inventory(
        target_ref=context.operation_model["targetRef"],
        expected_inventory=expected_inventory,
        quality_gates=quality_gates,
    )["targetRef"]
    sanitized_context = ai_draft_pack_context(context)
    allowed_refs = ai_draft_pack_allowed_evidence_refs(
        context=sanitized_context,
        expected_inventory=expected_inventory,
    )
    orchestrator = LangGraphAiDraftPackOrchestrator(
        framework_adapter=OpenAIAgentsFrameworkAdapter()
    )

    try:
        run = orchestrator.build_run(
            target_ref=target_ref,
            sanitized_draft_context=sanitized_context,
            expected_inventory=expected_inventory,
            quality_gates=quality_gates,
            model_gateway=FakeModelGateway(),
            profile_id="openai_ai_draft_pack",
            allowed_evidence_refs=allowed_refs,
        )
    except ModelGatewayError as exc:
        sanitized_error = dict(exc.provider_error)
        pytest.fail(
            "P45 OpenAI Agents live gate failed before deterministic scoring; "
            f"production_ready remains false: {exc.code}; "
            f"sanitizedError={json.dumps(sanitized_error, sort_keys=True)}"
        )

    report = validate_ai_java_mybatis_draft_pack_quality(run.structured_output)
    serialized_invocation = json.dumps(
        run.model_invocation.to_storage_dict(),
        ensure_ascii=False,
        sort_keys=True,
    )

    assert report.status == ValidationStatus.PASSED
    assert run.model_invocation.provider == "openai-agents-sdk"
    assert run.model_invocation.component_invocations[-1]["orchestrator"] == "langgraph"
    assert "CREATE PROCEDURE" not in serialized_invocation.upper()
    assert "raw_prompt" not in serialized_invocation
    assert "raw_provider_response" not in serialized_invocation
    assert "row data" not in serialized_invocation.lower()
    _assert_no_collapsed_or_fallback_pack(run.structured_output)
    _assert_no_raw_trace_leakage(serialized_invocation)
