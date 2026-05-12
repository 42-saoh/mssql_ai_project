from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from ai_agent_runtime.gateway import (
    ModelGateway,
    ModelGatewayError,
    build_model_gateway_from_env,
    model_profile_from_env,
)
from ai_agent_runtime.metadata_analysis import build_metadata_analysis_run
from ai_agent_runtime.models import AiToolPlanningOutput, stable_json_hash
from ai_agent_runtime.prompts import render_metadata_tool_planning_prompt
from mssql_mcp_app.catalog import load_tool_catalog
from mssql_mcp_app.errors import MetadataToolError

from api_app.ai_tool_orchestrator import (
    REVIEW_STATUS,
    SKIPPED_STATUS,
    SUCCEEDED_STATUS,
    AgentToolPolicy,
    _blocked_request,
    _build_internal_registry,
    _dedupe_markers,
    _dedupe_strings,
    _deterministic_fact,
    _review_marker,
    _safe_dict,
    _safe_dict_list,
    _sanitize_tool_payload,
    _tool_capabilities,
    _tool_component,
)
from api_app.metadata_service import (
    DEFAULT_METADATA_SEARCH_OBJECT_TYPES,
    MetadataSearchDependencyError,
    list_safe_metadata_profiles,
    search_metadata_objects,
)
from api_app.schemas import (
    EvidenceRef,
    MetadataAnalysisInsight,
    MetadataAnalysisOptions,
    MetadataAnalysisRequest,
    MetadataAnalysisResponse,
    MetadataAnalysisReviewMarker,
    MetadataObjectIdentity,
    MetadataSearchBlocker,
    MetadataSearchResult,
    ModelInvocationSummary,
)

AI_METADATA_ANALYSIS_SKIPPED = "AI_METADATA_ANALYSIS_SKIPPED"
AI_METADATA_ANALYSIS_REVIEW_REQUIRED = "AI_METADATA_ANALYSIS_REVIEW_REQUIRED"


@dataclass(frozen=True)
class MetadataToolRunResult:
    evidence: dict[str, Any]
    deterministic_facts: tuple[dict[str, Any], ...]
    component_invocations: tuple[dict[str, Any], ...]
    review_markers: tuple[dict[str, Any], ...]
    caveats: tuple[str, ...]


class MetadataAnalysisService:
    def __init__(self, *, model_gateway: ModelGateway | None = None) -> None:
        self.model_gateway = model_gateway or build_model_gateway_from_env()

    def analyze(self, request: MetadataAnalysisRequest) -> MetadataAnalysisResponse:
        options = request.options
        targets, source_profile, source_database, snapshot_id, collected_at, blockers, caveats = (
            _baseline_targets(request)
        )
        target_ref = _analysis_target_ref(request, targets)
        baseline_facts = _baseline_facts(targets)
        metadata_payload: dict[str, Any] = {
            "dbProfileId": request.db_profile_id,
            "mode": "QUERY" if request.query else "TARGET",
            "query": request.query,
            "target": request.target.to_response() if request.target else None,
            "targets": [target.to_response() for target in targets],
            "deterministicFacts": baseline_facts,
            "caveats": list(caveats),
            "blockers": [blocker.to_response() for blocker in blockers],
        }

        tool_run = _run_ai_metadata_tools(
            db_profile_id=request.db_profile_id,
            target_ref=target_ref,
            metadata=metadata_payload,
            options=options,
            model_gateway=self.model_gateway,
        )
        deterministic_facts = [*baseline_facts, *tool_run.deterministic_facts]
        metadata_payload["aiToolEvidence"] = tool_run.evidence
        metadata_payload["deterministicFacts"] = deterministic_facts
        all_caveats = _dedupe_strings([*caveats, *tool_run.caveats])
        review_markers = [*tool_run.review_markers]
        model_invocation: ModelInvocationSummary | None = None
        object_insights: list[MetadataAnalysisInsight] = []
        assumptions: list[str] = []
        summary = "Metadata analysis did not run because no deterministic evidence was available."

        if not options.use_llm_analysis:
            review_markers.append(
                _review_marker(
                    AI_METADATA_ANALYSIS_SKIPPED,
                    "Metadata LLM analysis was skipped because useLlmAnalysis=false.",
                    evidence_refs=_fallback_fact_refs(deterministic_facts),
                )
            )
            all_caveats = _dedupe_strings([*all_caveats, AI_METADATA_ANALYSIS_SKIPPED])
            summary = "Metadata LLM analysis skipped by request option."
        elif deterministic_facts:
            try:
                run = build_metadata_analysis_run(
                    target_ref=target_ref,
                    metadata=metadata_payload,
                    allowed_evidence_refs=[
                        *[str(fact["id"]) for fact in tool_run.deterministic_facts],
                        *[str(fact["id"]) for fact in baseline_facts],
                    ],
                    model_gateway=self.model_gateway,
                    profile_id=options.llm_profile_id,
                )
                output = run.structured_output
                summary = str(output.get("summary") or run.summary)
                object_insights = [
                    MetadataAnalysisInsight.model_validate(item)
                    for item in output.get("objectInsights", [])
                    if isinstance(item, dict)
                ]
                review_markers.extend(
                    item
                    for item in output.get("reviewMarkers", [])
                    if isinstance(item, dict)
                )
                assumptions = [
                    str(item) for item in output.get("assumptions", []) if str(item).strip()
                ]
                model_invocation = ModelInvocationSummary.model_validate(
                    run.model_invocation.to_storage_dict()
                )
            except (ModelGatewayError, ValueError) as exc:
                review_markers.append(
                    _review_marker(
                        AI_METADATA_ANALYSIS_SKIPPED,
                        (
                            "Metadata LLM analysis failed; response contains deterministic "
                            f"metadata only. code={getattr(exc, 'code', exc.__class__.__name__)}"
                        ),
                        evidence_refs=_fallback_fact_refs(deterministic_facts),
                    )
                )
                all_caveats = _dedupe_strings([*all_caveats, AI_METADATA_ANALYSIS_SKIPPED])
                summary = "Metadata LLM analysis skipped after model gateway failure."
        else:
            review_markers.append(
                _review_marker(
                    AI_METADATA_ANALYSIS_SKIPPED,
                    "Metadata LLM analysis was skipped because no deterministic fact ids exist.",
                    evidence_refs=["metadata.analysis.no_fact"],
                )
            )
            all_caveats = _dedupe_strings([*all_caveats, AI_METADATA_ANALYSIS_SKIPPED])

        marker_models = [
            MetadataAnalysisReviewMarker.model_validate(marker)
            for marker in _dedupe_markers(review_markers)
        ]
        return MetadataAnalysisResponse(
            dbProfileId=request.db_profile_id,
            mode="QUERY" if request.query else "TARGET",
            query=request.query,
            target=request.target,
            objectTypes=list(
                request.object_types or DEFAULT_METADATA_SEARCH_OBJECT_TYPES
            ),
            sourceProfile=source_profile,
            sourceDatabase=source_database,
            snapshotId=snapshot_id,
            collectedAt=collected_at,
            targets=targets,
            summary=summary,
            objectInsights=object_insights,
            aiToolEvidence=tool_run.evidence,
            deterministicFacts=deterministic_facts,
            reviewMarkers=marker_models,
            assumptions=assumptions,
            caveats=all_caveats,
            reviewRequired=bool(
                blockers
                or all_caveats
                or marker_models
                or any(target.review_required for target in targets)
            ),
            blockers=blockers,
            modelInvocation=model_invocation,
            componentInvocations=list(tool_run.component_invocations),
        )


def _baseline_targets(
    request: MetadataAnalysisRequest,
) -> tuple[
    list[MetadataSearchResult],
    str,
    str,
    str | None,
    str | None,
    list[MetadataSearchBlocker],
    list[str],
]:
    source_profile = request.db_profile_id
    source_database = _source_database(request.db_profile_id)
    if request.query:
        search = search_metadata_objects(
            db_profile_id=request.db_profile_id,
            query=request.query,
            object_types=tuple(request.object_types or DEFAULT_METADATA_SEARCH_OBJECT_TYPES),
            limit=request.options.max_targets,
        )
        return (
            list(search.results[: request.options.max_targets]),
            search.source_profile,
            search.source_database,
            search.snapshot_id,
            search.collected_at,
            list(search.blockers),
            list(search.caveats),
        )

    target = request.target
    if target is None:
        raise ValueError("metadata analysis target is required.")
    search = _find_target_via_search(request)
    if search is not None:
        exact = [
            item
            for item in search.results
            if item.object_identity.schema_name == target.schema_name
            and item.object_identity.name == target.name
            and item.object_identity.type == target.type
        ]
        if exact:
            return (
                exact[:1],
                search.source_profile,
                search.source_database,
                search.snapshot_id,
                search.collected_at,
                list(search.blockers),
                list(search.caveats),
            )
        source_profile = search.source_profile
        source_database = search.source_database
    return (
        [_target_result(target, request.db_profile_id, source_profile, source_database)],
        source_profile,
        source_database,
        None,
        None,
        [],
        ["TARGET_METADATA_SEARCH_MISS"],
    )


def _find_target_via_search(request: MetadataAnalysisRequest):
    target = request.target
    if target is None:
        return None
    try:
        return search_metadata_objects(
            db_profile_id=request.db_profile_id,
            query=target.name,
            object_types=(target.type,),
            limit=20,
        )
    except (MetadataSearchDependencyError, MetadataToolError, ValueError):
        return None


def _run_ai_metadata_tools(
    *,
    db_profile_id: str,
    target_ref: str,
    metadata: dict[str, Any],
    options: MetadataAnalysisOptions,
    model_gateway: ModelGateway,
) -> MetadataToolRunResult:
    if not options.use_llm_analysis or not options.use_ai_tool_orchestration:
        marker = _review_marker(
            AI_METADATA_ANALYSIS_SKIPPED,
            "AI metadata tool orchestration was skipped by request options.",
            evidence_refs=_fallback_fact_refs(metadata.get("deterministicFacts", [])),
        )
        return _tool_run_result(
            status=SKIPPED_STATUS,
            tool_results=[],
            deterministic_facts=[],
            review_markers=[marker],
            caveats=[AI_METADATA_ANALYSIS_SKIPPED],
            blocked_requests=[],
            component_invocations=[],
        )

    planner = getattr(model_gateway, "plan_metadata_tools", None)
    if not callable(planner):
        marker = _review_marker(
            AI_METADATA_ANALYSIS_SKIPPED,
            "Configured model gateway does not expose metadata tool planning.",
            evidence_refs=_fallback_fact_refs(metadata.get("deterministicFacts", [])),
        )
        return _tool_run_result(
            status=SKIPPED_STATUS,
            tool_results=[],
            deterministic_facts=[],
            review_markers=[marker],
            caveats=[AI_METADATA_ANALYSIS_SKIPPED],
            blocked_requests=[],
            component_invocations=[],
        )

    tools = [tool for tool in load_tool_catalog() if tool.active and tool.read_only]
    policy = AgentToolPolicy(tools=tools, request_db_profile_id=db_profile_id)
    tool_capabilities = _tool_capabilities(tools)
    profile = model_profile_from_env(options.llm_profile_id)
    component_invocations: list[dict[str, Any]] = []
    tool_results: list[dict[str, Any]] = []
    deterministic_facts: list[dict[str, Any]] = []
    review_markers: list[dict[str, Any]] = []
    blocked_requests: list[dict[str, Any]] = []
    caveats: list[str] = []
    seen_requests: set[tuple[str, str]] = set()

    try:
        registry = _build_internal_registry(db_profile_id)
    except Exception as exc:
        marker = _review_marker(
            AI_METADATA_ANALYSIS_SKIPPED,
            f"Internal MCP registry setup failed for metadata analysis: {exc.__class__.__name__}.",
            evidence_refs=_fallback_fact_refs(metadata.get("deterministicFacts", [])),
        )
        return _tool_run_result(
            status=SKIPPED_STATUS,
            tool_results=[],
            deterministic_facts=[],
            review_markers=[marker],
            caveats=[AI_METADATA_ANALYSIS_SKIPPED],
            blocked_requests=[],
            component_invocations=[],
        )

    for round_index in range(1, 3):
        if len(tool_results) >= 5:
            break
        prompt = render_metadata_tool_planning_prompt(
            target_ref=target_ref,
            metadata={
                **metadata,
                "aiToolEvidence": {
                    "toolResults": tool_results,
                    "blockedRequests": blocked_requests,
                    "caveats": caveats,
                },
            },
            static_analysis=None,
            tool_capabilities=tool_capabilities,
            previous_tool_evidence=tool_results,
            max_tool_calls=5 - len(tool_results),
            round_index=round_index,
        )
        try:
            invocation = planner(prompt=prompt, profile=profile)
            plan = AiToolPlanningOutput.model_validate(invocation.structured_output)
        except (ModelGatewayError, ValueError) as exc:
            review_markers.append(
                _review_marker(
                    AI_METADATA_ANALYSIS_SKIPPED,
                    (
                        "Metadata tool planning failed; analysis continued with baseline "
                        f"metadata. code={getattr(exc, 'code', exc.__class__.__name__)}"
                    ),
                    evidence_refs=_fallback_fact_refs(
                        [*metadata.get("deterministicFacts", []), *deterministic_facts]
                    ),
                )
            )
            caveats.append(AI_METADATA_ANALYSIS_SKIPPED)
            break
        component_invocations.append(
            {
                "stage": "ai_metadata_tool_planning",
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
        executable_this_round = 0
        for marker in plan.review_markers:
            marker_payload = marker.model_dump(by_alias=True, mode="json")
            if not marker_payload.get("evidenceRefs"):
                marker_payload["evidenceRefs"] = _fallback_fact_refs(
                    [*metadata.get("deterministicFacts", []), *deterministic_facts]
                )
            review_markers.append(marker_payload)
        for request in plan.tool_requests:
            if len(tool_results) >= 5:
                caveats.append("AI_TOOL_CALL_BUDGET_EXHAUSTED")
                break
            decision = policy.decide(tool_name=request.tool_name, arguments=request.arguments)
            request_key = (decision.tool_name, stable_json_hash(decision.arguments))
            if request_key in seen_requests:
                continue
            seen_requests.add(request_key)
            if not decision.allowed:
                blocked = _blocked_request(decision)
                blocked_requests.append(blocked)
                review_markers.append(
                    _review_marker(
                        AI_METADATA_ANALYSIS_REVIEW_REQUIRED,
                        str(decision.message or "AI metadata tool request was blocked."),
                        evidence_refs=_fallback_fact_refs(
                            [*metadata.get("deterministicFacts", []), *deterministic_facts]
                        ),
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
                review_markers.append(
                    _review_marker(
                        AI_METADATA_ANALYSIS_REVIEW_REQUIRED,
                        f"AI metadata tool invocation failed with MCP error: {exc.code}.",
                        evidence_refs=_fallback_fact_refs(
                            [*metadata.get("deterministicFacts", []), *deterministic_facts]
                        ),
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
            fact = _deterministic_fact(decision.tool_name, sanitized_payload)
            deterministic_facts.append(fact)
            tool_results.append(
                {
                    "toolName": decision.tool_name,
                    "factId": fact["id"],
                    "snapshotId": sanitized_payload.get("snapshotId"),
                    "collectedAt": sanitized_payload.get("collectedAt"),
                    "evidenceRefs": _safe_dict_list(sanitized_payload.get("evidenceRefs")),
                    "data": _safe_dict(sanitized_payload.get("data")),
                    "argumentHash": stable_json_hash(decision.arguments),
                    "outputHash": stable_json_hash(sanitized_payload),
                }
            )
            component_invocations.append(
                _tool_component(
                    tool_name=decision.tool_name,
                    arguments=decision.arguments,
                    status=SUCCEEDED_STATUS,
                    output_hash=stable_json_hash(sanitized_payload),
                    latency_ms=int((time.monotonic() - started) * 1000),
                    evidence_count=len(_safe_dict_list(sanitized_payload.get("evidenceRefs"))),
                    error_code=None,
                )
            )
        if executable_this_round == 0:
            break

    status = SUCCEEDED_STATUS if tool_results and not blocked_requests else REVIEW_STATUS
    if not tool_results and not blocked_requests and not caveats:
        status = SUCCEEDED_STATUS
    return _tool_run_result(
        status=status,
        tool_results=tool_results,
        deterministic_facts=deterministic_facts,
        review_markers=review_markers,
        caveats=caveats,
        blocked_requests=blocked_requests,
        component_invocations=component_invocations,
    )


def _tool_run_result(
    *,
    status: str,
    tool_results: list[dict[str, Any]],
    deterministic_facts: list[dict[str, Any]],
    review_markers: list[dict[str, Any]],
    caveats: list[str],
    blocked_requests: list[dict[str, Any]],
    component_invocations: list[dict[str, Any]],
) -> MetadataToolRunResult:
    return MetadataToolRunResult(
        evidence={
            "status": status,
            "toolCallCount": len(tool_results),
            "toolResults": tool_results,
            "blockedRequests": blocked_requests,
            "reviewMarkers": _dedupe_markers(review_markers),
            "caveats": _dedupe_strings(caveats),
        },
        deterministic_facts=tuple(deterministic_facts),
        component_invocations=tuple(component_invocations),
        review_markers=tuple(_dedupe_markers(review_markers)),
        caveats=tuple(_dedupe_strings(caveats)),
    )


def _baseline_facts(targets: list[MetadataSearchResult]) -> list[dict[str, Any]]:
    facts = []
    for target in targets:
        identity = target.object_identity
        payload = {
            "objectIdentity": identity.to_response(),
            "sourceProfile": target.source_profile,
            "sourceDatabase": target.source_database,
            "snapshotId": target.snapshot_id,
            "evidenceRefs": [ref.to_response() for ref in target.evidence_refs],
        }
        fact_id = f"metadata.search.{stable_json_hash(payload)[:12]}"
        facts.append(
            {
                "id": fact_id,
                "type": "MSSQL_METADATA_SEARCH_RESULT",
                "fact_type": "MSSQL_METADATA_SEARCH_RESULT",
                "summary": (
                    f"Metadata search identified {identity.type} "
                    f"{identity.schema_name}.{identity.name}."
                ),
                "evidenceRefs": [ref.to_response() for ref in target.evidence_refs],
            }
        )
    return facts


def _analysis_target_ref(
    request: MetadataAnalysisRequest,
    targets: list[MetadataSearchResult],
) -> str:
    if request.target is not None:
        return f"{request.target.schema_name}.{request.target.name}"
    if len(targets) == 1:
        identity = targets[0].object_identity
        return f"{identity.schema_name}.{identity.name}"
    return f"metadata.search:{request.query}"


def _target_result(
    target: MetadataObjectIdentity,
    db_profile_id: str,
    source_profile: str,
    source_database: str,
) -> MetadataSearchResult:
    object_ref = f"{source_database}.{target.schema_name}.{target.name}"
    return MetadataSearchResult(
        objectIdentity=target,
        sourceProfile=source_profile or db_profile_id,
        sourceDatabase=source_database or db_profile_id,
        evidenceRefs=[
            EvidenceRef(
                type="USER_INPUT",
                objectRef=object_ref,
                locator="metadata.analysis.request.target",
            )
        ],
        caveats=["TARGET_METADATA_SEARCH_MISS"],
        reviewRequired=True,
        blockers=[],
    )


def _source_database(db_profile_id: str) -> str:
    try:
        _, profiles = list_safe_metadata_profiles()
    except Exception:
        return db_profile_id
    for profile in profiles:
        if profile.id == db_profile_id:
            return profile.database
    return db_profile_id


def _fallback_fact_refs(facts: Any) -> list[str]:
    if isinstance(facts, list):
        for fact in facts:
            if isinstance(fact, dict) and str(fact.get("id") or "").strip():
                return [str(fact["id"])]
    return ["metadata.analysis.no_fact"]
