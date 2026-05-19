from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace as dataclass_replace
from typing import Any

from ai_agent_runtime.ai_draft_pack import (
    AI_JAVA_MYBATIS_DRAFT_PACK_ROLE_STAGES,
    AiDraftPackValidationError,
    validate_ai_java_mybatis_draft_pack_stage_output,
    validate_ai_java_mybatis_draft_pack_output,
)
from ai_agent_runtime.framework_adapter import (
    AiGenerationFrameworkAdapter,
    AiGenerationFrameworkAdapterRequest,
)
from ai_agent_runtime.gateway import ModelGateway, ModelGatewayError, model_profile_from_env
from ai_agent_runtime.models import AgentRunPayload, AgentRunStatus, stable_json_hash
from ai_agent_runtime.prompts import render_ai_java_mybatis_draft_pack_prompt

AGENT_TYPE = "LLM_AI_DRAFT_PACK_PLANNER"
REPAIRABLE_AI_DRAFT_PACK_GATEWAY_CODES = frozenset({"OPENAI_AI_DRAFT_PACK_INVALID"})
REPAIR_COMPONENT = "ai_draft_pack_repair_stage"
REFERENCE_GUARD_COMPONENT = "ai_draft_pack_reference_guard"
COMPOSER_COMPONENT = "ai_draft_pack_internal_composer"
AI_DRAFT_PACK_COMPOSER_STAGES = (
    "dto_inventory",
    "dto_content",
    "service_content",
    "mapper_interface_content",
    "mapper_xml_content",
    "integration_quality_gate",
)
FRAMEWORK_ADAPTER_STAGES = frozenset(
    {"file_inventory", "file_content", "repair", *AI_JAVA_MYBATIS_DRAFT_PACK_ROLE_STAGES}
)
ROLE_DRAFT_STAGES = AI_JAVA_MYBATIS_DRAFT_PACK_ROLE_STAGES


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
    framework_adapter: AiGenerationFrameworkAdapter | None = None,
    run_file_inventory_stage: bool = False,
) -> AgentRunPayload:
    allowed_refs = _allowed_evidence_refs(
        context=sanitized_draft_context,
        inventory=expected_inventory,
        additional_refs=allowed_evidence_refs,
    )
    profile = model_profile_from_env(profile_id)
    prior_component_invocations: tuple[dict[str, Any], ...] = ()
    if framework_adapter is not None and run_file_inventory_stage and repair_context is None:
        inventory_invocation = _invoke_ai_java_mybatis_draft_pack_stage(
            target_ref=target_ref,
            sanitized_draft_context=sanitized_draft_context,
            expected_inventory=expected_inventory,
            quality_gates=quality_gates,
            model_gateway=model_gateway,
            profile=profile,
            allowed_refs=allowed_refs,
            stage="file_inventory",
            repair_context=None,
            framework_adapter=framework_adapter,
        )
        _validate_ai_draft_pack_invocation(
            inventory_invocation,
            stage="file_inventory",
        )
        prior_component_invocations = tuple(inventory_invocation.component_invocations)
    if framework_adapter is not None and repair_context is None:
        return _build_ai_java_mybatis_draft_pack_staged_run(
            target_ref=target_ref,
            sanitized_draft_context=sanitized_draft_context,
            expected_inventory=expected_inventory,
            quality_gates=quality_gates,
            model_gateway=model_gateway,
            profile=profile,
            allowed_refs=allowed_refs,
            framework_adapter=framework_adapter,
            prior_component_invocations=prior_component_invocations,
        )
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
            framework_adapter=framework_adapter,
            prior_component_invocations=prior_component_invocations,
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
            framework_adapter=framework_adapter,
            prior_component_invocations=prior_component_invocations,
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
    framework_adapter: AiGenerationFrameworkAdapter | None,
    prior_component_invocations: Sequence[Mapping[str, Any]] = (),
) -> AgentRunPayload:
    invocation = _invoke_ai_java_mybatis_draft_pack_stage(
        target_ref=target_ref,
        sanitized_draft_context=sanitized_draft_context,
        expected_inventory=expected_inventory,
        quality_gates=quality_gates,
        model_gateway=model_gateway,
        profile=profile,
        allowed_refs=allowed_refs,
        stage=stage,
        repair_context=repair_context,
        framework_adapter=framework_adapter,
    )
    model = _validate_ai_draft_pack_invocation(
        invocation,
        stage=stage if framework_adapter is not None else None,
    )
    structured_output = model.to_storage_dict()
    guard_component = _reference_guard_component(
        structured_output=structured_output,
        expected_inventory=expected_inventory,
    )
    composer_component = _composer_component(stage=stage)
    structured_output["qualityGates"] = dict(quality_gates)
    component_invocations = invocation.component_invocations
    component_invocations = (*component_invocations, composer_component)
    if guard_component is not None:
        component_invocations = (*component_invocations, guard_component)
    if prior_component_invocations:
        component_invocations = (
            *(dict(item) for item in prior_component_invocations),
            *component_invocations,
        )
    if (
        invocation.structured_output != structured_output
        or composer_component is not None
        or guard_component is not None
        or prior_component_invocations
    ):
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


def _build_ai_java_mybatis_draft_pack_staged_run(
    *,
    target_ref: str,
    sanitized_draft_context: Mapping[str, Any],
    expected_inventory: Sequence[Mapping[str, Any]],
    quality_gates: Mapping[str, Any],
    model_gateway: ModelGateway,
    profile: Any,
    allowed_refs: Sequence[str],
    framework_adapter: AiGenerationFrameworkAdapter,
    prior_component_invocations: Sequence[Mapping[str, Any]] = (),
) -> AgentRunPayload:
    stage_outputs: dict[str, dict[str, Any]] = {}
    component_invocations: list[dict[str, Any]] = [
        dict(item) for item in prior_component_invocations
    ]
    last_invocation: Any | None = None
    repair_context: Mapping[str, Any] | None = None
    for stage in ROLE_DRAFT_STAGES:
        invocation = _invoke_ai_java_mybatis_draft_pack_stage(
            target_ref=target_ref,
            sanitized_draft_context=sanitized_draft_context,
            expected_inventory=expected_inventory,
            quality_gates=quality_gates,
            model_gateway=model_gateway,
            profile=profile,
            allowed_refs=allowed_refs,
            stage=stage,
            repair_context=None,
            framework_adapter=framework_adapter,
        )
        stage_model = _validate_ai_draft_pack_stage_invocation(invocation, stage=stage)
        stage_outputs[stage] = stage_model.to_storage_dict()
        component_invocations.extend(dict(item) for item in invocation.component_invocations)
        last_invocation = invocation
    try:
        return _build_run_from_stage_outputs(
            target_ref=target_ref,
            stage_outputs=stage_outputs,
            expected_inventory=expected_inventory,
            quality_gates=quality_gates,
            allowed_refs=allowed_refs,
            base_invocation=last_invocation,
            component_invocations=component_invocations,
            repair_context=None,
        )
    except AiDraftPackValidationError as exc:
        repair_context = _repair_context_from_exception(exc)
        target_stages = _repair_stages_from_findings(exc.findings)
        if not target_stages:
            raise
    for stage in target_stages:
        stage_repair_context = {
            **dict(repair_context or {}),
            "targetStage": stage,
            "targetStages": list(target_stages),
        }
        invocation = _invoke_ai_java_mybatis_draft_pack_stage(
            target_ref=target_ref,
            sanitized_draft_context=sanitized_draft_context,
            expected_inventory=expected_inventory,
            quality_gates=quality_gates,
            model_gateway=model_gateway,
            profile=profile,
            allowed_refs=allowed_refs,
            stage=stage,
            repair_context=stage_repair_context,
            framework_adapter=framework_adapter,
        )
        stage_model = _validate_ai_draft_pack_stage_invocation(invocation, stage=stage)
        stage_outputs[stage] = stage_model.to_storage_dict()
        component_invocations.extend(dict(item) for item in invocation.component_invocations)
        last_invocation = invocation
    return _build_run_from_stage_outputs(
        target_ref=target_ref,
        stage_outputs=stage_outputs,
        expected_inventory=expected_inventory,
        quality_gates=quality_gates,
        allowed_refs=allowed_refs,
        base_invocation=last_invocation,
        component_invocations=component_invocations,
        repair_context=repair_context,
    )


def _build_run_from_stage_outputs(
    *,
    target_ref: str,
    stage_outputs: Mapping[str, Mapping[str, Any]],
    expected_inventory: Sequence[Mapping[str, Any]],
    quality_gates: Mapping[str, Any],
    allowed_refs: Sequence[str],
    base_invocation: Any,
    component_invocations: Sequence[Mapping[str, Any]],
    repair_context: Mapping[str, Any] | None,
) -> AgentRunPayload:
    if base_invocation is None:
        raise AiDraftPackValidationError(["role stage composer had no model invocation."])
    structured_output = _compose_ai_java_mybatis_draft_pack_output(
        target_ref=target_ref,
        stage_outputs=stage_outputs,
        expected_inventory=expected_inventory,
        quality_gates=quality_gates,
        allowed_refs=allowed_refs,
    )
    model = validate_ai_java_mybatis_draft_pack_output(
        structured_output,
        allowed_evidence_refs=allowed_refs,
    )
    structured_output = model.to_storage_dict()
    guard_component = _reference_guard_component(
        structured_output=structured_output,
        expected_inventory=expected_inventory,
    )
    composer_component = _composer_component(stage="integration_quality_gate")
    components: tuple[dict[str, Any], ...] = (
        *(dict(item) for item in component_invocations),
        composer_component,
    )
    if guard_component is not None:
        components = (*components, guard_component)
    if repair_context is not None:
        components = (*components, _repair_component(repair_context))
    final_invocation = dataclass_replace(
        base_invocation,
        structured_output=structured_output,
        output_hash=stable_json_hash(structured_output),
        component_invocations=components,
    )
    return AgentRunPayload(
        agent_type=AGENT_TYPE,
        status=AgentRunStatus.SUCCEEDED,
        target_ref=model.target_ref,
        structured_output=structured_output,
        model_invocation=final_invocation,
        summary=(
            f"AI Java/MyBatis staged draft pack planned {len(model.files)} files "
            f"for {model.target_ref}."
        ),
    )


def _compose_ai_java_mybatis_draft_pack_output(
    *,
    target_ref: str,
    stage_outputs: Mapping[str, Mapping[str, Any]],
    expected_inventory: Sequence[Mapping[str, Any]],
    quality_gates: Mapping[str, Any],
    allowed_refs: Sequence[str],
) -> dict[str, Any]:
    stage_files: dict[tuple[str, str], Mapping[str, Any]] = {}
    stage_root_refs: list[str] = []
    stage_root_markers: list[str] = []
    assumptions: list[str] = []
    for stage in ROLE_DRAFT_STAGES:
        output = stage_outputs.get(stage) or {}
        stage_root_refs.extend(_strings(output.get("evidenceRefs")))
        stage_root_markers.extend(_strings(output.get("reviewMarkers")))
        assumptions.extend(_strings(output.get("assumptions")))
        for file in output.get("files", []):
            if not isinstance(file, Mapping):
                continue
            key = (str(file.get("artifactType") or ""), str(file.get("path") or ""))
            stage_files[key] = file

    composed_files: list[dict[str, Any]] = []
    missing: list[str] = []
    allowed_set = {str(ref) for ref in allowed_refs if str(ref).strip()}
    for expected in expected_inventory:
        artifact_type = str(expected.get("artifactType") or "")
        path = str(expected.get("path") or "")
        actual = stage_files.get((artifact_type, path))
        if actual is None:
            missing.append(f"{artifact_type} {path}")
            continue
        expected_refs = _strings(expected.get("evidenceRefs"))
        actual_refs = _strings(actual.get("evidenceRefs"))
        evidence_refs = _dedupe_refs([*expected_refs, *actual_refs], allowed_set)
        if not evidence_refs:
            evidence_refs = _dedupe_refs([*stage_root_refs, *allowed_refs], allowed_set)
        composed = {
            "artifactType": artifact_type,
            "path": path,
            "role": str(expected.get("role") or actual.get("role") or ""),
            "className": str(expected.get("className") or actual.get("className") or ""),
            "content": str(actual.get("content") or ""),
            "operationIds": _dedupe(
                [
                    *_strings(expected.get("operationIds")),
                    *_strings(actual.get("operationIds")),
                ]
            ),
            "evidenceRefs": evidence_refs,
            "reviewMarkers": _dedupe(
                [
                    *_strings(expected.get("reviewMarkers")),
                    *_strings(actual.get("reviewMarkers")),
                ]
            ),
        }
        for optional_key in ("dtoRole", "requiredFields", "references"):
            values = expected.get(optional_key)
            if values is None:
                values = actual.get(optional_key)
            if values is not None:
                composed[optional_key] = values
        if actual.get("qualityScore") is not None:
            composed["qualityScore"] = actual.get("qualityScore")
        composed_files.append(composed)
    if missing:
        raise AiDraftPackValidationError(
            [f"integration_quality_gate: missing expected stage files: {missing}."]
        )

    root_refs = _dedupe_refs(
        [
            *_strings(stage_root_refs),
            *(ref for file in composed_files for ref in _strings(file.get("evidenceRefs"))),
            *allowed_refs,
        ],
        allowed_set,
    )
    root_markers = _dedupe(
        [
            *_strings(stage_root_markers),
            *_strings(quality_gates.get("requiredReviewMarkers")),
            *(marker for file in composed_files for marker in _strings(file.get("reviewMarkers"))),
        ]
    )
    return {
        "schemaVersion": "AiJavaMyBatisDraftPack.v0.1",
        "contractTarget": "AiJavaMyBatisDraftPack",
        "targetRef": target_ref,
        "sourcePolicy": "sanitized_facts_only",
        "productionReady": False,
        "files": composed_files,
        "evidenceRefs": root_refs or list(allowed_refs),
        "reviewMarkers": root_markers,
        "qualityGates": dict(quality_gates),
        "assumptions": _dedupe(
            [*assumptions, "P50 role-stage outputs were merged by deterministic composer."]
        ),
    }


def _invoke_ai_java_mybatis_draft_pack_stage(
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
    framework_adapter: AiGenerationFrameworkAdapter | None,
):
    prompt = render_ai_java_mybatis_draft_pack_prompt(
        target_ref=target_ref,
        sanitized_draft_context=sanitized_draft_context,
        expected_inventory=expected_inventory,
        quality_gates=quality_gates,
        allowed_evidence_refs=allowed_refs,
        stage=stage,
        repair_context=dict(repair_context or {}) if repair_context else None,
    )
    if framework_adapter is None:
        invocation = model_gateway.draft_ai_java_mybatis_pack(prompt=prompt, profile=profile)
    else:
        adapter_request = AiGenerationFrameworkAdapterRequest(
            target_ref=target_ref,
            sanitized_draft_context=sanitized_draft_context,
            expected_inventory=expected_inventory,
            quality_gates=quality_gates,
            allowed_evidence_refs=allowed_refs,
            prompt=prompt,
            profile=profile,
            stage=stage,
            repair_context=repair_context,
        )
        invocation = (
            framework_adapter.repair_draft_pack(request=adapter_request)
            if stage == "repair"
            else (
                framework_adapter.plan_file_inventory(request=adapter_request)
                if stage == "file_inventory"
                else (
                    framework_adapter.draft_role_stage(request=adapter_request)
                    if stage in ROLE_DRAFT_STAGES
                    else framework_adapter.draft_file_content(request=adapter_request)
                )
            )
        )
    return invocation


def _validate_ai_draft_pack_invocation(invocation: Any, *, stage: str | None):
    try:
        return validate_ai_java_mybatis_draft_pack_output(invocation.structured_output)
    except AiDraftPackValidationError as exc:
        if stage is None:
            raise
        raise AiDraftPackValidationError(
            _stage_validation_findings(stage=stage, findings=exc.findings)
        ) from exc


def _validate_ai_draft_pack_stage_invocation(invocation: Any, *, stage: str):
    try:
        return validate_ai_java_mybatis_draft_pack_stage_output(
            invocation.structured_output,
            stage=stage,
        )
    except AiDraftPackValidationError as exc:
        raise AiDraftPackValidationError(
            _stage_validation_findings(stage=stage, findings=exc.findings)
        ) from exc


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


def _composer_component(*, stage: str) -> dict[str, Any]:
    stages = (
        (*AI_DRAFT_PACK_COMPOSER_STAGES, "repair")
        if stage == "repair"
        else AI_DRAFT_PACK_COMPOSER_STAGES
    )
    return {
        "component": COMPOSER_COMPONENT,
        "status": "SUCCEEDED",
        "stage": stage,
        "composerStages": list(stages),
        "stageCount": len(stages),
        "defaultProfile": "openai_ai_draft_pack",
        "action": "split_java_mybatis_draft_pack_by_artifact_role",
    }


def _repair_context_from_exception(exc: Exception) -> dict[str, Any]:
    if isinstance(exc, AiDraftPackValidationError):
        return {
            "failureStage": _schema_failure_stage_from_findings(exc.findings),
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
    for key in ("type", "code", "param", "message", "stage", "findingCount", "findings"):
        value = provider_error.get(key)
        if value is not None:
            safe[key] = str(value)[:300]
    return safe


def _stage_validation_findings(
    *,
    stage: str,
    findings: Sequence[str],
) -> list[str]:
    prefix = stage if stage in FRAMEWORK_ADAPTER_STAGES else "ai_draft_pack"
    return [
        finding
        if str(finding).startswith(f"{prefix}:")
        else f"{prefix}: {finding}"
        for finding in findings
    ]


def _schema_failure_stage_from_findings(findings: Sequence[str]) -> str:
    for stage in FRAMEWORK_ADAPTER_STAGES:
        if any(str(finding).startswith(f"{stage}:") for finding in findings):
            return f"{stage}_schema_validation"
    return "schema_validation"


def _repair_stages_from_findings(findings: Sequence[str]) -> tuple[str, ...]:
    stages: list[str] = []
    text = "\n".join(str(finding) for finding in findings)
    for stage in ROLE_DRAFT_STAGES:
        if f"{stage}:" in text:
            stages.append(stage)
    if "SERVICE_DRAFT" in text or "service" in text.lower():
        stages.append("service_content")
    if "MAPPER_XML" in text or "mapper_xml" in text.lower() or "xml" in text.lower():
        stages.append("mapper_xml_content")
    if "MAPPER_INTERFACE" in text or "mapper interface" in text.lower():
        stages.append("mapper_interface_content")
    if "DTO_DRAFT" in text or "dto" in text.lower():
        stages.extend(["dto_inventory", "dto_content"])
    return tuple(stage for stage in ROLE_DRAFT_STAGES if stage in set(stages))


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


def _strings(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if not isinstance(value, Sequence):
        return []
    return _dedupe(str(item) for item in value if item is not None and str(item).strip())


def _dedupe(values: Any) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if str(value).strip()))


def _dedupe_refs(values: Any, allowed_refs: set[str]) -> list[str]:
    refs = _dedupe(values)
    if not allowed_refs:
        return refs
    return [ref for ref in refs if ref in allowed_refs]
