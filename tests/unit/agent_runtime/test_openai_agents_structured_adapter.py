from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
import yaml
from ai_agent_runtime import (
    AI_STRUCTURED_FRAMEWORK_ADAPTER_VERSION,
    FakeModelGateway,
    FrameworkModelGateway,
    ModelGatewayError,
    ModelProfile,
    OpenAIAgentsStructuredAdapter,
    P48_OPENAI_AGENTS_STRUCTURED_ADAPTER_FAILED,
)
from ai_agent_runtime.models import RenderedPrompt, stable_json_hash
from ai_agent_runtime.operation_model import (
    all_sp_operation_model_evidence_refs,
    validate_sp_operation_model_output,
)

OPERATION_FIXTURE = Path("fixtures/eval/sp_operation_model_p41_manage_bond_v1.yaml")


@pytest.fixture(autouse=True)
def _fake_agents_sdk(monkeypatch: pytest.MonkeyPatch) -> None:
    class FakeAgents:
        class RunConfig:
            def __init__(self, **kwargs: Any) -> None:
                self.tracing_disabled = bool(kwargs.get("tracing_disabled"))
                self.trace_include_sensitive_data = bool(
                    kwargs.get("trace_include_sensitive_data", False)
                )

        @staticmethod
        def set_tracing_disabled(_disabled: bool) -> None:
            return None

    monkeypatch.setattr("ai_agent_runtime.framework_adapter._agents_sdk", lambda: FakeAgents)
    monkeypatch.delenv("LLM_REMOTE_PROVIDER", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)


def test_openai_agents_structured_adapter_routes_all_non_draft_structured_paths() -> None:
    operation_model = _operation_model_fixture()
    outputs = [
        _semantic_output(),
        _tool_plan_output("get_table_schema"),
        _metadata_analysis_output(),
        _tool_plan_output("collect_workflow_context"),
        operation_model,
    ]
    captured_stages: list[str] = []

    def runner(agent: Any, _user_prompt: str, run_config: Any) -> Any:
        captured_stages.append(agent.stage)
        assert run_config.tracing_disabled is True
        assert run_config.trace_include_sensitive_data is False
        return SimpleNamespace(
            final_output=outputs.pop(0),
            usage=SimpleNamespace(input_tokens=3, output_tokens=5, total_tokens=8),
            response_id=f"resp_{agent.stage}",
        )

    gateway = FrameworkModelGateway(
        fallback_gateway=FakeModelGateway(),
        structured_adapter=OpenAIAgentsStructuredAdapter(
            runner=runner,
            agent_factory=lambda request: SimpleNamespace(stage=request.stage),
        ),
    )
    profile = _profile()
    operation_refs = _allowed_operation_refs(operation_model)

    invocations = [
        gateway.invoke_semantic_analysis(
            prompt=_prompt(
                schema="schema:llm_semantic_analysis@0.4.1",
                metadata={"targetRef": "dbo.usp_Demo", "allowedEvidenceRefs": ["fact.demo"]},
            ),
            profile=profile,
        ),
        gateway.plan_metadata_tools(
            prompt=_prompt(
                schema="schema:mssql_metadata_tool_plan@0.1.0",
                metadata={
                    "targetRef": "dbo.TableA",
                    "toolNames": ["get_table_schema"],
                },
            ),
            profile=profile,
        ),
        gateway.analyze_metadata(
            prompt=_prompt(
                schema="schema:mssql_metadata_analysis@0.1.1",
                metadata={"targetRef": "dbo.TableA", "allowedEvidenceRefs": ["fact.demo"]},
            ),
            profile=profile,
        ),
        gateway.plan_platform_tools(
            prompt=_prompt(
                schema="schema:platform_tool_plan@0.1.0",
                metadata={
                    "targetRef": "job-1",
                    "toolNames": ["collect_workflow_context"],
                },
            ),
            profile=profile,
        ),
        gateway.plan_sp_operation_model(
            prompt=_prompt(
                schema="schema:sp_operation_model@0.1.0",
                metadata={
                    "targetRef": operation_model["targetRef"],
                    "allowedEvidenceRefs": operation_refs,
                },
                payload={"statementEvidence": operation_model["statementEvidence"]},
            ),
            profile=profile,
        ),
    ]

    assert captured_stages == [
        "llm_semantic_analysis",
        "metadata_tool_planning",
        "metadata_analysis",
        "platform_tool_planning",
        "sp_operation_model",
    ]
    assert invocations[0].structured_output["businessRules"][0]["category"] == "DEMO_RULE"
    assert invocations[1].structured_output["toolRequests"][0]["toolName"] == (
        "get_table_schema"
    )
    assert invocations[2].structured_output["summary"] == "Metadata evidence requires review."
    assert invocations[3].structured_output["toolRequests"][0]["toolName"] == (
        "collect_workflow_context"
    )
    assert invocations[4].structured_output["contractTarget"] == "SpOperationModel"

    for invocation in invocations:
        stored = invocation.to_storage_dict()
        component = stored["componentInvocations"][-1]
        assert invocation.provider == "openai-agents-sdk"
        assert invocation.token_usage == {
            "inputTokens": 3,
            "outputTokens": 5,
            "totalTokens": 8,
        }
        assert component["adapterContract"] == AI_STRUCTURED_FRAMEWORK_ADAPTER_VERSION
        assert component["candidateFramework"] == "openai_agents_sdk"
        assert "traceHash" in component
        serialized = json.dumps(stored, ensure_ascii=False)
        assert "raw_prompt" not in serialized
        assert "CREATE PROCEDURE" not in serialized


def test_openai_agents_structured_adapter_schema_failure_is_sanitized() -> None:
    gateway = FrameworkModelGateway(
        fallback_gateway=FakeModelGateway(),
        structured_adapter=OpenAIAgentsStructuredAdapter(
            runner=lambda _agent, _prompt, _config: SimpleNamespace(
                final_output={"not": "metadata analysis"}
            ),
            agent_factory=lambda request: SimpleNamespace(stage=request.stage),
        ),
    )

    with pytest.raises(ModelGatewayError) as exc:
        gateway.analyze_metadata(
            prompt=_prompt(
                schema="schema:mssql_metadata_analysis@0.1.1",
                metadata={"targetRef": "dbo.TableA", "allowedEvidenceRefs": ["fact.demo"]},
            ),
            profile=_profile(),
        )

    diagnostics = json.dumps(exc.value.provider_error, ensure_ascii=False)
    assert exc.value.code == "OPENAI_METADATA_ANALYSIS_INVALID"
    assert "metadata analysis" not in diagnostics
    assert "outputHash" in diagnostics
    assert "metadata_analysis" in diagnostics


def test_openai_agents_structured_adapter_operation_model_diagnostics_include_findings() -> None:
    operation_model = _operation_model_fixture()
    invalid_output = dict(operation_model)
    invalid_output["operations"] = []
    invalid_output["dtoBlueprints"] = []

    gateway = FrameworkModelGateway(
        fallback_gateway=FakeModelGateway(),
        structured_adapter=OpenAIAgentsStructuredAdapter(
            runner=lambda _agent, _prompt, _config: SimpleNamespace(
                final_output=invalid_output
            ),
            agent_factory=lambda request: SimpleNamespace(stage=request.stage),
        ),
    )

    with pytest.raises(ModelGatewayError) as exc:
        gateway.plan_sp_operation_model(
            prompt=_prompt(
                schema="schema:sp_operation_model@0.1.0",
                metadata={
                    "targetRef": operation_model["targetRef"],
                    "allowedEvidenceRefs": _allowed_operation_refs(operation_model),
                },
                payload={"statementEvidence": operation_model["statementEvidence"]},
            ),
            profile=_profile(),
        )

    provider_error = exc.value.provider_error
    diagnostics = json.dumps(provider_error, ensure_ascii=False)
    assert exc.value.code == "OPENAI_SP_OPERATION_MODEL_INVALID"
    assert provider_error["schemaName"] == "sp_operation_model"
    assert provider_error["stage"] == "sp_operation_model"
    assert provider_error["findingCount"] >= 1
    assert any("operations must not be empty" in item for item in provider_error["findings"])
    assert "input_value" not in diagnostics
    assert "CREATE PROCEDURE" not in diagnostics


def test_openai_agents_structured_adapter_hard_fails_without_fallback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class InternalServerError(Exception):
        pass

    class FallbackSpy(FakeModelGateway):
        def __init__(self) -> None:
            super().__init__()
            self.semantic_calls = 0

        def invoke_semantic_analysis(self, *, prompt: Any, profile: Any) -> Any:
            self.semantic_calls += 1
            return super().invoke_semantic_analysis(prompt=prompt, profile=profile)

    fallback = FallbackSpy()
    monkeypatch.setenv("LLM_REMOTE_PROVIDER", "pgpt")
    monkeypatch.setenv("OPENAI_AGENTS_COMPATIBLE_API", "responses")
    gateway = FrameworkModelGateway(
        fallback_gateway=fallback,
        structured_adapter=OpenAIAgentsStructuredAdapter(
            runner=lambda _agent, _prompt, _config: (_ for _ in ()).throw(
                InternalServerError(
                    "raw provider response: CREATE PROCEDURE secret-token"
                )
            ),
            agent_factory=lambda request: SimpleNamespace(stage=request.stage),
        ),
    )

    with pytest.raises(ModelGatewayError) as exc:
        gateway.invoke_semantic_analysis(
            prompt=_prompt(
                schema="schema:llm_semantic_analysis@0.4.1",
                metadata={"targetRef": "dbo.usp_Demo"},
            ),
            profile=_profile(),
        )

    assert exc.value.code == P48_OPENAI_AGENTS_STRUCTURED_ADAPTER_FAILED
    assert fallback.semantic_calls == 0
    provider_error = exc.value.provider_error
    assert provider_error == {
        "type": "openai_agents_structured_adapter",
        "code": P48_OPENAI_AGENTS_STRUCTURED_ADAPTER_FAILED,
        "stage": "llm_semantic_analysis",
        "schemaName": "llm_semantic_analysis",
        "endpointClass": "pgpt_compatible",
        "sdkTransport": "responses",
        "modelProfileId": "openai_fast_test",
        "model": "gpt-5-nano",
        "errorClass": "InternalServerError",
    }
    diagnostics = json.dumps(provider_error, ensure_ascii=False)
    assert "CREATE PROCEDURE" not in diagnostics
    assert "secret-token" not in diagnostics
    assert "raw provider response" not in diagnostics


def test_framework_model_gateway_keeps_sp_text_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_ALLOW_SP_TEXT", "0")
    gateway = FrameworkModelGateway(
        fallback_gateway=FakeModelGateway(),
        structured_adapter=OpenAIAgentsStructuredAdapter(
            runner=lambda _agent, _prompt, _config: SimpleNamespace(
                final_output=_semantic_output()
            ),
            agent_factory=lambda request: SimpleNamespace(stage=request.stage),
        ),
    )

    with pytest.raises(ModelGatewayError) as exc:
        gateway.invoke_semantic_analysis(
            prompt=_prompt(
                schema="schema:llm_semantic_analysis@0.4.1",
                metadata={
                    "targetRef": "dbo.usp_Demo",
                    "procedureDefinitionIncluded": True,
                },
            ),
            profile=_profile(),
        )

    assert exc.value.code == "LLM_SP_TEXT_NOT_ALLOWED"


def test_framework_model_gateway_delegates_ai_draft_pack_to_existing_path() -> None:
    gateway = FrameworkModelGateway(
        fallback_gateway=FakeModelGateway(),
        structured_adapter=OpenAIAgentsStructuredAdapter(
            runner=lambda _agent, _prompt, _config: (_ for _ in ()).throw(
                AssertionError("AI Draft Pack must remain on the P44 workflow path")
            ),
            agent_factory=lambda request: SimpleNamespace(stage=request.stage),
        ),
    )

    invocation = gateway.draft_ai_java_mybatis_pack(
        prompt=_prompt(
            schema="schema:ai_java_mybatis_draft_pack@0.1.0",
            metadata={"targetRef": "dbo.usp_Demo", "allowedEvidenceRefs": ["fact.demo"]},
            payload={"targetRef": "dbo.usp_Demo"},
        ),
        profile=_profile(),
    )

    assert invocation.provider == "fake-openai-compatible"
    assert invocation.structured_output["schemaVersion"] == "AiJavaMyBatisDraftPack.v0.1"


def _prompt(
    *,
    schema: str,
    metadata: dict[str, Any],
    payload: dict[str, Any] | None = None,
) -> RenderedPrompt:
    body = payload or {"targetRef": metadata.get("targetRef")}
    user_prompt = json.dumps(body, ensure_ascii=False, sort_keys=True)
    return RenderedPrompt(
        prompt_version="prompt:p48_test@0.1.0",
        output_schema_version=schema,
        system_prompt="Return strict JSON only.",
        user_prompt=user_prompt,
        input_hash=stable_json_hash(body),
        prompt_hash=stable_json_hash({"prompt": "p48", "body": body}),
        metadata=dict(metadata),
    )


def _profile() -> ModelProfile:
    return ModelProfile(
        profile_id="openai_fast_test",
        model="gpt-5-nano",
        registry_ref="model:openai_fast_test@gpt-5-nano@0.1.0",
        reasoning_effort="low",
    )


def _semantic_output() -> dict[str, Any]:
    return {
        "businessRules": [
            {
                "category": "DEMO_RULE",
                "summary": "Demo behavior inferred from deterministic evidence.",
                "status": "INFERRED_DESCRIPTION",
                "evidenceRefs": ["fact.demo"],
            }
        ],
        "modernizationPoints": [],
        "riskFlags": [],
        "reviewMarkers": [],
        "conversionGuidance": [],
        "migrationGuideInsights": [],
        "assumptions": [],
    }


def _tool_plan_output(tool_name: str) -> dict[str, Any]:
    return {
        "toolRequests": [
            {
                "toolName": tool_name,
                "arguments": {"targetRef": "dbo.TableA"},
                "reason": "Collect read-only metadata evidence.",
                "expectedEvidenceUse": "Support a review-required structured claim.",
            }
        ],
        "assumptions": [],
        "reviewMarkers": [],
    }


def _metadata_analysis_output() -> dict[str, Any]:
    return {
        "summary": "Metadata evidence requires review.",
        "objectInsights": [
            {
                "code": "TABLE_REVIEW_REQUIRED",
                "objectRef": "dbo.TableA",
                "summary": "Review deterministic metadata before conversion.",
                "status": "REVIEW_REQUIRED",
                "evidenceRefs": ["fact.demo"],
            }
        ],
        "insightGroups": [
            {
                "category": "DTO_READINESS",
                "insights": [
                    {
                        "code": "DTO_REVIEW_REQUIRED",
                        "objectRef": "dbo.TableA",
                        "summary": "DTO shape needs manual review.",
                        "status": "REVIEW_REQUIRED",
                        "evidenceRefs": ["fact.demo"],
                    }
                ],
            }
        ],
        "dtoReadiness": [
            {
                "objectRef": "dbo.TableA",
                "status": "REVIEW_REQUIRED",
                "fieldCount": 1,
                "reviewReasons": ["Metadata fixture is incomplete."],
                "evidenceRefs": ["fact.demo"],
            }
        ],
        "reviewMarkers": [],
        "assumptions": [],
    }


def _operation_model_fixture() -> dict[str, Any]:
    payload = yaml.safe_load(OPERATION_FIXTURE.read_text(encoding="utf-8"))
    return deepcopy(payload["operation_model"])


def _allowed_operation_refs(payload: dict[str, Any]) -> list[str]:
    model = validate_sp_operation_model_output(payload)
    return sorted(set(all_sp_operation_model_evidence_refs(model)))
