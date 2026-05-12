from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

VALID_TOOL_FACT_PREFIXES = ("mcp.", "metadata.profile.")
_SEMANTIC_CLAIM_FIELDS = (
    "businessRules",
    "modernizationPoints",
    "riskFlags",
    "reviewMarkers",
    "conversionGuidance",
    "migrationGuideInsights",
)
_METADATA_CLAIM_FIELDS = ("objectInsights", "dtoReadiness", "reviewMarkers")
_PLANNING_STAGES = {"ai_tool_planning", "ai_metadata_tool_planning"}


def attach_planner_metrics_to_ai_tool_evidence(
    ai_tool_evidence: Mapping[str, Any] | None,
    *,
    deterministic_facts: Sequence[Mapping[str, Any]] = (),
    component_invocations: Sequence[Mapping[str, Any]] = (),
    structured_output: Mapping[str, Any] | None = None,
    planned_request_count: int | None = None,
    failed_tool_call_count: int | None = None,
    deduped_request_count: int | None = None,
    budget_exhausted: bool | None = None,
) -> dict[str, Any]:
    evidence = dict(ai_tool_evidence or {})
    evidence["plannerMetrics"] = build_planner_metrics(
        ai_tool_evidence=evidence,
        deterministic_facts=deterministic_facts,
        component_invocations=component_invocations,
        structured_output=structured_output,
        planned_request_count=planned_request_count,
        failed_tool_call_count=failed_tool_call_count,
        deduped_request_count=deduped_request_count,
        budget_exhausted=budget_exhausted,
    )
    return evidence


def build_planner_metrics(
    *,
    ai_tool_evidence: Mapping[str, Any] | None,
    deterministic_facts: Sequence[Mapping[str, Any]] = (),
    component_invocations: Sequence[Mapping[str, Any]] = (),
    structured_output: Mapping[str, Any] | None = None,
    planned_request_count: int | None = None,
    failed_tool_call_count: int | None = None,
    deduped_request_count: int | None = None,
    budget_exhausted: bool | None = None,
) -> dict[str, Any]:
    evidence = ai_tool_evidence or {}
    components = [dict(item) for item in component_invocations if isinstance(item, Mapping)]
    tool_results = _mapping_list(evidence.get("toolResults"))
    blocked_requests = _mapping_list(evidence.get("blockedRequests"))
    existing = evidence.get("plannerMetrics")
    existing_metrics = dict(existing) if isinstance(existing, Mapping) else {}

    planned = _first_int(
        planned_request_count,
        existing_metrics.get("plannedRequestCount"),
        sum(
            _int(component.get("toolRequestCount"))
            for component in components
            if str(component.get("stage") or "") in _PLANNING_STAGES
        ),
    )
    executed = max(_int(evidence.get("toolCallCount")), len(tool_results))
    blocked = max(_int(existing_metrics.get("blockedRequestCount")), len(blocked_requests))
    failed = _first_int(
        failed_tool_call_count,
        existing_metrics.get("failedToolCallCount"),
        _failed_tool_call_count(components, blocked),
    )
    deduped = _first_int(
        deduped_request_count,
        existing_metrics.get("dedupedRequestCount"),
        max(planned - executed - blocked - failed, 0),
    )
    exhausted = bool(
        budget_exhausted
        if budget_exhausted is not None
        else existing_metrics.get("budgetExhausted")
        or "AI_TOOL_CALL_BUDGET_EXHAUSTED" in _string_list(evidence.get("caveats"))
    )

    evidence_fact_ids = _tool_fact_ids(
        tool_results=tool_results,
        deterministic_facts=deterministic_facts,
    )
    claim_items = _claim_items(structured_output)
    cited_fact_ids = sorted(
        {
            ref
            for item in claim_items
            for ref in _evidence_refs(item)
            if ref in evidence_fact_ids
        }
    )
    supported_claim_count = sum(
        1
        for item in claim_items
        if any(ref in evidence_fact_ids for ref in _evidence_refs(item))
    )
    evidence_fact_count = len(evidence_fact_ids)
    cited_fact_count = len(cited_fact_ids)
    claim_count = len(claim_items)
    claim_analysis_available = structured_output is not None
    evidence_utilization = (
        cited_fact_count / evidence_fact_count
        if evidence_fact_count
        else (1.0 if executed == 0 else 0.0)
    )
    claim_support_rate = (
        supported_claim_count / claim_count
        if claim_count
        else 1.0
    )

    status = _metrics_status(
        evidence_status=str(evidence.get("status") or ""),
        planned=planned,
        executed=executed,
        blocked=blocked,
        failed=failed,
        evidence_fact_count=evidence_fact_count,
        evidence_utilization=evidence_utilization,
        claim_support_rate=claim_support_rate,
        claim_analysis_available=claim_analysis_available,
    )

    return {
        "status": status,
        "plannedRequestCount": planned,
        "executedToolCallCount": executed,
        "blockedRequestCount": blocked,
        "failedToolCallCount": failed,
        "dedupedRequestCount": deduped,
        "budgetExhausted": exhausted,
        "evidenceFactCount": evidence_fact_count,
        "citedEvidenceFactCount": cited_fact_count,
        "evidenceUtilization": round(evidence_utilization, 4),
        "claimCount": claim_count,
        "supportedClaimCount": supported_claim_count,
        "claimSupportRate": round(claim_support_rate, 4),
        "claimAnalysisAvailable": claim_analysis_available,
        "validFactPrefixes": list(VALID_TOOL_FACT_PREFIXES),
    }


def _metrics_status(
    *,
    evidence_status: str,
    planned: int,
    executed: int,
    blocked: int,
    failed: int,
    evidence_fact_count: int,
    evidence_utilization: float,
    claim_support_rate: float,
    claim_analysis_available: bool,
) -> str:
    if evidence_status == "SKIPPED":
        return "SKIPPED"
    if not claim_analysis_available:
        if evidence_status:
            return "PENDING_CLAIM_ANALYSIS"
        return "NO_TOOL_REQUESTED" if planned == 0 and executed == 0 else "PENDING_CLAIM_ANALYSIS"
    if planned == 0 and executed == 0:
        return "NO_TOOL_REQUESTED"
    if executed == 0 and evidence_fact_count == 0:
        return "NO_TOOL_EVIDENCE"
    if blocked or failed:
        return "REVIEW_REQUIRED"
    if evidence_fact_count and evidence_utilization < 0.5:
        return "REVIEW_REQUIRED"
    if claim_support_rate < 0.9:
        return "REVIEW_REQUIRED"
    return "SUCCEEDED"


def _tool_fact_ids(
    *,
    tool_results: Sequence[Mapping[str, Any]],
    deterministic_facts: Sequence[Mapping[str, Any]],
) -> set[str]:
    ids: set[str] = set()
    for result in tool_results:
        fact_id = str(result.get("factId") or "").strip()
        if _is_valid_tool_fact_id(fact_id):
            ids.add(fact_id)
    for fact in deterministic_facts:
        fact_id = str(fact.get("id") or "").strip()
        if _is_valid_tool_fact_id(fact_id):
            ids.add(fact_id)
    return ids


def _claim_items(structured_output: Mapping[str, Any] | None) -> list[Mapping[str, Any]]:
    if structured_output is None:
        return []
    claims: list[Mapping[str, Any]] = []
    for field in (*_SEMANTIC_CLAIM_FIELDS, *_METADATA_CLAIM_FIELDS):
        claims.extend(_mapping_list(structured_output.get(field)))
    for group in _mapping_list(structured_output.get("insightGroups")):
        claims.extend(_mapping_list(group.get("insights")))
    graph = structured_output.get("dependencyGraph")
    if isinstance(graph, Mapping):
        claims.extend(_mapping_list(graph.get("nodes")))
        claims.extend(_mapping_list(graph.get("edges")))
        claims.extend(_mapping_list(graph.get("unresolved")))
    return [claim for claim in claims if _evidence_refs(claim)]


def _failed_tool_call_count(
    component_invocations: Sequence[Mapping[str, Any]],
    blocked_count: int,
) -> int:
    review_required_executions = sum(
        1
        for component in component_invocations
        if str(component.get("stage") or "") == "ai_tool_execution"
        and str(component.get("status") or "") == "REVIEW_REQUIRED"
    )
    return max(review_required_executions - blocked_count, 0)


def _mapping_list(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return []
    return [str(item) for item in value if str(item)]


def _evidence_refs(item: Mapping[str, Any]) -> list[str]:
    value = item.get("evidenceRefs") or item.get("evidence_refs") or []
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return []
    return [str(ref) for ref in value if str(ref).strip()]


def _is_valid_tool_fact_id(value: str) -> bool:
    return value.startswith(VALID_TOOL_FACT_PREFIXES)


def _first_int(*values: Any) -> int:
    for value in values:
        if value is not None:
            return _int(value)
    return 0


def _int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0
