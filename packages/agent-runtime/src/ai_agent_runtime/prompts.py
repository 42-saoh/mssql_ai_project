from __future__ import annotations

import json
from typing import Any

from ai_agent_runtime.models import (
    OUTPUT_SCHEMA_VERSION,
    PROMPT_VERSION,
    RenderedPrompt,
    stable_json_hash,
    text_hash,
)

SYSTEM_PROMPT = """You analyze MSSQL stored procedures for a draft-only migration platform.
Return only schema-valid JSON. Treat deterministic metadata and static analysis as evidence.
Do not invent dependencies, tables, functions, or procedures. Mark uncertain conclusions as
REVIEW_REQUIRED. Never request row data, procedure execution, DDL/DML, deployment, or secrets."""


def render_semantic_analysis_prompt(
    *,
    target_ref: str,
    metadata: dict[str, Any],
    static_analysis: dict[str, Any] | None,
    procedure_definition: str | None,
) -> RenderedPrompt:
    input_payload = {
        "targetRef": target_ref,
        "metadata": _metadata_without_raw_definition(metadata),
        "staticAnalysis": static_analysis,
        "procedureDefinitionHash": text_hash(procedure_definition or ""),
        "procedureDefinitionLength": len(procedure_definition or ""),
        "procedureDefinitionIncluded": procedure_definition is not None,
        "task": (
            "Infer business rules, modernization points, risk flags, review markers, and "
            "assumptions from the supplied MSSQL procedure evidence."
        ),
    }
    if procedure_definition is not None:
        input_payload["procedureDefinition"] = procedure_definition
    user_prompt = json.dumps(input_payload, ensure_ascii=False, sort_keys=True, default=str)
    prompt_hash = text_hash(f"{SYSTEM_PROMPT}\n{user_prompt}")
    return RenderedPrompt(
        prompt_version=PROMPT_VERSION,
        output_schema_version=OUTPUT_SCHEMA_VERSION,
        system_prompt=SYSTEM_PROMPT,
        user_prompt=user_prompt,
        input_hash=stable_json_hash(input_payload),
        prompt_hash=prompt_hash,
        metadata={
            "targetRef": target_ref,
            "procedureDefinitionHash": input_payload["procedureDefinitionHash"],
            "procedureDefinitionIncluded": procedure_definition is not None,
        },
    )


def _metadata_without_raw_definition(metadata: dict[str, Any]) -> dict[str, Any]:
    sanitized = json.loads(json.dumps(metadata, ensure_ascii=False, default=str))
    definition = sanitized.get("procedureDefinition")
    if isinstance(definition, dict):
        definition.pop("definition", None)
    return sanitized
