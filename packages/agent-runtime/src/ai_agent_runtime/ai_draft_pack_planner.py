from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace as dataclass_replace
from typing import Any

from ai_agent_runtime.ai_draft_pack import validate_ai_java_mybatis_draft_pack_output
from ai_agent_runtime.gateway import ModelGateway, model_profile_from_env
from ai_agent_runtime.models import AgentRunPayload, AgentRunStatus, stable_json_hash
from ai_agent_runtime.prompts import render_ai_java_mybatis_draft_pack_prompt

AGENT_TYPE = "LLM_AI_DRAFT_PACK_PLANNER"


def build_ai_java_mybatis_draft_pack_run(
    *,
    target_ref: str,
    sanitized_draft_context: Mapping[str, Any],
    expected_inventory: Sequence[Mapping[str, Any]],
    quality_gates: Mapping[str, Any],
    model_gateway: ModelGateway,
    profile_id: str | None,
    allowed_evidence_refs: Sequence[str] | None = None,
    repair_context: Mapping[str, Any] | None = None,
) -> AgentRunPayload:
    allowed_refs = _allowed_evidence_refs(
        context=sanitized_draft_context,
        inventory=expected_inventory,
        additional_refs=allowed_evidence_refs,
    )
    prompt = render_ai_java_mybatis_draft_pack_prompt(
        target_ref=target_ref,
        sanitized_draft_context=sanitized_draft_context,
        expected_inventory=expected_inventory,
        quality_gates=quality_gates,
        allowed_evidence_refs=allowed_refs,
        stage="file_content",
        repair_context=repair_context,
    )
    profile = model_profile_from_env(profile_id)
    invocation = model_gateway.draft_ai_java_mybatis_pack(prompt=prompt, profile=profile)
    model = validate_ai_java_mybatis_draft_pack_output(invocation.structured_output)
    structured_output = model.to_storage_dict()
    if invocation.structured_output != structured_output:
        invocation = dataclass_replace(
            invocation,
            structured_output=structured_output,
            output_hash=stable_json_hash(structured_output),
        )
    return AgentRunPayload(
        agent_type=AGENT_TYPE,
        status=AgentRunStatus.SUCCEEDED,
        target_ref=model.target_ref,
        structured_output=structured_output,
        model_invocation=invocation,
        summary=(
            f"AI Java/MyBatis draft pack planned {len(model.files)} files "
            f"for {model.target_ref}."
        ),
    )


def _allowed_evidence_refs(
    *,
    context: Mapping[str, Any],
    inventory: Sequence[Mapping[str, Any]],
    additional_refs: Sequence[str] | None,
) -> tuple[str, ...]:
    refs: list[str] = []
    refs.extend(str(ref) for ref in context.get("evidenceRefs", []) if str(ref).strip())
    refs.extend(str(ref) for ref in context.get("allowedEvidenceRefs", []) if str(ref).strip())
    for file in inventory:
        refs.extend(str(ref) for ref in file.get("evidenceRefs", []) if str(ref).strip())
    refs.extend(str(ref) for ref in (additional_refs or ()) if str(ref).strip())
    return tuple(dict.fromkeys(refs))
