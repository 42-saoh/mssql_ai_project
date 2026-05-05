from __future__ import annotations

import re

from ai_agent_analysis.models import EvidenceStatus, ResultSetColumnHint, ResultSetHint
from ai_agent_analysis.sql_utils import (
    IDENTIFIER_PATTERN,
    is_client_result_select,
    make_evidence,
    mask_comments_and_literals,
    normalize_identifier_token,
    scan_static_sql,
    split_top_level_csv,
)


SELECT_RE = re.compile(r"\bSELECT\b", re.IGNORECASE)
AS_ALIAS_RE = re.compile(rf"\s+AS\s+(?P<alias>{IDENTIFIER_PATTERN})\s*$", re.IGNORECASE)
TRAILING_ALIAS_RE = re.compile(rf"\s+(?P<alias>{IDENTIFIER_PATTERN})\s*$", re.IGNORECASE)
SIMPLE_IDENTIFIER_RE = re.compile(
    rf"^(?:(?:{IDENTIFIER_PATTERN})\s*\.\s*)?(?P<name>{IDENTIFIER_PATTERN})$",
    re.IGNORECASE,
)
TOP_RE = re.compile(r"^\s*(?:DISTINCT\s+)?TOP\s*(?:\([^)]+\)|\d+)\s+", re.IGNORECASE)
DISTINCT_RE = re.compile(r"^\s*DISTINCT\s+", re.IGNORECASE)


def extract_result_set_hints(
    sql_text: str,
    *,
    source_name: str = "<memory>",
) -> list[ResultSetHint]:
    sanitized = mask_comments_and_literals(sql_text)
    scan = scan_static_sql(sql_text)
    result_sets: list[ResultSetHint] = []
    for match in SELECT_RE.finditer(sanitized):
        select_start = match.start()
        if not is_client_result_select(sanitized, select_start, scan=scan):
            continue
        select_list_start, select_list_end = _select_list_bounds(sanitized, match.end())
        select_list = sql_text[select_list_start:select_list_end]
        columns = _extract_column_hints(
            sql_text,
            select_list,
            source_name,
            block_offset=select_list_start,
        )
        status = (
            EvidenceStatus.REVIEW_REQUIRED
            if any(column.status == EvidenceStatus.REVIEW_REQUIRED for column in columns)
            else EvidenceStatus.OBSERVED
        )
        review_notes = (
            ["Result-set columns include wildcard or complex expressions that need review."]
            if status == EvidenceStatus.REVIEW_REQUIRED
            else []
        )
        result_sets.append(
            ResultSetHint(
                ordinal=len(result_sets) + 1,
                columns=columns,
                status=status,
                evidence=[make_evidence(sql_text, select_start, source_name, status=status)],
                review_notes=review_notes,
            )
        )
    return result_sets


def _extract_column_hints(
    sql_text: str,
    select_list: str,
    source_name: str,
    *,
    block_offset: int,
) -> list[ResultSetColumnHint]:
    cleaned_select = _strip_select_modifiers(select_list)
    columns: list[ResultSetColumnHint] = []
    for part in split_top_level_csv(cleaned_select):
        expression = " ".join(part.strip().split())
        if not expression:
            continue
        name, status, review_notes = _derive_column_name(expression)
        columns.append(
            ResultSetColumnHint(
                name=name,
                expression=expression,
                status=status,
                evidence=[
                    make_evidence(
                        sql_text,
                        block_offset + max(select_list.find(part), 0),
                        source_name,
                        status=status,
                    )
                ],
                review_notes=review_notes,
            )
        )
    return columns


def _derive_column_name(expression: str) -> tuple[str | None, EvidenceStatus, list[str]]:
    if expression == "*" or expression.endswith(".*"):
        return (
            None,
            EvidenceStatus.REVIEW_REQUIRED,
            ["Wildcard result columns require metadata-backed review."],
        )
    alias_match = AS_ALIAS_RE.search(expression)
    if alias_match:
        return normalize_identifier_token(alias_match.group("alias")), EvidenceStatus.OBSERVED, []
    simple_match = SIMPLE_IDENTIFIER_RE.match(expression)
    if simple_match:
        return normalize_identifier_token(simple_match.group("name")), EvidenceStatus.OBSERVED, []
    trailing_alias_match = TRAILING_ALIAS_RE.search(expression)
    if trailing_alias_match and any(char in expression for char in (" ", ")", "+", "-")):
        return (
            normalize_identifier_token(trailing_alias_match.group("alias")),
            EvidenceStatus.OBSERVED,
            [],
        )
    return (
        None,
        EvidenceStatus.REVIEW_REQUIRED,
        ["Complex result expression requires alias or manual review."],
    )


def _strip_select_modifiers(select_list: str) -> str:
    value = TOP_RE.sub("", select_list.strip())
    return DISTINCT_RE.sub("", value).strip()


def _select_list_bounds(sanitized_sql: str, select_keyword_end: int) -> tuple[int, int]:
    depth = 0
    index = select_keyword_end
    while index < len(sanitized_sql):
        char = sanitized_sql[index]
        if char == "(":
            depth += 1
        elif char == ")" and depth:
            depth -= 1
        elif depth == 0:
            if char == ";":
                return select_keyword_end, index
            if _keyword_at(sanitized_sql, index, "FROM"):
                return select_keyword_end, index
        index += 1
    return select_keyword_end, len(sanitized_sql)


def _keyword_at(text: str, index: int, keyword: str) -> bool:
    end = index + len(keyword)
    if text[index:end].upper() != keyword:
        return False
    before = text[index - 1] if index > 0 else " "
    after = text[end] if end < len(text) else " "
    return not _is_identifier_char(before) and not _is_identifier_char(after)


def _is_identifier_char(char: str) -> bool:
    return char.isalnum() or char in "_#@$]"
