from __future__ import annotations

import os
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from ai_agent_runtime.framework_adapter import (
    AiStructuredFrameworkAdapter,
    AiStructuredFrameworkAdapterRequest,
    OpenAIAgentsStructuredAdapter,
)
from ai_agent_runtime.gateway import (
    ModelGateway,
    ModelGatewayError,
    _prompt_operation_statement_evidence,
    _sp_operation_model_text_with_statement_evidence_defaults,
)
from ai_agent_runtime.models import (
    AiToolPlanningOutput,
    LlmSemanticAnalysisOutput,
    MetadataAnalysisOutput,
    ModelInvocationRecord,
    ModelProfile,
    RenderedPrompt,
)
from ai_agent_runtime.operation_model import (
    SpOperationModelPlannerOutput,
    parse_sp_operation_model_json,
)

STRUCTURED_STAGE_SEMANTIC_ANALYSIS = "llm_semantic_analysis"
STRUCTURED_STAGE_METADATA_TOOL_PLANNING = "metadata_tool_planning"
STRUCTURED_STAGE_METADATA_ANALYSIS = "metadata_analysis"
STRUCTURED_STAGE_PLATFORM_TOOL_PLANNING = "platform_tool_planning"
STRUCTURED_STAGE_SP_OPERATION_MODEL = "sp_operation_model"


@dataclass(frozen=True)
class FrameworkModelGateway:
    fallback_gateway: ModelGateway
    structured_adapter: AiStructuredFrameworkAdapter
    provider: str = "openai-agents-sdk"

    def invoke_semantic_analysis(
        self,
        *,
        prompt: RenderedPrompt,
        profile: ModelProfile,
    ) -> ModelInvocationRecord:
        _ensure_sp_text_allowed(prompt)
        return self._invoke_structured(
            prompt=prompt,
            profile=profile,
            schema_name="llm_semantic_analysis",
            stage=STRUCTURED_STAGE_SEMANTIC_ANALYSIS,
            parser=LlmSemanticAnalysisOutput.model_validate_json,
            invalid_code="OPENAI_STRUCTURED_OUTPUT_INVALID",
            output_type=LlmSemanticAnalysisOutput,
        )

    def plan_metadata_tools(
        self,
        *,
        prompt: RenderedPrompt,
        profile: ModelProfile,
    ) -> ModelInvocationRecord:
        return self._invoke_structured(
            prompt=prompt,
            profile=profile,
            schema_name="metadata_tool_plan",
            stage=STRUCTURED_STAGE_METADATA_TOOL_PLANNING,
            parser=AiToolPlanningOutput.model_validate_json,
            invalid_code="OPENAI_TOOL_PLAN_INVALID",
            allowed_tool_names=_strings(prompt.metadata.get("toolNames") or ()),
            output_type=AiToolPlanningOutput,
        )

    def analyze_metadata(
        self,
        *,
        prompt: RenderedPrompt,
        profile: ModelProfile,
    ) -> ModelInvocationRecord:
        return self._invoke_structured(
            prompt=prompt,
            profile=profile,
            schema_name="metadata_analysis",
            stage=STRUCTURED_STAGE_METADATA_ANALYSIS,
            parser=MetadataAnalysisOutput.model_validate_json,
            invalid_code="OPENAI_METADATA_ANALYSIS_INVALID",
            output_type=MetadataAnalysisOutput,
        )

    def plan_platform_tools(
        self,
        *,
        prompt: RenderedPrompt,
        profile: ModelProfile,
    ) -> ModelInvocationRecord:
        return self._invoke_structured(
            prompt=prompt,
            profile=profile,
            schema_name="platform_tool_plan",
            stage=STRUCTURED_STAGE_PLATFORM_TOOL_PLANNING,
            parser=AiToolPlanningOutput.model_validate_json,
            invalid_code="OPENAI_PLATFORM_TOOL_PLAN_INVALID",
            allowed_tool_names=_strings(prompt.metadata.get("toolNames") or ()),
            output_type=AiToolPlanningOutput,
        )

    def plan_sp_operation_model(
        self,
        *,
        prompt: RenderedPrompt,
        profile: ModelProfile,
    ) -> ModelInvocationRecord:
        _ensure_sp_text_allowed(prompt)
        allowed_refs = _strings(prompt.metadata.get("allowedEvidenceRefs") or ())
        statement_defaults = _prompt_operation_statement_evidence(prompt)

        def parse_with_statement_defaults(output_text: str) -> SpOperationModelPlannerOutput:
            return parse_sp_operation_model_json(
                _sp_operation_model_text_with_statement_evidence_defaults(
                    output_text,
                    statement_defaults=statement_defaults,
                ),
                allowed_evidence_refs=allowed_refs,
            )

        return self._invoke_structured(
            prompt=prompt,
            profile=profile,
            schema_name="sp_operation_model",
            stage=STRUCTURED_STAGE_SP_OPERATION_MODEL,
            parser=parse_with_statement_defaults,
            invalid_code="OPENAI_SP_OPERATION_MODEL_INVALID",
            output_type=SpOperationModelPlannerOutput,
        )

    def draft_ai_java_mybatis_pack(
        self,
        *,
        prompt: RenderedPrompt,
        profile: ModelProfile,
    ) -> ModelInvocationRecord:
        return self.fallback_gateway.draft_ai_java_mybatis_pack(
            prompt=prompt,
            profile=profile,
        )

    def _invoke_structured(
        self,
        *,
        prompt: RenderedPrompt,
        profile: ModelProfile,
        schema_name: str,
        stage: str,
        parser: Callable[[str], Any],
        invalid_code: str,
        allowed_tool_names: Sequence[str] = (),
        output_type: Any | None = None,
    ) -> ModelInvocationRecord:
        _ensure_remote_api_key()
        return self.structured_adapter.invoke_structured(
            request=AiStructuredFrameworkAdapterRequest(
                target_ref=_target_ref(prompt),
                prompt=prompt,
                profile=profile,
                schema_name=schema_name,
                stage=stage,
                parser=parser,
                invalid_code=invalid_code,
                allowed_tool_names=allowed_tool_names,
                output_type=output_type,
            )
        )


def _ensure_remote_api_key() -> None:
    if (
        os.getenv("LLM_ENABLE_REMOTE", "0").strip() == "1"
        and not os.getenv("OPENAI_API_KEY", "").strip()
    ):
        raise ModelGatewayError(
            "OPENAI_API_KEY is required when LLM_ENABLE_REMOTE=1.",
            code="OPENAI_API_KEY_MISSING",
        )


def openai_agents_framework_model_gateway(
    *,
    fallback_gateway: ModelGateway,
) -> FrameworkModelGateway:
    return FrameworkModelGateway(
        fallback_gateway=fallback_gateway,
        structured_adapter=OpenAIAgentsStructuredAdapter(),
    )


def _ensure_sp_text_allowed(prompt: RenderedPrompt) -> None:
    if (
        prompt.metadata.get("procedureDefinitionIncluded")
        or prompt.metadata.get("sourceContextIncluded")
    ) and os.getenv("LLM_ALLOW_SP_TEXT", "0").strip() != "1":
        raise ModelGatewayError(
            "LLM_ALLOW_SP_TEXT=1 is required before sending SP source text.",
            code="LLM_SP_TEXT_NOT_ALLOWED",
        )


def _target_ref(prompt: RenderedPrompt) -> str:
    target_ref = prompt.metadata.get("targetRef")
    if target_ref:
        return str(target_ref)
    payload = _prompt_payload(prompt)
    return str(payload.get("targetRef") or "")


def _prompt_payload(prompt: RenderedPrompt) -> Mapping[str, Any]:
    try:
        import json

        payload = json.loads(prompt.user_prompt)
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, Mapping) else {}


def _strings(value: Any) -> tuple[str, ...]:
    if isinstance(value, str | bytes) or not isinstance(value, Sequence):
        return ()
    return tuple(dict.fromkeys(str(item) for item in value if str(item).strip()))
