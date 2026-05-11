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
Every claim must use evidenceRefs copied exactly from evidenceRefContract.allowedFactIds.
Never use prompt hashes, input hashes, output hashes, raw SQL snippets, row data, or provider
trace ids as claim evidence. Do not invent dependencies, tables, functions, or procedures.
Mark uncertain conclusions as REVIEW_REQUIRED. Never request row data, procedure execution,
DDL/DML, deployment, or secrets."""


def render_semantic_analysis_prompt(
    *,
    target_ref: str,
    metadata: dict[str, Any],
    static_analysis: dict[str, Any] | None,
    procedure_definition: str | None,
    stage: str = "semantic_claims",
    allowed_evidence_refs: list[str] | tuple[str, ...] | None = None,
    required_review_markers: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    repair_context: dict[str, Any] | None = None,
) -> RenderedPrompt:
    allowed_refs = sorted(
        {str(ref) for ref in (allowed_evidence_refs or ()) if str(ref).strip()}
    )
    required_markers = list(required_review_markers or ())
    input_payload = {
        "targetRef": target_ref,
        "metadata": _metadata_without_raw_definition(metadata),
        "staticAnalysis": static_analysis,
        "procedureDefinitionHash": text_hash(procedure_definition or ""),
        "procedureDefinitionLength": len(procedure_definition or ""),
        "procedureDefinitionIncluded": procedure_definition is not None,
        "stage": stage,
        "task": _stage_task(stage),
        "evidenceRefContract": {
            "allowedFactIds": allowed_refs,
            "factCatalog": _fact_catalog(metadata, static_analysis, allowed_refs),
            "forbiddenEvidenceRefs": [
                "prompt.inputHash",
                "prompt.promptHash",
                "modelInvocation.outputHash",
                "metadata.snapshot",
                "static.analysis",
            ],
            "rule": (
                "Each claim evidenceRefs array must contain one or more ids copied "
                "exactly from allowedFactIds. If no allowed fact supports a claim, "
                "omit that claim or put the uncertainty in assumptions."
            ),
        },
        "requiredReviewMarkers": required_markers,
    }
    if repair_context is not None:
        input_payload["repairContext"] = repair_context
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
            "stage": stage,
            "allowedEvidenceRefs": allowed_refs,
            "requiredReviewMarkers": required_markers,
        },
    )


def _metadata_without_raw_definition(metadata: dict[str, Any]) -> dict[str, Any]:
    sanitized = json.loads(json.dumps(metadata, ensure_ascii=False, default=str))
    definition = sanitized.get("procedureDefinition")
    if isinstance(definition, dict):
        definition.pop("definition", None)
    return sanitized


def _stage_task(stage: str) -> str:
    if stage == "semantic_claims":
        return (
            "Infer only supported business rules, modernization points, and risk flags. "
            "Use exact allowedFactIds for every evidenceRefs array."
        )
    if stage == "review_markers":
        return (
            "Focus on REVIEW_REQUIRED markers for dynamic SQL, cross-database references, "
            "and unsupported dependency/table/function/procedure claims."
        )
    if stage == "repair":
        return (
            "Repair the supplied structured output so evidenceRefs use exact allowedFactIds "
            "and requiredReviewMarkers are present with status REVIEW_REQUIRED."
        )
    return "Infer draft-only SP semantic analysis from deterministic evidence."


def _fact_catalog(
    metadata: dict[str, Any],
    static_analysis: dict[str, Any] | None,
    allowed_refs: list[str],
) -> list[dict[str, str]]:
    deterministic_facts = metadata.get("deterministicFacts") or metadata.get("deterministic_facts")
    if isinstance(deterministic_facts, list):
        catalog = []
        for fact in deterministic_facts:
            if not isinstance(fact, dict):
                continue
            fact_id = str(fact.get("id") or "")
            if fact_id in allowed_refs:
                catalog.append(
                    {
                        "id": fact_id,
                        "type": str(fact.get("fact_type") or fact.get("type") or "FACT"),
                        "summary": str(fact.get("summary") or ""),
                    }
                )
        if catalog:
            return catalog

    catalog = []
    for ref in allowed_refs:
        summary = "Deterministic metadata or static analysis evidence."
        if ref.startswith("static.pattern."):
            summary = f"Static analysis detected {ref.removeprefix('static.pattern.')}."
        elif ref.startswith("metadata."):
            summary = "MSSQL metadata evidence."
        catalog.append({"id": ref, "type": "DETERMINISTIC_EVIDENCE", "summary": summary})
    return catalog
