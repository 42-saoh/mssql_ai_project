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
DTO_RECONCILED_MARKER = "SP_OPERATION_MODEL_DTO_BLUEPRINT_RECONCILED"
DTO_RECONCILIATION_REVIEW_MARKER = "DTO_BLUEPRINT_RECONCILIATION_REVIEW_REQUIRED"
OPENAI_SP_OPERATION_MODEL_INVALID = "OPENAI_SP_OPERATION_MODEL_INVALID"
MAX_REPAIR_FINDINGS = 12
DTO_BLUEPRINT_ROLES = {
    "QUERY",
    "RESULT",
    "COMMAND",
    "BATCH_ITEM",
    "CALL_REQUEST",
    "CALL_RESULT",
    "REVIEW_REQUIRED",
}


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
                statement_evidence=statements,
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
            if _repairable_operation_model_error(exc):
                repair_prompt = render_sp_operation_model_prompt(
                    target_ref=target_ref,
                    statement_evidence=statements,
                    allowed_evidence_refs=allowed_refs,
                    task_mode="repair",
                    stage="operation_model_repair",
                    branch_plan_context={},
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
                        statement_evidence=statements,
                        branch_plan_context={},
                        reconcile_dto_refs=True,
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
                        sidecar_runs=(*sidecar_runs, failed_run, failed_repair),
                    ) from repair_exc

                sidecar_runs.extend([failed_run, repair_run])
                final_run = _final_run_from_repair(repair_run)
                return OperationModelRunResult(
                    final_run=final_run,
                    sidecar_runs=tuple(sidecar_runs),
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
            statement_evidence=statements,
            branch_plan_context=branch_plan_context,
            reconcile_dto_refs=True,
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
                statement_evidence=statements,
                branch_plan_context=branch_plan_context,
                reconcile_dto_refs=True,
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
    statement_evidence: Sequence[Mapping[str, Any]] = (),
    branch_plan_context: Mapping[str, Any] | None = None,
    reconcile_dto_refs: bool = False,
    summary_prefix: str,
) -> AgentRunPayload:
    invocation = model_gateway.plan_sp_operation_model(prompt=prompt, profile=profile)
    model, repair_summary = _validated_or_repaired(
        invocation.structured_output,
        allowed_refs,
        statement_evidence=statement_evidence,
        branch_plan_context=branch_plan_context,
        reconcile_dto_refs=reconcile_dto_refs,
    )
    structured_output = model.to_storage_dict()
    component_invocations = list(invocation.component_invocations)
    if repair_summary.get("dtoReconciled"):
        component_invocations.append(
            {
                "component": "sp_operation_model_dto_blueprint_reconciler",
                "status": "SUCCEEDED",
                "action": "restored_missing_dto_blueprints_from_refs",
                "reviewMarker": DTO_RECONCILED_MARKER,
                "restoredDtoCount": int(repair_summary.get("restoredDtoCount") or 0),
                "generatedDtoCount": int(repair_summary.get("generatedDtoCount") or 0),
                "dtoBlueprintNames": list(repair_summary.get("dtoBlueprintNames") or [])[:30],
            }
        )
    if repair_summary.get("evidenceRepaired"):
        component_invocations.append(
            {
                "component": "sp_operation_model_evidence_guard",
                "status": "SUCCEEDED",
                "action": "repaired_invalid_or_empty_evidence_refs",
                "reviewMarker": EVIDENCE_REPAIRED_MARKER,
            }
        )
    if component_invocations != list(invocation.component_invocations):
        invocation = dataclass_replace(
            invocation,
            structured_output=structured_output,
            output_hash=stable_json_hash(structured_output),
            component_invocations=tuple(component_invocations),
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
    *,
    statement_evidence: Sequence[Mapping[str, Any]] = (),
    branch_plan_context: Mapping[str, Any] | None = None,
    reconcile_dto_refs: bool = False,
) -> tuple[SpOperationModelPlannerOutput, dict[str, Any]]:
    repaired_payload = deepcopy(dict(payload))
    repair_summary: dict[str, Any] = {
        "dtoReconciled": False,
        "evidenceRepaired": False,
        "restoredDtoCount": 0,
        "generatedDtoCount": 0,
        "dtoBlueprintNames": [],
    }
    if reconcile_dto_refs:
        repair_summary.update(
            _reconcile_dto_blueprint_refs(
                repaired_payload,
                allowed_refs=allowed_refs,
                statement_evidence=statement_evidence,
                branch_plan_context=branch_plan_context or {},
            )
        )
    try:
        return (
            validate_sp_operation_model_output(
                repaired_payload,
                allowed_evidence_refs=allowed_refs,
            ),
            repair_summary,
        )
    except OperationModelValidationError as exc:
        if not allowed_refs:
            raise
        if not _evidence_findings_only(exc.findings):
            raise
    repaired_payload = _repair_evidence_refs(
        repaired_payload,
        allowed_refs=allowed_refs,
        fallback_ref=allowed_refs[0],
    )
    repair_summary["evidenceRepaired"] = True
    model = validate_sp_operation_model_output(
        repaired_payload,
        allowed_evidence_refs=allowed_refs,
    )
    return model, repair_summary


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
        "missingDtoBlueprintRefs": _missing_dto_blueprint_refs_from_findings(findings),
        "rawFailedOutputIncluded": False,
        "instructions": (
            "Repair from validator findings, statementEvidence, branchPlanContext, "
            "and missingDtoBlueprintRefs only. Preserve branchPlanContext DTO inventory."
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
            "evidenceRefs": _string_list(operation.get("evidenceRefs"), limit=40),
            "branchVariables": _string_list(
                (operation.get("branchCondition") or {}).get("variables"),
                limit=20,
            )
            if isinstance(operation.get("branchCondition"), Mapping)
            else [],
            "branchEvidenceRefs": _string_list(
                (operation.get("branchCondition") or {}).get("evidenceRefs"),
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
            "fields": _dto_field_context_items(dto.get("fields")),
            "evidenceRefs": _string_list(dto.get("evidenceRefs"), limit=40),
            "reviewMarkers": _string_list(dto.get("reviewMarkers"), limit=20),
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


def _reconcile_dto_blueprint_refs(
    payload: dict[str, Any],
    *,
    allowed_refs: Sequence[str],
    statement_evidence: Sequence[Mapping[str, Any]],
    branch_plan_context: Mapping[str, Any],
) -> dict[str, Any]:
    operations = [item for item in _mapping_items(payload.get("operations"))]
    if not operations:
        return {}
    statement_items = [item for item in _mapping_items(payload.get("statementEvidence"))]
    if not statement_items:
        statement_items = [item for item in statement_evidence if isinstance(item, Mapping)]
    statements_by_id = {
        str(statement.get("statementId") or ""): statement
        for statement in statement_items
        if str(statement.get("statementId") or "").strip()
    }
    operation_ids = {
        str(operation.get("operationId") or "")
        for operation in operations
        if str(operation.get("operationId") or "").strip()
    }
    refs_to_operations: dict[str, list[str]] = {}
    refs_to_statements: dict[str, list[str]] = {}
    for operation in operations:
        operation_id = str(operation.get("operationId") or "").strip()
        if not operation_id:
            continue
        statement_refs = _string_list(operation.get("statementRefs"), limit=80)
        for dto_ref in _string_list(operation.get("dtoBlueprintRefs"), limit=80):
            refs_to_operations.setdefault(dto_ref, [])
            if operation_id not in refs_to_operations[dto_ref]:
                refs_to_operations[dto_ref].append(operation_id)
            refs_to_statements.setdefault(dto_ref, [])
            for statement_id in statement_refs:
                if statement_id not in refs_to_statements[dto_ref]:
                    refs_to_statements[dto_ref].append(statement_id)

    dto_blueprints = [
        dict(item) for item in _mapping_items(payload.get("dtoBlueprints"))
    ]
    current_by_name: dict[str, dict[str, Any]] = {}
    for dto in dto_blueprints:
        name = str(dto.get("name") or "").strip()
        if not name:
            continue
        current_by_name[name] = dto
        dto["operationIds"] = _reconciled_operation_ids(
            dto.get("operationIds"),
            referenced_by=refs_to_operations.get(name, []),
            valid_operation_ids=operation_ids,
        )
        dto["evidenceRefs"] = _safe_evidence_refs(
            dto.get("evidenceRefs"),
            allowed_refs=allowed_refs,
            fallback_refs=_dto_fallback_refs(
                dto_name=name,
                operations=operations,
                statements_by_id=statements_by_id,
                refs_to_operations=refs_to_operations,
                refs_to_statements=refs_to_statements,
                allowed_refs=allowed_refs,
            ),
        )
        if not dto.get("fields"):
            dto["fields"] = _field_blueprints_for_dto(
                dto_name=name,
                role=str(dto.get("role") or ""),
                operation_ids=refs_to_operations.get(name, []),
                operations=operations,
                statements_by_id=statements_by_id,
                allowed_refs=allowed_refs,
            )

    branch_dtos = {
        str(dto.get("name") or "").strip(): dict(dto)
        for dto in _mapping_items(branch_plan_context.get("dtoBlueprints"))
        if str(dto.get("name") or "").strip()
    }
    restored_names: list[str] = []
    generated_names: list[str] = []
    for dto_name, operation_refs in refs_to_operations.items():
        if dto_name in current_by_name:
            continue
        branch_dto = branch_dtos.get(dto_name)
        if branch_dto:
            dto = _dto_from_branch_plan_context(
                dto_name=dto_name,
                branch_dto=branch_dto,
                operation_refs=operation_refs,
                operations=operations,
                statements_by_id=statements_by_id,
                allowed_refs=allowed_refs,
            )
            restored_names.append(dto_name)
        else:
            dto = _minimal_dto_blueprint(
                dto_name=dto_name,
                operation_refs=operation_refs,
                operations=operations,
                statements_by_id=statements_by_id,
                allowed_refs=allowed_refs,
            )
            generated_names.append(dto_name)
        dto_blueprints.append(dto)
        current_by_name[dto_name] = dto

    if restored_names or generated_names:
        markers = _string_list(payload.get("reviewMarkers"), limit=80)
        if DTO_RECONCILED_MARKER not in markers:
            markers.append(DTO_RECONCILED_MARKER)
        if generated_names and DTO_RECONCILIATION_REVIEW_MARKER not in markers:
            markers.append(DTO_RECONCILIATION_REVIEW_MARKER)
        payload["reviewMarkers"] = markers
    payload["dtoBlueprints"] = dto_blueprints
    return {
        "dtoReconciled": bool(restored_names or generated_names),
        "restoredDtoCount": len(restored_names),
        "generatedDtoCount": len(generated_names),
        "dtoBlueprintNames": [*restored_names, *generated_names],
    }


def _reconciled_operation_ids(
    value: Any,
    *,
    referenced_by: Sequence[str],
    valid_operation_ids: set[str],
) -> list[str]:
    operation_ids = [
        item
        for item in _string_list(value, limit=80)
        if not valid_operation_ids or item in valid_operation_ids
    ]
    for operation_id in referenced_by:
        if operation_id and operation_id not in operation_ids:
            operation_ids.append(operation_id)
    return operation_ids


def _dto_from_branch_plan_context(
    *,
    dto_name: str,
    branch_dto: Mapping[str, Any],
    operation_refs: Sequence[str],
    operations: Sequence[Mapping[str, Any]],
    statements_by_id: Mapping[str, Mapping[str, Any]],
    allowed_refs: Sequence[str],
) -> dict[str, Any]:
    role = _normalized_dto_role(
        branch_dto.get("role"),
        dto_name=dto_name,
        operation_refs=operation_refs,
        operations=operations,
        statements_by_id=statements_by_id,
    )
    evidence_refs = _safe_evidence_refs(
        branch_dto.get("evidenceRefs"),
        allowed_refs=allowed_refs,
        fallback_refs=_dto_fallback_refs(
            dto_name=dto_name,
            operations=operations,
            statements_by_id=statements_by_id,
            refs_to_operations={dto_name: list(operation_refs)},
            refs_to_statements={},
            allowed_refs=allowed_refs,
        ),
    )
    fields = _dto_field_context_items(branch_dto.get("fields"))
    fields = [
        _normalized_field_blueprint(field, allowed_refs=allowed_refs, fallback_refs=evidence_refs)
        for field in fields
    ]
    fields = [field for field in fields if field]
    if not fields:
        fields = _field_blueprints_for_dto(
            dto_name=dto_name,
            role=role,
            operation_ids=operation_refs,
            operations=operations,
            statements_by_id=statements_by_id,
            allowed_refs=allowed_refs,
        )
    return {
        "name": dto_name,
        "role": role,
        "operationIds": list(dict.fromkeys(operation_refs)),
        "fields": fields,
        "evidenceRefs": evidence_refs,
        "reviewMarkers": _string_list(branch_dto.get("reviewMarkers"), limit=30),
    }


def _minimal_dto_blueprint(
    *,
    dto_name: str,
    operation_refs: Sequence[str],
    operations: Sequence[Mapping[str, Any]],
    statements_by_id: Mapping[str, Mapping[str, Any]],
    allowed_refs: Sequence[str],
) -> dict[str, Any]:
    role = _normalized_dto_role(
        None,
        dto_name=dto_name,
        operation_refs=operation_refs,
        operations=operations,
        statements_by_id=statements_by_id,
    )
    evidence_refs = _dto_fallback_refs(
        dto_name=dto_name,
        operations=operations,
        statements_by_id=statements_by_id,
        refs_to_operations={dto_name: list(operation_refs)},
        refs_to_statements={},
        allowed_refs=allowed_refs,
    )
    return {
        "name": dto_name,
        "role": role,
        "operationIds": list(dict.fromkeys(operation_refs)),
        "fields": _field_blueprints_for_dto(
            dto_name=dto_name,
            role=role,
            operation_ids=operation_refs,
            operations=operations,
            statements_by_id=statements_by_id,
            allowed_refs=allowed_refs,
        ),
        "evidenceRefs": evidence_refs,
        "reviewMarkers": [DTO_RECONCILIATION_REVIEW_MARKER],
    }


def _field_blueprints_for_dto(
    *,
    dto_name: str,
    role: str,
    operation_ids: Sequence[str],
    operations: Sequence[Mapping[str, Any]],
    statements_by_id: Mapping[str, Mapping[str, Any]],
    allowed_refs: Sequence[str],
) -> list[dict[str, Any]]:
    role = _normalized_dto_role(
        role,
        dto_name=dto_name,
        operation_refs=operation_ids,
        operations=operations,
        statements_by_id=statements_by_id,
    )
    tokens: list[tuple[str, str, list[str]]] = []
    operation_id_set = set(operation_ids)
    for operation in operations:
        operation_id = str(operation.get("operationId") or "")
        if operation_id not in operation_id_set:
            continue
        branch = operation.get("branchCondition")
        fallback_values = _string_list(operation.get("evidenceRefs"), limit=40)
        if isinstance(branch, Mapping):
            fallback_values.extend(_string_list(branch.get("evidenceRefs"), limit=40))
        operation_refs = _safe_evidence_refs(
            fallback_values,
            allowed_refs=allowed_refs,
            fallback_refs=allowed_refs[:1],
        )
        if isinstance(branch, Mapping):
            for variable in _string_list(branch.get("variables"), limit=30):
                tokens.append((variable, f"branch.{_field_name_from_token(variable)}", operation_refs))
        for statement_id in _string_list(operation.get("statementRefs"), limit=80):
            statement = statements_by_id.get(statement_id)
            if not isinstance(statement, Mapping):
                continue
            statement_refs = _safe_evidence_refs(
                statement.get("evidenceRefs"),
                allowed_refs=allowed_refs,
                fallback_refs=operation_refs or allowed_refs[:1],
            )
            candidate_keys = (
                ("outputs",)
                if role in {"RESULT", "CALL_RESULT"}
                else ("inputs", "writes")
            )
            for key in candidate_keys:
                for token in _string_list(statement.get(key), limit=40):
                    tokens.append(
                        (
                            token,
                            f"statement.{statement_id}.{key}.{_field_name_from_token(token)}",
                            statement_refs,
                        )
                    )
    fields: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for token, source, refs in tokens:
        name = _field_name_from_token(token)
        if not name or name in seen_names:
            continue
        fields.append(
            {
                "name": name,
                "dbType": "REVIEW_REQUIRED",
                "source": _safe_field_source(source),
                "required": False,
                "evidenceRefs": refs or _safe_evidence_refs(
                    [],
                    allowed_refs=allowed_refs,
                    fallback_refs=allowed_refs[:1],
                ),
            }
        )
        seen_names.add(name)
        if len(fields) >= 30:
            break
    if fields:
        return fields
    return [
        {
            "name": "reviewRequiredField",
            "dbType": "REVIEW_REQUIRED",
            "source": "operation_model_reconciliation",
            "required": False,
            "evidenceRefs": _safe_evidence_refs(
                [],
                allowed_refs=allowed_refs,
                fallback_refs=allowed_refs[:1],
            ),
        }
    ]


def _dto_fallback_refs(
    *,
    dto_name: str,
    operations: Sequence[Mapping[str, Any]],
    statements_by_id: Mapping[str, Mapping[str, Any]],
    refs_to_operations: Mapping[str, Sequence[str]],
    refs_to_statements: Mapping[str, Sequence[str]],
    allowed_refs: Sequence[str],
) -> list[str]:
    values: list[str] = []
    operation_ids = set(refs_to_operations.get(dto_name, []))
    for operation in operations:
        if str(operation.get("operationId") or "") not in operation_ids:
            continue
        values.extend(_string_list(operation.get("evidenceRefs"), limit=40))
        branch = operation.get("branchCondition")
        if isinstance(branch, Mapping):
            values.extend(_string_list(branch.get("evidenceRefs"), limit=40))
        for statement_id in _string_list(operation.get("statementRefs"), limit=80):
            statement = statements_by_id.get(statement_id)
            if isinstance(statement, Mapping):
                values.extend(_string_list(statement.get("evidenceRefs"), limit=40))
    for statement_id in refs_to_statements.get(dto_name, []):
        statement = statements_by_id.get(statement_id)
        if isinstance(statement, Mapping):
            values.extend(_string_list(statement.get("evidenceRefs"), limit=40))
    return _safe_evidence_refs(values, allowed_refs=allowed_refs, fallback_refs=allowed_refs[:1])


def _normalized_dto_role(
    value: Any,
    *,
    dto_name: str,
    operation_refs: Sequence[str],
    operations: Sequence[Mapping[str, Any]],
    statements_by_id: Mapping[str, Mapping[str, Any]],
) -> str:
    role = str(value or "").strip().upper()
    if role in DTO_BLUEPRINT_ROLES:
        return role
    normalized_name = dto_name.lower()
    if "criteria" in normalized_name or normalized_name.endswith("query"):
        return "QUERY"
    if "batchitem" in normalized_name or "batch_item" in normalized_name:
        return "BATCH_ITEM"
    if "callrequest" in normalized_name or "call_request" in normalized_name:
        return "CALL_REQUEST"
    if "callresult" in normalized_name or "call_result" in normalized_name:
        return "CALL_RESULT"
    if "row" in normalized_name:
        return "RESULT"
    if "command" in normalized_name:
        return "COMMAND"
    if normalized_name.endswith("result"):
        statement_operations = _statement_operations_for_operations(
            operation_refs=operation_refs,
            operations=operations,
            statements_by_id=statements_by_id,
        )
        return "CALL_RESULT" if statement_operations & {"EXECUTE", "CALL"} else "RESULT"
    statement_operations = _statement_operations_for_operations(
        operation_refs=operation_refs,
        operations=operations,
        statements_by_id=statements_by_id,
    )
    if statement_operations <= {"SELECT"} and statement_operations:
        return "QUERY"
    if statement_operations & {"EXECUTE", "CALL"}:
        return "CALL_REQUEST"
    return "COMMAND"


def _statement_operations_for_operations(
    *,
    operation_refs: Sequence[str],
    operations: Sequence[Mapping[str, Any]],
    statements_by_id: Mapping[str, Mapping[str, Any]],
) -> set[str]:
    operation_id_set = set(operation_refs)
    values: set[str] = set()
    for operation in operations:
        if str(operation.get("operationId") or "") not in operation_id_set:
            continue
        for statement_id in _string_list(operation.get("statementRefs"), limit=80):
            statement = statements_by_id.get(statement_id)
            if isinstance(statement, Mapping):
                values.add(str(statement.get("operation") or "").upper())
    return {value for value in values if value}


def _dto_field_context_items(value: Any) -> list[dict[str, Any]]:
    fields = []
    for field in _mapping_items(value):
        normalized = {
            "name": str(field.get("name") or "")[:80],
            "dbType": str(field.get("dbType") or field.get("db_type") or "REVIEW_REQUIRED")[
                :80
            ],
            "source": _safe_field_source(str(field.get("source") or "branch_plan_context")),
            "required": bool(field.get("required")),
            "evidenceRefs": _string_list(field.get("evidenceRefs"), limit=20),
        }
        if normalized["name"]:
            fields.append(normalized)
        if len(fields) >= 30:
            break
    return fields


def _normalized_field_blueprint(
    field: Mapping[str, Any],
    *,
    allowed_refs: Sequence[str],
    fallback_refs: Sequence[str],
) -> dict[str, Any] | None:
    name = _field_name_from_token(str(field.get("name") or ""))
    if not name:
        return None
    return {
        "name": name,
        "dbType": str(field.get("dbType") or "REVIEW_REQUIRED")[:80],
        "source": _safe_field_source(str(field.get("source") or "branch_plan_context")),
        "required": bool(field.get("required")),
        "evidenceRefs": _safe_evidence_refs(
            field.get("evidenceRefs"),
            allowed_refs=allowed_refs,
            fallback_refs=fallback_refs,
        ),
    }


def _field_name_from_token(value: str) -> str:
    text = str(value or "").strip().strip("@[]")
    if "." in text:
        text = text.split(".")[-1]
    parts = [part for part in re.split(r"[^0-9A-Za-z]+", text) if part]
    if not parts:
        return ""
    first, *rest = parts
    candidate = first[:1].lower() + first[1:] + "".join(
        part[:1].upper() + part[1:] for part in rest
    )
    if not re.match(r"[A-Za-z_]", candidate):
        candidate = f"field{candidate[:1].upper()}{candidate[1:]}"
    return candidate[:80]


def _safe_field_source(value: str) -> str:
    text = re.sub(r"[^0-9A-Za-z_@.:/-]+", "_", str(value or "")).strip("_")
    return text[:120] or "operation_model_reconciliation"


def _safe_evidence_refs(
    value: Any,
    *,
    allowed_refs: Sequence[str],
    fallback_refs: Sequence[str],
) -> list[str]:
    allowed = {str(ref) for ref in allowed_refs if str(ref).strip()}
    values = _string_list(value, limit=80)
    refs = [
        ref
        for ref in values
        if ref and (not allowed or ref in allowed)
    ]
    for ref in fallback_refs:
        text = str(ref or "").strip()
        if text and (not allowed or text in allowed) and text not in refs:
            refs.append(text)
    if not refs and allowed_refs:
        refs.append(str(allowed_refs[0]))
    return refs


def _missing_dto_blueprint_refs_from_findings(
    findings: Sequence[str],
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for finding in findings:
        match = re.search(
            r"operations\[([^\]]+)\]\.dtoBlueprintRefs contains unknown DTOs: \[(.*?)\]",
            finding,
        )
        if not match:
            continue
        dto_refs = []
        for single, double in re.findall(r"'([^']+)'|\"([^\"]+)\"", match.group(2)):
            text = single or double
            if text and text not in dto_refs:
                dto_refs.append(text)
        if dto_refs:
            items.append(
                {
                    "operationId": match.group(1),
                    "dtoBlueprintRefs": dto_refs,
                }
            )
    return items


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
