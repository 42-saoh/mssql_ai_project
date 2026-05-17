from __future__ import annotations

import json
import os
import re
from collections.abc import Mapping, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from typing import Any

from ai_agent_analysis.source_map import (
    context_pack_summary,
    shrink_context_pack,
    without_source_text_context_pack,
)

from ai_agent_runtime.gateway import (
    ModelGateway,
    ModelGatewayError,
    model_profile_from_env,
)
from ai_agent_runtime.localization import (
    append_korean_language_review_marker,
    contains_korean,
    human_text_needs_korean,
    korean_language_review_paths,
)
from ai_agent_runtime.models import (
    AgentRunPayload,
    AgentRunStatus,
    LlmSemanticAnalysisOutput,
    ModelInvocationRecord,
    stable_json_hash,
    text_hash,
)
from ai_agent_runtime.prompts import render_semantic_analysis_prompt
from ai_agent_runtime.storage_safety import (
    sanitize_value_for_storage,
    storage_safety_findings,
)

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
OUTPUT_FIELDS = (
    "businessRules",
    "modernizationPoints",
    "riskFlags",
    "reviewMarkers",
    "conversionGuidance",
    "migrationGuideInsights",
)
KEY_FIELDS = {
    "businessRules": "category",
    "modernizationPoints": "code",
    "riskFlags": "code",
    "reviewMarkers": "code",
    "conversionGuidance": "code",
    "migrationGuideInsights": "section",
}
CONTEXT_BUDGET_MARKER_CODE = "LLM_CONTEXT_BUDGET_REVIEW_REQUIRED"
PROMPT_COMPACTION_MARKER_CODE = "LLM_PROMPT_COMPACTED_FOR_CONTEXT"
_COMPACTION_NONE = "none"
_COMPACTION_COMPACT = "compact"
_COMPACTION_MINIMUM = "minimum"


@dataclass(frozen=True)
class _PromptAttempt:
    prompt: Any
    metadata: dict[str, Any]
    static_analysis: dict[str, Any] | None
    source_context: dict[str, Any] | None
    allowed_evidence_refs: tuple[str, ...]
    compaction_level: str = _COMPACTION_NONE
    compaction_summary: dict[str, Any] | None = None

    @property
    def estimated_tokens(self) -> int:
        return _estimated_prompt_tokens(self.prompt)


@dataclass(frozen=True)
class SemanticAnalysisTask:
    target_ref: str
    metadata: dict[str, Any]
    static_analysis: dict[str, Any] | None = None
    procedure_definition: str | None = None
    source_context_packs: dict[str, dict[str, Any]] | None = None


def build_semantic_analysis_run(
    *,
    target_ref: str,
    metadata: dict[str, Any],
    static_analysis: dict[str, Any] | None,
    procedure_definition: str | None,
    source_context_packs: dict[str, dict[str, Any]] | None = None,
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
                source_context_packs=source_context_packs,
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
    source_context_summaries: list[dict[str, Any]] = []
    context_budget_markers: list[dict[str, Any]] = []

    for stage in stages:
        invocation, source_summary, budget_markers = _invoke_stage_with_context_fallback(
            model_gateway=model_gateway,
            profile=profile,
            task=task,
            stage=stage,
            allowed_evidence_refs=allowed_evidence_refs,
            required_review_markers=required_review_markers,
        )
        invocations.append((stage, invocation))
        source_context_summaries.append(source_summary)
        context_budget_markers.extend(budget_markers)
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
        invocation, source_summary, budget_markers = _invoke_stage_with_context_fallback(
            model_gateway=model_gateway,
            profile=profile,
            task=task,
            stage="repair",
            allowed_evidence_refs=allowed_evidence_refs,
            required_review_markers=required_review_markers,
            repair_context=_repair_context(combined_output),
        )
        invocations.append(("repair", invocation))
        source_context_summaries.append(source_summary)
        context_budget_markers.extend(budget_markers)
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
    if _uses_pgpt(invocations):
        repaired_output = _apply_deterministic_safety_net(
            repaired_output,
            metadata=task.metadata,
            static_analysis=task.static_analysis,
            allowed_evidence_refs=allowed_evidence_refs,
        )
    language_paths = korean_language_review_paths(repaired_output)
    if language_paths:
        invocation, source_summary, budget_markers = _invoke_stage_with_context_fallback(
            model_gateway=model_gateway,
            profile=profile,
            task=task,
            stage="language_repair",
            allowed_evidence_refs=allowed_evidence_refs,
            required_review_markers=required_review_markers,
            repair_context={
                "locale": "ko-KR",
                "languageReviewPaths": language_paths,
                "structuredOutput": _repair_context(repaired_output),
            },
        )
        invocations.append(("language_repair", invocation))
        source_context_summaries.append(source_summary)
        context_budget_markers.extend(budget_markers)
        language_repair_output = LlmSemanticAnalysisOutput.model_validate(
            invocation.structured_output,
        ).to_storage_dict()
        repaired_output = _repair_evidence_refs(
            _apply_language_repair_output(repaired_output, language_repair_output),
            allowed_evidence_refs=allowed_evidence_refs,
        )
        if korean_language_review_paths(repaired_output):
            repaired_output = append_korean_language_review_marker(
                repaired_output,
                evidence_refs=_fallback_evidence_refs(
                    {"code": "LLM_OUTPUT_LANGUAGE_REVIEW_REQUIRED"},
                    allowed_evidence_refs,
                ),
            )
    storage_safe_output = _sanitize_output_for_storage(
        _append_context_budget_markers(repaired_output, context_budget_markers),
        procedure_definition=task.procedure_definition or "",
        allowed_evidence_refs=allowed_evidence_refs,
    )
    output = LlmSemanticAnalysisOutput.model_validate(storage_safe_output)
    invocation = _aggregate_invocations(
        invocations=invocations,
        structured_output=output.to_storage_dict(),
        profile=profile,
        source_context_summaries=source_context_summaries,
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


def _invoke_stage_with_context_fallback(
    *,
    model_gateway: ModelGateway,
    profile: Any,
    task: SemanticAnalysisTask,
    stage: str,
    allowed_evidence_refs: Sequence[str],
    required_review_markers: Sequence[Mapping[str, Any]],
    repair_context: dict[str, Any] | None = None,
) -> tuple[ModelInvocationRecord, dict[str, Any], list[dict[str, Any]]]:
    source_context = _source_context_for_stage(task.source_context_packs, stage)
    attempt = _build_prompt_attempt(
        task=task,
        stage=stage,
        source_context=source_context,
        allowed_evidence_refs=allowed_evidence_refs,
        required_review_markers=required_review_markers,
        repair_context=repair_context,
    )
    if attempt.estimated_tokens > _semantic_input_token_budget():
        shrunk_context = shrink_context_pack(source_context, status="PRE_PROVIDER_SHRINK")
        attempt = _build_prompt_attempt(
            task=task,
            stage=stage,
            source_context=shrunk_context,
            allowed_evidence_refs=allowed_evidence_refs,
            required_review_markers=required_review_markers,
            repair_context=repair_context,
        )
    if attempt.estimated_tokens > _semantic_input_token_budget():
        attempt = _build_prompt_attempt(
            task=task,
            stage=stage,
            source_context=source_context,
            allowed_evidence_refs=allowed_evidence_refs,
            required_review_markers=required_review_markers,
            repair_context=repair_context,
            compaction_level=_COMPACTION_COMPACT,
            source_context_status="COMPACT_NO_SOURCE_TEXT",
        )
    if attempt.estimated_tokens > _semantic_input_token_budget():
        attempt = _build_prompt_attempt(
            task=task,
            stage=stage,
            source_context=source_context,
            allowed_evidence_refs=allowed_evidence_refs,
            required_review_markers=required_review_markers,
            repair_context=repair_context,
            compaction_level=_COMPACTION_MINIMUM,
            source_context_status="MINIMUM_EVIDENCE_DIGEST",
        )
    try:
        invocation = model_gateway.invoke_semantic_analysis(
            prompt=attempt.prompt,
            profile=profile,
        )
        return (
            invocation,
            _attempt_source_summary(attempt),
            _attempt_budget_markers(attempt),
        )
    except ModelGatewayError as exc:
        if not _is_context_length_error(exc):
            raise

    shrunk_context = shrink_context_pack(source_context, status="SHRUNK_RETRY")
    attempt = _build_prompt_attempt(
        task=task,
        stage=stage,
        source_context=shrunk_context,
        allowed_evidence_refs=allowed_evidence_refs,
        required_review_markers=required_review_markers,
        repair_context=repair_context,
    )
    try:
        invocation = model_gateway.invoke_semantic_analysis(
            prompt=attempt.prompt,
            profile=profile,
        )
        markers = _attempt_budget_markers(attempt) or _context_length_review_markers(
            attempt.allowed_evidence_refs
        )
        return invocation, _attempt_source_summary(attempt), markers
    except ModelGatewayError as exc:
        if not _is_context_length_error(exc):
            raise

    fallback_context = without_source_text_context_pack(
        source_context,
        status="FALLBACK_NO_SOURCE",
    )
    attempt = _build_prompt_attempt(
        task=task,
        stage=stage,
        source_context=fallback_context,
        allowed_evidence_refs=allowed_evidence_refs,
        required_review_markers=required_review_markers,
        repair_context=repair_context,
    )
    try:
        invocation = model_gateway.invoke_semantic_analysis(
            prompt=attempt.prompt,
            profile=profile,
        )
        markers = _attempt_budget_markers(attempt) or _context_length_review_markers(
            attempt.allowed_evidence_refs
        )
        return invocation, _attempt_source_summary(attempt), markers
    except ModelGatewayError as exc:
        if not _is_context_length_error(exc):
            raise

    for level, status in (
        (_COMPACTION_COMPACT, "COMPACT_NO_SOURCE_TEXT"),
        (_COMPACTION_MINIMUM, "MINIMUM_EVIDENCE_DIGEST"),
    ):
        attempt = _build_prompt_attempt(
            task=task,
            stage=stage,
            source_context=source_context,
            allowed_evidence_refs=allowed_evidence_refs,
            required_review_markers=required_review_markers,
            repair_context=repair_context,
            compaction_level=level,
            source_context_status=status,
        )
        try:
            invocation = model_gateway.invoke_semantic_analysis(
                prompt=attempt.prompt,
                profile=profile,
            )
            markers = _attempt_budget_markers(attempt) or _context_length_review_markers(
                attempt.allowed_evidence_refs
            )
            return invocation, _attempt_source_summary(attempt), markers
        except ModelGatewayError as exc:
            if not _is_context_length_error(exc):
                raise
            if level == _COMPACTION_MINIMUM:
                raise _context_length_error_with_attempt_summary(exc, attempt) from exc

    raise AssertionError("unreachable context fallback path")


def _build_prompt_attempt(
    *,
    task: SemanticAnalysisTask,
    stage: str,
    source_context: dict[str, Any] | None,
    allowed_evidence_refs: Sequence[str],
    required_review_markers: Sequence[Mapping[str, Any]],
    repair_context: dict[str, Any] | None,
    compaction_level: str = _COMPACTION_NONE,
    source_context_status: str | None = None,
) -> _PromptAttempt:
    metadata: dict[str, Any] = dict(task.metadata)
    static_analysis = (
        dict(task.static_analysis)
        if isinstance(task.static_analysis, Mapping)
        else None
    )
    attempt_source_context = source_context
    attempt_allowed_refs = tuple(str(ref) for ref in allowed_evidence_refs if str(ref).strip())
    compaction_summary: dict[str, Any] | None = None
    if compaction_level != _COMPACTION_NONE:
        compacted = _compact_semantic_inputs(
            metadata=metadata,
            static_analysis=static_analysis,
            source_context=source_context,
            allowed_evidence_refs=attempt_allowed_refs,
            stage=stage,
            level=compaction_level,
            source_context_status=source_context_status or "COMPACT_NO_SOURCE_TEXT",
        )
        metadata = compacted["metadata"]
        static_analysis = compacted["static_analysis"]
        attempt_source_context = compacted["source_context"]
        attempt_allowed_refs = compacted["allowed_evidence_refs"]
        compaction_summary = compacted["summary"]
    prompt = _render_stage_prompt(
        task=task,
        stage=stage,
        metadata=metadata,
        static_analysis=static_analysis,
        source_context=attempt_source_context,
        allowed_evidence_refs=attempt_allowed_refs,
        required_review_markers=_markers_for_allowed_refs(
            required_review_markers,
            attempt_allowed_refs,
        ),
        repair_context=repair_context,
    )
    return _PromptAttempt(
        prompt=prompt,
        metadata=metadata,
        static_analysis=static_analysis,
        source_context=attempt_source_context,
        allowed_evidence_refs=attempt_allowed_refs,
        compaction_level=compaction_level,
        compaction_summary=compaction_summary,
    )


def _render_stage_prompt(
    *,
    task: SemanticAnalysisTask,
    stage: str,
    metadata: Mapping[str, Any] | None = None,
    static_analysis: Mapping[str, Any] | None = None,
    source_context: dict[str, Any] | None,
    allowed_evidence_refs: Sequence[str],
    required_review_markers: Sequence[Mapping[str, Any]],
    repair_context: dict[str, Any] | None,
) -> Any:
    return render_semantic_analysis_prompt(
        target_ref=task.target_ref,
        metadata=dict(metadata) if metadata is not None else task.metadata,
        static_analysis=(
            dict(static_analysis)
            if static_analysis is not None
            else task.static_analysis
        ),
        procedure_definition=task.procedure_definition,
        source_context=source_context,
        stage=stage,
        allowed_evidence_refs=list(allowed_evidence_refs),
        required_review_markers=[dict(marker) for marker in required_review_markers],
        repair_context=repair_context,
    )


def _source_context_for_stage(
    source_context_packs: Mapping[str, dict[str, Any]] | None,
    stage: str,
) -> dict[str, Any] | None:
    if not isinstance(source_context_packs, Mapping):
        return None
    value = source_context_packs.get(stage)
    if isinstance(value, Mapping):
        return dict(value)
    return None


def _compact_semantic_inputs(
    *,
    metadata: Mapping[str, Any],
    static_analysis: Mapping[str, Any] | None,
    source_context: Mapping[str, Any] | None,
    allowed_evidence_refs: Sequence[str],
    stage: str,
    level: str,
    source_context_status: str,
) -> dict[str, Any]:
    minimum = level == _COMPACTION_MINIMUM
    fact_limit = _compact_limit("LLM_SEMANTIC_COMPACT_FACT_LIMIT", 80, 24, minimum)
    ref_limit = _compact_limit("LLM_SEMANTIC_COMPACT_REF_LIMIT", 96, 32, minimum)
    compact_metadata = _compact_metadata(
        metadata,
        stage=stage,
        fact_limit=fact_limit,
        minimum=minimum,
    )
    compact_static = _compact_static_analysis(static_analysis, minimum=minimum)
    compact_refs = tuple(
        _ranked_evidence_refs(
            _allowed_evidence_refs(
                metadata=compact_metadata,
                static_analysis=compact_static,
            )
            or [str(ref) for ref in allowed_evidence_refs if str(ref).strip()],
            stage=stage,
        )[:ref_limit]
    )
    compact_source_context = without_source_text_context_pack(
        source_context,
        status=source_context_status,
    )
    if minimum and isinstance(compact_source_context, Mapping):
        compact_source_context = {
            key: value
            for key, value in dict(compact_source_context).items()
            if key
            in {
                "version",
                "targetRef",
                "stage",
                "mode",
                "budgetStatus",
                "tokenBudget",
                "estimatedSourceTokens",
                "skippedSpanCount",
                "analysisCoverage",
                "reviewMarkers",
            }
        }
        compact_source_context["selectedSpans"] = []
    summary = {
        "applied": True,
        "level": level,
        "stage": stage,
        "reason": "CONTEXT_LENGTH_BUDGET",
        "allowedEvidenceRefCount": len(compact_refs),
        "deterministicFactCount": len(_mapping_items(compact_metadata.get("deterministicFacts"))),
        "dependencyNodeCount": len(
            _mapping_items(_get_nested(compact_metadata, "dependencyEvidence", "nodes"))
        ),
        "dependencyEdgeCount": len(
            _mapping_items(_get_nested(compact_metadata, "dependencyEvidence", "edges"))
        ),
        "tableSchemaCount": len(_mapping_items(compact_metadata.get("tableSchemas"))),
    }
    compact_metadata["promptCompaction"] = dict(summary)
    return {
        "metadata": compact_metadata,
        "static_analysis": compact_static,
        "source_context": compact_source_context,
        "allowed_evidence_refs": compact_refs,
        "summary": summary,
    }


def _compact_metadata(
    metadata: Mapping[str, Any],
    *,
    stage: str,
    fact_limit: int,
    minimum: bool,
) -> dict[str, Any]:
    compact: dict[str, Any] = {}
    for key in ("dbProfileId", "objectRef", "snapshotId", "collectedAt", "status"):
        if metadata.get(key) is not None:
            compact[key] = metadata.get(key)
    definition = _mapping(metadata.get("procedureDefinition"))
    if definition:
        compact["procedureDefinition"] = {
            key: _safe_compact_value(value)
            for key, value in definition.items()
            if _safe_prompt_key(key)
        }
    parameters = _mapping(metadata.get("procedureParameters"))
    if parameters:
        compact["procedureParameters"] = _compact_parameters(parameters, minimum=minimum)
    dependencies = _mapping(metadata.get("procedureDependencies"))
    if dependencies and not minimum:
        compact["procedureDependencies"] = _compact_procedure_dependencies(dependencies)
    dependency_evidence = _mapping(metadata.get("dependencyEvidence"))
    if dependency_evidence:
        compact["dependencyEvidence"] = _compact_dependency_evidence(
            dependency_evidence,
            stage=stage,
            minimum=minimum,
        )
    facts = _ranked_facts(
        _mapping_items(metadata.get("deterministicFacts")),
        stage=stage,
    )[:fact_limit]
    if facts:
        compact["deterministicFacts"] = [_compact_fact(fact) for fact in facts]
    evidence_refs = _mapping_items(metadata.get("evidenceRefs"))
    ref_limit = _compact_limit("LLM_SEMANTIC_COMPACT_METADATA_REF_LIMIT", 48, 16, minimum)
    if evidence_refs:
        compact["evidenceRefs"] = [_compact_evidence_ref(ref) for ref in evidence_refs[:ref_limit]]
    tables = _mapping_items(metadata.get("tableSchemas"))
    if tables:
        compact["tableSchemas"] = _compact_table_schemas(tables, minimum=minimum)
    for key in ("aiToolEvidence", "platformToolEvidence"):
        evidence = _mapping(metadata.get(key))
        if evidence:
            compact[key] = _compact_tool_evidence(evidence, stage=stage, minimum=minimum)
    for key in ("notes", "errors"):
        values = _sequence(metadata.get(key))
        if values:
            compact[key] = [_safe_compact_value(item) for item in values[:6 if not minimum else 3]]
    return compact


def _compact_static_analysis(
    static_analysis: Mapping[str, Any] | None,
    *,
    minimum: bool,
) -> dict[str, Any] | None:
    if not isinstance(static_analysis, Mapping):
        return None
    compact: dict[str, Any] = {}
    for key in ("patterns", "analysisCoverage", "migrationGuideStaticMetrics", "fact_ids"):
        if static_analysis.get(key) is not None:
            compact[key] = _safe_compact_value(static_analysis.get(key))
    source_map = _mapping(static_analysis.get("sourceMap"))
    if source_map:
        span_limit = _compact_limit("LLM_SEMANTIC_COMPACT_SOURCE_SPAN_LIMIT", 40, 12, minimum)
        compact["sourceMap"] = {
            "version": source_map.get("version"),
            "sourceName": source_map.get("sourceName"),
            "sourceHashSha256": source_map.get("sourceHashSha256"),
            "totalLines": source_map.get("totalLines"),
            "spans": [
                {
                    key: _safe_compact_value(span.get(key))
                    for key in (
                        "spanId",
                        "kind",
                        "startLine",
                        "endLine",
                        "referencedObjects",
                        "riskTags",
                        "evidenceRefs",
                    )
                    if span.get(key) is not None
                }
                for span in _mapping_items(source_map.get("spans"))[:span_limit]
            ],
        }
    return compact or None


def _compact_parameters(value: Mapping[str, Any], *, minimum: bool) -> dict[str, Any]:
    params = _mapping_items(value.get("parameters"))
    limit = _compact_limit("LLM_SEMANTIC_COMPACT_PARAMETER_LIMIT", 40, 12, minimum)
    return {
        "parameterCount": len(params),
        "parameters": [
            {
                key: _safe_compact_value(item.get(key))
                for key in ("name", "dataType", "direction", "isNullable", "hasDefault")
                if item.get(key) is not None
            }
            for item in params[:limit]
        ],
    }


def _compact_procedure_dependencies(value: Mapping[str, Any]) -> dict[str, Any]:
    dependencies = _mapping_items(value.get("dependencies"))
    return {
        "dependencyCount": len(dependencies),
        "dependencies": [
            {
                key: _safe_compact_value(item.get(key))
                for key in ("schema", "name", "objectType", "dependencyType")
                if item.get(key) is not None
            }
            for item in dependencies[:24]
        ],
    }


def _compact_dependency_evidence(
    value: Mapping[str, Any],
    *,
    stage: str,
    minimum: bool,
) -> dict[str, Any]:
    node_limit = _compact_limit("LLM_SEMANTIC_COMPACT_DEP_NODE_LIMIT", 24, 8, minimum)
    edge_limit = _compact_limit("LLM_SEMANTIC_COMPACT_DEP_EDGE_LIMIT", 32, 12, minimum)
    unresolved_limit = _compact_limit("LLM_SEMANTIC_COMPACT_DEP_UNRESOLVED_LIMIT", 12, 6, minimum)
    nodes = _ranked_dependency_items(_mapping_items(value.get("nodes")), stage=stage)[:node_limit]
    edges = _ranked_dependency_items(_mapping_items(value.get("edges")), stage=stage)[:edge_limit]
    unresolved = _ranked_dependency_items(
        _mapping_items(value.get("unresolved")),
        stage=stage,
    )[:unresolved_limit]
    return {
        "toolName": value.get("toolName") or "get_dependency_closure",
        "dbProfileId": value.get("dbProfileId"),
        "snapshotId": value.get("snapshotId"),
        "rootObject": _safe_compact_value(value.get("rootObject")),
        "summary": _safe_compact_value(value.get("summary")),
        "nodes": [_compact_dependency_node(item) for item in nodes],
        "edges": [_compact_dependency_edge(item) for item in edges],
        "unresolved": [_compact_dependency_unresolved(item) for item in unresolved],
        "evidenceRefs": [
            _compact_evidence_ref(ref)
            for ref in _mapping_items(value.get("evidenceRefs"))[: 16 if minimum else 48]
        ],
        "caveats": [str(item)[:240] for item in _sequence(value.get("caveats"))[:8]],
        "reviewRequired": bool(value.get("reviewRequired")),
        "originalCounts": {
            "nodes": len(_mapping_items(value.get("nodes"))),
            "edges": len(_mapping_items(value.get("edges"))),
            "unresolved": len(_mapping_items(value.get("unresolved"))),
        },
    }


def _compact_dependency_node(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: _safe_compact_value(item.get(key))
        for key in (
            "id",
            "database",
            "schema",
            "name",
            "objectType",
            "sourceScope",
            "reviewStatus",
            "evidenceRefs",
        )
        if item.get(key) is not None
    }


def _compact_dependency_edge(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: _safe_compact_value(item.get(key))
        for key in (
            "from",
            "to",
            "dependencyType",
            "resolutionStatus",
            "resolutionStrategy",
            "resolutionConfidence",
            "unresolvedReason",
            "evidenceRefs",
        )
        if item.get(key) is not None
    }


def _compact_dependency_unresolved(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: _safe_compact_value(item.get(key))
        for key in (
            "database",
            "schema",
            "name",
            "objectType",
            "dependencyType",
            "resolutionStatus",
            "resolutionStrategy",
            "unresolvedReason",
            "evidenceRefs",
        )
        if item.get(key) is not None
    }


def _compact_table_schemas(
    tables: Sequence[Mapping[str, Any]],
    *,
    minimum: bool,
) -> list[dict[str, Any]]:
    table_limit = _compact_limit("LLM_SEMANTIC_COMPACT_TABLE_LIMIT", 8, 3, minimum)
    column_limit = _compact_limit("LLM_SEMANTIC_COMPACT_COLUMN_LIMIT", 16, 6, minimum)
    compacted: list[dict[str, Any]] = []
    for table in tables[:table_limit]:
        columns = _mapping_items(table.get("columns"))
        compacted.append(
            {
                "schema": table.get("schema"),
                "tableName": table.get("tableName"),
                "columnCount": len(columns),
                "columns": [
                    {
                        key: _safe_compact_value(column.get(key))
                        for key in ("name", "dataType", "isNullable", "logicalName", "description")
                        if column.get(key) is not None
                    }
                    for column in columns[:column_limit]
                ],
            }
        )
    return compacted


def _compact_tool_evidence(
    evidence: Mapping[str, Any],
    *,
    stage: str,
    minimum: bool,
) -> dict[str, Any]:
    result_limit = _compact_limit("LLM_SEMANTIC_COMPACT_TOOL_RESULT_LIMIT", 12, 4, minimum)
    results = _ranked_dependency_items(_mapping_items(evidence.get("toolResults")), stage=stage)
    return {
        "status": evidence.get("status"),
        "toolCallCount": evidence.get("toolCallCount"),
        "toolResults": [
            {
                key: _safe_compact_value(result.get(key))
                for key in ("factId", "toolName", "summary", "status", "evidenceRefs")
                if result.get(key) is not None
            }
            for result in results[:result_limit]
        ],
        "blockedRequests": [
            {
                key: _safe_compact_value(item.get(key))
                for key in ("toolName", "code", "message", "reason")
                if item.get(key) is not None
            }
            for item in _mapping_items(evidence.get("blockedRequests"))[: 4 if minimum else 8]
        ],
        "reviewMarkers": [
            _compact_review_marker(marker)
            for marker in _mapping_items(evidence.get("reviewMarkers"))[: 4 if minimum else 12]
        ],
        "caveats": [str(item)[:240] for item in _sequence(evidence.get("caveats"))[:8]],
        "plannerMetrics": _safe_compact_value(evidence.get("plannerMetrics")),
    }


def _compact_fact(fact: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: _safe_compact_value(fact.get(key))
        for key in ("id", "fact_type", "type", "summary", "status", "evidenceRefs")
        if fact.get(key) is not None
    }


def _compact_evidence_ref(ref: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: _safe_compact_value(ref.get(key))
        for key in ("type", "objectRef", "locator", "snapshotId")
        if ref.get(key) is not None
    }


def _compact_review_marker(marker: Mapping[str, Any]) -> dict[str, Any]:
    return {
        key: _safe_compact_value(marker.get(key))
        for key in ("code", "message", "status", "evidenceRefs")
        if marker.get(key) is not None
    }


def _ranked_facts(items: Sequence[Mapping[str, Any]], *, stage: str) -> list[Mapping[str, Any]]:
    keywords = _stage_keywords(stage)
    return sorted(
        items,
        key=lambda item: (
            -_keyword_score(item, keywords),
            str(item.get("id") or ""),
        ),
    )


def _ranked_dependency_items(
    items: Sequence[Mapping[str, Any]],
    *,
    stage: str,
) -> list[Mapping[str, Any]]:
    keywords = _stage_keywords(stage)
    return sorted(
        items,
        key=lambda item: (
            -_keyword_score(item, keywords),
            str(item.get("id") or item.get("to") or item.get("name") or ""),
        ),
    )


def _ranked_evidence_refs(items: Sequence[str], *, stage: str) -> list[str]:
    keywords = _stage_keywords(stage)
    deduped = _dedupe([str(item) for item in items if str(item).strip()])
    return sorted(deduped, key=lambda item: (-_keyword_score({"ref": item}, keywords), item))


def _stage_keywords(stage: str) -> tuple[str, ...]:
    if stage == "business_rule_extraction":
        return ("business", "parameter", "result", "select", "insert", "update", "delete", "branch")
    if stage == "conversion_readiness":
        return ("dto", "java", "mybatis", "parameter", "result", "transaction", "dml", "dependency")
    if stage == "migration_guide_insights":
        return ("migration", "dml", "dependency", "call", "result", "risk", "dynamic", "cross")
    if stage == "evidence_critic":
        return ("dynamic", "cross", "unresolved", "ambiguous", "review", "caveat", "dependency")
    return ("procedure", "parameter", "dependency", "source", "metadata", "result", "dml")


def _keyword_score(item: Mapping[str, Any], keywords: Sequence[str]) -> int:
    text = json.dumps(item, ensure_ascii=False, sort_keys=True, default=str).lower()
    return sum(1 for keyword in keywords if keyword in text)


def _safe_compact_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _safe_compact_value(item)
            for key, item in value.items()
            if _safe_prompt_key(str(key))
        }
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return [_safe_compact_value(item) for item in list(value)[:32]]
    if isinstance(value, str):
        return value[:240]
    return value


def _safe_prompt_key(key: str) -> bool:
    normalized = key.replace("-", "_").lower()
    return normalized not in {
        "definition",
        "raw_definition",
        "raw_definition_text",
        "rawsql",
        "raw_sql",
        "sqltext",
        "sql_text",
        "statement",
        "command",
        "rowdata",
        "row_data",
        "rows",
        "records",
        "password",
        "secret",
        "token",
        "apikey",
        "api_key",
        "connectionstring",
        "connection_string",
        "prompt",
        "raw_prompt",
        "provider_response",
    }


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _mapping_items(value: Any) -> list[Mapping[str, Any]]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _sequence(value: Any) -> list[Any]:
    if not isinstance(value, Sequence) or isinstance(value, str | bytes):
        return []
    return list(value)


def _get_nested(value: Mapping[str, Any], *path: str) -> Any:
    current: Any = value
    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)
    return current


def _compact_limit(name: str, compact_default: int, minimum_default: int, minimum: bool) -> int:
    return max(1, _env_int(name, minimum_default if minimum else compact_default))


def _markers_for_allowed_refs(
    markers: Sequence[Mapping[str, Any]],
    allowed_evidence_refs: Sequence[str],
) -> list[dict[str, Any]]:
    allowed = set(allowed_evidence_refs)
    repaired = []
    for marker in markers:
        item = dict(marker)
        refs = [ref for ref in _evidence_refs(item) if ref in allowed]
        if not refs:
            refs = _fallback_evidence_refs(item, allowed_evidence_refs)
        item["evidenceRefs"] = refs
        repaired.append(item)
    return repaired


def _attempt_source_summary(attempt: _PromptAttempt) -> dict[str, Any]:
    summary = context_pack_summary(attempt.source_context)
    if attempt.compaction_summary:
        summary["promptCompaction"] = dict(attempt.compaction_summary)
    return summary


def _attempt_budget_markers(attempt: _PromptAttempt) -> list[dict[str, Any]]:
    markers = _context_markers(attempt.source_context)
    if attempt.compaction_summary:
        markers.append(_prompt_compaction_marker(attempt))
    return markers


def _prompt_compaction_marker(attempt: _PromptAttempt) -> dict[str, Any]:
    return {
        "code": PROMPT_COMPACTION_MARKER_CODE,
        "message": (
            "Semantic model input was compacted to a bounded evidence digest after "
            "context budget pressure."
        ),
        "status": "REVIEW_REQUIRED",
        "evidenceRefs": _fallback_evidence_refs(
            {"code": PROMPT_COMPACTION_MARKER_CODE},
            attempt.allowed_evidence_refs,
        ),
    }


def _context_length_error_with_attempt_summary(
    exc: ModelGatewayError,
    attempt: _PromptAttempt,
) -> ModelGatewayError:
    provider_error = {
        key: _sanitize_provider_error_text(value)
        for key, value in exc.provider_error.items()
        if value is not None
    }
    provider_error.update(
        {
            "semanticCompactionLevel": attempt.compaction_level,
            "semanticCompactionApplied": "true",
            "semanticEstimatedPromptTokens": str(attempt.estimated_tokens),
            "semanticAllowedEvidenceRefCount": str(len(attempt.allowed_evidence_refs)),
        }
    )
    return ModelGatewayError(str(exc), code=exc.code, provider_error=provider_error)


def _sanitize_provider_error_text(value: Any) -> str:
    text = str(sanitize_value_for_storage(str(value), procedure_definition=""))
    text = re.sub(r"(?i)\bbearer\s+[^\s,}]+", "Bearer [REDACTED]", text)
    text = re.sub(
        r"(?i)\b(access[_-]?token|api[_-]?key|password|secret)\s*=\s*[^\s,}]+",
        lambda match: f"{match.group(1)}=[REDACTED]",
        text,
    )
    return text[:500]


def _is_context_length_error(exc: ModelGatewayError) -> bool:
    haystack = " ".join(
        str(value)
        for value in (
            exc.code,
            exc,
            *exc.provider_error.values(),
        )
        if value is not None
    ).lower()
    return "context_length" in haystack or "context length" in haystack


def _semantic_input_token_budget() -> int:
    return max(1024, _env_int("LLM_SEMANTIC_INPUT_TOKEN_BUDGET", 64000))


def _estimated_prompt_tokens(prompt: Any) -> int:
    return max(1, (len(prompt.system_prompt) + len(prompt.user_prompt) + 3) // 4)


def _context_markers(source_context: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(source_context, Mapping):
        return []
    return [
        dict(item)
        for item in source_context.get("reviewMarkers", [])
        if isinstance(item, Mapping)
    ]


def _context_length_review_markers(
    allowed_evidence_refs: Sequence[str],
) -> list[dict[str, Any]]:
    return [
        {
            "code": CONTEXT_BUDGET_MARKER_CODE,
            "message": (
                "Model input exceeded provider context and analysis used reduced evidence context."
            ),
            "status": "REVIEW_REQUIRED",
            "evidenceRefs": _fallback_evidence_refs(
                {"code": CONTEXT_BUDGET_MARKER_CODE},
                allowed_evidence_refs,
            ),
        }
    ]


def _append_context_budget_markers(
    output: Mapping[str, Any],
    markers: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if not markers:
        return dict(output)
    repaired = LlmSemanticAnalysisOutput.model_validate(output).to_storage_dict()
    existing_codes = {
        str(item.get("code") or "")
        for item in repaired["reviewMarkers"]
        if isinstance(item, Mapping)
    }
    for marker in markers:
        code = str(marker.get("code") or "")
        if not code or code in existing_codes:
            continue
        repaired["reviewMarkers"].append(
            {
                "code": code,
                "message": str(marker.get("message") or ""),
                "status": "REVIEW_REQUIRED",
                "evidenceRefs": [
                    str(ref)
                    for ref in marker.get("evidenceRefs", [])
                    if str(ref).strip()
                ],
            }
        )
        existing_codes.add(code)
    return repaired


def _summary(output: LlmSemanticAnalysisOutput) -> str:
    return (
        f"비즈니스 규칙 {len(output.business_rules)}개, "
        f"현대화 포인트 {len(output.modernization_points)}개, "
        f"위험 플래그 {len(output.risk_flags)}개, "
        f"근거 caveat {len(output.review_markers)}개, "
        f"전환 가이드 {len(output.conversion_guidance)}개, "
        f"마이그레이션 가이드 인사이트 {len(output.migration_guide_insights)}개"
    )


def _stages_for_task(
    *,
    static_analysis: Mapping[str, Any] | None,
    required_review_markers: Sequence[Mapping[str, Any]],
) -> tuple[str, ...]:
    return (
        "deterministic_evidence_digest",
        "business_rule_extraction",
        "conversion_readiness",
        "migration_guide_insights",
        "evidence_critic",
    )


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

    refs: list[str] = []
    refs.extend(deterministic_refs)
    for ref in _metadata_evidence_refs(metadata):
        refs.append(ref)
    if not deterministic_refs:
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
                "동적 SQL 또는 cross-database SQL에서 추론한 구체 테이블 의존성은 "
                "결정론적 메타데이터가 확인하기 전까지 REVIEW_REQUIRED로 유지해야 합니다."
            ),
            "status": "REVIEW_REQUIRED",
            "evidenceRefs": dynamic_refs,
        },
        {
            "code": "UNSUPPORTED_FUNCTION_CLAIM_REVIEW",
            "message": (
                "추론된 helper function 의존성은 결정론적 메타데이터가 확인하기 전까지 "
                "REVIEW_REQUIRED로 유지해야 합니다."
            ),
            "status": "REVIEW_REQUIRED",
            "evidenceRefs": function_refs or dynamic_refs,
        },
        {
            "code": "UNSUPPORTED_PROCEDURE_CLAIM_REVIEW",
            "message": (
                "결정론적 procedure-call fact만 확인된 호출로 취급할 수 있으며, "
                "추가 procedure 의존성은 검토가 필요합니다."
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
        "conversionGuidance": [],
        "migrationGuideInsights": [],
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


def _apply_language_repair_output(
    output: Mapping[str, Any],
    repair_output: Mapping[str, Any],
) -> dict[str, Any]:
    repaired = LlmSemanticAnalysisOutput.model_validate(output).to_storage_dict()
    candidate = LlmSemanticAnalysisOutput.model_validate(repair_output).to_storage_dict()
    for field_name in OUTPUT_FIELDS:
        key_field = KEY_FIELDS[field_name]
        candidate_by_key = {
            str(item.get(key_field) or ""): item
            for item in candidate[field_name]
            if isinstance(item, Mapping)
        }
        for item in repaired[field_name]:
            candidate_item = candidate_by_key.get(str(item.get(key_field) or ""))
            if not candidate_item:
                continue
            for text_field in ("summary", "message", "whatToExtractNext"):
                if text_field not in item or text_field not in candidate_item:
                    continue
                candidate_text = str(candidate_item.get(text_field) or "")
                if human_text_needs_korean(item.get(text_field)) and contains_korean(
                    candidate_text
                ):
                    item[text_field] = candidate_text
    if any(contains_korean(item) for item in candidate["assumptions"]):
        repaired["assumptions"] = list(candidate["assumptions"])
    return repaired


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


def _uses_pgpt(invocations: Sequence[tuple[str, ModelInvocationRecord]]) -> bool:
    if os.getenv("LLM_REMOTE_PROVIDER", "").strip().lower() in {"pgpt", "p-gpt", "private-gpt"}:
        return True
    return any(
        str(invocation.provider).strip().lower() in {"pgpt", "p-gpt", "private-gpt"}
        for _stage, invocation in invocations
    )


def _apply_deterministic_safety_net(
    output: Mapping[str, Any],
    *,
    metadata: Mapping[str, Any],
    static_analysis: Mapping[str, Any] | None,
    allowed_evidence_refs: Sequence[str],
) -> dict[str, Any]:
    repaired = LlmSemanticAnalysisOutput.model_validate(output).to_storage_dict()
    facts = _deterministic_fact_index(
        metadata=metadata,
        static_analysis=static_analysis,
        allowed_evidence_refs=allowed_evidence_refs,
    )
    if not facts:
        return repaired

    def refs(*themes: str, limit: int = 3) -> list[str]:
        values: list[str] = []
        for theme in themes:
            values.extend(facts.get(theme, []))
        return _dedupe(ref for ref in values if ref in allowed_evidence_refs)[:limit]

    read_refs = refs("parameter", "table_read", "result_shape")
    if read_refs:
        _append_claim(
            repaired["businessRules"],
            key_field="category",
            key="DETERMINISTIC_SAFETY_NET_READ_ONLY_LOOKUP",
            payload={
                "category": "DETERMINISTIC_SAFETY_NET_READ_ONLY_LOOKUP",
                "summary": (
                    "결정론적 fact가 읽기 전용 조회 동작을 보여 주며, 초안 비즈니스 "
                    "맥락으로 검토해야 합니다."
                ),
                "status": "INFERRED_DESCRIPTION",
                "evidenceRefs": read_refs,
            },
        )
        _append_claim(
            repaired["modernizationPoints"],
            key_field="code",
            key="DETERMINISTIC_SAFETY_NET_LOOKUP_DTO_SHAPE",
            payload={
                "code": "DETERMINISTIC_SAFETY_NET_LOOKUP_DTO_SHAPE",
                "summary": (
                    "조회 입력과 result-shape fact는 Java/MyBatis 전환 전에 명시적인 "
                    "DTO 필드로 매핑해야 합니다."
                ),
                "status": "REVIEW_REQUIRED",
                "evidenceRefs": read_refs,
            },
        )
        _append_claim(
            repaired["conversionGuidance"],
            key_field="code",
            key="DETERMINISTIC_SAFETY_NET_LOOKUP_CONVERSION_GUIDANCE",
            payload={
                "code": "DETERMINISTIC_SAFETY_NET_LOOKUP_CONVERSION_GUIDANCE",
                "summary": (
                    "결정론적 DTO 계약이 검증될 때까지 조회 parameter binding과 결과 "
                    "매핑은 REVIEW_REQUIRED로 유지합니다."
                ),
                "status": "REVIEW_REQUIRED",
                "evidenceRefs": read_refs,
            },
        )
        _append_claim(
            repaired["migrationGuideInsights"],
            key_field="section",
            key="DETERMINISTIC_SAFETY_NET_LOOKUP_GUIDE",
            payload={
                "section": "DETERMINISTIC_SAFETY_NET_LOOKUP_GUIDE",
                "summary": (
                    "마이그레이션 가이드는 조회 입력, 읽기 의존성, result-shape 검토 "
                    "메모를 포함해야 합니다."
                ),
                "status": "REVIEW_REQUIRED",
                "evidenceRefs": read_refs,
            },
        )

    branch_refs = refs("branch", "parameter")
    if branch_refs:
        _append_claim(
            repaired["businessRules"],
            key_field="category",
            key="DETERMINISTIC_SAFETY_NET_BRANCH_RULE",
            payload={
                "category": "DETERMINISTIC_SAFETY_NET_BRANCH_RULE",
                "summary": (
                    "결정론적 branch fact가 조건별 비즈니스 결과를 나타내며, "
                    "마이그레이션 가이드에서 검토해야 합니다."
                ),
                "status": "INFERRED_DESCRIPTION",
                "evidenceRefs": branch_refs,
            },
        )

    dml_refs = refs("transaction", "table_write", "error", "branch", limit=4)
    if dml_refs:
        _append_claim(
            repaired["riskFlags"],
            key_field="code",
            key="DETERMINISTIC_SAFETY_NET_TRANSACTION_DML_REVIEW",
            payload={
                "code": "DETERMINISTIC_SAFETY_NET_TRANSACTION_DML_REVIEW",
                "severity": "WARNING",
                "summary": (
                    "Transaction, DML, branch, error-handling fact는 Java/MyBatis "
                    "transaction boundary 초안 작성 전에 사람 검토가 필요합니다."
                ),
                "status": "REVIEW_REQUIRED",
                "evidenceRefs": dml_refs,
            },
        )
        _append_claim(
            repaired["conversionGuidance"],
            key_field="code",
            key="DETERMINISTIC_SAFETY_NET_TRANSACTION_CONVERSION_GUIDANCE",
            payload={
                "code": "DETERMINISTIC_SAFETY_NET_TRANSACTION_CONVERSION_GUIDANCE",
                "summary": (
                    "Transaction boundary, branch 결과, error handling은 REVIEW_REQUIRED "
                    "전환 가이드로 보존합니다."
                ),
                "status": "REVIEW_REQUIRED",
                "evidenceRefs": dml_refs,
            },
        )
        _append_claim(
            repaired["migrationGuideInsights"],
            key_field="section",
            key="DETERMINISTIC_SAFETY_NET_DML_MATRIX",
            payload={
                "section": "DETERMINISTIC_SAFETY_NET_DML_MATRIX",
                "summary": (
                    "마이그레이션 가이드는 DML/transaction matrix와 REVIEW_REQUIRED "
                    "branch 결과를 포함해야 합니다."
                ),
                "status": "REVIEW_REQUIRED",
                "evidenceRefs": dml_refs,
            },
        )

    audit_refs = refs("audit_write", "table_write")
    if audit_refs:
        _append_claim(
            repaired["businessRules"],
            key_field="category",
            key="DETERMINISTIC_SAFETY_NET_AUDIT_SIDE_EFFECT",
            payload={
                "category": "DETERMINISTIC_SAFETY_NET_AUDIT_SIDE_EFFECT",
                "summary": (
                    "결정론적 write fact가 audit 또는 reporting side effect를 나타내며, "
                    "초안 비즈니스 맥락으로 유지합니다."
                ),
                "status": "INFERRED_DESCRIPTION",
                "evidenceRefs": audit_refs,
            },
        )
        _append_claim(
            repaired["modernizationPoints"],
            key_field="code",
            key="DETERMINISTIC_SAFETY_NET_AUDIT_MODERNIZATION_REVIEW",
            payload={
                "code": "DETERMINISTIC_SAFETY_NET_AUDIT_MODERNIZATION_REVIEW",
                "summary": (
                    "Audit/reporting side effect는 결정론적 검토 후에만 service logic과 "
                    "분리합니다."
                ),
                "status": "REVIEW_REQUIRED",
                "evidenceRefs": audit_refs,
            },
        )

    dynamic_refs = refs(
        "dynamic_sql",
        "cross_database",
        "procedure_call",
        "result_uncertain",
        limit=4,
    )
    if dynamic_refs:
        _append_claim(
            repaired["modernizationPoints"],
            key_field="code",
            key="DETERMINISTIC_SAFETY_NET_DYNAMIC_SQL_REVIEW",
            payload={
                "code": "DETERMINISTIC_SAFETY_NET_DYNAMIC_SQL_REVIEW",
                "summary": (
                    "Dynamic SQL 또는 cross-database evidence는 REVIEW_REQUIRED 현대화 "
                    "작업으로 분리해야 합니다."
                ),
                "status": "REVIEW_REQUIRED",
                "evidenceRefs": dynamic_refs,
            },
        )
        _append_claim(
            repaired["conversionGuidance"],
            key_field="code",
            key="DETERMINISTIC_SAFETY_NET_DYNAMIC_SQL_CONVERSION_GUIDANCE",
            payload={
                "code": "DETERMINISTIC_SAFETY_NET_DYNAMIC_SQL_CONVERSION_GUIDANCE",
                "summary": (
                    "결정론적 메타데이터 없이는 dynamic SQL 의존성이나 result shape를 "
                    "확정하지 말고 전환 가이드는 REVIEW_REQUIRED로 유지합니다."
                ),
                "status": "REVIEW_REQUIRED",
                "evidenceRefs": dynamic_refs,
            },
        )
        _append_claim(
            repaired["migrationGuideInsights"],
            key_field="section",
            key="DETERMINISTIC_SAFETY_NET_DYNAMIC_DEPENDENCY_GUIDE",
            payload={
                "section": "DETERMINISTIC_SAFETY_NET_DYNAMIC_DEPENDENCY_GUIDE",
                "summary": (
                    "마이그레이션 가이드는 dynamic SQL, cross-database, 불확실한 "
                    "result-shape caveat를 REVIEW_REQUIRED로 나열해야 합니다."
                ),
                "status": "REVIEW_REQUIRED",
                "evidenceRefs": dynamic_refs,
            },
        )
        _append_claim(
            repaired["riskFlags"],
            key_field="code",
            key="DETERMINISTIC_SAFETY_NET_DYNAMIC_DEPENDENCY_RISK",
            payload={
                "code": "DETERMINISTIC_SAFETY_NET_DYNAMIC_DEPENDENCY_RISK",
                "severity": "WARNING",
                "summary": (
                    "Dynamic SQL, cross-database reference, 불확실한 result shape는 "
                    "의존성을 숨길 수 있으므로 REVIEW_REQUIRED로 유지해야 합니다."
                ),
                "status": "REVIEW_REQUIRED",
                "evidenceRefs": dynamic_refs,
            },
        )
        _append_claim(
            repaired["reviewMarkers"],
            key_field="code",
            key="DETERMINISTIC_SAFETY_NET_UNSUPPORTED_DEPENDENCY_REVIEW",
            payload={
                "code": "DETERMINISTIC_SAFETY_NET_UNSUPPORTED_DEPENDENCY_REVIEW",
                "message": (
                    "Dynamic 또는 cross-database evidence에서 나온 미지원 dependency/table/"
                    "function/procedure claim은 evidence caveat로만 유지합니다."
                ),
                "status": "REVIEW_REQUIRED",
                "evidenceRefs": dynamic_refs,
            },
        )

    if repaired["assumptions"] and "DETERMINISTIC_SAFETY_NET" not in " ".join(
        repaired["assumptions"]
    ):
        repaired["assumptions"].append(
            "DETERMINISTIC_SAFETY_NET은 허용된 결정론적 fact id만 사용해 초안 claim을 추가했습니다."
        )
    elif not repaired["assumptions"]:
        repaired["assumptions"].append(
            "DETERMINISTIC_SAFETY_NET은 허용된 결정론적 fact id만 사용해 초안 claim을 추가했습니다."
        )
    return repaired


def _deterministic_fact_index(
    *,
    metadata: Mapping[str, Any],
    static_analysis: Mapping[str, Any] | None,
    allowed_evidence_refs: Sequence[str],
) -> dict[str, list[str]]:
    allowed = {str(ref) for ref in allowed_evidence_refs if str(ref).strip()}
    themes: dict[str, list[str]] = {}
    deterministic_facts = metadata.get("deterministicFacts") or metadata.get("deterministic_facts")
    if isinstance(deterministic_facts, Sequence) and not isinstance(
        deterministic_facts,
        str | bytes,
    ):
        for fact in deterministic_facts:
            if not isinstance(fact, Mapping):
                continue
            fact_id = str(fact.get("id") or "")
            if fact_id not in allowed:
                continue
            haystack = " ".join(
                str(fact.get(key) or "")
                for key in ("id", "type", "fact_type", "summary", "objectRef", "object_ref")
            ).lower()
            for theme, keywords in _fact_theme_keywords().items():
                if any(keyword in haystack for keyword in keywords):
                    themes.setdefault(theme, []).append(fact_id)

    for ref in _static_pattern_refs(static_analysis):
        if ref not in allowed:
            continue
        haystack = ref.lower()
        for theme, keywords in _fact_theme_keywords().items():
            if any(keyword in haystack for keyword in keywords):
                themes.setdefault(theme, []).append(ref)

    return {theme: _dedupe(refs) for theme, refs in themes.items()}


def _fact_theme_keywords() -> dict[str, tuple[str, ...]]:
    return {
        "parameter": ("parameter", "input", "param"),
        "table_read": ("table_read", "read", "lookup", "select"),
        "result_shape": ("result_shape", "result shape", "result"),
        "result_uncertain": ("uncertain", "unknown", "ambiguous"),
        "transaction": ("transaction", "commit", "rollback", "try_catch", "try catch"),
        "branch": ("branch", "approve", "hold", "conditional", "decision"),
        "table_write": ("table_write", "write", "insert", "update", "delete", "dml"),
        "audit_write": ("audit", "reporting", "extract"),
        "error": ("error", "exception", "raiserror", "throw"),
        "dynamic_sql": ("dynamic", "sp_executesql"),
        "cross_database": ("cross", "database", "tenant"),
        "procedure_call": ("procedure_call", "procedure", "sp_executesql"),
    }


def _append_claim(
    items: list[dict[str, Any]],
    *,
    key_field: str,
    key: str,
    payload: dict[str, Any],
) -> None:
    for existing in items:
        if str(existing.get(key_field) or "") == key:
            existing["evidenceRefs"] = _dedupe(
                [*_evidence_refs(existing), *_evidence_refs(payload)]
            )
            existing["status"] = payload.get("status", existing.get("status"))
            return
    if payload.get("evidenceRefs"):
        items.append(payload)


def _sanitize_output_for_storage(
    output: Mapping[str, Any],
    *,
    procedure_definition: str,
    allowed_evidence_refs: Sequence[str],
) -> dict[str, Any]:
    normalized = LlmSemanticAnalysisOutput.model_validate(output).to_storage_dict()
    findings = storage_safety_findings(
        payloads=(normalized,),
        procedure_definition=procedure_definition,
    )
    if not findings:
        return normalized

    sanitized = LlmSemanticAnalysisOutput.model_validate(
        sanitize_value_for_storage(
            normalized,
            procedure_definition=procedure_definition,
        )
    ).to_storage_dict()
    _append_storage_safety_marker(
        sanitized,
        allowed_evidence_refs=allowed_evidence_refs,
    )
    return sanitized


def _append_storage_safety_marker(
    output: dict[str, Any],
    *,
    allowed_evidence_refs: Sequence[str],
) -> None:
    marker_code = "LLM_OUTPUT_STORAGE_SANITIZED"
    evidence_refs = _fallback_evidence_refs(
        {"code": marker_code, "message": "storage sanitized"},
        allowed_evidence_refs,
    )
    marker = {
        "code": marker_code,
        "message": (
            "저장 전에 LLM 출력에서 안전하지 않은 SQL, provider trace, row-data 또는 "
            "secret-like 내용을 제거했습니다."
        ),
        "status": "REVIEW_REQUIRED",
        "evidenceRefs": evidence_refs,
    }
    for existing in output["reviewMarkers"]:
        if existing.get("code") == marker_code:
            existing["status"] = "REVIEW_REQUIRED"
            existing["evidenceRefs"] = _dedupe(
                [*_evidence_refs(existing), *evidence_refs]
            )
            existing["message"] = marker["message"]
            return
    output["reviewMarkers"].append(marker)


def _aggregate_invocations(
    *,
    invocations: Sequence[tuple[str, ModelInvocationRecord]],
    structured_output: dict[str, Any],
    profile: Any,
    source_context_summaries: Sequence[Mapping[str, Any]] = (),
) -> ModelInvocationRecord:
    if not invocations:
        raise ValueError("At least one model invocation is required.")
    _first_stage, first = invocations[0]
    component_invocations = tuple(
        _component_invocation_summary(
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
                "sourceContextSummary": (
                    dict(source_context_summaries[index])
                    if index < len(source_context_summaries)
                    else {}
                ),
            },
            nested=invocation.component_invocations,
        )
        for index, (stage, invocation) in enumerate(invocations)
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


def _component_invocation_summary(
    payload: dict[str, Any],
    *,
    nested: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    summary = dict(payload)
    if nested:
        summary["componentInvocations"] = [dict(item) for item in nested]
    return summary


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
