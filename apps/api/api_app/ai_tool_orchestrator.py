from __future__ import annotations

import os
import re
import time
from collections.abc import Mapping
from dataclasses import dataclass, replace
from typing import Any

from ai_agent_runtime.gateway import ModelGateway, ModelGatewayError, model_profile_from_env
from ai_agent_runtime.models import (
    AiToolPlanningOutput,
    stable_json_hash,
)
from ai_agent_runtime.planner_effectiveness import (
    attach_planner_metrics_to_ai_tool_evidence,
)
from ai_agent_runtime.prompts import render_metadata_tool_planning_prompt
from ai_agent_runtime.storage_safety import sanitize_value_for_storage
from mssql_mcp_app.catalog import ToolSpec, load_tool_catalog
from mssql_mcp_app.errors import MetadataToolError
from mssql_mcp_app.profiles import load_db_profiles
from mssql_mcp_app.registry import build_tool_registry
from mssql_mcp_app.repositories import FixtureMetadataRepository, LiveMetadataRepository
from mssql_mcp_app.settings import load_live_metadata_settings
from mssql_mcp_app.tool_cache import MetadataToolCacheEvent

from api_app.metadata_gateway import MetadataCollectionResult
from api_app.metadata_service import load_profiles_for_metadata_request, repo_root
from api_app.repositories import WorkRequestRecord

MAX_AI_TOOL_CALLS = 5
MAX_AI_TOOL_ROUNDS = 2
REVIEW_STATUS = "REVIEW_REQUIRED"
SKIPPED_STATUS = "SKIPPED"
SUCCEEDED_STATUS = "SUCCEEDED"
AI_TOOL_PLANNER_DETERMINISTIC_FALLBACK = "AI_TOOL_PLANNER_DETERMINISTIC_FALLBACK"
FORBIDDEN_ARGUMENT_KEYS = frozenset(
    {
        "sql",
        "statement",
        "command",
        "execute",
        "execution",
        "procedure_execution",
        "ddl",
        "dml",
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
        "credential",
        "definition",
    }
)
WRITE_SQL_PATTERN = re.compile(
    r"\b(select|insert|update|delete|merge|exec|execute|create|alter|drop|truncate)\b",
    re.IGNORECASE,
)
VOLATILE_FACT_HASH_KEYS = frozenset(
    {
        "snapshotid",
        "snapshot_id",
        "collectedat",
        "collected_at",
    }
)


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        return int(value)
    except ValueError:
        return default


def ai_tool_max_calls() -> int:
    return max(_env_int("AI_TOOL_MAX_CALLS", MAX_AI_TOOL_CALLS), 0)


def ai_tool_max_rounds() -> int:
    return max(_env_int("AI_TOOL_MAX_ROUNDS", MAX_AI_TOOL_ROUNDS), 0)


def ai_tool_live_max_rounds() -> int:
    return max(_env_int("AI_TOOL_LIVE_MAX_ROUNDS", 1), 0)


def effective_ai_tool_budget(
    db_profile_id: str,
    *,
    max_tool_calls: int | None = None,
    max_rounds: int | None = None,
) -> tuple[int, int, bool]:
    calls = ai_tool_max_calls() if max_tool_calls is None else max(max_tool_calls, 0)
    rounds = ai_tool_max_rounds() if max_rounds is None else max(max_rounds, 0)
    if _live_ppm_metadata_enabled(db_profile_id):
        live_rounds = ai_tool_live_max_rounds()
        if live_rounds < rounds:
            return calls, live_rounds, True
    return calls, rounds, False


def _live_ppm_metadata_enabled(db_profile_id: str) -> bool:
    return (
        db_profile_id.strip().lower() == "ppm"
        and os.getenv("MSSQL_ENABLE_LIVE_METADATA", "0").strip().lower()
        in {"1", "true", "yes", "on"}
    )


@dataclass(frozen=True)
class AiToolOrchestrationResult:
    metadata: MetadataCollectionResult
    component_invocations: tuple[dict[str, Any], ...]


@dataclass(frozen=True)
class PolicyDecision:
    allowed: bool
    tool_name: str
    arguments: dict[str, Any]
    code: str | None = None
    message: str | None = None


class AgentToolPolicy:
    def __init__(
        self,
        *,
        tools: list[ToolSpec],
        request_db_profile_id: str,
        max_tool_calls: int = MAX_AI_TOOL_CALLS,
    ) -> None:
        self.request_db_profile_id = request_db_profile_id
        self.max_tool_calls = max_tool_calls
        self._tools = {
            tool.name: tool for tool in tools if tool.active and tool.read_only
        }

    @property
    def tool_names(self) -> set[str]:
        return set(self._tools)

    def decide(
        self,
        *,
        tool_name: str,
        arguments: Mapping[str, Any],
    ) -> PolicyDecision:
        normalized_tool = tool_name.strip()
        if normalized_tool not in self._tools:
            return PolicyDecision(
                allowed=False,
                tool_name=normalized_tool,
                arguments={},
                code="AI_TOOL_NOT_ACTIVE_READ_ONLY",
                message="요청한 tool은 활성화된 read-only MCP metadata tool이 아닙니다.",
            )
        normalized_arguments = _normalized_arguments(
            arguments,
            request_db_profile_id=self.request_db_profile_id,
        )
        if normalized_arguments.get("dbProfileId") != self.request_db_profile_id:
            return PolicyDecision(
                allowed=False,
                tool_name=normalized_tool,
                arguments=normalized_arguments,
                code="AI_TOOL_PROFILE_SWITCH_BLOCKED",
                message="AI tool orchestration은 metadata profile 전환을 허용하지 않습니다.",
            )
        violation = _argument_policy_violation(normalized_tool, normalized_arguments)
        if violation is not None:
            return PolicyDecision(
                allowed=False,
                tool_name=normalized_tool,
                arguments=normalized_arguments,
                code=violation[0],
                message=violation[1],
            )
        return PolicyDecision(
            allowed=True,
            tool_name=normalized_tool,
            arguments=normalized_arguments,
        )


def deterministic_fallback_tool_requests(
    *,
    db_profile_id: str,
    target: Mapping[str, Any] | None,
    tool_names: set[str] | list[str] | tuple[str, ...],
    max_tool_calls: int,
) -> list[dict[str, Any]]:
    target_info = _target_mapping(target)
    if not target_info or max_tool_calls <= 0:
        return []
    schema = target_info["schema"]
    name = target_info["name"]
    object_type = target_info["type"]
    allowed = set(tool_names)
    requests: list[dict[str, Any]] = []

    def add(
        tool_name: str,
        arguments: dict[str, Any],
        *,
        reason: str,
        expected: str,
    ) -> None:
        if tool_name not in allowed:
            return
        requests.append(
            {
                "toolName": tool_name,
                "arguments": {"dbProfileId": db_profile_id, **arguments},
                "reason": reason,
                "expectedEvidenceUse": expected,
            }
        )

    if object_type == "TABLE":
        table_args = {"schema": schema, "tableName": name}
        add(
            "get_table_schema",
            table_args,
            reason="fallback에는 결정론적 table shape 근거가 필요합니다.",
            expected="column, DTO, result-shape 검토 claim의 근거로 사용합니다.",
        )
        add(
            "get_table_constraints",
            table_args,
            reason="fallback에는 결정론적 key/relationship 근거가 필요합니다.",
            expected="PK/FK/constraint 및 relationship claim의 근거로 사용합니다.",
        )
        add(
            "get_table_indexes",
            table_args,
            reason="fallback에는 결정론적 index 근거가 필요합니다.",
            expected="index 및 access-path 검토 claim의 근거로 사용합니다.",
        )
        object_args = {"schema": schema, "objectName": name, "objectType": object_type}
        add(
            "get_extended_properties",
            object_args,
            reason="fallback에는 결정론적 documentation 근거가 필요합니다.",
            expected="description coverage 및 documentation gap claim의 근거로 사용합니다.",
        )
        add(
            "get_related_db_objects",
            object_args,
            reason="fallback에는 결정론적 related-object 근거가 필요합니다.",
            expected="dependency 및 relationship 검토 claim의 근거로 사용합니다.",
        )
    elif object_type in {"PROCEDURE", "VIEW", "FUNCTION"}:
        object_args = {"schema": schema, "objectName": name, "objectType": object_type}
        add(
            "get_dependency_closure",
            {**object_args, "maxDepth": 1, "includeReviewRequired": True},
            reason="fallback에는 제한된 dependency closure 근거가 필요합니다.",
            expected="dependency, related object, review marker claim의 근거로 사용합니다.",
        )
        add(
            "get_extended_properties",
            object_args,
            reason="fallback에는 결정론적 documentation 근거가 필요합니다.",
            expected="documentation 및 migration guide 검토 claim의 근거로 사용합니다.",
        )
        add(
            "get_related_db_objects",
            object_args,
            reason="fallback에는 결정론적 related-object 근거가 필요합니다.",
            expected="relationship 및 dependency 검토 claim의 근거로 사용합니다.",
        )
    return requests[:max_tool_calls]


class AiToolOrchestrator:
    def __init__(
        self,
        *,
        model_gateway: ModelGateway,
        max_tool_calls: int | None = None,
        max_rounds: int | None = None,
    ) -> None:
        self.model_gateway = model_gateway
        self.max_tool_calls = max_tool_calls if max_tool_calls is not None else ai_tool_max_calls()
        self.max_rounds = max_rounds if max_rounds is not None else ai_tool_max_rounds()

    def run(
        self,
        *,
        request_record: WorkRequestRecord,
        metadata: MetadataCollectionResult,
        static_analysis: dict[str, Any] | None,
    ) -> AiToolOrchestrationResult:
        if not _orchestration_enabled(request_record.options):
            return AiToolOrchestrationResult(metadata=metadata, component_invocations=())
        if _sp_text_gate_will_block_semantic(request_record.options):
            enriched = _metadata_with_ai_tool_evidence(
                metadata,
                status=SKIPPED_STATUS,
                tool_results=[],
                deterministic_facts=[],
                review_markers=[
                    _review_marker(
                        "AI_TOOL_ORCHESTRATION_SKIPPED",
                        (
                            "remote model 사용 전에 semantic analysis SP text gate가 실패해야 해서 "
                            "AI tool orchestration을 건너뛰었습니다."
                        ),
                        evidence_refs=_fallback_evidence_refs(metadata, []),
                    )
                ],
                caveats=["AI_TOOL_ORCHESTRATION_SKIPPED"],
                blocked_requests=[],
                component_invocations=[],
            )
            return AiToolOrchestrationResult(metadata=enriched, component_invocations=())

        planner = getattr(self.model_gateway, "plan_metadata_tools", None)
        if not callable(planner):
            enriched = _metadata_with_ai_tool_evidence(
                metadata,
                status=SKIPPED_STATUS,
                tool_results=[],
                deterministic_facts=[],
                review_markers=[
                    _review_marker(
                        "AI_TOOL_ORCHESTRATION_SKIPPED",
                        "설정된 model gateway가 metadata tool planning을 제공하지 않습니다.",
                        evidence_refs=_fallback_evidence_refs(metadata, []),
                    )
                ],
                caveats=["AI_TOOL_ORCHESTRATION_SKIPPED"],
                blocked_requests=[],
                component_invocations=[],
            )
            return AiToolOrchestrationResult(metadata=enriched, component_invocations=())

        tools = [tool for tool in load_tool_catalog() if tool.active and tool.read_only]
        policy = AgentToolPolicy(
            tools=tools,
            request_db_profile_id=request_record.db_profile_id,
            max_tool_calls=self.max_tool_calls,
        )
        tool_capabilities = _tool_capabilities(tools)
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
        max_tool_calls, max_rounds, budget_reduced = effective_ai_tool_budget(
            request_record.db_profile_id,
            max_tool_calls=self.max_tool_calls,
            max_rounds=self.max_rounds,
        )
        if budget_reduced:
            caveats.append("AI_TOOL_BUDGET_REDUCED")
            review_markers.append(
                _review_marker(
                    "AI_TOOL_BUDGET_REDUCED",
                    "live PPM latency와 비용 제어를 위해 AI tool planning round를 줄였습니다.",
                    evidence_refs=_fallback_evidence_refs(metadata, deterministic_facts),
                )
            )

        try:
            registry = _build_internal_registry(request_record.db_profile_id)
        except Exception as exc:
            marker = _review_marker(
                "AI_TOOL_ORCHESTRATION_SKIPPED",
                (
                    "AI tool orchestration용 internal MCP registry 설정이 실패했습니다: "
                    f"{exc.__class__.__name__}."
                ),
                evidence_refs=_fallback_evidence_refs(metadata, deterministic_facts),
            )
            enriched = _metadata_with_ai_tool_evidence(
                metadata,
                status=SKIPPED_STATUS,
                tool_results=[],
                deterministic_facts=[],
                review_markers=[marker],
                caveats=["AI_TOOL_ORCHESTRATION_SKIPPED"],
                blocked_requests=[],
                component_invocations=[],
            )
            return AiToolOrchestrationResult(metadata=enriched, component_invocations=())

        for round_index in range(1, max_rounds + 1):
            if len(tool_results) >= max_tool_calls:
                break
            prompt = render_metadata_tool_planning_prompt(
                target_ref=target_ref,
                metadata=metadata.as_dict(),
                static_analysis=static_analysis,
                tool_capabilities=tool_capabilities,
                previous_tool_evidence=tool_results,
                max_tool_calls=max_tool_calls - len(tool_results),
                round_index=round_index,
            )
            try:
                invocation = planner(prompt=prompt, profile=profile)
                plan = AiToolPlanningOutput.model_validate(invocation.structured_output)
            except (ModelGatewayError, ValueError) as exc:
                fallback_requests = deterministic_fallback_tool_requests(
                    db_profile_id=request_record.db_profile_id,
                    target=request_record.target,
                    tool_names=policy.tool_names,
                    max_tool_calls=max_tool_calls - len(tool_results),
                )
                component_invocations.append(
                    {
                        "stage": "ai_tool_planning",
                        "toolName": "metadata_tool_planner",
                        "status": REVIEW_STATUS,
                        "latencyMs": 0,
                        "evidenceCount": 0,
                        "toolRequestCount": len(fallback_requests),
                        "errorCode": getattr(exc, "code", exc.__class__.__name__),
                    }
                )
                if not fallback_requests:
                    marker = _review_marker(
                        "AI_TOOL_ORCHESTRATION_SKIPPED",
                        (
                            "Metadata tool planning이 실패해 baseline metadata로 "
                            "workflow를 계속했습니다. "
                            f"code={getattr(exc, 'code', exc.__class__.__name__)}"
                        ),
                        evidence_refs=_fallback_evidence_refs(metadata, deterministic_facts),
                    )
                    review_markers.append(marker)
                    caveats.append("AI_TOOL_ORCHESTRATION_SKIPPED")
                    break
                plan = _fallback_tool_plan(
                    fallback_requests,
                    evidence_refs=_fallback_evidence_refs(metadata, deterministic_facts),
                    detail_code=getattr(exc, "code", exc.__class__.__name__),
                )
                caveats.append(AI_TOOL_PLANNER_DETERMINISTIC_FALLBACK)
            else:
                component_invocations.append(
                    {
                        "stage": "ai_tool_planning",
                        "toolName": "metadata_tool_planner",
                        "status": invocation.status.value,
                        "inputHash": invocation.input_hash,
                        "promptHash": invocation.prompt_hash,
                        "outputHash": invocation.output_hash,
                        "latencyMs": invocation.latency_ms,
                        "evidenceCount": 0,
                        "toolRequestCount": len(plan.tool_requests),
                    }
                )
                if not plan.tool_requests and not tool_results:
                    fallback_requests = deterministic_fallback_tool_requests(
                        db_profile_id=request_record.db_profile_id,
                        target=request_record.target,
                        tool_names=policy.tool_names,
                        max_tool_calls=max_tool_calls - len(tool_results),
                    )
                    if fallback_requests:
                        plan = _fallback_tool_plan(
                            fallback_requests,
                            evidence_refs=_fallback_evidence_refs(metadata, deterministic_facts),
                            detail_code="EMPTY_TOOL_PLAN",
                        )
                        caveats.append(AI_TOOL_PLANNER_DETERMINISTIC_FALLBACK)
            planned_request_count += len(plan.tool_requests)
            for marker in plan.review_markers:
                marker_payload = marker.model_dump(by_alias=True, mode="json")
                if not marker_payload.get("evidenceRefs"):
                    marker_payload["evidenceRefs"] = _fallback_evidence_refs(
                        metadata,
                        deterministic_facts,
                    )
                review_markers.append(marker_payload)
            executable_this_round = 0
            cache_hit_this_round = False
            for request in plan.tool_requests:
                if len(tool_results) >= max_tool_calls:
                    caveats.append("AI_TOOL_CALL_BUDGET_EXHAUSTED")
                    budget_exhausted = True
                    review_markers.append(
                        _review_marker(
                            "AI_TOOL_CALL_BUDGET_EXHAUSTED",
                            (
                                "계획된 요청을 모두 실행하기 전에 AI metadata tool call budget을 "
                                "소진했습니다."
                            ),
                            evidence_refs=_fallback_evidence_refs(metadata, deterministic_facts),
                        )
                    )
                    break
                decision = policy.decide(
                    tool_name=request.tool_name,
                    arguments=request.arguments,
                )
                request_key = (
                    decision.tool_name,
                    stable_json_hash(decision.arguments),
                )
                if request_key in seen_requests:
                    deduped_request_count += 1
                    continue
                seen_requests.add(request_key)
                if not decision.allowed:
                    blocked = _blocked_request(decision)
                    blocked_requests.append(blocked)
                    review_markers.append(
                        _review_marker(
                            "AI_TOOL_ORCHESTRATION_REVIEW_REQUIRED",
                            str(decision.message or "AI metadata tool request가 차단되었습니다."),
                            evidence_refs=_fallback_evidence_refs(metadata, deterministic_facts),
                        )
                    )
                    caveats.append(str(decision.code or "AI_TOOL_REQUEST_BLOCKED"))
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
                executable_this_round += 1
                started = time.monotonic()
                try:
                    payload = registry.invoke_payload(
                        decision.tool_name,
                        {"arguments": decision.arguments},
                    )
                except MetadataToolError as exc:
                    failed_tool_call_count += 1
                    review_markers.append(
                        _review_marker(
                            "AI_TOOL_ORCHESTRATION_REVIEW_REQUIRED",
                            (
                                "AI metadata tool invocation이 문서화된 MCP error로 실패했습니다: "
                                f"{exc.code}."
                            ),
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
                sanitized_payload = _sanitize_tool_payload(payload)
                cache_event = getattr(registry, "last_cache_event", None)
                if isinstance(cache_event, MetadataToolCacheEvent):
                    cache_hit_this_round = cache_hit_this_round or cache_event.status == "HIT"
                argument_hash = stable_json_hash(decision.arguments)
                content_hash = _tool_content_hash(
                    decision.tool_name,
                    sanitized_payload,
                    argument_hash=argument_hash,
                )
                fact = _deterministic_fact(
                    decision.tool_name,
                    sanitized_payload,
                    argument_hash=argument_hash,
                    content_hash=content_hash,
                )
                output_hash = stable_json_hash(sanitized_payload)
                deterministic_facts.append(fact)
                tool_results.append(
                    {
                        "toolName": decision.tool_name,
                        "factId": fact["id"],
                        "snapshotId": sanitized_payload.get("snapshotId"),
                        "collectedAt": sanitized_payload.get("collectedAt"),
                        "evidenceRefs": _safe_dict_list(
                            sanitized_payload.get("evidenceRefs")
                        ),
                        "data": _safe_dict(sanitized_payload.get("data")),
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
                        evidence_count=len(
                            _safe_dict_list(sanitized_payload.get("evidenceRefs"))
                        ),
                        error_code=None,
                        cache_event=(
                            cache_event
                            if isinstance(cache_event, MetadataToolCacheEvent)
                            else None
                        ),
                    )
                )
            if executable_this_round == 0:
                break
            if cache_hit_this_round and tool_results:
                break

        status = SUCCEEDED_STATUS if tool_results and not blocked_requests else REVIEW_STATUS
        if not tool_results and not blocked_requests and not caveats:
            status = SUCCEEDED_STATUS
        enriched = _metadata_with_ai_tool_evidence(
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
        return AiToolOrchestrationResult(
            metadata=enriched,
            component_invocations=tuple(component_invocations),
        )


def _orchestration_enabled(options: Mapping[str, Any]) -> bool:
    use_llm = bool(options.get("useLlmAnalysis", True))
    use_tools = bool(options.get("useAiToolOrchestration", True))
    return use_llm and use_tools


def _sp_text_gate_will_block_semantic(options: Mapping[str, Any]) -> bool:
    return (
        os.getenv("LLM_ENABLE_REMOTE", "0").strip() == "1"
        and bool(options.get("allowSpDefinitionToModel", False))
        and str(options.get("sourceContextMode") or "RETRIEVED_SPANS").strip().upper()
        == "RETRIEVED_SPANS"
        and os.getenv("LLM_ALLOW_SP_TEXT", "0").strip() != "1"
    )


def _build_internal_registry(db_profile_id: str):
    settings = load_live_metadata_settings()
    profiles = (
        load_profiles_for_metadata_request(settings, db_profile_id=db_profile_id)
        if db_profile_id
        else load_db_profiles(settings, repo_root=repo_root())
    )
    repository = (
        LiveMetadataRepository(settings=settings, profiles=profiles)
        if settings.live_metadata_enabled
        else FixtureMetadataRepository()
    )
    return build_tool_registry(repository=repository, profiles=profiles)


def _tool_capabilities(tools: list[ToolSpec]) -> list[dict[str, Any]]:
    return [
        {
            "name": tool.name,
            "description": tool.description,
            "inputSchema": _sanitize_value(tool.input_schema),
        }
        for tool in tools
        if tool.active and tool.read_only
    ]


def _target_ref(request_record: WorkRequestRecord) -> str:
    target = request_record.target
    return f"{target['schema']}.{target['name']}"


def _target_mapping(target: Mapping[str, Any] | None) -> dict[str, str] | None:
    if not isinstance(target, Mapping):
        return None
    schema = str(target.get("schema") or target.get("schemaName") or "").strip()
    name = str(target.get("name") or target.get("objectName") or "").strip()
    object_type = str(target.get("type") or target.get("objectType") or "").strip().upper()
    if not schema or not name or object_type not in {"PROCEDURE", "TABLE", "VIEW", "FUNCTION"}:
        return None
    return {"schema": schema, "name": name, "type": object_type}


def _normalized_arguments(
    arguments: Mapping[str, Any],
    *,
    request_db_profile_id: str,
) -> dict[str, Any]:
    normalized = _sanitize_value(dict(arguments))
    normalized.setdefault("dbProfileId", request_db_profile_id)
    return _cap_argument_values(normalized)


def _cap_argument_values(value: Any) -> Any:
    if isinstance(value, dict):
        capped = {}
        for key, item in value.items():
            key_text = str(key)
            if key_text in {"limit", "topK"}:
                capped[key] = min(int(item or 0), 20)
            elif key_text == "maxDepth":
                capped[key] = min(int(item or 0), 3)
            else:
                capped[key] = _cap_argument_values(item)
        return capped
    if isinstance(value, list):
        return [_cap_argument_values(item) for item in value]
    return value


def _argument_policy_violation(
    tool_name: str,
    value: Any,
    *,
    path: str = "arguments",
) -> tuple[str, str] | None:
    if isinstance(value, dict):
        for key, item in value.items():
            key_text = str(key)
            normalized_key = key_text.replace("-", "_").lower()
            nested_path = f"{path}.{key_text}"
            if normalized_key in FORBIDDEN_ARGUMENT_KEYS:
                if not (tool_name == "search_metadata_objects" and normalized_key == "query"):
                    return (
                        "AI_TOOL_FORBIDDEN_ARGUMENT",
                        f"금지된 argument key를 {nested_path}에서 차단했습니다.",
                    )
            violation = _argument_policy_violation(tool_name, item, path=nested_path)
            if violation is not None:
                return violation
        return None
    if isinstance(value, list):
        for index, item in enumerate(value):
            violation = _argument_policy_violation(tool_name, item, path=f"{path}[{index}]")
            if violation is not None:
                return violation
        return None
    if isinstance(value, str) and _looks_like_freeform_sql(value):
        return (
            "AI_TOOL_FREEFORM_SQL_BLOCKED",
            f"free-form SQL처럼 보이는 argument를 {path}에서 차단했습니다.",
        )
    return None


def _looks_like_freeform_sql(value: str) -> bool:
    text = value.strip()
    if not text:
        return False
    if WRITE_SQL_PATTERN.search(text) and (" " in text or ";" in text):
        return True
    return "--" in text or "/*" in text or "*/" in text


def _sanitize_tool_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    return _sanitize_value(sanitize_value_for_storage(dict(payload), procedure_definition=""))


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, dict):
        sanitized = {}
        for key, item in value.items():
            key_text = str(key)
            normalized = key_text.replace("-", "_").lower()
            if normalized in {
                "definition",
                "raw_definition",
                "rawsql",
                "raw_sql",
                "sqltext",
                "sql_text",
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
            }:
                continue
            sanitized[key] = _sanitize_value(item)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_value(item) for item in value]
    return value


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
            "content": _stable_fact_hash_content(payload),
        }
    )


def _stable_fact_hash_content(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: _stable_fact_hash_content(item)
            for key, item in value.items()
            if str(key).replace("-", "_").lower() not in VOLATILE_FACT_HASH_KEYS
        }
    if isinstance(value, list):
        return [_stable_fact_hash_content(item) for item in value]
    return value


def _deterministic_fact(
    tool_name: str,
    payload: Mapping[str, Any],
    *,
    argument_hash: str | None = None,
    content_hash: str | None = None,
) -> dict[str, Any]:
    argument_hash = argument_hash or stable_json_hash({})
    content_hash = content_hash or _tool_content_hash(
        tool_name,
        payload,
        argument_hash=argument_hash,
    )
    fact_hash = content_hash[:12]
    return {
        "id": f"mcp.{tool_name}.{fact_hash}",
        "type": "MSSQL_MCP_TOOL_EVIDENCE",
        "fact_type": "MSSQL_MCP_TOOL_EVIDENCE",
        "toolName": tool_name,
        "contentHash": content_hash,
        "summary": _fact_summary(tool_name, payload),
        "evidenceRefs": _safe_dict_list(payload.get("evidenceRefs")),
    }


def _fact_summary(tool_name: str, payload: Mapping[str, Any]) -> str:
    data = _safe_dict(payload.get("data"))
    if tool_name == "get_table_schema":
        table_name = data.get("tableName") or data.get("name") or "table"
        columns = data.get("columns") if isinstance(data.get("columns"), list) else []
        return (
            f"{data.get('schema', '')}.{table_name} table schema metadata입니다. "
            f"컬럼 {len(columns)}개를 포함합니다."
        )
    if tool_name == "search_metadata_objects":
        results = data.get("results") if isinstance(data.get("results"), list) else []
        return f"Metadata object search가 candidate identity {len(results)}개를 반환했습니다."
    if tool_name == "get_dependency_closure":
        summary = _safe_dict(data.get("summary"))
        node_count = summary.get("nodeCount", 0)
        edge_count = summary.get("edgeCount", 0)
        return (
            "의존성 closure metadata입니다. "
            f"node {node_count}개와 edge {edge_count}개를 포함합니다."
        )
    return f"{tool_name}이 sanitized read-only MSSQL metadata evidence를 반환했습니다."


def _metadata_with_ai_tool_evidence(
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
    existing_facts = list(metadata.deterministic_facts)
    return replace(
        metadata,
        ai_tool_evidence=evidence,
        deterministic_facts=tuple([*existing_facts, *deterministic_facts]),
        notes=tuple(
            _dedupe_strings(
                [
                    *metadata.notes,
                    "AI tool orchestration은 internal read-only MSSQL MCP registry "
                    "경계를 사용했습니다.",
                ]
            )
        ),
    )


def _tool_component(
    *,
    tool_name: str,
    arguments: Mapping[str, Any],
    status: str,
    output_hash: str | None,
    latency_ms: int,
    evidence_count: int,
    error_code: str | None,
    cache_event: MetadataToolCacheEvent | None = None,
) -> dict[str, Any]:
    component = {
        "stage": "ai_tool_execution",
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
    if cache_event is not None:
        component.update(cache_event.summary())
    return component


def _blocked_request(decision: PolicyDecision) -> dict[str, Any]:
    return {
        "toolName": decision.tool_name,
        "argumentHash": stable_json_hash(decision.arguments),
        "code": str(decision.code or "AI_TOOL_REQUEST_BLOCKED"),
        "message": str(decision.message or "AI metadata tool request가 차단되었습니다."),
    }


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
                    "model planner가 invalid 또는 empty 상태라 결정론적 read-only fallback "
                    "metadata request를 사용했습니다."
                )
            ],
            "reviewMarkers": [
                _review_marker(
                    AI_TOOL_PLANNER_DETERMINISTIC_FALLBACK,
                    (
                        "Metadata tool planner output이 invalid 또는 empty 상태라 결정론적 "
                        f"read-only fallback tool request를 사용했습니다. code={detail_code}"
                    ),
                    evidence_refs=evidence_refs,
                )
            ],
        }
    )


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
