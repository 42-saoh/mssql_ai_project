from __future__ import annotations

import json
from typing import Any

from ai_agent_runtime.models import (
    METADATA_ANALYSIS_OUTPUT_SCHEMA_VERSION,
    METADATA_ANALYSIS_PROMPT_VERSION,
    OUTPUT_SCHEMA_VERSION,
    PLATFORM_TOOL_PLANNER_OUTPUT_SCHEMA_VERSION,
    PLATFORM_TOOL_PLANNER_PROMPT_VERSION,
    PROMPT_VERSION,
    TOOL_PLANNER_OUTPUT_SCHEMA_VERSION,
    TOOL_PLANNER_PROMPT_VERSION,
    RenderedPrompt,
    stable_json_hash,
    text_hash,
)

SYSTEM_PROMPT = """You analyze MSSQL stored procedures for a draft-only migration platform.
Return only schema-valid JSON. Treat deterministic metadata and static analysis as evidence.
Every claim must use evidenceRefs copied exactly from evidenceRefContract.allowedFactIds.
Always return these top-level arrays even when empty: businessRules, modernizationPoints,
riskFlags, reviewMarkers, conversionGuidance, migrationGuideInsights, and assumptions.
For migrationGuideInsights, use section keys from the migration guide contract and, when useful,
populate guideElement, targetRef, riskArea, and whatToExtractNext. Use whatToExtractNext for
uncertain dependencies, dynamic SQL, cross-database references, result-shape gaps, and any
Needs verification guide row.
Never use prompt hashes, input hashes, output hashes, raw SQL snippets, row data, or provider
trace ids as claim evidence. Do not invent dependencies, tables, functions, or procedures.
Allowed claim statuses are only INFERRED_DESCRIPTION and REVIEW_REQUIRED. Never use
CONFIRMED, SUPPORTED, DONE, OK, or other completion statuses. Mark uncertain conclusions
as REVIEW_REQUIRED. Prioritize migration guide quality and Java/MyBatis conversion
readiness, but never treat LLM inference as deterministic fact.
Never request row data, procedure execution, DDL/DML, deployment, or secrets."""

TOOL_PLANNER_SYSTEM_PROMPT = """You plan bounded MSSQL metadata tool use for an AI agent workflow.
Return only schema-valid JSON. Choose only tools from toolCapabilities. Request metadata-only
facts that will improve the later semantic analysis. Never request row data, procedure execution,
free-form SQL, DDL/DML, deployment, secrets, credentials, or profile switching. Prefer the
smallest number of tool calls and use structured arguments only. Use the exact output field
names toolRequests, toolName, arguments, reason, expectedEvidenceUse, assumptions, and
reviewMarkers; do not use aliases such as tools, requests, tool, args, parameters, rationale,
or evidenceUse. Return no toolRequests only when existing evidence is already sufficient."""

PLATFORM_TOOL_PLANNER_SYSTEM_PROMPT = """You plan bounded platform context tool use for an
AI agent workflow. Return only schema-valid JSON. Choose only tools from toolCapabilities.
Request read-only platform evidence that will improve the later semantic analysis. Never
request artifact full content, raw SQL, raw stored procedure definitions, row data, procedure
execution, DDL/DML, deployment, approval/review writes, export creation, secrets, credentials,
raw prompts, or provider responses. Stay within the supplied job, db profile, and target scope.
Prefer the smallest number of tool calls and use structured arguments only. Use the exact
output field names toolRequests, toolName, arguments, reason, expectedEvidenceUse,
assumptions, and reviewMarkers; do not use aliases such as tools, requests, tool, args,
parameters, rationale, or evidenceUse."""

METADATA_ANALYSIS_SYSTEM_PROMPT = """You analyze read-only MSSQL metadata evidence for an
AI agent platform. Return only schema-valid JSON. Every insight must use evidenceRefs copied
exactly from evidenceRefContract.allowedFactIds. Do not invent tables, columns, procedures,
views, functions, dependencies, or constraints. Never use prompt hashes, input hashes, output
hashes, raw SQL snippets, row data, or provider trace ids as claim evidence. Mark uncertain
conclusions as REVIEW_REQUIRED. Group object insights by column risk, relationship, index,
constraint, documentation gap, DTO readiness, and dependency categories when supported.
Never request or imply row data access, procedure execution, DDL/DML, deployment, secrets,
credentials, or profile switching."""


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
        "qualityHints": _quality_hints(metadata, static_analysis, allowed_refs),
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


def render_metadata_tool_planning_prompt(
    *,
    target_ref: str,
    metadata: dict[str, Any],
    static_analysis: dict[str, Any] | None,
    tool_capabilities: list[dict[str, Any]],
    previous_tool_evidence: list[dict[str, Any]] | None = None,
    max_tool_calls: int = 5,
    round_index: int = 1,
) -> RenderedPrompt:
    input_payload = {
        "targetRef": target_ref,
        "metadata": _metadata_without_raw_definition(metadata),
        "staticAnalysis": static_analysis,
        "toolCapabilities": tool_capabilities,
        "previousToolEvidence": list(previous_tool_evidence or []),
        "policy": {
            "maxToolCalls": max_tool_calls,
            "allowedScope": "active read-only MSSQL metadata tools only",
            "forbidden": [
                "row data",
                "procedure execution",
                "free-form SQL",
                "DDL/DML",
                "deployment",
                "secrets or credentials",
                "db profile switching",
                "raw definition storage",
            ],
            "rawDefinitionHandling": (
                "Definition tools may be requested only for metadata value; raw definition "
                "text is removed before later prompts, storage, artifacts, and audit logs."
            ),
        },
        "task": (
            "Select additional metadata tool calls that can produce deterministic evidence "
            "for the later semantic analysis. For TABLE targets or table search results, "
            "prefer get_table_schema, get_table_constraints, get_table_indexes, "
            "get_extended_properties, and get_related_db_objects when those facts are "
            "missing. For PROCEDURE, VIEW, or FUNCTION targets, prefer dependency closure, "
            "related objects, extended properties, and definition-metadata tools, knowing "
            "raw definition text will be removed. Use exact JSON field names only: "
            "toolRequests items must contain toolName, arguments, reason, and "
            "expectedEvidenceUse. Return no toolRequests only when existing evidence is "
            "sufficient for dependency, documentation, shape, and relationship claims."
        ),
        "round": round_index,
    }
    user_prompt = json.dumps(input_payload, ensure_ascii=False, sort_keys=True, default=str)
    prompt_hash = text_hash(f"{TOOL_PLANNER_SYSTEM_PROMPT}\n{user_prompt}")
    tool_names = [
        str(tool.get("name"))
        for tool in tool_capabilities
        if isinstance(tool, dict) and tool.get("name")
    ]
    return RenderedPrompt(
        prompt_version=TOOL_PLANNER_PROMPT_VERSION,
        output_schema_version=TOOL_PLANNER_OUTPUT_SCHEMA_VERSION,
        system_prompt=TOOL_PLANNER_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        input_hash=stable_json_hash(input_payload),
        prompt_hash=prompt_hash,
        metadata={
            "targetRef": target_ref,
            "stage": "metadata_tool_planning",
            "toolNames": sorted(set(tool_names)),
            "maxToolCalls": max_tool_calls,
            "round": round_index,
        },
    )


def render_platform_tool_planning_prompt(
    *,
    target_ref: str,
    metadata: dict[str, Any],
    static_analysis: dict[str, Any] | None,
    tool_capabilities: list[dict[str, Any]],
    job_context: dict[str, Any],
    previous_tool_evidence: list[dict[str, Any]] | None = None,
    max_tool_calls: int = 3,
) -> RenderedPrompt:
    input_payload = {
        "targetRef": target_ref,
        "jobContext": job_context,
        "metadata": _metadata_without_raw_definition(metadata),
        "staticAnalysis": static_analysis,
        "toolCapabilities": tool_capabilities,
        "previousToolEvidence": list(previous_tool_evidence or []),
        "policy": {
            "maxToolCalls": max_tool_calls,
            "allowedScope": "internal active read-only platform context tools only",
            "forbidden": [
                "artifact full content",
                "raw SQL",
                "raw stored procedure definitions",
                "row data",
                "procedure execution",
                "DDL/DML",
                "deployment",
                "approval or review writes",
                "export creation",
                "secrets or credentials",
                "raw prompts or provider responses",
                "job, db profile, or target switching",
            ],
        },
        "task": (
            "Select platform context tool calls that can produce sanitized evidence for "
            "later semantic analysis. Prefer knowledge facts/assets for the current target "
            "when available, validation summaries for current-job artifacts when relevant, "
            "agent-run summaries for current-job trace context, and registry versions for "
            "reproducibility evidence. Use exact JSON field names only: toolRequests items "
            "must contain toolName, arguments, reason, and expectedEvidenceUse."
        ),
        "round": 1,
    }
    user_prompt = json.dumps(input_payload, ensure_ascii=False, sort_keys=True, default=str)
    prompt_hash = text_hash(f"{PLATFORM_TOOL_PLANNER_SYSTEM_PROMPT}\n{user_prompt}")
    tool_names = [
        str(tool.get("name"))
        for tool in tool_capabilities
        if isinstance(tool, dict) and tool.get("name")
    ]
    return RenderedPrompt(
        prompt_version=PLATFORM_TOOL_PLANNER_PROMPT_VERSION,
        output_schema_version=PLATFORM_TOOL_PLANNER_OUTPUT_SCHEMA_VERSION,
        system_prompt=PLATFORM_TOOL_PLANNER_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        input_hash=stable_json_hash(input_payload),
        prompt_hash=prompt_hash,
        metadata={
            "targetRef": target_ref,
            "stage": "platform_tool_planning",
            "toolNames": sorted(set(tool_names)),
            "maxToolCalls": max_tool_calls,
            "round": 1,
        },
    )


def render_metadata_analysis_prompt(
    *,
    target_ref: str,
    metadata: dict[str, Any],
    allowed_evidence_refs: list[str] | tuple[str, ...] | None = None,
    stage: str = "metadata_analysis",
) -> RenderedPrompt:
    allowed_refs = sorted(
        {str(ref) for ref in (allowed_evidence_refs or ()) if str(ref).strip()}
    )
    input_payload = {
        "targetRef": target_ref,
        "metadata": _metadata_without_raw_definition(metadata),
        "stage": stage,
        "task": (
            "Summarize metadata structure, object profile depth, column risk, relationships, "
            "indexes, constraints, documentation gaps, dependency graph implications, and "
            "draft-only DTO readiness using only deterministic fact ids. Populate "
            "insightGroups and dtoReadiness. Do not invent FK, PK, index, constraint, "
            "column, dependency, or DTO claims."
        ),
        "evidenceRefContract": {
            "allowedFactIds": allowed_refs,
            "factCatalog": _fact_catalog(metadata, None, allowed_refs),
            "forbiddenEvidenceRefs": [
                "prompt.inputHash",
                "prompt.promptHash",
                "modelInvocation.outputHash",
                "metadata.snapshot",
                "static.analysis",
            ],
            "rule": (
                "Each objectInsights, insightGroups.insights, dtoReadiness, and "
                "reviewMarkers evidenceRefs array must contain one or more ids copied "
                "exactly from allowedFactIds. If no allowed fact supports a claim, omit "
                "that claim or put uncertainty in assumptions."
            ),
        },
    }
    user_prompt = json.dumps(input_payload, ensure_ascii=False, sort_keys=True, default=str)
    prompt_hash = text_hash(f"{METADATA_ANALYSIS_SYSTEM_PROMPT}\n{user_prompt}")
    return RenderedPrompt(
        prompt_version=METADATA_ANALYSIS_PROMPT_VERSION,
        output_schema_version=METADATA_ANALYSIS_OUTPUT_SCHEMA_VERSION,
        system_prompt=METADATA_ANALYSIS_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        input_hash=stable_json_hash(input_payload),
        prompt_hash=prompt_hash,
        metadata={
            "targetRef": target_ref,
            "stage": stage,
            "allowedEvidenceRefs": allowed_refs,
        },
    )


def _metadata_without_raw_definition(metadata: dict[str, Any]) -> dict[str, Any]:
    sanitized = json.loads(json.dumps(metadata, ensure_ascii=False, default=str))
    return _remove_raw_metadata_fields(sanitized)


def _remove_raw_metadata_fields(value: Any) -> Any:
    if isinstance(value, dict):
        cleaned = {}
        for key, item in value.items():
            normalized = str(key).replace("-", "_").lower()
            if normalized in {
                "definition",
                "raw_definition",
                "raw_definition_text",
                "rawsql",
                "raw_sql",
                "sqltext",
                "sql_text",
                "rowdata",
                "row_data",
                "rows",
                "records",
                "password",
                "secret",
                "token",
                "apikey",
                "api_key",
                "connectionstring",
                "connection_string",
            }:
                continue
            cleaned[key] = _remove_raw_metadata_fields(item)
        return cleaned
    if isinstance(value, list):
        return [_remove_raw_metadata_fields(item) for item in value]
    return value


def _stage_task(stage: str) -> str:
    if stage == "deterministic_evidence_digest":
        return (
            "Summarize the deterministic evidence that will anchor later claims. "
            "Return only supported low-level insights and assumptions; do not create "
            "new dependency facts."
        )
    if stage == "business_rule_extraction":
        return (
            "Extract business rules, read-only lookup behavior, transaction/DML side "
            "effects, dynamic SQL or cross-database risk candidates, and uncertain result "
            "shape candidates by deterministic fact type. Populate businessRules and "
            "riskFlags only with exact allowedFactIds."
        )
    if stage == "conversion_readiness":
        return (
            "Focus on Java/MyBatis conversion readiness. Populate conversionGuidance "
            "with draft-only implementation guidance, blockers, and REVIEW_REQUIRED "
            "caveats tied to exact allowedFactIds. Java/MyBatis guidance must be in "
            "conversionGuidance and marked REVIEW_REQUIRED."
        )
    if stage == "migration_guide_insights":
        return (
            "Focus on migration guide quality. Populate migrationGuideInsights with "
            "section-level insights for overview, dependency inventory, DML matrix, "
            "call flow, risk metrics, metadata extraction appendix, and migration "
            "strategy. Distinguish Confirmed from Needs verification in summaries. "
            "Use stable guide section keys rather than prose-only headings, and fill "
            "whatToExtractNext for uncertain dynamic SQL, cross-database, ambiguous, "
            "or unresolved dependency observations."
        )
    if stage == "evidence_critic":
        return (
            "Critique the accumulated evidence discipline. Add missing REVIEW_REQUIRED "
            "markers and avoid unsupported dependency, table, function, or procedure claims. "
            "Unsupported dependency/table/function/procedure observations belong only in "
            "reviewMarkers, not deterministic facts or confirmed claims."
        )
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


def _quality_hints(
    metadata: dict[str, Any],
    static_analysis: dict[str, Any] | None,
    allowed_refs: list[str],
) -> dict[str, Any]:
    fact_catalog = _fact_catalog(metadata, static_analysis, allowed_refs)
    coverage = []
    ref_text = " ".join(
        [
            *allowed_refs,
            *[
                f"{item.get('type', '')} {item.get('summary', '')}"
                for item in fact_catalog
                if isinstance(item, dict)
            ],
        ]
    ).lower()
    coverage_specs = (
        (
            "readOnlyLookup",
            ("read", "lookup", "parameter", "result_shape", "result shape"),
            (
                "When lookup/read/result facts exist, cover businessRules, "
                "conversionGuidance, and migrationGuideInsights."
            ),
        ),
        (
            "transactionDml",
            ("transaction", "commit", "rollback", "insert", "update", "delete", "dml", "write"),
            (
                "When transaction or DML facts exist, cover side effects, riskFlags, "
                "conversionGuidance, and DML-matrix guide sections."
            ),
        ),
        (
            "dynamicSqlCrossDb",
            ("dynamic", "sp_executesql", "cross", "database", "tenant"),
            (
                "When dynamic SQL or cross-database facts exist, keep dependency "
                "claims REVIEW_REQUIRED and add reviewMarkers."
            ),
        ),
        (
            "uncertainResultShape",
            ("uncertain", "result shape", "result_shape", "rowcount", "unknown shape"),
            (
                "When result shape is uncertain, add REVIEW_REQUIRED conversion and "
                "migration guide caveats."
            ),
        ),
    )
    for key, keywords, instruction in coverage_specs:
        if any(keyword in ref_text for keyword in keywords):
            coverage.append(
                {
                    "coverageKey": key,
                    "instruction": instruction,
                    "claimKeyExamples": [
                        f"{key}.business",
                        f"{key}.conversion",
                        f"{key}.migration",
                    ],
                }
            )
    return {
        "expectedCoverage": coverage,
        "claimKeyRule": (
            "Use generic stable keys from the detected coverage area; never copy "
            "fixture-specific expected wording."
        ),
    }


def _fact_catalog(
    metadata: dict[str, Any],
    static_analysis: dict[str, Any] | None,
    allowed_refs: list[str],
) -> list[dict[str, str]]:
    deterministic_facts = metadata.get("deterministicFacts") or metadata.get("deterministic_facts")
    used: set[str] = set()
    catalog = []
    if isinstance(deterministic_facts, list):
        for fact in deterministic_facts:
            if not isinstance(fact, dict):
                continue
            fact_id = str(fact.get("id") or "")
            if fact_id in allowed_refs:
                used.add(fact_id)
                catalog.append(
                    {
                        "id": fact_id,
                        "type": str(fact.get("fact_type") or fact.get("type") or "FACT"),
                        "summary": str(fact.get("summary") or ""),
                    }
                )

    for ref in allowed_refs:
        if ref in used:
            continue
        summary = "Deterministic metadata or static analysis evidence."
        if ref.startswith("static.pattern."):
            summary = f"Static analysis detected {ref.removeprefix('static.pattern.')}."
        elif ref.startswith("mcp."):
            summary = "MSSQL MCP tool evidence gathered by bounded AI orchestration."
        elif ref.startswith("platform."):
            summary = "Platform context tool evidence gathered by bounded AI orchestration."
        elif ref.startswith("metadata."):
            summary = "MSSQL metadata evidence."
        catalog.append({"id": ref, "type": "DETERMINISTIC_EVIDENCE", "summary": summary})
    return catalog
