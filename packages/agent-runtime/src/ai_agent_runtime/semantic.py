from __future__ import annotations

from typing import Any

from ai_agent_runtime.gateway import ModelGateway, model_profile_from_env
from ai_agent_runtime.models import AgentRunPayload, AgentRunStatus, LlmSemanticAnalysisOutput
from ai_agent_runtime.prompts import render_semantic_analysis_prompt

AGENT_TYPE = "LLM_SEMANTIC_ANALYST"


def build_semantic_analysis_run(
    *,
    target_ref: str,
    metadata: dict[str, Any],
    static_analysis: dict[str, Any] | None,
    procedure_definition: str | None,
    model_gateway: ModelGateway,
    profile_id: str | None,
) -> AgentRunPayload:
    prompt = render_semantic_analysis_prompt(
        target_ref=target_ref,
        metadata=metadata,
        static_analysis=static_analysis,
        procedure_definition=procedure_definition,
    )
    profile = model_profile_from_env(profile_id)
    invocation = model_gateway.invoke_semantic_analysis(prompt=prompt, profile=profile)
    output = LlmSemanticAnalysisOutput.model_validate(invocation.structured_output)
    return AgentRunPayload(
        agent_type=AGENT_TYPE,
        status=AgentRunStatus.SUCCEEDED,
        target_ref=target_ref,
        structured_output=output.to_storage_dict(),
        model_invocation=invocation,
        summary=_summary(output),
    )


def merge_llm_semantic_analysis(
    *,
    deterministic_context: dict[str, Any],
    llm_output: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = dict(deterministic_context)
    if not llm_output:
        return merged
    output = LlmSemanticAnalysisOutput.model_validate(llm_output)
    merged["llmSemanticAnalysis"] = output.to_storage_dict()
    return merged


def _summary(output: LlmSemanticAnalysisOutput) -> str:
    return (
        f"{len(output.business_rules)} business rules, "
        f"{len(output.modernization_points)} modernization points, "
        f"{len(output.risk_flags)} risk flags, "
        f"{len(output.review_markers)} review markers"
    )
