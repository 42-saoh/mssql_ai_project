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
TABLE_NAME_PHRASE_RE = re.compile(
    r"(?:테이블\s*명|테이블명|table\s*name)\s*(?:은|는|:|=)?\s*(?P<table>[^\s,.;]+)",
    re.IGNORECASE,
)
FIELD_LIST_PHRASE_RE = re.compile(
    r"(?:필드|컬럼|column|field)(?:\s*(?:은|는|:|=))?\s*(?P<fields>.+)",
    re.IGNORECASE,
)
OBJECT_REF_RE = re.compile(
    r"^(?:(?P<schema>[A-Za-z_][A-Za-z0-9_]*)\.)?(?P<table>[A-Za-z_][A-Za-z0-9_]*)$"
)
KNOWN_FIELD_TERMS: tuple[tuple[tuple[str, ...], str, str, str], ...] = (
    (
        ("계약번호", "계약 번호", "contract number", "contract no", "ctrt_no"),
        "CTRT_NO",
        "Contract number",
        "VARCHAR(50)",
    ),
    (
        ("계약명", "계약 명", "계약 이름", "contract name", "ctrt_nm"),
        "CTRT_NM",
        "Contract name",
        "VARCHAR(100)",
    ),
    (
        ("주문번호", "주문 번호", "발주번호", "발주 번호", "order number", "ordr_no", "order_no"),
        "ORDR_NO",
        "Order number",
        "VARCHAR(50)",
    ),
    (
        (
            "계약변경차수",
            "계약 변경 차수",
            "계약변경 순번",
            "contract change sequence",
            "contract change seq",
            "ctrt_chg_seq_no",
        ),
        "CTRT_CHG_SEQ_NO",
        "Contract change sequence number",
        "INT",
    ),
    (
        ("계약금액", "계약 금액", "contract amount", "ctrt_amt"),
        "CTRT_AMT",
        "Contract amount",
        "NUMERIC(18,3)",
    ),
    (
        (
            "계약유형",
            "계약 유형",
            "계약종류",
            "계약 종류",
            "contract type",
            "contract kind",
            "ctrt_tp_cd",
        ),
        "CTRT_TP_CD",
        "Contract type code",
        "VARCHAR(30)",
    ),
    (
        (
            "사전감사yn",
            "사전감사 yn",
            "사전 감사 yn",
            "사전감사 여부",
            "pre audit yn",
            "prior audit yn",
            "prev audit yn",
        ),
        "PREV_AUDT_YN",
        "Pre-audit yes/no",
        "VARCHAR(1)",
    ),
    (
        (
            "알림여부",
            "알림 여부",
            "notification yn",
            "notice yn",
            "ntc_yn",
        ),
        "NTC_YN",
        "Notification yes/no",
        "VARCHAR(1)",
    ),
    (
        (
            "알림내용",
            "알림 내용",
            "notification content",
            "notice content",
            "ntc_cntnt",
        ),
        "NTC_CNTNT",
        "Notification content",
        "VARCHAR(2000)",
    ),
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
    (("사전감사", "사전 감사", "pre audit", "prior audit"), "PCO_PREV_AUDT", "Pre-audit table"),
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
            candidate_context=candidate_context,
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
    message_table_name = _table_name_from_message(message)
    table_hint = _safe_text(request.design_inputs.table_name_hint)
    table_name = (
        message_table_name
        or ("" if _table_name_hint_is_reference_scope(table_hint) else table_hint)
    )
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
    field_clause = _field_clause_from_message(text)
    if field_clause:
        fields = _fields_from_field_clause(field_clause)
        if fields:
            return fields[:20]
    known = _known_fields_from_text(text)

    inferred: list[MetadataDesignFieldInput] = []
    for part in FIELD_CONNECTOR_RE.split(text):
        candidate = _field_text_from_fragment(part)
        if not candidate:
            continue
        inferred.append(_field_input_from_text(candidate))
    return _dedupe_field_inputs([*known, *inferred])[:20]


def _field_clause_from_message(message: str) -> str:
    text = _safe_text(message)
    if not text:
        return ""
    matches = list(FIELD_LIST_PHRASE_RE.finditer(text))
    if not matches:
        return ""
    clause = matches[-1].group("fields")
    clause = re.split(r"(?:\.|입니다|이다|다\.|\bplease\b)", clause, maxsplit=1)[0]
    quoted = re.match(r"\s*[\"“](?P<fields>[^\"”]+)[\"”]", clause)
    if quoted:
        clause = quoted.group("fields")
    return _strip_korean_sentence_tail(clause)


def _fields_from_field_clause(clause: str) -> list[MetadataDesignFieldInput]:
    fields: list[MetadataDesignFieldInput] = []
    for part in FIELD_CONNECTOR_RE.split(clause):
        candidate = _field_text_from_fragment(part)
        if not candidate:
            continue
        fields.append(_field_input_from_text(candidate))
    return _dedupe_field_inputs(fields)


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
    explicit = TABLE_NAME_PHRASE_RE.search(text)
    if explicit:
        candidate = _standard_table_candidate(explicit.group("table"))
        if candidate:
            return candidate
    for terms, table_name, _description in KNOWN_TABLE_TERMS:
        if any(_normalize_match_text(term) in folded for term in terms):
            return table_name
    explicit = re.search(r"\b([A-Za-z][A-Za-z0-9_]*_[A-Za-z0-9_가-힣]+)\b", text)
    if explicit and "_" in explicit.group(1):
        return _standard_table_candidate(explicit.group(1))
    return ""


def _table_description_from_message(message: str) -> str:
    text = _safe_text(message)
    folded = _normalize_match_text(text)
    for terms, _table_name, description in KNOWN_TABLE_TERMS:
        if any(_normalize_match_text(term) in folded for term in terms):
            return description
    return text[:200]


def _standard_table_candidate(value: str) -> str:
    text = _strip_korean_sentence_tail(value)
    if not text:
        return ""
    for terms, table_name, _description in KNOWN_TABLE_TERMS:
        if any(_normalize_match_text(term) in _normalize_match_text(text) for term in terms):
            prefix = _standard_identifier(text.split("_", 1)[0]) if "_" in text else ""
            if prefix and prefix in {"PCO", "PCS", "PEM", "PPE", "PEI", "PPN", "PEX", "PAD", "PPM", "PDM", "PMA", "PEQ"}:
                return f"{prefix}_{table_name.split('_', 1)[1]}"
            return table_name
    return _standard_identifier(_replace_known_korean_table_terms(text))


def _replace_known_korean_table_terms(value: str) -> str:
    replacements = {
        "사전감사": "PREV_AUDT",
        "사전 감사": "PREV_AUDT",
        "감사": "AUDT",
        "계약": "CTRT",
        "주문": "ORDR",
        "발주": "ORDR",
    }
    text = _strip_korean_sentence_tail(value)
    for source, target in replacements.items():
        text = text.replace(source, target)
    return text


def _table_name_hint_is_reference_scope(hint: str) -> bool:
    text = _safe_text(hint)
    if not text:
        return False
    return len(_table_reference_hints(text)) > 1


def _table_reference_hints(hint: str) -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []
    for part in re.split(r"[,;\n\r]+", _safe_text(hint)):
        token = part.strip()
        if not token:
            continue
        match = OBJECT_REF_RE.match(token)
        if not match:
            continue
        schema = _standard_identifier(match.group("schema") or "dbo") or "dbo"
        table_name = _standard_identifier(match.group("table") or "")
        if table_name:
            refs.append((schema, table_name))
    deduped: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    for schema, table_name in refs:
        key = (schema.lower(), table_name.lower())
        if key in seen:
            continue
        seen.add(key)
        deduped.append((schema, table_name))
    return deduped


def _metadata_reference_hints_for_request(
    request: MetadataDesignRunRequest,
) -> list[tuple[str, str]]:
    hint = _safe_text(request.design_inputs.table_name_hint)
    refs = _table_reference_hints(hint)
    if not refs:
        return []
    if _table_name_hint_is_reference_scope(hint):
        return refs
    if "." in hint and _table_name_from_message(request.message):
        return refs
    return []


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
    text = _safe_text(fragment).strip(" .:()[]{}\"'“”‘’")
    if not text:
        return ""
    text = _strip_field_fragment_tail(text)
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
    text = _strip_korean_sentence_tail(text)
    return text[:80]


def _strip_field_fragment_tail(value: str) -> str:
    text = _safe_text(value).strip(" .:()[]{}\"'“”‘’")
    text = re.sub(
        r"[\"'“”‘’]\s*(?:이|가|은|는)?\s*"
        r"(?:들어가(?:요)?|들어갑니다|들어있어(?:요)?|들어있습니다|"
        r"포함(?:돼|되어)?(?:요|있어|있습니다)?|포함됩니다|있어(?:요)?|있습니다)$",
        "",
        text,
    ).strip(" .:()[]{}\"'“”‘’")
    text = re.sub(
        r"\s+(?:이|가|은|는)?\s*"
        r"(?:들어가(?:요)?|들어갑니다|들어있어(?:요)?|들어있습니다|"
        r"포함(?:돼|되어)?(?:요|있어|있습니다)?|포함됩니다|있어(?:요)?|있습니다)$",
        "",
        text,
    ).strip(" .:()[]{}\"'“”‘’")
    return text


def _strip_korean_sentence_tail(value: str) -> str:
    text = _safe_text(value).strip(" .:()[]{}")
    return re.sub(r"(?:이야|야|입니다|임|다)$", "", text).strip()


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
    reference_hints = _metadata_reference_hints_for_request(request)
    direct_schema_refs: set[tuple[str, str]] = set()
    table_description = request.design_inputs.table_description or _description_from_message(
        request.message
    )
    if reference_hints:
        for schema, table_name in reference_hints[:max_candidates]:
            data = invoke(
                "search_tables",
                {
                    "physicalName": table_name,
                    "logicalName": table_name,
                    "description": _safe_text(table_description),
                    "topK": max_candidates,
                },
            )
            _append_table_candidates(related, facts, data, "TABLE")
            direct_schema_refs.add((schema.lower(), table_name.lower()))
            schema_data = invoke(
                "get_table_schema",
                {"schema": schema, "tableName": table_name},
            )
            _append_schema_metadata(related, facts, schema_data, _evidence_ids(schema_data or {}))
    elif table_hint or table_description:
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
    column_table_filter = (
        reference_hints[0][1]
        if len(reference_hints) == 1
        else _safe_text(table_hint)
        if not reference_hints
        else ""
    )
    for field in fields[:10]:
        data = invoke(
            "search_columns",
            {
                "physicalName": _safe_text(field.name),
                "logicalName": _safe_text(field.name),
                "description": _safe_text(field.description),
                "tableName": column_table_filter,
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
        if (schema.lower(), table_name.lower()) in direct_schema_refs:
            continue
        direct_schema_refs.add((schema.lower(), table_name.lower()))
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
    fact_prefix = _standard_identifier(table_name).lower() or "table"
    facts.append(_fact(f"metadata_design.table_schema.{fact_prefix}", object_ref, evidence_refs))
    for column_index, column in enumerate(data.get("columns") or []):
        if not isinstance(column, dict):
            continue
        column_name = _standard_identifier(str(column.get("name") or ""))
        lowered_name = column_name.lower()
        if (
            not column_name
            or FORBIDDEN_TEXT_RE.search(column_name)
            or any(token in lowered_name for token in ("secret", "password", "token", "definition"))
        ):
            continue
        column_ref = f"{object_ref}.{column_name}"
        column_payload = {
            "schema": schema,
            "tableName": table_name,
            "columnName": column_name,
            "logicalName": column.get("logicalName"),
            "description": column.get("description"),
            "descriptionStatus": column.get("descriptionStatus", "CONFIRMED"),
            "dataType": column.get("dataType"),
            "score": 80,
        }
        related.append(
            MetadataRelatedMetadata(
                kind="COLUMN",
                objectRef=column_ref,
                score=80,
                summary=_safe_text(
                    column.get("description")
                    or column.get("logicalName")
                    or column_name
                    or column_ref
                ),
                evidenceRefs=evidence_refs,
                payload=_safe_payload(column_payload),
            )
        )
        facts.append(
            _fact(
                f"metadata_design.table_schema_column.{fact_prefix}.{column_index}",
                column_ref,
                evidence_refs,
            )
        )


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
    candidate_context: CandidateContext,
    policy: dict[str, Any],
) -> MetadataTableProposal:
    table_name, table_reasons = _standard_table_name(request, policy)
    table_description = _safe_text(
        request.design_inputs.table_description or request.message[:200]
    )
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
        metadata_column = _common_column_from_metadata(name, candidate_context)
        columns.append(metadata_column or _common_column_from_policy(name, common))
        existing_names.add(name)
    proposal_reasons = [
        *table_reasons,
        "REVIEW_REQUIRED: PK/FK and index structure must be confirmed before applying.",
    ]
    script = _render_create_table_preview(
        schema_name="dbo",
        table_name=table_name,
        table_description=table_description,
        columns=columns,
        review_reasons=proposal_reasons,
    )
    return MetadataTableProposal(
        schema="dbo",
        tableName=table_name,
        tableDescription=table_description,
        columns=columns,
        createTableScriptPreview=script,
        evidenceRefs=_dedupe_strings(
            [ref for column in columns for ref in column.evidence_refs]
        ),
        reviewRequired=True,
        reviewReasons=proposal_reasons,
    )


def _common_column_from_metadata(
    name: str,
    candidate_context: CandidateContext,
) -> MetadataTableProposalColumn | None:
    for item in candidate_context.related_metadata:
        if item.kind != "COLUMN":
            continue
        payload = item.payload
        column_name = _standard_identifier(
            str(payload.get("columnName") or item.object_ref.rsplit(".", 1)[-1])
        )
        if column_name != name:
            continue
        data_type = _safe_text(payload.get("dataType"))
        if not data_type:
            continue
        description = _safe_text(payload.get("description") or payload.get("logicalName"))
        return MetadataTableProposalColumn(
            name=name,
            dataType=data_type,
            nullable=False,
            description=description or _common_column_description(name),
            source="METADATA",
            evidenceRefs=item.evidence_refs,
            reviewRequired=not bool(description),
            reviewReasons=(
                []
                if description
                else ["REVIEW_REQUIRED: common column description was not confirmed."]
            ),
        )
    return None


def _common_column_from_policy(name: str, common: dict[str, Any]) -> MetadataTableProposalColumn:
    return MetadataTableProposalColumn(
        name=name,
        dataType=str(common.get("type") or "VARCHAR(500)"),
        nullable=False,
        description=_common_column_description(name),
        source="STANDARD_POLICY",
        evidenceRefs=[POLICY_REF],
        reviewRequired=False,
        reviewReasons=[],
    )


def _common_column_description(name: str) -> str:
    descriptions = {
        "CRE_USR_ID": "등록 사용자 ID",
        "CRE_DTM": "등록 일시",
        "UPD_USR_ID": "수정 사용자 ID",
        "UPD_DTM": "수정 일시",
    }
    return descriptions.get(name, "표준 공통 컬럼")


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
    table_description: str,
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
    lines.extend(
        _render_description_preview(
            schema_name=schema_name,
            table_name=table_name,
            table_description=table_description,
            columns=columns,
        )
    )
    return ensure_trailing_newline("\n".join(lines))


def _render_description_preview(
    *,
    schema_name: str,
    table_name: str,
    table_description: str,
    columns: list[MetadataTableProposalColumn],
) -> list[str]:
    lines = [
        "",
        "-- REVIEW_REQUIRED: MS_Description preview only; manual schema review required.",
    ]
    if table_description:
        lines.extend(
            [
                "-- REVIEW_REQUIRED: table description must be confirmed before applying.",
                _extended_property_sql(
                    value=table_description,
                    schema_name=schema_name,
                    table_name=table_name,
                ),
            ]
        )
    for column in columns:
        description = _safe_text(column.description)
        if not description:
            lines.append(
                f"-- REVIEW_REQUIRED: [{column.name}] has no confirmed description."
            )
            continue
        if column.review_required:
            reasons = "; ".join(column.review_reasons) or "column metadata requires review"
            lines.append(f"-- REVIEW_REQUIRED: [{column.name}] {reasons}")
        lines.append(
            _extended_property_sql(
                value=description,
                schema_name=schema_name,
                table_name=table_name,
                column_name=column.name,
            )
        )
    return lines


def _extended_property_sql(
    *,
    value: str,
    schema_name: str,
    table_name: str,
    column_name: str | None = None,
) -> str:
    parts = [
        "EXEC sys.sp_addextendedproperty",
        "    @name = N'MS_Description',",
        f"    @value = N'{_escape_sql_unicode_literal(value)}',",
        "    @level0type = N'SCHEMA',",
        f"    @level0name = N'{_escape_sql_unicode_literal(schema_name)}',",
        "    @level1type = N'TABLE',",
        f"    @level1name = N'{_escape_sql_unicode_literal(table_name)}'",
    ]
    if column_name:
        parts[-1] = f"{parts[-1]},"
        parts.extend(
            [
                "    @level2type = N'COLUMN',",
                f"    @level2name = N'{_escape_sql_unicode_literal(column_name)}'",
            ]
        )
    parts[-1] = f"{parts[-1]};"
    return "\n".join(parts)


def _escape_sql_unicode_literal(value: str) -> str:
    return _safe_text(value).replace("'", "''")


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
    expected_name = _expected_column_name_for_field(field)
    text_tokens = {
        _normalize_match_text(field.description),
    } - {""}
    if not expected_name and field.name:
        text_tokens.add(_normalize_match_text(field.name))
    scored: list[tuple[int, MetadataRelatedMetadata]] = []
    for candidate in candidates:
        candidate_name = _standard_identifier(str(candidate.payload.get("columnName") or ""))
        payload_text = " ".join(
            _normalize_match_text(candidate.payload.get(key))
            for key in ("columnName", "logicalName", "description")
        )
        exact_name_match = bool(expected_name and candidate_name == expected_name)
        has_text_match = any(token and token in payload_text for token in text_tokens)
        if not exact_name_match and not has_text_match:
            continue
        match_bonus = 1000 if exact_name_match else 100
        scored.append((candidate.score + match_bonus, candidate))
    scored.sort(key=lambda item: item[0], reverse=True)
    return scored[0][1] if scored and scored[0][0] > 0 else None


def _expected_column_name_for_field(field: MetadataDesignFieldInput) -> str:
    known = _known_field_for_text(" ".join([field.name or "", field.description or ""]))
    if known:
        return known[0]
    return _standard_identifier(field.name or "")


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
    if normalized.startswith("REVIEW_REQUIRED_FIELD_"):
        reasons.append(
            "REVIEW_REQUIRED: approved abbreviation was not found for the requested meaning."
        )
    reasons.extend(_identifier_policy_review_reasons(normalized, policy))
    return normalized, data_type, reasons


def _standard_table_name(
    request: MetadataDesignRunRequest,
    policy: dict[str, Any],
) -> tuple[str, list[str]]:
    hint = request.design_inputs.table_name_hint
    message_candidate = _table_name_from_message(request.message)
    if message_candidate:
        return message_candidate, _table_name_review_reasons(message_candidate, policy)
    if hint and not _table_name_hint_is_reference_scope(hint):
        candidate = _standard_identifier(hint)
        if candidate:
            return candidate, _table_name_review_reasons(candidate, policy)
    prefix = policy.get("schema_generation_rules", {}).get("new_platform_table_prefix", "PPM")
    return f"{prefix}_META_DESIGN_TMP", [
        "REVIEW_REQUIRED: table name was inferred because no confirmed table name was supplied."
    ]


def _table_name_review_reasons(table_name: str, policy: dict[str, Any]) -> list[str]:
    approved_roles = {
        _standard_identifier(role)
        for role in policy.get("table_naming", {}).get("approved_roles", [])
    }
    parts = [part for part in _standard_identifier(table_name).split("_") if part]
    if approved_roles and parts and parts[-1] not in approved_roles:
        return ["REVIEW_REQUIRED: table role suffix must be confirmed against platform naming rules."]
    return []


def _name_from_description(source: str, policy: dict[str, Any], index: int) -> str:
    known = _known_field_for_text(source)
    if known:
        return known[0]
    text = _normalize_match_text(source)
    class_word = _class_word_from_text(source)
    if class_word:
        term = _term_abbreviation_from_text(source)
        if term:
            return f"{term}_{class_word}"
        return f"UNCONFIRMED_{index + 1}_{class_word}"
    if any(token in text for token in ("datetime", "timestamp", "일시")):
        return f"UNCONFIRMED_{index + 1}_DTM"
    if any(token in text for token in ("date", "날짜", "일자")):
        return f"UNCONFIRMED_{index + 1}_DT"
    if any(token in text for token in ("amount", "amt", "금액")):
        return f"UNCONFIRMED_{index + 1}_AMT"
    if any(token in text for token in ("quantity", "qty", "수량")):
        return f"UNCONFIRMED_{index + 1}_QTY"
    if any(token in text for token in ("code", "코드")):
        return f"UNCONFIRMED_{index + 1}_CD"
    if any(token in text for token in ("name", "이름", "명")):
        return f"UNCONFIRMED_{index + 1}_NM"
    return f"UNCONFIRMED_{index + 1}_VAL"


def _term_abbreviation_from_text(source: str) -> str:
    text = _normalize_match_text(source)
    for tokens, abbreviation in (
        (("계약", "contract", "ctrt"), "CTRT"),
        (("주문", "발주", "order", "ordr"), "ORDR"),
        (("알림", "notification", "notice", "ntc"), "NTC"),
        (("테스트", "test"), "TEST"),
    ):
        if any(token in text for token in tokens):
            return abbreviation
    return ""


def _identifier_policy_review_reasons(identifier: str, policy: dict[str, Any]) -> list[str]:
    name = _standard_identifier(identifier)
    if not name:
        return ["REVIEW_REQUIRED: approved abbreviation was not found for the requested meaning."]
    class_words = {
        _standard_identifier(key)
        for key in policy.get("column_naming", {}).get("class_words", {})
    }
    qualifiers = {
        _standard_identifier(item)
        for item in policy.get("column_naming", {}).get("qualifiers", [])
    }
    approved = set()
    for group in policy.get("approved_abbreviations", {}).values():
        if isinstance(group, dict):
            approved.update(_standard_identifier(key) for key in group)
    ignored = class_words | qualifiers | {"", "UNCONFIRMED"}
    unknown = [
        part
        for part in name.split("_")
        if part and not part.isdigit() and part not in ignored and part not in approved
    ]
    if not unknown:
        return []
    return [
        "REVIEW_REQUIRED: approved abbreviation was not confirmed for "
        + ", ".join(_dedupe_strings(unknown))
        + "."
    ]


def _type_from_text(source: str, policy: dict[str, Any]) -> str:
    known = _known_field_for_text(source)
    if known:
        return known[2]
    text = _normalize_match_text(source)
    class_words = policy.get("column_naming", {}).get("class_words", {})
    class_word = _class_word_from_text(source)
    if class_word:
        return str(class_words.get(class_word, {}).get("standard_type") or "VARCHAR(500)")
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


def _class_word_from_text(source: str) -> str:
    text = _normalize_match_text(source)
    if any(token in text for token in ("yn", "여부", "유무")):
        return "YN"
    if any(token in text for token in ("차수", "순번", "sequence", "seq")):
        return "SEQ_NO"
    if any(token in text for token in ("번호", "number", " no", "_no")):
        return "NO"
    if any(token in text for token in ("일시", "datetime", "timestamp")):
        return "DTM"
    if any(token in text for token in ("날짜", "일자", "date")):
        return "DT"
    if any(token in text for token in ("금액", "amount", "amt")):
        return "AMT"
    if any(token in text for token in ("수량", "quantity", "qty")):
        return "QTY"
    if any(token in text for token in ("건수", "count", "cnt")):
        return "CNT"
    if any(token in text for token in ("코드", "code")):
        return "CD"
    if any(token in text for token in ("유형", "종류", "type", "kind", "tp_cd")):
        return "TP_CD"
    if any(token in text for token in ("내용", "content", "cntnt")):
        return "CNTNT"
    if any(token in text for token in ("설명", "메모", "description", "desc", "memo")):
        return "DESC"
    if any(token in text for token in ("이름", "명", "name")):
        return "NM"
    return ""


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
