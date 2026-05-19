from __future__ import annotations

import json
import logging
import os
import re
import time
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol

from ai_agent_runtime.ai_draft_pack import (
    AiJavaMyBatisDraftPackOutput,
    parse_ai_java_mybatis_draft_pack_json,
    validate_ai_java_mybatis_draft_pack_output,
)
from ai_agent_runtime.gateway import (
    REMOTE_PROVIDER_OPENAI,
    REMOTE_PROVIDER_PGPT,
    ModelGatewayError,
    _parse_structured_output,
    remote_provider_from_env,
)
from ai_agent_runtime.models import (
    AgentRunStatus,
    ModelInvocationRecord,
    ModelProfile,
    RenderedPrompt,
    stable_json_hash,
)
from ai_agent_runtime.storage_safety import storage_safety_findings

AI_GENERATION_FRAMEWORK_ADAPTER_VERSION = "AiGenerationFrameworkAdapter.v0.1"
FRAMEWORK_RUNTIME_SUMMARY_VERSION = "FrameworkRuntimeSummary.v0.1"
P43_FRAMEWORK_RAW_TRACE_BLOCKED = "P43_FRAMEWORK_RAW_TRACE_BLOCKED"
P43_FRAMEWORK_TOOL_CONTEXT_BLOCKED = "P43_FRAMEWORK_TOOL_CONTEXT_BLOCKED"
P44_OPENAI_AGENTS_ADAPTER_FAILED = "P44_OPENAI_AGENTS_ADAPTER_FAILED"
P44_OPENAI_AGENTS_SDK_UNAVAILABLE = "P44_OPENAI_AGENTS_SDK_UNAVAILABLE"
P44_OPENAI_AGENTS_TRACE_POLICY = "P44_OPENAI_AGENTS_TRACE_POLICY"
AI_STRUCTURED_FRAMEWORK_ADAPTER_VERSION = "AiStructuredFrameworkAdapter.v0.1"
P48_OPENAI_AGENTS_STRUCTURED_ADAPTER_FAILED = (
    "P48_OPENAI_AGENTS_STRUCTURED_ADAPTER_FAILED"
)
P48_OPENAI_AGENTS_STRUCTURED_OUTPUT_INVALID = (
    "P48_OPENAI_AGENTS_STRUCTURED_OUTPUT_INVALID"
)
OPENAI_AGENTS_ENDPOINT_OFFICIAL_OPENAI = "official_openai"
OPENAI_AGENTS_ENDPOINT_PGPT_COMPATIBLE = "pgpt_compatible"
OPENAI_AGENTS_ENDPOINT_CUSTOM_COMPATIBLE = "custom_compatible"
OPENAI_AGENTS_COMPATIBLE_API_RESPONSES = "responses"
OPENAI_AGENTS_COMPATIBLE_API_CHAT_COMPLETIONS = "chat_completions"

_ADAPTER_COMPONENT = "ai_generation_framework_adapter"
_FRAMEWORK_TRACE_CONTRACTS = frozenset(
    {
        AI_GENERATION_FRAMEWORK_ADAPTER_VERSION,
        AI_STRUCTURED_FRAMEWORK_ADAPTER_VERSION,
    }
)
_STRUCTURED_FRAMEWORK_STAGES = frozenset(
    {
        "llm_semantic_analysis",
        "metadata_tool_planning",
        "metadata_analysis",
        "platform_tool_planning",
        "sp_operation_model",
    }
)
_FRAMEWORK_STAGES = frozenset(
    {"file_inventory", "file_content", "repair", *_STRUCTURED_FRAMEWORK_STAGES}
)
_TRACE_SUMMARY_FIELDS = frozenset(
    {
        "component",
        "adapterContract",
        "adapterId",
        "candidateFramework",
        "targetRefHash",
        "stage",
        "status",
        "eventCount",
        "componentIds",
        "blockerIds",
        "failureCodes",
        "metrics",
        "traceHash",
    }
)
_SAFE_TRACE_METRIC = re.compile(r"^[A-Za-z][A-Za-z0-9]*(?:Count|Ms|Bytes|Tokens)$")
_FORBIDDEN_TRACE_TEXT_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\braw\s+guide\s+body\b",
        r"\braw\s+provider\s+response\b",
        r"\braw\s+prompt\b",
        r"\braw\s+sp\s+definition\b",
        r"\brow\s+data\b",
        r"\bprocedure\s+execution\b",
        r"\bexecute\s+(?:stored\s+)?procedure\b",
        r"\bddl\s*/?\s*dml\s+apply\b",
        r"\bapply\s+business\s+db\s+(?:ddl|dml)\b",
        r"\bsource\s+apply\b",
        r"\bgenerated\s+source\s+apply\b",
        r"\bdeploy(?:ed|ment)?\b",
        r"\bpublic\s+(?:class|interface)\s+\w+",
        r"<\s*/?\s*mapper\b",
    )
)


@dataclass(frozen=True)
class AiGenerationFrameworkAdapterRequest:
    target_ref: str
    sanitized_draft_context: Mapping[str, Any]
    expected_inventory: Sequence[Mapping[str, Any]]
    quality_gates: Mapping[str, Any]
    allowed_evidence_refs: Sequence[str]
    prompt: RenderedPrompt
    profile: ModelProfile
    stage: str
    repair_context: Mapping[str, Any] | None = None


class AiGenerationFrameworkAdapter(Protocol):
    adapter_id: str
    candidate_framework: str

    def plan_file_inventory(
        self,
        *,
        request: AiGenerationFrameworkAdapterRequest,
    ) -> ModelInvocationRecord:
        ...

    def draft_file_content(
        self,
        *,
        request: AiGenerationFrameworkAdapterRequest,
    ) -> ModelInvocationRecord:
        ...

    def repair_draft_pack(
        self,
        *,
        request: AiGenerationFrameworkAdapterRequest,
    ) -> ModelInvocationRecord:
        ...

    def summarize_trace(
        self,
        *,
        request: AiGenerationFrameworkAdapterRequest,
        stage: str,
        status: str,
        events: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class AiStructuredFrameworkAdapterRequest:
    target_ref: str
    prompt: RenderedPrompt
    profile: ModelProfile
    schema_name: str
    stage: str
    parser: Callable[[str], Any]
    invalid_code: str
    allowed_tool_names: Sequence[str] = ()
    output_type: Any | None = None


class AiStructuredFrameworkAdapter(Protocol):
    adapter_id: str
    candidate_framework: str

    def invoke_structured(
        self,
        *,
        request: AiStructuredFrameworkAdapterRequest,
    ) -> ModelInvocationRecord:
        ...


@dataclass(frozen=True)
class OpenAIAgentsFrameworkAdapter:
    adapter_id: str = "openai_agents_sdk"
    candidate_framework: str = "openai_agents_sdk"
    runner: Callable[[Any, str, Any], Any] | None = None
    agent_factory: Callable[[AiGenerationFrameworkAdapterRequest], Any] | None = None

    def plan_file_inventory(
        self,
        *,
        request: AiGenerationFrameworkAdapterRequest,
    ) -> ModelInvocationRecord:
        validate_framework_tool_context(request)
        return self._run_agent_stage(request=request, stage="file_inventory")

    def draft_file_content(
        self,
        *,
        request: AiGenerationFrameworkAdapterRequest,
    ) -> ModelInvocationRecord:
        validate_framework_tool_context(request)
        return self._run_agent_stage(request=request, stage="file_content")

    def repair_draft_pack(
        self,
        *,
        request: AiGenerationFrameworkAdapterRequest,
    ) -> ModelInvocationRecord:
        validate_framework_tool_context(request)
        return self._run_agent_stage(request=request, stage="repair")

    def summarize_trace(
        self,
        *,
        request: AiGenerationFrameworkAdapterRequest,
        stage: str,
        status: str,
        events: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        return summarize_framework_trace(
            adapter_id=self.adapter_id,
            candidate_framework=self.candidate_framework,
            target_ref=request.target_ref,
            stage=stage,
            status=status,
            events=events,
        )

    def _run_agent_stage(
        self,
        *,
        request: AiGenerationFrameworkAdapterRequest,
        stage: str,
    ) -> ModelInvocationRecord:
        _enforce_openai_agents_trace_policy()
        started = time.monotonic()
        try:
            result = self._run_agents_sdk(request=request)
            structured_output = _coerce_openai_agents_output(
                result,
                allowed_evidence_refs=request.allowed_evidence_refs,
            )
        except ModelGatewayError:
            raise
        except Exception as exc:  # noqa: BLE001 - diagnostics must stay sanitized
            raise ModelGatewayError(
                "OpenAI Agents SDK adapter failed before producing a valid draft pack.",
                code=P44_OPENAI_AGENTS_ADAPTER_FAILED,
                provider_error={
                    "type": "openai_agents_framework_adapter",
                    "code": P44_OPENAI_AGENTS_ADAPTER_FAILED,
                    "stage": _safe_stage(stage),
                    "errorClass": exc.__class__.__name__,
                },
            ) from None
        latency_ms = int((time.monotonic() - started) * 1000)
        token_usage = _openai_agents_token_usage(result)
        endpoint_class = openai_agents_endpoint_class_from_env()
        sdk_transport = (
            openai_agents_compatible_api_from_env()
            if endpoint_class != OPENAI_AGENTS_ENDPOINT_OFFICIAL_OPENAI
            else OPENAI_AGENTS_COMPATIBLE_API_RESPONSES
        )
        component = self.summarize_trace(
            request=request,
            stage=stage,
            status=AgentRunStatus.SUCCEEDED.value,
            events=(
                {
                    "eventType": "openai_agents_sdk_run",
                    "componentId": (
                        f"openai_agents_{stage}_{endpoint_class}_{sdk_transport}"
                    ),
                    "outputHash": stable_json_hash(structured_output),
                    "fileCount": len(structured_output.get("files", [])),
                    "latencyMs": latency_ms,
                    "inputTokens": token_usage.get("inputTokens", 0),
                    "outputTokens": token_usage.get("outputTokens", 0),
                    "totalTokens": token_usage.get("totalTokens", 0),
                },
            ),
        )
        return ModelInvocationRecord(
            provider="openai-agents-sdk",
            model=request.profile.model,
            model_profile_id=request.profile.profile_id,
            model_registry_ref=request.profile.registry_ref,
            reasoning_effort=request.profile.reasoning_effort,
            prompt_version=request.prompt.prompt_version,
            output_schema_version=request.prompt.output_schema_version,
            input_hash=request.prompt.input_hash,
            prompt_hash=request.prompt.prompt_hash,
            output_hash=stable_json_hash(structured_output),
            status=AgentRunStatus.SUCCEEDED,
            structured_output=structured_output,
            token_usage=token_usage,
            latency_ms=latency_ms,
            provider_request_id=_openai_agents_provider_request_id(result),
            component_invocations=(component,),
        )

    def _run_agents_sdk(self, *, request: AiGenerationFrameworkAdapterRequest) -> Any:
        if self.runner is not None:
            return self.runner(
                self._build_agent(request=request),
                request.prompt.user_prompt,
                _openai_agents_run_config(),
            )
        agents = _agents_sdk()
        return agents.Runner.run_sync(
            self._build_agent(request=request),
            request.prompt.user_prompt,
            run_config=_openai_agents_run_config(),
        )

    def _build_agent(self, *, request: AiGenerationFrameworkAdapterRequest) -> Any:
        if self.agent_factory is not None:
            return self.agent_factory(request)
        agents = _agents_sdk()
        agent_kwargs = {
            "name": f"AI Draft Pack {request.stage}",
            "instructions": request.prompt.system_prompt,
            "model": _openai_agents_model_for_profile(profile=request.profile),
        }
        if _openai_agents_native_structured_output_enabled():
            agent_kwargs["output_type"] = AiJavaMyBatisDraftPackOutput
        return agents.Agent(**agent_kwargs)


@dataclass(frozen=True)
class OpenAIAgentsStructuredAdapter:
    adapter_id: str = "openai_agents_sdk_structured"
    candidate_framework: str = "openai_agents_sdk"
    runner: Callable[[Any, str, Any], Any] | None = None
    agent_factory: Callable[[AiStructuredFrameworkAdapterRequest], Any] | None = None

    def invoke_structured(
        self,
        *,
        request: AiStructuredFrameworkAdapterRequest,
    ) -> ModelInvocationRecord:
        _enforce_openai_agents_trace_policy()
        started = time.monotonic()
        try:
            result = self._run_agents_sdk(request=request)
            structured_output, normalizer_components = _coerce_openai_agents_structured_output(
                result,
                request=request,
            )
        except ModelGatewayError:
            raise
        except Exception as exc:  # noqa: BLE001 - diagnostics must stay sanitized
            raise ModelGatewayError(
                "OpenAI Agents SDK structured adapter failed before valid output.",
                code=P48_OPENAI_AGENTS_STRUCTURED_ADAPTER_FAILED,
                provider_error={
                    "type": "openai_agents_structured_adapter",
                    "code": P48_OPENAI_AGENTS_STRUCTURED_ADAPTER_FAILED,
                    "stage": _safe_stage(request.stage),
                    "schemaName": _safe_schema_name(request.schema_name),
                    "errorClass": exc.__class__.__name__,
                },
            ) from None
        latency_ms = int((time.monotonic() - started) * 1000)
        token_usage = _openai_agents_token_usage(result)
        endpoint_class = openai_agents_endpoint_class_from_env()
        sdk_transport = (
            openai_agents_compatible_api_from_env()
            if endpoint_class != OPENAI_AGENTS_ENDPOINT_OFFICIAL_OPENAI
            else OPENAI_AGENTS_COMPATIBLE_API_RESPONSES
        )
        component = summarize_framework_trace(
            adapter_contract=AI_STRUCTURED_FRAMEWORK_ADAPTER_VERSION,
            adapter_id=self.adapter_id,
            candidate_framework=self.candidate_framework,
            target_ref=request.target_ref,
            stage=request.stage,
            status=AgentRunStatus.SUCCEEDED.value,
            events=(
                {
                    "eventType": "openai_agents_sdk_structured_run",
                    "componentId": (
                        f"openai_agents_{request.schema_name}_{endpoint_class}_{sdk_transport}"
                    ),
                    "outputHash": stable_json_hash(structured_output),
                    "latencyMs": latency_ms,
                    "inputTokens": token_usage.get("inputTokens", 0),
                    "outputTokens": token_usage.get("outputTokens", 0),
                    "totalTokens": token_usage.get("totalTokens", 0),
                    "outputKeyCount": len(structured_output),
                },
            ),
        )
        return ModelInvocationRecord(
            provider="openai-agents-sdk",
            model=request.profile.model,
            model_profile_id=request.profile.profile_id,
            model_registry_ref=request.profile.registry_ref,
            reasoning_effort=request.profile.reasoning_effort,
            prompt_version=request.prompt.prompt_version,
            output_schema_version=request.prompt.output_schema_version,
            input_hash=request.prompt.input_hash,
            prompt_hash=request.prompt.prompt_hash,
            output_hash=stable_json_hash(structured_output),
            status=AgentRunStatus.SUCCEEDED,
            structured_output=structured_output,
            token_usage=token_usage,
            latency_ms=latency_ms,
            provider_request_id=_openai_agents_provider_request_id(result),
            component_invocations=(*normalizer_components, component),
        )

    def _run_agents_sdk(self, *, request: AiStructuredFrameworkAdapterRequest) -> Any:
        if self.runner is not None:
            return self.runner(
                self._build_agent(request=request),
                request.prompt.user_prompt,
                _openai_agents_run_config(),
            )
        agents = _agents_sdk()
        return agents.Runner.run_sync(
            self._build_agent(request=request),
            request.prompt.user_prompt,
            run_config=_openai_agents_run_config(),
        )

    def _build_agent(self, *, request: AiStructuredFrameworkAdapterRequest) -> Any:
        if self.agent_factory is not None:
            return self.agent_factory(request)
        agents = _agents_sdk()
        agent_kwargs = {
            "name": f"Structured {request.stage}",
            "instructions": request.prompt.system_prompt,
            "model": _openai_agents_model_for_profile(profile=request.profile),
        }
        if (
            request.output_type is not None
            and _openai_agents_native_structured_output_enabled()
        ):
            agent_kwargs["output_type"] = request.output_type
        return agents.Agent(**agent_kwargs)


def openai_agents_endpoint_class_from_env(
    env: Mapping[str, str] | None = None,
) -> str:
    source = os.environ if env is None else env
    provider = _remote_provider_from_mapping(source)
    if provider == REMOTE_PROVIDER_PGPT:
        return OPENAI_AGENTS_ENDPOINT_PGPT_COMPATIBLE
    base_url = source.get("OPENAI_BASE_URL", "").strip()
    if not base_url or _openai_base_url_is_official(base_url):
        return OPENAI_AGENTS_ENDPOINT_OFFICIAL_OPENAI
    return OPENAI_AGENTS_ENDPOINT_CUSTOM_COMPATIBLE


def openai_agents_sdk_base_url_from_env(
    env: Mapping[str, str] | None = None,
) -> str:
    source = os.environ if env is None else env
    exact_url = source.get("OPENAI_RESPONSES_URL", "").strip().rstrip("/")
    if exact_url:
        return _sdk_base_url_from_responses_url(exact_url)
    base_url = source.get("OPENAI_BASE_URL", "").strip().rstrip("/")
    if not base_url:
        return "https://api.openai.com/v1"
    if base_url.endswith("/responses"):
        return _sdk_base_url_from_responses_url(base_url)
    if base_url.endswith("/v1"):
        return base_url
    return f"{base_url}/v1"


def openai_agents_compatible_api_from_env(
    env: Mapping[str, str] | None = None,
) -> str:
    source = os.environ if env is None else env
    value = source.get("OPENAI_AGENTS_COMPATIBLE_API", "").strip().lower()
    if value in {"chat", "chat_completion", "chat_completions", "chat-completions"}:
        return OPENAI_AGENTS_COMPATIBLE_API_CHAT_COMPLETIONS
    return OPENAI_AGENTS_COMPATIBLE_API_RESPONSES


def _openai_agents_native_structured_output_enabled() -> bool:
    """Use native output_type only for the official OpenAI endpoint.

    Some OpenAI-compatible gateways accept Responses-style JSON generation but do not
    support the Agents SDK structured-output payload shape. The adapter still validates
    the final output with AiJavaMyBatisDraftPack.v0.1 immediately after the run.
    """

    return openai_agents_endpoint_class_from_env() == OPENAI_AGENTS_ENDPOINT_OFFICIAL_OPENAI


def _openai_agents_model_for_request(
    *,
    request: AiGenerationFrameworkAdapterRequest,
) -> Any:
    return _openai_agents_model_for_profile(profile=request.profile)


def _openai_agents_model_for_profile(
    *,
    profile: ModelProfile,
) -> Any:
    endpoint_class = openai_agents_endpoint_class_from_env()
    if endpoint_class == OPENAI_AGENTS_ENDPOINT_OFFICIAL_OPENAI:
        return profile.model
    agents = _agents_sdk()
    client = _openai_agents_compatible_client(agents=agents)
    compatible_api = openai_agents_compatible_api_from_env()
    model_class_name = (
        "OpenAIChatCompletionsModel"
        if compatible_api == OPENAI_AGENTS_COMPATIBLE_API_CHAT_COMPLETIONS
        else "OpenAIResponsesModel"
    )
    model_class = getattr(agents, model_class_name, None)
    if model_class is None:
        raise ModelGatewayError(
            "OpenAI Agents SDK compatible model transport is unavailable.",
            code=P44_OPENAI_AGENTS_SDK_UNAVAILABLE,
            provider_error={
                "type": "openai_agents_framework_adapter",
                "code": P44_OPENAI_AGENTS_SDK_UNAVAILABLE,
                "dependency": model_class_name,
                "endpointClass": endpoint_class,
                "sdkTransport": compatible_api,
            },
        )
    return model_class(model=profile.model, openai_client=client)


def _openai_agents_compatible_client(*, agents: Any) -> Any:
    async_openai = getattr(agents, "AsyncOpenAI", None)
    if async_openai is None:
        try:
            from openai import AsyncOpenAI as async_openai  # type: ignore[no-redef]
        except Exception as exc:  # noqa: BLE001
            raise ModelGatewayError(
                "OpenAI compatible client dependency is unavailable.",
                code=P44_OPENAI_AGENTS_SDK_UNAVAILABLE,
                provider_error={
                    "type": "openai_agents_framework_adapter",
                    "code": P44_OPENAI_AGENTS_SDK_UNAVAILABLE,
                    "dependency": "AsyncOpenAI",
                },
            ) from exc
    api_key = os.getenv("OPENAI_API_KEY", "").strip()
    return async_openai(
        api_key=api_key or None,
        base_url=openai_agents_sdk_base_url_from_env(),
    )


def _sdk_base_url_from_responses_url(value: str) -> str:
    normalized = value.rstrip("/")
    suffix = "/responses"
    if normalized.endswith(suffix):
        return normalized[: -len(suffix)].rstrip("/")
    return normalized


def _remote_provider_from_mapping(source: Mapping[str, str]) -> str:
    if source is os.environ:
        return remote_provider_from_env()
    provider = source.get("LLM_REMOTE_PROVIDER", REMOTE_PROVIDER_OPENAI).strip().lower()
    if provider in {REMOTE_PROVIDER_PGPT, "p-gpt", "private-gpt"}:
        return REMOTE_PROVIDER_PGPT
    return REMOTE_PROVIDER_OPENAI


def _openai_base_url_is_official(value: str) -> bool:
    try:
        from urllib.parse import urlparse

        return (urlparse(value).hostname or "").lower() == "api.openai.com"
    except Exception:  # noqa: BLE001 - malformed env should take conservative path
        return False


def _enforce_openai_agents_trace_policy() -> None:
    os.environ["OPENAI_AGENTS_DISABLE_TRACING"] = "1"
    os.environ["OPENAI_AGENTS_TRACE_INCLUDE_SENSITIVE_DATA"] = "0"
    os.environ["OPENAI_AGENTS_DONT_LOG_MODEL_DATA"] = "1"
    os.environ["OPENAI_AGENTS_DONT_LOG_TOOL_DATA"] = "1"
    logging.getLogger("openai.agents").setLevel(logging.CRITICAL)
    agents = _agents_sdk()
    disable_tracing = getattr(agents, "set_tracing_disabled", None)
    if not callable(disable_tracing):
        raise ModelGatewayError(
            "OpenAI Agents SDK tracing policy hook is unavailable.",
            code=P44_OPENAI_AGENTS_TRACE_POLICY,
            provider_error={
                "type": "openai_agents_trace_policy",
                "code": P44_OPENAI_AGENTS_TRACE_POLICY,
                "traceDisabled": "false",
            },
        )
    disable_tracing(True)


def _openai_agents_run_config() -> Any:
    agents = _agents_sdk()
    run_config = getattr(agents, "RunConfig", None)
    if run_config is None:
        raise ModelGatewayError(
            "OpenAI Agents SDK RunConfig is unavailable.",
            code=P44_OPENAI_AGENTS_TRACE_POLICY,
            provider_error={
                "type": "openai_agents_trace_policy",
                "code": P44_OPENAI_AGENTS_TRACE_POLICY,
                "traceDisabled": "false",
            },
        )
    try:
        return run_config(
            tracing_disabled=True,
            trace_include_sensitive_data=False,
        )
    except TypeError:
        return run_config(tracing_disabled=True)


def _agents_sdk() -> Any:
    try:
        import agents  # type: ignore[import-not-found]
    except Exception as exc:  # noqa: BLE001 - import diagnostics must stay sanitized
        raise ModelGatewayError(
            "OpenAI Agents SDK dependency is unavailable.",
            code=P44_OPENAI_AGENTS_SDK_UNAVAILABLE,
            provider_error={
                "type": "openai_agents_framework_adapter",
                "code": P44_OPENAI_AGENTS_SDK_UNAVAILABLE,
                "dependency": "openai-agents",
            },
        ) from exc
    return agents


def _coerce_openai_agents_output(
    result: Any,
    *,
    allowed_evidence_refs: Sequence[str],
) -> dict[str, Any]:
    output = getattr(result, "final_output", result)
    try:
        if isinstance(output, AiJavaMyBatisDraftPackOutput):
            model = output
        elif hasattr(output, "to_storage_dict") and callable(output.to_storage_dict):
            model = validate_ai_java_mybatis_draft_pack_output(
                output.to_storage_dict(),
                allowed_evidence_refs=allowed_evidence_refs,
            )
        elif hasattr(output, "model_dump") and callable(output.model_dump):
            model = validate_ai_java_mybatis_draft_pack_output(
                output.model_dump(by_alias=True, mode="json"),
                allowed_evidence_refs=allowed_evidence_refs,
            )
        elif isinstance(output, Mapping):
            model = validate_ai_java_mybatis_draft_pack_output(
                output,
                allowed_evidence_refs=allowed_evidence_refs,
            )
        elif isinstance(output, str):
            model = parse_ai_java_mybatis_draft_pack_json(
                output,
                allowed_evidence_refs=allowed_evidence_refs,
            )
        else:
            raise TypeError(output.__class__.__name__)
    except Exception as exc:  # noqa: BLE001 - raw adapter output must not be stored
        raise ModelGatewayError(
            "OpenAI Agents SDK output failed AiJavaMyBatisDraftPack validation.",
            code="OPENAI_AI_DRAFT_PACK_INVALID",
            provider_error={
                "type": "openai_agents_framework_adapter",
                "code": "OPENAI_AI_DRAFT_PACK_INVALID",
                "outputHash": _safe_output_hash(output),
                "errorClass": exc.__class__.__name__,
            },
        ) from exc
    return model.to_storage_dict()


def _coerce_openai_agents_structured_output(
    result: Any,
    *,
    request: AiStructuredFrameworkAdapterRequest,
) -> tuple[dict[str, Any], tuple[dict[str, Any], ...]]:
    output = getattr(result, "final_output", result)
    output_text = _structured_output_text(output)
    try:
        model, normalizer_components = _parse_structured_output(
            output_text=output_text,
            parser=request.parser,
            schema_name=request.schema_name,
            allowed_tool_names=request.allowed_tool_names,
            provider=remote_provider_from_env(),
        )
    except Exception as exc:  # noqa: BLE001 - raw adapter output must not be stored
        raise ModelGatewayError(
            "OpenAI Agents SDK structured output failed validation.",
            code=request.invalid_code or P48_OPENAI_AGENTS_STRUCTURED_OUTPUT_INVALID,
            provider_error={
                "type": "openai_agents_structured_adapter",
                "code": request.invalid_code
                or P48_OPENAI_AGENTS_STRUCTURED_OUTPUT_INVALID,
                "stage": _safe_stage(request.stage),
                "schemaName": _safe_schema_name(request.schema_name),
                "outputHash": _safe_output_hash(output),
                "errorClass": exc.__class__.__name__,
            },
        ) from exc
    if hasattr(model, "to_storage_dict") and callable(model.to_storage_dict):
        return model.to_storage_dict(), tuple(normalizer_components)
    if hasattr(model, "model_dump") and callable(model.model_dump):
        return (
            model.model_dump(by_alias=True, mode="json"),
            tuple(normalizer_components),
        )
    if isinstance(model, Mapping):
        return dict(model), tuple(normalizer_components)
    raise ModelGatewayError(
        "OpenAI Agents SDK structured output parser returned an unsupported model.",
        code=request.invalid_code or P48_OPENAI_AGENTS_STRUCTURED_OUTPUT_INVALID,
        provider_error={
            "type": "openai_agents_structured_adapter",
            "code": request.invalid_code or P48_OPENAI_AGENTS_STRUCTURED_OUTPUT_INVALID,
            "stage": _safe_stage(request.stage),
            "schemaName": _safe_schema_name(request.schema_name),
            "outputClass": model.__class__.__name__,
        },
    )


def _structured_output_text(output: Any) -> str:
    if isinstance(output, str):
        return output
    if isinstance(output, Mapping):
        return json.dumps(output, ensure_ascii=False, separators=(",", ":"))
    if hasattr(output, "to_storage_dict") and callable(output.to_storage_dict):
        return json.dumps(
            output.to_storage_dict(),
            ensure_ascii=False,
            separators=(",", ":"),
        )
    if hasattr(output, "model_dump") and callable(output.model_dump):
        return json.dumps(
            output.model_dump(by_alias=True, mode="json"),
            ensure_ascii=False,
            separators=(",", ":"),
        )
    raise TypeError(output.__class__.__name__)


def _safe_output_hash(output: Any) -> str:
    if isinstance(output, Mapping):
        return stable_json_hash(output)
    if hasattr(output, "to_storage_dict") and callable(output.to_storage_dict):
        return stable_json_hash(output.to_storage_dict())
    if hasattr(output, "model_dump") and callable(output.model_dump):
        return stable_json_hash(output.model_dump(by_alias=True, mode="json"))
    if isinstance(output, str):
        return stable_json_hash({"textLength": len(output), "textSha": stable_json_hash(output)})
    return stable_json_hash({"outputClass": output.__class__.__name__})


def _openai_agents_token_usage(result: Any) -> dict[str, int]:
    usage = getattr(result, "usage", None)
    if usage is None and isinstance(result, Mapping):
        usage = result.get("usage")
    mapping = _usage_mapping(usage)
    input_tokens = _usage_int(mapping, "inputTokens", "input_tokens", "prompt_tokens")
    output_tokens = _usage_int(mapping, "outputTokens", "output_tokens", "completion_tokens")
    total_tokens = _usage_int(mapping, "totalTokens", "total_tokens")
    if total_tokens == 0 and (input_tokens or output_tokens):
        total_tokens = input_tokens + output_tokens
    return {
        "inputTokens": input_tokens,
        "outputTokens": output_tokens,
        "totalTokens": total_tokens,
    }


def _usage_mapping(usage: Any) -> Mapping[str, Any]:
    if isinstance(usage, Mapping):
        return usage
    if usage is None:
        return {}
    return {
        key: getattr(usage, key)
        for key in (
            "inputTokens",
            "input_tokens",
            "prompt_tokens",
            "outputTokens",
            "output_tokens",
            "completion_tokens",
            "totalTokens",
            "total_tokens",
        )
        if hasattr(usage, key)
    }


def _usage_int(mapping: Mapping[str, Any], *keys: str) -> int:
    for key in keys:
        value = mapping.get(key)
        if isinstance(value, int) and not isinstance(value, bool):
            return value
    return 0


def _openai_agents_provider_request_id(result: Any) -> str | None:
    for key in ("response_id", "last_response_id", "run_id", "id"):
        value = getattr(result, key, None)
        if value:
            return str(value)
    if isinstance(result, Mapping):
        for key in ("response_id", "last_response_id", "run_id", "id"):
            value = result.get(key)
            if value:
                return str(value)
    return None


def summarize_framework_trace(
    *,
    adapter_contract: str = AI_GENERATION_FRAMEWORK_ADAPTER_VERSION,
    adapter_id: str,
    candidate_framework: str,
    target_ref: str,
    stage: str,
    status: str,
    events: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    findings = _trace_storage_findings(events)
    if findings:
        raise ModelGatewayError(
            "Framework adapter trace contains forbidden storage material.",
            code=P43_FRAMEWORK_RAW_TRACE_BLOCKED,
            provider_error={
                "type": "framework_adapter_trace_policy",
                "code": P43_FRAMEWORK_RAW_TRACE_BLOCKED,
                "stage": _safe_stage(stage),
                "findingCount": str(len(findings)),
                "findings": ",".join(findings[:8]),
            },
        )
    summary = {
        "component": _ADAPTER_COMPONENT,
        "adapterContract": adapter_contract,
        "adapterId": adapter_id,
        "candidateFramework": candidate_framework,
        "targetRefHash": stable_json_hash({"targetRef": target_ref}),
        "stage": stage,
        "status": status,
        "eventCount": len(events),
        "componentIds": _trace_component_ids(events),
        "blockerIds": _trace_blocker_ids(events),
        "failureCodes": _trace_failure_codes(events),
        "metrics": _trace_numeric_metrics(events),
        "traceHash": stable_json_hash(list(events)),
    }
    validate_framework_trace_summary(summary)
    return summary


def build_framework_tool_context(
    request: AiGenerationFrameworkAdapterRequest,
) -> dict[str, Any]:
    context = request.sanitized_draft_context
    operation_model_summary = _mapping(context.get("operationModelSummary"))
    operations = _sequence_of_mappings(context.get("operations"))
    dto_blueprints = _sequence_of_mappings(context.get("dtoBlueprints"))
    statement_evidence = _sequence_of_mappings(context.get("statementEvidence"))
    review_markers = _dedupe_strings(
        [
            *_sequence(operation_model_summary.get("reviewMarkers")),
            *_sequence(context.get("reviewRequiredFacts")),
            *_sequence(request.quality_gates.get("requiredReviewMarkers")),
            *_sequence((request.repair_context or {}).get("reviewMarkers")),
        ]
    )
    return {
        "adapterContract": AI_GENERATION_FRAMEWORK_ADAPTER_VERSION,
        "stage": request.stage,
        "targetRefHash": stable_json_hash({"targetRef": request.target_ref}),
        "metadataSummary": {
            "inputParamCount": len(_sequence(context.get("inputParams"))),
            "resultShapeCount": len(_sequence(context.get("resultShape"))),
            "allowedEvidenceRefCount": len(request.allowed_evidence_refs),
            "dependencyEvidenceRefCount": len(
                _sequence(_mapping(context.get("dependencyEvidenceSummary")).get("evidenceRefs"))
            ),
            "aiToolEvidenceRefCount": len(
                _sequence(_mapping(context.get("aiToolEvidenceSummary")).get("evidenceRefs"))
            ),
            "platformToolEvidenceRefCount": len(
                _sequence(
                    _mapping(context.get("platformToolEvidenceSummary")).get("evidenceRefs")
                )
            ),
        },
        "operationSummary": {
            "schemaVersion": operation_model_summary.get("schemaVersion"),
            "operationCount": len(operations),
            "operationIds": _ids_from_items(operations, "operationId"),
            "statementEvidenceCount": len(statement_evidence),
            "statementIds": _ids_from_items(statement_evidence, "statementId"),
            "statementOperations": _ids_from_items(statement_evidence, "operation"),
            "dtoBlueprintCount": len(dto_blueprints),
            "dtoBlueprintNames": _ids_from_items(dto_blueprints, "name"),
            "reviewMarkers": review_markers,
        },
        "deterministicInventoryContract": [
            _framework_inventory_item(item) for item in request.expected_inventory
        ],
        "allowedEvidenceRefs": list(dict.fromkeys(map(str, request.allowed_evidence_refs))),
        "qualityGates": _policy_safe_mapping(request.quality_gates),
        "reviewRequiredMarkers": review_markers,
    }


def validate_framework_tool_context(
    request: AiGenerationFrameworkAdapterRequest,
) -> dict[str, Any]:
    raw_inputs: list[Mapping[str, Any]] = [
        {"sanitizedDraftContext": dict(request.sanitized_draft_context)},
        {"expectedInventory": [dict(item) for item in request.expected_inventory]},
        {"qualityGates": dict(request.quality_gates)},
        {"allowedEvidenceRefs": list(request.allowed_evidence_refs)},
    ]
    if request.repair_context is not None:
        raw_inputs.append({"repairContext": dict(request.repair_context)})
    findings = _policy_findings(raw_inputs)
    context = build_framework_tool_context(request)
    findings.extend(_policy_findings((context,)))
    if findings:
        raise ModelGatewayError(
            "Framework adapter tool context contains forbidden material.",
            code=P43_FRAMEWORK_TOOL_CONTEXT_BLOCKED,
            provider_error={
                "type": "framework_adapter_tool_context_policy",
                "code": P43_FRAMEWORK_TOOL_CONTEXT_BLOCKED,
                "stage": _safe_stage(request.stage),
                "findingCount": str(len(findings)),
                "findings": ",".join(findings[:8]),
            },
        )
    return context


def validate_framework_trace_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    findings: list[str] = []
    extra = sorted(set(map(str, summary)) - _TRACE_SUMMARY_FIELDS)
    if extra:
        findings.append("P43_FRAMEWORK_TRACE_SUMMARY_FIELD_NOT_ALLOWED")
    if summary.get("component") != _ADAPTER_COMPONENT:
        findings.append("P43_FRAMEWORK_TRACE_SUMMARY_COMPONENT_INVALID")
    if summary.get("adapterContract") not in _FRAMEWORK_TRACE_CONTRACTS:
        findings.append("P43_FRAMEWORK_TRACE_SUMMARY_CONTRACT_INVALID")
    if str(summary.get("stage") or "") not in _FRAMEWORK_STAGES:
        findings.append("P43_FRAMEWORK_TRACE_SUMMARY_STAGE_INVALID")
    for key in ("adapterId", "candidateFramework", "targetRefHash", "status", "traceHash"):
        if not str(summary.get(key) or "").strip():
            findings.append(f"P43_FRAMEWORK_TRACE_SUMMARY_{key}_MISSING")
    if not isinstance(summary.get("eventCount"), int) or isinstance(
        summary.get("eventCount"),
        bool,
    ):
        findings.append("P43_FRAMEWORK_TRACE_SUMMARY_EVENT_COUNT_INVALID")
    for key in ("componentIds", "blockerIds", "failureCodes"):
        value = summary.get(key, [])
        if not isinstance(value, Sequence) or isinstance(value, str | bytes):
            findings.append(f"P43_FRAMEWORK_TRACE_SUMMARY_{key}_INVALID")
        elif not all(isinstance(item, str) for item in value):
            findings.append(f"P43_FRAMEWORK_TRACE_SUMMARY_{key}_INVALID")
    metrics = summary.get("metrics", {})
    if not isinstance(metrics, Mapping):
        findings.append("P43_FRAMEWORK_TRACE_SUMMARY_METRICS_INVALID")
    else:
        for key, value in metrics.items():
            if not _SAFE_TRACE_METRIC.fullmatch(str(key)):
                findings.append("P43_FRAMEWORK_TRACE_SUMMARY_METRIC_KEY_INVALID")
            if isinstance(value, bool) or not isinstance(value, int | float):
                findings.append("P43_FRAMEWORK_TRACE_SUMMARY_METRIC_VALUE_INVALID")
    findings.extend(_policy_findings((dict(summary),)))
    if findings:
        raise ModelGatewayError(
            "Framework adapter trace summary contains forbidden storage material.",
            code=P43_FRAMEWORK_RAW_TRACE_BLOCKED,
            provider_error={
                "type": "framework_adapter_trace_summary_policy",
                "code": P43_FRAMEWORK_RAW_TRACE_BLOCKED,
                "stage": _safe_stage(summary.get("stage")),
                "findingCount": str(len(findings)),
                "findings": ",".join(list(dict.fromkeys(findings))[:8]),
            },
        )
    return dict(summary)


def _trace_storage_findings(events: Sequence[Mapping[str, Any]]) -> list[str]:
    return _policy_findings(events)


def _policy_findings(payloads: Sequence[Mapping[str, Any]]) -> list[str]:
    findings = [finding["code"] for finding in storage_safety_findings(payloads=payloads)]
    for text in _iter_trace_text(payloads):
        if any(pattern.search(text) for pattern in _FORBIDDEN_TRACE_TEXT_PATTERNS):
            findings.append("FORBIDDEN_FRAMEWORK_POLICY_TEXT_PRESENT")
    return list(dict.fromkeys(findings))


def _framework_inventory_item(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "artifactType": str(item.get("artifactType") or ""),
        "path": str(item.get("path") or ""),
        "role": str(item.get("role") or ""),
        "className": str(item.get("className") or ""),
        "operationIds": _dedupe_strings(item.get("operationIds", [])),
        "dtoRole": str(item.get("dtoRole") or ""),
        "requiredFields": _dedupe_strings(item.get("requiredFields", [])),
        "references": _dedupe_strings(item.get("references", [])),
        "evidenceRefs": _dedupe_strings(item.get("evidenceRefs", [])),
        "reviewMarkers": _dedupe_strings(item.get("reviewMarkers", [])),
    }


def _policy_safe_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        str(key): _policy_safe_value(item)
        for key, item in value.items()
        if isinstance(item, str | int | float | bool)
        or (
            isinstance(item, Sequence)
            and not isinstance(item, str | bytes)
            and all(isinstance(seq_item, str | int | float | bool) for seq_item in item)
        )
    }


def _policy_safe_value(value: Any) -> Any:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return list(value)
    return value


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, str | bytes) else ()


def _sequence_of_mappings(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in _sequence(value) if isinstance(item, Mapping)]


def _ids_from_items(items: Sequence[Mapping[str, Any]], key: str) -> list[str]:
    return _dedupe_strings([item.get(key) for item in items])


def _dedupe_strings(items: Any) -> list[str]:
    values = items if isinstance(items, Sequence) and not isinstance(items, str | bytes) else ()
    return list(
        dict.fromkeys(str(item) for item in values if item is not None and str(item).strip())
    )


def _safe_stage(value: Any) -> str:
    stage = str(value or "")
    return stage if stage in _FRAMEWORK_STAGES else "unknown"


def _safe_schema_name(value: Any) -> str:
    schema_name = str(value or "")
    return schema_name if re.fullmatch(r"[a-z0-9_]{1,80}", schema_name) else "unknown"


def _iter_trace_text(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        text: list[str] = []
        for key, item in value.items():
            text.append(str(key))
            text.extend(_iter_trace_text(item))
        return text
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        text = []
        for item in value:
            text.extend(_iter_trace_text(item))
        return text
    return []


def _trace_blocker_ids(events: Sequence[Mapping[str, Any]]) -> list[str]:
    blockers: list[str] = []
    for event in events:
        if not isinstance(event, Mapping):
            continue
        blocker_id = event.get("blockerId")
        if blocker_id:
            blockers.append(str(blocker_id))
        for item in event.get("blockerIds", []):
            if str(item).strip():
                blockers.append(str(item))
    return list(dict.fromkeys(blockers))


def _trace_component_ids(events: Sequence[Mapping[str, Any]]) -> list[str]:
    component_ids = []
    for event in events:
        if not isinstance(event, Mapping):
            continue
        component_id = event.get("componentId")
        if component_id:
            component_ids.append(str(component_id))
    return list(dict.fromkeys(component_ids))


def _trace_failure_codes(events: Sequence[Mapping[str, Any]]) -> list[str]:
    codes = []
    for event in events:
        if not isinstance(event, Mapping):
            continue
        for key in ("failureCode", "errorCode"):
            code = event.get(key)
            if code:
                codes.append(str(code))
    return list(dict.fromkeys(codes))


def _trace_numeric_metrics(events: Sequence[Mapping[str, Any]]) -> dict[str, int | float]:
    metrics: dict[str, int | float] = {}
    for event in events:
        if not isinstance(event, Mapping):
            continue
        for key, value in event.items():
            if (
                _SAFE_TRACE_METRIC.fullmatch(str(key))
                and isinstance(value, int | float)
                and not isinstance(value, bool)
            ):
                metrics[str(key)] = value
    return metrics
