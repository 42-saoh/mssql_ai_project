from __future__ import annotations

import re

from ai_agent_analysis.models import (
    DependencyOperation,
    EvidenceStatus,
    PatternFinding,
    PatternSummary,
    TempTableFinding,
)
from ai_agent_analysis.sql_utils import (
    is_client_result_select,
    make_evidence,
    mask_comments_and_literals,
    scan_static_sql,
    split_top_level_csv,
)


TRANSACTION_RE = re.compile(
    r"\b(?:BEGIN|COMMIT|ROLLBACK)\s+(?:TRAN|TRANSACTION)\b|\b@@TRANCOUNT\b",
    re.IGNORECASE,
)
TRY_RE = re.compile(r"\bBEGIN\s+TRY\b", re.IGNORECASE)
CATCH_RE = re.compile(r"\bBEGIN\s+CATCH\b", re.IGNORECASE)
DYNAMIC_SQL_RE = re.compile(
    r"\bsp_executesql\b|\bEXEC(?:UTE)?\s*\(|\bEXEC(?:UTE)?\s+@[A-Za-z_][A-Za-z0-9_]*\b",
    re.IGNORECASE,
)
CREATE_TEMP_TABLE_RE = re.compile(
    r"\bCREATE\s+TABLE\s+(?P<name>#[A-Za-z_][A-Za-z0-9_]*)\s*\((?P<columns>.*?)\)",
    re.IGNORECASE | re.DOTALL,
)
SELECT_INTO_TEMP_RE = re.compile(
    r"\bINTO\s+(?P<name>#[A-Za-z_][A-Za-z0-9_]*)\b",
    re.IGNORECASE,
)
CURSOR_RE = re.compile(
    r"\bDECLARE\s+[A-Za-z_][A-Za-z0-9_]*\s+CURSOR\b"
    r"|\b(?:OPEN|CLOSE|DEALLOCATE)\s+[A-Za-z_][A-Za-z0-9_]*\b"
    r"|\bFETCH\s+(?:NEXT|PRIOR|FIRST|LAST|ABSOLUTE|RELATIVE)?\s*FROM\b",
    re.IGNORECASE,
)
SELECT_RE = re.compile(r"\bSELECT\b", re.IGNORECASE)


def detect_patterns(sql_text: str, *, source_name: str = "<memory>") -> PatternSummary:
    sanitized = mask_comments_and_literals(sql_text)
    scan = scan_static_sql(sql_text)
    transaction_evidence = [
        make_evidence(sql_text, match.start(), source_name)
        for match in TRANSACTION_RE.finditer(sanitized)
    ]
    try_evidence = [
        make_evidence(sql_text, match.start(), source_name)
        for match in TRY_RE.finditer(sanitized)
    ]
    catch_evidence = [
        make_evidence(sql_text, match.start(), source_name)
        for match in CATCH_RE.finditer(sanitized)
    ]
    dynamic_evidence = [
        make_evidence(sql_text, match.start(), source_name, status=EvidenceStatus.REVIEW_REQUIRED)
        for match in DYNAMIC_SQL_RE.finditer(sanitized)
    ]
    temp_tables = detect_temp_tables(sql_text, source_name=source_name)
    cursor_evidence = [
        make_evidence(sql_text, match.start(), source_name)
        for match in CURSOR_RE.finditer(sanitized)
    ]
    result_select_evidence = [
        make_evidence(sql_text, match.start(), source_name)
        for match in SELECT_RE.finditer(sanitized)
        if is_client_result_select(sanitized, match.start(), scan=scan)
    ]
    return PatternSummary(
        transaction=PatternFinding(
            name="TRANSACTION",
            detected=bool(transaction_evidence),
            evidence=transaction_evidence,
            details={"signal_count": len(transaction_evidence)},
        ),
        try_catch=PatternFinding(
            name="TRY_CATCH",
            detected=bool(try_evidence and catch_evidence),
            evidence=[*try_evidence, *catch_evidence],
            details={
                "has_begin_try": bool(try_evidence),
                "has_begin_catch": bool(catch_evidence),
            },
        ),
        dynamic_sql=PatternFinding(
            name="DYNAMIC_SQL",
            detected=bool(dynamic_evidence),
            status=EvidenceStatus.REVIEW_REQUIRED if dynamic_evidence else EvidenceStatus.OBSERVED,
            evidence=dynamic_evidence,
            details={
                "review_reason": "Dynamic SQL text에는 미확정 의존성이 포함될 수 있습니다."
                if dynamic_evidence
                else None
            },
        ),
        temp_table=PatternFinding(
            name="TEMP_TABLE",
            detected=bool(temp_tables),
            evidence=[evidence for table in temp_tables for evidence in table.evidence],
            details={"temp_table_names": [table.name for table in temp_tables]},
        ),
        cursor=PatternFinding(
            name="CURSOR",
            detected=bool(cursor_evidence),
            evidence=cursor_evidence,
            details={"signal_count": len(cursor_evidence)},
        ),
        multi_result_set=PatternFinding(
            name="MULTI_RESULT_SET",
            detected=len(result_select_evidence) > 1,
            status=(
                EvidenceStatus.REVIEW_REQUIRED
                if len(result_select_evidence) > 1
                else EvidenceStatus.OBSERVED
            ),
            evidence=result_select_evidence,
            details={"result_select_count": len(result_select_evidence)},
        ),
    )


def detect_temp_tables(sql_text: str, *, source_name: str = "<memory>") -> list[TempTableFinding]:
    sanitized = mask_comments_and_literals(sql_text)
    findings: list[TempTableFinding] = []
    seen: set[str] = set()
    for match in CREATE_TEMP_TABLE_RE.finditer(sanitized):
        name = match.group("name")
        seen.add(name.upper())
        findings.append(
            TempTableFinding(
                name=name,
                columns=_extract_column_names(match.group("columns")),
                evidence=[make_evidence(sql_text, match.start("name"), source_name)],
            )
        )
    for match in SELECT_INTO_TEMP_RE.finditer(sanitized):
        name = match.group("name")
        if name.upper() in seen:
            continue
        seen.add(name.upper())
        findings.append(
            TempTableFinding(
                name=name,
                operation=DependencyOperation.WRITE,
                evidence=[make_evidence(sql_text, match.start("name"), source_name)],
            )
        )
    return findings


def _extract_column_names(columns_block: str) -> list[str]:
    columns: list[str] = []
    for part in split_top_level_csv(columns_block):
        token = part.strip().split(maxsplit=1)[0] if part.strip() else ""
        if not token:
            continue
        if token.startswith("[") and token.endswith("]"):
            token = token[1:-1]
        if token.upper() in {"CONSTRAINT", "PRIMARY", "FOREIGN", "CHECK", "UNIQUE"}:
            continue
        columns.append(token)
    return columns
