from __future__ import annotations

import os
import time
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from ai_agent_runtime.gateway import ModelGateway, ModelGatewayError, model_profile_from_env
from ai_agent_runtime.models import AiToolPlanningOutput, stable_json_hash
from ai_agent_runtime.planner_effectiveness import (
    attach_planner_metrics_to_ai_tool_evidence,
)
from ai_agent_runtime.prompts import render_platform_tool_planning_prompt

from api_app.metadata_gateway import MetadataCollectionResult
from api_app.platform_tool_registry import (
    PlatformToolDecision,
    PlatformToolError,
    PlatformToolPolicy,
    PlatformToolRegistry,
    load_platform_tool_catalog,
    platform_tool_capabilities,
)
from api_app.repositories import WorkflowRepository, WorkRequestRecord

MAX_PLATFORM_TOOL_CALLS = 3
REVIEW_STATUS = "REVIEW_REQUIRED"
SKIPPED_STATUS = "SKIPPED"
SUCCEEDED_STATUS = "SUCCEEDED"
PLATFORM_TOOL_PLANNER_DETERMINISTIC_FALLBACK = (
    "PLATFORM_TOOL_PLANNER_DETERMINISTIC_FALLBACK"
)


@dataclass(frozen=True)
class PlatformToolOrchestrationResult:
    metadata: MetadataCollectionResult
    component_invocations: tuple[dict[str, Any], ...]


class PlatformToolOrchestrator:
    def __init__(
        self,
        *,
        model_gateway: ModelGateway,
        repository: WorkflowRepository,
        max_tool_calls: int | None = None,
    ) -> None:
        self.model_gateway = model_gateway
        self.repository = repository
        self.max_tool_calls = (
            max_tool_calls if max_tool_calls is not None else _platform_tool_max_calls()
        )

    def run(
        self,
        *,
        job_id: str,
        request_record: WorkRequestRecord,
        metadata: MetadataCollectionResult,
        static_analysis: dict[str, Any] | None,
    ) -> PlatformToolOrchestrationResult:
        if not _orchestration_enabled(request_record.options):
            return PlatformToolOrchestrationResult(
                metadata=metadata,
                component_invocations=(),
            )

        max_tool_calls = max(self.max_tool_calls, 0)
        if max_tool_calls <= 0:
            marker = _review_marker(
                "PLATFORM_TOOL_CALL_BUDGET_EXHAUSTED",
                "planning 실행 전에 platform tool call budget을 소진했습니다.",
                evidence_refs=_fallback_evidence_refs(metadata, []),
            )
            return PlatformToolOrchestrationResult(
                metadata=_metadata_with_platform_tool_evidence(
                    metadata,
                    status=REVIEW_STATUS,
                    tool_results=[],
                    deterministic_facts=[],
                    review_markers=[marker],
                    caveats=["PLATFORM_TOOL_CALL_BUDGET_EXHAUSTED"],
                    blocked_requests=[],
                    component_invocations=[],
                    planned_request_count=0,
                    failed_tool_call_count=0,
                    deduped_request_count=0,
                    budget_exhausted=True,
                ),
                component_invocations=(),
            )

        planner = getattr(self.model_gateway, "plan_platform_tools", None)
        if not callable(planner):
            marker = _review_marker(
                "PLATFORM_TOOL_ORCHESTRATION_SKIPPED",
                "설정된 model gateway가 platform tool planning을 제공하지 않습니다.",
                evidence_refs=_fallback_evidence_refs(metadata, []),
            )
            return PlatformToolOrchestrationResult(
                metadata=_metadata_with_platform_tool_evidence(
                    metadata,
                    status=SKIPPED_STATUS,
                    tool_results=[],
                    deterministic_facts=[],
                    review_markers=[marker],
                    caveats=["PLATFORM_TOOL_ORCHESTRATION_SKIPPED"],
                    blocked_requests=[],
                    component_invocations=[],
                ),
                component_invocations=(),
            )

        tools = load_platform_tool_catalog()
        policy = PlatformToolPolicy(
            tools=tools,
            request_record=request_record,
            job_id=job_id,
        )
        registry = PlatformToolRegistry(
            repository=self.repository,
            request_record=request_record,
            job_id=job_id,
        )
        profile = model_profile_from_env(str(request_record.options.get("llmProfileId") or ""))
        target_ref = _target_ref(request_record)
        component_invocations: list[dict[str, Any]] = []
        tool_results: list[dict[str, Any]] = []
        deterministic_facts: list[dict[str, Any]] = []
        review_markers: list[dict[str, Any]] = []
        blocked_requests: list[dict[str, Any]] = []
        caveats: list[str] = []
        seen_requests: set[tuple[str, str]] = set()
        planned_request_count = 0
        deduped_request_count = 0
        failed_tool_call_count = 0
        budget_exhausted = False

        prompt = render_platform_tool_planning_prompt(
            target_ref=target_ref,
            metadata=metadata.as_dict(),
            static_analysis=static_analysis,
            tool_capabilities=platform_tool_capabilities(tools),
            job_context=_job_context(job_id, request_record),
            max_tool_calls=max_tool_calls,
        )
        try:
            invocation = planner(prompt=prompt, profile=profile)
            plan = AiToolPlanningOutput.model_validate(invocation.structured_output)
        except (ModelGatewayError, ValueError) as exc:
            fallback_requests = _deterministic_fallback_tool_requests(
                max_tool_calls=max_tool_calls,
                tool_names=policy.tool_names,
            )
            component_invocations.append(
                {
                    "stage": "platform_tool_planning",
                    "toolName": "platform_tool_planner",
                    "status": REVIEW_STATUS,
                    "latencyMs": 0,
                    "evidenceCount": 0,
                    "toolRequestCount": len(fallback_requests),
                    "errorCode": getattr(exc, "code", exc.__class__.__name__),
                }
            )
            plan = _fallback_tool_plan(
                fallback_requests,
                evidence_refs=_fallback_evidence_refs(metadata, deterministic_facts),
                detail_code=getattr(exc, "code", exc.__class__.__name__),
            )
            caveats.append(PLATFORM_TOOL_PLANNER_DETERMINISTIC_FALLBACK)
        else:
            component_invocations.append(
                {
                    "stage": "platform_tool_planning",
                    "toolName": "platform_tool_planner",
                    "status": invocation.status.value,
                    "inputHash": invocation.input_hash,
                    "promptHash": invocation.prompt_hash,
                    "outputHash": invocation.output_hash,
                    "latencyMs": invocation.latency_ms,
                    "evidenceCount": 0,
                    "toolRequestCount": len(plan.tool_requests),
                }
            )
            if not plan.tool_requests:
                fallback_requests = _deterministic_fallback_tool_requests(
                    max_tool_calls=max_tool_calls,
                    tool_names=policy.tool_names,
                )
                plan = _fallback_tool_plan(
                    fallback_requests,
                    evidence_refs=_fallback_evidence_refs(metadata, deterministic_facts),
                    detail_code="EMPTY_PLATFORM_TOOL_PLAN",
                )
                caveats.append(PLATFORM_TOOL_PLANNER_DETERMINISTIC_FALLBACK)

        planned_request_count += len(plan.tool_requests)
        for marker in plan.review_markers:
            marker_payload = marker.model_dump(by_alias=True, mode="json")
            if not marker_payload.get("evidenceRefs"):
                marker_payload["evidenceRefs"] = _fallback_evidence_refs(
                    metadata,
                    deterministic_facts,
                )
            review_markers.append(marker_payload)

        for request in plan.tool_requests:
            if len(tool_results) >= max_tool_calls:
                caveats.append("PLATFORM_TOOL_CALL_BUDGET_EXHAUSTED")
                budget_exhausted = True
                review_markers.append(
                    _review_marker(
                        "PLATFORM_TOOL_CALL_BUDGET_EXHAUSTED",
                        "계획된 요청을 모두 실행하기 전에 platform tool call budget을 소진했습니다.",
                        evidence_refs=_fallback_evidence_refs(metadata, deterministic_facts),
                    )
                )
                break
            decision = policy.decide(
                tool_name=request.tool_name,
                arguments=request.arguments,
            )
            request_key = (decision.tool_name, stable_json_hash(decision.arguments))
            if request_key in seen_requests:
                deduped_request_count += 1
                continue
            seen_requests.add(request_key)
            if not decision.allowed:
                blocked = _blocked_request(decision)
                blocked_requests.append(blocked)
                review_markers.append(
                    _review_marker(
                        "PLATFORM_TOOL_ORCHESTRATION_REVIEW_REQUIRED",
                        str(decision.message or "Platform tool request가 차단되었습니다."),
                        evidence_refs=_fallback_evidence_refs(metadata, deterministic_facts),
                    )
                )
                caveats.append(str(decision.code or "PLATFORM_TOOL_REQUEST_BLOCKED"))
                component_invocations.append(
                    _tool_component(
                        tool_name=decision.tool_name,
                        arguments=decision.arguments,
                        status=REVIEW_STATUS,
                        output_hash=None,
                        latency_ms=0,
                        evidence_count=0,
                        error_code=decision.code,
                    )
                )
                continue

            started = time.monotonic()
            try:
                payload = registry.invoke_payload(
                    decision.tool_name,
                    {"arguments": decision.arguments},
                )
            except PlatformToolError as exc:
                failed_tool_call_count += 1
                review_markers.append(
                    _review_marker(
                        "PLATFORM_TOOL_ORCHESTRATION_REVIEW_REQUIRED",
                        f"Platform tool invocation이 실패했습니다: {exc.code}.",
                        evidence_refs=_fallback_evidence_refs(metadata, deterministic_facts),
                    )
                )
                caveats.append(exc.code)
                component_invocations.append(
                    _tool_component(
                        tool_name=decision.tool_name,
                        arguments=decision.arguments,
                        status=REVIEW_STATUS,
                        output_hash=None,
                        latency_ms=int((time.monotonic() - started) * 1000),
                        evidence_count=0,
                        error_code=exc.code,
                    )
                )
                continue

            argument_hash = stable_json_hash(decision.arguments)
            content_hash = _tool_content_hash(
                decision.tool_name,
                payload,
                argument_hash=argument_hash,
            )
            fact = _deterministic_fact(
                decision.tool_name,
                payload,
                argument_hash=argument_hash,
                content_hash=content_hash,
            )
            output_hash = stable_json_hash(payload)
            deterministic_facts.append(fact)
            tool_results.append(
                {
                    "toolName": decision.tool_name,
                    "factId": fact["id"],
                    "evidenceRefs": _safe_dict_list(payload.get("evidenceRefs")),
                    "data": _safe_dict(payload.get("data")),
                    "argumentHash": argument_hash,
                    "contentHash": content_hash,
                    "outputHash": output_hash,
                }
            )
            component_invocations.append(
                _tool_component(
                    tool_name=decision.tool_name,
                    arguments=decision.arguments,
                    status=SUCCEEDED_STATUS,
                    output_hash=output_hash,
                    latency_ms=int((time.monotonic() - started) * 1000),
                    evidence_count=len(_safe_dict_list(payload.get("evidenceRefs"))),
                    error_code=None,
                )
            )

        status = _platform_tool_evidence_status(
            tool_results=tool_results,
            review_markers=review_markers,
            caveats=caveats,
            blocked_requests=blocked_requests,
            failed_tool_call_count=failed_tool_call_count,
            budget_exhausted=budget_exhausted,
        )
        enriched = _metadata_with_platform_tool_evidence(
            metadata,
            status=status,
            tool_results=tool_results,
            deterministic_facts=deterministic_facts,
            review_markers=review_markers,
            caveats=caveats,
            blocked_requests=blocked_requests,
            component_invocations=component_invocations,
            planned_request_count=planned_request_count,
            failed_tool_call_count=failed_tool_call_count,
            deduped_request_count=deduped_request_count,
            budget_exhausted=budget_exhausted,
        )
        return PlatformToolOrchestrationResult(
            metadata=enriched,
            component_invocations=tuple(component_invocations),
        )


def _platform_tool_max_calls() -> int:
    value = os.getenv("PLATFORM_TOOL_MAX_CALLS")
    if value is None or not value.strip():
        return MAX_PLATFORM_TOOL_CALLS
    try:
        return int(value)
    except ValueError:
        return MAX_PLATFORM_TOOL_CALLS


def _orchestration_enabled(options: Mapping[str, Any]) -> bool:
    use_llm = bool(options.get("useLlmAnalysis", True))
    use_tools = bool(options.get("usePlatformToolOrchestration", True))
    return use_llm and use_tools


def _target_ref(request_record: WorkRequestRecord) -> str:
    target = request_record.target
    return f"{target['schema']}.{target['name']}"


def _job_context(job_id: str, request_record: WorkRequestRecord) -> dict[str, str]:
    target = request_record.target
    return {
        "jobId": job_id,
        "dbProfileId": request_record.db_profile_id,
        "targetType": str(target.get("type") or ""),
        "targetRef": _target_ref(request_record),
        "scopeRule": "current job, db profile, and target only",
    }


def _deterministic_fallback_tool_requests(
    *,
    max_tool_calls: int,
    tool_names: set[str],
) -> list[dict[str, Any]]:
    if max_tool_calls <= 0 or "platform.list_registry_versions" not in tool_names:
        return []
    return [
        {
            "toolName": "platform.list_registry_versions",
            "arguments": {},
            "reason": "fallback에는 재현성을 위한 registry version 근거가 필요합니다.",
            "expectedEvidenceUse": (
                "prompt, schema, model, generator, policy, template version claim의 근거로 사용합니다."
            ),
        }
    ][:max_tool_calls]


def _fallback_tool_plan(
    tool_requests: list[dict[str, Any]],
    *,
    evidence_refs: list[str],
    detail_code: str,
) -> AiToolPlanningOutput:
    return AiToolPlanningOutput.model_validate(
        {
            "toolRequests": tool_requests,
            "assumptions": [
                (
                    "platform tool planner가 invalid 또는 empty 상태라 결정론적 read-only "
                    "platform context request를 사용했습니다."
                )
            ],
            "reviewMarkers": [
                _review_marker(
                    PLATFORM_TOOL_PLANNER_DETERMINISTIC_FALLBACK,
                    (
                        "Platform tool planner output이 invalid 또는 empty 상태라 결정론적 "
                        f"read-only fallback tool request를 사용했습니다. code={detail_code}"
                    ),
                    evidence_refs=evidence_refs,
                )
            ],
        }
    )


def _metadata_with_platform_tool_evidence(
    metadata: MetadataCollectionResult,
    *,
    status: str,
    tool_results: list[dict[str, Any]],
    deterministic_facts: list[dict[str, Any]],
    review_markers: list[dict[str, Any]],
    caveats: list[str],
    blocked_requests: list[dict[str, Any]],
    component_invocations: list[dict[str, Any]],
    planned_request_count: int | None = None,
    failed_tool_call_count: int | None = None,
    deduped_request_count: int | None = None,
    budget_exhausted: bool | None = None,
) -> MetadataCollectionResult:
    evidence = {
        "status": status,
        "toolCallCount": len(tool_results),
        "toolResults": tool_results,
        "blockedRequests": blocked_requests,
        "reviewMarkers": _dedupe_markers(review_markers),
        "caveats": _dedupe_strings(caveats),
    }
    evidence = attach_planner_metrics_to_ai_tool_evidence(
        evidence,
        deterministic_facts=deterministic_facts,
        component_invocations=component_invocations,
        planned_request_count=planned_request_count,
        failed_tool_call_count=failed_tool_call_count,
        deduped_request_count=deduped_request_count,
        budget_exhausted=budget_exhausted,
    )
    return replace(
        metadata,
        platform_tool_evidence=evidence,
        deterministic_facts=tuple([*metadata.deterministic_facts, *deterministic_facts]),
        notes=tuple(
            _dedupe_strings(
                [
                    *metadata.notes,
                    "Platform tool orchestration은 internal read-only platform registry를 사용했습니다.",
                ]
            )
        ),
    )


def _tool_content_hash(
    tool_name: str,
    payload: Mapping[str, Any],
    *,
    argument_hash: str,
) -> str:
    return stable_json_hash(
        {
            "toolName": tool_name,
            "argumentHash": argument_hash,
            "content": payload.get("data", {}),
        }
    )


def _deterministic_fact(
    tool_name: str,
    payload: Mapping[str, Any],
    *,
    argument_hash: str,
    content_hash: str,
) -> dict[str, Any]:
    fact_hash = content_hash[:12]
    return {
        "id": f"platform.{tool_name.removeprefix('platform.')}.{fact_hash}",
        "type": "PLATFORM_TOOL_EVIDENCE",
        "fact_type": "PLATFORM_TOOL_EVIDENCE",
        "toolName": tool_name,
        "contentHash": content_hash,
        "summary": _fact_summary(tool_name, payload),
        "evidenceRefs": _safe_dict_list(payload.get("evidenceRefs")),
    }


def _fact_summary(tool_name: str, payload: Mapping[str, Any]) -> str:
    data = _safe_dict(payload.get("data"))
    if tool_name == "platform.search_knowledge_facts":
        return f"Platform knowledge fact search가 fact {data.get('resultCount', 0)}개를 반환했습니다."
    if tool_name == "platform.list_knowledge_assets":
        return f"Platform knowledge asset listing이 asset {data.get('resultCount', 0)}개를 반환했습니다."
    if tool_name == "platform.get_knowledge_version_graph":
        facts = data.get("facts") if isinstance(data.get("facts"), list) else []
        edges = data.get("edges") if isinstance(data.get("edges"), list) else []
        return f"Platform knowledge graph가 fact {len(facts)}개와 edge {len(edges)}개를 반환했습니다."
    if tool_name == "platform.list_job_artifacts":
        return f"현재 job artifact listing이 artifact {data.get('resultCount', 0)}개를 반환했습니다."
    if tool_name == "platform.get_latest_validation_report":
        return f"최신 validation report status는 {data.get('status', 'UNKNOWN')}입니다."
    if tool_name == "platform.list_job_agent_runs":
        return f"현재 job agent run listing이 run {data.get('resultCount', 0)}개를 반환했습니다."
    if tool_name == "platform.list_registry_versions":
        return f"Platform registry version listing이 binding {data.get('resultCount', 0)}개를 반환했습니다."
    return f"{tool_name}이 sanitized read-only platform evidence를 반환했습니다."


def _tool_component(
    *,
    tool_name: str,
    arguments: Mapping[str, Any],
    status: str,
    output_hash: str | None,
    latency_ms: int,
    evidence_count: int,
    error_code: str | None,
) -> dict[str, Any]:
    component = {
        "stage": "platform_tool_execution",
        "toolName": tool_name,
        "argumentHash": stable_json_hash(arguments),
        "status": status,
        "latencyMs": latency_ms,
        "evidenceCount": evidence_count,
    }
    if output_hash:
        component["outputHash"] = output_hash
    if error_code:
        component["errorCode"] = error_code
    return component


def _platform_tool_evidence_status(
    *,
    tool_results: list[dict[str, Any]],
    review_markers: list[dict[str, Any]],
    caveats: list[str],
    blocked_requests: list[dict[str, Any]],
    failed_tool_call_count: int,
    budget_exhausted: bool,
) -> str:
    if (
        review_markers
        or caveats
        or blocked_requests
        or failed_tool_call_count > 0
        or budget_exhausted
    ):
        return REVIEW_STATUS
    if tool_results:
        return SUCCEEDED_STATUS
    return REVIEW_STATUS


def _blocked_request(decision: PlatformToolDecision) -> dict[str, Any]:
    return {
        "toolName": decision.tool_name,
        "argumentHash": stable_json_hash(decision.arguments),
        "code": str(decision.code or "PLATFORM_TOOL_REQUEST_BLOCKED"),
        "message": str(decision.message or "Platform tool request가 차단되었습니다."),
    }


def _review_marker(
    code: str,
    message: str,
    *,
    evidence_refs: list[str],
) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "status": REVIEW_STATUS,
        "evidenceRefs": evidence_refs,
    }


def _fallback_evidence_refs(
    metadata: MetadataCollectionResult,
    deterministic_facts: list[dict[str, Any]],
) -> list[str]:
    if deterministic_facts:
        return [str(deterministic_facts[0]["id"])]
    for ref in metadata.evidence_refs:
        object_ref = str(ref.get("objectRef") or ref.get("object_ref") or "").strip()
        locator = str(ref.get("locator") or "").strip()
        if object_ref or locator:
            return [f"metadata:{object_ref}:{locator}"]
    return [f"metadata:{metadata.object_ref}:request.target"]


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _safe_dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _dedupe_strings(items: list[str] | tuple[str, ...]) -> list[str]:
    return list(dict.fromkeys(str(item) for item in items if str(item)))


def _dedupe_markers(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    markers: dict[str, dict[str, Any]] = {}
    for item in items:
        code = str(item.get("code") or "")
        if not code:
            continue
        if code not in markers:
            markers[code] = dict(item)
            continue
        existing = markers[code]
        existing["evidenceRefs"] = _dedupe_strings(
            [
                *[str(ref) for ref in existing.get("evidenceRefs", [])],
                *[str(ref) for ref in item.get("evidenceRefs", [])],
            ]
        )
    return list(markers.values())
