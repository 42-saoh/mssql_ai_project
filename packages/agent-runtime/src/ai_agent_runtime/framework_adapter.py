from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace as dataclass_replace
from typing import Any, Protocol

from ai_agent_runtime.gateway import ModelGateway, ModelGatewayError
from ai_agent_runtime.models import (
    AgentRunStatus,
    ModelInvocationRecord,
    ModelProfile,
    RenderedPrompt,
    stable_json_hash,
)
from ai_agent_runtime.storage_safety import storage_safety_findings

AI_GENERATION_FRAMEWORK_ADAPTER_VERSION = "AiGenerationFrameworkAdapter.v0.1"
P43_FRAMEWORK_RAW_TRACE_BLOCKED = "P43_FRAMEWORK_RAW_TRACE_BLOCKED"
P43_FRAMEWORK_TOOL_CONTEXT_BLOCKED = "P43_FRAMEWORK_TOOL_CONTEXT_BLOCKED"

_ADAPTER_COMPONENT = "ai_generation_framework_adapter"
_FRAMEWORK_STAGES = frozenset({"file_inventory", "file_content", "repair"})
_TRACE_SUMMARY_FIELDS = frozenset(
    {
        "component",
        "adapterContract",
        "adapterId",
        "candidateFramework",
        "targetRefHash",
        "stage",
        "status",
        "eventCount",
        "componentIds",
        "blockerIds",
        "failureCodes",
        "metrics",
        "traceHash",
    }
)
_SAFE_TRACE_METRIC = re.compile(r"^[A-Za-z][A-Za-z0-9]*(?:Count|Ms|Bytes|Tokens)$")
_FORBIDDEN_TRACE_TEXT_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\braw\s+guide\s+body\b",
        r"\braw\s+provider\s+response\b",
        r"\braw\s+prompt\b",
        r"\braw\s+sp\s+definition\b",
        r"\brow\s+data\b",
        r"\bprocedure\s+execution\b",
        r"\bexecute\s+(?:stored\s+)?procedure\b",
        r"\bddl\s*/?\s*dml\s+apply\b",
        r"\bapply\s+business\s+db\s+(?:ddl|dml)\b",
        r"\bsource\s+apply\b",
        r"\bgenerated\s+source\s+apply\b",
        r"\bdeploy(?:ed|ment)?\b",
        r"\bpublic\s+(?:class|interface)\s+\w+",
        r"<\s*/?\s*mapper\b",
    )
)


@dataclass(frozen=True)
class AiGenerationFrameworkAdapterRequest:
    target_ref: str
    sanitized_draft_context: Mapping[str, Any]
    expected_inventory: Sequence[Mapping[str, Any]]
    quality_gates: Mapping[str, Any]
    allowed_evidence_refs: Sequence[str]
    prompt: RenderedPrompt
    profile: ModelProfile
    stage: str
    repair_context: Mapping[str, Any] | None = None


class AiGenerationFrameworkAdapter(Protocol):
    adapter_id: str
    candidate_framework: str

    def plan_file_inventory(
        self,
        *,
        request: AiGenerationFrameworkAdapterRequest,
    ) -> ModelInvocationRecord:
        ...

    def draft_file_content(
        self,
        *,
        request: AiGenerationFrameworkAdapterRequest,
    ) -> ModelInvocationRecord:
        ...

    def repair_draft_pack(
        self,
        *,
        request: AiGenerationFrameworkAdapterRequest,
    ) -> ModelInvocationRecord:
        ...

    def summarize_trace(
        self,
        *,
        request: AiGenerationFrameworkAdapterRequest,
        stage: str,
        status: str,
        events: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        ...


@dataclass(frozen=True)
class BaselineResponsesFrameworkAdapter:
    model_gateway: ModelGateway
    adapter_id: str = "baseline_internal_responses_gateway"
    candidate_framework: str = "baseline_internal_responses_gateway"

    def plan_file_inventory(
        self,
        *,
        request: AiGenerationFrameworkAdapterRequest,
    ) -> ModelInvocationRecord:
        validate_framework_tool_context(request)
        return self._invoke_gateway(request=request, stage="file_inventory")

    def draft_file_content(
        self,
        *,
        request: AiGenerationFrameworkAdapterRequest,
    ) -> ModelInvocationRecord:
        validate_framework_tool_context(request)
        return self._invoke_gateway(request=request, stage="file_content")

    def repair_draft_pack(
        self,
        *,
        request: AiGenerationFrameworkAdapterRequest,
    ) -> ModelInvocationRecord:
        validate_framework_tool_context(request)
        return self._invoke_gateway(request=request, stage="repair")

    def summarize_trace(
        self,
        *,
        request: AiGenerationFrameworkAdapterRequest,
        stage: str,
        status: str,
        events: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        return summarize_framework_trace(
            adapter_id=self.adapter_id,
            candidate_framework=self.candidate_framework,
            target_ref=request.target_ref,
            stage=stage,
            status=status,
            events=events,
        )

    def _invoke_gateway(
        self,
        *,
        request: AiGenerationFrameworkAdapterRequest,
        stage: str,
    ) -> ModelInvocationRecord:
        invocation = self.model_gateway.draft_ai_java_mybatis_pack(
            prompt=request.prompt,
            profile=request.profile,
        )
        component = self.summarize_trace(
            request=request,
            stage=stage,
            status=invocation.status.value,
            events=(
                {
                    "eventType": "baseline_gateway_call",
                    "outputHash": invocation.output_hash,
                    "fileCount": len(invocation.structured_output.get("files", []))
                    if isinstance(invocation.structured_output, Mapping)
                    else 0,
                },
            ),
        )
        return dataclass_replace(
            invocation,
            component_invocations=(*invocation.component_invocations, component),
        )


@dataclass(frozen=True)
class FakeAiGenerationFrameworkAdapter:
    output: Mapping[str, Any] | None = None
    stage_outputs: Mapping[str, Mapping[str, Any]] = field(default_factory=dict)
    candidate_framework: str = "openai_agents_sdk_fake"
    adapter_id: str | None = None
    trace_events: Sequence[Mapping[str, Any]] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if self.adapter_id is None:
            object.__setattr__(self, "adapter_id", self.candidate_framework)

    def plan_file_inventory(
        self,
        *,
        request: AiGenerationFrameworkAdapterRequest,
    ) -> ModelInvocationRecord:
        validate_framework_tool_context(request)
        return self._build_invocation(request=request, stage="file_inventory")

    def draft_file_content(
        self,
        *,
        request: AiGenerationFrameworkAdapterRequest,
    ) -> ModelInvocationRecord:
        validate_framework_tool_context(request)
        return self._build_invocation(request=request, stage="file_content")

    def repair_draft_pack(
        self,
        *,
        request: AiGenerationFrameworkAdapterRequest,
    ) -> ModelInvocationRecord:
        validate_framework_tool_context(request)
        return self._build_invocation(request=request, stage="repair")

    def summarize_trace(
        self,
        *,
        request: AiGenerationFrameworkAdapterRequest,
        stage: str,
        status: str,
        events: Sequence[Mapping[str, Any]],
    ) -> dict[str, Any]:
        return summarize_framework_trace(
            adapter_id=str(self.adapter_id),
            candidate_framework=self.candidate_framework,
            target_ref=request.target_ref,
            stage=stage,
            status=status,
            events=events,
        )

    def _build_invocation(
        self,
        *,
        request: AiGenerationFrameworkAdapterRequest,
        stage: str,
    ) -> ModelInvocationRecord:
        structured_output = dict(
            self.stage_outputs.get(stage)
            or self.output
            or {
                "schemaVersion": "AiJavaMyBatisDraftPack.v0.1",
                "contractTarget": "AiJavaMyBatisDraftPack",
                "targetRef": request.target_ref,
                "sourcePolicy": "sanitized_facts_only",
                "productionReady": False,
                "files": [],
                "evidenceRefs": list(request.allowed_evidence_refs),
                "reviewMarkers": list(request.quality_gates.get("requiredReviewMarkers", [])),
                "qualityGates": dict(request.quality_gates),
                "assumptions": [],
            }
        )
        component = self.summarize_trace(
            request=request,
            stage=stage,
            status=AgentRunStatus.SUCCEEDED.value,
            events=(
                *self.trace_events,
                {
                    "eventType": "fake_framework_adapter_call",
                    "candidateFramework": self.candidate_framework,
                    "stage": stage,
                    "outputHash": stable_json_hash(structured_output),
                    "fileCount": len(structured_output.get("files", []))
                    if isinstance(structured_output.get("files"), Sequence)
                    else 0,
                },
            ),
        )
        return ModelInvocationRecord(
            provider=f"fake-framework-adapter:{self.candidate_framework}",
            model=request.profile.model,
            model_profile_id=request.profile.profile_id,
            model_registry_ref=request.profile.registry_ref,
            reasoning_effort=request.profile.reasoning_effort,
            prompt_version=request.prompt.prompt_version,
            output_schema_version=request.prompt.output_schema_version,
            input_hash=request.prompt.input_hash,
            prompt_hash=request.prompt.prompt_hash,
            output_hash=stable_json_hash(structured_output),
            status=AgentRunStatus.SUCCEEDED,
            structured_output=structured_output,
            token_usage={"inputTokens": 0, "outputTokens": 0, "totalTokens": 0},
            latency_ms=0,
            provider_request_id=None,
            component_invocations=(component,),
        )


def summarize_framework_trace(
    *,
    adapter_id: str,
    candidate_framework: str,
    target_ref: str,
    stage: str,
    status: str,
    events: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    findings = _trace_storage_findings(events)
    if findings:
        raise ModelGatewayError(
            "Framework adapter trace contains forbidden storage material.",
            code=P43_FRAMEWORK_RAW_TRACE_BLOCKED,
            provider_error={
                "type": "framework_adapter_trace_policy",
                "code": P43_FRAMEWORK_RAW_TRACE_BLOCKED,
                "stage": _safe_stage(stage),
                "findingCount": str(len(findings)),
                "findings": ",".join(findings[:8]),
            },
        )
    summary = {
        "component": _ADAPTER_COMPONENT,
        "adapterContract": AI_GENERATION_FRAMEWORK_ADAPTER_VERSION,
        "adapterId": adapter_id,
        "candidateFramework": candidate_framework,
        "targetRefHash": stable_json_hash({"targetRef": target_ref}),
        "stage": stage,
        "status": status,
        "eventCount": len(events),
        "componentIds": _trace_component_ids(events),
        "blockerIds": _trace_blocker_ids(events),
        "failureCodes": _trace_failure_codes(events),
        "metrics": _trace_numeric_metrics(events),
        "traceHash": stable_json_hash(list(events)),
    }
    validate_framework_trace_summary(summary)
    return summary


def build_framework_tool_context(
    request: AiGenerationFrameworkAdapterRequest,
) -> dict[str, Any]:
    context = request.sanitized_draft_context
    operation_model_summary = _mapping(context.get("operationModelSummary"))
    operations = _sequence_of_mappings(context.get("operations"))
    dto_blueprints = _sequence_of_mappings(context.get("dtoBlueprints"))
    statement_evidence = _sequence_of_mappings(context.get("statementEvidence"))
    review_markers = _dedupe_strings(
        [
            *_sequence(operation_model_summary.get("reviewMarkers")),
            *_sequence(context.get("reviewRequiredFacts")),
            *_sequence(request.quality_gates.get("requiredReviewMarkers")),
            *_sequence((request.repair_context or {}).get("reviewMarkers")),
        ]
    )
    return {
        "adapterContract": AI_GENERATION_FRAMEWORK_ADAPTER_VERSION,
        "stage": request.stage,
        "targetRefHash": stable_json_hash({"targetRef": request.target_ref}),
        "metadataSummary": {
            "inputParamCount": len(_sequence(context.get("inputParams"))),
            "resultShapeCount": len(_sequence(context.get("resultShape"))),
            "allowedEvidenceRefCount": len(request.allowed_evidence_refs),
            "dependencyEvidenceRefCount": len(
                _sequence(_mapping(context.get("dependencyEvidenceSummary")).get("evidenceRefs"))
            ),
            "aiToolEvidenceRefCount": len(
                _sequence(_mapping(context.get("aiToolEvidenceSummary")).get("evidenceRefs"))
            ),
            "platformToolEvidenceRefCount": len(
                _sequence(
                    _mapping(context.get("platformToolEvidenceSummary")).get("evidenceRefs")
                )
            ),
        },
        "operationSummary": {
            "schemaVersion": operation_model_summary.get("schemaVersion"),
            "operationCount": len(operations),
            "operationIds": _ids_from_items(operations, "operationId"),
            "statementEvidenceCount": len(statement_evidence),
            "statementIds": _ids_from_items(statement_evidence, "statementId"),
            "statementOperations": _ids_from_items(statement_evidence, "operation"),
            "dtoBlueprintCount": len(dto_blueprints),
            "dtoBlueprintNames": _ids_from_items(dto_blueprints, "name"),
            "reviewMarkers": review_markers,
        },
        "deterministicInventoryContract": [
            _framework_inventory_item(item) for item in request.expected_inventory
        ],
        "allowedEvidenceRefs": list(dict.fromkeys(map(str, request.allowed_evidence_refs))),
        "qualityGates": _policy_safe_mapping(request.quality_gates),
        "reviewRequiredMarkers": review_markers,
    }


def validate_framework_tool_context(
    request: AiGenerationFrameworkAdapterRequest,
) -> dict[str, Any]:
    raw_inputs: list[Mapping[str, Any]] = [
        {"sanitizedDraftContext": dict(request.sanitized_draft_context)},
        {"expectedInventory": [dict(item) for item in request.expected_inventory]},
        {"qualityGates": dict(request.quality_gates)},
        {"allowedEvidenceRefs": list(request.allowed_evidence_refs)},
    ]
    if request.repair_context is not None:
        raw_inputs.append({"repairContext": dict(request.repair_context)})
    findings = _policy_findings(raw_inputs)
    context = build_framework_tool_context(request)
    findings.extend(_policy_findings((context,)))
    if findings:
        raise ModelGatewayError(
            "Framework adapter tool context contains forbidden material.",
            code=P43_FRAMEWORK_TOOL_CONTEXT_BLOCKED,
            provider_error={
                "type": "framework_adapter_tool_context_policy",
                "code": P43_FRAMEWORK_TOOL_CONTEXT_BLOCKED,
                "stage": _safe_stage(request.stage),
                "findingCount": str(len(findings)),
                "findings": ",".join(findings[:8]),
            },
        )
    return context


def validate_framework_trace_summary(summary: Mapping[str, Any]) -> dict[str, Any]:
    findings: list[str] = []
    extra = sorted(set(map(str, summary)) - _TRACE_SUMMARY_FIELDS)
    if extra:
        findings.append("P43_FRAMEWORK_TRACE_SUMMARY_FIELD_NOT_ALLOWED")
    if summary.get("component") != _ADAPTER_COMPONENT:
        findings.append("P43_FRAMEWORK_TRACE_SUMMARY_COMPONENT_INVALID")
    if summary.get("adapterContract") != AI_GENERATION_FRAMEWORK_ADAPTER_VERSION:
        findings.append("P43_FRAMEWORK_TRACE_SUMMARY_CONTRACT_INVALID")
    if str(summary.get("stage") or "") not in _FRAMEWORK_STAGES:
        findings.append("P43_FRAMEWORK_TRACE_SUMMARY_STAGE_INVALID")
    for key in ("adapterId", "candidateFramework", "targetRefHash", "status", "traceHash"):
        if not str(summary.get(key) or "").strip():
            findings.append(f"P43_FRAMEWORK_TRACE_SUMMARY_{key}_MISSING")
    if not isinstance(summary.get("eventCount"), int) or isinstance(
        summary.get("eventCount"),
        bool,
    ):
        findings.append("P43_FRAMEWORK_TRACE_SUMMARY_EVENT_COUNT_INVALID")
    for key in ("componentIds", "blockerIds", "failureCodes"):
        value = summary.get(key, [])
        if not isinstance(value, Sequence) or isinstance(value, str | bytes):
            findings.append(f"P43_FRAMEWORK_TRACE_SUMMARY_{key}_INVALID")
        elif not all(isinstance(item, str) for item in value):
            findings.append(f"P43_FRAMEWORK_TRACE_SUMMARY_{key}_INVALID")
    metrics = summary.get("metrics", {})
    if not isinstance(metrics, Mapping):
        findings.append("P43_FRAMEWORK_TRACE_SUMMARY_METRICS_INVALID")
    else:
        for key, value in metrics.items():
            if not _SAFE_TRACE_METRIC.fullmatch(str(key)):
                findings.append("P43_FRAMEWORK_TRACE_SUMMARY_METRIC_KEY_INVALID")
            if isinstance(value, bool) or not isinstance(value, int | float):
                findings.append("P43_FRAMEWORK_TRACE_SUMMARY_METRIC_VALUE_INVALID")
    findings.extend(_policy_findings((dict(summary),)))
    if findings:
        raise ModelGatewayError(
            "Framework adapter trace summary contains forbidden storage material.",
            code=P43_FRAMEWORK_RAW_TRACE_BLOCKED,
            provider_error={
                "type": "framework_adapter_trace_summary_policy",
                "code": P43_FRAMEWORK_RAW_TRACE_BLOCKED,
                "stage": _safe_stage(summary.get("stage")),
                "findingCount": str(len(findings)),
                "findings": ",".join(list(dict.fromkeys(findings))[:8]),
            },
        )
    return dict(summary)


def _trace_storage_findings(events: Sequence[Mapping[str, Any]]) -> list[str]:
    return _policy_findings(events)


def _policy_findings(payloads: Sequence[Mapping[str, Any]]) -> list[str]:
    findings = [finding["code"] for finding in storage_safety_findings(payloads=payloads)]
    for text in _iter_trace_text(payloads):
        if any(pattern.search(text) for pattern in _FORBIDDEN_TRACE_TEXT_PATTERNS):
            findings.append("FORBIDDEN_FRAMEWORK_POLICY_TEXT_PRESENT")
    return list(dict.fromkeys(findings))


def _framework_inventory_item(item: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "artifactType": str(item.get("artifactType") or ""),
        "path": str(item.get("path") or ""),
        "role": str(item.get("role") or ""),
        "className": str(item.get("className") or ""),
        "operationIds": _dedupe_strings(item.get("operationIds", [])),
        "dtoRole": str(item.get("dtoRole") or ""),
        "requiredFields": _dedupe_strings(item.get("requiredFields", [])),
        "references": _dedupe_strings(item.get("references", [])),
        "evidenceRefs": _dedupe_strings(item.get("evidenceRefs", [])),
        "reviewMarkers": _dedupe_strings(item.get("reviewMarkers", [])),
    }


def _policy_safe_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return {
        str(key): _policy_safe_value(item)
        for key, item in value.items()
        if isinstance(item, str | int | float | bool)
        or (
            isinstance(item, Sequence)
            and not isinstance(item, str | bytes)
            and all(isinstance(seq_item, str | int | float | bool) for seq_item in item)
        )
    }


def _policy_safe_value(value: Any) -> Any:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return list(value)
    return value


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    return value if isinstance(value, Sequence) and not isinstance(value, str | bytes) else ()


def _sequence_of_mappings(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in _sequence(value) if isinstance(item, Mapping)]


def _ids_from_items(items: Sequence[Mapping[str, Any]], key: str) -> list[str]:
    return _dedupe_strings([item.get(key) for item in items])


def _dedupe_strings(items: Any) -> list[str]:
    values = items if isinstance(items, Sequence) and not isinstance(items, str | bytes) else ()
    return list(
        dict.fromkeys(str(item) for item in values if item is not None and str(item).strip())
    )


def _safe_stage(value: Any) -> str:
    stage = str(value or "")
    return stage if stage in _FRAMEWORK_STAGES else "unknown"


def _iter_trace_text(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Mapping):
        text: list[str] = []
        for key, item in value.items():
            text.append(str(key))
            text.extend(_iter_trace_text(item))
        return text
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        text = []
        for item in value:
            text.extend(_iter_trace_text(item))
        return text
    return []


def _trace_blocker_ids(events: Sequence[Mapping[str, Any]]) -> list[str]:
    blockers: list[str] = []
    for event in events:
        if not isinstance(event, Mapping):
            continue
        blocker_id = event.get("blockerId")
        if blocker_id:
            blockers.append(str(blocker_id))
        for item in event.get("blockerIds", []):
            if str(item).strip():
                blockers.append(str(item))
    return list(dict.fromkeys(blockers))


def _trace_component_ids(events: Sequence[Mapping[str, Any]]) -> list[str]:
    component_ids = []
    for event in events:
        if not isinstance(event, Mapping):
            continue
        component_id = event.get("componentId")
        if component_id:
            component_ids.append(str(component_id))
    return list(dict.fromkeys(component_ids))


def _trace_failure_codes(events: Sequence[Mapping[str, Any]]) -> list[str]:
    codes = []
    for event in events:
        if not isinstance(event, Mapping):
            continue
        for key in ("failureCode", "errorCode"):
            code = event.get(key)
            if code:
                codes.append(str(code))
    return list(dict.fromkeys(codes))


def _trace_numeric_metrics(events: Sequence[Mapping[str, Any]]) -> dict[str, int | float]:
    metrics: dict[str, int | float] = {}
    for event in events:
        if not isinstance(event, Mapping):
            continue
        for key, value in event.items():
            if (
                _SAFE_TRACE_METRIC.fullmatch(str(key))
                and isinstance(value, int | float)
                and not isinstance(value, bool)
            ):
                metrics[str(key)] = value
    return metrics
