from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from ai_agent_runtime.ai_draft_pack import (
    AI_JAVA_MYBATIS_DRAFT_PACK_OUTPUT_SCHEMA_VERSION,
    AI_JAVA_MYBATIS_DRAFT_PACK_PROMPT_VERSION,
    AI_JAVA_MYBATIS_DRAFT_PACK_ROLE_STAGES,
    AI_JAVA_MYBATIS_DRAFT_PACK_STAGE_OUTPUT_SCHEMA_VERSION,
    AI_JAVA_MYBATIS_DRAFT_PACK_STAGE_SCHEMA_VERSION,
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
Use exact JSON keys from the output contract only. Operation objects use riskMarkers, not
reviewMarkers. Branch conditions use evidenceRefs, not evidence_refs. DTO fields use dbType, not
db_type. Do not add koreanName, localizedName, explanation, notes, confidence, or other helper
fields; put uncertain text into summary, assumptions, or REVIEW_REQUIRED markers.
Every statementEvidence item must be referenced by at least one operation.statementRefs entry.
Split operations by distinct branch predicates and business use-cases. Do not merge unrelated
CRUD, approval, create, update, delete, vendor, online, batch, or called-procedure responsibilities
into a single operation. DTO blueprint names should use the target-derived business stem and
use-case role, not only generic CrudR/CrudC/CrudU names when better branch evidence exists.
{KOREAN_OUTPUT_INSTRUCTION}"""

AI_JAVA_MYBATIS_DRAFT_PACK_SYSTEM_PROMPT = f"""You draft Java/MyBatis files for complex MSSQL
stored procedure migration as an AiJavaMyBatisDraftPack.v0.1 JSON object. Return only schema-valid
JSON. Use sanitized draft context, expected file inventory, quality gates, and evidence refs only.
Keep productionReady false and sourcePolicy sanitized_facts_only. Produce multiple DTO_DRAFT files
for query criteria, result rows, commands, batch items, and called procedure request shapes; keep
SERVICE_DRAFT, MAPPER_INTERFACE, and MAPPER_XML as single files. Never create procedure-wide
single DTO collapse or OperationModelReviewRequired fallback skeletons. Every file must contain
non-empty draft content,
operationIds, evidenceRefs copied exactly from evidenceRefContract.allowedFactIds, and reviewMarkers
when facts are weak. Use draftPackEvidenceBundle as the authoritative generic coverage plan:
operationCoverageMatrix drives method coverage, dtoResponsibilityMatrix drives DTO separation,
reviewMarkerContract drives required caveats, and mapperCoverageContract drives Service/Mapper/XML
wiring. Do not satisfy quality by copying benchmark-specific class names; use roles, operation ids,
statement refs, and deterministic responsibilities. Preserve REVIEW_REQUIRED markers for weak
business naming, cross-database
writes, called procedure I/O, TVF/procedure uncertainty, result-shape variants, and transaction
boundary uncertainty. The non-DTO files are aggregate files: use the expectedInventory path and
className exactly for the single Service, Mapper interface, and Mapper XML, and put every required
method from qualityGates into those aggregate files. Never create use-case-specific Service or
Mapper files. Never include raw SP definitions, raw guide body, raw prompts, raw provider
responses, row data, procedure execution, DDL/DML apply, source apply, deployment, or secrets.
{KOREAN_OUTPUT_INSTRUCTION}"""

DRAFT_PACK_EVIDENCE_BUNDLE_VERSION = "DraftPackEvidenceBundle.v0.1"
AI_DRAFT_PACK_COMPOSER_STAGES = (
    "dto_inventory",
    "dto_content",
    "service_content",
    "mapper_interface_content",
    "mapper_xml_content",
    "integration_quality_gate",
    "repair",
)


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
    task_mode: str = "final_model",
    branch_plan_context: Mapping[str, Any] | None = None,
    stage: str = "operation_model_planning",
    repair_context: dict[str, Any] | None = None,
) -> RenderedPrompt:
    allowed_refs = sorted(
        {str(ref) for ref in (allowed_evidence_refs or ()) if str(ref).strip()}
    )
    input_payload = {
        "targetRef": target_ref,
        "stage": stage,
        "taskMode": task_mode,
        "taskModeInstructions": _operation_task_mode_instruction(task_mode),
        "statementEvidence": statement_evidence,
        "branchPlanContext": dict(branch_plan_context or {}),
        "task": (
            "Create a SpOperationModel.v0.1 object with branch-level operations, "
            "statementRefs, dtoBlueprintRefs, and multi-DTO blueprints. Keep QUERY and "
            "RESULT DTOs separate from COMMAND, BATCH_ITEM, and CALL_REQUEST DTOs."
        ),
        "operationSeparationPolicy": {
            "mustCoverEveryStatementEvidenceId": True,
            "statementCoverageRule": (
                "Every statementEvidence[].statementId must appear in at least one "
                "operations[].statementRefs array. If a statement is initialization, "
                "cleanup, dynamic SQL, or a called-procedure bridge, create a distinct "
                "REVIEW_REQUIRED operation instead of omitting it."
            ),
            "splitByDistinctBranchCondition": True,
            "splitByDistinctCrudOrUseCase": True,
            "branchCoverage": _operation_branch_contract(statement_evidence),
            "namingRule": (
                "Derive a stable Java business stem from the procedure name by removing "
                "schema/company prefixes and procedure suffixes, then append use-case "
                "and DTO role words. Avoid DTO names that are only CrudR, CrudC, CrudU, "
                "CrudD, or similar generic flags when branch/use-case evidence exists."
            ),
        },
        "outputContract": {
            "schemaVersion": "SpOperationModel.v0.1",
            "contractTarget": "SpOperationModel",
            "productionReady": False,
            "sourcePolicy": "sanitized_facts_only",
            "rootKeys": [
                "schemaVersion",
                "contractTarget",
                "targetRef",
                "sourcePolicy",
                "productionReady",
                "operations",
                "statementEvidence",
                "dtoBlueprints",
                "reviewMarkers",
                "evidenceRefs",
                "assumptions",
            ],
            "operationKeys": [
                "operationId",
                "crudFlag",
                "title",
                "summary",
                "branchCondition",
                "statementRefs",
                "dtoBlueprintRefs",
                "stateTransitions",
                "riskMarkers",
                "evidenceRefs",
                "status",
            ],
            "branchConditionKeys": ["expression", "variables", "evidenceRefs", "status"],
            "statementKeys": [
                "statementId",
                "operation",
                "targetRef",
                "phase",
                "inputs",
                "outputs",
                "writes",
                "crossDatabase",
                "reviewMarkers",
                "evidenceRefs",
                "status",
            ],
            "dtoBlueprintKeys": [
                "name",
                "role",
                "operationIds",
                "fields",
                "evidenceRefs",
                "reviewMarkers",
            ],
            "dtoFieldKeys": ["name", "dbType", "source", "required", "evidenceRefs"],
            "forbiddenHelperKeys": [
                "koreanName",
                "localizedName",
                "explanation",
                "notes",
                "confidence",
            ],
        },
        "dtoBlueprintPolicy": {
            "mustNotCollapseToSingleDto": True,
            "dtoBlueprintRefsAreInventoryContract": True,
            "branchPlanContextIsInventoryFloor": bool(branch_plan_context),
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
            "referenceRule": (
                "Every operations[].dtoBlueprintRefs entry is a required DTO blueprint. "
                "When branchPlanContext.dtoBlueprints contains the name, copy or merge that "
                "DTO rather than dropping it."
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
            "taskMode": task_mode,
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
    non_dto_inventory = [
        item
        for item in inventory
        if item.get("artifactType") in {"SERVICE_DRAFT", "MAPPER_INTERFACE", "MAPPER_XML"}
    ]
    stage_expected_inventory = _ai_draft_pack_stage_expected_inventory(stage, inventory)
    evidence_bundle = build_draft_pack_evidence_bundle(
        sanitized_draft_context=context,
        expected_inventory=inventory,
        quality_gates=gates,
        allowed_evidence_refs=allowed_refs,
    )
    input_payload = {
        "targetRef": target_ref,
        "stage": stage,
        "stageTask": _ai_draft_pack_stage_task(stage),
        "stagedOutputFlow": list(AI_DRAFT_PACK_COMPOSER_STAGES),
        "sanitizedDraftContext": context,
        "draftPackEvidenceBundle": evidence_bundle,
        "operationCoverageMatrix": evidence_bundle["operationCoverageMatrix"],
        "dtoResponsibilityMatrix": evidence_bundle["dtoResponsibilityMatrix"],
        "reviewMarkerContract": evidence_bundle["reviewMarkerContract"],
        "mapperCoverageContract": evidence_bundle["mapperCoverageContract"],
        "expectedInventory": inventory,
        "stageExpectedInventory": stage_expected_inventory,
        "qualityGates": gates,
        "outputContract": _ai_draft_pack_output_contract(
            stage,
            stage_expected_inventory=stage_expected_inventory,
        ),
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
            "blockedClassNames": ["OperationModelReviewRequired"],
            "blockedMarkers": ["P41_OPERATION_MODEL_REVIEW_REQUIRED"],
            "exactExpectedFileCount": len(inventory),
            "exactStageExpectedFileCount": len(stage_expected_inventory),
            "exactExpectedInventoryRequired": True,
            "stageExactInventoryRequired": stage in AI_JAVA_MYBATIS_DRAFT_PACK_ROLE_STAGES,
            "genericCoverageFirst": True,
            "benchmarkNamesAreNotAnswerKeys": True,
            "composerStages": list(AI_DRAFT_PACK_COMPOSER_STAGES),
            "composerRule": (
                "Plan DTO inventory first, then draft DTO content, Service orchestration, "
                "Mapper interface signatures, Mapper XML database statements, and finally "
                "run integration quality checks before any repair."
            ),
            "nonDtoAggregatePolicy": {
                "exactFiles": non_dto_inventory,
                "rule": (
                    "Return exactly these Service/Mapper/MapperXML path and className values. "
                    "They are aggregate files and must include every method listed in "
                    "qualityGates.requiredServiceMethods and qualityGates.requiredMapperMethods."
                ),
                "blocked": (
                    "Do not create use-case-specific Service, Mapper interface, or Mapper XML "
                    "files such as ReadService, CreateMapper, or per-branch XML files."
                ),
            },
            "methodCoveragePolicy": {
                "requiredServiceMethods": gates.get("requiredServiceMethods", []),
                "requiredMapperMethods": gates.get("requiredMapperMethods", []),
                "rule": (
                    "Each required service method token must appear in the SERVICE_DRAFT "
                    "content. Each required mapper method token must appear in both the "
                    "MAPPER_INTERFACE content and the MAPPER_XML statement ids."
                ),
            },
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
        output_schema_version=(
            AI_JAVA_MYBATIS_DRAFT_PACK_STAGE_OUTPUT_SCHEMA_VERSION
            if stage in AI_JAVA_MYBATIS_DRAFT_PACK_ROLE_STAGES
            else AI_JAVA_MYBATIS_DRAFT_PACK_OUTPUT_SCHEMA_VERSION
        ),
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
            "evidenceBundleVersion": DRAFT_PACK_EVIDENCE_BUNDLE_VERSION,
        },
    )


def _ai_draft_pack_output_contract(
    stage: str,
    *,
    stage_expected_inventory: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    file_keys = [
        "artifactType",
        "path",
        "role",
        "className",
        "content",
        "operationIds",
        "evidenceRefs",
        "reviewMarkers",
        "dtoRole",
        "requiredFields",
        "references",
    ]
    if stage in AI_JAVA_MYBATIS_DRAFT_PACK_ROLE_STAGES:
        stage_artifacts = {
            "dto_inventory": ["DTO_DRAFT"],
            "dto_content": ["DTO_DRAFT"],
            "service_content": ["SERVICE_DRAFT"],
            "mapper_interface_content": ["MAPPER_INTERFACE"],
            "mapper_xml_content": ["MAPPER_XML"],
        }[stage]
        return {
            "schemaVersion": AI_JAVA_MYBATIS_DRAFT_PACK_STAGE_SCHEMA_VERSION,
            "contractTarget": "AiJavaMyBatisDraftPackStage",
            "stage": stage,
            "stageStructuredOutputRequiresContent": True,
            "allowedArtifactTypesForStage": stage_artifacts,
            "productionReady": False,
            "sourcePolicy": "sanitized_facts_only",
            "rootKeys": [
                "schemaVersion",
                "contractTarget",
                "targetRef",
                "stage",
                "sourcePolicy",
                "productionReady",
                "files",
                "evidenceRefs",
                "reviewMarkers",
                "assumptions",
            ],
            "fileKeys": file_keys,
            "composerRule": (
                "Return only this stage's file slice. The deterministic composer will merge "
                "role-stage files into AiJavaMyBatisDraftPack.v0.1 and run integration checks."
            ),
            "exactStageExpectedFiles": stage_expected_inventory,
        }
    return {
        "schemaVersion": "AiJavaMyBatisDraftPack.v0.1",
        "contractTarget": "AiJavaMyBatisDraftPack",
        "finalStructuredOutputRequiresContent": True,
        "productionReady": False,
        "sourcePolicy": "sanitized_facts_only",
        "rootKeys": [
            "schemaVersion",
            "contractTarget",
            "targetRef",
            "sourcePolicy",
            "productionReady",
            "files",
            "evidenceRefs",
            "reviewMarkers",
            "qualityGates",
            "assumptions",
        ],
        "fileKeys": file_keys,
    }


def _ai_draft_pack_stage_expected_inventory(
    stage: str,
    inventory: Sequence[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    stage_artifacts = {
        "dto_inventory": {"DTO_DRAFT"},
        "dto_content": {"DTO_DRAFT"},
        "service_content": {"SERVICE_DRAFT"},
        "mapper_interface_content": {"MAPPER_INTERFACE"},
        "mapper_xml_content": {"MAPPER_XML"},
    }.get(stage)
    if not stage_artifacts:
        return [dict(item) for item in inventory]
    return [
        dict(item)
        for item in inventory
        if str(item.get("artifactType") or "") in stage_artifacts
    ]


def build_draft_pack_evidence_bundle(
    *,
    sanitized_draft_context: Mapping[str, Any],
    expected_inventory: Sequence[Mapping[str, Any]],
    quality_gates: Mapping[str, Any],
    allowed_evidence_refs: Sequence[str],
) -> dict[str, Any]:
    operations = _sequence_of_mappings(sanitized_draft_context.get("operations"))
    statement_evidence = _sequence_of_mappings(sanitized_draft_context.get("statementEvidence"))
    dependency_summary = _safe_summary_mapping(
        sanitized_draft_context.get("dependencyEvidenceSummary")
    )
    platform_summary = _safe_summary_mapping(
        sanitized_draft_context.get("platformToolEvidenceSummary")
    )
    ai_tool_summary = _safe_summary_mapping(
        sanitized_draft_context.get("aiToolEvidenceSummary")
    )
    p51_projection = _p51_evidence_projection_summary(sanitized_draft_context)
    return {
        "version": DRAFT_PACK_EVIDENCE_BUNDLE_VERSION,
        "evidenceRefCount": len(tuple(dict.fromkeys(map(str, allowed_evidence_refs)))),
        "operationCoverageMatrix": _operation_coverage_matrix(
            operations=operations,
            statement_evidence=statement_evidence,
            expected_inventory=expected_inventory,
            quality_gates=quality_gates,
        ),
        "dtoResponsibilityMatrix": _dto_responsibility_matrix(expected_inventory),
        "reviewMarkerContract": _review_marker_contract(
            quality_gates=quality_gates,
            sanitized_draft_context=sanitized_draft_context,
            statement_evidence=statement_evidence,
        ),
        "mapperCoverageContract": _mapper_coverage_contract(
            expected_inventory=expected_inventory,
            quality_gates=quality_gates,
        ),
        "supportingEvidenceSummaries": {
            "dependencyEvidenceSummary": dependency_summary,
            "platformToolEvidenceSummary": platform_summary,
            "aiToolEvidenceSummary": ai_tool_summary,
            "p51EvidenceProjection": p51_projection,
        },
        "qualityPrinciple": (
            "Improve generic operation, DTO, mapper, and REVIEW_REQUIRED coverage. "
            "Named benchmark procedures may appear in evidence, but their DTO names are "
            "comparison signals only and must not be treated as runtime answer keys."
        ),
    }


def _p51_evidence_projection_summary(
    sanitized_draft_context: Mapping[str, Any],
) -> dict[str, Any]:
    explicit = sanitized_draft_context.get("p51EvidenceProjection")
    if isinstance(explicit, Mapping):
        return _bounded_json_summary(explicit)
    result: dict[str, Any] = {}
    for source_key, target_key in (
        ("sql_statement_evidence", "sql_statement_evidence"),
        ("sqlStatementEvidence", "sql_statement_evidence"),
        ("java_mybatis_evidence", "java_mybatis_evidence"),
        ("javaMybatisEvidence", "java_mybatis_evidence"),
        ("semantic_inference_evidence", "semantic_inference_evidence"),
        ("semanticInferenceEvidence", "semantic_inference_evidence"),
        ("evidence_map", "evidence_map"),
        ("evidenceMap", "evidence_map"),
    ):
        value = sanitized_draft_context.get(source_key)
        if value is None or target_key in result:
            continue
        result[target_key] = _bounded_json_summary(value)
    return result


def _bounded_json_summary(value: Any, *, limit: int = 40) -> Any:
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for index, (key, item) in enumerate(value.items()):
            if index >= limit:
                result["truncated"] = True
                break
            result[str(key)] = _bounded_json_summary(item, limit=limit)
        return result
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return [_bounded_json_summary(item, limit=limit) for item in list(value)[:limit]]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def _ai_draft_pack_stage_task(stage: str) -> str:
    if stage == "dto_inventory":
        return "Derive DTO file inventory from DML, SP/FN parameters, result fields, and call I/O."
    if stage == "dto_content":
        return "Draft DTO fields and accessors from the DTO responsibility matrix."
    if stage == "service_content":
        return "Draft Service business orchestration and mapper calls without SQL text."
    if stage == "mapper_interface_content":
        return "Draft Mapper interface signatures matching Service calls and XML ids."
    if stage == "mapper_xml_content":
        return "Draft Mapper XML DB-facing DML and call statements from statement evidence."
    if stage == "integration_quality_gate":
        return "Check DTO, Service, Mapper interface, and Mapper XML consistency before repair."
    if stage == "file_inventory":
        return (
            "Verify the expected inventory against generic operation, DTO responsibility, "
            "review marker, and mapper coverage contracts before drafting content."
        )
    if stage == "file_content":
        return (
            "Draft every expected file using the bundle matrices. Preserve exact paths, "
            "class names, operation ids, evidence refs, and required REVIEW_REQUIRED markers."
        )
    if stage == "repair":
        return (
            "Repair only schema, inventory, DTO separation, method wiring, evidence ref, "
            "and REVIEW_REQUIRED coverage failures described by sanitized diagnostics."
        )
    return (
        "Produce draft-only Java/MyBatis structured output from sanitized deterministic "
        "evidence."
    )


def _operation_coverage_matrix(
    *,
    operations: Sequence[Mapping[str, Any]],
    statement_evidence: Sequence[Mapping[str, Any]],
    expected_inventory: Sequence[Mapping[str, Any]],
    quality_gates: Mapping[str, Any],
) -> list[dict[str, Any]]:
    statements_by_operation = _statements_by_operation(statement_evidence)
    inventory_by_operation = _inventory_by_operation(expected_inventory)
    required_service = set(_strings(quality_gates.get("requiredServiceMethods")))
    required_mapper = set(_strings(quality_gates.get("requiredMapperMethods")))
    operation_ids = _deduped(
        [
            *_ids_from_mapping_items(operations, "operationId"),
            *inventory_by_operation.keys(),
            *required_service,
            *required_mapper,
        ]
    )
    return [
        {
            "operationId": operation_id,
            "statementRefs": statements_by_operation.get(operation_id, []),
            "expectedFilePaths": inventory_by_operation.get(operation_id, []),
            "requiresServiceMethod": operation_id in required_service,
            "requiresMapperMethod": operation_id in required_mapper,
            "coverageRule": (
                "This operation id must be represented in relevant DTO files and in the "
                "aggregate Service, Mapper interface, and Mapper XML when method flags are true."
            ),
        }
        for operation_id in operation_ids
        if operation_id
    ]


def _dto_responsibility_matrix(
    expected_inventory: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    result = []
    for item in expected_inventory:
        if str(item.get("artifactType") or "") != "DTO_DRAFT":
            continue
        result.append(
            {
                "path": str(item.get("path") or ""),
                "className": str(item.get("className") or ""),
                "role": str(item.get("role") or ""),
                "dtoRole": str(item.get("dtoRole") or item.get("role") or ""),
                "operationIds": _strings(item.get("operationIds")),
                "requiredFields": _strings(item.get("requiredFields")),
                "reviewMarkers": _strings(item.get("reviewMarkers")),
                "separationRule": (
                    "Keep this DTO responsibility separate unless another expected inventory "
                    "item explicitly shares the same path and className."
                ),
            }
        )
    return result


def _review_marker_contract(
    *,
    quality_gates: Mapping[str, Any],
    sanitized_draft_context: Mapping[str, Any],
    statement_evidence: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    statement_markers: list[str] = []
    for statement in statement_evidence:
        statement_markers.extend(_strings(statement.get("reviewMarkers")))
    markers = _deduped(
        [
            *_strings(quality_gates.get("requiredReviewMarkers")),
            *_strings(sanitized_draft_context.get("reviewRequiredFacts")),
            *_strings(
                _mapping(sanitized_draft_context.get("operationModelSummary")).get(
                    "reviewMarkers"
                )
            ),
            *statement_markers,
        ]
    )
    return {
        "requiredMarkers": markers,
        "rule": (
            "Every marker must appear at the root or relevant file reviewMarkers and weak facts "
            "must remain REVIEW_REQUIRED instead of being converted to confident implementation "
            "claims."
        ),
    }


def _mapper_coverage_contract(
    *,
    expected_inventory: Sequence[Mapping[str, Any]],
    quality_gates: Mapping[str, Any],
) -> dict[str, Any]:
    non_dto = [
        {
            "artifactType": str(item.get("artifactType") or ""),
            "path": str(item.get("path") or ""),
            "className": str(item.get("className") or ""),
            "references": _strings(item.get("references")),
            "operationIds": _strings(item.get("operationIds")),
        }
        for item in expected_inventory
        if str(item.get("artifactType") or "")
        in {"SERVICE_DRAFT", "MAPPER_INTERFACE", "MAPPER_XML"}
    ]
    return {
        "aggregateFiles": non_dto,
        "requiredServiceMethods": _strings(quality_gates.get("requiredServiceMethods")),
        "requiredMapperMethods": _strings(quality_gates.get("requiredMapperMethods")),
        "rule": (
            "Use one aggregate Service, one aggregate Mapper interface, and one aggregate "
            "Mapper XML. Each required mapper method must appear as a Java mapper method "
            "and XML statement id."
        ),
    }


def _statements_by_operation(
    statement_evidence: Sequence[Mapping[str, Any]],
) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for statement in statement_evidence:
        operation = str(statement.get("operation") or statement.get("operationId") or "")
        statement_id = str(statement.get("statementId") or "")
        if operation and statement_id:
            result.setdefault(operation, []).append(statement_id)
    return {key: _deduped(value) for key, value in result.items()}


def _inventory_by_operation(
    expected_inventory: Sequence[Mapping[str, Any]],
) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for item in expected_inventory:
        path = str(item.get("path") or "")
        for operation_id in _strings(item.get("operationIds")):
            if path:
                result.setdefault(operation_id, []).append(path)
    return {key: _deduped(value) for key, value in result.items()}


def _safe_summary_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {
        str(key): item
        for key, item in value.items()
        if isinstance(item, str | int | float | bool)
        or (
            isinstance(item, Sequence)
            and not isinstance(item, str | bytes)
            and all(isinstance(seq_item, str | int | float | bool) for seq_item in item)
        )
    }


def _sequence_of_mappings(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _ids_from_mapping_items(items: Sequence[Mapping[str, Any]], key: str) -> list[str]:
    return _deduped(str(item.get(key) or "") for item in items)


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _strings(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return []
    return _deduped(str(item) for item in value if item is not None and str(item).strip())


def _deduped(values: Sequence[str] | Any) -> list[str]:
    return list(dict.fromkeys(str(value) for value in values if str(value).strip()))


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


def _operation_branch_contract(statement_evidence: list[dict[str, Any]]) -> dict[str, Any]:
    statement_ids: list[str] = []
    phases: list[str] = []
    operation_types: list[str] = []
    branch_like_phases: list[str] = []
    branch_keywords = (
        "crud",
        "flag",
        "kind",
        "type",
        "status",
        "gubun",
        "mode",
        "value",
        "approval",
        "vendor",
        "online",
        "batch",
    )
    for statement in statement_evidence:
        if not isinstance(statement, dict):
            continue
        statement_id = str(statement.get("statementId") or "")
        phase = str(statement.get("phase") or "")
        operation = str(statement.get("operation") or "")
        if statement_id:
            statement_ids.append(statement_id)
        if phase and phase not in phases:
            phases.append(phase)
        if operation and operation not in operation_types:
            operation_types.append(operation)
        if phase and any(keyword in phase.lower() for keyword in branch_keywords):
            if phase not in branch_like_phases:
                branch_like_phases.append(phase)
    return {
        "statementIds": statement_ids,
        "distinctPhaseCount": len(phases),
        "operationTypes": operation_types,
        "branchLikePhases": branch_like_phases,
        "coverageRule": (
            "Use these ids as the complete deterministic statement coverage set. "
            "Operation grouping may be higher-level, but coverage must be total and "
            "branch-like phases should not be collapsed into one method/DTO responsibility."
        ),
    }


def _operation_task_mode_instruction(task_mode: str) -> dict[str, Any]:
    if task_mode == "branch_plan":
        return {
            "goal": (
                "First stabilize branch/use-case grouping before final DTO assembly."
            ),
            "requirements": [
                "Cover every deterministic statementEvidence[].statementId.",
                "Split CRUD, GUBUN, SValue, status, approval, batch, EXEC bridge, and DML branches.",
                "Create branch-level operationIds and DTO responsibility candidates.",
                "Every operations[].dtoBlueprintRefs value must exactly match a dtoBlueprints[].name.",
                "Every dtoBlueprints[].operationIds value must exactly match an operations[].operationId.",
                "Return schema-valid SpOperationModel.v0.1; do not return prose or helper objects.",
            ],
        }
    if task_mode == "repair":
        return {
            "goal": (
                "Repair a previous operation-model attempt using only validator findings."
            ),
            "requirements": [
                "Do not depend on failed provider payload text.",
                "Use repairContext.validationFindings and repairContext.missingDtoBlueprintRefs as constraints to satisfy.",
                "If an operation references a DTO, dtoBlueprints must include that DTO or preserve it from branchPlanContext.",
                "Preserve total statement coverage and allowed evidenceRefs discipline.",
                "Return a complete schema-valid SpOperationModel.v0.1 object.",
            ],
        }
    return {
        "goal": "Assemble the final branch-level operation model for Java/MyBatis drafting.",
        "requirements": [
            "Use branchPlanContext when present as the sanitized DTO inventory floor, not optional guidance.",
            "Connect every operation to statementRefs and dtoBlueprintRefs.",
            "Do not delete or collapse branchPlanContext.dtoBlueprints while assembling the final model.",
            "Create separate QUERY, RESULT, COMMAND, BATCH_ITEM, and CALL_REQUEST DTOs when evidence supports them.",
            "Keep weak inferences as REVIEW_REQUIRED markers instead of collapsing responsibilities.",
        ],
    }


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
