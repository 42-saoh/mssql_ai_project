from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from dataclasses import replace as dataclass_replace
from typing import Any, Protocol, TypedDict

from ai_agent_validation import (
    ValidationReport,
    ValidationStatus,
    validate_ai_java_mybatis_draft_pack_quality,
)

from ai_agent_runtime.ai_draft_pack import AiDraftPackValidationError
from ai_agent_runtime.ai_draft_pack_planner import (
    AGENT_TYPE,
    _allowed_evidence_refs,
    _build_ai_java_mybatis_draft_pack_run_stage,
    _invoke_ai_java_mybatis_draft_pack_stage,
    _is_repairable_planner_exception,
    _repair_context_from_exception,
    _validate_ai_draft_pack_invocation,
)
from ai_agent_runtime.framework_adapter import (
    AI_GENERATION_FRAMEWORK_ADAPTER_VERSION,
    FRAMEWORK_RUNTIME_SUMMARY_VERSION,
    AiGenerationFrameworkAdapter,
)
from ai_agent_runtime.gateway import ModelGateway, ModelGatewayError, model_profile_from_env
from ai_agent_runtime.models import AgentRunPayload, stable_json_hash

P44_LANGGRAPH_ORCHESTRATOR_FAILED = "P44_LANGGRAPH_ORCHESTRATOR_FAILED"
P44_LANGGRAPH_UNAVAILABLE = "P44_LANGGRAPH_UNAVAILABLE"
LANGGRAPH_AI_DRAFT_PACK_ORCHESTRATOR_COMPONENT = "langgraph_ai_draft_pack_orchestrator"


class AiDraftPackOrchestrator(Protocol):
    def build_run(
        self,
        *,
        target_ref: str,
        sanitized_draft_context: Mapping[str, Any],
        expected_inventory: Sequence[Mapping[str, Any]],
        quality_gates: Mapping[str, Any],
        model_gateway: ModelGateway,
        profile_id: str | None,
        allowed_evidence_refs: Sequence[str] | None = None,
    ) -> AgentRunPayload:
        ...


class _DraftPackGraphState(TypedDict, total=False):
    priorComponents: list[dict[str, Any]]
    runPayload: AgentRunPayload
    repairContext: dict[str, Any]
    repairAttempted: bool
    needsRepair: bool
    stageTrace: list[str]
    qualityStatus: str
    qualityFailedCheckCount: int


@dataclass(frozen=True)
class LangGraphAiDraftPackOrchestrator:
    framework_adapter: AiGenerationFrameworkAdapter

    def build_run(
        self,
        *,
        target_ref: str,
        sanitized_draft_context: Mapping[str, Any],
        expected_inventory: Sequence[Mapping[str, Any]],
        quality_gates: Mapping[str, Any],
        model_gateway: ModelGateway,
        profile_id: str | None,
        allowed_evidence_refs: Sequence[str] | None = None,
    ) -> AgentRunPayload:
        profile = model_profile_from_env(profile_id)
        allowed_refs = _allowed_evidence_refs(
            context=sanitized_draft_context,
            inventory=expected_inventory,
            additional_refs=allowed_evidence_refs,
        )

        def file_inventory_node(state: _DraftPackGraphState) -> _DraftPackGraphState:
            invocation = _invoke_ai_java_mybatis_draft_pack_stage(
                target_ref=target_ref,
                sanitized_draft_context=sanitized_draft_context,
                expected_inventory=expected_inventory,
                quality_gates=quality_gates,
                model_gateway=model_gateway,
                profile=profile,
                allowed_refs=allowed_refs,
                stage="file_inventory",
                repair_context=None,
                framework_adapter=self.framework_adapter,
            )
            _validate_ai_draft_pack_invocation(invocation, stage="file_inventory")
            return {
                "priorComponents": [
                    *state.get("priorComponents", []),
                    *(dict(item) for item in invocation.component_invocations),
                ],
                "stageTrace": [*state.get("stageTrace", []), "file_inventory"],
            }

        def file_content_node(state: _DraftPackGraphState) -> _DraftPackGraphState:
            try:
                run_payload = _build_ai_java_mybatis_draft_pack_run_stage(
                    target_ref=target_ref,
                    sanitized_draft_context=sanitized_draft_context,
                    expected_inventory=expected_inventory,
                    quality_gates=quality_gates,
                    model_gateway=model_gateway,
                    profile=profile,
                    allowed_refs=allowed_refs,
                    stage="file_content",
                    repair_context=None,
                    framework_adapter=self.framework_adapter,
                    prior_component_invocations=state.get("priorComponents", []),
                )
            except (ModelGatewayError, AiDraftPackValidationError) as exc:
                if not _is_repairable_planner_exception(exc):
                    raise
                return {
                    "needsRepair": True,
                    "repairContext": _repair_context_from_exception(exc),
                    "priorComponents": [
                        *state.get("priorComponents", []),
                        _adapter_stage_failure_component(
                            adapter=self.framework_adapter,
                            target_ref=target_ref,
                            stage="file_content",
                            exc=exc,
                        ),
                    ],
                    "stageTrace": [*state.get("stageTrace", []), "file_content"],
                }
            return {
                "runPayload": run_payload,
                "needsRepair": False,
                "stageTrace": [*state.get("stageTrace", []), "file_content"],
            }

        def quality_gate_node(state: _DraftPackGraphState) -> _DraftPackGraphState:
            run_payload = state.get("runPayload")
            if run_payload is None:
                return {
                    "needsRepair": True,
                    "stageTrace": [*state.get("stageTrace", []), "quality_gate"],
                }
            report = validate_ai_java_mybatis_draft_pack_quality(run_payload.structured_output)
            if report.status == ValidationStatus.PASSED:
                return {
                    "needsRepair": False,
                    "qualityStatus": report.status.value,
                    "qualityFailedCheckCount": 0,
                    "stageTrace": [*state.get("stageTrace", []), "quality_gate"],
                }
            if state.get("repairAttempted"):
                return {
                    "needsRepair": False,
                    "qualityStatus": report.status.value,
                    "qualityFailedCheckCount": len(report.failed_checks),
                    "stageTrace": [*state.get("stageTrace", []), "quality_gate"],
                }
            return {
                "needsRepair": True,
                "repairContext": _quality_repair_context(report),
                "qualityStatus": report.status.value,
                "qualityFailedCheckCount": len(report.failed_checks),
                "stageTrace": [*state.get("stageTrace", []), "quality_gate"],
            }

        def repair_node(state: _DraftPackGraphState) -> _DraftPackGraphState:
            repair_context = state.get("repairContext") or {
                "failureStage": "langgraph_repair_required",
                "errorCode": "AI_DRAFT_PACK_REPAIR_REQUIRED",
                "errorClass": "LangGraphState",
                "reason": "LangGraph AI Draft Pack stage requested repair.",
            }
            repaired_payload = _build_ai_java_mybatis_draft_pack_run_stage(
                target_ref=target_ref,
                sanitized_draft_context=sanitized_draft_context,
                expected_inventory=expected_inventory,
                quality_gates=quality_gates,
                model_gateway=model_gateway,
                profile=profile,
                allowed_refs=allowed_refs,
                stage="repair",
                repair_context=repair_context,
                framework_adapter=self.framework_adapter,
                prior_component_invocations=(
                    ()
                    if state.get("runPayload") is not None
                    else state.get("priorComponents", [])
                ),
            )
            failed_payload = state.get("runPayload")
            if failed_payload is not None:
                repaired_payload = _merge_repair_components(
                    failed_run_payload=failed_payload,
                    repaired_run_payload=repaired_payload,
                )
            return {
                "runPayload": repaired_payload,
                "repairAttempted": True,
                "needsRepair": False,
                "stageTrace": [*state.get("stageTrace", []), "repair"],
            }

        def final_node(state: _DraftPackGraphState) -> _DraftPackGraphState:
            return {"stageTrace": [*state.get("stageTrace", []), "final"]}

        graph = _compile_langgraph(
            file_inventory_node=file_inventory_node,
            file_content_node=file_content_node,
            quality_gate_node=quality_gate_node,
            repair_node=repair_node,
            final_node=final_node,
        )
        final_state = graph.invoke(
            {
                "priorComponents": [],
                "repairAttempted": False,
                "needsRepair": False,
                "stageTrace": [],
            }
        )
        run_payload = final_state.get("runPayload") if isinstance(final_state, Mapping) else None
        if not isinstance(run_payload, AgentRunPayload):
            raise ModelGatewayError(
                "LangGraph AI Draft Pack orchestrator did not produce a valid draft pack.",
                code=P44_LANGGRAPH_ORCHESTRATOR_FAILED,
                provider_error={
                    "type": "langgraph_ai_draft_pack_orchestrator",
                    "code": P44_LANGGRAPH_ORCHESTRATOR_FAILED,
                    "stage": "final",
                },
            )
        return _attach_langgraph_component(
            run_payload,
            target_ref=target_ref,
            stage_trace=final_state.get("stageTrace", []),
            repair_attempted=bool(final_state.get("repairAttempted")),
            quality_status=str(final_state.get("qualityStatus") or ""),
            quality_failed_check_count=int(final_state.get("qualityFailedCheckCount") or 0),
        )


def _compile_langgraph(
    *,
    file_inventory_node: Any,
    file_content_node: Any,
    quality_gate_node: Any,
    repair_node: Any,
    final_node: Any,
) -> Any:
    try:
        from langgraph.graph import END, START, StateGraph
    except Exception as exc:  # noqa: BLE001 - diagnostics must stay sanitized
        raise ModelGatewayError(
            "LangGraph dependency is unavailable.",
            code=P44_LANGGRAPH_UNAVAILABLE,
            provider_error={
                "type": "langgraph_ai_draft_pack_orchestrator",
                "code": P44_LANGGRAPH_UNAVAILABLE,
                "dependency": "langgraph",
            },
        ) from exc

    graph = StateGraph(_DraftPackGraphState)
    graph.add_node("file_inventory", file_inventory_node)
    graph.add_node("file_content", file_content_node)
    graph.add_node("quality_gate", quality_gate_node)
    graph.add_node("repair", repair_node)
    graph.add_node("final", final_node)
    graph.add_edge(START, "file_inventory")
    graph.add_edge("file_inventory", "file_content")
    graph.add_conditional_edges(
        "file_content",
        _route_after_file_content,
        {"repair": "repair", "quality_gate": "quality_gate"},
    )
    graph.add_edge("repair", "quality_gate")
    graph.add_conditional_edges(
        "quality_gate",
        _route_after_quality_gate,
        {"repair": "repair", "final": "final"},
    )
    graph.add_edge("final", END)
    return graph.compile(checkpointer=False)


def _route_after_file_content(state: _DraftPackGraphState) -> str:
    return "repair" if state.get("needsRepair") else "quality_gate"


def _route_after_quality_gate(state: _DraftPackGraphState) -> str:
    return "repair" if state.get("needsRepair") and not state.get("repairAttempted") else "final"


def _quality_repair_context(report: ValidationReport) -> dict[str, Any]:
    failed = [
        {
            "ruleId": check.rule_id,
            "severity": check.severity.value,
            "message": check.message[:300],
        }
        for check in report.failed_checks[:20]
    ]
    return {
        "failureStage": "deterministic_quality_validation",
        "errorCode": "AI_DRAFT_PACK_QUALITY_GATE_FAILED",
        "errorClass": "ValidationReport",
        "reason": "Deterministic P42 quality gate failed.",
        "failedCheckCount": len(report.failed_checks),
        "failedChecks": failed,
        "instruction": (
            "Repair the draft pack so all expected files, DTO references, mapper methods, "
            "and required REVIEW_REQUIRED markers pass deterministic validation."
        ),
    }


def _adapter_stage_failure_component(
    *,
    adapter: AiGenerationFrameworkAdapter,
    target_ref: str,
    stage: str,
    exc: Exception,
) -> dict[str, Any]:
    failure_code = (
        exc.code
        if isinstance(exc, ModelGatewayError)
        else "AI_DRAFT_PACK_SCHEMA_VALIDATION_FAILED"
    )
    return {
        "component": "ai_generation_framework_adapter",
        "adapterContract": AI_GENERATION_FRAMEWORK_ADAPTER_VERSION,
        "adapterId": str(getattr(adapter, "adapter_id", "unknown")),
        "candidateFramework": str(getattr(adapter, "candidate_framework", "unknown")),
        "targetRefHash": stable_json_hash({"targetRef": target_ref}),
        "stage": stage,
        "status": "FAILED",
        "eventCount": 0,
        "componentIds": [],
        "blockerIds": [],
        "failureCodes": [str(failure_code)],
        "metrics": {},
        "traceHash": stable_json_hash(
            {
                "targetRef": target_ref,
                "stage": stage,
                "failureCode": str(failure_code),
                "errorClass": exc.__class__.__name__,
            }
        ),
    }


def _merge_repair_components(
    *,
    failed_run_payload: AgentRunPayload,
    repaired_run_payload: AgentRunPayload,
) -> AgentRunPayload:
    failed_components = tuple(failed_run_payload.model_invocation.component_invocations)
    if not failed_components:
        return repaired_run_payload
    merged_invocation = dataclass_replace(
        repaired_run_payload.model_invocation,
        component_invocations=(
            *failed_components,
            *repaired_run_payload.model_invocation.component_invocations,
        ),
    )
    return dataclass_replace(repaired_run_payload, model_invocation=merged_invocation)


def _attach_langgraph_component(
    run_payload: AgentRunPayload,
    *,
    target_ref: str,
    stage_trace: Sequence[Any],
    repair_attempted: bool,
    quality_status: str,
    quality_failed_check_count: int,
) -> AgentRunPayload:
    safe_stage_trace = [str(stage) for stage in stage_trace if str(stage).strip()]
    component = {
        "component": LANGGRAPH_AI_DRAFT_PACK_ORCHESTRATOR_COMPONENT,
        "runtimeContract": FRAMEWORK_RUNTIME_SUMMARY_VERSION,
        "orchestrator": "langgraph",
        "status": "SUCCEEDED",
        "agentType": AGENT_TYPE,
        "checkpointer": "disabled",
        "stageTrace": safe_stage_trace,
        "stageCount": len(safe_stage_trace),
        "repairAttempted": repair_attempted,
        "qualityStatus": quality_status,
        "qualityFailedCheckCount": quality_failed_check_count,
        "stateHash": stable_json_hash(
            {
                "targetRef": target_ref,
                "stageTrace": safe_stage_trace,
                "repairAttempted": repair_attempted,
                "qualityStatus": quality_status,
                "qualityFailedCheckCount": quality_failed_check_count,
            }
        ),
    }
    invocation = dataclass_replace(
        run_payload.model_invocation,
        component_invocations=(
            *run_payload.model_invocation.component_invocations,
            component,
        ),
    )
    return dataclass_replace(run_payload, model_invocation=invocation)
