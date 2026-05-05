from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from ai_agent_analysis.models import (
    CanonicalConversionBlocker,
    EvidenceStatus,
    StoredProcedureAnalysisResult,
)


def canonical_conversion_blockers() -> list[CanonicalConversionBlocker]:
    return [
        CanonicalConversionBlocker(
            code="DOMAIN_CONTRACT_MISSING",
            message=(
                "P11 requests CanonicalAnalysisModel expansion, but this worker boundary "
                "marks packages/domain as read-only."
            ),
            target_path="packages/domain/src/ai_agent_domain/models.py",
        )
    ]


def to_canonical_candidate(result: StoredProcedureAnalysisResult) -> dict:
    return {
        "target_contract": "CanonicalAnalysisModel",
        "status": EvidenceStatus.REVIEW_REQUIRED.value,
        "evidenceRefs": _openapi_static_analysis_refs(result),
        "blockers": [
            blocker.model_dump(mode="json") for blocker in canonical_conversion_blockers()
        ],
        "analysis_local": result.model_dump(mode="json"),
    }


def _openapi_static_analysis_refs(result: StoredProcedureAnalysisResult) -> list[dict[str, str]]:
    object_ref = result.procedure.identifier.full_name or result.source_name
    refs: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for evidence in _iter_evidence_dicts(result.model_dump(mode="json")):
        source = str(evidence["source"])
        line = evidence.get("line")
        locator = f"{source}:{line}" if line is not None else f"{source}#{evidence['snippet']}"
        ref = {
            "type": "STATIC_ANALYSIS",
            "objectRef": object_ref,
            "locator": locator,
        }
        key = (ref["type"], ref["objectRef"], ref["locator"])
        if key in seen:
            continue
        seen.add(key)
        refs.append(ref)
    return refs


def _iter_evidence_dicts(payload: Any) -> Iterator[dict[str, Any]]:
    if isinstance(payload, dict):
        if {"source", "snippet", "status"}.issubset(payload):
            yield payload
            return
        for value in payload.values():
            yield from _iter_evidence_dicts(value)
    elif isinstance(payload, list | tuple):
        for item in payload:
            yield from _iter_evidence_dicts(item)
