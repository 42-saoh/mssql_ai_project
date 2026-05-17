from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from pydantic import BaseModel, Field

from ai_agent_analysis.source_map import ProcedureSourceMap, build_procedure_source_map
from ai_agent_domain import (
    CanonicalEvidenceStatus,
    SpStatementContract,
    SpStatementOperation,
)

STATEMENT_EVIDENCE_EXTRACTOR_VERSION = "sp_statement_evidence_extractor@0.1.0"

_PARAM_RE = re.compile(r"@\w+")
_CRUD_BRANCH_RE = re.compile(r"(?i)@CRUDFlag\s*=\s*'(?P<flag>[^']+)'")
_SQL_IDENTIFIER_RE = re.compile(r"(?:\[[^\]]+\]|\w+)(?:\s*\.\s*(?:\[[^\]]+\]|\w+))*")
_AS_ALIAS_RE = re.compile(r"(?i)\bAS\s+(\[[^\]]+\]|\w+)\s*$")
_UPDATE_SET_RE = re.compile(r"(?is)\bSET\b(?P<body>.*?)(?:\bWHERE\b|$)")
_INSERT_COLUMNS_RE = re.compile(
    r"(?is)\bINSERT\s+INTO\s+(?:\[[^\]]+\]|\w+)(?:\s*\.\s*(?:\[[^\]]+\]|\w+))*\s*"
    r"\((?P<body>.*?)\)"
)
_SELECT_COLUMNS_RE = re.compile(r"(?is)\bSELECT\b(?P<body>.*?)(?:\bFROM\b|$)")


class StatementEvidenceExtraction(BaseModel):
    version: str = STATEMENT_EVIDENCE_EXTRACTOR_VERSION
    target_ref: str = Field(alias="targetRef")
    source_map_version: str = Field(alias="sourceMapVersion")
    statement_evidence: list[SpStatementContract] = Field(alias="statementEvidence")
    branch_hints: dict[str, str] = Field(default_factory=dict, alias="branchHints")
    review_markers: list[str] = Field(default_factory=list, alias="reviewMarkers")
    evidence_refs: list[str] = Field(default_factory=list, alias="evidenceRefs")
    production_ready: bool = Field(default=False, alias="productionReady")

    def to_storage_dict(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, mode="json")


def extract_statement_evidence(
    sql_text: str,
    *,
    target_ref: str,
    source_name: str = "<memory>",
    source_map: ProcedureSourceMap | None = None,
) -> StatementEvidenceExtraction:
    source_map = source_map or build_procedure_source_map(sql_text, source_name=source_name)
    lines = sql_text.splitlines()
    branch_hints = _branch_hints(source_map=source_map, lines=lines)
    statements: list[SpStatementContract] = []
    review_markers: list[str] = []

    for span in source_map.spans:
        if span.kind not in {"DML", "RESULT_SET", "CALL", "DYNAMIC_SQL"}:
            continue
        text = _line_range_text(lines, span.start_line, span.end_line)
        operation = _statement_operation(span.kind, text)
        target = _target_ref(span.referenced_objects, span.kind, target_ref)
        cross_database = _is_cross_database(target=target, root_target_ref=target_ref)
        markers = _review_markers(
            operation=operation,
            target=target,
            cross_database=cross_database,
            kind=span.kind,
            risk_tags=span.risk_tags,
            outputs=_output_candidates(operation, text),
        )
        review_markers.extend(markers)
        branch_expression = _nearest_branch_hint(span.start_line, branch_hints)
        inputs = _input_candidates(text, branch_expression)
        statement_id = f"stmt.{operation.value.lower()}.{span.span_id}"
        statements.append(
            SpStatementContract(
                statementId=statement_id,
                operation=operation,
                targetRef=target,
                phase=_phase(operation=operation, branch_expression=branch_expression),
                inputs=inputs,
                outputs=_output_candidates(operation, text),
                writes=_write_candidates(operation, text, target),
                crossDatabase=cross_database,
                reviewMarkers=markers,
                evidenceRefs=list(span.evidence_refs),
                status=(
                    CanonicalEvidenceStatus.REVIEW_REQUIRED
                    if markers
                    else CanonicalEvidenceStatus.OBSERVED
                ),
            )
        )

    return StatementEvidenceExtraction(
        targetRef=target_ref,
        sourceMapVersion=source_map.version,
        statementEvidence=statements,
        branchHints={
            statement.statement_id: _nearest_branch_hint(
                _span_start_line(statement.statement_id, source_map),
                branch_hints,
            )
            for statement in statements
            if _nearest_branch_hint(_span_start_line(statement.statement_id, source_map), branch_hints)
        },
        reviewMarkers=sorted(set(review_markers)),
        evidenceRefs=sorted({ref for statement in statements for ref in statement.evidence_refs}),
        productionReady=False,
    )


def _statement_operation(kind: str, text: str) -> SpStatementOperation:
    normalized = text.upper()
    if kind == "RESULT_SET":
        return SpStatementOperation.SELECT
    if kind in {"CALL", "DYNAMIC_SQL"}:
        return SpStatementOperation.EXECUTE
    for operation in (
        SpStatementOperation.INSERT,
        SpStatementOperation.UPDATE,
        SpStatementOperation.DELETE,
    ):
        if re.search(rf"(?i)\b{operation.value}\b", text):
            return operation
    if "MERGE" in normalized:
        return SpStatementOperation.UPDATE
    return SpStatementOperation.COMPUTE


def _target_ref(referenced_objects: Sequence[str], kind: str, root_target_ref: str) -> str:
    if kind == "DYNAMIC_SQL":
        return "DYNAMIC_SQL.REVIEW_REQUIRED"
    for ref in referenced_objects:
        if ref and ref.upper() not in {"SELECT", "VALUES"}:
            return ref
    if kind == "RESULT_SET":
        return f"{root_target_ref}.RESULT_SET_REVIEW_REQUIRED"
    return f"{root_target_ref}.TARGET_REVIEW_REQUIRED"


def _review_markers(
    *,
    operation: SpStatementOperation,
    target: str,
    cross_database: bool,
    kind: str,
    risk_tags: Sequence[str],
    outputs: Sequence[str],
) -> list[str]:
    markers: list[str] = []
    if target.endswith("TARGET_REVIEW_REQUIRED"):
        markers.append("TARGET_REF_REVIEW_REQUIRED")
    if kind == "DYNAMIC_SQL" or "DYNAMIC_SQL" in risk_tags:
        markers.append("DYNAMIC_SQL_REVIEW_REQUIRED")
    if operation == SpStatementOperation.EXECUTE:
        markers.append("CALLED_PROCEDURE_IO_REVIEW_REQUIRED")
    if operation in {
        SpStatementOperation.INSERT,
        SpStatementOperation.UPDATE,
        SpStatementOperation.DELETE,
    } and cross_database:
        markers.append("CROSS_DB_WRITE_REVIEW_REQUIRED")
    if operation == SpStatementOperation.SELECT and "REVIEW_REQUIRED_RESULT_SHAPE" in outputs:
        markers.append("RESULT_SHAPE_REVIEW_REQUIRED")
    return list(dict.fromkeys(markers))


def _input_candidates(text: str, branch_expression: str | None) -> list[str]:
    candidates = list(_PARAM_RE.findall(text))
    if branch_expression:
        candidates.extend(_PARAM_RE.findall(branch_expression))
    return list(dict.fromkeys(candidates))


def _output_candidates(operation: SpStatementOperation, text: str) -> list[str]:
    if operation != SpStatementOperation.SELECT:
        return []
    match = _SELECT_COLUMNS_RE.search(text)
    if not match:
        return ["REVIEW_REQUIRED_RESULT_SHAPE"]
    candidates = [
        _column_candidate(part)
        for part in _split_csv(match.group("body"))
        if _column_candidate(part)
    ]
    if not candidates or any(candidate == "*" for candidate in candidates):
        return ["REVIEW_REQUIRED_RESULT_SHAPE"]
    return list(dict.fromkeys(candidates))


def _write_candidates(operation: SpStatementOperation, text: str, target: str) -> list[str]:
    if operation == SpStatementOperation.UPDATE:
        match = _UPDATE_SET_RE.search(text)
        if not match:
            return ["REVIEW_REQUIRED_WRITE_COLUMNS"]
        columns = []
        for assignment in _split_csv(match.group("body")):
            lhs = assignment.split("=", 1)[0].strip()
            candidate = _column_candidate(lhs)
            if candidate:
                columns.append(candidate)
        return list(dict.fromkeys(columns)) or ["REVIEW_REQUIRED_WRITE_COLUMNS"]
    if operation == SpStatementOperation.INSERT:
        match = _INSERT_COLUMNS_RE.search(text)
        if not match:
            return ["REVIEW_REQUIRED_INSERT_COLUMNS"]
        return list(
            dict.fromkeys(
                candidate
                for candidate in (_column_candidate(part) for part in _split_csv(match.group("body")))
                if candidate
            )
        ) or ["REVIEW_REQUIRED_INSERT_COLUMNS"]
    if operation == SpStatementOperation.DELETE:
        return [_object_name_leaf(target)]
    return []


def _branch_hints(*, source_map: ProcedureSourceMap, lines: Sequence[str]) -> list[tuple[int, str]]:
    hints: list[tuple[int, str]] = []
    for span in source_map.spans:
        if span.kind != "CONTROL_FLOW":
            continue
        text = _line_range_text(lines, span.start_line, span.end_line)
        match = _CRUD_BRANCH_RE.search(text)
        if not match:
            continue
        flag = match.group("flag")
        hints.append((span.start_line, f"@CRUDFlag = '{flag}'"))
    return hints


def _nearest_branch_hint(start_line: int, hints: Sequence[tuple[int, str]]) -> str | None:
    candidates = [expression for line, expression in hints if line <= start_line]
    return candidates[-1] if candidates else None


def _phase(*, operation: SpStatementOperation, branch_expression: str | None) -> str:
    if not branch_expression:
        return operation.value.lower()
    flag_match = _CRUD_BRANCH_RE.search(branch_expression)
    if not flag_match:
        return operation.value.lower()
    flag = re.sub(r"[^a-z0-9]+", "_", flag_match.group("flag").lower()).strip("_")
    return f"crud_{flag}_{operation.value.lower()}"


def _is_cross_database(*, target: str, root_target_ref: str) -> bool:
    target_parts = target.split(".")
    root_parts = root_target_ref.split(".")
    if len(target_parts) < 3:
        return False
    if len(root_parts) < 3:
        return True
    return target_parts[0].upper() != root_parts[0].upper()


def _column_candidate(value: str) -> str:
    cleaned = value.strip().strip("[]")
    if not cleaned:
        return ""
    alias_match = _AS_ALIAS_RE.search(cleaned)
    if alias_match:
        return alias_match.group(1).strip("[]")
    identifiers = _SQL_IDENTIFIER_RE.findall(cleaned)
    if not identifiers:
        return ""
    candidate = identifiers[-1].split(".")[-1].strip().strip("[]")
    if candidate.upper() in {"NULL", "CASE", "WHEN", "THEN", "ELSE", "END"}:
        return ""
    return candidate


def _object_name_leaf(target: str) -> str:
    return target.split(".")[-1] if target else "REVIEW_REQUIRED_DELETE_TARGET"


def _split_csv(value: str) -> list[str]:
    parts: list[str] = []
    current: list[str] = []
    depth = 0
    for char in value:
        if char == "(":
            depth += 1
        elif char == ")" and depth:
            depth -= 1
        if char == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
            continue
        current.append(char)
    tail = "".join(current).strip()
    if tail:
        parts.append(tail)
    return parts


def _line_range_text(lines: Sequence[str], start_line: int, end_line: int) -> str:
    return "\n".join(lines[max(0, start_line - 1) : min(len(lines), end_line)])


def _span_start_line(statement_id: str, source_map: ProcedureSourceMap) -> int:
    span_id = statement_id.rsplit(".", 1)[-1]
    for span in source_map.spans:
        if span.span_id == span_id:
            return span.start_line
    return 0
