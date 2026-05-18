from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from enum import StrEnum
from typing import Any

from pydantic import Field, ValidationError

from ai_agent_runtime.models import StrictModel
from ai_agent_runtime.storage_safety import storage_safety_findings_for_text

AI_JAVA_MYBATIS_DRAFT_PACK_SCHEMA_VERSION = "AiJavaMyBatisDraftPack.v0.1"
AI_JAVA_MYBATIS_DRAFT_PACK_PROMPT_VERSION = "prompt:ai_java_mybatis_draft_pack@0.2.0"
AI_JAVA_MYBATIS_DRAFT_PACK_OUTPUT_SCHEMA_VERSION = (
    "schema:ai_java_mybatis_draft_pack@0.1.0"
)


class AiDraftPackValidationError(ValueError):
    def __init__(self, findings: Sequence[str]) -> None:
        self.findings = tuple(str(finding) for finding in findings if str(finding).strip())
        message = "; ".join(self.findings) or "AI Java/MyBatis draft pack validation failed."
        super().__init__(message)


class AiDraftPackArtifactType(StrEnum):
    DTO_DRAFT = "DTO_DRAFT"
    SERVICE_DRAFT = "SERVICE_DRAFT"
    MAPPER_INTERFACE = "MAPPER_INTERFACE"
    MAPPER_XML = "MAPPER_XML"


class AiDraftPackFileRole(StrEnum):
    QUERY_DTO = "QUERY_DTO"
    RESULT_DTO = "RESULT_DTO"
    COMMAND_DTO = "COMMAND_DTO"
    BATCH_ITEM_DTO = "BATCH_ITEM_DTO"
    CALL_REQUEST_DTO = "CALL_REQUEST_DTO"
    SERVICE = "SERVICE"
    MAPPER_INTERFACE = "MAPPER_INTERFACE"
    MAPPER_XML = "MAPPER_XML"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class AiJavaMyBatisDraftPackFile(StrictModel):
    artifact_type: AiDraftPackArtifactType = Field(alias="artifactType")
    path: str = Field(min_length=1)
    role: AiDraftPackFileRole
    class_name: str = Field(alias="className", min_length=1)
    content: str = Field(min_length=1)
    operation_ids: list[str] = Field(alias="operationIds", min_length=1)
    evidence_refs: list[str] = Field(alias="evidenceRefs", min_length=1)
    review_markers: list[str] = Field(default_factory=list, alias="reviewMarkers")
    dto_role: str | None = Field(default=None, alias="dtoRole")
    required_fields: list[str] = Field(default_factory=list, alias="requiredFields")
    references: list[str] = Field(default_factory=list)
    quality_score: float | None = Field(default=None, alias="qualityScore")


class AiJavaMyBatisDraftPackQualityGates(StrictModel):
    required_dto_classes: list[str] = Field(default_factory=list, alias="requiredDtoClasses")
    required_service_methods: list[str] = Field(
        default_factory=list,
        alias="requiredServiceMethods",
    )
    required_mapper_methods: list[str] = Field(
        default_factory=list,
        alias="requiredMapperMethods",
    )
    required_review_markers: list[str] = Field(
        default_factory=list,
        alias="requiredReviewMarkers",
    )
    blocker_patterns: list[str] = Field(default_factory=list, alias="blockerPatterns")
    blank_content_is_blocker: bool = Field(default=True, alias="blankContentIsBlocker")
    dto_collapse_is_blocker: bool = Field(default=True, alias="dtoCollapseIsBlocker")
    fallback_skeleton_persistence_allowed_on_failure: bool = Field(
        default=False,
        alias="fallbackSkeletonPersistenceAllowedOnFailure",
    )


class AiJavaMyBatisDraftPackOutput(StrictModel):
    schema_version: str = Field(
        default=AI_JAVA_MYBATIS_DRAFT_PACK_SCHEMA_VERSION,
        alias="schemaVersion",
    )
    contract_target: str = Field(default="AiJavaMyBatisDraftPack", alias="contractTarget")
    target_ref: str = Field(alias="targetRef", min_length=1)
    source_policy: str = Field(default="sanitized_facts_only", alias="sourcePolicy")
    production_ready: bool = Field(default=False, alias="productionReady")
    files: list[AiJavaMyBatisDraftPackFile] = Field(min_length=1)
    evidence_refs: list[str] = Field(alias="evidenceRefs", min_length=1)
    review_markers: list[str] = Field(default_factory=list, alias="reviewMarkers")
    quality_gates: AiJavaMyBatisDraftPackQualityGates = Field(alias="qualityGates")
    assumptions: list[str] = Field(default_factory=list)

    def to_storage_dict(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, mode="json")


class AiJavaMyBatisDraftPackPlannerOutput(AiJavaMyBatisDraftPackOutput):
    pass


def parse_ai_java_mybatis_draft_pack_json(
    output_text: str,
    *,
    allowed_evidence_refs: Sequence[str] | None = None,
) -> AiJavaMyBatisDraftPackPlannerOutput:
    payload = json.loads(output_text)
    if not isinstance(payload, Mapping):
        raise AiDraftPackValidationError(["Root AI draft pack output must be an object."])
    return validate_ai_java_mybatis_draft_pack_output(
        payload,
        allowed_evidence_refs=allowed_evidence_refs,
    )


def validate_ai_java_mybatis_draft_pack_output(
    payload: Mapping[str, Any],
    *,
    allowed_evidence_refs: Sequence[str] | None = None,
) -> AiJavaMyBatisDraftPackPlannerOutput:
    findings: list[str] = []
    try:
        model = AiJavaMyBatisDraftPackPlannerOutput.model_validate(payload)
    except ValidationError as exc:
        for error in exc.errors(include_input=False):
            loc = ".".join(str(part) for part in error.get("loc", ())) or "<root>"
            message = str(error.get("msg") or "schema validation failed")
            error_type = str(error.get("type") or "validation_error")
            findings.append(f"schema validation failed at {loc}: {message} ({error_type})")
        if not findings:
            findings.append("schema validation failed")
        raise AiDraftPackValidationError(findings) from exc

    if model.schema_version != AI_JAVA_MYBATIS_DRAFT_PACK_SCHEMA_VERSION:
        findings.append(f"schemaVersion must be {AI_JAVA_MYBATIS_DRAFT_PACK_SCHEMA_VERSION}.")
    if model.contract_target != "AiJavaMyBatisDraftPack":
        findings.append("contractTarget must be AiJavaMyBatisDraftPack.")
    if model.source_policy != "sanitized_facts_only":
        findings.append("sourcePolicy must be sanitized_facts_only.")
    if model.production_ready is not False:
        findings.append("productionReady must be false for P42 AI draft packs.")
    if not model.evidence_refs:
        findings.append("root evidenceRefs must not be empty.")
    findings.extend(_root_blocker_findings(model))
    findings.extend(_root_storage_safety_findings(model))

    files = list(model.files)
    dto_files = [file for file in files if file.artifact_type == AiDraftPackArtifactType.DTO_DRAFT]
    service_files = [
        file for file in files if file.artifact_type == AiDraftPackArtifactType.SERVICE_DRAFT
    ]
    mapper_files = [
        file for file in files if file.artifact_type == AiDraftPackArtifactType.MAPPER_INTERFACE
    ]
    mapper_xml_files = [
        file for file in files if file.artifact_type == AiDraftPackArtifactType.MAPPER_XML
    ]
    if len(dto_files) < 2:
        findings.append("files must include at least two DTO_DRAFT entries.")
    if len(service_files) != 1:
        findings.append("files must include exactly one SERVICE_DRAFT entry.")
    if len(mapper_files) != 1:
        findings.append("files must include exactly one MAPPER_INTERFACE entry.")
    if len(mapper_xml_files) != 1:
        findings.append("files must include exactly one MAPPER_XML entry.")

    class_names = {file.class_name for file in files}
    required_dtos = set(model.quality_gates.required_dto_classes)
    missing_dtos = sorted(required_dtos - {file.class_name for file in dto_files})
    if missing_dtos:
        findings.append(f"qualityGates.requiredDtoClasses missing DTO files: {missing_dtos}.")

    for file in files:
        path = f"files[{file.path}]"
        if not file.content.strip():
            findings.append(f"{path}.content must not be blank.")
        if not file.evidence_refs:
            findings.append(f"{path}.evidenceRefs must not be empty.")
        findings.extend(_artifact_role_findings(file, path))
        findings.extend(_blocked_identifier_findings(file, path))
        findings.extend(_storage_safety_findings(file, path))
        for reference in file.references:
            if reference and reference not in class_names:
                findings.append(f"{path}.references contains unknown class: {reference}.")

    required_markers = set(model.quality_gates.required_review_markers)
    if required_markers:
        present_markers = set(model.review_markers)
        for file in files:
            present_markers.update(file.review_markers)
        missing_markers = sorted(required_markers - present_markers)
        if missing_markers:
            findings.append(f"required REVIEW_REQUIRED markers missing: {missing_markers}.")

    allowed = {str(ref) for ref in (allowed_evidence_refs or ()) if str(ref).strip()}
    if allowed:
        for ref in sorted(set(all_ai_java_mybatis_draft_pack_evidence_refs(model)) - allowed):
            findings.append(f"evidenceRefs contains unknown ref: {ref}.")

    if findings:
        raise AiDraftPackValidationError(findings)
    return model


def all_ai_java_mybatis_draft_pack_evidence_refs(
    model: AiJavaMyBatisDraftPackOutput,
) -> tuple[str, ...]:
    refs: list[str] = []
    refs.extend(model.evidence_refs)
    for file in model.files:
        refs.extend(file.evidence_refs)
    return tuple(ref for ref in refs if str(ref).strip())


def ai_java_mybatis_draft_pack_output_schema(
    allowed_evidence_refs: Sequence[str] | None = None,
) -> dict[str, Any]:
    evidence_ref_array = _evidence_ref_array_schema(allowed_evidence_refs)
    return {
        "type": "object",
        "properties": {
            "schemaVersion": {
                "type": "string",
                "const": AI_JAVA_MYBATIS_DRAFT_PACK_SCHEMA_VERSION,
            },
            "contractTarget": {"type": "string", "const": "AiJavaMyBatisDraftPack"},
            "targetRef": {"type": "string", "minLength": 1},
            "sourcePolicy": {"type": "string", "const": "sanitized_facts_only"},
            "productionReady": {"type": "boolean", "const": False},
            "files": {
                "type": "array",
                "minItems": 1,
                "items": _draft_pack_file_schema(evidence_ref_array),
            },
            "evidenceRefs": evidence_ref_array,
            "reviewMarkers": {"type": "array", "items": {"type": "string"}},
            "qualityGates": _quality_gates_schema(),
            "assumptions": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "schemaVersion",
            "contractTarget",
            "targetRef",
            "sourcePolicy",
            "productionReady",
            "files",
            "evidenceRefs",
            "reviewMarkers",
            "qualityGates",
            "assumptions",
        ],
        "additionalProperties": False,
    }


def _draft_pack_file_schema(evidence_ref_array: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "artifactType": {
                "type": "string",
                "enum": [artifact_type.value for artifact_type in AiDraftPackArtifactType],
            },
            "path": {"type": "string", "minLength": 1},
            "role": {"type": "string", "enum": [role.value for role in AiDraftPackFileRole]},
            "className": {"type": "string", "minLength": 1},
            "content": {"type": "string", "minLength": 1},
            "operationIds": {
                "type": "array",
                "minItems": 1,
                "items": {"type": "string", "minLength": 1},
            },
            "evidenceRefs": evidence_ref_array,
            "reviewMarkers": {"type": "array", "items": {"type": "string"}},
            "dtoRole": {"type": ["string", "null"]},
            "requiredFields": {"type": "array", "items": {"type": "string"}},
            "references": {"type": "array", "items": {"type": "string"}},
            "qualityScore": {"type": ["number", "null"]},
        },
        "required": [
            "artifactType",
            "path",
            "role",
            "className",
            "content",
            "operationIds",
            "evidenceRefs",
            "reviewMarkers",
        ],
        "additionalProperties": False,
    }


def _quality_gates_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "requiredDtoClasses": {"type": "array", "items": {"type": "string"}},
            "requiredServiceMethods": {"type": "array", "items": {"type": "string"}},
            "requiredMapperMethods": {"type": "array", "items": {"type": "string"}},
            "requiredReviewMarkers": {"type": "array", "items": {"type": "string"}},
            "blockerPatterns": {"type": "array", "items": {"type": "string"}},
            "blankContentIsBlocker": {"type": "boolean"},
            "dtoCollapseIsBlocker": {"type": "boolean"},
            "fallbackSkeletonPersistenceAllowedOnFailure": {"type": "boolean"},
        },
        "required": [
            "requiredDtoClasses",
            "requiredServiceMethods",
            "requiredMapperMethods",
            "requiredReviewMarkers",
            "blockerPatterns",
            "blankContentIsBlocker",
            "dtoCollapseIsBlocker",
            "fallbackSkeletonPersistenceAllowedOnFailure",
        ],
        "additionalProperties": False,
    }


def _evidence_ref_array_schema(allowed_evidence_refs: Sequence[str] | None) -> dict[str, Any]:
    item_schema: dict[str, Any] = {"type": "string", "minLength": 1}
    allowed_refs = sorted({str(ref) for ref in (allowed_evidence_refs or ()) if str(ref).strip()})
    if allowed_refs:
        item_schema["enum"] = allowed_refs
    return {"type": "array", "items": item_schema, "minItems": 1}


def _artifact_role_findings(file: AiJavaMyBatisDraftPackFile, path: str) -> list[str]:
    dto_roles = {
        AiDraftPackFileRole.QUERY_DTO,
        AiDraftPackFileRole.RESULT_DTO,
        AiDraftPackFileRole.COMMAND_DTO,
        AiDraftPackFileRole.BATCH_ITEM_DTO,
        AiDraftPackFileRole.CALL_REQUEST_DTO,
        AiDraftPackFileRole.REVIEW_REQUIRED,
    }
    expected_roles = {
        AiDraftPackArtifactType.SERVICE_DRAFT: AiDraftPackFileRole.SERVICE,
        AiDraftPackArtifactType.MAPPER_INTERFACE: AiDraftPackFileRole.MAPPER_INTERFACE,
        AiDraftPackArtifactType.MAPPER_XML: AiDraftPackFileRole.MAPPER_XML,
    }
    if file.artifact_type == AiDraftPackArtifactType.DTO_DRAFT and file.role not in dto_roles:
        return [f"{path}.role must be a DTO role for DTO_DRAFT."]
    expected_role = expected_roles.get(file.artifact_type)
    if expected_role is not None and file.role != expected_role:
        return [f"{path}.role must be {expected_role.value} for {file.artifact_type.value}."]
    return []


def _blocked_identifier_findings(
    file: AiJavaMyBatisDraftPackFile,
    path: str,
) -> list[str]:
    text = "\n".join([file.path, file.class_name, file.content, *file.review_markers])
    blockers = (
        "OperationModelReviewRequired",
        "P41_OPERATION_MODEL_REVIEW_REQUIRED",
    )
    return [
        f"{path} contains blocked fallback or DTO-collapse marker: {blocker}."
        for blocker in blockers
        if blocker in text
    ]


def _root_blocker_findings(model: AiJavaMyBatisDraftPackOutput) -> list[str]:
    text = "\n".join([*model.review_markers, *model.assumptions])
    blockers = (
        "OperationModelReviewRequired",
        "P41_OPERATION_MODEL_REVIEW_REQUIRED",
    )
    return [
        f"root payload contains blocked fallback or DTO-collapse marker: {blocker}."
        for blocker in blockers
        if blocker in text
    ]


def _root_storage_safety_findings(model: AiJavaMyBatisDraftPackOutput) -> list[str]:
    findings: list[str] = []
    for text in (*model.review_markers, *model.assumptions):
        for finding in storage_safety_findings_for_text(text):
            findings.append(f"root payload contains forbidden storage text: {finding['code']}.")
    return findings


def _storage_safety_findings(
    file: AiJavaMyBatisDraftPackFile,
    path: str,
) -> list[str]:
    findings: list[str] = []
    for text in (file.path, file.class_name, file.content):
        for finding in storage_safety_findings_for_text(text):
            findings.append(f"{path} contains forbidden storage text: {finding['code']}.")
    lowered = file.content.lower()
    for marker in (
        "raw guide body",
        "raw provider response",
        "raw openai response",
        "raw prompt",
        "row data",
        "source apply",
        "automatic source apply",
        "deploy this source",
    ):
        if marker in lowered:
            findings.append(f"{path}.content contains forbidden marker: {marker}.")
    return findings
