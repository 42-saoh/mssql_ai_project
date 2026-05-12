from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from ai_agent_runtime.gateway import ModelGatewayError, OpenAIModelGateway, model_profile_from_env
from ai_agent_runtime.models import SEMANTIC_MODEL_PROFILE_ID, RenderedPrompt

SEMANTIC_OUTPUT = {
    "businessRules": [
        {
            "category": "TEST_RULE",
            "summary": "Schema-valid semantic output for gateway tests.",
            "status": "INFERRED_DESCRIPTION",
            "evidenceRefs": ["fact_demo"],
        }
    ],
    "modernizationPoints": [],
    "riskFlags": [],
    "reviewMarkers": [],
    "conversionGuidance": [],
    "migrationGuideInsights": [],
    "assumptions": [],
}


def test_openai_default_responses_url_and_payload_are_unchanged(
    monkeypatch: Any,
) -> None:
    captured = _capture_post(monkeypatch, _json_response())
    monkeypatch.delenv("LLM_REMOTE_PROVIDER", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.test/v1")
    monkeypatch.setenv("OPENAI_MODEL_ANALYSIS", "gpt-5.5")
    monkeypatch.setenv("OPENAI_REASONING_EFFORT_ANALYSIS", "medium")

    result = OpenAIModelGateway(timeout_seconds=1).invoke_semantic_analysis(
        prompt=_prompt(),
        profile=model_profile_from_env(SEMANTIC_MODEL_PROFILE_ID),
    )

    assert captured["url"] == "https://api.openai.test/v1/responses"
    assert captured["json"]["model"] == "gpt-5.5"
    assert captured["json"]["input"][0]["role"] == "system"
    assert captured["json"]["text"]["format"]["type"] == "json_schema"
    assert captured["json"]["reasoning"]["effort"] == "medium"
    assert "instructions" not in captured["json"]
    assert result.provider == "openai"


def test_pgpt_base_url_adds_v1_responses_and_uses_minimal_pgpt_payload(
    monkeypatch: Any,
) -> None:
    captured = _capture_post(monkeypatch, _json_response())
    monkeypatch.setenv("LLM_REMOTE_PROVIDER", "pgpt")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://aigpt.posco.net/gpgpta01-gpt")
    monkeypatch.setenv("OPENAI_MODEL_ANALYSIS", "gpt-5.5")
    monkeypatch.delenv("PGPT_MODEL_ANALYSIS", raising=False)
    monkeypatch.delenv("OPENAI_RESPONSES_URL", raising=False)

    result = OpenAIModelGateway(timeout_seconds=1).invoke_semantic_analysis(
        prompt=_prompt(),
        profile=model_profile_from_env(SEMANTIC_MODEL_PROFILE_ID),
    )

    assert captured["url"] == "http://aigpt.posco.net/gpgpta01-gpt/v1/responses"
    assert captured["json"] == {
        "model": "gpt-4o",
        "instructions": "Return only JSON.",
        "input": [{"role": "user", "content": "Summarize dbo.usp_Demo."}],
    }
    assert "stream" not in captured["json"]
    assert "max_output_tokens" not in captured["json"]
    assert "text" not in captured["json"]
    assert "reasoning" not in captured["json"]
    assert result.provider == "pgpt"
    assert result.model == "gpt-4o"
    assert result.reasoning_effort == "none"


def test_pgpt_exact_responses_url_override(monkeypatch: Any) -> None:
    captured = _capture_post(monkeypatch, _json_response())
    monkeypatch.setenv("LLM_REMOTE_PROVIDER", "pgpt")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://ignored.example/gpgpta01-gpt")
    monkeypatch.setenv(
        "OPENAI_RESPONSES_URL",
        "http://gateway.example/custom/v1/responses",
    )
    monkeypatch.setenv("PGPT_MODEL_ANALYSIS", "gpt-4o-mini")

    result = OpenAIModelGateway(timeout_seconds=1).invoke_semantic_analysis(
        prompt=_prompt(),
        profile=model_profile_from_env(SEMANTIC_MODEL_PROFILE_ID),
    )

    assert captured["url"] == "http://gateway.example/custom/v1/responses"
    assert captured["json"]["model"] == "gpt-4o-mini"
    assert result.provider == "pgpt"


def test_pgpt_provider_requires_base_or_exact_responses_url(monkeypatch: Any) -> None:
    _capture_post(monkeypatch, _json_response())
    monkeypatch.setenv("LLM_REMOTE_PROVIDER", "pgpt")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_RESPONSES_URL", raising=False)

    with pytest.raises(ModelGatewayError) as exc_info:
        OpenAIModelGateway(timeout_seconds=1).invoke_semantic_analysis(
            prompt=_prompt(),
            profile=model_profile_from_env(SEMANTIC_MODEL_PROFILE_ID),
        )

    assert exc_info.value.code == "PGPT_RESPONSES_URL_MISSING"


def test_pgpt_sse_output_text_delta_parses_structured_json(monkeypatch: Any) -> None:
    output_text = json.dumps(SEMANTIC_OUTPUT)
    midpoint = len(output_text) // 2
    sse_body = "\n".join(
        [
            'event: response.output_text.delta',
            "data: "
            + json.dumps(
                {
                    "type": "response.output_text.delta",
                    "delta": output_text[:midpoint],
                }
            ),
            "",
            "data: "
            + json.dumps(
                {
                    "type": "response.output_text.delta",
                    "delta": output_text[midpoint:],
                }
            ),
            "data: [DONE]",
        ]
    )
    _capture_post(
        monkeypatch,
        httpx.Response(
            200,
            headers={"content-type": "text/event-stream"},
            content=sse_body.encode("utf-8"),
            request=httpx.Request("POST", "http://pgpt.test/v1/responses"),
        ),
    )
    monkeypatch.setenv("LLM_REMOTE_PROVIDER", "pgpt")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://pgpt.test")

    result = OpenAIModelGateway(timeout_seconds=1).invoke_semantic_analysis(
        prompt=_prompt(),
        profile=model_profile_from_env(SEMANTIC_MODEL_PROFILE_ID),
    )

    assert result.provider == "pgpt"
    assert result.structured_output["businessRules"][0]["category"] == "TEST_RULE"
    assert result.token_usage == {"inputTokens": 0, "outputTokens": 0, "totalTokens": 0}


def test_pgpt_model_profile_defaults(monkeypatch: Any) -> None:
    monkeypatch.setenv("LLM_REMOTE_PROVIDER", "pgpt")
    monkeypatch.setenv("OPENAI_MODEL_ANALYSIS", "gpt-5.5")
    monkeypatch.setenv("OPENAI_MODEL_FAST_TEST", "gpt-5.5")
    monkeypatch.delenv("PGPT_MODEL_ANALYSIS", raising=False)
    monkeypatch.delenv("PGPT_MODEL_FAST_TEST", raising=False)

    semantic = model_profile_from_env("openai_sp_semantic_analysis")
    fast = model_profile_from_env("openai_fast_test")

    assert semantic.model == "gpt-4o"
    assert semantic.reasoning_effort == "none"
    assert fast.model == "gpt-4o-mini"
    assert fast.reasoning_effort == "none"


def _prompt() -> RenderedPrompt:
    return RenderedPrompt(
        prompt_version="prompt:test@0.1.0",
        output_schema_version="schema:test@0.1.0",
        system_prompt="Return only JSON.",
        user_prompt="Summarize dbo.usp_Demo.",
        input_hash="input-hash",
        prompt_hash="prompt-hash",
        metadata={"allowedEvidenceRefs": ["fact_demo"]},
    )


def _json_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "resp_test",
            "output_text": json.dumps(SEMANTIC_OUTPUT),
            "usage": {"input_tokens": 12, "output_tokens": 34, "total_tokens": 46},
        },
        request=httpx.Request("POST", "https://api.openai.test/v1/responses"),
    )


def _capture_post(monkeypatch: Any, response: httpx.Response) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def fake_post(
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
        timeout: float,
    ) -> httpx.Response:
        captured["url"] = url
        captured["headers"] = dict(headers)
        captured["json"] = dict(json)
        captured["timeout"] = timeout
        return response

    monkeypatch.setattr("ai_agent_runtime.gateway.httpx.post", fake_post)
    return captured
