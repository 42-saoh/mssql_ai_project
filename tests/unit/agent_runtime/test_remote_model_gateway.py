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
    assert captured["json"]["text"]["format"]["strict"] is True
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


def test_pgpt_markdown_fenced_semantic_json_is_adapted_and_fills_missing_roots(
    monkeypatch: Any,
) -> None:
    partial_output = {"businessRules": SEMANTIC_OUTPUT["businessRules"]}
    fenced_output = f"```json\n{json.dumps(partial_output)}\n```"
    _capture_post(monkeypatch, _pgpt_response({"output_text": fenced_output}))
    _set_pgpt_env(monkeypatch)

    result = OpenAIModelGateway(timeout_seconds=1).invoke_semantic_analysis(
        prompt=_prompt(),
        profile=model_profile_from_env(SEMANTIC_MODEL_PROFILE_ID),
    )

    assert result.provider == "pgpt"
    assert result.structured_output["businessRules"][0]["category"] == "TEST_RULE"
    assert result.structured_output["modernizationPoints"] == []
    assert result.structured_output["riskFlags"] == []
    assert result.structured_output["reviewMarkers"] == []
    assert result.structured_output["conversionGuidance"] == []
    assert result.structured_output["migrationGuideInsights"] == []
    assert result.structured_output["assumptions"] == []
    assert result.component_invocations == (
        {
            "component": "pgpt_structured_output_adapter",
            "status": "SUCCEEDED",
            "action": "adapted_pgpt_semantic_output",
        },
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"output_text": json.dumps(SEMANTIC_OUTPUT)},
        {"message": {"content": json.dumps(SEMANTIC_OUTPUT)}},
    ],
)
def test_pgpt_text_wrappers_with_json_strings_are_adapted(
    monkeypatch: Any,
    payload: dict[str, Any],
) -> None:
    _capture_post(monkeypatch, _pgpt_response(payload))
    _set_pgpt_env(monkeypatch)

    result = OpenAIModelGateway(timeout_seconds=1).invoke_semantic_analysis(
        prompt=_prompt(),
        profile=model_profile_from_env(SEMANTIC_MODEL_PROFILE_ID),
    )

    assert result.provider == "pgpt"
    assert result.structured_output["businessRules"][0]["summary"] == (
        "Schema-valid semantic output for gateway tests."
    )


@pytest.mark.parametrize("wrapper_key", ["structuredOutput", "llmSemanticAnalysis"])
def test_pgpt_semantic_wrapper_objects_are_adapted(
    monkeypatch: Any,
    wrapper_key: str,
) -> None:
    _capture_post(
        monkeypatch,
        _pgpt_response(
            {
                wrapper_key: {
                    "business_rules": SEMANTIC_OUTPUT["businessRules"],
                }
            }
        ),
    )
    _set_pgpt_env(monkeypatch)

    result = OpenAIModelGateway(timeout_seconds=1).invoke_semantic_analysis(
        prompt=_prompt(),
        profile=model_profile_from_env(SEMANTIC_MODEL_PROFILE_ID),
    )

    assert result.provider == "pgpt"
    assert result.structured_output["businessRules"][0]["category"] == "TEST_RULE"
    assert result.structured_output["modernizationPoints"] == []


def test_pgpt_migration_guide_text_lists_are_normalized(monkeypatch: Any) -> None:
    output = {
        **SEMANTIC_OUTPUT,
        "migrationGuideInsights": [
            {
                "section": "dependency_inventory",
                "summary": "Provider guide insight.",
                "status": "SUPPORTED",
                "evidenceRefs": ["fact_demo"],
                "whatToExtractNext": [
                    "Enumerate permitted tenant schemas.",
                    "Confirm read-only metadata evidence.",
                ],
            }
        ],
    }
    _capture_post(monkeypatch, _pgpt_response({"output_text": json.dumps(output)}))
    _set_pgpt_env(monkeypatch)

    result = OpenAIModelGateway(timeout_seconds=1).invoke_semantic_analysis(
        prompt=_prompt(),
        profile=model_profile_from_env(SEMANTIC_MODEL_PROFILE_ID),
    )

    guide_insight = result.structured_output["migrationGuideInsights"][0]
    assert guide_insight["status"] == "REVIEW_REQUIRED"
    assert guide_insight["whatToExtractNext"] == (
        "Enumerate permitted tenant schemas.; Confirm read-only metadata evidence."
    )
    assert result.component_invocations == (
        {
            "component": "pgpt_structured_output_adapter",
            "status": "SUCCEEDED",
            "action": "adapted_pgpt_semantic_output",
        },
        {
            "component": "structured_output_normalizer",
            "status": "SUCCEEDED",
            "action": "removed_schema_extra_fields",
            "removedFieldPaths": [
                "$.migrationGuideInsights[0].status",
                "$.migrationGuideInsights[0].whatToExtractNext",
            ],
        },
    )


def test_pgpt_natural_language_response_fails_without_storing_raw_output(
    monkeypatch: Any,
) -> None:
    raw_output = "I cannot produce the requested JSON for dbo.usp_Demo."
    _capture_post(monkeypatch, _pgpt_response({"output_text": raw_output}))
    _set_pgpt_env(monkeypatch)

    with pytest.raises(ModelGatewayError) as exc_info:
        OpenAIModelGateway(timeout_seconds=1).invoke_semantic_analysis(
            prompt=_prompt(),
            profile=model_profile_from_env(SEMANTIC_MODEL_PROFILE_ID),
        )

    assert exc_info.value.code == "OPENAI_STRUCTURED_OUTPUT_INVALID"
    assert raw_output not in str(exc_info.value)


def test_remote_semantic_output_extra_fields_are_pruned_before_storage(
    monkeypatch: Any,
) -> None:
    output = {
        **SEMANTIC_OUTPUT,
        "target": {"schema": "dbo", "name": "usp_Demo"},
        "deterministicEvidenceSummary": {"factCount": 1},
        "reviewFlags": [{"code": "MODEL_SIDE_EXTRA"}],
        "assumptions": [{"item": "Do not store this provider-side assumption text."}],
        "conversionGuidance": {
            "summary": [{"text": "Provider guidance text.", "status": "CONFIRMED"}]
        },
        "migrationGuideInsights": [
            {
                "section": "dependency_inventory",
                "summary": "Provider guide insight.",
                "status": "SUPPORTED",
                "evidenceRefs": ["fact_demo"],
                "guide_element": "Needs verification",
                "target_ref": "dbo.TargetA",
                "risk_area": "dynamic_sql",
                "what_to_extract_next": "Run metadata-only dependency extraction.",
                "rawSnippet": "SELECT * FROM dbo.SecretTable",
            }
        ],
        "riskFlags": [{"evidenceRefs": ["fact_demo"]}],
        "businessRules": [
            {
                **SEMANTIC_OUTPUT["businessRules"][0],
                "rawSnippet": "SELECT * FROM dbo.SecretTable",
                "status": "CONFIRMED",
            }
        ],
    }
    _capture_post(monkeypatch, _json_response(output=output))
    monkeypatch.delenv("LLM_REMOTE_PROVIDER", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.test/v1")

    result = OpenAIModelGateway(timeout_seconds=1).invoke_semantic_analysis(
        prompt=_prompt(),
        profile=model_profile_from_env(SEMANTIC_MODEL_PROFILE_ID),
    )

    assert "target" not in result.structured_output
    assert "deterministicEvidenceSummary" not in result.structured_output
    assert "reviewFlags" not in result.structured_output
    assert "rawSnippet" not in result.structured_output["businessRules"][0]
    assert result.structured_output["businessRules"][0]["status"] == "INFERRED_DESCRIPTION"
    assert result.structured_output["conversionGuidance"][0]["status"] == "REVIEW_REQUIRED"
    assert result.structured_output["conversionGuidance"][0]["summary"] == (
        "Provider guidance text."
    )
    assert result.structured_output["conversionGuidance"][0]["code"].startswith(
        "NORMALIZED_PROVIDER_CONVERSIONGUIDANCE"
    )
    guide_insight = result.structured_output["migrationGuideInsights"][0]
    assert guide_insight["status"] == "REVIEW_REQUIRED"
    assert guide_insight["guideElement"] == "Needs verification"
    assert guide_insight["targetRef"] == "dbo.TargetA"
    assert guide_insight["riskArea"] == "dynamic_sql"
    assert guide_insight["whatToExtractNext"] == "Run metadata-only dependency extraction."
    assert "rawSnippet" not in guide_insight
    assert result.structured_output["riskFlags"] == []
    assert result.structured_output["assumptions"] == [
        "Provider returned a structured assumption object; text was not stored."
    ]
    assert result.component_invocations == (
        {
            "component": "structured_output_normalizer",
            "status": "SUCCEEDED",
            "action": "removed_schema_extra_fields",
            "removedFieldPaths": [
                "$.assumptions[0]",
                "$.businessRules[0].rawSnippet",
                "$.businessRules[0].status",
                "$.conversionGuidance",
                "$.conversionGuidance[0].status",
                "$.conversionGuidance[0].text",
                "$.deterministicEvidenceSummary",
                "$.migrationGuideInsights[0].rawSnippet",
                "$.migrationGuideInsights[0].status",
                "$.reviewFlags",
                "$.riskFlags[0]",
                "$.target",
            ],
        },
    )


def test_remote_metadata_tool_plan_aliases_are_normalized_before_storage(
    monkeypatch: Any,
) -> None:
    output = {
        "tools": [
            {
                "tool": "get_table_schema",
                "args": {
                    "dbProfileId": "master",
                    "schema": "dbo",
                    "tableName": "TB_ORDER",
                },
                "rationale": "Need table shape evidence.",
                "evidenceUse": "Anchor DTO claims.",
                "confidence": "provider-side-extra",
            }
        ],
        "assumptions": [{"text": "Provider object assumption must not be stored."}],
        "review_markers": [
            {
                "code": "PLANNER_ALIAS_NORMALIZED",
                "message": "Alias output normalized.",
                "status": "DONE",
            }
        ],
        "target": {"schema": "dbo", "name": "TB_ORDER"},
    }
    _capture_post(monkeypatch, _json_response(output=output))
    monkeypatch.delenv("LLM_REMOTE_PROVIDER", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.test/v1")

    result = OpenAIModelGateway(timeout_seconds=1).plan_metadata_tools(
        prompt=_tool_prompt(),
        profile=model_profile_from_env(SEMANTIC_MODEL_PROFILE_ID),
    )

    assert result.structured_output["toolRequests"] == [
        {
            "toolName": "get_table_schema",
            "arguments": {
                "dbProfileId": "master",
                "schema": "dbo",
                "tableName": "TB_ORDER",
            },
            "reason": "Need table shape evidence.",
            "expectedEvidenceUse": "Anchor DTO claims.",
        }
    ]
    assert result.structured_output["reviewMarkers"][0]["status"] == "REVIEW_REQUIRED"
    assert result.structured_output["assumptions"] == [
        "Provider returned a structured assumption object; text was not stored."
    ]
    assert result.component_invocations[0]["action"] == "normalized_metadata_tool_plan"
    assert "$.target" in result.component_invocations[0]["removedFieldPaths"]
    assert "$.tools[0].confidence" in result.component_invocations[0]["removedFieldPaths"]


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


def _tool_prompt() -> RenderedPrompt:
    return RenderedPrompt(
        prompt_version="prompt:test@0.1.0",
        output_schema_version="schema:test@0.1.0",
        system_prompt="Return only JSON.",
        user_prompt="Plan tools for dbo.TB_ORDER.",
        input_hash="input-hash",
        prompt_hash="prompt-hash",
        metadata={"toolNames": ["get_table_schema"]},
    )


def _json_response(*, output: dict[str, Any] | None = None) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "resp_test",
            "output_text": json.dumps(output or SEMANTIC_OUTPUT),
            "usage": {"input_tokens": 12, "output_tokens": 34, "total_tokens": 46},
        },
        request=httpx.Request("POST", "https://api.openai.test/v1/responses"),
    )


def _pgpt_response(payload: dict[str, Any]) -> httpx.Response:
    return httpx.Response(
        200,
        json={"id": "resp_test", **payload},
        request=httpx.Request("POST", "http://pgpt.test/v1/responses"),
    )


def _set_pgpt_env(monkeypatch: Any) -> None:
    monkeypatch.setenv("LLM_REMOTE_PROVIDER", "pgpt")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://pgpt.test")


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
