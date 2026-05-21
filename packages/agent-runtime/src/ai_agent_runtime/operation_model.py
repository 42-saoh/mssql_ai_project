from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import ValidationError

from ai_agent_domain import (
    SP_OPERATION_MODEL_SCHEMA_VERSION,
    CanonicalEvidenceStatus,
    SpDtoBlueprintRole,
    SpOperationModel,
    SpStatementOperation,
)

SP_OPERATION_PLANNER_PROMPT_VERSION = "prompt:sp_operation_planner@0.1.0"
SP_OPERATION_PLANNER_OUTPUT_SCHEMA_VERSION = "schema:sp_operation_model@0.1.0"


class OperationModelValidationError(ValueError):
    def __init__(self, findings: Sequence[str]) -> None:
        unique_findings: list[str] = []
        seen: set[str] = set()
        for finding in findings:
            text = str(finding).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            unique_findings.append(text)
        self.findings = tuple(unique_findings)
        message = "; ".join(self.findings) or "SP operation model validation failed."
        super().__init__(message)


class SpOperationModelPlannerOutput(SpOperationModel):
    def to_storage_dict(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, mode="json")


def parse_sp_operation_model_json(
    output_text: str,
    *,
    allowed_evidence_refs: Sequence[str] | None = None,
) -> SpOperationModelPlannerOutput:
    payload = json.loads(output_text)
    if not isinstance(payload, Mapping):
        raise OperationModelValidationError(["Root operation model output must be an object."])
    return validate_sp_operation_model_output(
        payload,
        allowed_evidence_refs=allowed_evidence_refs,
    )


def validate_sp_operation_model_output(
    payload: Mapping[str, Any],
    *,
    allowed_evidence_refs: Sequence[str] | None = None,
) -> SpOperationModelPlannerOutput:
    findings: list[str] = []
    findings.extend(_strict_shape_findings(payload))
    try:
        model = SpOperationModelPlannerOutput.model_validate(payload)
    except ValidationError as exc:
        findings.append(f"schema validation failed: {_safe_validation_error_summary(exc)}")
        raise OperationModelValidationError(findings) from exc

    if model.schema_version != SP_OPERATION_MODEL_SCHEMA_VERSION:
        findings.append(f"schemaVersion must be {SP_OPERATION_MODEL_SCHEMA_VERSION}.")
    if model.contract_target != "SpOperationModel":
        findings.append("contractTarget must be SpOperationModel.")
    if model.source_policy != "sanitized_facts_only":
        findings.append("sourcePolicy must be sanitized_facts_only.")
    if model.production_ready is not False:
        findings.append("productionReady must be false for P41 operation models.")
    if not model.evidence_refs:
        findings.append("root evidenceRefs must not be empty.")
    if not model.operations:
        findings.append("operations must not be empty.")
    if not model.statement_evidence:
        findings.append("statementEvidence must not be empty.")
    if not model.dto_blueprints:
        findings.append("dtoBlueprints must not be empty.")

    statement_ids = {statement.statement_id for statement in model.statement_evidence}
    dto_names = {dto.name for dto in model.dto_blueprints}
    operation_ids = {operation.operation_id for operation in model.operations}

    for operation in model.operations:
        path = f"operations[{operation.operation_id}]"
        if not operation.evidence_refs:
            findings.append(f"{path}.evidenceRefs must not be empty.")
        if not operation.branch_condition.evidence_refs:
            findings.append(f"{path}.branchCondition.evidenceRefs must not be empty.")
        if not operation.statement_refs:
            findings.append(f"{path}.statementRefs must not be empty.")
        if not operation.dto_blueprint_refs:
            findings.append(f"{path}.dtoBlueprintRefs must not be empty.")
        missing_statements = sorted(set(operation.statement_refs) - statement_ids)
        if missing_statements:
            findings.append(f"{path}.statementRefs contains unknown ids: {missing_statements}.")
        missing_dtos = sorted(set(operation.dto_blueprint_refs) - dto_names)
        if missing_dtos:
            findings.append(f"{path}.dtoBlueprintRefs contains unknown DTOs: {missing_dtos}.")

    for statement in model.statement_evidence:
        path = f"statementEvidence[{statement.statement_id}]"
        if not statement.evidence_refs:
            findings.append(f"{path}.evidenceRefs must not be empty.")
        if _looks_like_raw_sql(statement.target_ref):
            findings.append(f"{path}.targetRef must be a sanitized object reference.")
        for value in (*statement.outputs, *statement.writes):
            if _looks_like_raw_sql(value):
                findings.append(f"{path} contains raw SQL-like field candidate {value!r}.")

    for dto in model.dto_blueprints:
        path = f"dtoBlueprints[{dto.name}]"
        if not dto.evidence_refs:
            findings.append(f"{path}.evidenceRefs must not be empty.")
        if not dto.operation_ids:
            findings.append(f"{path}.operationIds must not be empty.")
        missing_operations = sorted(set(dto.operation_ids) - operation_ids)
        if missing_operations:
            findings.append(f"{path}.operationIds contains unknown operations: {missing_operations}.")
        if not dto.fields:
            findings.append(f"{path}.fields must not be empty.")
        for field in dto.fields:
            field_path = f"{path}.fields[{field.name}]"
            if not field.evidence_refs:
                findings.append(f"{field_path}.evidenceRefs must not be empty.")
            if _looks_like_raw_sql(field.source):
                findings.append(f"{field_path}.source must be a sanitized source token.")

    allowed = {str(ref) for ref in (allowed_evidence_refs or ()) if str(ref).strip()}
    if allowed:
        for ref in sorted(set(all_sp_operation_model_evidence_refs(model)) - allowed):
            findings.append(f"evidenceRefs contains unknown ref: {ref}.")

    if findings:
        raise OperationModelValidationError(findings)
    return model


def all_sp_operation_model_evidence_refs(model: SpOperationModel) -> tuple[str, ...]:
    refs: list[str] = []
    refs.extend(model.evidence_refs)
    for operation in model.operations:
        refs.extend(operation.evidence_refs)
        refs.extend(operation.branch_condition.evidence_refs)
    for statement in model.statement_evidence:
        refs.extend(statement.evidence_refs)
    for dto in model.dto_blueprints:
        refs.extend(dto.evidence_refs)
        for field in dto.fields:
            refs.extend(field.evidence_refs)
    return tuple(ref for ref in refs if str(ref).strip())


def _safe_validation_error_summary(exc: ValidationError) -> str:
    items: list[str] = []
    for error in exc.errors(include_input=False)[:12]:
        loc = ".".join(str(part) for part in error.get("loc", ()) if str(part))
        error_type = str(error.get("type") or "validation_error")
        message = " ".join(str(error.get("msg") or "").split())
        if loc:
            items.append(f"{loc}:{error_type}:{message}"[:240])
        else:
            items.append(f"{error_type}:{message}"[:240])
    if len(exc.errors(include_input=False)) > len(items):
        items.append(f"... {len(exc.errors(include_input=False)) - len(items)} more")
    return "; ".join(items) or "schema validation failed"


def sp_operation_model_output_schema(
    allowed_evidence_refs: Sequence[str] | None = None,
) -> dict[str, Any]:
    evidence_ref_array = _evidence_ref_array_schema(allowed_evidence_refs)
    status_schema = {
        "type": "string",
        "enum": [status.value for status in CanonicalEvidenceStatus],
    }
    return {
        "type": "object",
        "properties": {
            "schemaVersion": {"type": "string", "const": SP_OPERATION_MODEL_SCHEMA_VERSION},
            "contractTarget": {"type": "string", "const": "SpOperationModel"},
            "targetRef": {"type": "string", "minLength": 1},
            "sourcePolicy": {"type": "string", "const": "sanitized_facts_only"},
            "productionReady": {"type": "boolean", "const": False},
            "operations": {
                "type": "array",
                "minItems": 1,
                "items": _operation_contract_schema(evidence_ref_array, status_schema),
            },
            "statementEvidence": {
                "type": "array",
                "minItems": 1,
                "items": _statement_contract_schema(evidence_ref_array, status_schema),
            },
            "dtoBlueprints": {
                "type": "array",
                "minItems": 1,
                "items": _dto_blueprint_schema(evidence_ref_array),
            },
            "reviewMarkers": {"type": "array", "items": {"type": "string"}},
            "evidenceRefs": evidence_ref_array,
            "assumptions": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "schemaVersion",
            "contractTarget",
            "targetRef",
            "sourcePolicy",
            "productionReady",
            "operations",
            "statementEvidence",
            "dtoBlueprints",
            "reviewMarkers",
            "evidenceRefs",
            "assumptions",
        ],
        "additionalProperties": False,
    }


def _operation_contract_schema(
    evidence_ref_array: Mapping[str, Any],
    status_schema: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "operationId": {"type": "string", "minLength": 1},
            "crudFlag": {"type": "string", "minLength": 1},
            "title": {"type": "string", "minLength": 1},
            "summary": {"type": "string", "minLength": 1},
            "branchCondition": {
                "type": "object",
                "properties": {
                    "expression": {"type": "string", "minLength": 1},
                    "variables": {"type": "array", "items": {"type": "string"}},
                    "evidenceRefs": evidence_ref_array,
                    "status": status_schema,
                },
                "required": ["expression", "variables", "evidenceRefs", "status"],
                "additionalProperties": False,
            },
            "statementRefs": {
                "type": "array",
                "minItems": 1,
                "items": {"type": "string", "minLength": 1},
            },
            "dtoBlueprintRefs": {
                "type": "array",
                "minItems": 1,
                "items": {"type": "string", "minLength": 1},
            },
            "stateTransitions": {"type": "array", "items": {"type": "string"}},
            "riskMarkers": {"type": "array", "items": {"type": "string"}},
            "evidenceRefs": evidence_ref_array,
            "status": status_schema,
        },
        "required": [
            "operationId",
            "crudFlag",
            "title",
            "summary",
            "branchCondition",
            "statementRefs",
            "dtoBlueprintRefs",
            "stateTransitions",
            "riskMarkers",
            "evidenceRefs",
            "status",
        ],
        "additionalProperties": False,
    }


def _statement_contract_schema(
    evidence_ref_array: Mapping[str, Any],
    status_schema: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "statementId": {"type": "string", "minLength": 1},
            "operation": {
                "type": "string",
                "enum": [operation.value for operation in SpStatementOperation],
            },
            "targetRef": {"type": "string", "minLength": 1},
            "phase": {"type": "string", "minLength": 1},
            "inputs": {"type": "array", "items": {"type": "string"}},
            "outputs": {"type": "array", "items": {"type": "string"}},
            "writes": {"type": "array", "items": {"type": "string"}},
            "crossDatabase": {"type": "boolean"},
            "reviewMarkers": {"type": "array", "items": {"type": "string"}},
            "evidenceRefs": evidence_ref_array,
            "status": status_schema,
        },
        "required": [
            "statementId",
            "operation",
            "targetRef",
            "phase",
            "inputs",
            "outputs",
            "writes",
            "crossDatabase",
            "reviewMarkers",
            "evidenceRefs",
            "status",
        ],
        "additionalProperties": False,
    }


def _dto_blueprint_schema(evidence_ref_array: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "name": {"type": "string", "minLength": 1},
            "role": {"type": "string", "enum": [role.value for role in SpDtoBlueprintRole]},
            "operationIds": {
                "type": "array",
                "minItems": 1,
                "items": {"type": "string", "minLength": 1},
            },
            "fields": {
                "type": "array",
                "minItems": 1,
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "minLength": 1},
                        "dbType": {"type": "string", "minLength": 1},
                        "source": {"type": "string", "minLength": 1},
                        "required": {"type": "boolean"},
                        "evidenceRefs": evidence_ref_array,
                    },
                    "required": ["name", "dbType", "source", "required", "evidenceRefs"],
                    "additionalProperties": False,
                },
            },
            "evidenceRefs": evidence_ref_array,
            "reviewMarkers": {"type": "array", "items": {"type": "string"}},
        },
        "required": [
            "name",
            "role",
            "operationIds",
            "fields",
            "evidenceRefs",
            "reviewMarkers",
        ],
        "additionalProperties": False,
    }


def _evidence_ref_array_schema(allowed_evidence_refs: Sequence[str] | None) -> dict[str, Any]:
    item_schema: dict[str, Any] = {"type": "string", "minLength": 1}
    allowed_refs = sorted({str(ref) for ref in (allowed_evidence_refs or ()) if str(ref).strip()})
    if allowed_refs:
        item_schema["enum"] = allowed_refs
    return {"type": "array", "items": item_schema, "minItems": 1}


def _strict_shape_findings(payload: Mapping[str, Any]) -> list[str]:
    findings: list[str] = []
    root_keys = {
        "schemaVersion",
        "contractTarget",
        "targetRef",
        "sourcePolicy",
        "productionReady",
        "operations",
        "statementEvidence",
        "dtoBlueprints",
        "reviewMarkers",
        "evidenceRefs",
        "assumptions",
    }
    findings.extend(_unexpected_keys("$.operationModel", payload, root_keys))
    for key, label in (
        ("operations", "operations"),
        ("statementEvidence", "statementEvidence"),
        ("dtoBlueprints", "dtoBlueprints"),
        ("evidenceRefs", "root evidenceRefs"),
    ):
        value = payload.get(key)
        if isinstance(value, Sequence) and not isinstance(value, (str, bytes)) and len(value) == 0:
            findings.append(f"{label} must not be empty.")
    _check_sequence_items(
        findings,
        payload.get("operations"),
        "$.operations",
        {
            "operationId",
            "crudFlag",
            "title",
            "summary",
            "branchCondition",
            "statementRefs",
            "dtoBlueprintRefs",
            "stateTransitions",
            "riskMarkers",
            "evidenceRefs",
            "status",
        },
    )
    _check_sequence_items(
        findings,
        payload.get("statementEvidence"),
        "$.statementEvidence",
        {
            "statementId",
            "operation",
            "targetRef",
            "phase",
            "inputs",
            "outputs",
            "writes",
            "crossDatabase",
            "reviewMarkers",
            "evidenceRefs",
            "status",
        },
    )
    _check_sequence_items(
        findings,
        payload.get("dtoBlueprints"),
        "$.dtoBlueprints",
        {"name", "role", "operationIds", "fields", "evidenceRefs", "reviewMarkers"},
    )
    return findings


def _check_sequence_items(
    findings: list[str],
    value: Any,
    path: str,
    allowed_keys: set[str],
) -> None:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
        return
    for index, item in enumerate(value):
        if isinstance(item, Mapping):
            findings.extend(_unexpected_keys(f"{path}[{index}]", item, allowed_keys))
            if path == "$.operations" and isinstance(item.get("branchCondition"), Mapping):
                findings.extend(
                    _unexpected_keys(
                        f"{path}[{index}].branchCondition",
                        item["branchCondition"],
                        {"expression", "variables", "evidenceRefs", "status"},
                    )
                )
            if path == "$.dtoBlueprints":
                fields = item.get("fields")
                if isinstance(fields, Sequence) and not isinstance(fields, (str, bytes)):
                    for field_index, field in enumerate(fields):
                        if isinstance(field, Mapping):
                            findings.extend(
                                _unexpected_keys(
                                    f"{path}[{index}].fields[{field_index}]",
                                    field,
                                    {"name", "dbType", "source", "required", "evidenceRefs"},
                                )
                            )


def _unexpected_keys(path: str, value: Mapping[str, Any], allowed_keys: set[str]) -> list[str]:
    return [f"{path} contains unsupported key {key!r}." for key in sorted(set(value) - allowed_keys)]


def _looks_like_raw_sql(value: str) -> bool:
    normalized = str(value).strip().upper()
    if not normalized:
        return True
    if "\n" in normalized or ";" in normalized:
        return True
    raw_markers = (
        "SELECT ",
        "UPDATE ",
        "INSERT ",
        "DELETE ",
        "CREATE PROCEDURE",
        "ALTER PROCEDURE",
        " FROM ",
        " WHERE ",
    )
    return any(marker in f" {normalized} " for marker in raw_markers)
