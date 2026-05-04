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


@dataclass(frozen=True)
class Identifier:
    schema_name: str | None
    object_name: str
    full_name: str


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
