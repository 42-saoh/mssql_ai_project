from __future__ import annotations

import re
from typing import Any

from ai_agent_analysis.sql_utils import (
    IDENTIFIER_PATTERN,
    mask_comments_and_literals,
    normalize_identifier_token,
    scan_static_sql,
)

QUALIFIED_ANY_IDENTIFIER_PATTERN = (
    rf"{IDENTIFIER_PATTERN}(?:\s*\.\s*{IDENTIFIER_PATTERN}){{0,3}}"
)

_DML_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "SELECT",
        re.compile(
            rf"\b(?:FROM|JOIN)\s+(?P<target>{QUALIFIED_ANY_IDENTIFIER_PATTERN})",
            re.IGNORECASE,
        ),
    ),
    (
        "INSERT",
        re.compile(
            rf"\bINSERT\s+(?:INTO\s+)?(?P<target>{QUALIFIED_ANY_IDENTIFIER_PATTERN})",
            re.IGNORECASE,
        ),
    ),
    (
        "UPDATE",
        re.compile(
            rf"\bUPDATE\s+(?P<target>{QUALIFIED_ANY_IDENTIFIER_PATTERN})",
            re.IGNORECASE,
        ),
    ),
    (
        "DELETE",
        re.compile(
            rf"\bDELETE\s+FROM\s+(?P<target>{QUALIFIED_ANY_IDENTIFIER_PATTERN})",
            re.IGNORECASE,
        ),
    ),
    (
        "MERGE",
        re.compile(
            rf"\bMERGE\s+(?:INTO\s+)?(?P<target>{QUALIFIED_ANY_IDENTIFIER_PATTERN})",
            re.IGNORECASE,
        ),
    ),
)
_CROSS_DB_RE = re.compile(
    rf"(?P<target>{IDENTIFIER_PATTERN}\s*\.\s*{IDENTIFIER_PATTERN}\s*\.\s*"
    rf"{IDENTIFIER_PATTERN}(?:\s*\.\s*{IDENTIFIER_PATTERN})?)",
    re.IGNORECASE,
)
_COUNT_PATTERNS: tuple[tuple[str, re.Pattern[str], str], ...] = (
    ("LOC", re.compile(r".+"), "Non-empty source lines after trimming whitespace."),
    (
        "BEGIN_END_BLOCK",
        re.compile(r"\bBEGIN\b", re.IGNORECASE),
        "Minimum of BEGIN and END tokens.",
    ),
    (
        "DECLARE_VARIABLE",
        re.compile(r"\bDECLARE\s+@[A-Za-z_][A-Za-z0-9_]*\b", re.IGNORECASE),
        "DECLARE @variable token count.",
    ),
    ("IF", re.compile(r"\bIF\b", re.IGNORECASE), "IF keyword count."),
    ("ELSE", re.compile(r"\bELSE\b", re.IGNORECASE), "ELSE keyword count."),
    ("WHILE", re.compile(r"\bWHILE\b", re.IGNORECASE), "WHILE keyword count."),
    ("CASE", re.compile(r"\bCASE\b", re.IGNORECASE), "CASE keyword count."),
    ("GOTO", re.compile(r"\bGOTO\b", re.IGNORECASE), "GOTO keyword count."),
    ("RETURN", re.compile(r"\bRETURN\b", re.IGNORECASE), "RETURN keyword count."),
    (
        "CURSOR_SIGNAL",
        re.compile(
            r"\bDECLARE\s+[A-Za-z_][A-Za-z0-9_]*\s+CURSOR\b"
            r"|\b(?:OPEN|FETCH|CLOSE|DEALLOCATE)\b",
            re.IGNORECASE,
        ),
        "DECLARE CURSOR / OPEN / FETCH / CLOSE / DEALLOCATE signal count.",
    ),
    (
        "TRY_CATCH_BLOCK",
        re.compile(r"\bBEGIN\s+(?:TRY|CATCH)\b", re.IGNORECASE),
        "BEGIN TRY/CATCH token count.",
    ),
    (
        "TRANSACTION_SIGNAL",
        re.compile(
            r"\b(?:BEGIN|COMMIT|ROLLBACK)\s+(?:TRAN|TRANSACTION)\b|\b@@TRANCOUNT\b",
            re.IGNORECASE,
        ),
        "Transaction control or @@TRANCOUNT signal count.",
    ),
    (
        "DYNAMIC_SQL_SIGNAL",
        re.compile(
            r"\bsp_executesql\b|\bEXEC(?:UTE)?\s*\(|\bEXEC(?:UTE)?\s+@[A-Za-z_][A-Za-z0-9_]*\b",
            re.IGNORECASE,
        ),
        "sp_executesql, EXEC(...), or EXEC @variable signal count.",
    ),
)
_KEYWORDS = {
    "SELECT",
    "VALUES",
    "OPENQUERY",
    "OPENROWSET",
    "TRANSACTION",
    "TRAN",
    "SET",
}
_BRANCH_PARAM_PATTERN = r"@[A-Za-z_][A-Za-z0-9_]*(?:Flag|Code)"
_BRANCH_EQ_RE = re.compile(
    rf"(?P<param>{_BRANCH_PARAM_PATTERN})\s*(?P<operator>=|<>|!=)\s*N?'(?P<value>[^']{{1,80}})'",
    re.IGNORECASE,
)
_BRANCH_IN_RE = re.compile(
    rf"(?P<param>{_BRANCH_PARAM_PATTERN})\s+IN\s*\((?P<values>[^)]{{1,500}})\)",
    re.IGNORECASE,
)
_SQL_LITERAL_RE = re.compile(r"N?'(?P<value>[^']{1,80})'", re.IGNORECASE)
_SAFE_BRANCH_VALUE_RE = re.compile(r"^[0-9A-Za-z_:-]{1,80}$")


def migration_guide_static_metrics(
    sql_text: str,
    *,
    source_name: str = "<memory>",
) -> dict[str, Any]:
    """Return sanitized static facts for migration-guide rendering."""
    sanitized = mask_comments_and_literals(sql_text)
    return {
        "sourceName": source_name,
        "dmlOperations": extract_dml_operations(sql_text, source_name=source_name),
        "branchPredicates": extract_branch_predicates(sql_text, source_name=source_name),
        "complexityMetrics": complexity_metrics(sql_text),
        "crossDatabaseReferences": _cross_database_references(sanitized),
    }


def extract_branch_predicates(
    sql_text: str,
    *,
    source_name: str = "<memory>",
) -> list[dict[str, Any]]:
    """Return sanitized @*Flag/@*Code branch predicates observed in SQL text."""
    branch_sql = _strip_sql_comments_preserve_literals(sql_text)
    predicates: dict[tuple[str, str, tuple[str, ...]], dict[str, Any]] = {}
    for pattern, operator in ((_BRANCH_EQ_RE, ""), (_BRANCH_IN_RE, "IN")):
        for match in pattern.finditer(branch_sql):
            parameter = _normalize_parameter(match.group("param"))
            values = (
                [_sanitize_branch_value(match.group("value"))]
                if "value" in match.groupdict()
                else [
                    _sanitize_branch_value(value.group("value"))
                    for value in _SQL_LITERAL_RE.finditer(match.group("values"))
                ][:8]
            )
            values = [value for value in values if value]
            if not parameter or not values:
                continue
            effective_operator = operator or match.groupdict().get("operator") or "="
            line = sql_text.count("\n", 0, max(match.start("param"), 0)) + 1
            key = (parameter.upper(), str(effective_operator).upper(), tuple(values))
            predicates.setdefault(
                key,
                {
                    "parameter": parameter,
                    "operator": str(effective_operator).upper(),
                    "values": values,
                    "line": line,
                    "sourceName": source_name,
                    "evidenceRef": (
                        "static.branch."
                        f"{_safe_ref_token(parameter.lstrip('@'))}."
                        f"{_safe_ref_token('_'.join(values))}"
                    ),
                    "status": "OBSERVED",
                },
            )
    return sorted(
        predicates.values(),
        key=lambda item: (
            str(item["parameter"]).upper(),
            int(item["line"]),
            ",".join(str(value) for value in item["values"]),
        ),
    )


def extract_dml_operations(
    sql_text: str,
    *,
    source_name: str = "<memory>",
) -> list[dict[str, Any]]:
    sanitized = mask_comments_and_literals(sql_text)
    scan = scan_static_sql(sql_text)
    operations: dict[tuple[str, str], dict[str, Any]] = {}
    for operation, pattern in _DML_PATTERNS:
        for match in pattern.finditer(sanitized):
            target = _normalize_target(match.group("target"))
            if not target or _target_is_keyword(target):
                continue
            if operation == "SELECT" and scan.is_cte_reference(
                _identifier_for_scan(target),
                match.start("target"),
            ):
                continue
            key = (operation, target.upper())
            line = sql_text.count("\n", 0, max(match.start("target"), 0)) + 1
            operations.setdefault(
                key,
                {
                    "operation": operation,
                    "targetRef": target,
                    "line": line,
                    "sourceName": source_name,
                    "evidenceRef": f"static.dml.{operation.lower()}.{_safe_ref_token(target)}",
                    "status": "OBSERVED",
                },
            )
    return sorted(
        operations.values(),
        key=lambda item: (str(item["targetRef"]).upper(), str(item["operation"])),
    )


def complexity_metrics(sql_text: str) -> list[dict[str, Any]]:
    sanitized = mask_comments_and_literals(sql_text)
    begin_count = len(re.findall(r"\bBEGIN\b", sanitized, flags=re.IGNORECASE))
    end_count = len(re.findall(r"\bEND\b", sanitized, flags=re.IGNORECASE))
    counts: dict[str, int] = {
        "LOC": sum(1 for line in sql_text.splitlines() if line.strip()),
        "BEGIN_END_BLOCK": min(begin_count, end_count),
    }
    for metric, pattern, _rule in _COUNT_PATTERNS:
        if metric in counts:
            continue
        counts[metric] = len(pattern.findall(sanitized))
    counts["CROSS_DB_REFERENCE"] = len(_cross_database_references(sanitized))
    rule_by_metric = {metric: rule for metric, _pattern, rule in _COUNT_PATTERNS}
    rule_by_metric["CROSS_DB_REFERENCE"] = "Unique three- or four-part identifier count."
    return [
        {
            "metric": metric,
            "count": count,
            "evidenceRule": rule_by_metric.get(metric, "Deterministic static token count."),
            "notes": "REVIEW_REQUIRED when count is non-zero for risky constructs."
            if metric
            in {
                "GOTO",
                "CURSOR_SIGNAL",
                "TRANSACTION_SIGNAL",
                "DYNAMIC_SQL_SIGNAL",
                "CROSS_DB_REFERENCE",
            }
            and count
            else "",
        }
        for metric, count in counts.items()
    ]


def _cross_database_references(sanitized_sql: str) -> list[str]:
    refs = {
        _normalize_target(match.group("target"))
        for match in _CROSS_DB_RE.finditer(sanitized_sql)
    }
    return sorted(ref for ref in refs if ref and not _target_is_keyword(ref))


def _normalize_target(value: str) -> str:
    parts = [
        normalize_identifier_token(part)
        for part in re.split(r"\s*\.\s*", value.strip())
        if part.strip()
    ]
    if not parts:
        return ""
    return ".".join(parts)


def _target_is_keyword(target: str) -> bool:
    object_name = target.rsplit(".", 1)[-1]
    return object_name.upper() in _KEYWORDS or object_name.startswith("@")


def _safe_ref_token(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z_]+", "_", value).strip("_").lower() or "target"


def _normalize_parameter(value: str) -> str:
    normalized = value.strip()
    return normalized if normalized.startswith("@") else f"@{normalized}"


def _sanitize_branch_value(value: str) -> str:
    text = value.strip()
    return text if _SAFE_BRANCH_VALUE_RE.match(text) else ""


def _strip_sql_comments_preserve_literals(sql_text: str) -> str:
    def _blank(match: re.Match[str]) -> str:
        return "".join("\n" if char == "\n" else " " for char in match.group(0))

    without_block_comments = re.sub(r"/\*.*?\*/", _blank, sql_text, flags=re.DOTALL)
    return re.sub(r"--[^\n\r]*", _blank, without_block_comments)


def _identifier_for_scan(target: str):
    from ai_agent_analysis.sql_utils import Identifier

    parts = target.split(".")
    if len(parts) >= 2:
        return Identifier(
            schema_name=parts[-2],
            object_name=parts[-1],
            full_name=f"{parts[-2]}.{parts[-1]}",
        )
    return Identifier(schema_name=None, object_name=parts[-1], full_name=parts[-1])
