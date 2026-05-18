from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace as dataclass_replace
from typing import Any

from ai_agent_runtime.ai_draft_pack import (
    AiDraftPackValidationError,
    validate_ai_java_mybatis_draft_pack_output,
)
from ai_agent_runtime.gateway import ModelGateway, ModelGatewayError, model_profile_from_env
from ai_agent_runtime.models import AgentRunPayload, AgentRunStatus, stable_json_hash
from ai_agent_runtime.prompts import render_ai_java_mybatis_draft_pack_prompt

AGENT_TYPE = "LLM_AI_DRAFT_PACK_PLANNER"
REPAIRABLE_AI_DRAFT_PACK_GATEWAY_CODES = frozenset({"OPENAI_AI_DRAFT_PACK_INVALID"})
REPAIR_COMPONENT = "ai_draft_pack_repair_stage"
REFERENCE_GUARD_COMPONENT = "ai_draft_pack_reference_guard"


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
    profile = model_profile_from_env(profile_id)
    stage = "repair" if repair_context else "file_content"
    try:
        return _build_ai_java_mybatis_draft_pack_run_stage(
            target_ref=target_ref,
            sanitized_draft_context=sanitized_draft_context,
            expected_inventory=expected_inventory,
            quality_gates=quality_gates,
            model_gateway=model_gateway,
            profile=profile,
            allowed_refs=allowed_refs,
            stage=stage,
            repair_context=repair_context,
        )
    except (ModelGatewayError, AiDraftPackValidationError) as exc:
        if repair_context is not None or not _is_repairable_planner_exception(exc):
            raise
        retry_context = _repair_context_from_exception(exc)
        return _build_ai_java_mybatis_draft_pack_run_stage(
            target_ref=target_ref,
            sanitized_draft_context=sanitized_draft_context,
            expected_inventory=expected_inventory,
            quality_gates=quality_gates,
            model_gateway=model_gateway,
            profile=profile,
            allowed_refs=allowed_refs,
            stage="repair",
            repair_context=retry_context,
        )


def _build_ai_java_mybatis_draft_pack_run_stage(
    *,
    target_ref: str,
    sanitized_draft_context: Mapping[str, Any],
    expected_inventory: Sequence[Mapping[str, Any]],
    quality_gates: Mapping[str, Any],
    model_gateway: ModelGateway,
    profile: Any,
    allowed_refs: Sequence[str],
    stage: str,
    repair_context: Mapping[str, Any] | None,
) -> AgentRunPayload:
    prompt = render_ai_java_mybatis_draft_pack_prompt(
        target_ref=target_ref,
        sanitized_draft_context=sanitized_draft_context,
        expected_inventory=expected_inventory,
        quality_gates=quality_gates,
        allowed_evidence_refs=allowed_refs,
        stage=stage,
        repair_context=dict(repair_context or {}) if repair_context else None,
    )
    invocation = model_gateway.draft_ai_java_mybatis_pack(prompt=prompt, profile=profile)
    model = validate_ai_java_mybatis_draft_pack_output(invocation.structured_output)
    structured_output = model.to_storage_dict()
    guard_component = None
    if repair_context is not None:
        guard_component = _reference_guard_component(
            structured_output=structured_output,
            expected_inventory=expected_inventory,
        )
    structured_output["qualityGates"] = dict(quality_gates)
    if invocation.structured_output != structured_output or guard_component is not None:
        component_invocations = invocation.component_invocations
        if guard_component is not None:
            component_invocations = (*component_invocations, guard_component)
        invocation = dataclass_replace(
            invocation,
            structured_output=structured_output,
            output_hash=stable_json_hash(structured_output),
            component_invocations=component_invocations,
        )
    if repair_context is not None:
        invocation = dataclass_replace(
            invocation,
            component_invocations=(
                *invocation.component_invocations,
                _repair_component(repair_context),
            ),
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


def _is_repairable_planner_exception(exc: Exception) -> bool:
    if isinstance(exc, AiDraftPackValidationError):
        return True
    if isinstance(exc, ModelGatewayError):
        return exc.code in REPAIRABLE_AI_DRAFT_PACK_GATEWAY_CODES
    return False


def _reference_guard_component(
    *,
    structured_output: dict[str, Any],
    expected_inventory: Sequence[Mapping[str, Any]],
) -> dict[str, Any] | None:
    expected_references = _expected_non_dto_references(expected_inventory)
    if not expected_references:
        return None
    repaired_files: list[str] = []
    for file in structured_output.get("files", []):
        if not isinstance(file, dict):
            continue
        artifact_type = str(file.get("artifactType") or "")
        references = expected_references.get(artifact_type)
        if not references:
            continue
        if file.get("references") != references:
            file["references"] = list(references)
            repaired_files.append(str(file.get("path") or artifact_type))
        content = str(file.get("content") or "")
        missing = [reference for reference in references if reference not in content]
        if missing:
            file["content"] = _append_reference_comment(
                content=content,
                artifact_type=artifact_type,
                missing=missing,
            )
            repaired_files.append(str(file.get("path") or artifact_type))
    if not repaired_files:
        return None
    return {
        "component": REFERENCE_GUARD_COMPONENT,
        "status": "SUCCEEDED",
        "action": "preserved_expected_dto_references_in_draft_metadata_and_comments",
        "fileCount": len(tuple(dict.fromkeys(repaired_files))),
    }


def _expected_non_dto_references(
    expected_inventory: Sequence[Mapping[str, Any]],
) -> dict[str, list[str]]:
    refs_by_type: dict[str, list[str]] = {}
    for item in expected_inventory:
        artifact_type = str(item.get("artifactType") or "")
        if artifact_type not in {
            "SERVICE_DRAFT",
            "MAPPER_INTERFACE",
            "MAPPER_XML",
        }:
            continue
        refs = [
            str(ref)
            for ref in item.get("references", [])
            if str(ref).strip()
        ]
        if refs:
            refs_by_type[artifact_type] = list(dict.fromkeys(refs))
    return refs_by_type


def _append_reference_comment(
    *,
    content: str,
    artifact_type: str,
    missing: Sequence[str],
) -> str:
    reference_text = " ".join(dict.fromkeys(str(item) for item in missing if str(item)))
    if artifact_type == "MAPPER_XML":
        comment = f"  <!-- REVIEW_REQUIRED DTO references: {reference_text} -->"
        if "</mapper>" in content:
            return content.replace("</mapper>", f"{comment}\n</mapper>", 1)
        return f"{content}\n<!-- REVIEW_REQUIRED DTO references: {reference_text} -->"
    return f"{content}\n// REVIEW_REQUIRED DTO references: {reference_text}"


def _repair_context_from_exception(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, AiDraftPackValidationError):
        return {
            "failureStage": "schema_validation",
            "errorClass": exc.__class__.__name__,
            "reason": "AiJavaMyBatisDraftPack schema validation failed.",
            "validationFindings": _safe_validation_findings(exc.findings),
        }
    if isinstance(exc, ModelGatewayError):
        return {
            "failureStage": "model_gateway_structured_output",
            "errorCode": exc.code,
            "errorClass": exc.__class__.__name__,
            "reason": "Provider output could not be parsed as AiJavaMyBatisDraftPack.",
            "providerError": _safe_provider_error(exc.provider_error),
        }
    return {
        "failureStage": "ai_draft_pack_planner",
        "errorClass": exc.__class__.__name__,
        "reason": "AI Draft Pack planner failed before repair.",
    }


def _repair_component(repair_context: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "component": REPAIR_COMPONENT,
        "status": "SUCCEEDED",
        "action": "retried_ai_java_mybatis_draft_pack_with_sanitized_repair_context",
        "failureStage": str(repair_context.get("failureStage") or "unknown"),
        "errorCode": str(repair_context.get("errorCode") or ""),
        "errorClass": str(repair_context.get("errorClass") or ""),
    }


def _safe_validation_findings(findings: Sequence[str]) -> list[str]:
    safe: list[str] = []
    for finding in findings[:12]:
        text = str(finding)
        safe.append(text[:300])
    return safe


def _safe_provider_error(provider_error: Mapping[str, Any]) -> dict[str, str]:
    safe: dict[str, str] = {}
    for key in ("type", "code", "param", "message", "findingCount", "findings"):
        value = provider_error.get(key)
        if value is not None:
            safe[key] = str(value)[:300]
    return safe


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
