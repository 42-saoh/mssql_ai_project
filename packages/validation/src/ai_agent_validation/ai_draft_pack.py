from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from collections.abc import Mapping, Sequence
from typing import Any

from ai_agent_runtime.ai_draft_pack import (
    AiDraftPackArtifactType,
    AiDraftPackValidationError,
    AiJavaMyBatisDraftPackFile,
    AiJavaMyBatisDraftPackOutput,
    validate_ai_java_mybatis_draft_pack_output,
)

from ai_agent_validation.models import (
    ValidationCheck,
    ValidationCheckResult,
    ValidationReport,
    ValidationSeverity,
    ValidationStatus,
)

RULE_SCHEMA = "p42.ai_draft_pack.schema"
RULE_PRODUCTION_READY = "p42.ai_draft_pack.production_ready"
RULE_DTO_CLASS = "p42.ai_draft_pack.dto.class_declaration"
RULE_DTO_FIELD = "p42.ai_draft_pack.dto.required_field"
RULE_DTO_COLLAPSE = "p42.ai_draft_pack.dto.collapse"
RULE_NON_DTO_REFERENCE = "p42.ai_draft_pack.non_dto.dto_reference"
RULE_SERVICE_METHOD = "p42.ai_draft_pack.service.method"
RULE_MAPPER_METHOD = "p42.ai_draft_pack.mapper.method"
RULE_MAPPER_XML = "p42.ai_draft_pack.mapper_xml.static_shape"
RULE_FORBIDDEN_PAYLOAD = "p42.ai_draft_pack.forbidden_payload"
RULE_REVIEW_MARKER = "p42.ai_draft_pack.review_marker"
RULE_ASCII_IDENTIFIER = "p50.ai_draft_pack.identifier.ascii"
RULE_SERVICE_FLOW = "p50.ai_draft_pack.service.business_flow"
RULE_MAPPER_CONSISTENCY = "p50.ai_draft_pack.mapper.interface_xml_consistency"
RULE_MAPPER_XML_DB_OPERATION = "p50.ai_draft_pack.mapper_xml.db_operation"

DEFAULT_REQUIRED_REVIEW_MARKERS = (
    "CROSS_DB_WRITE_REVIEW_REQUIRED",
    "CALLED_PROCEDURE_IO_REVIEW_REQUIRED",
    "TVF_OR_PROCEDURE_KIND_REVIEW_REQUIRED",
    "TRANSACTION_BOUNDARY_REVIEW_REQUIRED",
)

DEFAULT_FORBIDDEN_PATTERNS = (
    "OperationModelReviewRequired",
    "P41_OPERATION_MODEL_REVIEW_REQUIRED",
    r"\bCREATE\s+(?:OR\s+ALTER\s+)?PROC(?:EDURE)?\b",
    r"\bALTER\s+PROC(?:EDURE)?\b",
    r"\braw\s+sp\b",
    r"\braw\s+guide\s+body\b",
    r"\braw\s+prompt\b",
    r"\braw\s+provider\s+response\b",
    r"\brow\s+data\b",
    r"\bsample\s+rows?\b",
    r"\bprocedure\s+execution\b",
    r"\bexecute\s+(?:stored\s+)?procedure\b",
    r"\bsource\s+apply\b",
    r"\bgenerated\s+source\s+apply\b",
    r"\bdeploy(?:ed|ment)?\b",
    r"\bproduction[-\s]+ready\b",
)


def validate_ai_java_mybatis_draft_pack_quality(
    payload: Mapping[str, Any] | AiJavaMyBatisDraftPackOutput,
    *,
    artifact_id: str = "ai-java-mybatis-draft-pack",
    required_review_markers: Sequence[str] | None = None,
) -> ValidationReport:
    """Validate P42 Java/MyBatis draft pack content without executing code or SQL."""

    model, schema_checks = _schema_validation(payload)
    if model is None:
        return ValidationReport(
            artifact_id=artifact_id,
            status=ValidationStatus.FAILED,
            checks=tuple(schema_checks),
            metadata={
                "schemaValidated": False,
                "productionReady": False,
                "scores": {},
            },
        )

    checks: list[ValidationCheck] = list(schema_checks)
    dto_files = _files_by_artifact(model, AiDraftPackArtifactType.DTO_DRAFT)
    service_files = _files_by_artifact(model, AiDraftPackArtifactType.SERVICE_DRAFT)
    mapper_files = _files_by_artifact(model, AiDraftPackArtifactType.MAPPER_INTERFACE)
    mapper_xml_files = _files_by_artifact(model, AiDraftPackArtifactType.MAPPER_XML)

    required_dtos = tuple(_dedupe(model.quality_gates.required_dto_classes))
    required_service_methods = tuple(_dedupe(model.quality_gates.required_service_methods))
    required_mapper_methods = tuple(_dedupe(model.quality_gates.required_mapper_methods))
    required_markers = tuple(
        _dedupe(
            [
                *DEFAULT_REQUIRED_REVIEW_MARKERS,
                *model.quality_gates.required_review_markers,
                *(required_review_markers or ()),
            ]
        )
    )

    checks.append(
        _check(
            not model.production_ready,
            RULE_PRODUCTION_READY,
            "P42 AI draft pack remains productionReady=false.",
            "P42 AI draft pack must remain productionReady=false.",
        )
    )
    checks.extend(_identifier_checks(model))
    checks.extend(_dto_quality_checks(dto_files, required_dtos))
    checks.extend(
        _non_dto_reference_checks(
            service_files,
            mapper_files,
            mapper_xml_files,
            required_dtos,
        )
    )
    checks.extend(_service_method_checks(service_files, required_service_methods))
    checks.extend(_service_business_flow_checks(service_files, required_service_methods))
    checks.extend(_mapper_method_checks(mapper_files, required_mapper_methods))
    checks.extend(
        _mapper_interface_xml_consistency_checks(
            mapper_files,
            mapper_xml_files,
            required_mapper_methods,
        )
    )
    checks.extend(
        _mapper_xml_checks(
            mapper_xml_files,
            required_mapper_methods,
            target_ref=model.target_ref,
        )
    )
    checks.extend(_forbidden_payload_checks(model))
    checks.extend(_required_review_marker_checks(model, required_markers))

    scores = _scores(
        dto_files=dto_files,
        service_files=service_files,
        mapper_files=mapper_files,
        mapper_xml_files=mapper_xml_files,
        required_dtos=required_dtos,
        required_service_methods=required_service_methods,
        required_mapper_methods=required_mapper_methods,
        required_markers=required_markers,
        model=model,
    )
    review_points = tuple(_dedupe(_present_review_markers(model)))
    return ValidationReport(
        artifact_id=artifact_id,
        status=_status_from_checks(checks),
        checks=tuple(checks),
        manual_review_points=review_points,
        metadata={
            "schemaValidated": True,
            "schemaVersion": model.schema_version,
            "targetRef": model.target_ref,
            "productionReady": model.production_ready,
            "scores": scores,
        },
    )


def _schema_validation(
    payload: Mapping[str, Any] | AiJavaMyBatisDraftPackOutput,
) -> tuple[AiJavaMyBatisDraftPackOutput | None, list[ValidationCheck]]:
    if isinstance(payload, AiJavaMyBatisDraftPackOutput):
        return payload, [
            _pass(RULE_SCHEMA, "AiJavaMyBatisDraftPack.v0.1 schema validation passed.")
        ]
    try:
        return validate_ai_java_mybatis_draft_pack_output(payload), [
            _pass(RULE_SCHEMA, "AiJavaMyBatisDraftPack.v0.1 schema validation passed.")
        ]
    except AiDraftPackValidationError as exc:
        findings = exc.findings or (str(exc),)
        return None, [
            _fail(
                RULE_SCHEMA,
                f"AiJavaMyBatisDraftPack.v0.1 schema validation failed: {finding}",
                severity=ValidationSeverity.BLOCKER,
            )
            for finding in findings
        ]


def _dto_quality_checks(
    dto_files: Sequence[AiJavaMyBatisDraftPackFile],
    required_dtos: Sequence[str],
) -> list[ValidationCheck]:
    checks: list[ValidationCheck] = []
    dto_by_class = {file.class_name: file for file in dto_files}
    missing = sorted(set(required_dtos) - set(dto_by_class))
    checks.append(
        _check(
            not missing,
            RULE_DTO_COLLAPSE,
            "Required DTO classes are represented by separate DTO_DRAFT files.",
            f"Required DTO classes are missing from DTO_DRAFT files: {missing}.",
            severity=ValidationSeverity.BLOCKER,
        )
    )
    for file in dto_files:
        class_declared = bool(_java_type_pattern("class", file.class_name).search(file.content))
        checks.append(
            _check(
                class_declared,
                RULE_DTO_CLASS,
                f"{file.path} declares {file.class_name}.",
                f"{file.path} must declare Java class {file.class_name}.",
            )
        )
        for field in file.required_fields:
            checks.append(
                _check(
                    _declares_java_field(file.content, field),
                    RULE_DTO_FIELD,
                    f"{file.path} declares required DTO field {field}.",
                    f"{file.path} is missing required DTO field declaration {field}.",
                )
            )
    return checks


def _non_dto_reference_checks(
    service_files: Sequence[AiJavaMyBatisDraftPackFile],
    mapper_files: Sequence[AiJavaMyBatisDraftPackFile],
    mapper_xml_files: Sequence[AiJavaMyBatisDraftPackFile],
    required_dtos: Sequence[str],
) -> list[ValidationCheck]:
    checks: list[ValidationCheck] = []
    for file in [*service_files, *mapper_files, *mapper_xml_files]:
        structured_refs = set(file.references)
        for dto in required_dtos:
            has_reference = dto in structured_refs and _contains_word(file.content, dto)
            checks.append(
                _check(
                    has_reference,
                    RULE_NON_DTO_REFERENCE,
                    f"{file.path} references DTO {dto}.",
                    f"{file.path} must reference DTO {dto} in metadata and content.",
                )
            )
    return checks


def _service_method_checks(
    service_files: Sequence[AiJavaMyBatisDraftPackFile],
    required_methods: Sequence[str],
) -> list[ValidationCheck]:
    return _method_checks(
        files=service_files,
        required_methods=required_methods,
        rule_id=RULE_SERVICE_METHOD,
        label="Service",
    )


def _mapper_method_checks(
    mapper_files: Sequence[AiJavaMyBatisDraftPackFile],
    required_methods: Sequence[str],
) -> list[ValidationCheck]:
    return _method_checks(
        files=mapper_files,
        required_methods=required_methods,
        rule_id=RULE_MAPPER_METHOD,
        label="Mapper interface",
    )


def _method_checks(
    *,
    files: Sequence[AiJavaMyBatisDraftPackFile],
    required_methods: Sequence[str],
    rule_id: str,
    label: str,
) -> list[ValidationCheck]:
    checks: list[ValidationCheck] = []
    for file in files:
        for method in required_methods:
            checks.append(
                _check(
                    _contains_word(file.content, method),
                    rule_id,
                    f"{label} {file.path} includes method token {method}.",
                    f"{label} {file.path} is missing method token {method}.",
                )
            )
    return checks


def _identifier_checks(model: AiJavaMyBatisDraftPackOutput) -> list[ValidationCheck]:
    checks: list[ValidationCheck] = []
    for file in model.files:
        checks.append(
            _check(
                _java_identifier(file.class_name),
                RULE_ASCII_IDENTIFIER,
                f"{file.path} uses ASCII Java class identifier {file.class_name}.",
                f"{file.path} className must be an ASCII Java identifier: {file.class_name}.",
                severity=ValidationSeverity.BLOCKER,
            )
        )
        for field in file.required_fields:
            checks.append(
                _check(
                    _java_identifier(field),
                    RULE_ASCII_IDENTIFIER,
                    f"{file.path} uses ASCII Java field identifier {field}.",
                    f"{file.path} requiredFields entry must be an ASCII Java identifier: {field}.",
                    severity=ValidationSeverity.BLOCKER,
                )
            )
    return checks


def _service_business_flow_checks(
    service_files: Sequence[AiJavaMyBatisDraftPackFile],
    required_methods: Sequence[str],
) -> list[ValidationCheck]:
    checks: list[ValidationCheck] = []
    for file in service_files:
        for method in required_methods:
            body = _java_method_body(file.content, method)
            meaningful_body = _strip_java_comments(body or "").strip()
            calls_mapper = bool(
                body
                and re.search(
                    rf"\bmapper\s*\.\s*{re.escape(method)}\s*\(",
                    body,
                )
            )
            has_business_flow = bool(
                meaningful_body
                and (
                    calls_mapper
                    or re.search(
                        r"\b(?:if|switch|for|while|return|throw)\b",
                        meaningful_body,
                    )
                )
            )
            checks.append(
                _check(
                    body is not None and has_business_flow,
                    RULE_SERVICE_FLOW,
                    f"{file.path} method {method} has non-empty Java orchestration flow.",
                    f"{file.path} method {method} must have a non-empty Service body with mapper orchestration or branch flow.",
                    severity=ValidationSeverity.BLOCKER,
                )
            )
    return checks


def _mapper_interface_xml_consistency_checks(
    mapper_files: Sequence[AiJavaMyBatisDraftPackFile],
    mapper_xml_files: Sequence[AiJavaMyBatisDraftPackFile],
    required_methods: Sequence[str],
) -> list[ValidationCheck]:
    mapper_method_names: set[str] = set()
    for file in mapper_files:
        mapper_method_names.update(_java_method_names(file.content))

    xml_statement_ids: set[str] = set()
    for file in mapper_xml_files:
        try:
            root = ET.fromstring(file.content)
        except ET.ParseError:
            continue
        xml_statement_ids.update(_xml_statement_ids(root))

    checks: list[ValidationCheck] = []
    for method in required_methods:
        checks.append(
            _check(
                method in mapper_method_names and method in xml_statement_ids,
                RULE_MAPPER_CONSISTENCY,
                f"Mapper interface method {method} has a matching Mapper XML statement id.",
                f"Mapper method {method} must exist in both interface and Mapper XML statement ids.",
                severity=ValidationSeverity.BLOCKER,
            )
        )
    return checks


def _mapper_xml_checks(
    mapper_xml_files: Sequence[AiJavaMyBatisDraftPackFile],
    required_methods: Sequence[str],
    *,
    target_ref: str,
) -> list[ValidationCheck]:
    checks: list[ValidationCheck] = []
    for file in mapper_xml_files:
        try:
            root = ET.fromstring(file.content)
        except ET.ParseError as exc:
            checks.append(
                _fail(
                    RULE_MAPPER_XML,
                    f"{file.path} must be well-formed Mapper XML: {exc}.",
                    severity=ValidationSeverity.BLOCKER,
                )
            )
            continue
        checks.append(
            _check(
                _local_name(root.tag) == "mapper",
                RULE_MAPPER_XML,
                f"{file.path} has mapper root element.",
                f"{file.path} must use a mapper root element.",
            )
        )
        statement_ids = _xml_statement_ids(root)
        for method in required_methods:
            statement = _xml_statement_by_id(root, method)
            checks.append(
                _check(
                    method in statement_ids,
                    RULE_MAPPER_XML,
                    f"{file.path} includes Mapper XML statement id {method}.",
                    f"{file.path} is missing Mapper XML statement id {method}.",
                )
            )
            if statement is None:
                continue
            statement_text = _xml_text(statement)
            checks.append(
                _check(
                    _contains_db_operation(statement_text),
                    RULE_MAPPER_XML_DB_OPERATION,
                    f"{file.path} statement {method} contains statement-level DB logic.",
                    f"{file.path} statement {method} must contain SELECT/INSERT/UPDATE/DELETE/MERGE/EXEC/CALL logic.",
                    severity=ValidationSeverity.BLOCKER,
                )
            )
        checks.append(
            _check(
                not _calls_original_target_sp(file.content, target_ref),
                RULE_MAPPER_XML_DB_OPERATION,
                f"{file.path} does not wrap the original target procedure.",
                f"{file.path} must not pass quality with a wrapper-only EXEC/CALL of the original target procedure.",
                severity=ValidationSeverity.BLOCKER,
            )
        )
    return checks


def _forbidden_payload_checks(model: AiJavaMyBatisDraftPackOutput) -> list[ValidationCheck]:
    checks: list[ValidationCheck] = []
    patterns = tuple(
        _dedupe([*DEFAULT_FORBIDDEN_PATTERNS, *model.quality_gates.blocker_patterns])
    )
    root_text = "\n".join([*model.review_markers, *model.assumptions])
    checks.extend(_forbidden_text_checks("root", root_text, patterns))
    for file in model.files:
        text = "\n".join([file.path, file.class_name, file.content, *file.review_markers])
        checks.extend(_forbidden_text_checks(file.path, text, patterns))
    if not checks:
        checks.append(_pass(RULE_FORBIDDEN_PAYLOAD, "No forbidden payload markers were found."))
    return checks


def _forbidden_text_checks(
    location: str,
    text: str,
    patterns: Sequence[str],
) -> list[ValidationCheck]:
    checks: list[ValidationCheck] = []
    for pattern in patterns:
        if re.search(pattern, text, flags=re.IGNORECASE):
            checks.append(
                _fail(
                    RULE_FORBIDDEN_PAYLOAD,
                    f"{location} contains forbidden payload marker matching {pattern}.",
                    severity=ValidationSeverity.BLOCKER,
                )
            )
    return checks


def _required_review_marker_checks(
    model: AiJavaMyBatisDraftPackOutput,
    required_markers: Sequence[str],
) -> list[ValidationCheck]:
    present = set(_present_review_markers(model))
    checks: list[ValidationCheck] = []
    for marker in required_markers:
        checks.append(
            _check(
                marker in present,
                RULE_REVIEW_MARKER,
                f"Required review marker is preserved: {marker}.",
                f"Required REVIEW_REQUIRED marker is missing: {marker}.",
                severity=ValidationSeverity.BLOCKER,
            )
        )
    return checks


def _present_review_markers(model: AiJavaMyBatisDraftPackOutput) -> list[str]:
    markers: list[str] = list(model.review_markers)
    for file in model.files:
        markers.extend(file.review_markers)
    return _dedupe(markers)


def _scores(
    *,
    dto_files: Sequence[AiJavaMyBatisDraftPackFile],
    service_files: Sequence[AiJavaMyBatisDraftPackFile],
    mapper_files: Sequence[AiJavaMyBatisDraftPackFile],
    mapper_xml_files: Sequence[AiJavaMyBatisDraftPackFile],
    required_dtos: Sequence[str],
    required_service_methods: Sequence[str],
    required_mapper_methods: Sequence[str],
    required_markers: Sequence[str],
    model: AiJavaMyBatisDraftPackOutput,
) -> dict[str, Any]:
    dto_classes = {file.class_name for file in dto_files}
    service_text = "\n".join(file.content for file in service_files)
    mapper_text = "\n".join(file.content for file in mapper_files)
    present_markers = set(_present_review_markers(model))
    return {
        "requiredDtoFileCoverage": _coverage(required_dtos, dto_classes),
        "requiredServiceMethodCoverage": _token_coverage(required_service_methods, service_text),
        "requiredMapperMethodCoverage": _token_coverage(required_mapper_methods, mapper_text),
        "requiredReviewMarkerCoverage": _coverage(required_markers, present_markers),
        "expectedDtoArtifactRows": len(dto_files),
        "expectedServiceArtifactRows": len(service_files),
        "expectedMapperInterfaceArtifactRows": len(mapper_files),
        "expectedMapperXmlArtifactRows": len(mapper_xml_files),
        "operationModelFallbackAllowed": (
            model.quality_gates.fallback_skeleton_persistence_allowed_on_failure
        ),
        "singleDtoCollapseAllowed": not model.quality_gates.dto_collapse_is_blocker,
        "blankFileAllowed": not model.quality_gates.blank_content_is_blocker,
        "forbiddenStorageFindings": 0,
    }


def _coverage(required: Sequence[str], present: set[str]) -> float:
    if not required:
        return 1.0
    return len(set(required) & present) / len(set(required))


def _token_coverage(required: Sequence[str], text: str) -> float:
    if not required:
        return 1.0
    present = {token for token in required if _contains_word(text, token)}
    return len(present) / len(set(required))


def _files_by_artifact(
    model: AiJavaMyBatisDraftPackOutput,
    artifact_type: AiDraftPackArtifactType,
) -> tuple[AiJavaMyBatisDraftPackFile, ...]:
    return tuple(file for file in model.files if file.artifact_type == artifact_type)


def _java_type_pattern(kind: str, name: str) -> re.Pattern[str]:
    return re.compile(rf"\b(?:public\s+)?{kind}\s+{re.escape(name)}\b")


def _java_identifier(value: str) -> bool:
    return bool(re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", str(value or "")))


def _declares_java_field(content: str, field: str) -> bool:
    if not _java_identifier(field):
        return False
    return bool(
        re.search(
            rf"\b(?:private|protected|public)\s+[\w.$<>\[\], ?]+\s+{re.escape(field)}\s*(?:[;=])",
            content,
        )
    )


def _java_method_body(content: str, method: str) -> str | None:
    if not _java_identifier(method):
        return None
    match = re.search(
        rf"\b{re.escape(method)}\s*\([^;{{}}]*\)\s*(?:throws\s+[\w.,\s]+)?\{{",
        content,
    )
    if match is None:
        return None
    opening_index = match.end() - 1
    depth = 0
    for index in range(opening_index, len(content)):
        char = content[index]
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return content[opening_index + 1 : index]
    return None


def _java_method_names(content: str) -> set[str]:
    pattern = re.compile(
        r"\b(?:public|protected|private)?\s*"
        r"(?:static\s+)?(?:default\s+)?"
        r"[\w.$<>\[\], ?]+\s+"
        r"([A-Za-z_$][A-Za-z0-9_$]*)\s*\([^;{}]*\)\s*(?:;|\{)"
    )
    return {match.group(1) for match in pattern.finditer(content)}


def _strip_java_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"//.*", "", text)


def _xml_statement_ids(root: ET.Element) -> set[str]:
    return {
        element.attrib.get("id", "")
        for element in root.iter()
        if element.attrib.get("id")
    }


def _xml_statement_by_id(root: ET.Element, statement_id: str) -> ET.Element | None:
    for element in root.iter():
        if element.attrib.get("id") == statement_id:
            return element
    return None


def _xml_text(element: ET.Element) -> str:
    return " ".join(part.strip() for part in element.itertext() if part.strip())


def _contains_db_operation(sql_text: str) -> bool:
    return bool(
        re.search(
            r"\b(?:SELECT|INSERT|UPDATE|DELETE|MERGE|EXEC(?:UTE)?|CALL)\b",
            _strip_sql_comments(sql_text),
            flags=re.IGNORECASE,
        )
    )


def _strip_sql_comments(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    return re.sub(r"--.*", "", text)


def _calls_original_target_sp(content: str, target_ref: str) -> bool:
    target_tail = _target_tail(target_ref)
    if not target_tail:
        return False
    normalized = _strip_sql_comments(content)
    pattern = re.compile(
        rf"\b(?:EXEC(?:UTE)?|CALL)\s+(?:\[[^\]]+\]\.)?(?:\bdbo\b\.|\[dbo\]\.)?"
        rf"\[?{re.escape(target_tail)}\]?\b",
        flags=re.IGNORECASE,
    )
    return bool(pattern.search(normalized))


def _target_tail(target_ref: str) -> str:
    parts = [part.strip("[] ") for part in str(target_ref or "").split(".") if part.strip()]
    return parts[-1] if parts else ""


def _contains_word(text: str, token: str) -> bool:
    return bool(re.search(rf"\b{re.escape(token)}\b", text))


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _check(
    condition: bool,
    rule_id: str,
    pass_message: str,
    fail_message: str,
    *,
    severity: ValidationSeverity = ValidationSeverity.ERROR,
) -> ValidationCheck:
    return ValidationCheck(
        rule_id=rule_id,
        severity=severity,
        result=ValidationCheckResult.PASS if condition else ValidationCheckResult.FAIL,
        message=pass_message if condition else fail_message,
    )


def _pass(rule_id: str, message: str) -> ValidationCheck:
    return ValidationCheck(
        rule_id=rule_id,
        severity=ValidationSeverity.INFO,
        result=ValidationCheckResult.PASS,
        message=message,
    )


def _fail(
    rule_id: str,
    message: str,
    *,
    severity: ValidationSeverity = ValidationSeverity.ERROR,
) -> ValidationCheck:
    return ValidationCheck(
        rule_id=rule_id,
        severity=severity,
        result=ValidationCheckResult.FAIL,
        message=message,
    )


def _status_from_checks(checks: Sequence[ValidationCheck]) -> ValidationStatus:
    if any(check.result == ValidationCheckResult.FAIL for check in checks):
        return ValidationStatus.FAILED
    return ValidationStatus.PASSED


def _dedupe(items: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        value = str(item).strip()
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
