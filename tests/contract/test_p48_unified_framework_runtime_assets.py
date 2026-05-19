from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from ai_agent_runtime import (
    AI_GENERATION_RUNTIME_OPENAI_AGENTS,
    AI_GENERATION_RUNTIME_RESPONSES_HTTPX,
    AI_STRUCTURED_FRAMEWORK_ADAPTER_VERSION,
    FrameworkModelGateway,
    OpenAIModelGateway,
    build_model_gateway_from_env,
    framework_runtime_config_from_env,
)

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "spec" / "eval" / "p48_unified_framework_runtime_contract.yaml"
PROJECT = ROOT / "PROJECT.md"
ARCHITECTURE = ROOT / "ARCHITECTURE.md"
POLICY = ROOT / "POLICY.md"
TOOLS = ROOT / "TOOLS.md"
EVAL_SPEC = ROOT / "EVAL_SPEC.md"
AGENT_RUNTIME_README = ROOT / "packages" / "agent-runtime" / "README.md"


def _yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_p48_contract_declares_unified_structured_runtime_matrix() -> None:
    contract = _yaml(CONTRACT)

    assert contract["contract_id"] == "p48_unified_framework_runtime@0.1.0"
    assert contract["extends"] == ["p44_framework_runtime_adoption@0.1.0"]
    assert contract["adapter_contract"] == AI_STRUCTURED_FRAMEWORK_ADAPTER_VERSION
    assert contract["structured_runtime"]["openai_remote_default"] == "openai_agents"
    assert contract["structured_runtime"]["pgpt_default"] == "openai_agents"
    assert contract["ai_draft_pack_runtime"] == "p44_existing_adapter_and_langgraph"
    assert contract["production_ready"] is False

    stages = {stage["stage_id"]: stage for stage in contract["runtime_matrix"]}
    assert set(stages) == {
        "llm_semantic_analysis",
        "metadata_tool_planning",
        "metadata_analysis",
        "platform_tool_planning",
        "sp_operation_model",
        "ai_java_mybatis_draft_pack",
    }
    assert stages["llm_semantic_analysis"]["schema_name"] == "llm_semantic_analysis"
    assert stages["metadata_tool_planning"]["schema_name"] == "metadata_tool_plan"
    assert stages["metadata_analysis"]["schema_name"] == "metadata_analysis"
    assert stages["platform_tool_planning"]["schema_name"] == "platform_tool_plan"
    assert stages["sp_operation_model"]["schema_name"] == "sp_operation_model"
    assert stages["ai_java_mybatis_draft_pack"]["runtime"] == "p44_openai_agents_langgraph"


def test_p48_runtime_env_defaults_and_rollback_selection(
    monkeypatch: Any,
) -> None:
    monkeypatch.setenv("LLM_ENABLE_REMOTE", "1")
    monkeypatch.delenv("LLM_REMOTE_PROVIDER", raising=False)
    monkeypatch.delenv("AI_GENERATION_RUNTIME", raising=False)
    monkeypatch.delenv("AI_STRUCTURED_LLM_RUNTIME", raising=False)

    config = framework_runtime_config_from_env()
    assert config.structured_llm_runtime == AI_GENERATION_RUNTIME_OPENAI_AGENTS
    assert isinstance(build_model_gateway_from_env(), FrameworkModelGateway)

    monkeypatch.setenv("LLM_REMOTE_PROVIDER", "pgpt")
    monkeypatch.delenv("AI_GENERATION_RUNTIME", raising=False)
    monkeypatch.delenv("AI_STRUCTURED_LLM_RUNTIME", raising=False)
    config = framework_runtime_config_from_env()
    assert config.ai_generation_runtime == AI_GENERATION_RUNTIME_RESPONSES_HTTPX
    assert config.structured_llm_runtime == AI_GENERATION_RUNTIME_OPENAI_AGENTS
    assert isinstance(build_model_gateway_from_env(), FrameworkModelGateway)

    monkeypatch.setenv("AI_STRUCTURED_LLM_RUNTIME", "responses_httpx")
    config = framework_runtime_config_from_env()
    assert config.structured_llm_runtime == AI_GENERATION_RUNTIME_RESPONSES_HTTPX
    assert isinstance(build_model_gateway_from_env(), OpenAIModelGateway)


def test_p48_contract_locks_trace_policy_and_forbidden_surface() -> None:
    contract = _yaml(CONTRACT)

    assert contract["trace_policy"]["adapter_contract"] == (
        AI_STRUCTURED_FRAMEWORK_ADAPTER_VERSION
    )
    assert contract["trace_policy"]["store_raw_prompt"] is False
    assert contract["trace_policy"]["store_raw_provider_response"] is False
    assert contract["trace_policy"]["store_raw_sp_definition"] is False
    assert contract["trace_policy"]["store_row_data"] is False
    assert all(contract["forbidden_behavior"].values())
    assert contract["public_surface"]["public_api_changed"] is False
    assert contract["public_surface"]["db_schema_changed"] is False
    assert contract["public_surface"]["ui_changed"] is False
    assert contract["public_surface"]["public_mcp_route_changed"] is False
    assert contract["public_surface"]["public_artifact_type_changed"] is False


def test_p48_docs_are_synchronized_without_readiness_claims() -> None:
    docs = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            PROJECT,
            ARCHITECTURE,
            POLICY,
            TOOLS,
            EVAL_SPEC,
            AGENT_RUNTIME_README,
        )
    )

    assert "P48" in docs
    assert AI_STRUCTURED_FRAMEWORK_ADAPTER_VERSION in docs
    assert "FrameworkModelGateway" in docs
    assert "OpenAIAgentsStructuredAdapter" in docs
    assert "metadata design planner" in docs
    assert "production_ready: false" in docs or "productionReady=false" in docs
    assert "public API" in docs
    assert "DB schema" in docs
    assert "row data" in docs or "row-data" in docs
    assert "procedure execution" in docs
