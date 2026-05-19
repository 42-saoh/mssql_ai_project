from __future__ import annotations

import importlib.util
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
P43_CONTRACT = ROOT / "spec" / "eval" / "p43_framework_adoption_contract.yaml"
P44_CONTRACT = ROOT / "spec" / "eval" / "p44_framework_runtime_adoption_contract.yaml"
PROJECT = ROOT / "PROJECT.md"
ARCHITECTURE = ROOT / "ARCHITECTURE.md"
POLICY = ROOT / "POLICY.md"
TOOLS = ROOT / "TOOLS.md"
EVAL_SPEC = ROOT / "EVAL_SPEC.md"
AGENT_RUNTIME_README = ROOT / "packages" / "agent-runtime" / "README.md"


def _yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_p44_contract_declares_actual_runtime_adoption() -> None:
    contract = _yaml(P44_CONTRACT)

    assert contract["contract_id"] == "p44_framework_runtime_adoption@0.1.0"
    assert contract["framework_adoption_decision"] == "adopt"
    assert contract["primary_generation_runtime"] == "openai_agents_sdk"
    assert contract["orchestration_runtime"] == "langgraph"
    assert contract["generated_artifacts_production_ready"] is False
    assert contract["public_surface_changes_allowed"] is False
    assert contract["supersedes"] == ["p43_framework_adoption@0.1.0"]


def test_p43_is_superseded_not_rewritten() -> None:
    p43 = _yaml(P43_CONTRACT)
    p44 = _yaml(P44_CONTRACT)

    assert p43["contract_id"] == "p43_framework_adoption@0.1.0"
    assert p43["decision_gate"]["decision"] == "pilot"
    assert p43["superseded_by"] == "p44_framework_runtime_adoption@0.1.0"
    assert "p43_framework_adoption@0.1.0" in p44["supersedes"]


def test_p44_dependency_contract_imports_are_available() -> None:
    contract = _yaml(P44_CONTRACT)
    dependencies = contract["dependency_policy"]["direct_dependencies"]

    assert dependencies["openai-agents"] == "0.17.2"
    assert dependencies["langgraph"] == "1.2.0"
    assert importlib.util.find_spec("agents") is not None
    assert importlib.util.find_spec("langgraph") is not None


def test_p44_runtime_config_keeps_internal_surface_and_pgpt_compatible_sdk_path() -> None:
    runtime = _yaml(P44_CONTRACT)["runtime_config"]

    assert runtime["config_contract"] == "FrameworkRuntimeConfig.v0.1"
    assert runtime["env"]["AI_GENERATION_RUNTIME"]["default_when_openai_remote"] == (
        "openai_agents"
    )
    assert runtime["env"]["AI_GENERATION_RUNTIME"]["pgpt_default_behavior"] == (
        "responses_httpx"
    )
    assert runtime["env"]["AI_GENERATION_RUNTIME"]["pgpt_explicit_openai_agents_allowed"] is True
    assert runtime["env"]["AI_DRAFT_PACK_ORCHESTRATOR"]["default_after_p44e"] == "langgraph"
    assert runtime["rollback"]["emergency_runtime"] == "responses_httpx"
    assert runtime["rollback"]["pgpt_explicit_sdk_runtime"] == "openai_agents"
    assert runtime["public_request_flag_added"] is False


def test_p44_policy_disables_unsafe_tracing_and_langgraph_persistence() -> None:
    contract = _yaml(P44_CONTRACT)
    openai_policy = contract["openai_agents_adapter"]["trace_policy"]
    langgraph_policy = contract["langgraph_orchestrator"]["persistence_policy"]

    assert openai_policy["set_tracing_disabled"] is True
    assert openai_policy["run_config"]["tracing_disabled"] is True
    assert openai_policy["run_config"]["trace_include_sensitive_data"] is False
    assert openai_policy["env_locks"]["OPENAI_AGENTS_DONT_LOG_MODEL_DATA"] == "1"
    assert openai_policy["env_locks"]["OPENAI_AGENTS_DONT_LOG_TOOL_DATA"] == "1"
    assert langgraph_policy["checkpointer"] is False
    assert langgraph_policy["db_backed_checkpointers_allowed"] is False
    assert langgraph_policy["platform_db_remains_only_persistent_workflow_store"] is True


def test_p44_docs_state_active_adoption_without_conversion_readiness() -> None:
    docs = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (PROJECT, ARCHITECTURE, POLICY, TOOLS, EVAL_SPEC, AGENT_RUNTIME_README)
    )

    assert "P44" in docs
    assert "OpenAI Agents SDK" in docs
    assert "LangGraph" in docs
    assert "FrameworkRuntimeConfig.v0.1" in docs
    assert "generated artifacts" in docs
    assert "production_ready: false" in docs or "productionReady=false" in docs
    assert "procedure execution" in docs
    assert "row-data" in docs or "row data" in docs
    assert "source apply" in docs
    assert "deploy" in docs


def test_p44_contract_forbids_public_surface_and_raw_storage() -> None:
    contract = _yaml(P44_CONTRACT)

    assert all(contract["forbidden_behavior"].values())
    assert contract["storage_policy"]["store_raw_prompt"] is False
    assert contract["storage_policy"]["store_raw_provider_response"] is False
    assert contract["storage_policy"]["store_raw_sp_definition"] is False
    assert contract["storage_policy"]["store_row_data"] is False
    assert contract["storage_policy"]["store_langgraph_checkpoint_state"] is False
