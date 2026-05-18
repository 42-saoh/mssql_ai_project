from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from ai_agent_runtime.ai_draft_pack import (
    AI_JAVA_MYBATIS_DRAFT_PACK_OUTPUT_SCHEMA_VERSION,
    AI_JAVA_MYBATIS_DRAFT_PACK_PROMPT_VERSION,
)
from ai_agent_runtime.localization import KOREAN_OUTPUT_INSTRUCTION
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
from ai_agent_runtime.operation_model import (
    SP_OPERATION_PLANNER_OUTPUT_SCHEMA_VERSION,
    SP_OPERATION_PLANNER_PROMPT_VERSION,
)

SYSTEM_PROMPT = f"""You analyze MSSQL stored procedures for a draft-only migration platform.
Return only schema-valid JSON. Treat deterministic metadata and static analysis as evidence.
{KOREAN_OUTPUT_INSTRUCTION}
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
execution, DDL/DML, deployment, decision-gate writes, export creation, secrets, credentials,
raw prompts, or provider responses. Stay within the supplied job, db profile, and target scope.
Prefer the smallest number of tool calls and use structured arguments only. Use the exact
output field names toolRequests, toolName, arguments, reason, expectedEvidenceUse,
assumptions, and reviewMarkers; do not use aliases such as tools, requests, tool, args,
parameters, rationale, or evidenceUse."""

METADATA_ANALYSIS_SYSTEM_PROMPT = f"""You analyze read-only MSSQL metadata evidence for an
AI agent platform. Return only schema-valid JSON. Every insight must use evidenceRefs copied
exactly from evidenceRefContract.allowedFactIds. Do not invent tables, columns, procedures,
views, functions, dependencies, or constraints. Never use prompt hashes, input hashes, output
hashes, raw SQL snippets, row data, or provider trace ids as claim evidence. Mark uncertain
conclusions as REVIEW_REQUIRED. Group object insights by column risk, relationship, index,
constraint, documentation gap, DTO readiness, and dependency categories when supported.
{KOREAN_OUTPUT_INSTRUCTION}
Never request or imply row data access, procedure execution, DDL/DML, deployment, secrets,
credentials, or profile switching."""

SP_OPERATION_PLANNER_SYSTEM_PROMPT = f"""You plan draft-only operation contracts for complex MSSQL
stored procedure Java/MyBatis generation. Return only schema-valid SpOperationModel JSON.
Every evidenceRefs array must use ids copied exactly from evidenceRefContract.allowedFactIds.
Use statementEvidence as deterministic evidence; do not promote LLM inference to metadata fact.
Keep productionReady false and sourcePolicy sanitized_facts_only. Preserve separate DTO blueprints
for query criteria, result rows, commands, batch items, and called procedure request shapes. Never
collapse all procedure inputs/results into one DTO. Mark weak business naming, result-shape
uncertainty, cross-database writes, dynamic SQL, TVF/procedure uncertainty, and called procedure
I/O as REVIEW_REQUIRED. Never include raw SQL snippets, row data, prompt/provider trace ids,
procedure execution, DDL/DML apply, deployment, or secrets.
{KOREAN_OUTPUT_INSTRUCTION}"""

AI_JAVA_MYBATIS_DRAFT_PACK_SYSTEM_PROMPT = f"""You draft Java/MyBatis files for complex MSSQL
stored procedure migration as an AiJavaMyBatisDraftPack.v0.1 JSON object. Return only schema-valid
JSON. Use sanitized draft context, expected file inventory, quality gates, and evidence refs only.
Keep productionReady false and sourcePolicy sanitized_facts_only. Produce multiple DTO_DRAFT files
for query criteria, result rows, commands, batch items, and called procedure request shapes; keep
SERVICE_DRAFT, MAPPER_INTERFACE, and MAPPER_XML as single files. Never create ManageBondDTO or
OperationModelReviewRequired fallback skeletons. Every file must contain non-empty draft content,
operationIds, evidenceRefs copied exactly from evidenceRefContract.allowedFactIds, and reviewMarkers
when facts are weak. Preserve REVIEW_REQUIRED markers for weak business naming, cross-database
writes, called procedure I/O, TVF/procedure uncertainty, result-shape variants, and transaction
boundary uncertainty. Never include raw SP definitions, raw guide body, raw prompts, raw provider
responses, row data, procedure execution, DDL/DML apply, source apply, deployment, or secrets.
{KOREAN_OUTPUT_INSTRUCTION}"""


def render_semantic_analysis_prompt(
    *,
    target_ref: str,
    metadata: dict[str, Any],
    static_analysis: dict[str, Any] | None,
    procedure_definition: str | None,
    source_context: dict[str, Any] | None = None,
    stage: str = "semantic_claims",
    allowed_evidence_refs: list[str] | tuple[str, ...] | None = None,
    required_review_markers: list[dict[str, Any]] | tuple[dict[str, Any], ...] | None = None,
    repair_context: dict[str, Any] | None = None,
) -> RenderedPrompt:
    allowed_refs = sorted(
        {str(ref) for ref in (allowed_evidence_refs or ()) if str(ref).strip()}
    )
    required_markers = list(required_review_markers or ())
    source_context_payload = _source_context_for_prompt(source_context)
    source_context_summary = _source_context_summary(source_context_payload)
    input_payload = {
        "targetRef": target_ref,
        "metadata": _metadata_without_raw_definition(metadata),
        "staticAnalysis": static_analysis,
        "procedureDefinitionHash": text_hash(procedure_definition or ""),
        "procedureDefinitionLength": len(procedure_definition or ""),
        "procedureDefinitionIncluded": (
            procedure_definition is not None and source_context_payload is None
        ),
        "sourceContextIncluded": _source_context_includes_text(source_context_payload),
        "sourceContextSummary": source_context_summary,
        "stage": stage,
        "task": _stage_task(stage),
        "qualityHints": _quality_hints(metadata, static_analysis, allowed_refs),
        "languageContract": {
            "locale": "ko-KR",
            "rule": KOREAN_OUTPUT_INSTRUCTION,
            "preserveIdentifiers": [
                "JSON keys",
                "enum/status/code values",
                "section ids",
                "artifact types",
                "evidence refs",
                "registry refs",
                "SQL identifiers",
                "Java identifiers",
            ],
        },
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
    if source_context_payload is not None:
        input_payload["sourceContext"] = source_context_payload
    elif procedure_definition is not None:
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
            "procedureDefinitionIncluded": bool(input_payload["procedureDefinitionIncluded"]),
            "sourceContextIncluded": bool(input_payload["sourceContextIncluded"]),
            "sourceContextSummary": source_context_summary,
            "stage": stage,
            "allowedEvidenceRefs": allowed_refs,
            "requiredReviewMarkers": required_markers,
        },
    )


def _source_context_for_prompt(source_context: dict[str, Any] | None) -> dict[str, Any] | None:
    if not isinstance(source_context, dict):
        return None
    payload = dict(source_context)
    selected = payload.get("selectedSpans")
    if isinstance(selected, list):
        payload["selectedSpans"] = [dict(item) for item in selected if isinstance(item, dict)]
    return payload


def _source_context_summary(source_context: dict[str, Any] | None) -> dict[str, Any]:
    if not isinstance(source_context, dict):
        return {
            "mode": "NONE",
            "budgetStatus": "NO_SOURCE_CONTEXT",
            "selectedSpanCount": 0,
            "skippedSpanCount": 0,
            "reviewMarkers": [],
        }
    selected = source_context.get("selectedSpans")
    selected_count = len(selected) if isinstance(selected, list) else 0
    return {
        "version": source_context.get("version"),
        "targetRef": source_context.get("targetRef"),
        "stage": source_context.get("stage"),
        "mode": source_context.get("mode", "NONE"),
        "budgetStatus": source_context.get("budgetStatus", "UNKNOWN"),
        "tokenBudget": source_context.get("tokenBudget", 0),
        "estimatedSourceTokens": source_context.get("estimatedSourceTokens", 0),
        "selectedSpanCount": selected_count,
        "skippedSpanCount": int(source_context.get("skippedSpanCount") or 0),
        "analysisCoverage": dict(source_context.get("analysisCoverage") or {}),
        "reviewMarkers": [
            dict(item)
            for item in source_context.get("reviewMarkers", [])
            if isinstance(item, dict)
        ],
    }


def _source_context_includes_text(source_context: dict[str, Any] | None) -> bool:
    selected = source_context.get("selectedSpans") if isinstance(source_context, dict) else None
    return isinstance(selected, list) and any(
        isinstance(item, dict) and bool(item.get("text")) for item in selected
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
    repair_context: dict[str, Any] | None = None,
) -> RenderedPrompt:
    allowed_refs = sorted(
        {str(ref) for ref in (allowed_evidence_refs or ()) if str(ref).strip()}
    )
    input_payload = {
        "targetRef": target_ref,
        "metadata": _metadata_without_raw_definition(metadata),
        "stage": stage,
        "languageContract": {
            "locale": "ko-KR",
            "rule": KOREAN_OUTPUT_INSTRUCTION,
            "preserveIdentifiers": [
                "JSON keys",
                "enum/status/code values",
                "category values",
                "evidence refs",
                "registry refs",
                "SQL identifiers",
                "Java identifiers",
            ],
        },
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
    if repair_context is not None:
        input_payload["repairContext"] = repair_context
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


def render_sp_operation_model_prompt(
    *,
    target_ref: str,
    statement_evidence: list[dict[str, Any]],
    allowed_evidence_refs: list[str] | tuple[str, ...] | None = None,
    stage: str = "operation_model_planning",
    repair_context: dict[str, Any] | None = None,
) -> RenderedPrompt:
    allowed_refs = sorted(
        {str(ref) for ref in (allowed_evidence_refs or ()) if str(ref).strip()}
    )
    input_payload = {
        "targetRef": target_ref,
        "stage": stage,
        "statementEvidence": statement_evidence,
        "task": (
            "Create a SpOperationModel.v0.1 object with branch-level operations, "
            "statementRefs, dtoBlueprintRefs, and multi-DTO blueprints. Keep QUERY and "
            "RESULT DTOs separate from COMMAND, BATCH_ITEM, and CALL_REQUEST DTOs."
        ),
        "dtoBlueprintPolicy": {
            "mustNotCollapseToSingleDto": True,
            "expectedRoles": [
                "QUERY",
                "RESULT",
                "COMMAND",
                "BATCH_ITEM",
                "CALL_REQUEST",
                "CALL_RESULT",
                "REVIEW_REQUIRED",
            ],
            "namingRule": (
                "Name DTOs by business operation and role, for example SearchCriteria, "
                "SearchRow, ApproveCommand, CreateBatchItem, or FinanceCallRequest. "
                "If business names are inferred from branch flags only, keep a "
                "REVIEW_REQUIRED marker."
            ),
        },
        "evidenceRefContract": {
            "allowedFactIds": allowed_refs,
            "factCatalog": _operation_fact_catalog(statement_evidence, allowed_refs),
            "forbiddenEvidenceRefs": [
                "prompt.inputHash",
                "prompt.promptHash",
                "modelInvocation.outputHash",
                "metadata.snapshot",
                "static.analysis",
            ],
            "rule": (
                "Every operation, branchCondition, statement, DTO, and DTO field "
                "evidenceRefs array must contain one or more ids copied exactly from "
                "allowedFactIds. If no allowed fact supports a claim, mark the item "
                "REVIEW_REQUIRED or omit it."
            ),
        },
        "requiredReviewMarkers": _operation_required_review_markers(statement_evidence),
    }
    if repair_context is not None:
        input_payload["repairContext"] = repair_context
    user_prompt = json.dumps(input_payload, ensure_ascii=False, sort_keys=True, default=str)
    prompt_hash = text_hash(f"{SP_OPERATION_PLANNER_SYSTEM_PROMPT}\n{user_prompt}")
    return RenderedPrompt(
        prompt_version=SP_OPERATION_PLANNER_PROMPT_VERSION,
        output_schema_version=SP_OPERATION_PLANNER_OUTPUT_SCHEMA_VERSION,
        system_prompt=SP_OPERATION_PLANNER_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        input_hash=stable_json_hash(input_payload),
        prompt_hash=prompt_hash,
        metadata={
            "targetRef": target_ref,
            "stage": stage,
            "allowedEvidenceRefs": allowed_refs,
            "statementEvidenceCount": len(statement_evidence),
        },
    )


def render_ai_java_mybatis_draft_pack_prompt(
    *,
    target_ref: str,
    sanitized_draft_context: Mapping[str, Any],
    expected_inventory: Sequence[Mapping[str, Any]] | None = None,
    quality_gates: Mapping[str, Any] | None = None,
    allowed_evidence_refs: list[str] | tuple[str, ...] | None = None,
    stage: str = "file_inventory",
    repair_context: dict[str, Any] | None = None,
) -> RenderedPrompt:
    allowed_refs = sorted(
        {str(ref) for ref in (allowed_evidence_refs or ()) if str(ref).strip()}
    )
    inventory = [
        _remove_raw_metadata_fields(json.loads(json.dumps(item, ensure_ascii=False, default=str)))
        for item in list(expected_inventory or [])
        if isinstance(item, Mapping)
    ]
    gates = _remove_raw_metadata_fields(
        json.loads(json.dumps(dict(quality_gates or {}), ensure_ascii=False, default=str))
    )
    context = _remove_raw_metadata_fields(
        json.loads(json.dumps(dict(sanitized_draft_context), ensure_ascii=False, default=str))
    )
    input_payload = {
        "targetRef": target_ref,
        "stage": stage,
        "stagedOutputFlow": [
            "file_inventory",
            "file_content",
            "deterministic_validation",
            "repair",
        ],
        "sanitizedDraftContext": context,
        "expectedInventory": inventory,
        "qualityGates": gates,
        "outputContract": {
            "schemaVersion": "AiJavaMyBatisDraftPack.v0.1",
            "contractTarget": "AiJavaMyBatisDraftPack",
            "finalStructuredOutputRequiresContent": True,
            "productionReady": False,
            "sourcePolicy": "sanitized_facts_only",
        },
        "filePolicy": {
            "artifactTypes": [
                "DTO_DRAFT",
                "SERVICE_DRAFT",
                "MAPPER_INTERFACE",
                "MAPPER_XML",
            ],
            "fileRoles": [
                "QUERY_DTO",
                "RESULT_DTO",
                "COMMAND_DTO",
                "BATCH_ITEM_DTO",
                "CALL_REQUEST_DTO",
                "SERVICE",
                "MAPPER_INTERFACE",
                "MAPPER_XML",
                "REVIEW_REQUIRED",
            ],
            "mustSplitDtoFiles": True,
            "serviceMapperAndXmlSingleFile": True,
            "blockedClassNames": ["OperationModelReviewRequired", "ManageBondDTO"],
            "blockedMarkers": ["P41_OPERATION_MODEL_REVIEW_REQUIRED"],
        },
        "evidenceRefContract": {
            "allowedFactIds": allowed_refs,
            "factCatalog": _draft_pack_fact_catalog(inventory, context, allowed_refs),
            "forbiddenEvidenceRefs": [
                "prompt.inputHash",
                "prompt.promptHash",
                "modelInvocation.outputHash",
                "metadata.snapshot",
                "static.analysis",
            ],
            "rule": (
                "Every root and file evidenceRefs array must contain one or more ids copied "
                "exactly from allowedFactIds. If no allowed fact supports a file or claim, "
                "mark the uncertainty in reviewMarkers and assumptions."
            ),
        },
        "requiredReviewMarkers": _draft_pack_required_review_markers(gates, context),
        "forbiddenStorage": [
            "raw SP definition",
            "raw guide body",
            "raw prompt",
            "raw provider response",
            "row data",
            "secrets",
            "source apply",
            "deployment",
        ],
    }
    if repair_context is not None:
        input_payload["repairContext"] = _remove_raw_metadata_fields(
            json.loads(json.dumps(repair_context, ensure_ascii=False, default=str))
        )
    user_prompt = json.dumps(input_payload, ensure_ascii=False, sort_keys=True, default=str)
    prompt_hash = text_hash(f"{AI_JAVA_MYBATIS_DRAFT_PACK_SYSTEM_PROMPT}\n{user_prompt}")
    return RenderedPrompt(
        prompt_version=AI_JAVA_MYBATIS_DRAFT_PACK_PROMPT_VERSION,
        output_schema_version=AI_JAVA_MYBATIS_DRAFT_PACK_OUTPUT_SCHEMA_VERSION,
        system_prompt=AI_JAVA_MYBATIS_DRAFT_PACK_SYSTEM_PROMPT,
        user_prompt=user_prompt,
        input_hash=stable_json_hash(input_payload),
        prompt_hash=prompt_hash,
        metadata={
            "targetRef": target_ref,
            "stage": stage,
            "allowedEvidenceRefs": allowed_refs,
            "expectedFileCount": len(inventory),
            "qualityGateCount": len(gates),
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
                "raw_sp_definition",
                "raw_prompt",
                "raw_provider_response",
                "raw_provider_response_text",
                "raw_openai_response_text",
                "raw_guide_body",
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


def _draft_pack_fact_catalog(
    expected_inventory: Sequence[Mapping[str, Any]],
    sanitized_draft_context: Mapping[str, Any],
    allowed_refs: list[str],
) -> list[dict[str, str]]:
    catalog: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in expected_inventory:
        refs = item.get("evidenceRefs")
        if not isinstance(refs, list):
            continue
        summary = (
            f"{item.get('artifactType', 'FILE')} {item.get('path', '')} "
            f"class={item.get('className', '')} role={item.get('role', '')}"
        )
        for ref in refs:
            ref_text = str(ref)
            if ref_text not in allowed_refs or ref_text in seen:
                continue
            seen.add(ref_text)
            catalog.append(
                {
                    "id": ref_text,
                    "type": "AI_DRAFT_PACK_FILE_EVIDENCE",
                    "summary": summary.strip(),
                }
            )
    context_facts = sanitized_draft_context.get("deterministicFacts")
    if isinstance(context_facts, list):
        for fact in context_facts:
            if not isinstance(fact, Mapping):
                continue
            fact_id = str(fact.get("id") or "")
            if fact_id not in allowed_refs or fact_id in seen:
                continue
            seen.add(fact_id)
            catalog.append(
                {
                    "id": fact_id,
                    "type": str(fact.get("type") or "DETERMINISTIC_EVIDENCE"),
                    "summary": str(fact.get("summary") or "Sanitized deterministic evidence."),
                }
            )
    for ref in allowed_refs:
        if ref in seen:
            continue
        catalog.append(
            {
                "id": ref,
                "type": "DETERMINISTIC_EVIDENCE",
                "summary": "Sanitized AI draft pack evidence.",
            }
        )
    return catalog


def _draft_pack_required_review_markers(
    quality_gates: Mapping[str, Any],
    sanitized_draft_context: Mapping[str, Any],
) -> list[dict[str, Any]]:
    raw_markers = (
        quality_gates.get("requiredReviewMarkers")
        or quality_gates.get("required_review_markers")
        or sanitized_draft_context.get("reviewRequiredFacts")
        or sanitized_draft_context.get("review_required_facts")
        or []
    )
    markers: list[dict[str, Any]] = []
    seen: set[str] = set()
    if isinstance(raw_markers, list):
        for marker in raw_markers:
            code = str(marker)
            if not code or code in seen:
                continue
            seen.add(code)
            markers.append({"code": code, "status": "REVIEW_REQUIRED"})
    return markers


def _operation_fact_catalog(
    statement_evidence: list[dict[str, Any]],
    allowed_refs: list[str],
) -> list[dict[str, str]]:
    catalog: list[dict[str, str]] = []
    seen: set[str] = set()
    for statement in statement_evidence:
        if not isinstance(statement, dict):
            continue
        refs = statement.get("evidenceRefs")
        if not isinstance(refs, list):
            continue
        summary = (
            f"{statement.get('operation', 'STATEMENT')} {statement.get('targetRef', '')} "
            f"phase={statement.get('phase', '')}"
        )
        for ref in refs:
            ref_text = str(ref)
            if ref_text not in allowed_refs or ref_text in seen:
                continue
            seen.add(ref_text)
            catalog.append(
                {
                    "id": ref_text,
                    "type": "STATEMENT_EVIDENCE",
                    "summary": summary.strip(),
                }
            )
    for ref in allowed_refs:
        if ref not in seen:
            catalog.append(
                {
                    "id": ref,
                    "type": "DETERMINISTIC_EVIDENCE",
                    "summary": "Additional deterministic operation-model evidence.",
                }
            )
    return catalog


def _operation_required_review_markers(
    statement_evidence: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    markers: list[dict[str, Any]] = []
    seen: set[str] = set()
    for statement in statement_evidence:
        if not isinstance(statement, dict):
            continue
        refs = [
            str(ref)
            for ref in statement.get("evidenceRefs", [])
            if str(ref).strip()
        ]
        for marker in statement.get("reviewMarkers", []) or []:
            marker_code = str(marker)
            if not marker_code or marker_code in seen:
                continue
            seen.add(marker_code)
            markers.append(
                {
                    "code": marker_code,
                    "status": "REVIEW_REQUIRED",
                    "evidenceRefs": refs[:1],
                }
            )
    if "LLM_BUSINESS_NAMING_REVIEW_REQUIRED" not in seen:
        markers.append(
            {
                "code": "LLM_BUSINESS_NAMING_REVIEW_REQUIRED",
                "status": "REVIEW_REQUIRED",
                "evidenceRefs": [],
            }
        )
    return markers


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
    if stage == "language_repair":
        return (
            "Translate human-readable free-text fields to Korean (ko-KR) while preserving "
            "all machine contract identifiers, evidenceRefs, statuses, codes, and section ids."
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
