from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from ai_agent_generation.utils import (
    ensure_trailing_newline,
    java_imports_for_types,
    java_type_for_db_type,
    snake_to_lower_camel,
    upper_first,
)
from ai_agent_runtime.gateway import (
    ModelGateway,
    ModelGatewayError,
    build_model_gateway_from_env,
    model_profile_from_env,
)
from ai_agent_runtime.models import (
    AiToolPlanningOutput,
    RenderedPrompt,
    stable_json_hash,
)
from mssql_mcp_app.errors import MetadataToolError

from api_app.ai_tool_orchestrator import (
    _build_internal_registry,
    _dedupe_strings,
    _review_marker,
    _safe_dict,
)
from api_app.metadata_service import MetadataSearchDependencyError, repo_root
from api_app.repositories import WorkflowRepository
from api_app.schemas import (
    MetadataAnalysisReviewMarker,
    MetadataDesignFieldInput,
    MetadataDesignResult,
    MetadataDesignRunRequest,
    MetadataGeneratedDraft,
    MetadataRelatedMetadata,
    MetadataStandardizationMapping,
    MetadataTableProposal,
    MetadataTableProposalColumn,
    ModelInvocationSummary,
)
from api_app.target_keys import target_key_for_target

DESIGN_PROMPT_VERSION = "prompt:metadata_design_chat_intent@0.1.0"
DESIGN_OUTPUT_SCHEMA_VERSION = "schema:mssql_metadata_tool_plan@0.1.0"
POLICY_REF = "policy:platform_db_standardization_rules_for_ai@1.0"
REVIEW_REQUIRED = "REVIEW_REQUIRED"
FORBIDDEN_TEXT_RE = re.compile(
    (
        r"(password|secret|token|api[_-]?key|connection\s*string|row\s*data|"
        r"raw\s+(prompt|sql|provider)|full\s+(definition|sql)|"
        r"select\s+\*|drop\s+table|truncate\s+table|exec(?:ute)?\s+)"
    ),
    re.IGNORECASE,
)
IDENTIFIER_CLEANUP_RE = re.compile(r"[^0-9A-Za-z_]+")
MESSAGE_SPLIT_RE = re.compile(r"[\n,;/]+")


@dataclass(frozen=True)
class ToolEnvelope:
    tool_name: str
    status: str
    response: dict[str, Any]
    evidence_refs: tuple[str, ...]
    result_count: int
    error_code: str | None = None


@dataclass(frozen=True)
class CandidateContext:
    tool_results: tuple[ToolEnvelope, ...]
    related_metadata: tuple[MetadataRelatedMetadata, ...]
    deterministic_facts: tuple[dict[str, Any], ...]
    caveats: tuple[str, ...]


class MetadataDesignChatService:
    def __init__(
        self,
        *,
        model_gateway: ModelGateway | None = None,
        repository: WorkflowRepository | None = None,
    ) -> None:
        self.model_gateway = model_gateway or build_model_gateway_from_env()
        self.repository = repository
        self._policy = _load_standardization_policy()

    def design(self, request: MetadataDesignRunRequest) -> MetadataDesignResult:
        fields = _normalized_field_inputs(request)
        model_invocation, planner_component, planner_caveats = _run_design_planner(
            request,
            fields=fields,
            model_gateway=self.model_gateway,
        )
        candidate_context = _collect_metadata_candidates(
            request,
            fields=fields,
            max_candidates=request.options.max_candidates,
        )
        mappings = _build_standardization_mappings(
            fields,
            candidate_context=candidate_context,
            policy=self._policy,
        )
        table_proposal = _build_table_proposal(
            request,
            mappings=mappings,
            policy=self._policy,
        )
        dto_draft = (
            _build_dto_draft(table_proposal)
            if request.options.generate_dto_draft
            else None
        )
        caveats = _dedupe_strings(
            [
                *candidate_context.caveats,
                *planner_caveats,
                *(
                    ["METADATA_DESIGN_DTO_SKIPPED"]
                    if not request.options.generate_dto_draft
                    else []
                ),
            ]
        )
        review_markers = _review_markers_for_design(
            mappings=mappings,
            table_proposal=table_proposal,
            caveats=caveats,
        )
        component_invocations = [
            *(
                [planner_component]
                if planner_component
                else []
            ),
            *[
                {
                    "stage": "metadata_design_tool",
                    "toolName": result.tool_name,
                    "status": result.status,
                    "evidenceCount": len(result.evidence_refs),
                    "resultCount": result.result_count,
                    **({"errorCode": result.error_code} if result.error_code else {}),
                }
                for result in candidate_context.tool_results
            ],
        ]
        ai_tool_evidence = {
            "status": "SUCCEEDED" if candidate_context.tool_results else REVIEW_REQUIRED,
            "toolResults": [
                {
                    "toolName": result.tool_name,
                    "status": result.status,
                    "evidenceRefs": list(result.evidence_refs),
                    "resultCount": result.result_count,
                    "contentHash": stable_json_hash(result.response.get("data", {})),
                    **({"errorCode": result.error_code} if result.error_code else {}),
                }
                for result in candidate_context.tool_results
            ],
            "plannerMetrics": {
                "status": "SUCCEEDED" if model_invocation else "SKIPPED",
                "executedToolCallCount": sum(
                    1 for result in candidate_context.tool_results if result.status == "SUCCEEDED"
                ),
                "blockedRequestCount": sum(
                    1 for result in candidate_context.tool_results if result.status != "SUCCEEDED"
                ),
                "cacheHitCount": 0,
                "cacheMissCount": 0,
            },
        }
        review_required = bool(
            caveats
            or review_markers
            or table_proposal.review_required
            or (dto_draft and dto_draft.review_required)
        )
        return MetadataDesignResult(
            assistantMessage=_assistant_message(
                table_proposal=table_proposal,
                dto_draft=dto_draft,
            ),
            relatedMetadata=list(candidate_context.related_metadata),
            standardizationMappings=list(mappings),
            tableProposal=table_proposal,
            dtoDraft=dto_draft,
            aiToolEvidence=ai_tool_evidence,
            deterministicFacts=list(candidate_context.deterministic_facts),
            reviewMarkers=[
                MetadataAnalysisReviewMarker.model_validate(marker)
                for marker in review_markers
            ],
            caveats=caveats,
            reviewRequired=review_required,
            modelInvocation=model_invocation,
            componentInvocations=component_invocations,
        )


def _run_design_planner(
    request: MetadataDesignRunRequest,
    *,
    fields: list[MetadataDesignFieldInput],
    model_gateway: ModelGateway,
) -> tuple[ModelInvocationSummary | None, dict[str, Any] | None, list[str]]:
    if not request.options.use_llm_analysis or not request.options.use_ai_tool_orchestration:
        return None, {
            "stage": "metadata_design_intent_planning",
            "toolName": "metadata_tool_planner",
            "status": "SKIPPED",
            "evidenceCount": 0,
            "toolRequestCount": 0,
        }, ["METADATA_DESIGN_LLM_PLANNER_SKIPPED"]
    planner = getattr(model_gateway, "plan_metadata_tools", None)
    if not callable(planner):
        return None, None, ["METADATA_DESIGN_LLM_PLANNER_SKIPPED"]
    payload = {
        "message": _safe_text(request.message),
        "tableNameHint": _safe_text(request.design_inputs.table_name_hint),
        "tableDescription": _safe_text(request.design_inputs.table_description),
        "fields": [
            {
                    "name": _safe_text(field.name),
                    "description": _safe_text(field.description),
                    "dbType": _safe_text(field.db_type),
            }
            for field in fields
        ],
        "allowedTools": [
            "search_columns",
            "search_tables",
            "find_similar_tables",
            "get_table_schema",
        ],
    }
    prompt = RenderedPrompt(
        prompt_version=DESIGN_PROMPT_VERSION,
        output_schema_version=DESIGN_OUTPUT_SCHEMA_VERSION,
        system_prompt=(
            "Extract bounded read-only MSSQL metadata search intent. "
            "Return only tool planning JSON; never request row data or write actions."
        ),
        user_prompt=json.dumps(payload, ensure_ascii=False, sort_keys=True),
        input_hash=stable_json_hash(payload),
        prompt_hash=stable_json_hash({"prompt": DESIGN_PROMPT_VERSION, "payload": payload}),
        metadata={"targetRef": f"metadata-design:{request.db_profile_id}"},
    )
    try:
        invocation = planner(
            prompt=prompt,
            profile=model_profile_from_env(request.options.llm_profile_id),
        )
        plan = AiToolPlanningOutput.model_validate(invocation.structured_output)
    except (ModelGatewayError, ValueError) as exc:
        return None, {
            "stage": "metadata_design_intent_planning",
            "toolName": "metadata_tool_planner",
            "status": REVIEW_REQUIRED,
            "errorCode": getattr(exc, "code", exc.__class__.__name__),
            "evidenceCount": 0,
            "toolRequestCount": 0,
        }, ["METADATA_DESIGN_LLM_PLANNER_SKIPPED"]
    return (
        ModelInvocationSummary.model_validate(invocation.to_storage_dict()),
        {
            "stage": "metadata_design_intent_planning",
            "toolName": "metadata_tool_planner",
            "status": invocation.status.value,
            "inputHash": invocation.input_hash,
            "promptHash": invocation.prompt_hash,
            "outputHash": invocation.output_hash,
            "latencyMs": invocation.latency_ms,
            "evidenceCount": 0,
            "toolRequestCount": len(plan.tool_requests),
        },
        [],
    )


def _collect_metadata_candidates(
    request: MetadataDesignRunRequest,
    *,
    fields: list[MetadataDesignFieldInput],
    max_candidates: int,
) -> CandidateContext:
    tool_results: list[ToolEnvelope] = []
    related: list[MetadataRelatedMetadata] = []
    facts: list[dict[str, Any]] = []
    caveats: list[str] = []
    try:
        registry = _build_internal_registry(request.db_profile_id)
    except Exception as exc:  # noqa: BLE001 - surface sanitized blocker in result
        return CandidateContext(
            tool_results=(),
            related_metadata=(),
            deterministic_facts=(
                {
                    "id": "metadata_design.registry_unavailable",
                    "kind": "METADATA_TOOL",
                    "status": REVIEW_REQUIRED,
                    "summary": f"Metadata registry unavailable: {exc.__class__.__name__}",
                    "evidenceRefs": [],
                },
            ),
            caveats=("METADATA_DESIGN_METADATA_UNAVAILABLE",),
        )

    def invoke(tool_name: str, arguments: dict[str, Any]) -> dict[str, Any] | None:
        try:
            response = registry.invoke_payload(
                tool_name,
                {"arguments": {"dbProfileId": request.db_profile_id, **arguments}},
            )
        except (MetadataToolError, MetadataSearchDependencyError, ValueError) as exc:
            tool_results.append(
                ToolEnvelope(
                    tool_name=tool_name,
                    status=REVIEW_REQUIRED,
                    response={},
                    evidence_refs=(),
                    result_count=0,
                    error_code=getattr(exc, "code", exc.__class__.__name__),
                )
            )
            caveats.append("METADATA_DESIGN_TOOL_REVIEW_REQUIRED")
            return None
        evidence_refs = tuple(_evidence_ids(response))
        data = dict(response.get("data") or {})
        data["__responseEvidenceRefs"] = list(evidence_refs)
        result_count = len(data.get("candidates") or data.get("columns") or [])
        tool_results.append(
            ToolEnvelope(
                tool_name=tool_name,
                status="SUCCEEDED",
                response=response,
                evidence_refs=evidence_refs,
                result_count=result_count,
            )
        )
        return data

    table_hint = request.design_inputs.table_name_hint
    table_description = request.design_inputs.table_description or _description_from_message(
        request.message
    )
    if table_hint or table_description:
        data = invoke(
            "search_tables",
            {
                "physicalName": _safe_text(table_hint),
                "logicalName": _safe_text(table_hint),
                "description": _safe_text(table_description),
                "topK": max_candidates,
            },
        )
        _append_table_candidates(related, facts, data, "TABLE")
    for field in fields[:10]:
        data = invoke(
            "search_columns",
            {
                "physicalName": _safe_text(field.name),
                "logicalName": _safe_text(field.name),
                "description": _safe_text(field.description),
                "tableName": _safe_text(table_hint),
                "topK": max_candidates,
            },
        )
        _append_column_candidates(related, facts, data)
    if fields:
        data = invoke(
            "find_similar_tables",
            {
                "description": _safe_text(table_description),
                "columns": [
                    {
                        "name": _safe_text(field.name or field.description or "FIELD"),
                        "type": _safe_text(field.db_type),
                    }
                    for field in fields[:10]
                ],
                "topK": max_candidates,
            },
        )
        _append_table_candidates(related, facts, data, "SIMILAR_TABLE")
    for item in related[:2]:
        if item.kind not in {"TABLE", "SIMILAR_TABLE"}:
            continue
        schema, table_name = _split_object_ref(item.object_ref)
        if not schema or not table_name:
            continue
        data = invoke(
            "get_table_schema",
            {"schema": schema, "tableName": table_name},
        )
        _append_schema_metadata(related, facts, data, item.evidence_refs)
    if not related:
        caveats.append("METADATA_DESIGN_NO_SIMILAR_METADATA")
    return CandidateContext(
        tool_results=tuple(tool_results),
        related_metadata=tuple(_dedupe_related(related)),
        deterministic_facts=tuple(facts),
        caveats=tuple(_dedupe_strings(caveats)),
    )


def _append_table_candidates(
    related: list[MetadataRelatedMetadata],
    facts: list[dict[str, Any]],
    data: dict[str, Any] | None,
    kind: str,
) -> None:
    if not data:
        return
    for index, candidate in enumerate(data.get("candidates", []) or []):
        if not isinstance(candidate, dict):
            continue
        object_ref = f"{candidate.get('schema', 'dbo')}.{candidate.get('tableName', '')}"
        evidence_refs = _candidate_evidence(candidate) or _evidence_ids(data)
        related.append(
            MetadataRelatedMetadata(
                kind=kind,
                objectRef=object_ref,
                score=int(candidate.get("score") or 0),
                summary=_safe_text(
                    candidate.get("description")
                    or candidate.get("logicalName")
                    or object_ref
                ),
                evidenceRefs=evidence_refs,
                payload=_safe_payload(candidate),
            )
        )
        facts.append(_fact(f"metadata_design.{kind.lower()}.{index}", object_ref, evidence_refs))


def _append_column_candidates(
    related: list[MetadataRelatedMetadata],
    facts: list[dict[str, Any]],
    data: dict[str, Any] | None,
) -> None:
    if not data:
        return
    fallback_refs = _evidence_ids(data)
    for index, candidate in enumerate(data.get("candidates", []) or []):
        if not isinstance(candidate, dict):
            continue
        object_ref = (
            f"{candidate.get('schema', 'dbo')}.{candidate.get('tableName', '')}."
            f"{candidate.get('columnName', '')}"
        )
        evidence_refs = _candidate_evidence(candidate) or fallback_refs
        related.append(
            MetadataRelatedMetadata(
                kind="COLUMN",
                objectRef=object_ref,
                score=int(candidate.get("score") or 0),
                summary=_safe_text(
                    candidate.get("description")
                    or candidate.get("logicalName")
                    or candidate.get("columnName")
                    or object_ref
                ),
                evidenceRefs=evidence_refs,
                payload=_safe_payload(candidate),
            )
        )
        facts.append(_fact(f"metadata_design.column.{index}", object_ref, evidence_refs))


def _append_schema_metadata(
    related: list[MetadataRelatedMetadata],
    facts: list[dict[str, Any]],
    data: dict[str, Any] | None,
    parent_refs: list[str],
) -> None:
    if not data:
        return
    schema = str(data.get("schema") or "dbo")
    table_name = str(data.get("tableName") or data.get("objectName") or "")
    object_ref = f"{schema}.{table_name}"
    evidence_refs = _evidence_ids(data) or parent_refs
    related.append(
        MetadataRelatedMetadata(
            kind="TABLE_SCHEMA",
            objectRef=object_ref,
            score=0,
            summary=f"{object_ref} column metadata",
            evidenceRefs=evidence_refs,
            payload=_safe_payload(
                {
                    "columnCount": len(data.get("columns") or []),
                    "columns": [
                        {
                            "name": column.get("name"),
                            "dataType": column.get("dataType"),
                            "nullable": column.get("nullable"),
                            "description": column.get("description"),
                        }
                        for column in (data.get("columns") or [])[:20]
                        if isinstance(column, dict)
                    ],
                }
            ),
        )
    )
    facts.append(_fact("metadata_design.table_schema", object_ref, evidence_refs))


def _build_standardization_mappings(
    fields: list[MetadataDesignFieldInput],
    *,
    candidate_context: CandidateContext,
    policy: dict[str, Any],
) -> list[MetadataStandardizationMapping]:
    column_candidates = [
        item for item in candidate_context.related_metadata if item.kind == "COLUMN"
    ]
    mappings: list[MetadataStandardizationMapping] = []
    for index, field in enumerate(fields):
        candidate = _best_column_candidate(field, column_candidates)
        if candidate is not None:
            payload = candidate.payload
            mappings.append(
                MetadataStandardizationMapping(
                    inputName=_safe_text(field.name),
                    inputDescription=_safe_text(field.description),
                    proposedName=_standard_identifier(
                        str(payload.get("columnName") or _safe_text(field.name))
                    ),
                    proposedType=str(
                        payload.get("dataType") or _safe_text(field.db_type) or "VARCHAR(500)"
                    ),
                    source="METADATA",
                    evidenceRefs=candidate.evidence_refs,
                    reviewRequired=bool(not payload.get("description")),
                    reviewReasons=(
                        []
                        if payload.get("description")
                        else ["REVIEW_REQUIRED: column description was not confirmed."]
                    ),
                )
            )
            continue
        proposed_name, proposed_type, reasons = _standardize_field(field, index, policy)
        if not reasons:
            reasons.append(
                "REVIEW_REQUIRED: metadata did not confirm this field name or type."
            )
        mappings.append(
            MetadataStandardizationMapping(
                inputName=_safe_text(field.name),
                inputDescription=_safe_text(field.description),
                proposedName=proposed_name,
                proposedType=_safe_text(field.db_type) or proposed_type,
                source="STANDARD_POLICY" if not reasons else "REVIEW_REQUIRED",
                evidenceRefs=[POLICY_REF],
                reviewRequired=bool(reasons),
                reviewReasons=reasons,
            )
        )
    return mappings


def _build_table_proposal(
    request: MetadataDesignRunRequest,
    *,
    mappings: list[MetadataStandardizationMapping],
    policy: dict[str, Any],
) -> MetadataTableProposal:
    table_name, table_reasons = _standard_table_name(request, policy)
    columns = [
        MetadataTableProposalColumn(
            name=mapping.proposed_name,
            dataType=mapping.proposed_type,
            nullable=True,
            description=mapping.input_description,
            source=(
                "METADATA"
                if mapping.source == "METADATA"
                else "STANDARD_POLICY"
                if mapping.source == "STANDARD_POLICY"
                else "REVIEW_REQUIRED"
            ),
            evidenceRefs=mapping.evidence_refs,
            reviewRequired=mapping.review_required,
            reviewReasons=mapping.review_reasons,
        )
        for mapping in mappings
    ]
    common_columns = policy.get("common_columns", {}).get("required_for_new_tables", [])
    existing_names = {column.name for column in columns}
    for common in common_columns:
        if not isinstance(common, dict):
            continue
        name = _standard_identifier(str(common.get("name") or ""))
        if not name or name in existing_names:
            continue
        columns.append(
            MetadataTableProposalColumn(
                name=name,
                dataType=str(common.get("type") or "VARCHAR(500)"),
                nullable=False,
                description="standard audit column",
                source="STANDARD_POLICY",
                evidenceRefs=[POLICY_REF],
                reviewRequired=False,
                reviewReasons=[],
            )
        )
    proposal_reasons = [
        *table_reasons,
        "REVIEW_REQUIRED: PK/FK and index structure must be confirmed before applying.",
    ]
    script = _render_create_table_preview(
        schema_name="dbo",
        table_name=table_name,
        columns=columns,
        review_reasons=proposal_reasons,
    )
    return MetadataTableProposal(
        schema="dbo",
        tableName=table_name,
        tableDescription=_safe_text(
            request.design_inputs.table_description or request.message[:200]
        ),
        columns=columns,
        createTableScriptPreview=script,
        evidenceRefs=_dedupe_strings(
            [ref for column in columns for ref in column.evidence_refs]
        ),
        reviewRequired=True,
        reviewReasons=proposal_reasons,
    )


def _build_dto_draft(table_proposal: MetadataTableProposal) -> MetadataGeneratedDraft:
    class_name = upper_first(snake_to_lower_camel(table_proposal.table_name.lower()))
    if not class_name.endswith("Dto"):
        class_name = f"{class_name}Dto"
    fields: list[tuple[str, str, MetadataTableProposalColumn]] = []
    for column in table_proposal.columns:
        java_type = java_type_for_db_type(column.data_type)
        fields.append((java_type, snake_to_lower_camel(column.name.lower()), column))
    imports = java_imports_for_types([java_type for java_type, _, _ in fields])
    lines = [
        "package com.example.metadata.dto;",
        "",
        *imports,
        *([] if not imports else [""]),
        "/**",
        " * REVIEW_REQUIRED: Generated from metadata design preview evidence.",
        f" * Source table proposal: {table_proposal.schema_name}.{table_proposal.table_name}",
        " */",
        f"public class {class_name} {{",
    ]
    for java_type, field_name, column in fields:
        refs = ", ".join(column.evidence_refs or [POLICY_REF])
        lines.extend(
            [
                f"    /** {column.name}; evidence={refs}; {'REVIEW_REQUIRED' if column.review_required else 'STANDARD_POLICY'} */",
                f"    private {java_type} {field_name};",
                "",
            ]
        )
    lines.append("}")
    return MetadataGeneratedDraft(
        artifactType="DTO_DRAFT",
        objectRef=f"{table_proposal.schema_name}.{table_proposal.table_name}",
        targetKey=target_key_for_target(
            "metadata-design",
            {
                "type": "TABLE",
                "schema": table_proposal.schema_name,
                "name": table_proposal.table_name,
            },
        ),
        fileName=f"{class_name}.java",
        language="java",
        content=ensure_trailing_newline("\n".join(lines)),
        evidenceRefs=table_proposal.evidence_refs,
        reviewRequired=True,
        reviewReasons=[
            "REVIEW_REQUIRED: DTO preview is not a compiled source artifact.",
            *table_proposal.review_reasons,
        ],
    )


def _render_create_table_preview(
    *,
    schema_name: str,
    table_name: str,
    columns: list[MetadataTableProposalColumn],
    review_reasons: list[str],
) -> str:
    lines = [
        "-- REVIEW_REQUIRED: metadata design preview only; manual schema review required.",
        "-- This script is not executed by the platform.",
        *[f"-- {reason}" for reason in review_reasons],
        f"CREATE TABLE [{schema_name}].[{table_name}] (",
    ]
    column_lines = []
    for column in columns:
        nullability = "NULL" if column.nullable else "NOT NULL"
        comment = (
            f" -- evidence: {', '.join(column.evidence_refs or [POLICY_REF])}; "
            f"{'REVIEW_REQUIRED' if column.review_required else column.source}"
        )
        column_lines.append(f"    [{column.name}] {column.data_type} {nullability}{comment}")
    lines.append(",\n".join(column_lines))
    lines.append(");")
    return ensure_trailing_newline("\n".join(lines))


def _review_markers_for_design(
    *,
    mappings: list[MetadataStandardizationMapping],
    table_proposal: MetadataTableProposal,
    caveats: list[str],
) -> list[dict[str, Any]]:
    markers: list[dict[str, Any]] = []
    if any(mapping.review_required for mapping in mappings):
        markers.append(
            _review_marker(
                "METADATA_DESIGN_STANDARDIZATION_REVIEW_REQUIRED",
                "Some fields could not be confirmed from metadata and need standardization review.",
                evidence_refs=_dedupe_strings(
                    [ref for mapping in mappings for ref in mapping.evidence_refs]
                )
                or [POLICY_REF],
            )
        )
    if table_proposal.review_required:
        markers.append(
            _review_marker(
                "METADATA_DESIGN_TABLE_REVIEW_REQUIRED",
                "The table script is a non-executable preview and needs manual schema review.",
                evidence_refs=table_proposal.evidence_refs or [POLICY_REF],
            )
        )
    for caveat in caveats:
        markers.append(
            _review_marker(
                caveat,
                f"Metadata design caveat: {caveat}",
                evidence_refs=table_proposal.evidence_refs or [POLICY_REF],
            )
        )
    return markers


def _assistant_message(
    *,
    table_proposal: MetadataTableProposal,
    dto_draft: MetadataGeneratedDraft | None,
) -> str:
    dto_part = (
        "A DTO_DRAFT preview was generated."
        if dto_draft
        else "DTO_DRAFT preview generation was skipped."
    )
    return (
        f"Built an evidence-backed table script preview for "
        f"{table_proposal.schema_name}.{table_proposal.table_name}. "
        f"{dto_part} Unconfirmed business rules, names, and constraints remain "
        "marked as REVIEW_REQUIRED."
    )


def _normalized_field_inputs(request: MetadataDesignRunRequest) -> list[MetadataDesignFieldInput]:
    fields = [
        field
        for field in request.design_inputs.fields
        if field.name or field.description or field.db_type
    ]
    if fields:
        return fields[:20]
    inferred = []
    for part in MESSAGE_SPLIT_RE.split(request.message):
        text = part.strip()
        if not text or len(text) > 80:
            continue
        if any(keyword in text.lower() for keyword in ("table", "create", "make")):
            continue
        inferred.append(MetadataDesignFieldInput(name=text))
    if inferred:
        return inferred[:20]
    return [MetadataDesignFieldInput(name="FIELD", description=request.message[:200])]


def _best_column_candidate(
    field: MetadataDesignFieldInput,
    candidates: list[MetadataRelatedMetadata],
) -> MetadataRelatedMetadata | None:
    if not candidates:
        return None
    tokens = {
        _normalize_match_text(field.name),
        _normalize_match_text(field.description),
    } - {""}
    if not tokens:
        return candidates[0]
    scored = []
    for candidate in candidates:
        payload_text = " ".join(
            _normalize_match_text(candidate.payload.get(key))
            for key in ("columnName", "logicalName", "description")
        )
        match_bonus = 100 if any(token and token in payload_text for token in tokens) else 0
        scored.append((candidate.score + match_bonus, candidate))
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1] if scored and scored[0][0] > 0 else None


def _standardize_field(
    field: MetadataDesignFieldInput,
    index: int,
    policy: dict[str, Any],
) -> tuple[str, str, list[str]]:
    source = _safe_text(field.name or field.description or f"FIELD_{index + 1}")
    normalized = _standard_identifier(source)
    reasons: list[str] = []
    if not normalized or _contains_non_ascii(source):
        normalized = _name_from_description(source, policy, index)
        reasons.append(
            "REVIEW_REQUIRED: field name was inferred because metadata did not confirm it."
        )
    data_type = field.db_type or _type_from_text(source, policy)
    if normalized == f"FIELD_{index + 1}_VAL":
        reasons.append(
            "REVIEW_REQUIRED: approved abbreviation was not found for the requested meaning."
        )
    return normalized, data_type, reasons


def _standard_table_name(
    request: MetadataDesignRunRequest,
    policy: dict[str, Any],
) -> tuple[str, list[str]]:
    hint = request.design_inputs.table_name_hint
    if hint:
        candidate = _standard_identifier(hint)
        if candidate:
            return candidate, []
    prefix = policy.get("schema_generation_rules", {}).get("new_platform_table_prefix", "PPM")
    return f"{prefix}_META_DESIGN_TMP", [
        "REVIEW_REQUIRED: table name was inferred because no confirmed table name was supplied."
    ]


def _name_from_description(source: str, policy: dict[str, Any], index: int) -> str:
    text = source.lower()
    if any(token in text for token in ("datetime", "timestamp")):
        return f"FIELD_{index + 1}_DTM"
    if any(token in text for token in ("date",)):
        return f"FIELD_{index + 1}_DT"
    if any(token in text for token in ("amount", "amt")):
        return f"FIELD_{index + 1}_AMT"
    if any(token in text for token in ("quantity", "qty")):
        return f"FIELD_{index + 1}_QTY"
    if any(token in text for token in ("code",)):
        return f"FIELD_{index + 1}_CD"
    if any(token in text for token in ("name",)):
        return f"FIELD_{index + 1}_NM"
    preferred = policy.get("preferred_term_columns", {})
    if "VAL" in preferred:
        return f"FIELD_{index + 1}_VAL"
    return f"FIELD_{index + 1}_VAL"


def _type_from_text(source: str, policy: dict[str, Any]) -> str:
    text = source.lower()
    class_words = policy.get("column_naming", {}).get("class_words", {})
    if any(token in text for token in ("datetime", "timestamp")):
        return str(class_words.get("DTM", {}).get("standard_type") or "DATETIME2")
    if any(token in text for token in ("date",)):
        return str(class_words.get("DT", {}).get("standard_type") or "VARCHAR(8)")
    if any(token in text for token in ("amount", "amt")):
        return str(class_words.get("AMT", {}).get("standard_type") or "NUMERIC(18,3)")
    if any(token in text for token in ("quantity", "qty")):
        return str(class_words.get("QTY", {}).get("standard_type") or "NUMERIC(18,5)")
    if any(token in text for token in ("count", "cnt")):
        return str(class_words.get("CNT", {}).get("standard_type") or "INT")
    if any(token in text for token in ("id", "identifier")):
        return str(class_words.get("ID", {}).get("standard_type") or "UNIQUEIDENTIFIER")
    if any(token in text for token in ("code",)):
        return str(class_words.get("CD", {}).get("standard_type") or "VARCHAR(20)")
    if any(token in text for token in ("description", "desc")):
        return str(class_words.get("DESC", {}).get("standard_type") or "VARCHAR(500)")
    return "VARCHAR(500)"


def _standard_identifier(value: str) -> str:
    cleaned = IDENTIFIER_CLEANUP_RE.sub("_", value.strip().upper()).strip("_")
    if not cleaned:
        return ""
    if cleaned[0].isdigit():
        cleaned = f"F_{cleaned}"
    return re.sub(r"_+", "_", cleaned)


def _safe_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if FORBIDDEN_TEXT_RE.search(text):
        return "[REDACTED_REVIEW_REQUIRED]"
    return text[:500]


def _description_from_message(message: str) -> str:
    return _safe_text(message[:500])


def _safe_payload(payload: dict[str, Any]) -> dict[str, Any]:
    safe = _safe_dict(payload)
    for key in list(safe):
        lowered = key.lower()
        if any(token in lowered for token in ("secret", "password", "token", "definition")):
            safe.pop(key, None)
    return safe


def _evidence_ids(value: dict[str, Any]) -> list[str]:
    refs = value.get("evidenceRefs") or value.get("__responseEvidenceRefs")
    if not refs and isinstance(value.get("data"), dict):
        refs = value["data"].get("evidenceRefs")
    evidence = []
    for ref in refs or []:
        if isinstance(ref, dict):
            evidence.append(
                str(ref.get("id") or ref.get("locator") or ref.get("path") or ref)
            )
        elif ref:
            evidence.append(str(ref))
    return _dedupe_strings(evidence)


def _candidate_evidence(candidate: dict[str, Any]) -> list[str]:
    return _evidence_ids({"evidenceRefs": candidate.get("evidenceRefs") or []})


def _fact(fact_id: str, object_ref: str, evidence_refs: list[str]) -> dict[str, Any]:
    return {
        "id": fact_id,
        "kind": "METADATA_DESIGN_EVIDENCE",
        "status": "OBSERVED" if evidence_refs else REVIEW_REQUIRED,
        "objectRef": object_ref,
        "summary": f"Metadata design evidence for {object_ref}",
        "evidenceRefs": evidence_refs,
    }


def _split_object_ref(object_ref: str) -> tuple[str, str]:
    parts = object_ref.split(".", 1)
    if len(parts) != 2:
        return "", ""
    return parts[0], parts[1]


def _dedupe_related(items: list[MetadataRelatedMetadata]) -> list[MetadataRelatedMetadata]:
    seen: set[tuple[str, str]] = set()
    deduped: list[MetadataRelatedMetadata] = []
    for item in items:
        key = (item.kind, item.object_ref)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped


def _normalize_match_text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "").strip().lower())


def _contains_non_ascii(value: str) -> bool:
    return any(ord(char) > 127 for char in value)


def _load_standardization_policy() -> dict[str, Any]:
    path = repo_root() / "spec" / "policy" / "platform_db_standardization_rules_for_ai.json"
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {
            "schema_generation_rules": {"new_platform_table_prefix": "PPM"},
            "common_columns": {"required_for_new_tables": []},
            "column_naming": {"class_words": {}},
        }
