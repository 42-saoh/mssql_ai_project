from __future__ import annotations

from collections.abc import Iterator
from typing import Any

from ai_agent_domain import CanonicalAnalysisModel

from ai_agent_analysis.models import (
    CanonicalConversionBlocker,
    EvidenceStatus,
    StoredProcedureAnalysisResult,
)


def canonical_conversion_blockers(
    result: StoredProcedureAnalysisResult | None = None,
    *,
    snapshot_id: str | None = None,
    registry_version_refs: list[Any] | None = None,
    evidence_refs_present: bool | None = None,
) -> list[CanonicalConversionBlocker]:
    if result is not None:
        snapshot_id = result.snapshot_id
        registry_version_refs = result.registry_version_refs
        evidence_refs_present = bool(_canonical_evidence_refs(result))

    blockers: list[CanonicalConversionBlocker] = []
    if not snapshot_id:
        blockers.append(
            CanonicalConversionBlocker(
                code="SNAPSHOT_ID_BINDING_MISSING",
                message="CanonicalAnalysisModel에는 명시적인 metadata snapshot id가 필요합니다.",
                target_path="packages/analysis/src/ai_agent_analysis/models.py",
            )
        )
    if not registry_version_refs:
        blockers.append(
            CanonicalConversionBlocker(
                code="REGISTRY_VERSION_REFS_MISSING",
                message="CanonicalAnalysisModel에는 연결된 registry version ref가 필요합니다.",
                target_path="packages/analysis/src/ai_agent_analysis/models.py",
            )
        )
    if evidence_refs_present is False:
        blockers.append(
            CanonicalConversionBlocker(
                code="CANONICAL_EVIDENCE_REFS_MISSING",
                message="CanonicalAnalysisModel의 observed field에는 evidence ref가 필요합니다.",
                target_path="packages/analysis/src/ai_agent_analysis/canonical.py",
            )
        )
    return blockers


def to_canonical_analysis_model(result: StoredProcedureAnalysisResult) -> CanonicalAnalysisModel:
    blockers = canonical_conversion_blockers(result)
    if blockers:
        codes = ", ".join(blocker.code for blocker in blockers)
        raise ValueError(f"Cannot build CanonicalAnalysisModel: {codes}")
    return CanonicalAnalysisModel.model_validate(_canonical_model_payload(result))


def to_canonical_candidate(result: StoredProcedureAnalysisResult) -> dict:
    blockers = canonical_conversion_blockers(result)
    payload = {
        "target_contract": "CanonicalAnalysisModel",
        "status": "CONTRACT_CLOSED" if not blockers else EvidenceStatus.REVIEW_REQUIRED.value,
        "analysis_status": result.evidence_assessment.status.value,
        "evidenceRefs": _openapi_static_analysis_refs(result),
        "blockers": [blocker.model_dump(mode="json") for blocker in blockers],
        "analysis_local": result.model_dump(mode="json"),
    }
    if not blockers:
        payload["canonical_model"] = to_canonical_analysis_model(result).model_dump(mode="json")
    return payload


def _canonical_model_payload(result: StoredProcedureAnalysisResult) -> dict[str, Any]:
    return {
        "analysis_version": result.analysis_version,
        "contract_target": result.contract_target,
        "snapshot_id": result.snapshot_id,
        "registry_version_refs": [
            registry_ref.model_dump(mode="json")
            for registry_ref in result.registry_version_refs
        ],
        "procedure": result.procedure.model_dump(mode="json"),
        "dependencies": result.dependencies.model_dump(mode="json"),
        "patterns": result.patterns.model_dump(mode="json"),
        "result_sets": [result_set.model_dump(mode="json") for result_set in result.result_sets],
        "call_graph": [edge.model_dump(mode="json") for edge in result.call_graph],
        "business_rules": [rule.model_dump(mode="json") for rule in result.business_rules],
        "modernization_points": [
            point.model_dump(mode="json") for point in result.modernization_points
        ],
        "evidence_refs": _canonical_evidence_refs(result),
        "review_markers": [marker.model_dump(mode="json") for marker in result.review_markers],
        "todos": [todo.model_dump(mode="json") for todo in result.todos],
        "evidence_assessment": result.evidence_assessment.model_dump(mode="json"),
        "overall_confidence": result.overall_confidence.model_dump(mode="json"),
    }


def _canonical_evidence_refs(result: StoredProcedureAnalysisResult) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[tuple[str, int | None, str, str]] = set()
    for evidence in _iter_evidence_dicts(result.model_dump(mode="json")):
        ref = {
            "source": str(evidence["source"]),
            "line": evidence.get("line"),
            "snippet": str(evidence["snippet"]),
            "status": str(evidence["status"]),
        }
        key = (ref["source"], ref["line"], ref["snippet"], ref["status"])
        if key in seen:
            continue
        seen.add(key)
        refs.append(ref)
    return refs


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
