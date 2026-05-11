from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from ai_agent_runtime.gateway import ModelGateway, model_profile_from_env
from ai_agent_runtime.models import (
    AgentRunPayload,
    AgentRunStatus,
    LlmSemanticAnalysisOutput,
    ModelInvocationRecord,
    stable_json_hash,
    text_hash,
)
from ai_agent_runtime.prompts import render_semantic_analysis_prompt

AGENT_TYPE = "LLM_SEMANTIC_ANALYST"
TRACE_EVIDENCE_REFS = frozenset(
    {
        "prompt.inputHash",
        "prompt.promptHash",
        "modelInvocation.outputHash",
        "metadata.snapshot",
        "static.analysis",
    }
)
OUTPUT_FIELDS = ("businessRules", "modernizationPoints", "riskFlags", "reviewMarkers")
KEY_FIELDS = {
    "businessRules": "category",
    "modernizationPoints": "code",
    "riskFlags": "code",
    "reviewMarkers": "code",
}


@dataclass(frozen=True)
class SemanticAnalysisTask:
    target_ref: str
    metadata: dict[str, Any]
    static_analysis: dict[str, Any] | None = None
    procedure_definition: str | None = None


def build_semantic_analysis_run(
    *,
    target_ref: str,
    metadata: dict[str, Any],
    static_analysis: dict[str, Any] | None,
    procedure_definition: str | None,
    model_gateway: ModelGateway,
    profile_id: str | None,
) -> AgentRunPayload:
    return build_semantic_analysis_runs(
        tasks=(
            SemanticAnalysisTask(
                target_ref=target_ref,
                metadata=metadata,
                static_analysis=static_analysis,
                procedure_definition=procedure_definition,
            ),
        ),
        model_gateway=model_gateway,
        profile_id=profile_id,
    )[0]


def build_semantic_analysis_runs(
    *,
    tasks: Sequence[SemanticAnalysisTask],
    model_gateway: ModelGateway,
    profile_id: str | None,
    concurrency: int | None = None,
) -> list[AgentRunPayload]:
    if not tasks:
        return []
    profile = model_profile_from_env(profile_id)
    max_workers = max(1, concurrency or _env_int("LLM_SP_CONCURRENCY", 2))
    if len(tasks) == 1 or max_workers == 1:
        return [
            _build_single_semantic_analysis_run(
                task=task,
                model_gateway=model_gateway,
                profile_id=profile_id,
            )
            for task in tasks
        ]
    with ThreadPoolExecutor(max_workers=min(max_workers, len(tasks))) as executor:
        return list(
            executor.map(
                lambda task: _build_single_semantic_analysis_run(
                    task=task,
                    model_gateway=model_gateway,
                    profile_id=profile.profile_id,
                ),
                tasks,
            )
        )


def _build_single_semantic_analysis_run(
    *,
    task: SemanticAnalysisTask,
    model_gateway: ModelGateway,
    profile_id: str | None,
) -> AgentRunPayload:
    profile = model_profile_from_env(profile_id)
    allowed_evidence_refs = _allowed_evidence_refs(
        metadata=task.metadata,
        static_analysis=task.static_analysis,
    )
    required_review_markers = _required_review_markers(
        static_analysis=task.static_analysis,
        allowed_evidence_refs=allowed_evidence_refs,
    )
    stages = _stages_for_task(
        static_analysis=task.static_analysis,
        required_review_markers=required_review_markers,
    )
    invocations: list[tuple[str, ModelInvocationRecord]] = []
    outputs: list[dict[str, Any]] = []

    for stage in stages:
        prompt = render_semantic_analysis_prompt(
            target_ref=task.target_ref,
            metadata=task.metadata,
            static_analysis=task.static_analysis,
            procedure_definition=task.procedure_definition,
            stage=stage,
            allowed_evidence_refs=allowed_evidence_refs,
            required_review_markers=required_review_markers,
        )
        invocation = model_gateway.invoke_semantic_analysis(prompt=prompt, profile=profile)
        invocations.append((stage, invocation))
        outputs.append(
            LlmSemanticAnalysisOutput.model_validate(
                invocation.structured_output,
            ).to_storage_dict()
        )

    combined_output = _merge_outputs(outputs)
    if "repair" not in stages and _needs_repair(
        combined_output,
        allowed_evidence_refs=allowed_evidence_refs,
        required_review_markers=required_review_markers,
    ):
        prompt = render_semantic_analysis_prompt(
            target_ref=task.target_ref,
            metadata=task.metadata,
            static_analysis=task.static_analysis,
            procedure_definition=task.procedure_definition,
            stage="repair",
            allowed_evidence_refs=allowed_evidence_refs,
            required_review_markers=required_review_markers,
            repair_context=_repair_context(combined_output),
        )
        invocation = model_gateway.invoke_semantic_analysis(prompt=prompt, profile=profile)
        invocations.append(("repair", invocation))
        outputs.append(
            LlmSemanticAnalysisOutput.model_validate(
                invocation.structured_output,
            ).to_storage_dict()
        )
        combined_output = _merge_outputs(outputs)

    repaired_output = _inject_required_review_markers(
        _repair_evidence_refs(combined_output, allowed_evidence_refs=allowed_evidence_refs),
        required_review_markers=required_review_markers,
    )
    output = LlmSemanticAnalysisOutput.model_validate(repaired_output)
    invocation = _aggregate_invocations(
        invocations=invocations,
        structured_output=output.to_storage_dict(),
        profile=profile,
    )
    return AgentRunPayload(
        agent_type=AGENT_TYPE,
        status=AgentRunStatus.SUCCEEDED,
        target_ref=task.target_ref,
        structured_output=output.to_storage_dict(),
        model_invocation=invocation,
        summary=_summary(output),
    )


def merge_llm_semantic_analysis(
    *,
    deterministic_context: dict[str, Any],
    llm_output: dict[str, Any] | None,
) -> dict[str, Any]:
    merged = dict(deterministic_context)
    if not llm_output:
        return merged
    output = LlmSemanticAnalysisOutput.model_validate(llm_output)
    merged["llmSemanticAnalysis"] = output.to_storage_dict()
    return merged


def _summary(output: LlmSemanticAnalysisOutput) -> str:
    return (
        f"{len(output.business_rules)} business rules, "
        f"{len(output.modernization_points)} modernization points, "
        f"{len(output.risk_flags)} risk flags, "
        f"{len(output.review_markers)} review markers"
    )


def _stages_for_task(
    *,
    static_analysis: Mapping[str, Any] | None,
    required_review_markers: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    complexity = _complexity(static_analysis, required_review_markers)
    if complexity == "simple":
        return ("semantic_claims",)
    return ("semantic_claims", "review_markers")


def _complexity(
    static_analysis: Mapping[str, Any] | None,
    required_review_markers: Sequence[Mapping[str, Any]],
) -> str:
    if required_review_markers or _truthy_path(
        static_analysis,
        ("patterns", "dynamic_sql"),
        ("patterns", "dynamicSql", "detected"),
        ("patterns", "dynamic_sql", "detected"),
        ("patterns", "cross_database_reference"),
        ("patterns", "unsupported_dependency_claims_possible"),
    ):
        return "complex"
    if _truthy_path(
        static_analysis,
        ("patterns", "transaction"),
        ("patterns", "transaction", "detected"),
        ("patterns", "try_catch", "detected"),
        ("patterns", "tryCatch", "detected"),
    ):
        return "medium"
    return "simple"


def _allowed_evidence_refs(
    *,
    metadata: Mapping[str, Any],
    static_analysis: Mapping[str, Any] | None,
) -> list[str]:
    deterministic_refs: list[str] = []
    deterministic_facts = metadata.get("deterministicFacts") or metadata.get("deterministic_facts")
    if isinstance(deterministic_facts, Sequence) and not isinstance(
        deterministic_facts,
        str | bytes,
    ):
        deterministic_refs.extend(
            str(fact.get("id"))
            for fact in deterministic_facts
            if isinstance(fact, Mapping) and fact.get("id")
        )
    fact_ids = _get_path(static_analysis, ("fact_ids",))
    if isinstance(fact_ids, Sequence) and not isinstance(fact_ids, str | bytes):
        deterministic_refs.extend(str(ref) for ref in fact_ids if str(ref).strip())
    if deterministic_refs:
        return _dedupe(
            ref for ref in deterministic_refs if ref and ref not in TRACE_EVIDENCE_REFS
        )

    refs: list[str] = []
    for ref in _metadata_evidence_refs(metadata):
        refs.append(ref)
    refs.extend(_static_pattern_refs(static_analysis))

    definition = metadata.get("procedureDefinition")
    if isinstance(definition, Mapping) and definition.get("definitionHash"):
        refs.append("metadata.procedureDefinitionHash")
    if static_analysis:
        refs.append("static.analysis")
    if metadata:
        refs.append("metadata.snapshot")
    return _dedupe(ref for ref in refs if ref and ref not in TRACE_EVIDENCE_REFS)


def _metadata_evidence_refs(metadata: Mapping[str, Any]) -> list[str]:
    values = metadata.get("evidenceRefs") or metadata.get("evidence_refs") or []
    refs = []
    if isinstance(values, Sequence) and not isinstance(values, str | bytes):
        for item in values:
            if not isinstance(item, Mapping):
                continue
            object_ref = str(item.get("objectRef") or item.get("object_ref") or "").strip()
            locator = str(item.get("locator") or "").strip()
            if object_ref or locator:
                refs.append(f"metadata:{object_ref}:{locator}")
    return refs


def _static_pattern_refs(static_analysis: Mapping[str, Any] | None) -> list[str]:
    patterns = _get_path(static_analysis, ("patterns",))
    if not isinstance(patterns, Mapping):
        return []
    refs = []
    for key, value in patterns.items():
        if isinstance(value, Mapping):
            detected = bool(value.get("detected"))
        else:
            detected = bool(value)
        if detected:
            refs.append(f"static.pattern.{_snake_case(str(key))}")
    return refs


def _required_review_markers(
    *,
    static_analysis: Mapping[str, Any] | None,
    allowed_evidence_refs: Sequence[str],
) -> list[dict[str, Any]]:
    dynamic_or_cross_db = _truthy_path(
        static_analysis,
        ("patterns", "dynamic_sql"),
        ("patterns", "dynamic_sql", "detected"),
        ("patterns", "dynamicSql", "detected"),
        ("patterns", "cross_database_reference"),
        ("patterns", "crossDatabaseReference", "detected"),
        ("patterns", "unsupported_dependency_claims_possible"),
    ) or any(
        "dynamic" in ref.lower() or "cross" in ref.lower()
        for ref in allowed_evidence_refs
    )
    if not dynamic_or_cross_db:
        return []
    dynamic_refs = _matching_refs(allowed_evidence_refs, ("dynamic", "cross"))
    function_refs = _matching_refs(allowed_evidence_refs, ("dynamic",))
    procedure_refs = _matching_refs(
        allowed_evidence_refs,
        ("sp_executesql", "procedure", "dynamic"),
    )
    return [
        {
            "code": "UNSUPPORTED_TABLE_CLAIM_REVIEW",
            "message": (
                "Any inferred concrete table dependency from dynamic or cross-database SQL "
                "must remain REVIEW_REQUIRED until deterministic metadata confirms it."
            ),
            "status": "REVIEW_REQUIRED",
            "evidenceRefs": dynamic_refs,
        },
        {
            "code": "UNSUPPORTED_FUNCTION_CLAIM_REVIEW",
            "message": (
                "Any inferred helper function dependency must remain REVIEW_REQUIRED until "
                "deterministic metadata confirms it."
            ),
            "status": "REVIEW_REQUIRED",
            "evidenceRefs": function_refs or dynamic_refs,
        },
        {
            "code": "UNSUPPORTED_PROCEDURE_CLAIM_REVIEW",
            "message": (
                "Only deterministic procedure-call facts may be treated as confirmed; "
                "additional procedure dependencies require review."
            ),
            "status": "REVIEW_REQUIRED",
            "evidenceRefs": procedure_refs or dynamic_refs,
        },
    ]


def _merge_outputs(outputs: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    merged: dict[str, Any] = {
        "businessRules": [],
        "modernizationPoints": [],
        "riskFlags": [],
        "reviewMarkers": [],
        "assumptions": [],
    }
    for output in outputs:
        normalized = LlmSemanticAnalysisOutput.model_validate(output).to_storage_dict()
        for field_name in OUTPUT_FIELDS:
            key_field = KEY_FIELDS[field_name]
            for item in normalized[field_name]:
                _merge_item(merged[field_name], item, key_field=key_field)
        merged["assumptions"] = _dedupe(
            [*merged["assumptions"], *[str(item) for item in normalized["assumptions"]]]
        )
    return merged


def _merge_item(items: list[dict[str, Any]], item: Mapping[str, Any], *, key_field: str) -> None:
    key = str(item.get(key_field) or "")
    if not key:
        items.append(dict(item))
        return
    for existing in items:
        if str(existing.get(key_field) or "") != key:
            continue
        existing["evidenceRefs"] = _dedupe(
            [*_evidence_refs(existing), *_evidence_refs(item)]
        )
        if item.get("status") == "REVIEW_REQUIRED":
            existing["status"] = "REVIEW_REQUIRED"
        for text_field in ("summary", "message"):
            if not str(existing.get(text_field) or "").strip() and item.get(text_field):
                existing[text_field] = item[text_field]
        return
    items.append(dict(item))


def _needs_repair(
    output: Mapping[str, Any],
    *,
    allowed_evidence_refs: Sequence[str],
    required_review_markers: Sequence[Mapping[str, Any]],
) -> bool:
    allowed = set(allowed_evidence_refs)
    for field_name in OUTPUT_FIELDS:
        for item in output[field_name]:
            refs = set(_evidence_refs(item))
            if not refs or refs - allowed or refs & TRACE_EVIDENCE_REFS:
                return True
    required_codes = {str(marker["code"]) for marker in required_review_markers}
    actual_codes = {
        str(marker.get("code"))
        for marker in output["reviewMarkers"]
        if str(marker.get("status")) == "REVIEW_REQUIRED"
    }
    return not required_codes <= actual_codes


def _repair_context(output: Mapping[str, Any]) -> dict[str, Any]:
    normalized = LlmSemanticAnalysisOutput.model_validate(output).to_storage_dict()
    return {
        "claimKeys": {
            field_name: [
                str(item.get(KEY_FIELDS[field_name]) or "")
                for item in normalized[field_name]
            ]
            for field_name in OUTPUT_FIELDS
        },
        "reviewMarkerCodes": [
            str(item.get("code") or "")
            for item in normalized["reviewMarkers"]
        ],
    }


def _repair_evidence_refs(
    output: Mapping[str, Any],
    *,
    allowed_evidence_refs: Sequence[str],
) -> dict[str, Any]:
    allowed = set(allowed_evidence_refs)
    repaired = LlmSemanticAnalysisOutput.model_validate(output).to_storage_dict()
    for field_name in OUTPUT_FIELDS:
        for item in repaired[field_name]:
            refs = [
                ref for ref in _evidence_refs(item)
                if ref in allowed and ref not in TRACE_EVIDENCE_REFS
            ]
            if not refs:
                refs = _fallback_evidence_refs(item, allowed_evidence_refs)
            item["evidenceRefs"] = _dedupe(refs)
            if str(item.get("code") or "").startswith("UNSUPPORTED_"):
                item["status"] = "REVIEW_REQUIRED"
    return repaired


def _inject_required_review_markers(
    output: Mapping[str, Any],
    *,
    required_review_markers: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    repaired = LlmSemanticAnalysisOutput.model_validate(output).to_storage_dict()
    existing_codes = {
        str(marker.get("code"))
        for marker in repaired["reviewMarkers"]
        if marker.get("code")
    }
    for marker in required_review_markers:
        marker_code = str(marker["code"])
        marker_payload = {
            "code": marker_code,
            "message": str(marker["message"]),
            "status": "REVIEW_REQUIRED",
            "evidenceRefs": list(marker.get("evidenceRefs") or []),
        }
        if marker_code in existing_codes:
            for existing in repaired["reviewMarkers"]:
                if existing.get("code") == marker_code:
                    existing["status"] = "REVIEW_REQUIRED"
                    existing["evidenceRefs"] = _dedupe(
                        [*_evidence_refs(existing), *_evidence_refs(marker_payload)]
                    )
                    if not existing["evidenceRefs"]:
                        existing["evidenceRefs"] = _fallback_evidence_refs(
                            existing,
                            marker_payload["evidenceRefs"],
                        )
                    break
        else:
            if not marker_payload["evidenceRefs"]:
                marker_payload["evidenceRefs"] = _fallback_evidence_refs(
                    marker_payload,
                    marker_payload["evidenceRefs"],
                )
            repaired["reviewMarkers"].append(marker_payload)
    return repaired


def _aggregate_invocations(
    *,
    invocations: Sequence[tuple[str, ModelInvocationRecord]],
    structured_output: dict[str, Any],
    profile: Any,
) -> ModelInvocationRecord:
    if not invocations:
        raise ValueError("At least one model invocation is required.")
    _first_stage, first = invocations[0]
    component_invocations = tuple(
        {
            "stage": stage,
            "provider": invocation.provider,
            "model": invocation.model,
            "modelProfileId": invocation.model_profile_id,
            "reasoningEffort": invocation.reasoning_effort,
            "promptVersion": invocation.prompt_version,
            "outputSchemaVersion": invocation.output_schema_version,
            "inputHash": invocation.input_hash,
            "promptHash": invocation.prompt_hash,
            "outputHash": invocation.output_hash,
            "status": invocation.status.value,
            "tokenUsage": dict(invocation.token_usage),
            "latencyMs": invocation.latency_ms,
        }
        for stage, invocation in invocations
    )
    token_usage = {
        "inputTokens": sum(
            invocation.token_usage.get("inputTokens", 0)
            for _stage, invocation in invocations
        ),
        "outputTokens": sum(
            invocation.token_usage.get("outputTokens", 0)
            for _stage, invocation in invocations
        ),
        "totalTokens": sum(
            invocation.token_usage.get("totalTokens", 0)
            for _stage, invocation in invocations
        ),
    }
    latency_values = [
        invocation.latency_ms
        for _stage, invocation in invocations
        if invocation.latency_ms is not None
    ]
    aggregate_input = {
        "inputHashes": [invocation.input_hash for _stage, invocation in invocations],
        "promptHashes": [invocation.prompt_hash for _stage, invocation in invocations],
        "outputHashes": [invocation.output_hash for _stage, invocation in invocations],
    }
    return ModelInvocationRecord(
        provider=first.provider,
        model=profile.model,
        model_profile_id=profile.profile_id,
        model_registry_ref=profile.registry_ref,
        reasoning_effort=profile.reasoning_effort,
        prompt_version=first.prompt_version,
        output_schema_version=first.output_schema_version,
        input_hash=stable_json_hash(aggregate_input),
        prompt_hash=text_hash(
            "\n".join(invocation.prompt_hash for _stage, invocation in invocations)
        ),
        output_hash=stable_json_hash(structured_output),
        status=AgentRunStatus.SUCCEEDED,
        structured_output=structured_output,
        token_usage=token_usage,
        latency_ms=sum(latency_values) if latency_values else None,
        provider_request_id=None,
        component_invocations=component_invocations,
    )


def _fallback_evidence_refs(
    item: Mapping[str, Any],
    allowed_evidence_refs: Sequence[str],
) -> list[str]:
    allowed = [ref for ref in allowed_evidence_refs if ref not in TRACE_EVIDENCE_REFS]
    if not allowed:
        return []
    haystack = " ".join(
        str(value)
        for key, value in item.items()
        if key in {"category", "code", "summary", "message", "severity", "status"}
    ).lower()
    keyword_groups = (
        (("dynamic", "sql", "result", "shape"), ("dynamic", "result")),
        (("cross", "tenant", "database"), ("cross", "tenant", "database")),
        (("audit", "reporting", "extract"), ("audit", "reporting", "extract")),
        (("customer", "lookup", "inactive"), ("customer", "parameter", "result")),
        (("tier",), ("tier",)),
        (("transaction", "rollback", "commit"), ("transaction",)),
        (("approve", "hold", "branch", "decision"), ("branch", "approve", "hold")),
        (("sp_executesql", "procedure"), ("sp_executesql", "procedure")),
        (("function",), ("function", "dynamic")),
        (("table", "dependency"), ("table", "dynamic", "cross")),
    )
    matched_refs: list[str] = []
    for haystack_keywords, ref_keywords in keyword_groups:
        if any(keyword in haystack for keyword in haystack_keywords):
            matched_refs.extend(_matching_refs(allowed, ref_keywords))
    if matched_refs:
        return _dedupe(matched_refs)[:3]
    return allowed[: min(2, len(allowed))]


def _matching_refs(refs: Sequence[str], keywords: Sequence[str]) -> list[str]:
    matched = [
        ref
        for ref in refs
        if any(keyword.lower() in ref.lower() for keyword in keywords)
        and ref not in TRACE_EVIDENCE_REFS
    ]
    fallback = [ref for ref in refs if ref not in TRACE_EVIDENCE_REFS]
    return _dedupe(matched or fallback[:1])


def _evidence_refs(item: Mapping[str, Any]) -> list[str]:
    value = item.get("evidenceRefs") or item.get("evidence_refs") or []
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return []
    return [str(ref) for ref in value if str(ref).strip()]


def _truthy_path(value: Mapping[str, Any] | None, *paths: Sequence[str]) -> bool:
    for path in paths:
        found = _get_path(value, path)
        if isinstance(found, Mapping):
            if bool(found.get("detected")):
                return True
            continue
        if bool(found):
            return True
    return False


def _get_path(value: Mapping[str, Any] | None, path: Sequence[str]) -> Any:
    current: Any = value
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _snake_case(value: str) -> str:
    result = []
    for index, char in enumerate(value):
        if char.isupper() and index > 0:
            result.append("_")
        result.append(char.lower())
    return "".join(result).replace("__", "_")


def _dedupe(items: Sequence[str] | Any) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for item in items:
        value = str(item)
        if not value or value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name, "").strip()
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default
