from __future__ import annotations

import json
import os
from types import SimpleNamespace
from typing import Any

import pytest
from ai_agent_runtime import (
    FRAMEWORK_RUNTIME_SUMMARY_VERSION,
    OPENAI_AGENTS_COMPATIBLE_API_CHAT_COMPLETIONS,
    OPENAI_AGENTS_COMPATIBLE_API_RESPONSES,
    OPENAI_AGENTS_ENDPOINT_PGPT_COMPATIBLE,
    P43_FRAMEWORK_RAW_TRACE_BLOCKED,
    P44_OPENAI_AGENTS_ADAPTER_FAILED,
    P44_OPENAI_AGENTS_TRACE_POLICY,
    ModelGatewayError,
    OpenAIAgentsFrameworkAdapter,
    openai_agents_compatible_api_from_env,
    openai_agents_endpoint_class_from_env,
    openai_agents_sdk_base_url_from_env,
)
from ai_agent_validation import validate_ai_java_mybatis_draft_pack_quality
from ai_agent_validation.models import ValidationStatus

from tests.unit.agent_runtime.test_framework_adapter import (
    _request,
    _valid_pack,
)


def test_openai_agents_adapter_mocked_runner_returns_valid_pack_and_disables_trace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _valid_pack()
    captured: dict[str, Any] = {}

    def runner(agent: Any, user_prompt: str, run_config: Any) -> Any:
        captured["agent"] = agent
        captured["promptLength"] = len(user_prompt)
        captured["tracingDisabled"] = bool(getattr(run_config, "tracing_disabled", True))
        captured["traceSensitive"] = bool(
            getattr(run_config, "trace_include_sensitive_data", False)
        )
        return SimpleNamespace(
            final_output=payload,
            usage=SimpleNamespace(input_tokens=11, output_tokens=22, total_tokens=33),
            response_id="resp_mocked_agents",
        )

    adapter = OpenAIAgentsFrameworkAdapter(
        runner=runner,
        agent_factory=lambda request: SimpleNamespace(name=f"mock-{request.stage}"),
    )

    invocation = adapter.draft_file_content(request=_request(payload))
    stored = invocation.to_storage_dict()
    stored_text = json.dumps(stored, ensure_ascii=False)

    assert invocation.provider == "openai-agents-sdk"
    assert invocation.provider_request_id == "resp_mocked_agents"
    assert invocation.token_usage == {"inputTokens": 11, "outputTokens": 22, "totalTokens": 33}
    assert invocation.structured_output["productionReady"] is False
    assert validate_ai_java_mybatis_draft_pack_quality(
        invocation.structured_output
    ).status == ValidationStatus.PASSED
    assert captured["agent"].name == "mock-file_content"
    assert captured["promptLength"] > 0
    assert captured["tracingDisabled"] is True
    assert captured["traceSensitive"] is False
    assert os.environ["OPENAI_AGENTS_DISABLE_TRACING"] == "1"
    assert os.environ["OPENAI_AGENTS_TRACE_INCLUDE_SENSITIVE_DATA"] == "0"
    assert os.environ["OPENAI_AGENTS_DONT_LOG_MODEL_DATA"] == "1"
    assert os.environ["OPENAI_AGENTS_DONT_LOG_TOOL_DATA"] == "1"
    assert stored["componentInvocations"][0]["candidateFramework"] == "openai_agents_sdk"
    assert stored["componentInvocations"][0]["stage"] == "file_content"
    assert stored["componentInvocations"][0]["traceHash"]
    assert FRAMEWORK_RUNTIME_SUMMARY_VERSION not in stored_text
    assert "raw_provider_response" not in stored_text
    assert "raw_prompt" not in stored_text
    assert "CREATE PROCEDURE" not in stored_text


def test_openai_agents_adapter_schema_failure_is_sanitized() -> None:
    adapter = OpenAIAgentsFrameworkAdapter(
        runner=lambda _agent, _prompt, _config: SimpleNamespace(
            final_output={"not": "an AiJavaMyBatisDraftPack"}
        ),
        agent_factory=lambda _request: SimpleNamespace(name="mock"),
    )

    with pytest.raises(ModelGatewayError) as exc:
        adapter.draft_file_content(request=_request(_valid_pack()))

    diagnostics = json.dumps(exc.value.provider_error, ensure_ascii=False)
    assert exc.value.code == "OPENAI_AI_DRAFT_PACK_INVALID"
    assert "AiJavaMyBatisDraftPack" not in diagnostics
    assert "not" not in diagnostics
    assert "outputHash" in diagnostics


def test_openai_agents_adapter_omits_native_output_type_for_custom_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeAgents:
        class AsyncOpenAI:
            def __init__(self, **kwargs: Any) -> None:
                self.kwargs = dict(kwargs)

        class OpenAIResponsesModel:
            def __init__(self, *, model: str, openai_client: Any) -> None:
                self.model = model
                self.openai_client = openai_client

        class Agent:
            def __init__(self, **kwargs: Any) -> None:
                captured.update(kwargs)
                self.name = kwargs["name"]

    monkeypatch.setenv("LLM_REMOTE_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://custom-openai-compatible.example/v1")
    monkeypatch.setattr("ai_agent_runtime.framework_adapter._agents_sdk", lambda: FakeAgents)

    adapter = OpenAIAgentsFrameworkAdapter()
    agent = adapter._build_agent(request=_request(_valid_pack()))  # noqa: SLF001

    assert agent.name == "AI Draft Pack file_content"
    assert "output_type" not in captured


def test_openai_agents_adapter_keeps_native_output_type_for_official_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeAgents:
        class Agent:
            def __init__(self, **kwargs: Any) -> None:
                captured.update(kwargs)
                self.name = kwargs["name"]

    monkeypatch.setenv("LLM_REMOTE_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    monkeypatch.setattr("ai_agent_runtime.framework_adapter._agents_sdk", lambda: FakeAgents)

    OpenAIAgentsFrameworkAdapter()._build_agent(  # noqa: SLF001
        request=_request(_valid_pack())
    )

    assert captured["output_type"].__name__ == "AiJavaMyBatisDraftPackOutput"


def test_openai_agents_adapter_builds_pgpt_responses_model_with_custom_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeAgents:
        class AsyncOpenAI:
            def __init__(self, **kwargs: Any) -> None:
                captured["client"] = dict(kwargs)

        class OpenAIResponsesModel:
            def __init__(self, *, model: str, openai_client: Any) -> None:
                captured["model"] = model
                captured["clientObject"] = openai_client
                self.model = model

        class Agent:
            def __init__(self, **kwargs: Any) -> None:
                captured["agent"] = dict(kwargs)
                self.name = kwargs["name"]

    monkeypatch.setenv("LLM_REMOTE_PROVIDER", "pgpt")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://pgpt.test/gpgpta01-gpt")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("OPENAI_RESPONSES_URL", raising=False)
    monkeypatch.delenv("OPENAI_AGENTS_COMPATIBLE_API", raising=False)
    monkeypatch.setattr("ai_agent_runtime.framework_adapter._agents_sdk", lambda: FakeAgents)

    agent = OpenAIAgentsFrameworkAdapter()._build_agent(  # noqa: SLF001
        request=_request(_valid_pack())
    )

    assert agent.name == "AI Draft Pack file_content"
    assert openai_agents_endpoint_class_from_env() == OPENAI_AGENTS_ENDPOINT_PGPT_COMPATIBLE
    assert openai_agents_compatible_api_from_env() == OPENAI_AGENTS_COMPATIBLE_API_RESPONSES
    assert captured["client"]["base_url"] == "http://pgpt.test/gpgpta01-gpt/v1"
    assert captured["client"]["api_key"] == "test-key"
    assert captured["model"] == _request(_valid_pack()).profile.model
    assert "output_type" not in captured["agent"]


def test_openai_agents_adapter_normalizes_exact_responses_url_without_storing_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _valid_pack()
    captured: dict[str, Any] = {}

    class FakeAgents:
        class AsyncOpenAI:
            def __init__(self, **kwargs: Any) -> None:
                captured["client"] = dict(kwargs)

        class OpenAIResponsesModel:
            def __init__(self, *, model: str, openai_client: Any) -> None:
                self.model = model
                self.openai_client = openai_client

        class Agent:
            def __init__(self, **kwargs: Any) -> None:
                self.name = kwargs["name"]

        class RunConfig:
            def __init__(self, **kwargs: Any) -> None:
                self.tracing_disabled = bool(kwargs.get("tracing_disabled"))
                self.trace_include_sensitive_data = bool(
                    kwargs.get("trace_include_sensitive_data", False)
                )

        class Runner:
            @staticmethod
            def run_sync(_agent: Any, _prompt: str, run_config: Any) -> Any:
                assert run_config.tracing_disabled is True
                assert run_config.trace_include_sensitive_data is False
                return SimpleNamespace(final_output=payload, response_id="resp_pgpt_agents")

        @staticmethod
        def set_tracing_disabled(_disabled: bool) -> None:
            captured["traceDisabled"] = True

    exact_url = "http://gateway.example/custom/v1/responses"
    monkeypatch.setenv("LLM_REMOTE_PROVIDER", "pgpt")
    monkeypatch.setenv("OPENAI_RESPONSES_URL", exact_url)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr("ai_agent_runtime.framework_adapter._agents_sdk", lambda: FakeAgents)

    invocation = OpenAIAgentsFrameworkAdapter().draft_file_content(
        request=_request(payload)
    )
    stored_text = json.dumps(invocation.to_storage_dict(), ensure_ascii=False)

    assert openai_agents_sdk_base_url_from_env() == "http://gateway.example/custom/v1"
    assert captured["client"]["base_url"] == "http://gateway.example/custom/v1"
    assert invocation.provider == "openai-agents-sdk"
    assert "pgpt_compatible" in stored_text
    assert "responses" in stored_text
    assert exact_url not in stored_text
    assert "gateway.example" not in stored_text


def test_openai_agents_adapter_builds_pgpt_chat_completions_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeAgents:
        class AsyncOpenAI:
            def __init__(self, **kwargs: Any) -> None:
                captured["client"] = dict(kwargs)

        class OpenAIChatCompletionsModel:
            def __init__(self, *, model: str, openai_client: Any) -> None:
                captured["chatModel"] = model

        class Agent:
            def __init__(self, **kwargs: Any) -> None:
                captured["agent"] = dict(kwargs)
                self.name = kwargs["name"]

    monkeypatch.setenv("LLM_REMOTE_PROVIDER", "pgpt")
    monkeypatch.setenv("OPENAI_RESPONSES_URL", "http://pgpt.test/v1/responses")
    monkeypatch.setenv("OPENAI_AGENTS_COMPATIBLE_API", "chat_completions")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setattr("ai_agent_runtime.framework_adapter._agents_sdk", lambda: FakeAgents)

    OpenAIAgentsFrameworkAdapter()._build_agent(  # noqa: SLF001
        request=_request(_valid_pack())
    )

    assert openai_agents_compatible_api_from_env() == (
        OPENAI_AGENTS_COMPATIBLE_API_CHAT_COMPLETIONS
    )
    assert captured["chatModel"] == _request(_valid_pack()).profile.model
    assert "output_type" not in captured["agent"]


def test_openai_agents_adapter_trace_policy_error_stays_sanitized(monkeypatch: Any) -> None:
    payload = _valid_pack()
    adapter = OpenAIAgentsFrameworkAdapter(
        runner=lambda _agent, _prompt, _config: SimpleNamespace(final_output=payload),
        agent_factory=lambda _request: SimpleNamespace(name="mock"),
    )
    monkeypatch.setattr(
        "ai_agent_runtime.framework_adapter._openai_agents_run_config",
        lambda: (_ for _ in ()).throw(
            ModelGatewayError(
                "RunConfig policy unavailable.",
                code=P44_OPENAI_AGENTS_TRACE_POLICY,
                provider_error={
                    "type": "openai_agents_trace_policy",
                    "code": P44_OPENAI_AGENTS_TRACE_POLICY,
                },
            )
        ),
    )

    with pytest.raises(ModelGatewayError) as exc:
        adapter.draft_file_content(request=_request(payload))

    assert exc.value.code == P44_OPENAI_AGENTS_TRACE_POLICY
    assert "raw_prompt" not in json.dumps(exc.value.provider_error, ensure_ascii=False)


def test_openai_agents_adapter_blocks_unsafe_trace_summary(monkeypatch: Any) -> None:
    payload = _valid_pack()
    adapter = OpenAIAgentsFrameworkAdapter(
        runner=lambda _agent, _prompt, _config: SimpleNamespace(final_output=payload),
        agent_factory=lambda _request: SimpleNamespace(name="mock"),
    )

    def unsafe_summary(**_kwargs: Any) -> dict[str, Any]:
        raise ModelGatewayError(
            "unsafe trace",
            code=P43_FRAMEWORK_RAW_TRACE_BLOCKED,
            provider_error={
                "type": "framework_adapter_trace_policy",
                "code": P43_FRAMEWORK_RAW_TRACE_BLOCKED,
                "findingCount": "1",
            },
        )

    monkeypatch.setattr(
        "ai_agent_runtime.framework_adapter.summarize_framework_trace",
        unsafe_summary,
    )

    with pytest.raises(ModelGatewayError) as exc:
        adapter.draft_file_content(request=_request(payload))

    assert exc.value.code == P43_FRAMEWORK_RAW_TRACE_BLOCKED


def test_openai_agents_adapter_runner_exception_is_sanitized() -> None:
    def runner(_agent: Any, _prompt: str, _config: Any) -> Any:
        raise RuntimeError("provider leaked: CREATE PROCEDURE password=secret")

    adapter = OpenAIAgentsFrameworkAdapter(
        runner=runner,
        agent_factory=lambda _request: SimpleNamespace(name="mock"),
    )

    with pytest.raises(ModelGatewayError) as exc:
        adapter.draft_file_content(request=_request(_valid_pack()))

    diagnostics = json.dumps(exc.value.provider_error, ensure_ascii=False)
    assert exc.value.code == P44_OPENAI_AGENTS_ADAPTER_FAILED
    assert exc.value.__cause__ is None
    assert "CREATE PROCEDURE" not in diagnostics
    assert "secret" not in diagnostics
    assert "RuntimeError" in diagnostics
