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
    QUALIFIED_IDENTIFIER_PATTERN,
    QUALIFIED_VARIABLE_OR_IDENTIFIER_PATTERN,
    make_evidence,
    mask_comments_and_literals,
    parse_identifier,
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
SYSTEM_DYNAMIC_EXECUTORS = {"sp_executesql"}


def extract_dependencies(sql_text: str, *, source_name: str = "<memory>") -> DependencySummary:
    return DependencySummary(
        table_references=extract_table_references(sql_text, source_name=source_name),
        called_procedures=extract_procedure_calls(sql_text, source_name=source_name),
        temp_tables=detect_temp_tables(sql_text, source_name=source_name),
    )


def extract_table_references(
    sql_text: str,
    *,
    source_name: str = "<memory>",
) -> list[ObjectReference]:
    sanitized = mask_comments_and_literals(sql_text)
    references: list[ObjectReference] = []
    seen: set[tuple[str, DependencyOperation, ObjectType]] = set()
    for operation, pattern in TABLE_REFERENCE_PATTERNS:
        for match in pattern.finditer(sanitized):
            target = match.group("target")
            identifier = parse_identifier(target)
            if not identifier.object_name or _is_keyword(identifier.object_name):
                continue
            object_type = (
                ObjectType.TEMP_TABLE
                if identifier.object_name.startswith("#")
                else ObjectType.TABLE
            )
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
                    evidence=[make_evidence(sql_text, match.start("target"), source_name)],
                )
            )
    return references


def extract_procedure_calls(sql_text: str, *, source_name: str = "<memory>") -> list[ProcedureCall]:
    sanitized = mask_comments_and_literals(sql_text)
    calls: list[ProcedureCall] = []
    seen: set[str] = set()
    for match in EXEC_RE.finditer(sanitized):
        target = match.group("target")
        identifier = parse_identifier(target)
        if not identifier.object_name:
            continue
        object_name_lower = identifier.object_name.lower()
        is_variable_exec = identifier.object_name.startswith("@")
        is_dynamic_executor = object_name_lower in SYSTEM_DYNAMIC_EXECUTORS or is_variable_exec
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
                    "Dynamic SQL executor; inner object dependencies require manual review."
                ]
                if is_dynamic_executor
                else [],
            )
        )
    return calls


def _is_keyword(token: str) -> bool:
    return token.upper() in {
        "SELECT",
        "VALUES",
        "OPENQUERY",
        "OPENROWSET",
        "TRANSACTION",
        "TRAN",
    }
