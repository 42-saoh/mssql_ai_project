from __future__ import annotations

import json
import re
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
DTO_FLOOR_COMPONENT = "ai_draft_pack_dto_content_floor"
DTO_FLOOR_REVIEW_MARKER = "DTO_CONTENT_FLOOR_REVIEW_REQUIRED"
PACKAGE_CONTEXT_REVIEW_MARKER = "PACKAGE_CONTEXT_REVIEW_REQUIRED"
DEFAULT_JAVA_PACKAGE_CONTEXT = {
    "modelPackage": "com.pec.draft.workflow.draft.model",
    "dtoPackage": "com.pec.draft.workflow.draft.model",
    "servicePackage": "com.pec.draft.workflow.draft.service",
    "mapperPackage": "com.pec.draft.workflow.draft.mapper",
    "mapperNamespaceRule": "full_mapper_interface_name",
}
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
            sanitized_draft_context=sanitized_draft_context,
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
        sanitized_draft_context=sanitized_draft_context,
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
    sanitized_draft_context: Mapping[str, Any],
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
    structured_output, dto_floor_summary = _compose_ai_java_mybatis_draft_pack_output(
        target_ref=target_ref,
        sanitized_draft_context=sanitized_draft_context,
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
    if dto_floor_summary.get("applied"):
        components = (*components, _dto_floor_component(dto_floor_summary))
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
    sanitized_draft_context: Mapping[str, Any],
    stage_outputs: Mapping[str, Mapping[str, Any]],
    expected_inventory: Sequence[Mapping[str, Any]],
    quality_gates: Mapping[str, Any],
    allowed_refs: Sequence[str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    stage_files: dict[tuple[str, str], Mapping[str, Any]] = {}
    stage_files_by_type: dict[str, list[Mapping[str, Any]]] = {}
    dto_inventory_files: dict[tuple[str, str], Mapping[str, Any]] = {}
    dto_content_files: dict[tuple[str, str], Mapping[str, Any]] = {}
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
            stage_files_by_type.setdefault(str(file.get("artifactType") or ""), []).append(file)
            if stage == "dto_inventory":
                dto_inventory_files[key] = file
            elif stage == "dto_content":
                dto_content_files[key] = file

    composed_files: list[dict[str, Any]] = []
    missing: list[dict[str, str]] = []
    floor_files: list[dict[str, Any]] = []
    dto_guard_files: list[dict[str, str]] = []
    allowed_set = {str(ref) for ref in allowed_refs if str(ref).strip()}
    package_context, package_context_review_required = _java_package_context(
        sanitized_draft_context
    )
    for expected in expected_inventory:
        artifact_type = str(expected.get("artifactType") or "")
        path = str(expected.get("path") or "")
        key = (artifact_type, path)
        actual = stage_files.get(key)
        if actual is None:
            actual = _aggregate_stage_file_for_expected(
                expected,
                stage_files_by_type=stage_files_by_type,
            )
        if actual is None:
            if artifact_type == "DTO_DRAFT":
                actual = _dto_floor_file(
                    expected,
                    allowed_refs=allowed_refs,
                    allowed_set=allowed_set,
                    source_file=dto_content_files.get(key) or dto_inventory_files.get(key),
                    package_context=package_context,
                    package_context_review_required=package_context_review_required,
                )
                floor_files.append(actual)
            else:
                missing.append(_missing_expected_stage_file(expected))
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
        if artifact_type == "DTO_DRAFT":
            guarded_content, guarded = _dto_content_policy_guard(
                composed,
                package_context=package_context,
                package_context_review_required=package_context_review_required,
            )
            if guarded:
                composed["content"] = guarded_content
                composed["reviewMarkers"] = _dedupe(
                    [
                        *_strings(composed.get("reviewMarkers")),
                        DTO_FLOOR_REVIEW_MARKER,
                        *(
                            [PACKAGE_CONTEXT_REVIEW_MARKER]
                            if package_context_review_required
                            else []
                        ),
                    ]
                )
                dto_guard_files.append(_missing_expected_stage_file(expected))
        composed_files.append(composed)
    if missing:
        raise AiDraftPackValidationError(
            [
                "integration_quality_gate: missing expected stage files: "
                f"{json.dumps(missing, sort_keys=True)}."
            ]
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
    dto_floor_summary = {
        "applied": bool(floor_files or dto_guard_files),
        "fileCount": len(floor_files),
        "files": [
            {
                "artifactType": str(file.get("artifactType") or ""),
                "path": str(file.get("path") or ""),
                "className": str(file.get("className") or ""),
                "owningStage": "dto_content",
            }
            for file in floor_files[:40]
        ],
        "augmentedFileCount": len(dto_guard_files),
        "augmentedFiles": dto_guard_files[:40],
    }
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
    }, dto_floor_summary


def _aggregate_stage_file_for_expected(
    expected: Mapping[str, Any],
    *,
    stage_files_by_type: Mapping[str, Sequence[Mapping[str, Any]]],
) -> Mapping[str, Any] | None:
    artifact_type = str(expected.get("artifactType") or "")
    if artifact_type not in {
        "SERVICE_DRAFT",
        "MAPPER_INTERFACE",
        "MAPPER_XML",
    }:
        return None
    candidates = [
        file
        for file in stage_files_by_type.get(artifact_type, [])
        if isinstance(file, Mapping)
    ]
    if not candidates:
        return None
    expected_class = str(expected.get("className") or "")
    for file in candidates:
        if str(file.get("className") or "") == expected_class:
            return file
    if len(candidates) == 1:
        return candidates[0]
    return None


def _dto_content_policy_guard(
    file: Mapping[str, Any],
    *,
    package_context: Mapping[str, str],
    package_context_review_required: bool,
) -> tuple[str, bool]:
    class_name = str(file.get("className") or "").strip()
    package_name = str(package_context.get("modelPackage") or "").strip()
    field_names = [
        field
        for field in _dedupe(_strings(file.get("requiredFields")))
        if _java_identifier(field) and not _is_placeholder_field(field)
    ]
    content = str(file.get("content") or "").strip()
    if not class_name or not field_names:
        return str(file.get("content") or ""), False
    if not content or not _java_type_pattern("class", class_name).search(content):
        return (
            _dto_floor_content(
                class_name=class_name,
                fields=field_names,
                package_name=package_name,
            ),
            True,
        )

    changed = False
    guarded = _ensure_java_package(
        content,
        package_name,
        force=not package_context_review_required,
    )
    changed = changed or guarded != content
    for field in field_names:
        if not _declares_java_field(guarded, field):
            guarded = _insert_before_final_brace(guarded, f"    private String {field};")
            changed = True
    if not _has_lombok_dto_policy(guarded):
        for field in field_names:
            missing_accessors = []
            if not _declares_java_getter(guarded, field):
                missing_accessors.append(_java_string_getter(field))
            if not _declares_java_setter(guarded, field):
                missing_accessors.append(_java_string_setter(field))
            if missing_accessors:
                guarded = _insert_before_final_brace(
                    guarded,
                    "\n\n".join(missing_accessors),
                )
                changed = True
    return guarded, changed


def _ensure_java_package(content: str, package_name: str, *, force: bool) -> str:
    if not package_name:
        return content
    package_pattern = _java_package_pattern()
    existing_package = _java_package_name(content)
    if existing_package and not force and not _placeholder_java_package(existing_package):
        return content
    replacement = f"package {package_name};\n\n"
    if package_pattern.search(content):
        return package_pattern.sub(replacement, content, count=1).lstrip()
    return f"{replacement}{content.lstrip()}"


def _java_package_pattern() -> re.Pattern[str]:
    return re.compile(
        r"^\s*package\s+([A-Za-z_$][A-Za-z0-9_$]*(?:\.[A-Za-z_$][A-Za-z0-9_$]*)*);\s*",
        flags=re.MULTILINE,
    )


def _java_package_name(content: str) -> str:
    match = _java_package_pattern().search(content)
    return match.group(1) if match else ""


def _placeholder_java_package(package_name: str) -> bool:
    lowered = str(package_name or "").lower()
    return lowered.startswith(("com.example", "org.example", "example."))


def _java_type_pattern(kind: str, name: str) -> re.Pattern[str]:
    return re.compile(rf"\b{re.escape(kind)}\s+{re.escape(name)}\b")


def _declares_java_field(content: str, field: str) -> bool:
    return bool(
        re.search(
            rf"\b(?:private|protected|public)\s+[\w.$<>, ?\[\]]+\s+{re.escape(field)}\s*(?:=[^;]+)?;",
            content,
        )
    )


def _declares_java_getter(content: str, field: str) -> bool:
    suffix = field[:1].upper() + field[1:]
    return bool(re.search(rf"\b(?:get|is){re.escape(suffix)}\s*\(", content))


def _declares_java_setter(content: str, field: str) -> bool:
    suffix = field[:1].upper() + field[1:]
    return bool(re.search(rf"\bset{re.escape(suffix)}\s*\(", content))


def _has_lombok_dto_policy(content: str) -> bool:
    return bool(re.search(r"@(Data|Getter|Setter|Value)\b", content))


def _insert_before_final_brace(content: str, insertion: str) -> str:
    text = content.rstrip()
    index = text.rfind("}")
    if index < 0:
        return f"{text}\n\n{insertion}\n"
    return f"{text[:index].rstrip()}\n\n{insertion}\n{text[index:]}"


def _java_string_getter(field: str) -> str:
    suffix = field[:1].upper() + field[1:]
    return (
        f"    public String get{suffix}() {{\n"
        f"        return {field};\n"
        "    }"
    )


def _java_string_setter(field: str) -> str:
    suffix = field[:1].upper() + field[1:]
    return (
        f"    public void set{suffix}(String {field}) {{\n"
        f"        this.{field} = {field};\n"
        "    }"
    )


def _dto_floor_file(
    expected: Mapping[str, Any],
    *,
    allowed_refs: Sequence[str],
    allowed_set: set[str],
    source_file: Mapping[str, Any] | None,
    package_context: Mapping[str, str],
    package_context_review_required: bool,
) -> dict[str, Any]:
    class_name = str(expected.get("className") or "").strip() or "DraftReviewRequiredDto"
    required_fields = [
        field
        for field in _strings(expected.get("requiredFields"))
        if _java_identifier(field) and not _is_placeholder_field(field)
    ]
    if not required_fields:
        raise AiDraftPackValidationError(
            [
                "dto_content: expected inventory lacks evidence-backed requiredFields "
                f"for DTO floor: {expected.get('path') or class_name}."
            ]
        )
    evidence_refs = _dedupe_refs(
        [
            *_strings(expected.get("evidenceRefs")),
            *_strings((source_file or {}).get("evidenceRefs")),
            *allowed_refs,
        ],
        allowed_set,
    ) or list(allowed_refs[:1])
    review_markers = _dedupe(
        [
            *_strings(expected.get("reviewMarkers")),
            *_strings((source_file or {}).get("reviewMarkers")),
            DTO_FLOOR_REVIEW_MARKER,
            *([PACKAGE_CONTEXT_REVIEW_MARKER] if package_context_review_required else []),
        ]
    )
    return {
        "artifactType": "DTO_DRAFT",
        "path": str(expected.get("path") or f"dto/{class_name}.java"),
        "role": str(expected.get("role") or "REVIEW_REQUIRED"),
        "className": class_name,
        "content": _dto_floor_content(
            class_name=class_name,
            fields=required_fields,
            package_name=str(package_context.get("modelPackage") or ""),
        ),
        "operationIds": _strings(expected.get("operationIds")),
        "evidenceRefs": evidence_refs,
        "reviewMarkers": review_markers,
        "dtoRole": expected.get("dtoRole") or (source_file or {}).get("dtoRole"),
        "requiredFields": required_fields,
        "references": _strings(expected.get("references")),
        "qualityScore": (source_file or {}).get("qualityScore"),
    }


def _dto_floor_content(
    *,
    class_name: str,
    fields: Sequence[str],
    package_name: str,
) -> str:
    field_names = [
        field
        for field in _dedupe(field for field in fields if _java_identifier(field))
        if not _is_placeholder_field(field)
    ]
    declarations = "\n".join(f"    private String {field};" for field in field_names)
    accessors = "\n\n".join(_java_string_accessors(field) for field in field_names)
    return (
        f"package {package_name};\n\n"
        f"public class {class_name} {{\n"
        "    // REVIEW_REQUIRED DTO content floor from sanitized P41 blueprint evidence.\n"
        f"{declarations}\n"
        "\n"
        f"{accessors}\n"
        "}"
    )


def _java_identifier(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", str(value or "")))


def _is_placeholder_field(value: str) -> bool:
    return bool(re.fullmatch(r"reviewRequiredField\d*", str(value or ""), flags=re.IGNORECASE))


def _java_package_context(
    sanitized_draft_context: Mapping[str, Any],
) -> tuple[dict[str, str], bool]:
    raw_context = sanitized_draft_context.get("javaPackageContext")
    raw_package_context = raw_context if isinstance(raw_context, Mapping) else {}
    model_package = _valid_java_package(
        str(
            raw_package_context.get("modelPackage")
            or raw_package_context.get("dtoPackage")
            or ""
        )
    )
    service_package = _valid_java_package(str(raw_package_context.get("servicePackage") or ""))
    mapper_package = _valid_java_package(str(raw_package_context.get("mapperPackage") or ""))
    package_context = dict(DEFAULT_JAVA_PACKAGE_CONTEXT)
    review_required = False
    if model_package:
        package_context["modelPackage"] = model_package
        package_context["dtoPackage"] = model_package
    else:
        review_required = True
    if service_package:
        package_context["servicePackage"] = service_package
    else:
        review_required = True
    if mapper_package:
        package_context["mapperPackage"] = mapper_package
    else:
        review_required = True
    return package_context, review_required


def _valid_java_package(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parts = text.split(".")
    if all(_java_identifier(part) for part in parts):
        return text
    return ""


def _java_string_accessors(field: str) -> str:
    suffix = field[:1].upper() + field[1:]
    return (
        f"    public String get{suffix}() {{\n"
        f"        return {field};\n"
        "    }\n\n"
        f"    public void set{suffix}(String {field}) {{\n"
        f"        this.{field} = {field};\n"
        "    }"
    )


def _missing_expected_stage_file(expected: Mapping[str, Any]) -> dict[str, str]:
    artifact_type = str(expected.get("artifactType") or "")
    return {
        "artifactType": artifact_type,
        "path": str(expected.get("path") or ""),
        "className": str(expected.get("className") or ""),
        "owningStage": _owning_stage_for_artifact(artifact_type),
    }


def _owning_stage_for_artifact(artifact_type: str) -> str:
    return {
        "DTO_DRAFT": "dto_content",
        "SERVICE_DRAFT": "service_content",
        "MAPPER_INTERFACE": "mapper_interface_content",
        "MAPPER_XML": "mapper_xml_content",
    }.get(str(artifact_type or ""), "integration_quality_gate")


def _dto_floor_component(summary: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "component": DTO_FLOOR_COMPONENT,
        "status": "SUCCEEDED",
        "action": "materialized_or_normalized_dto_stage_files_from_expected_inventory",
        "reviewMarker": DTO_FLOOR_REVIEW_MARKER,
        "fileCount": int(summary.get("fileCount") or 0),
        "files": list(summary.get("files") or [])[:40],
        "augmentedFileCount": int(summary.get("augmentedFileCount") or 0),
        "augmentedFiles": list(summary.get("augmentedFiles") or [])[:40],
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
        missing_files = _missing_expected_stage_files_from_findings(exc.findings)
        target_stages = _repair_stages_from_findings(exc.findings)
        return {
            "failureStage": _schema_failure_stage_from_findings(exc.findings),
            "errorClass": exc.__class__.__name__,
            "reason": "AiJavaMyBatisDraftPack schema validation failed.",
            "validationFindings": _safe_validation_findings(exc.findings),
            "missingExpectedStageFiles": missing_files,
            "targetStages": list(target_stages),
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
        "targetStages": list(repair_context.get("targetStages") or []),
        "missingExpectedStageFileCount": len(
            list(repair_context.get("missingExpectedStageFiles") or [])
        ),
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
    for item in _missing_expected_stage_files_from_findings(findings):
        stage = str(item.get("owningStage") or "")
        if stage:
            stages.append(stage)
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


def _missing_expected_stage_files_from_findings(
    findings: Sequence[str],
) -> list[dict[str, str]]:
    parsed: list[dict[str, str]] = []
    for finding in findings:
        text = str(finding)
        marker = "missing expected stage files:"
        if marker not in text:
            continue
        payload = text.split(marker, 1)[1].strip()
        if payload.endswith("."):
            payload = payload[:-1]
        try:
            raw_items = json.loads(payload)
        except json.JSONDecodeError:
            raw_items = _legacy_missing_stage_files(payload)
        if not isinstance(raw_items, Sequence) or isinstance(raw_items, str | bytes):
            continue
        for item in raw_items:
            if isinstance(item, Mapping):
                artifact_type = str(item.get("artifactType") or "")
                path = str(item.get("path") or "")
                class_name = str(item.get("className") or "")
                owning_stage = str(item.get("owningStage") or "") or _owning_stage_for_artifact(
                    artifact_type
                )
            else:
                text_item = str(item)
                parts = text_item.split(maxsplit=1)
                artifact_type = parts[0] if parts else ""
                path = parts[1] if len(parts) > 1 else ""
                class_name = path.rsplit("/", 1)[-1].removesuffix(".java").removesuffix(".xml")
                owning_stage = _owning_stage_for_artifact(artifact_type)
            if artifact_type or path:
                parsed.append(
                    {
                        "artifactType": artifact_type,
                        "path": path,
                        "className": class_name,
                        "owningStage": owning_stage,
                    }
                )
    return parsed[:80]


def _legacy_missing_stage_files(payload: str) -> list[str]:
    return re.findall(r"([A-Z_]+\s+[^'\\],]+)", payload)


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
