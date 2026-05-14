from __future__ import annotations

from dataclasses import replace as dataclass_replace
from collections.abc import Sequence
from typing import Any

from ai_agent_runtime.gateway import ModelGateway, model_profile_from_env
from ai_agent_runtime.localization import (
    append_korean_language_review_marker,
    contains_korean,
    human_text_needs_korean,
    korean_language_review_paths,
)
from ai_agent_runtime.models import (
    AgentRunPayload,
    AgentRunStatus,
    LlmEvidenceStatus,
    MetadataAnalysisOutput,
    stable_json_hash,
)
from ai_agent_runtime.prompts import render_metadata_analysis_prompt
from ai_agent_runtime.storage_safety import sanitize_value_for_storage

AGENT_TYPE = "LLM_METADATA_ANALYST"


def build_metadata_analysis_run(
    *,
    target_ref: str,
    metadata: dict[str, Any],
    allowed_evidence_refs: Sequence[str],
    model_gateway: ModelGateway,
    profile_id: str | None,
) -> AgentRunPayload:
    profile = model_profile_from_env(profile_id)
    allowed_refs = tuple(
        dict.fromkeys(str(ref) for ref in allowed_evidence_refs if str(ref).strip())
    )
    prompt = render_metadata_analysis_prompt(
        target_ref=target_ref,
        metadata=metadata,
        allowed_evidence_refs=allowed_refs,
    )
    invocation = model_gateway.analyze_metadata(prompt=prompt, profile=profile)
    output = MetadataAnalysisOutput.model_validate(invocation.structured_output)
    repaired = _repair_metadata_analysis_output(output.to_storage_dict(), allowed_refs)
    language_paths = korean_language_review_paths(repaired)
    component_invocations = ()
    if language_paths:
        repair_prompt = render_metadata_analysis_prompt(
            target_ref=target_ref,
            metadata=metadata,
            allowed_evidence_refs=allowed_refs,
            stage="language_repair",
            repair_context={
                "locale": "ko-KR",
                "languageReviewPaths": language_paths,
                "summary": repaired.get("summary"),
            },
        )
        language_invocation = model_gateway.analyze_metadata(
            prompt=repair_prompt,
            profile=profile,
        )
        component_invocations = (
            {
                "stage": "metadata_analysis",
                "provider": invocation.provider,
                "model": invocation.model,
                "modelProfileId": invocation.model_profile_id,
                "promptVersion": invocation.prompt_version,
                "outputSchemaVersion": invocation.output_schema_version,
                "inputHash": invocation.input_hash,
                "promptHash": invocation.prompt_hash,
                "outputHash": invocation.output_hash,
                "status": invocation.status.value,
            },
            {
                "stage": "language_repair",
                "provider": language_invocation.provider,
                "model": language_invocation.model,
                "modelProfileId": language_invocation.model_profile_id,
                "promptVersion": language_invocation.prompt_version,
                "outputSchemaVersion": language_invocation.output_schema_version,
                "inputHash": language_invocation.input_hash,
                "promptHash": language_invocation.prompt_hash,
                "outputHash": language_invocation.output_hash,
                "status": language_invocation.status.value,
            },
        )
        repaired = _repair_metadata_analysis_output(
            _apply_language_repair_output(
                repaired,
                MetadataAnalysisOutput.model_validate(
                    language_invocation.structured_output,
                ).to_storage_dict(),
            ),
            allowed_refs,
        )
        if korean_language_review_paths(repaired):
            repaired = append_korean_language_review_marker(
                repaired,
                evidence_refs=[allowed_refs[0]] if allowed_refs else [],
            )
    storage_safe = sanitize_value_for_storage(repaired, procedure_definition="")
    final_output = MetadataAnalysisOutput.model_validate(storage_safe)
    invocation = dataclass_replace(
        invocation,
        structured_output=final_output.to_storage_dict(),
        output_hash=stable_json_hash(final_output.to_storage_dict()),
        component_invocations=component_invocations,
    )
    return AgentRunPayload(
        agent_type=AGENT_TYPE,
        status=AgentRunStatus.SUCCEEDED,
        target_ref=target_ref,
        structured_output=final_output.to_storage_dict(),
        model_invocation=invocation,
        summary=_summary(final_output),
    )


def _repair_metadata_analysis_output(
    output: dict[str, Any],
    allowed_refs: Sequence[str],
) -> dict[str, Any]:
    allowed = tuple(dict.fromkeys(str(ref) for ref in allowed_refs if str(ref).strip()))
    if not allowed:
        return output
    repaired = dict(output)
    marker_added = False
    for field in ("objectInsights", "dtoReadiness", "reviewMarkers"):
        items = []
        for item in repaired.get(field, []) or []:
            if not isinstance(item, dict):
                continue
            repaired_item, repaired_refs = _repair_item_refs(item, allowed)
            marker_added = marker_added or repaired_refs
            if field == "reviewMarkers":
                repaired_item["status"] = LlmEvidenceStatus.REVIEW_REQUIRED.value
            items.append(repaired_item)
        repaired[field] = items
    groups = []
    for group in repaired.get("insightGroups", []) or []:
        if not isinstance(group, dict):
            continue
        repaired_group = dict(group)
        insights = []
        for insight in repaired_group.get("insights", []) or []:
            if not isinstance(insight, dict):
                continue
            repaired_insight, repaired_refs = _repair_item_refs(insight, allowed)
            marker_added = marker_added or repaired_refs
            insights.append(repaired_insight)
        repaired_group["insights"] = insights
        groups.append(repaired_group)
    repaired["insightGroups"] = groups
    if marker_added:
        markers = list(repaired.get("reviewMarkers", []) or [])
        markers.append(
            {
                "code": "METADATA_ANALYSIS_EVIDENCE_REPAIRED",
                "message": (
                    "Metadata analysis evidenceRefs를 결정론적 fact id로 보정했습니다."
                ),
                "status": LlmEvidenceStatus.REVIEW_REQUIRED.value,
                "evidenceRefs": [allowed[0]],
            }
        )
        repaired["reviewMarkers"] = markers
    return repaired


def _apply_language_repair_output(
    output: dict[str, Any],
    repair_output: dict[str, Any],
) -> dict[str, Any]:
    repaired = MetadataAnalysisOutput.model_validate(output).to_storage_dict()
    candidate = MetadataAnalysisOutput.model_validate(repair_output).to_storage_dict()
    if human_text_needs_korean(repaired.get("summary")) and contains_korean(
        candidate.get("summary")
    ):
        repaired["summary"] = candidate["summary"]
    _apply_item_language_repair(repaired.get("objectInsights", []), candidate.get("objectInsights", []), "code")
    _apply_item_language_repair(repaired.get("dtoReadiness", []), candidate.get("dtoReadiness", []), "objectRef")
    _apply_item_language_repair(repaired.get("reviewMarkers", []), candidate.get("reviewMarkers", []), "code")
    candidate_groups = {
        str(group.get("category") or ""): group
        for group in candidate.get("insightGroups", [])
        if isinstance(group, dict)
    }
    for group in repaired.get("insightGroups", []):
        if not isinstance(group, dict):
            continue
        candidate_group = candidate_groups.get(str(group.get("category") or ""))
        if not candidate_group:
            continue
        _apply_item_language_repair(
            group.get("insights", []),
            candidate_group.get("insights", []),
            "code",
        )
    if any(contains_korean(item) for item in candidate.get("assumptions", [])):
        repaired["assumptions"] = list(candidate.get("assumptions", []))
    return repaired


def _apply_item_language_repair(
    items: Any,
    candidate_items: Any,
    key_field: str,
) -> None:
    if not isinstance(items, list) or not isinstance(candidate_items, list):
        return
    candidate_by_key = {
        str(item.get(key_field) or ""): item
        for item in candidate_items
        if isinstance(item, dict)
    }
    for item in items:
        if not isinstance(item, dict):
            continue
        candidate = candidate_by_key.get(str(item.get(key_field) or ""))
        if not candidate:
            continue
        for text_field in ("summary", "message"):
            if human_text_needs_korean(item.get(text_field)) and contains_korean(
                candidate.get(text_field)
            ):
                item[text_field] = candidate[text_field]
        if "reviewReasons" in item and isinstance(item["reviewReasons"], list):
            candidate_reasons = candidate.get("reviewReasons")
            if isinstance(candidate_reasons, list) and any(
                contains_korean(reason) for reason in candidate_reasons
            ):
                item["reviewReasons"] = candidate_reasons


def _repair_item_refs(
    item: dict[str, Any],
    allowed: Sequence[str],
) -> tuple[dict[str, Any], bool]:
    repaired_item = dict(item)
    evidence_refs = [
        str(ref)
        for ref in repaired_item.get("evidenceRefs", [])
        if str(ref) in allowed
    ]
    repaired = False
    if not evidence_refs:
        evidence_refs = [allowed[0]]
        repaired = True
    repaired_item["evidenceRefs"] = evidence_refs
    return repaired_item, repaired


def _summary(output: MetadataAnalysisOutput) -> str:
    return (
        f"메타데이터 인사이트 {len(output.object_insights)}개, "
        f"인사이트 그룹 {len(output.insight_groups)}개, "
        f"검토 마커 {len(output.review_markers)}개"
    )
