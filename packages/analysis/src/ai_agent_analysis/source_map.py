from __future__ import annotations

import hashlib
import os
import re
from collections.abc import Iterable, Mapping, Sequence
from typing import Any, Literal

from pydantic import BaseModel, Field

SOURCE_MAP_VERSION = "procedure_source_map@0.1.0"
CONTEXT_PACK_VERSION = "procedure_context_pack@0.1.0"
DEFAULT_CONTEXT_STAGES = (
    "deterministic_evidence_digest",
    "business_rule_extraction",
    "conversion_readiness",
    "migration_guide_insights",
    "evidence_critic",
    "repair",
    "language_repair",
)

SourceSpanKind = Literal[
    "SIGNATURE",
    "PARAMETER_BLOCK",
    "DML",
    "RESULT_SET",
    "CALL",
    "TEMP_TABLE",
    "TRANSACTION",
    "TRY_CATCH",
    "DYNAMIC_SQL",
    "CONTROL_FLOW",
    "OTHER",
]

_STAGE_PRIORITIES: dict[str, tuple[str, ...]] = {
    "deterministic_evidence_digest": (
        "SIGNATURE",
        "PARAMETER_BLOCK",
        "DML",
        "RESULT_SET",
        "CALL",
        "TEMP_TABLE",
        "TRANSACTION",
        "TRY_CATCH",
        "DYNAMIC_SQL",
    ),
    "business_rule_extraction": (
        "CONTROL_FLOW",
        "DML",
        "RESULT_SET",
        "CALL",
        "DYNAMIC_SQL",
        "TEMP_TABLE",
    ),
    "conversion_readiness": (
        "TRANSACTION",
        "TRY_CATCH",
        "DML",
        "TEMP_TABLE",
        "CALL",
        "DYNAMIC_SQL",
        "RESULT_SET",
    ),
    "migration_guide_insights": (
        "DML",
        "RESULT_SET",
        "CALL",
        "TEMP_TABLE",
        "TRANSACTION",
        "TRY_CATCH",
        "DYNAMIC_SQL",
        "CONTROL_FLOW",
    ),
    "evidence_critic": (
        "DYNAMIC_SQL",
        "TEMP_TABLE",
        "TRANSACTION",
        "TRY_CATCH",
        "CALL",
        "RESULT_SET",
        "DML",
    ),
    "repair": (
        "DYNAMIC_SQL",
        "DML",
        "RESULT_SET",
        "CALL",
        "TRANSACTION",
        "TRY_CATCH",
    ),
    "language_repair": (),
}

_SOURCE_KEYWORD_RE = re.compile(
    r"^\s*(SELECT|INSERT|UPDATE|DELETE|MERGE|EXEC(?:UTE)?|IF|ELSE|WHILE|BEGIN\s+TRY|"
    r"END\s+TRY|BEGIN\s+CATCH|END\s+CATCH|BEGIN\s+TRAN|COMMIT|ROLLBACK|"
    r"CREATE\s+TABLE\s+#|DECLARE\s+@\w+\s+TABLE)\b",
    re.IGNORECASE,
)
_OBJECT_REF_RE = re.compile(
    r"(?i)\b(?:FROM|JOIN|INTO|UPDATE|MERGE\s+INTO|EXEC(?:UTE)?)\s+"
    r"(?P<name>(?:\[[^\]]+\]|\w+)(?:\s*\.\s*(?:\[[^\]]+\]|\w+)){0,3})"
)
_TEMP_TABLE_RE = re.compile(r"(?i)(?:#\w+|DECLARE\s+@\w+\s+TABLE|CREATE\s+TABLE\s+#)")
_DYNAMIC_SQL_RE = re.compile(r"(?i)\b(sp_executesql|EXEC\s*\(|EXEC\s+@\w+|OPENQUERY)\b")
_DML_RE = re.compile(r"(?i)\b(INSERT|UPDATE|DELETE|MERGE)\b")
_RESULT_RE = re.compile(r"(?i)\bSELECT\b")
_CALL_RE = re.compile(r"(?i)\bEXEC(?:UTE)?\b")
_TRANSACTION_RE = re.compile(r"(?i)\b(BEGIN\s+TRAN|COMMIT|ROLLBACK|XACT_ABORT)\b")
_TRY_CATCH_RE = re.compile(r"(?i)\b(BEGIN\s+TRY|END\s+TRY|BEGIN\s+CATCH|END\s+CATCH)\b")
_CONTROL_FLOW_RE = re.compile(r"(?i)\b(IF|ELSE|WHILE|CASE)\b")


class ProcedureSourceSpan(BaseModel):
    span_id: str = Field(alias="spanId")
    kind: SourceSpanKind
    start_line: int = Field(alias="startLine")
    end_line: int = Field(alias="endLine")
    referenced_objects: list[str] = Field(default_factory=list, alias="referencedObjects")
    risk_tags: list[str] = Field(default_factory=list, alias="riskTags")
    evidence_refs: list[str] = Field(default_factory=list, alias="evidenceRefs")

    def to_storage_dict(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, mode="json")


class ProcedureSourceMap(BaseModel):
    version: str = SOURCE_MAP_VERSION
    source_name: str = Field(alias="sourceName")
    source_hash_sha256: str = Field(alias="sourceHashSha256")
    total_lines: int = Field(alias="totalLines")
    spans: list[ProcedureSourceSpan] = Field(default_factory=list)

    def to_storage_dict(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, mode="json")

    @property
    def analysis_coverage(self) -> dict[str, Any]:
        span_count_by_kind: dict[str, int] = {}
        risk_tag_count_by_kind: dict[str, int] = {}
        for span in self.spans:
            span_count_by_kind[span.kind] = span_count_by_kind.get(span.kind, 0) + 1
            for risk in span.risk_tags:
                risk_tag_count_by_kind[risk] = risk_tag_count_by_kind.get(risk, 0) + 1
        return {
            "sourceMapVersion": self.version,
            "totalLineCount": self.total_lines,
            "spanCount": len(self.spans),
            "spanCountByKind": span_count_by_kind,
            "riskTagCountByKind": risk_tag_count_by_kind,
            "hasDynamicSql": bool(risk_tag_count_by_kind.get("DYNAMIC_SQL")),
            "hasTempTables": bool(risk_tag_count_by_kind.get("TEMP_TABLE")),
            "hasTransaction": bool(risk_tag_count_by_kind.get("TRANSACTION")),
            "hasTryCatch": bool(risk_tag_count_by_kind.get("TRY_CATCH")),
        }


class RetrievedSourceSpan(BaseModel):
    span_id: str = Field(alias="spanId")
    kind: SourceSpanKind
    start_line: int = Field(alias="startLine")
    end_line: int = Field(alias="endLine")
    referenced_objects: list[str] = Field(default_factory=list, alias="referencedObjects")
    risk_tags: list[str] = Field(default_factory=list, alias="riskTags")
    evidence_refs: list[str] = Field(default_factory=list, alias="evidenceRefs")
    text: str = Field(default="", repr=False)

    def to_prompt_dict(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, mode="json")

    def to_storage_dict(self) -> dict[str, Any]:
        payload = self.model_dump(by_alias=True, mode="json")
        payload.pop("text", None)
        return payload


class ContextPack(BaseModel):
    version: str = CONTEXT_PACK_VERSION
    target_ref: str = Field(alias="targetRef")
    stage: str
    mode: Literal["NONE", "RETRIEVED_SPANS"] = "RETRIEVED_SPANS"
    budget_status: str = Field(default="WITHIN_BUDGET", alias="budgetStatus")
    token_budget: int = Field(default=0, alias="tokenBudget")
    estimated_source_tokens: int = Field(default=0, alias="estimatedSourceTokens")
    selected_spans: list[RetrievedSourceSpan] = Field(default_factory=list, alias="selectedSpans")
    skipped_span_count: int = Field(default=0, alias="skippedSpanCount")
    analysis_coverage: dict[str, Any] = Field(default_factory=dict, alias="analysisCoverage")
    review_markers: list[dict[str, Any]] = Field(default_factory=list, alias="reviewMarkers")

    def to_prompt_dict(self) -> dict[str, Any]:
        return self.model_dump(by_alias=True, mode="json")

    def to_storage_dict(self) -> dict[str, Any]:
        payload = self.model_dump(by_alias=True, mode="json")
        payload["selectedSpans"] = [span.to_storage_dict() for span in self.selected_spans]
        return payload

    def summary(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "targetRef": self.target_ref,
            "stage": self.stage,
            "mode": self.mode,
            "budgetStatus": self.budget_status,
            "tokenBudget": self.token_budget,
            "estimatedSourceTokens": self.estimated_source_tokens,
            "selectedSpanCount": len(self.selected_spans),
            "skippedSpanCount": self.skipped_span_count,
            "analysisCoverage": dict(self.analysis_coverage),
            "reviewMarkers": list(self.review_markers),
        }


class SourceSpanExtractionOutput(BaseModel):
    source_map: ProcedureSourceMap = Field(alias="sourceMap")
    context_packs: dict[str, ContextPack] = Field(default_factory=dict, alias="contextPacks")

    def to_storage_dict(self) -> dict[str, Any]:
        return {
            "sourceMap": self.source_map.to_storage_dict(),
            "contextPacks": {
                stage: pack.to_storage_dict() for stage, pack in self.context_packs.items()
            },
        }


def build_procedure_source_map(
    sql_text: str,
    *,
    source_name: str = "<memory>",
) -> ProcedureSourceMap:
    lines = sql_text.splitlines()
    spans: list[ProcedureSourceSpan] = []
    signature_span = _signature_span(lines)
    if signature_span is not None:
        spans.append(_span_from_range("spn001", "SIGNATURE", signature_span, lines))
        if _contains_parameter_text(_line_range_text(lines, *signature_span)):
            spans.append(_span_from_range("spn002", "PARAMETER_BLOCK", signature_span, lines))

    next_index = 3
    for start, end in _statement_ranges(lines):
        text = _line_range_text(lines, start, end)
        kind = _classify_span(text)
        if kind == "OTHER" and not _meaningful_span(text):
            continue
        spans.append(
            _span_from_range(
                f"spn{next_index:03d}",
                kind,
                (start, end),
                lines,
            )
        )
        next_index += 1

    deduped = _dedupe_spans(spans)
    return ProcedureSourceMap(
        sourceName=source_name,
        sourceHashSha256=hashlib.sha256(sql_text.encode("utf-8")).hexdigest(),
        totalLines=len(lines),
        spans=deduped,
    )


def build_context_packs(
    *,
    sql_text: str,
    source_map: ProcedureSourceMap,
    target_ref: str,
    mode: str = "RETRIEVED_SPANS",
    stages: Sequence[str] = DEFAULT_CONTEXT_STAGES,
    max_spans: int | None = None,
    source_token_budget: int | None = None,
) -> dict[str, ContextPack]:
    normalized_mode = "RETRIEVED_SPANS" if mode == "RETRIEVED_SPANS" else "NONE"
    max_selected = max(1, max_spans or _env_int("LLM_SP_MAX_RETRIEVED_SPANS", 24))
    budget = max(256, source_token_budget or _env_int("LLM_SEMANTIC_SOURCE_TOKEN_BUDGET", 32000))
    lines = sql_text.splitlines()
    return {
        stage: build_context_pack(
            sql_lines=lines,
            source_map=source_map,
            target_ref=target_ref,
            stage=stage,
            mode=normalized_mode,
            max_spans=max_selected,
            source_token_budget=budget,
        )
        for stage in stages
    }


def build_context_pack(
    *,
    sql_lines: Sequence[str],
    source_map: ProcedureSourceMap,
    target_ref: str,
    stage: str,
    mode: str = "RETRIEVED_SPANS",
    max_spans: int = 24,
    source_token_budget: int = 32000,
) -> ContextPack:
    if mode != "RETRIEVED_SPANS":
        return ContextPack(
            targetRef=target_ref,
            stage=stage,
            mode="NONE",
            budgetStatus="NO_SOURCE_CONTEXT",
            tokenBudget=source_token_budget,
            analysisCoverage=source_map.analysis_coverage,
            skippedSpanCount=len(source_map.spans),
        )

    selected: list[RetrievedSourceSpan] = []
    estimated_tokens = 0
    for span in _rank_spans_for_stage(source_map.spans, stage):
        if len(selected) >= max_spans:
            continue
        text = _line_range_text(sql_lines, span.start_line, span.end_line)
        span_tokens = _estimate_tokens(text)
        if selected and estimated_tokens + span_tokens > source_token_budget:
            continue
        selected.append(
            RetrievedSourceSpan(
                spanId=span.span_id,
                kind=span.kind,
                startLine=span.start_line,
                endLine=span.end_line,
                referencedObjects=list(span.referenced_objects),
                riskTags=list(span.risk_tags),
                evidenceRefs=list(span.evidence_refs),
                text=text,
            )
        )
        estimated_tokens += span_tokens

    skipped_count = max(0, len(source_map.spans) - len(selected))
    budget_status = "WITHIN_BUDGET"
    markers: list[dict[str, Any]] = []
    if skipped_count:
        budget_status = "TRUNCATED_TO_BUDGET"
        markers.append(
            {
                "code": "SOURCE_CONTEXT_TRUNCATED",
                "message": "Source context was bounded to selected spans for model input.",
                "status": "REVIEW_REQUIRED",
                "evidenceRefs": [
                    span.evidence_refs[0] for span in selected[:1] if span.evidence_refs
                ],
            }
        )
    return ContextPack(
        targetRef=target_ref,
        stage=stage,
        mode="RETRIEVED_SPANS",
        budgetStatus=budget_status,
        tokenBudget=source_token_budget,
        estimatedSourceTokens=estimated_tokens,
        selectedSpans=selected,
        skippedSpanCount=skipped_count,
        analysisCoverage=source_map.analysis_coverage,
        reviewMarkers=markers,
    )


def shrink_context_pack(pack: Mapping[str, Any] | None, *, status: str) -> dict[str, Any] | None:
    if not isinstance(pack, Mapping):
        return None
    selected = pack.get("selectedSpans")
    if not isinstance(selected, list):
        return dict(pack)
    keep_count = max(1, len(selected) // 2) if selected else 0
    shrunk = dict(pack)
    shrunk["selectedSpans"] = selected[:keep_count]
    shrunk["skippedSpanCount"] = int(pack.get("skippedSpanCount") or 0) + max(
        0,
        len(selected) - keep_count,
    )
    shrunk["budgetStatus"] = status
    shrunk["estimatedSourceTokens"] = sum(
        _estimate_tokens(str(item.get("text") or ""))
        for item in selected[:keep_count]
        if isinstance(item, Mapping)
    )
    markers = list(pack.get("reviewMarkers") or [])
    markers.append(
        {
            "code": "LLM_CONTEXT_BUDGET_REVIEW_REQUIRED",
            "message": "Model context exceeded provider limits; source context was reduced.",
            "status": "REVIEW_REQUIRED",
            "evidenceRefs": _first_context_evidence_refs(selected),
        }
    )
    shrunk["reviewMarkers"] = markers
    return shrunk


def without_source_text_context_pack(
    pack: Mapping[str, Any] | None,
    *,
    status: str = "FALLBACK_NO_SOURCE",
) -> dict[str, Any] | None:
    if not isinstance(pack, Mapping):
        return None
    fallback = dict(pack)
    selected = pack.get("selectedSpans")
    fallback["selectedSpans"] = [
        {key: value for key, value in dict(item).items() if key != "text"}
        for item in selected
        if isinstance(item, Mapping)
    ] if isinstance(selected, list) else []
    fallback["budgetStatus"] = status
    fallback["estimatedSourceTokens"] = 0
    markers = list(pack.get("reviewMarkers") or [])
    markers.append(
        {
            "code": "LLM_CONTEXT_BUDGET_REVIEW_REQUIRED",
            "message": (
                "Model analysis used evidence digest without raw source spans after "
                "context fallback."
            ),
            "status": "REVIEW_REQUIRED",
            "evidenceRefs": _first_context_evidence_refs(selected),
        }
    )
    fallback["reviewMarkers"] = markers
    return fallback


def context_pack_summary(pack: Mapping[str, Any] | None) -> dict[str, Any]:
    if not isinstance(pack, Mapping):
        return {
            "mode": "NONE",
            "budgetStatus": "NO_SOURCE_CONTEXT",
            "selectedSpanCount": 0,
            "skippedSpanCount": 0,
            "reviewMarkers": [],
        }
    selected = pack.get("selectedSpans")
    selected_count = len(selected) if isinstance(selected, list) else 0
    return {
        "version": pack.get("version"),
        "targetRef": pack.get("targetRef"),
        "stage": pack.get("stage"),
        "mode": pack.get("mode", "NONE"),
        "budgetStatus": pack.get("budgetStatus", "UNKNOWN"),
        "tokenBudget": pack.get("tokenBudget", 0),
        "estimatedSourceTokens": pack.get("estimatedSourceTokens", 0),
        "selectedSpanCount": selected_count,
        "skippedSpanCount": int(pack.get("skippedSpanCount") or 0),
        "analysisCoverage": dict(pack.get("analysisCoverage") or {}),
        "reviewMarkers": [
            dict(item) for item in pack.get("reviewMarkers", []) if isinstance(item, Mapping)
        ],
    }


def source_context_contains_text(pack: Mapping[str, Any] | None) -> bool:
    selected = pack.get("selectedSpans") if isinstance(pack, Mapping) else None
    return isinstance(selected, list) and any(
        isinstance(item, Mapping) and bool(item.get("text")) for item in selected
    )


def _signature_span(lines: Sequence[str]) -> tuple[int, int] | None:
    start: int | None = None
    for index, line in enumerate(lines, start=1):
        if re.search(r"(?i)\bCREATE\s+(?:OR\s+ALTER\s+)?PROC(?:EDURE)?\b", line):
            start = index
            break
    if start is None:
        return None
    end = start
    for index in range(start, min(len(lines), start + 80) + 1):
        if re.search(r"(?i)^\s*AS\s*$|\bAS\s+BEGIN\b", lines[index - 1]):
            end = index
            break
    return start, end


def _statement_ranges(lines: Sequence[str]) -> Iterable[tuple[int, int]]:
    current_start: int | None = None
    for index, line in enumerate(lines, start=1):
        if not line.strip():
            if current_start is not None:
                yield current_start, index - 1
                current_start = None
            continue
        starts_new = bool(_SOURCE_KEYWORD_RE.search(line))
        if starts_new and current_start is not None:
            yield current_start, index - 1
            current_start = index
        elif current_start is None:
            current_start = index
        if line.rstrip().endswith(";") and current_start is not None:
            yield current_start, index
            current_start = None
    if current_start is not None:
        yield current_start, len(lines)


def _span_from_range(
    span_id: str,
    kind: SourceSpanKind,
    line_range: tuple[int, int],
    lines: Sequence[str],
) -> ProcedureSourceSpan:
    start, end = line_range
    text = _line_range_text(lines, start, end)
    risk_tags = _risk_tags(kind, text)
    return ProcedureSourceSpan(
        spanId=span_id,
        kind=kind,
        startLine=start,
        endLine=end,
        referencedObjects=_referenced_objects(text),
        riskTags=risk_tags,
        evidenceRefs=[f"source.span.{span_id}"],
    )


def _classify_span(text: str) -> SourceSpanKind:
    if _DYNAMIC_SQL_RE.search(text):
        return "DYNAMIC_SQL"
    if _TEMP_TABLE_RE.search(text):
        return "TEMP_TABLE"
    if _TRY_CATCH_RE.search(text):
        return "TRY_CATCH"
    if _TRANSACTION_RE.search(text):
        return "TRANSACTION"
    if _DML_RE.search(text):
        return "DML"
    if _CALL_RE.search(text):
        return "CALL"
    if _RESULT_RE.search(text):
        return "RESULT_SET"
    if _CONTROL_FLOW_RE.search(text):
        return "CONTROL_FLOW"
    return "OTHER"


def _risk_tags(kind: SourceSpanKind, text: str) -> list[str]:
    tags = []
    if kind == "DYNAMIC_SQL" or _DYNAMIC_SQL_RE.search(text):
        tags.append("DYNAMIC_SQL")
    if kind == "TEMP_TABLE" or _TEMP_TABLE_RE.search(text):
        tags.append("TEMP_TABLE")
    if kind == "TRANSACTION" or _TRANSACTION_RE.search(text):
        tags.append("TRANSACTION")
    if kind == "TRY_CATCH" or _TRY_CATCH_RE.search(text):
        tags.append("TRY_CATCH")
    if _DML_RE.search(text):
        tags.append("DML_WRITE")
    if _RESULT_RE.search(text):
        tags.append("RESULT_SHAPE")
    if _CALL_RE.search(text):
        tags.append("PROCEDURE_CALL")
    return list(dict.fromkeys(tags))


def _referenced_objects(text: str) -> list[str]:
    refs = []
    for match in _OBJECT_REF_RE.finditer(text):
        value = _normalize_object_ref(match.group("name"))
        if value and not value.startswith("#") and value.upper() not in {"SELECT", "VALUES"}:
            refs.append(value)
    return list(dict.fromkeys(refs))


def _normalize_object_ref(value: str) -> str:
    tokens = [
        token.strip().strip("[]")
        for token in re.split(r"\s*\.\s*", value.strip())
        if token.strip()
    ]
    return ".".join(tokens)


def _rank_spans_for_stage(
    spans: Sequence[ProcedureSourceSpan],
    stage: str,
) -> list[ProcedureSourceSpan]:
    priorities = _STAGE_PRIORITIES.get(stage, _STAGE_PRIORITIES["deterministic_evidence_digest"])
    score_by_kind = {kind: index for index, kind in enumerate(priorities)}

    def score(span: ProcedureSourceSpan) -> tuple[int, int, int]:
        return (
            score_by_kind.get(span.kind, len(score_by_kind) + 1),
            0 if span.risk_tags else 1,
            span.start_line,
        )

    ranked = sorted(spans, key=score)
    if stage == "language_repair":
        return []
    return ranked


def _line_range_text(lines: Sequence[str], start_line: int, end_line: int) -> str:
    return "\n".join(lines[max(0, start_line - 1) : min(len(lines), end_line)])


def _contains_parameter_text(text: str) -> bool:
    return bool(re.search(r"@\w+\s+[\w\[\]]+", text))


def _meaningful_span(text: str) -> bool:
    return bool(text.strip()) and text.strip().upper() not in {"BEGIN", "END"}


def _dedupe_spans(spans: Sequence[ProcedureSourceSpan]) -> list[ProcedureSourceSpan]:
    deduped: list[ProcedureSourceSpan] = []
    seen: set[tuple[str, int, int]] = set()
    for span in spans:
        key = (span.kind, span.start_line, span.end_line)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(span)
    return deduped


def _estimate_tokens(text: str) -> int:
    return max(1, (len(text) + 3) // 4)


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        return default


def _first_context_evidence_refs(value: Any) -> list[str]:
    if isinstance(value, list):
        for item in value:
            if not isinstance(item, Mapping):
                continue
            refs = item.get("evidenceRefs")
            if isinstance(refs, list):
                return [str(ref) for ref in refs if str(ref)]
    return []
