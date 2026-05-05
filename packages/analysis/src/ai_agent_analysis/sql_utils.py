from __future__ import annotations

import re
from dataclasses import dataclass

from ai_agent_analysis.models import EvidenceRef, EvidenceStatus


IDENTIFIER_PATTERN = r"(?:\[[^\]]+\]|#?[A-Za-z_][A-Za-z0-9_#$]*)"
VARIABLE_OR_IDENTIFIER_PATTERN = r"(?:\[[^\]]+\]|[@#]?[A-Za-z_][A-Za-z0-9_#$]*)"
QUALIFIED_IDENTIFIER_PATTERN = rf"{IDENTIFIER_PATTERN}(?:\s*\.\s*{IDENTIFIER_PATTERN})?"
QUALIFIED_VARIABLE_OR_IDENTIFIER_PATTERN = (
    rf"{VARIABLE_OR_IDENTIFIER_PATTERN}(?:\s*\.\s*{VARIABLE_OR_IDENTIFIER_PATTERN})?"
)
CTE_START_RE = re.compile(r"\bWITH\b", re.IGNORECASE)
CTE_DEFINITION_RE = re.compile(
    rf"\s*(?P<name>{IDENTIFIER_PATTERN})(?:\s*\([^)]*\))?\s+AS\s*\(",
    re.IGNORECASE | re.DOTALL,
)
INSERT_SELECT_CONTEXT_RE = re.compile(
    r"\bINSERT\s+(?:INTO\s+)?(?:#[A-Za-z_][A-Za-z0-9_]*|[A-Za-z_\[][^;]*)$",
    re.IGNORECASE | re.DOTALL,
)
CURSOR_SELECT_CONTEXT_RE = re.compile(r"\bCURSOR\s+FOR\s*$", re.IGNORECASE | re.DOTALL)
ASSIGNMENT_SELECT_RE = re.compile(r"^\s*SELECT\s+@[A-Za-z_][A-Za-z0-9_]*\s*=", re.IGNORECASE)


@dataclass(frozen=True)
class Identifier:
    schema_name: str | None
    object_name: str
    full_name: str


@dataclass(frozen=True)
class TextSpan:
    start: int
    end: int

    def contains(self, index: int) -> bool:
        return self.start <= index < self.end


@dataclass(frozen=True)
class StaticSqlScan:
    cte_names: frozenset[str] = frozenset()
    cte_body_spans: tuple[TextSpan, ...] = ()

    def is_inside_cte_body(self, index: int) -> bool:
        return any(span.contains(index) for span in self.cte_body_spans)

    def is_cte_reference(self, identifier: Identifier) -> bool:
        if identifier.schema_name:
            return False
        return normalize_identifier_token(identifier.object_name).lower() in self.cte_names


def mask_comments_and_literals(sql_text: str) -> str:
    without_comments = _replace_preserving_newlines(
        re.compile(r"/\*.*?\*/|--[^\n\r]*", re.DOTALL).sub,
        sql_text,
    )
    return _replace_preserving_newlines(
        re.compile(r"N?'(?:''|[^'])*'", re.IGNORECASE).sub,
        without_comments,
    )


def normalize_identifier_token(token: str) -> str:
    token = token.strip()
    if token.startswith("[") and token.endswith("]"):
        return token[1:-1]
    return token


def parse_identifier(token: str) -> Identifier:
    parts = [normalize_identifier_token(part) for part in re.split(r"\s*\.\s*", token.strip())]
    parts = [part for part in parts if part]
    if len(parts) >= 2:
        schema_name = parts[-2]
        object_name = parts[-1]
        full_name = f"{schema_name}.{object_name}"
        return Identifier(schema_name=schema_name, object_name=object_name, full_name=full_name)
    if len(parts) == 1:
        return Identifier(schema_name=None, object_name=parts[0], full_name=parts[0])
    return Identifier(schema_name=None, object_name="", full_name="")


def scan_static_sql(sql_text: str) -> StaticSqlScan:
    sanitized = mask_comments_and_literals(sql_text)
    cte_names: list[str] = []
    cte_body_spans: list[TextSpan] = []
    for with_match in CTE_START_RE.finditer(sanitized):
        parsed = _parse_cte_clause(sanitized, with_match.end())
        if parsed is None:
            continue
        names, spans = parsed
        cte_names.extend(names)
        cte_body_spans.extend(spans)
    return StaticSqlScan(frozenset(cte_names), tuple(cte_body_spans))


def is_client_result_select(
    sanitized_sql: str,
    select_start: int,
    *,
    scan: StaticSqlScan | None = None,
) -> bool:
    if scan is not None and scan.is_inside_cte_body(select_start):
        return False
    statement_prefix = sanitized_sql[
        max(0, sanitized_sql.rfind(";", 0, select_start)) : select_start
    ]
    if INSERT_SELECT_CONTEXT_RE.search(statement_prefix):
        return False
    if CURSOR_SELECT_CONTEXT_RE.search(statement_prefix):
        return False
    statement_tail = sanitized_sql[select_start : select_start + 160]
    if ASSIGNMENT_SELECT_RE.match(statement_tail):
        return False
    return True


def make_evidence(
    sql_text: str,
    start: int,
    source_name: str,
    *,
    status: EvidenceStatus = EvidenceStatus.OBSERVED,
) -> EvidenceRef:
    line_no = sql_text.count("\n", 0, max(start, 0)) + 1
    lines = sql_text.splitlines()
    snippet = lines[line_no - 1].strip() if 0 < line_no <= len(lines) else ""
    return EvidenceRef(source=source_name, line=line_no, snippet=snippet, status=status)


def split_top_level_csv(text: str) -> list[str]:
    parts: list[str] = []
    start = 0
    depth = 0
    in_string = False
    index = 0
    while index < len(text):
        char = text[index]
        if char == "'":
            if in_string and index + 1 < len(text) and text[index + 1] == "'":
                index += 2
                continue
            in_string = not in_string
        elif not in_string:
            if char == "(":
                depth += 1
            elif char == ")" and depth:
                depth -= 1
            elif char == "," and depth == 0:
                parts.append(text[start:index].strip())
                start = index + 1
        index += 1
    tail = text[start:].strip()
    if tail:
        parts.append(tail)
    return parts


def _replace_preserving_newlines(sub_func, text: str) -> str:
    def replacement(match: re.Match[str]) -> str:
        return "".join("\n" if char == "\n" else " " for char in match.group(0))

    return sub_func(replacement, text)


def _parse_cte_clause(
    sanitized_sql: str,
    start: int,
) -> tuple[list[str], list[TextSpan]] | None:
    cte_names: list[str] = []
    cte_body_spans: list[TextSpan] = []
    cursor = start
    while True:
        definition_match = CTE_DEFINITION_RE.match(sanitized_sql, cursor)
        if definition_match is None:
            return None if not cte_names else (cte_names, cte_body_spans)
        open_paren = definition_match.end() - 1
        close_paren = _find_matching_paren(sanitized_sql, open_paren)
        if close_paren is None:
            return None
        cte_names.append(normalize_identifier_token(definition_match.group("name")).lower())
        cte_body_spans.append(TextSpan(open_paren + 1, close_paren))
        cursor = close_paren + 1
        while cursor < len(sanitized_sql) and sanitized_sql[cursor].isspace():
            cursor += 1
        if cursor >= len(sanitized_sql) or sanitized_sql[cursor] != ",":
            return cte_names, cte_body_spans
        cursor += 1


def _find_matching_paren(sql_text: str, open_paren: int) -> int | None:
    depth = 0
    for index in range(open_paren, len(sql_text)):
        char = sql_text[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
    return None
