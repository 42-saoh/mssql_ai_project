from __future__ import annotations

import re

from ai_agent_analysis.detectors import detect_temp_tables
from ai_agent_analysis.models import (
    DependencyOperation,
    DependencySummary,
    EvidenceStatus,
    ObjectReference,
    ObjectType,
    ProcedureCall,
)
from ai_agent_analysis.sql_utils import (
    IDENTIFIER_PATTERN,
    QUALIFIED_IDENTIFIER_PATTERN,
    QUALIFIED_VARIABLE_OR_IDENTIFIER_PATTERN,
    make_evidence,
    mask_comments_and_literals,
    parse_identifier,
    scan_static_sql,
)


TABLE_REFERENCE_PATTERNS: tuple[tuple[DependencyOperation, re.Pattern[str]], ...] = (
    (
        DependencyOperation.READ,
        re.compile(rf"\b(?:FROM|JOIN)\s+(?P<target>{QUALIFIED_IDENTIFIER_PATTERN})", re.IGNORECASE),
    ),
    (
        DependencyOperation.WRITE,
        re.compile(
            rf"\bINSERT\s+(?:INTO\s+)?(?P<target>{QUALIFIED_IDENTIFIER_PATTERN})",
            re.IGNORECASE,
        ),
    ),
    (
        DependencyOperation.WRITE,
        re.compile(rf"\bUPDATE\s+(?P<target>{QUALIFIED_IDENTIFIER_PATTERN})", re.IGNORECASE),
    ),
    (
        DependencyOperation.WRITE,
        re.compile(
            rf"\bDELETE\s+FROM\s+(?P<target>{QUALIFIED_IDENTIFIER_PATTERN})",
            re.IGNORECASE,
        ),
    ),
    (
        DependencyOperation.WRITE,
        re.compile(
            rf"\bMERGE\s+(?:INTO\s+)?(?P<target>{QUALIFIED_IDENTIFIER_PATTERN})",
            re.IGNORECASE,
        ),
    ),
    (
        DependencyOperation.DECLARE,
        re.compile(
            rf"\bCREATE\s+TABLE\s+(?P<target>{QUALIFIED_IDENTIFIER_PATTERN})",
            re.IGNORECASE,
        ),
    ),
)

EXEC_RE = re.compile(
    rf"\bEXEC(?:UTE)?\s+(?P<target>{QUALIFIED_VARIABLE_OR_IDENTIFIER_PATTERN})",
    re.IGNORECASE,
)
EXEC_PAREN_RE = re.compile(
    rf"\bEXEC(?:UTE)?\s*\(\s*(?P<target>{QUALIFIED_VARIABLE_OR_IDENTIFIER_PATTERN})\s*\)",
    re.IGNORECASE,
)
FUNCTION_CALL_RE = re.compile(
    rf"(?P<target>{IDENTIFIER_PATTERN}\s*\.\s*{IDENTIFIER_PATTERN})\s*\(",
    re.IGNORECASE,
)
CURSOR_FETCH_CONTEXT_RE = re.compile(
    r"\bFETCH\s+(?:NEXT|PRIOR|FIRST|LAST|ABSOLUTE|RELATIVE)?\s*FROM\s*$",
    re.IGNORECASE | re.DOTALL,
)
DML_TARGET_FUNCTION_FALSE_POSITIVE_RE = re.compile(
    r"\b(?:INSERT\s+(?:INTO\s+)?|UPDATE|MERGE\s+(?:INTO\s+)?)$",
    re.IGNORECASE | re.DOTALL,
)
SYSTEM_DYNAMIC_EXECUTORS = {"sp_executesql"}


def extract_dependencies(sql_text: str, *, source_name: str = "<memory>") -> DependencySummary:
    relation_references = extract_table_references(sql_text, source_name=source_name)
    return DependencySummary(
        table_references=[
            reference
            for reference in relation_references
            if reference.object_type in {ObjectType.TABLE, ObjectType.TEMP_TABLE}
        ],
        view_references=[
            reference
            for reference in relation_references
            if reference.object_type == ObjectType.VIEW
        ],
        function_references=extract_function_references(sql_text, source_name=source_name),
        called_procedures=extract_procedure_calls(sql_text, source_name=source_name),
        temp_tables=detect_temp_tables(sql_text, source_name=source_name),
    )


def extract_table_references(
    sql_text: str,
    *,
    source_name: str = "<memory>",
) -> list[ObjectReference]:
    sanitized = mask_comments_and_literals(sql_text)
    scan = scan_static_sql(sql_text)
    references: list[ObjectReference] = []
    seen: set[tuple[str, DependencyOperation, ObjectType]] = set()
    for operation, pattern in TABLE_REFERENCE_PATTERNS:
        for match in pattern.finditer(sanitized):
            target = match.group("target")
            if operation == DependencyOperation.READ and _is_cursor_fetch_target(
                sanitized,
                match.start("target"),
            ):
                continue
            identifier = parse_identifier(target)
            if not identifier.object_name or _is_keyword(identifier.object_name):
                continue
            if scan.is_cte_reference(identifier, match.start("target")):
                continue
            object_type, status = _classify_relation_reference(identifier.object_name)
            key = (identifier.full_name.upper(), operation, object_type)
            if key in seen:
                continue
            seen.add(key)
            references.append(
                ObjectReference(
                    schema_name=identifier.schema_name,
                    object_name=identifier.object_name,
                    full_name=identifier.full_name,
                    object_type=object_type,
                    operation=operation,
                    status=status,
                    evidence=[
                        make_evidence(
                            sql_text,
                            match.start("target"),
                            source_name,
                            status=status,
                        )
                    ],
                )
            )
    return references


def extract_procedure_calls(sql_text: str, *, source_name: str = "<memory>") -> list[ProcedureCall]:
    sanitized = mask_comments_and_literals(sql_text)
    calls: list[ProcedureCall] = []
    seen: set[str] = set()
    exec_matches = [
        *[(match, False) for match in EXEC_RE.finditer(sanitized)],
        *[(match, True) for match in EXEC_PAREN_RE.finditer(sanitized)],
    ]
    for match, force_dynamic_review in sorted(exec_matches, key=lambda item: item[0].start()):
        target = match.group("target")
        identifier = parse_identifier(target)
        if not identifier.object_name:
            continue
        object_name_lower = identifier.object_name.lower()
        is_variable_exec = identifier.object_name.startswith("@")
        is_dynamic_executor = (
            object_name_lower in SYSTEM_DYNAMIC_EXECUTORS
            or is_variable_exec
            or force_dynamic_review
        )
        status = EvidenceStatus.REVIEW_REQUIRED if is_dynamic_executor else EvidenceStatus.OBSERVED
        object_type = (
            ObjectType.SYSTEM_PROCEDURE
            if object_name_lower in SYSTEM_DYNAMIC_EXECUTORS
            else ObjectType.PROCEDURE
        )
        key = identifier.full_name.upper()
        if key in seen:
            continue
        seen.add(key)
        calls.append(
            ProcedureCall(
                schema_name=identifier.schema_name,
                procedure_name=identifier.object_name,
                full_name=identifier.full_name,
                object_type=object_type,
                is_dynamic_sql_executor=is_dynamic_executor,
                status=status,
                evidence=[
                    make_evidence(
                        sql_text,
                        match.start("target"),
                        source_name,
                        status=status,
                    )
                ],
                review_notes=[
                    "Dynamic SQL executor입니다. 내부 객체 의존성은 수동 검토가 필요합니다."
                ]
                if is_dynamic_executor
                else [],
            )
        )
    return calls


def extract_function_references(
    sql_text: str,
    *,
    source_name: str = "<memory>",
) -> list[ObjectReference]:
    sanitized = mask_comments_and_literals(sql_text)
    references: list[ObjectReference] = []
    seen: set[str] = set()
    for match in FUNCTION_CALL_RE.finditer(sanitized):
        if _is_dml_target_false_positive(sanitized, match.start("target")):
            continue
        identifier = parse_identifier(match.group("target"))
        if not identifier.schema_name or not identifier.object_name:
            continue
        if identifier.object_name.lower() in SYSTEM_DYNAMIC_EXECUTORS:
            continue
        key = identifier.full_name.upper()
        if key in seen:
            continue
        seen.add(key)
        references.append(
            ObjectReference(
                schema_name=identifier.schema_name,
                object_name=identifier.object_name,
                full_name=identifier.full_name,
                object_type=ObjectType.FUNCTION,
                operation=DependencyOperation.EXECUTE,
                evidence=[make_evidence(sql_text, match.start("target"), source_name)],
            )
        )
    return references


def _is_keyword(token: str) -> bool:
    return token.upper() in {
        "SELECT",
        "VALUES",
        "OPENQUERY",
        "OPENROWSET",
        "TRANSACTION",
        "TRAN",
    }


def _classify_relation_reference(object_name: str) -> tuple[ObjectType, EvidenceStatus]:
    if object_name.startswith("#"):
        return ObjectType.TEMP_TABLE, EvidenceStatus.OBSERVED
    upper_name = object_name.upper()
    if upper_name.startswith("VW_") or upper_name.endswith("_V"):
        return ObjectType.VIEW, EvidenceStatus.REVIEW_REQUIRED
    return ObjectType.TABLE, EvidenceStatus.OBSERVED


def _is_cursor_fetch_target(sanitized_sql: str, target_start: int) -> bool:
    statement_prefix = sanitized_sql[
        max(0, sanitized_sql.rfind(";", 0, target_start)) : target_start
    ]
    return bool(CURSOR_FETCH_CONTEXT_RE.search(statement_prefix))


def _is_dml_target_false_positive(sanitized_sql: str, target_start: int) -> bool:
    statement_prefix = sanitized_sql[
        max(0, sanitized_sql.rfind(";", 0, target_start)) : target_start
    ]
    return bool(DML_TARGET_FUNCTION_FALSE_POSITIVE_RE.search(statement_prefix))
