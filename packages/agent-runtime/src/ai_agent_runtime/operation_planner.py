from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, replace as dataclass_replace
from typing import Any

from ai_agent_domain import SpStatementContract
from ai_agent_runtime.gateway import ModelGateway, ModelGatewayError, model_profile_from_env
from ai_agent_runtime.models import (
    AgentRunPayload,
    AgentRunStatus,
    ModelInvocationRecord,
    ModelProfile,
    RenderedPrompt,
    stable_json_hash,
)
from ai_agent_runtime.operation_model import (
    OperationModelValidationError,
    SpOperationModelPlannerOutput,
    validate_sp_operation_model_output,
)
from ai_agent_runtime.prompts import render_sp_operation_model_prompt

AGENT_TYPE = "LLM_SP_OPERATION_PLANNER"
BRANCH_PLANNER_AGENT_TYPE = "LLM_SP_OPERATION_BRANCH_PLANNER"
REPAIR_AGENT_TYPE = "LLM_SP_OPERATION_MODEL_REPAIR"
EVIDENCE_REPAIRED_MARKER = "SP_OPERATION_MODEL_EVIDENCE_REPAIRED"
VALIDATOR_REPAIRED_MARKER = "SP_OPERATION_MODEL_VALIDATOR_REPAIRED"
OPENAI_SP_OPERATION_MODEL_INVALID = "OPENAI_SP_OPERATION_MODEL_INVALID"
MAX_REPAIR_FINDINGS = 12


@dataclass(frozen=True)
class OperationModelRunResult:
    final_run: AgentRunPayload
    sidecar_runs: tuple[AgentRunPayload, ...] = ()


class OperationModelPlanningError(ModelGatewayError):
    def __init__(
        self,
        message: str,
        *,
        code: str,
        provider_error: Mapping[str, Any] | None = None,
        sidecar_runs: Sequence[AgentRunPayload] = (),
    ) -> None:
        super().__init__(message, code=code, provider_error=provider_error or {})
        self.sidecar_runs = tuple(sidecar_runs)


def build_sp_operation_model_run(
    *,
    target_ref: str,
    statement_evidence: Sequence[Mapping[str, Any] | SpStatementContract],
    model_gateway: ModelGateway,
    profile_id: str | None,
    allowed_evidence_refs: Sequence[str] | None = None,
) -> AgentRunPayload:
    return build_sp_operation_model_run_result(
        target_ref=target_ref,
        statement_evidence=statement_evidence,
        model_gateway=model_gateway,
        profile_id=profile_id,
        allowed_evidence_refs=allowed_evidence_refs,
    ).final_run


def build_sp_operation_model_run_result(
    *,
    target_ref: str,
    statement_evidence: Sequence[Mapping[str, Any] | SpStatementContract],
    model_gateway: ModelGateway,
    profile_id: str | None,
    allowed_evidence_refs: Sequence[str] | None = None,
) -> OperationModelRunResult:
    statements = [_statement_to_storage_dict(statement) for statement in statement_evidence]
    allowed_refs = _allowed_evidence_refs(
        statements=statements,
        additional_refs=allowed_evidence_refs,
    )
    profile = model_profile_from_env(profile_id)
    sidecar_runs: list[AgentRunPayload] = []
    branch_plan_context: dict[str, Any] = {}

    if _requires_task_split(statements):
        branch_prompt = render_sp_operation_model_prompt(
            target_ref=target_ref,
            statement_evidence=statements,
            allowed_evidence_refs=allowed_refs,
            task_mode="branch_plan",
            stage="operation_model_branch_plan",
        )
        try:
            branch_run = _invoke_operation_model_once(
                agent_type=BRANCH_PLANNER_AGENT_TYPE,
                target_ref=target_ref,
                prompt=branch_prompt,
                model_gateway=model_gateway,
                profile=profile,
                allowed_refs=allowed_refs,
                summary_prefix="SP operation branch plan",
            )
        except (ModelGatewayError, OperationModelValidationError) as exc:
            failed_run = _failed_sidecar_run(
                agent_type=BRANCH_PLANNER_AGENT_TYPE,
                target_ref=target_ref,
                prompt=branch_prompt,
                profile=profile,
                exc=exc,
                failure_stage="operation_model_branch_plan",
            )
            raise OperationModelPlanningError(
                "SP operation branch planning failed before valid output.",
                code=_exception_code(exc),
                provider_error=_exception_provider_error(
                    exc,
                    failure_stage="operation_model_branch_plan",
                ),
                sidecar_runs=(*sidecar_runs, failed_run),
            ) from exc
        sidecar_runs.append(branch_run)
        branch_plan_context = _branch_plan_context(branch_run.structured_output)

    final_prompt = render_sp_operation_model_prompt(
        target_ref=target_ref,
        statement_evidence=statements,
        allowed_evidence_refs=allowed_refs,
        task_mode="final_model",
        branch_plan_context=branch_plan_context,
    )
    try:
        final_run = _invoke_operation_model_once(
            agent_type=AGENT_TYPE,
            target_ref=target_ref,
            prompt=final_prompt,
            model_gateway=model_gateway,
            profile=profile,
            allowed_refs=allowed_refs,
            summary_prefix="SP operation model",
        )
        return OperationModelRunResult(
            final_run=final_run,
            sidecar_runs=tuple(sidecar_runs),
        )
    except (ModelGatewayError, OperationModelValidationError) as exc:
        if not _repairable_operation_model_error(exc):
            raise OperationModelPlanningError(
                "SP operation model planning failed before valid output.",
                code=_exception_code(exc),
                provider_error=_exception_provider_error(
                    exc,
                    failure_stage="sp_operation_model_planner",
                ),
                sidecar_runs=tuple(sidecar_runs),
            ) from exc
        repair_prompt = render_sp_operation_model_prompt(
            target_ref=target_ref,
            statement_evidence=statements,
            allowed_evidence_refs=allowed_refs,
            task_mode="repair",
            stage="operation_model_repair",
            branch_plan_context=branch_plan_context,
            repair_context=_repair_context(exc),
        )
        try:
            repair_run = _invoke_operation_model_once(
                agent_type=REPAIR_AGENT_TYPE,
                target_ref=target_ref,
                prompt=repair_prompt,
                model_gateway=model_gateway,
                profile=profile,
                allowed_refs=allowed_refs,
                summary_prefix="SP operation model repair",
            )
        except (ModelGatewayError, OperationModelValidationError) as repair_exc:
            failed_repair = _failed_sidecar_run(
                agent_type=REPAIR_AGENT_TYPE,
                target_ref=target_ref,
                prompt=repair_prompt,
                profile=profile,
                exc=repair_exc,
                failure_stage="operation_model_repair",
            )
            raise OperationModelPlanningError(
                "SP operation model repair failed before valid output.",
                code=_exception_code(repair_exc),
                provider_error=_exception_provider_error(
                    repair_exc,
                    failure_stage="operation_model_repair",
                ),
                sidecar_runs=(*sidecar_runs, failed_repair),
            ) from repair_exc

    sidecar_runs.append(repair_run)
    final_run = _final_run_from_repair(repair_run)
    return OperationModelRunResult(
        final_run=final_run,
        sidecar_runs=tuple(sidecar_runs),
    )


def _invoke_operation_model_once(
    *,
    agent_type: str,
    target_ref: str,
    prompt: RenderedPrompt,
    model_gateway: ModelGateway,
    profile: ModelProfile,
    allowed_refs: Sequence[str],
    summary_prefix: str,
) -> AgentRunPayload:
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
        agent_type=agent_type,
        status=AgentRunStatus.SUCCEEDED,
        target_ref=target_ref,
        structured_output=structured_output,
        model_invocation=invocation,
        summary=(
            f"{summary_prefix} planned {len(model.operations)} operations and "
            f"{len(model.dto_blueprints)} DTO blueprints."
        ),
    )


def _final_run_from_repair(repair_run: AgentRunPayload) -> AgentRunPayload:
    invocation = dataclass_replace(
        repair_run.model_invocation,
        component_invocations=(
            *repair_run.model_invocation.component_invocations,
            {
                "component": "sp_operation_model_validator_repair",
                "status": "SUCCEEDED",
                "action": "used_repaired_operation_model_as_final",
                "reviewMarker": VALIDATOR_REPAIRED_MARKER,
            },
        ),
    )
    markers = list(repair_run.structured_output.get("reviewMarkers") or [])
    if VALIDATOR_REPAIRED_MARKER not in markers:
        markers.append(VALIDATOR_REPAIRED_MARKER)
    structured_output = dict(repair_run.structured_output)
    structured_output["reviewMarkers"] = markers
    invocation = dataclass_replace(
        invocation,
        structured_output=structured_output,
        output_hash=stable_json_hash(structured_output),
    )
    return AgentRunPayload(
        agent_type=AGENT_TYPE,
        status=AgentRunStatus.SUCCEEDED,
        target_ref=repair_run.target_ref,
        structured_output=structured_output,
        model_invocation=invocation,
        summary=(
            "SP operation model planned after validator-guided repair "
            f"with {len(structured_output.get('operations') or [])} operations and "
            f"{len(structured_output.get('dtoBlueprints') or [])} DTO blueprints."
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


def _repairable_operation_model_error(exc: Exception) -> bool:
    if isinstance(exc, OperationModelValidationError):
        return not _evidence_findings_only(exc.findings)
    if isinstance(exc, ModelGatewayError):
        return exc.code == OPENAI_SP_OPERATION_MODEL_INVALID
    return False


def _repair_context(exc: Exception) -> dict[str, Any]:
    findings = _exception_findings(exc)
    return {
        "repairReason": _exception_code(exc),
        "validationFindingCount": len(findings),
        "validationFindings": findings[:MAX_REPAIR_FINDINGS],
        "rawFailedOutputIncluded": False,
        "instructions": (
            "Repair from validator findings, statementEvidence, and branchPlanContext only."
        ),
    }


def _requires_task_split(statements: Sequence[Mapping[str, Any]]) -> bool:
    if len(statements) >= 20:
        return True
    operations = {str(statement.get("operation") or "").upper() for statement in statements}
    if operations & {"INSERT", "UPDATE", "DELETE", "EXECUTE"}:
        return len(statements) >= 4
    branch_keywords = (
        "crud",
        "flag",
        "kind",
        "type",
        "status",
        "gubun",
        "mode",
        "svalue",
        "approval",
        "vendor",
        "online",
        "batch",
    )
    for statement in statements:
        phase = str(statement.get("phase") or "").lower()
        inputs = " ".join(str(item).lower() for item in statement.get("inputs", []) or [])
        if any(keyword in phase or keyword in inputs for keyword in branch_keywords):
            return True
    return False


def _branch_plan_context(output: Mapping[str, Any]) -> dict[str, Any]:
    operations = [
        {
            "operationId": str(operation.get("operationId") or "")[:80],
            "crudFlag": str(operation.get("crudFlag") or "")[:40],
            "statementRefs": _string_list(operation.get("statementRefs"), limit=40),
            "dtoBlueprintRefs": _string_list(operation.get("dtoBlueprintRefs"), limit=40),
            "branchVariables": _string_list(
                (operation.get("branchCondition") or {}).get("variables"),
                limit=20,
            )
            if isinstance(operation.get("branchCondition"), Mapping)
            else [],
            "riskMarkers": _string_list(operation.get("riskMarkers"), limit=20),
        }
        for operation in _mapping_items(output.get("operations"))[:80]
    ]
    dto_blueprints = [
        {
            "name": str(dto.get("name") or "")[:80],
            "role": str(dto.get("role") or "")[:40],
            "operationIds": _string_list(dto.get("operationIds"), limit=20),
        }
        for dto in _mapping_items(output.get("dtoBlueprints"))[:80]
    ]
    return {
        "source": BRANCH_PLANNER_AGENT_TYPE,
        "operationCount": len(_mapping_items(output.get("operations"))),
        "statementEvidenceCount": len(_mapping_items(output.get("statementEvidence"))),
        "dtoBlueprintCount": len(_mapping_items(output.get("dtoBlueprints"))),
        "operations": operations,
        "dtoBlueprints": dto_blueprints,
        "reviewMarkers": _string_list(output.get("reviewMarkers"), limit=40),
    }


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


def _failed_sidecar_run(
    *,
    agent_type: str,
    target_ref: str,
    prompt: RenderedPrompt,
    profile: ModelProfile,
    exc: Exception,
    failure_stage: str,
) -> AgentRunPayload:
    diagnostics = _exception_provider_error(exc, failure_stage=failure_stage)
    structured_output = {
        "schemaVersion": "SpOperationModelSidecar.v0.1",
        "contractTarget": "SpOperationModelSidecar",
        "targetRef": target_ref,
        "sourcePolicy": "sanitized_facts_only",
        "productionReady": False,
        "status": "FAILED",
        "failureDiagnostics": diagnostics,
    }
    invocation = ModelInvocationRecord(
        provider="workflow",
        model="deterministic-operation-model-sidecar-gate",
        model_profile_id=profile.profile_id,
        model_registry_ref=profile.registry_ref,
        reasoning_effort="none",
        prompt_version=prompt.prompt_version,
        output_schema_version=prompt.output_schema_version,
        input_hash=prompt.input_hash,
        prompt_hash=prompt.prompt_hash,
        output_hash=stable_json_hash(structured_output),
        status=AgentRunStatus.FAILED,
        structured_output=structured_output,
        token_usage={"inputTokens": 0, "outputTokens": 0, "totalTokens": 0},
        latency_ms=0,
        error_code=_exception_code(exc),
        error_message="SP operation-model sidecar failed with sanitized diagnostics.",
        component_invocations=(
            {
                "component": failure_stage,
                "status": "FAILED",
                "errorCode": _exception_code(exc),
                "failureDiagnostics": diagnostics,
            },
        ),
    )
    return AgentRunPayload(
        agent_type=agent_type,
        status=AgentRunStatus.FAILED,
        target_ref=target_ref,
        structured_output=structured_output,
        model_invocation=invocation,
        summary=f"{agent_type} failed before valid operation-model output.",
    )


def _exception_code(exc: Exception) -> str:
    if isinstance(exc, ModelGatewayError):
        return str(exc.code)
    if isinstance(exc, OperationModelValidationError):
        return OPENAI_SP_OPERATION_MODEL_INVALID
    return exc.__class__.__name__


def _exception_provider_error(
    exc: Exception,
    *,
    failure_stage: str,
) -> dict[str, Any]:
    provider_error: dict[str, Any] = {
        "failureStage": failure_stage,
        "schemaName": "sp_operation_model",
        "errorCode": _exception_code(exc),
        "errorClass": exc.__class__.__name__,
    }
    if isinstance(exc, ModelGatewayError):
        for key, value in exc.provider_error.items():
            if key in {
                "type",
                "code",
                "stage",
                "schemaName",
                "endpointClass",
                "sdkTransport",
                "modelProfileId",
                "model",
                "errorClass",
                "outputHash",
            }:
                provider_error[key] = str(value)[:300]
        findings = _exception_findings(exc)
    elif isinstance(exc, OperationModelValidationError):
        findings = _exception_findings(exc)
    else:
        findings = []
    if findings:
        provider_error["findingCount"] = len(findings)
        provider_error["findings"] = findings[:MAX_REPAIR_FINDINGS]
    return provider_error


def _exception_findings(exc: Exception) -> list[str]:
    raw_findings: Sequence[Any]
    if isinstance(exc, OperationModelValidationError):
        raw_findings = exc.findings
    elif isinstance(exc, ModelGatewayError):
        provider_findings = exc.provider_error.get("findings")
        if isinstance(provider_findings, Sequence) and not isinstance(
            provider_findings,
            str | bytes,
        ):
            raw_findings = provider_findings
        elif provider_findings:
            raw_findings = [str(provider_findings)]
        else:
            raw_findings = []
    else:
        raw_findings = []
    safe: list[str] = []
    for finding in raw_findings[:MAX_REPAIR_FINDINGS]:
        text = _safe_finding_text(str(finding))
        if text:
            safe.append(text[:240])
    return safe


def _safe_finding_text(value: str) -> str:
    text = " ".join(value.split())
    text = re.sub(r"(?i)create\s+procedure\b.*", "[REDACTED_SQL]", text)
    text = re.sub(r"(?i)alter\s+procedure\b.*", "[REDACTED_SQL]", text)
    text = re.sub(r"(?i)raw\s+provider\s+response\b.*", "[REDACTED_PROVIDER_RESPONSE]", text)
    text = re.sub(r"(?i)secret[-_ ]?[A-Za-z0-9._~+/=-]+", "[REDACTED_SECRET]", text)
    text = re.sub(r"(?i)bearer\s+[a-z0-9._~+/=-]+", "Bearer [REDACTED]", text)
    text = re.sub(r"\bsk-[A-Za-z0-9_-]{8,}\b", "[REDACTED]", text)
    return text


def _mapping_items(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _string_list(value: Any, *, limit: int) -> list[str]:
    if isinstance(value, str | bytes) or not isinstance(value, Sequence):
        return []
    return [str(item)[:120] for item in value[:limit] if str(item).strip()]
