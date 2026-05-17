from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import replace as dataclass_replace
from typing import Any

from ai_agent_domain import SpStatementContract
from ai_agent_runtime.gateway import ModelGateway, model_profile_from_env
from ai_agent_runtime.models import AgentRunPayload, AgentRunStatus, stable_json_hash
from ai_agent_runtime.operation_model import (
    OperationModelValidationError,
    SpOperationModelPlannerOutput,
    validate_sp_operation_model_output,
)
from ai_agent_runtime.prompts import render_sp_operation_model_prompt

AGENT_TYPE = "LLM_SP_OPERATION_PLANNER"
EVIDENCE_REPAIRED_MARKER = "SP_OPERATION_MODEL_EVIDENCE_REPAIRED"


def build_sp_operation_model_run(
    *,
    target_ref: str,
    statement_evidence: Sequence[Mapping[str, Any] | SpStatementContract],
    model_gateway: ModelGateway,
    profile_id: str | None,
    allowed_evidence_refs: Sequence[str] | None = None,
) -> AgentRunPayload:
    statements = [_statement_to_storage_dict(statement) for statement in statement_evidence]
    allowed_refs = _allowed_evidence_refs(
        statements=statements,
        additional_refs=allowed_evidence_refs,
    )
    prompt = render_sp_operation_model_prompt(
        target_ref=target_ref,
        statement_evidence=statements,
        allowed_evidence_refs=allowed_refs,
    )
    profile = model_profile_from_env(profile_id)
    invocation = model_gateway.plan_sp_operation_model(prompt=prompt, profile=profile)
    model, repaired = _validated_or_repaired(invocation.structured_output, allowed_refs)
    structured_output = model.to_storage_dict()
    if repaired:
        invocation = dataclass_replace(
            invocation,
            structured_output=structured_output,
            output_hash=stable_json_hash(structured_output),
            component_invocations=(
                *invocation.component_invocations,
                {
                    "component": "sp_operation_model_evidence_guard",
                    "status": "SUCCEEDED",
                    "action": "repaired_invalid_or_empty_evidence_refs",
                    "reviewMarker": EVIDENCE_REPAIRED_MARKER,
                },
            ),
        )
    return AgentRunPayload(
        agent_type=AGENT_TYPE,
        status=AgentRunStatus.SUCCEEDED,
        target_ref=target_ref,
        structured_output=structured_output,
        model_invocation=invocation,
        summary=(
            f"SP operation model planned {len(model.operations)} operations and "
            f"{len(model.dto_blueprints)} DTO blueprints."
        ),
    )


def _statement_to_storage_dict(
    statement: Mapping[str, Any] | SpStatementContract,
) -> dict[str, Any]:
    if isinstance(statement, SpStatementContract):
        return statement.model_dump(by_alias=True, mode="json")
    return SpStatementContract.model_validate(statement).model_dump(by_alias=True, mode="json")


def _allowed_evidence_refs(
    *,
    statements: Sequence[Mapping[str, Any]],
    additional_refs: Sequence[str] | None,
) -> tuple[str, ...]:
    refs: list[str] = []
    for statement in statements:
        refs.extend(str(ref) for ref in statement.get("evidenceRefs", []) if str(ref).strip())
    refs.extend(str(ref) for ref in (additional_refs or ()) if str(ref).strip())
    return tuple(dict.fromkeys(refs))


def _validated_or_repaired(
    payload: Mapping[str, Any],
    allowed_refs: Sequence[str],
) -> tuple[SpOperationModelPlannerOutput, bool]:
    try:
        return (
            validate_sp_operation_model_output(
                payload,
                allowed_evidence_refs=allowed_refs,
            ),
            False,
        )
    except OperationModelValidationError as exc:
        if not allowed_refs:
            raise
        if not _evidence_findings_only(exc.findings):
            raise
    repaired_payload = _repair_evidence_refs(
        payload,
        allowed_refs=allowed_refs,
        fallback_ref=allowed_refs[0],
    )
    model = validate_sp_operation_model_output(
        repaired_payload,
        allowed_evidence_refs=allowed_refs,
    )
    return model, True


def _evidence_findings_only(findings: Sequence[str]) -> bool:
    evidence_markers = (
        "evidenceRefs must not be empty",
        "evidenceRefs contains unknown ref",
        "unknown ref",
    )
    return bool(findings) and all(
        any(marker in finding for marker in evidence_markers)
        for finding in findings
    )


def _repair_evidence_refs(
    payload: Mapping[str, Any],
    *,
    allowed_refs: Sequence[str],
    fallback_ref: str,
) -> dict[str, Any]:
    repaired = deepcopy(dict(payload))
    _repair_evidence_refs_in_value(
        repaired,
        allowed_refs=set(allowed_refs),
        fallback_ref=fallback_ref,
    )
    markers = list(repaired.get("reviewMarkers") or [])
    if EVIDENCE_REPAIRED_MARKER not in markers:
        markers.append(EVIDENCE_REPAIRED_MARKER)
    repaired["reviewMarkers"] = markers
    return repaired


def _repair_evidence_refs_in_value(
    value: Any,
    *,
    allowed_refs: set[str],
    fallback_ref: str,
) -> None:
    if isinstance(value, dict):
        for key, item in list(value.items()):
            if key == "evidenceRefs":
                refs = (
                    [str(ref) for ref in item if str(ref) in allowed_refs]
                    if isinstance(item, list)
                    else []
                )
                value[key] = refs or [fallback_ref]
                continue
            _repair_evidence_refs_in_value(
                item,
                allowed_refs=allowed_refs,
                fallback_ref=fallback_ref,
            )
    elif isinstance(value, list):
        for item in value:
            _repair_evidence_refs_in_value(
                item,
                allowed_refs=allowed_refs,
                fallback_ref=fallback_ref,
            )
