from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass

from ai_agent_runtime.ai_draft_pack_orchestrator import (
    AiDraftPackOrchestrator,
    LangGraphAiDraftPackOrchestrator,
)
from ai_agent_runtime.framework_adapter import (
    OPENAI_AGENTS_ENDPOINT_CUSTOM_COMPATIBLE,
    OPENAI_AGENTS_ENDPOINT_OFFICIAL_OPENAI,
    OPENAI_AGENTS_ENDPOINT_PGPT_COMPATIBLE,
    AiGenerationFrameworkAdapter,
    OpenAIAgentsFrameworkAdapter,
    openai_agents_endpoint_class_from_env,
)
from ai_agent_runtime.framework_model_gateway import openai_agents_framework_model_gateway
from ai_agent_runtime.gateway import (
    REMOTE_PROVIDER_OPENAI,
    REMOTE_PROVIDER_PGPT,
    ModelGateway,
    remote_provider_from_env,
)

FRAMEWORK_RUNTIME_CONFIG_VERSION = "FrameworkRuntimeConfig.v0.1"
AI_GENERATION_RUNTIME_OPENAI_AGENTS = "openai_agents"
AI_GENERATION_RUNTIME_RESPONSES_HTTPX = "responses_httpx"
AI_DRAFT_PACK_ORCHESTRATOR_LANGGRAPH = "langgraph"
AI_DRAFT_PACK_ORCHESTRATOR_INLINE = "inline"
P44_OPENAI_AGENTS_LIVE_GATE = "P44_OPENAI_AGENTS_LIVE_GATE"
P44_OPENAI_AGENTS_LIVE_REQUIRED = "P44_OPENAI_AGENTS_LIVE_REQUIRED"
OPENAI_AGENTS_TRACE_ENV_LOCKS = {
    "OPENAI_AGENTS_DISABLE_TRACING": "1",
    "OPENAI_AGENTS_TRACE_INCLUDE_SENSITIVE_DATA": "0",
    "OPENAI_AGENTS_DONT_LOG_MODEL_DATA": "1",
    "OPENAI_AGENTS_DONT_LOG_TOOL_DATA": "1",
}
OPENAI_AGENTS_OFFICIAL_BASE_URL_REQUIREMENT = (
    "OPENAI_BASE_URL empty_or_https://api.openai.com/v1"
)
OPENAI_AGENTS_COMPATIBLE_ENDPOINT_REQUIREMENT = (
    "OPENAI_BASE_URL_or_OPENAI_RESPONSES_URL_required_for_pgpt_compatible_agents"
)
OPENAI_AGENTS_PGPT_RUNTIME_REQUIREMENT = (
    "AI_GENERATION_RUNTIME=openai_agents when LLM_REMOTE_PROVIDER=pgpt"
)


@dataclass(frozen=True)
class FrameworkRuntimeConfig:
    config_version: str = FRAMEWORK_RUNTIME_CONFIG_VERSION
    ai_generation_runtime: str = AI_GENERATION_RUNTIME_RESPONSES_HTTPX
    structured_llm_runtime: str = AI_GENERATION_RUNTIME_RESPONSES_HTTPX
    ai_draft_pack_orchestrator: str = AI_DRAFT_PACK_ORCHESTRATOR_INLINE
    remote_provider: str = REMOTE_PROVIDER_OPENAI
    remote_enabled: bool = False
    rollback_path: str = AI_GENERATION_RUNTIME_RESPONSES_HTTPX
    generated_artifacts_production_ready: bool = False


@dataclass(frozen=True)
class FrameworkRuntimeSelection:
    config: FrameworkRuntimeConfig
    framework_adapter: AiGenerationFrameworkAdapter | None = None
    ai_draft_pack_orchestrator: AiDraftPackOrchestrator | None = None


def framework_runtime_config_from_env() -> FrameworkRuntimeConfig:
    remote_enabled = os.getenv("LLM_ENABLE_REMOTE", "0").strip() == "1"
    provider = remote_provider_from_env()
    requested_generation_runtime = os.getenv("AI_GENERATION_RUNTIME", "").strip().lower()
    requested_structured_runtime = os.getenv("AI_STRUCTURED_LLM_RUNTIME", "").strip().lower()
    requested_orchestrator = os.getenv("AI_DRAFT_PACK_ORCHESTRATOR", "").strip().lower()

    if provider == REMOTE_PROVIDER_PGPT and not requested_generation_runtime:
        generation_runtime = AI_GENERATION_RUNTIME_RESPONSES_HTTPX
    elif requested_generation_runtime:
        generation_runtime = _normalized_generation_runtime(requested_generation_runtime)
    elif remote_enabled and provider == REMOTE_PROVIDER_OPENAI:
        generation_runtime = AI_GENERATION_RUNTIME_OPENAI_AGENTS
    else:
        generation_runtime = AI_GENERATION_RUNTIME_RESPONSES_HTTPX

    if generation_runtime == AI_GENERATION_RUNTIME_OPENAI_AGENTS:
        orchestrator = (
            _normalized_orchestrator(requested_orchestrator)
            if requested_orchestrator
            else AI_DRAFT_PACK_ORCHESTRATOR_LANGGRAPH
        )
    else:
        orchestrator = AI_DRAFT_PACK_ORCHESTRATOR_INLINE

    if requested_structured_runtime:
        structured_llm_runtime = _normalized_generation_runtime(
            requested_structured_runtime
        )
    elif remote_enabled:
        structured_llm_runtime = AI_GENERATION_RUNTIME_OPENAI_AGENTS
    else:
        structured_llm_runtime = generation_runtime

    return FrameworkRuntimeConfig(
        ai_generation_runtime=generation_runtime,
        structured_llm_runtime=structured_llm_runtime,
        ai_draft_pack_orchestrator=orchestrator,
        remote_provider=provider,
        remote_enabled=remote_enabled,
    )


def build_framework_runtime_from_env(
    *,
    model_gateway: ModelGateway,
) -> FrameworkRuntimeSelection:
    config = framework_runtime_config_from_env()
    if config.ai_generation_runtime != AI_GENERATION_RUNTIME_OPENAI_AGENTS:
        return FrameworkRuntimeSelection(config=config)

    adapter = OpenAIAgentsFrameworkAdapter()
    orchestrator: AiDraftPackOrchestrator | None = None
    if config.ai_draft_pack_orchestrator == AI_DRAFT_PACK_ORCHESTRATOR_LANGGRAPH:
        orchestrator = LangGraphAiDraftPackOrchestrator(framework_adapter=adapter)
    return FrameworkRuntimeSelection(
        config=config,
        framework_adapter=adapter,
        ai_draft_pack_orchestrator=orchestrator,
    )


def build_model_gateway_runtime_from_env(
    *,
    model_gateway: ModelGateway,
) -> ModelGateway:
    config = framework_runtime_config_from_env()
    if config.structured_llm_runtime != AI_GENERATION_RUNTIME_OPENAI_AGENTS:
        return model_gateway
    return openai_agents_framework_model_gateway(fallback_gateway=model_gateway)


def openai_agents_live_gate_enabled(env: Mapping[str, str] | None = None) -> bool:
    source = os.environ if env is None else env
    return source.get(P44_OPENAI_AGENTS_LIVE_GATE, "").strip() == "1"


def openai_agents_live_gate_missing_requirements(
    env: Mapping[str, str] | None = None,
) -> list[str]:
    source = os.environ if env is None else env
    if not openai_agents_live_gate_enabled(source):
        return []
    missing: list[str] = []
    for key, expected in (("LLM_ENABLE_REMOTE", "1"), *OPENAI_AGENTS_TRACE_ENV_LOCKS.items()):
        if source.get(key, "").strip() != expected:
            missing.append(f"{key}={expected}")
    provider = _provider_from_source(source)
    if provider not in {REMOTE_PROVIDER_OPENAI, REMOTE_PROVIDER_PGPT}:
        missing.append("LLM_REMOTE_PROVIDER=openai_or_pgpt")
    if not source.get("OPENAI_API_KEY", "").strip():
        missing.append("OPENAI_API_KEY")
    endpoint_class = openai_agents_endpoint_class_from_env(source)
    if endpoint_class == OPENAI_AGENTS_ENDPOINT_OFFICIAL_OPENAI:
        pass
    elif endpoint_class == OPENAI_AGENTS_ENDPOINT_PGPT_COMPATIBLE:
        if (
            source.get("AI_GENERATION_RUNTIME", "").strip().lower()
            not in {"openai_agents", "openai-agents", "openai_agents_sdk"}
        ):
            missing.append(OPENAI_AGENTS_PGPT_RUNTIME_REQUIREMENT)
        if not (
            source.get("OPENAI_BASE_URL", "").strip()
            or source.get("OPENAI_RESPONSES_URL", "").strip()
        ):
            missing.append(OPENAI_AGENTS_COMPATIBLE_ENDPOINT_REQUIREMENT)
    elif endpoint_class == OPENAI_AGENTS_ENDPOINT_CUSTOM_COMPATIBLE:
        missing.append(OPENAI_AGENTS_OFFICIAL_BASE_URL_REQUIREMENT)
    return missing


def _provider_from_source(source: Mapping[str, str]) -> str:
    provider = source.get("LLM_REMOTE_PROVIDER", REMOTE_PROVIDER_OPENAI).strip().lower()
    if provider in {REMOTE_PROVIDER_PGPT, "p-gpt", "private-gpt"}:
        return REMOTE_PROVIDER_PGPT
    if provider in {REMOTE_PROVIDER_OPENAI, ""}:
        return REMOTE_PROVIDER_OPENAI
    return provider


def _normalized_generation_runtime(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"openai_agents", "openai-agents", "openai_agents_sdk"}:
        return AI_GENERATION_RUNTIME_OPENAI_AGENTS
    if normalized in {"responses_httpx", "responses-httpx", "baseline", "rollback"}:
        return AI_GENERATION_RUNTIME_RESPONSES_HTTPX
    return AI_GENERATION_RUNTIME_RESPONSES_HTTPX


def _normalized_orchestrator(value: str) -> str:
    normalized = value.strip().lower()
    if normalized in {"langgraph", "langgraph_ai_draft_pack"}:
        return AI_DRAFT_PACK_ORCHESTRATOR_LANGGRAPH
    if normalized in {"inline", "none", "responses_httpx"}:
        return AI_DRAFT_PACK_ORCHESTRATOR_INLINE
    return AI_DRAFT_PACK_ORCHESTRATOR_LANGGRAPH
