from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from ai_agent_runtime.gateway import ModelGateway, model_profile_from_env
from ai_agent_runtime.models import (
    AgentRunPayload,
    AgentRunStatus,
    LlmEvidenceStatus,
    MetadataAnalysisOutput,
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
    storage_safe = sanitize_value_for_storage(repaired, procedure_definition="")
    final_output = MetadataAnalysisOutput.model_validate(storage_safe)
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
    for field in ("objectInsights", "reviewMarkers"):
        items = []
        for item in repaired.get(field, []) or []:
            if not isinstance(item, dict):
                continue
            repaired_item = dict(item)
            evidence_refs = [
                str(ref)
                for ref in repaired_item.get("evidenceRefs", [])
                if str(ref) in allowed
            ]
            if not evidence_refs:
                evidence_refs = [allowed[0]]
                marker_added = True
            repaired_item["evidenceRefs"] = evidence_refs
            if field == "reviewMarkers":
                repaired_item["status"] = LlmEvidenceStatus.REVIEW_REQUIRED.value
            items.append(repaired_item)
        repaired[field] = items
    if marker_added:
        markers = list(repaired.get("reviewMarkers", []) or [])
        markers.append(
            {
                "code": "METADATA_ANALYSIS_EVIDENCE_REPAIRED",
                "message": (
                    "Metadata analysis evidenceRefs were repaired to deterministic fact ids."
                ),
                "status": LlmEvidenceStatus.REVIEW_REQUIRED.value,
                "evidenceRefs": [allowed[0]],
            }
        )
        repaired["reviewMarkers"] = markers
    return repaired


def _summary(output: MetadataAnalysisOutput) -> str:
    return (
        f"{len(output.object_insights)} metadata insights, "
        f"{len(output.review_markers)} review markers"
    )
