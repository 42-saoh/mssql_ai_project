from __future__ import annotations

import re

from ai_agent_analysis.models import (
    ParameterDirection,
    ProcedureIdentifier,
    ProcedureParameter,
    ProcedureSignature,
    ReviewMarker,
)
from ai_agent_analysis.sql_utils import (
    QUALIFIED_IDENTIFIER_PATTERN,
    make_evidence,
    mask_comments_and_literals,
    parse_identifier,
    split_top_level_csv,
)


PROCEDURE_HEADER_RE = re.compile(
    rf"\b(?:CREATE|ALTER)\s+(?:OR\s+ALTER\s+)?PROC(?:EDURE)?\s+"
    rf"(?P<name>{QUALIFIED_IDENTIFIER_PATTERN})"
    rf"(?P<params>.*?)\bAS\b",
    re.IGNORECASE | re.DOTALL,
)

PARAMETER_RE = re.compile(
    r"^\s*(?P<name>@[A-Za-z_][A-Za-z0-9_]*)\s+"
    r"(?P<data_type>[A-Za-z_][A-Za-z0-9_]*(?:\s*\([^)]*\))?)"
    r"(?:\s*=\s*(?P<default>.+?))?"
    r"(?:\s+(?P<direction>OUT|OUTPUT))?\s*$",
    re.IGNORECASE | re.DOTALL,
)


def parse_procedure_signature(
    sql_text: str,
    *,
    source_name: str = "<memory>",
) -> tuple[ProcedureSignature, list[ReviewMarker]]:
    sanitized = mask_comments_and_literals(sql_text)
    match = PROCEDURE_HEADER_RE.search(sanitized)
    if not match:
        fallback = ProcedureSignature(
            identifier=ProcedureIdentifier(
                schema_name=None,
                procedure_name="REVIEW_REQUIRED",
                full_name="REVIEW_REQUIRED",
            )
        )
        return (
            fallback,
            [
                ReviewMarker(
                    code="PROCEDURE_HEADER_REVIEW",
                    message="procedure header를 결정론적으로 파싱하지 못했습니다.",
                )
            ],
        )

    identifier = parse_identifier(match.group("name"))
    signature = ProcedureSignature(
        identifier=ProcedureIdentifier(
            schema_name=identifier.schema_name,
            procedure_name=identifier.object_name,
            full_name=identifier.full_name,
        ),
        evidence=[make_evidence(sql_text, match.start("name"), source_name)],
    )
    params_block = match.group("params").strip()
    signature.parameters.extend(
        _parse_parameters(sql_text, params_block, source_name, block_offset=match.start("params"))
    )
    return signature, []


def _parse_parameters(
    sql_text: str,
    params_block: str,
    source_name: str,
    *,
    block_offset: int,
) -> list[ProcedureParameter]:
    if not params_block:
        return []

    parameters: list[ProcedureParameter] = []
    for part in split_top_level_csv(params_block):
        if not part or not part.lstrip().startswith("@"):
            continue
        match = PARAMETER_RE.match(part)
        if not match:
            parameters.append(
                ProcedureParameter(
                    name=part.split()[0],
                    data_type="REVIEW_REQUIRED",
                    evidence=[
                        make_evidence(
                            sql_text,
                            block_offset + max(params_block.find(part), 0),
                            source_name,
                        )
                    ],
                )
            )
            continue
        direction = ParameterDirection.INPUT
        if match.group("direction"):
            direction = ParameterDirection.OUTPUT
        parameters.append(
            ProcedureParameter(
                name=match.group("name"),
                data_type=" ".join(match.group("data_type").split()).upper(),
                default=_clean_default(match.group("default")),
                direction=direction,
                evidence=[
                    make_evidence(
                        sql_text,
                        block_offset + max(params_block.find(part), 0),
                        source_name,
                    )
                ],
            )
        )
    return parameters


def _clean_default(default: str | None) -> str | None:
    if default is None:
        return None
    value = default.strip()
    for suffix in (" OUTPUT", " OUT"):
        if value.upper().endswith(suffix):
            value = value[: -len(suffix)].strip()
    return value or None
