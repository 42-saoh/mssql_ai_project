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
    MetadataDesignAppliedChange,
    MetadataDesignFieldInput,
    MetadataDesignIntentChange,
    MetadataDesignInterpretedIntent,
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
FIELD_CONNECTOR_RE = re.compile(
    r"\s*(?:,|/|;|\n|\r|와|과|및|하고|이랑|랑|and|with)\s*",
    re.IGNORECASE,
)
KNOWN_FIELD_TERMS: tuple[tuple[tuple[str, ...], str, str, str], ...] = (
    (
        ("고객명", "고객 이름", "customer name", "customer_nm"),
        "CUSTOMER_NM",
        "Customer name",
        "VARCHAR(100)",
    ),
    (
        ("고객주소", "고객 주소", "customer address", "customer_addr"),
        "CUSTOMER_ADDR",
        "Customer address",
        "VARCHAR(500)",
    ),
    (("주소", "address", "addr"), "ADDR", "Address", "VARCHAR(500)"),
    (("주문일", "주문 일자", "order date", "order_dt"), "ORDER_DT", "Order date", "VARCHAR(8)"),
    (
        ("배송메모", "배송 메모", "delivery memo", "shipping memo", "dlv_memo"),
        "DLV_MEMO",
        "Delivery memo",
        "VARCHAR(500)",
    ),
    (("메모", "memo"), "MEMO", "Memo", "VARCHAR(500)"),
)
KNOWN_TABLE_TERMS: tuple[tuple[tuple[str, ...], str, str], ...] = (
    (("주문 요청", "order request"), "PPM_ORDER_REQ", "Order request table"),
    (("고객 주문", "customer order"), "PPM_CUSTOMER_ORDER", "Customer order table"),
)
DATE_TYPE_HINTS = ("날짜", "일자", "date")
ADD_HINTS = ("추가", "넣어", "add", "include")
REMOVE_HINTS = ("빼", "삭제", "제거", "remove", "exclude", "drop")
CHANGE_HINTS = ("변경", "바꿔", "수정", "change", "convert")


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
        intent = _interpret_design_intent(request)
        effective_request, fields, applied_changes, intent_caveats = _effective_request_for_intent(
            request,
            intent=intent,
            repository=self.repository,
            policy=self._policy,
        )
        model_invocation, planner_component, planner_caveats = _run_design_planner(
            effective_request,
            fields=fields,
            model_gateway=self.model_gateway,
        )
        candidate_context = _collect_metadata_candidates(
            effective_request,
            fields=fields,
            max_candidates=effective_request.options.max_candidates,
        )
        mappings = _build_standardization_mappings(
            fields,
            candidate_context=candidate_context,
            policy=self._policy,
        )
        table_proposal = _build_table_proposal(
            effective_request,
            mappings=mappings,
            policy=self._policy,
        )
        dto_draft = (
            _build_dto_draft(table_proposal)
            if effective_request.options.generate_dto_draft
            else None
        )
        caveats = _dedupe_strings(
            [
                *intent_caveats,
                *candidate_context.caveats,
                *planner_caveats,
                *(
                    ["METADATA_DESIGN_DTO_SKIPPED"]
                    if not effective_request.options.generate_dto_draft
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
            interpretedIntent=intent,
            appliedChanges=list(applied_changes),
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


def _interpret_design_intent(request: MetadataDesignRunRequest) -> MetadataDesignInterpretedIntent:
    message = _safe_text(request.message)
    fields = _fields_from_request_or_message(request)
    modifications = _modifications_from_message(message, fields=fields)
    table_name = _safe_text(request.design_inputs.table_name_hint) or _table_name_from_message(message)
    table_description = (
        _safe_text(request.design_inputs.table_description)
        or _table_description_from_message(message)
    )
    mode = request.options.conversation_mode
    review_reasons: list[str] = []
    if not fields and not modifications:
        review_reasons.append(
            "REVIEW_REQUIRED: natural language intent did not identify field candidates."
        )
    if mode == "REFINE_CURRENT" and not modifications:
        review_reasons.append(
            "REVIEW_REQUIRED: refine mode needs an add, remove, rename, or type-change instruction."
        )
    return MetadataDesignInterpretedIntent(
        intent="REFINE_TABLE" if mode == "REFINE_CURRENT" else "CREATE_TABLE",
        tableNameCandidate=table_name or None,
        tableDescription=table_description or None,
        fields=fields,
        modifications=modifications,
        confidence=0.78 if not review_reasons else 0.42,
        reviewRequired=bool(review_reasons),
        reviewReasons=review_reasons,
    )


def _effective_request_for_intent(
    request: MetadataDesignRunRequest,
    *,
    intent: MetadataDesignInterpretedIntent,
    repository: WorkflowRepository | None,
    policy: dict[str, Any],
) -> tuple[MetadataDesignRunRequest, list[MetadataDesignFieldInput], list[MetadataDesignAppliedChange], list[str]]:
    if request.options.conversation_mode == "REFINE_CURRENT":
        return _refine_request_from_baseline(
            request,
            intent=intent,
            repository=repository,
            policy=policy,
        )
    fields = intent.fields or _normalized_field_inputs(request)
    design_inputs = request.design_inputs.model_copy(
        update={
            "table_name_hint": request.design_inputs.table_name_hint
            or intent.table_name_candidate,
            "table_description": request.design_inputs.table_description
            or intent.table_description,
            "fields": fields,
        }
    )
    applied = [
        MetadataDesignAppliedChange(
            action="ADD_FIELD",
            target=_safe_text(field.name or field.description),
            summary=(
                "Accepted natural-language field candidate "
                f"{_safe_text(field.name or field.description)}."
            ),
            reviewRequired=False,
            reviewReasons=[],
        )
        for field in fields
    ]
    return request.model_copy(update={"design_inputs": design_inputs}), fields, applied, []


def _refine_request_from_baseline(
    request: MetadataDesignRunRequest,
    *,
    intent: MetadataDesignInterpretedIntent,
    repository: WorkflowRepository | None,
    policy: dict[str, Any],
) -> tuple[MetadataDesignRunRequest, list[MetadataDesignFieldInput], list[MetadataDesignAppliedChange], list[str]]:
    baseline = _latest_successful_table_proposal(
        repository,
        conversation_id=request.conversation_id,
    )
    if baseline is None:
        caveat = "METADATA_DESIGN_REFINE_BASELINE_REQUIRED"
        design_inputs = request.design_inputs.model_copy(
            update={
                "table_name_hint": request.design_inputs.table_name_hint
                or intent.table_name_candidate,
                "table_description": request.design_inputs.table_description
                or intent.table_description,
                "fields": [],
            }
        )
        return (
            request.model_copy(update={"design_inputs": design_inputs}),
            [],
            [
                MetadataDesignAppliedChange(
                    action="REVIEW_REQUIRED",
                    target=request.conversation_id,
                    summary="Refine mode could not find a previous successful design result.",
                    reviewRequired=True,
                    reviewReasons=["REVIEW_REQUIRED: baseline table proposal is required."],
                )
            ],
            [caveat],
        )
    fields = _baseline_fields_from_table(baseline, policy)
    applied: list[MetadataDesignAppliedChange] = []
    for change in intent.modifications:
        fields, applied_change = _apply_intent_change(fields, change)
        applied.append(applied_change)
    if not intent.modifications and intent.fields:
        for field in intent.fields:
            fields = _upsert_field(fields, field)
            applied.append(
                MetadataDesignAppliedChange(
                    action="ADD_FIELD",
                    target=_safe_text(field.name or field.description),
                    summary=f"Added field candidate {_safe_text(field.name or field.description)}.",
                    reviewRequired=False,
                    reviewReasons=[],
                )
            )
    caveats = []
    if not applied:
        caveats.append("METADATA_DESIGN_REFINE_AMBIGUOUS")
        applied.append(
            MetadataDesignAppliedChange(
                action="REVIEW_REQUIRED",
                target=request.message[:80],
                summary="Refine instruction was not specific enough to alter the baseline.",
                reviewRequired=True,
                reviewReasons=["REVIEW_REQUIRED: specify a field add/remove/type change."],
            )
        )
    table_name = intent.table_name_candidate or baseline.table_name
    table_description = intent.table_description or baseline.table_description
    design_inputs = request.design_inputs.model_copy(
        update={
            "table_name_hint": table_name,
            "table_description": table_description,
            "fields": fields,
        }
    )
    return request.model_copy(update={"design_inputs": design_inputs}), fields, applied, caveats


def _latest_successful_table_proposal(
    repository: WorkflowRepository | None,
    *,
    conversation_id: str | None,
) -> MetadataTableProposal | None:
    if repository is None or not conversation_id:
        return None
    records = repository.list_metadata_design_runs_for_conversation(conversation_id, limit=20)
    candidates = [
        record
        for record in records
        if record.status == "SUCCEEDED" and isinstance(record.result, dict)
    ]
    candidates.sort(
        key=lambda record: record.completed_at or record.started_at or record.submitted_at,
        reverse=True,
    )
    for record in candidates:
        try:
            return MetadataDesignResult.model_validate(record.result).table_proposal
        except ValueError:
            continue
    return None


def _baseline_fields_from_table(
    table_proposal: MetadataTableProposal,
    policy: dict[str, Any],
) -> list[MetadataDesignFieldInput]:
    common_names = {
        _standard_identifier(str(item.get("name") or ""))
        for item in policy.get("common_columns", {}).get("required_for_new_tables", [])
        if isinstance(item, dict)
    }
    fields = []
    for column in table_proposal.columns:
        if column.name in common_names:
            continue
        fields.append(
            MetadataDesignFieldInput(
                name=column.name,
                description=column.description,
                dbType=column.data_type,
                nullable=column.nullable,
            )
        )
    return fields


def _apply_intent_change(
    fields: list[MetadataDesignFieldInput],
    change: MetadataDesignIntentChange,
) -> tuple[list[MetadataDesignFieldInput], MetadataDesignAppliedChange]:
    target = change.target or change.value or ""
    if change.action == "ADD_FIELD":
        field = _field_from_change(change)
        return _upsert_field(fields, field), MetadataDesignAppliedChange(
            action=change.action,
            target=field.name or field.description,
            summary=change.summary,
            reviewRequired=change.review_required,
            reviewReasons=change.review_reasons,
        )
    if change.action == "REMOVE_FIELD":
        remaining = [field for field in fields if not _field_matches_target(field, target)]
        removed = len(remaining) != len(fields)
        return remaining, MetadataDesignAppliedChange(
            action=change.action,
            target=target,
            summary=change.summary if removed else "No baseline field matched the remove instruction.",
            reviewRequired=not removed,
            reviewReasons=[] if removed else ["REVIEW_REQUIRED: field removal target was not found."],
        )
    if change.action == "CHANGE_TYPE":
        changed = False
        next_fields = []
        for field in fields:
            if _field_matches_target(field, target):
                changed = True
                next_fields.append(field.model_copy(update={"db_type": change.value}))
            else:
                next_fields.append(field)
        return next_fields, MetadataDesignAppliedChange(
            action=change.action,
            target=target,
            summary=change.summary if changed else "No baseline field matched the type change.",
            reviewRequired=not changed,
            reviewReasons=[] if changed else ["REVIEW_REQUIRED: type-change target was not found."],
        )
    return fields, MetadataDesignAppliedChange(
        action=change.action,
        target=_safe_text(target),
        summary=change.summary,
        reviewRequired=True,
        reviewReasons=change.review_reasons
        or ["REVIEW_REQUIRED: refine instruction requires manual confirmation."],
    )


def _fields_from_request_or_message(
    request: MetadataDesignRunRequest,
) -> list[MetadataDesignFieldInput]:
    fields = [
        _sanitized_field_input(field)
        for field in request.design_inputs.fields
        if field.name or field.description or field.db_type
    ]
    if fields:
        return fields[:20]
    return _fields_from_message(request.message)


def _fields_from_message(message: str) -> list[MetadataDesignFieldInput]:
    text = _safe_text(message)
    known = _known_fields_from_text(text)
    if known:
        return known[:20]

    inferred: list[MetadataDesignFieldInput] = []
    for part in FIELD_CONNECTOR_RE.split(text):
        candidate = _field_text_from_fragment(part)
        if not candidate:
            continue
        inferred.append(_field_input_from_text(candidate))
    return _dedupe_field_inputs(inferred)[:20]


def _modifications_from_message(
    message: str,
    *,
    fields: list[MetadataDesignFieldInput],
) -> list[MetadataDesignIntentChange]:
    text = _safe_text(message)
    folded = _normalize_match_text(text)
    if not folded:
        return []
    clause_modifications: list[MetadataDesignIntentChange] = []
    for clause in _message_action_clauses(text):
        if clause == text:
            continue
        clause_fields = _fields_from_message(clause)
        clause_modifications.extend(
            _modifications_from_message(clause, fields=clause_fields)
        )
    if clause_modifications:
        return _dedupe_intent_changes(clause_modifications)

    has_remove = any(token in folded for token in REMOVE_HINTS)
    has_add = any(token in folded for token in ADD_HINTS)
    has_change = any(token in folded for token in CHANGE_HINTS)
    type_hint = _type_hint_from_message(text)
    modifications: list[MetadataDesignIntentChange] = []

    if has_remove:
        targets = fields or [_field_input_from_text(_remove_target_text(text))]
        for field in targets:
            target = _safe_text(field.name or field.description)
            if not target:
                continue
            modifications.append(
                MetadataDesignIntentChange(
                    action="REMOVE_FIELD",
                    target=target,
                    summary=f"Remove field candidate {target}.",
                )
            )
        return modifications

    if has_change and type_hint:
        targets = fields or [_field_input_from_text(text)]
        for field in targets:
            target = _safe_text(field.name or field.description)
            if not target:
                continue
            modifications.append(
                MetadataDesignIntentChange(
                    action="CHANGE_TYPE",
                    target=target,
                    value=type_hint,
                    summary=f"Change {target} to {type_hint}.",
                )
            )
        return modifications

    if has_add:
        targets = fields or [_field_input_from_text(text)]
        for field in targets:
            target = _safe_text(field.name or field.description)
            if not target:
                continue
            modifications.append(
                MetadataDesignIntentChange(
                    action="ADD_FIELD",
                    target=target,
                    value=field.db_type,
                    summary=f"Add field candidate {target}.",
                )
            )
    return modifications


def _message_action_clauses(message: str) -> list[str]:
    parts = [
        part.strip()
        for part in re.split(r"(?:,|;|\n|\r|하고|그리고|\band\b)", message, flags=re.IGNORECASE)
        if part.strip()
    ]
    return parts if len(parts) > 1 else [message]


def _dedupe_intent_changes(
    changes: list[MetadataDesignIntentChange],
) -> list[MetadataDesignIntentChange]:
    seen: set[tuple[str, str, str]] = set()
    deduped: list[MetadataDesignIntentChange] = []
    for change in changes:
        key = (
            change.action,
            _standard_identifier(change.target or ""),
            _safe_text(change.value),
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(change)
    return deduped


def _table_name_from_message(message: str) -> str:
    text = _safe_text(message)
    folded = _normalize_match_text(text)
    for terms, table_name, _description in KNOWN_TABLE_TERMS:
        if any(_normalize_match_text(term) in folded for term in terms):
            return table_name
    explicit = re.search(r"\b([A-Za-z][A-Za-z0-9_]{2,})\b", text)
    if explicit and "_" in explicit.group(1):
        return _standard_identifier(explicit.group(1))
    return ""


def _table_description_from_message(message: str) -> str:
    text = _safe_text(message)
    folded = _normalize_match_text(text)
    for terms, _table_name, description in KNOWN_TABLE_TERMS:
        if any(_normalize_match_text(term) in folded for term in terms):
            return description
    return text[:200]


def _field_from_change(change: MetadataDesignIntentChange) -> MetadataDesignFieldInput:
    source = change.target or change.value or change.summary
    field = _field_input_from_text(source)
    if change.value and change.action in {"ADD_FIELD", "CHANGE_TYPE"}:
        field = field.model_copy(update={"db_type": _safe_text(change.value)})
    return field


def _upsert_field(
    fields: list[MetadataDesignFieldInput],
    field: MetadataDesignFieldInput,
) -> list[MetadataDesignFieldInput]:
    replacement = _sanitized_field_input(field)
    replaced = False
    next_fields: list[MetadataDesignFieldInput] = []
    for existing in fields:
        if _field_matches_target(existing, replacement.name or replacement.description or ""):
            next_fields.append(
                existing.model_copy(
                    update={
                        "name": replacement.name or existing.name,
                        "description": replacement.description or existing.description,
                        "db_type": replacement.db_type or existing.db_type,
                        "nullable": replacement.nullable
                        if replacement.nullable is not None
                        else existing.nullable,
                    }
                )
            )
            replaced = True
        else:
            next_fields.append(existing)
    if not replaced:
        next_fields.append(replacement)
    return _dedupe_field_inputs(next_fields)[:20]


def _field_matches_target(field: MetadataDesignFieldInput, target: str) -> bool:
    target_text = _safe_text(target)
    if not target_text:
        return False
    target_known = _known_field_for_text(target_text)
    target_names = {
        _standard_identifier(target_text),
        _normalize_match_text(target_text),
    }
    if target_known:
        target_names.add(target_known[0])
        target_names.add(_normalize_match_text(target_known[1]))

    candidates = {
        _standard_identifier(field.name or ""),
        _standard_identifier(field.description or ""),
        _normalize_match_text(field.name),
        _normalize_match_text(field.description),
    }
    field_known = _known_field_for_text(" ".join([field.name or "", field.description or ""]))
    if field_known:
        candidates.add(field_known[0])
        candidates.add(_normalize_match_text(field_known[1]))
    return bool((target_names - {""}) & (candidates - {""}))


def _known_fields_from_text(text: str) -> list[MetadataDesignFieldInput]:
    folded = _normalize_match_text(text)
    matches: list[tuple[int, str, str, str]] = []
    for terms, name, description, db_type in KNOWN_FIELD_TERMS:
        positions = [
            folded.find(_normalize_match_text(term))
            for term in terms
            if _normalize_match_text(term) and _normalize_match_text(term) in folded
        ]
        if positions:
            matches.append((min(positions), name, description, db_type))
    matches.sort(key=lambda item: item[0])

    fields: list[MetadataDesignFieldInput] = []
    seen: set[str] = set()
    for _position, name, description, db_type in matches:
        if name == "ADDR" and "CUSTOMER_ADDR" in seen:
            continue
        if name == "MEMO" and "DLV_MEMO" in seen:
            continue
        if name in seen:
            continue
        seen.add(name)
        fields.append(
            MetadataDesignFieldInput(
                name=name,
                description=description,
                dbType=db_type,
            )
        )
    return fields


def _field_input_from_text(text: str) -> MetadataDesignFieldInput:
    source = _safe_text(text)
    known = _known_field_for_text(source)
    if known:
        return MetadataDesignFieldInput(
            name=known[0],
            description=known[1],
            dbType=known[2],
        )
    return MetadataDesignFieldInput(
        name=_safe_text(source),
        description=_safe_text(source),
        dbType=_type_hint_from_message(source) or None,
    )


def _known_field_for_text(text: str) -> tuple[str, str, str] | None:
    folded = _normalize_match_text(text)
    if not folded:
        return None
    for terms, name, description, db_type in KNOWN_FIELD_TERMS:
        if any(_normalize_match_text(term) in folded for term in terms):
            return name, description, db_type
    return None


def _type_hint_from_message(text: str) -> str:
    folded = _normalize_match_text(text)
    if any(token in folded for token in ("datetime", "timestamp", "일시")):
        return "DATETIME2"
    if any(token in folded for token in DATE_TYPE_HINTS):
        return "VARCHAR(8)"
    if any(token in folded for token in ("amount", "amt", "금액")):
        return "NUMERIC(18,3)"
    if any(token in folded for token in ("quantity", "qty", "수량")):
        return "NUMERIC(18,5)"
    if any(token in folded for token in ("count", "cnt", "건수")):
        return "INT"
    if any(token in folded for token in ("code", "코드")):
        return "VARCHAR(20)"
    return ""


def _field_text_from_fragment(fragment: str) -> str:
    text = _safe_text(fragment).strip(" .:()[]{}")
    if not text:
        return ""
    folded = _normalize_match_text(text)
    blocked_terms = (
        "table",
        "create",
        "make",
        "generate",
        "테이블",
        "생성",
        "만들",
        "목적",
    )
    if any(term in folded for term in blocked_terms):
        return ""
    text = re.sub(r"\b(field|column|type)\b", "", text, flags=re.IGNORECASE).strip()
    text = re.sub(r"(필드|컬럼|타입|으로|로|은|는|을|를|이|가)$", "", text).strip()
    return text[:80]


def _remove_target_text(message: str) -> str:
    text = _safe_text(message)
    for token in REMOVE_HINTS:
        index = _normalize_match_text(text).find(_normalize_match_text(token))
        if index > 0:
            return text[:index].strip()
    return text


def _dedupe_field_inputs(
    fields: list[MetadataDesignFieldInput],
) -> list[MetadataDesignFieldInput]:
    seen: set[str] = set()
    deduped: list[MetadataDesignFieldInput] = []
    for field in fields:
        sanitized = _sanitized_field_input(field)
        key = (
            _standard_identifier(sanitized.name or "")
            or _standard_identifier(sanitized.description or "")
            or _normalize_match_text(sanitized.description)
        )
        if not key or key in seen:
            continue
        seen.add(key)
        deduped.append(sanitized)
    return deduped


def _sanitized_field_input(field: MetadataDesignFieldInput) -> MetadataDesignFieldInput:
    return MetadataDesignFieldInput(
        name=_safe_text(field.name) or None,
        description=_safe_text(field.description) or None,
        dbType=_safe_text(field.db_type) or None,
        nullable=field.nullable,
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
    tool_names = [
        "search_columns",
        "search_tables",
        "find_similar_tables",
        "get_table_schema",
    ]
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
        "allowedTools": tool_names,
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
        metadata={
            "targetRef": f"metadata-design:{request.db_profile_id}",
            "toolNames": tool_names,
        },
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
    fields = _fields_from_request_or_message(request)
    if fields:
        return fields[:20]
    return [
        MetadataDesignFieldInput(
            name="FIELD",
            description=_safe_text(request.message[:200]) or "Unspecified field",
        )
    ]


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
    known = _known_field_for_text(source)
    if known:
        return known[0], field.db_type or known[2], []
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
    known = _known_field_for_text(source)
    if known:
        return known[0]
    text = _normalize_match_text(source)
    if any(token in text for token in ("datetime", "timestamp", "일시")):
        return f"FIELD_{index + 1}_DTM"
    if any(token in text for token in ("date", "날짜", "일자")):
        return f"FIELD_{index + 1}_DT"
    if any(token in text for token in ("amount", "amt", "금액")):
        return f"FIELD_{index + 1}_AMT"
    if any(token in text for token in ("quantity", "qty", "수량")):
        return f"FIELD_{index + 1}_QTY"
    if any(token in text for token in ("code", "코드")):
        return f"FIELD_{index + 1}_CD"
    if any(token in text for token in ("name", "이름", "명")):
        return f"FIELD_{index + 1}_NM"
    preferred = policy.get("preferred_term_columns", {})
    if "VAL" in preferred:
        return f"FIELD_{index + 1}_VAL"
    return f"FIELD_{index + 1}_VAL"


def _type_from_text(source: str, policy: dict[str, Any]) -> str:
    known = _known_field_for_text(source)
    if known:
        return known[2]
    text = _normalize_match_text(source)
    class_words = policy.get("column_naming", {}).get("class_words", {})
    if any(token in text for token in ("datetime", "timestamp", "일시")):
        return str(class_words.get("DTM", {}).get("standard_type") or "DATETIME2")
    if any(token in text for token in ("date", "날짜", "일자")):
        return str(class_words.get("DT", {}).get("standard_type") or "VARCHAR(8)")
    if any(token in text for token in ("amount", "amt", "금액")):
        return str(class_words.get("AMT", {}).get("standard_type") or "NUMERIC(18,3)")
    if any(token in text for token in ("quantity", "qty", "수량")):
        return str(class_words.get("QTY", {}).get("standard_type") or "NUMERIC(18,5)")
    if any(token in text for token in ("count", "cnt", "건수")):
        return str(class_words.get("CNT", {}).get("standard_type") or "INT")
    if any(token in text for token in ("id", "identifier")):
        return str(class_words.get("ID", {}).get("standard_type") or "UNIQUEIDENTIFIER")
    if any(token in text for token in ("code", "코드")):
        return str(class_words.get("CD", {}).get("standard_type") or "VARCHAR(20)")
    if any(token in text for token in ("description", "desc", "설명", "메모")):
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
