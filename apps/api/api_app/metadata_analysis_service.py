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
from ai_agent_runtime.planner_effectiveness import (
    attach_planner_metrics_to_ai_tool_evidence,
)
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
    _tool_content_hash,
    _tool_component,
    effective_ai_tool_budget,
)
from api_app.knowledge_service import persist_metadata_analysis_knowledge
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
    MetadataDependencyGraph,
    MetadataDtoReadiness,
    MetadataInsightGroup,
    MetadataObjectIdentity,
    MetadataObjectProfile,
    MetadataSearchBlocker,
    MetadataSearchResult,
    ModelInvocationSummary,
)
from api_app.repositories import WorkflowRepository

AI_METADATA_ANALYSIS_SKIPPED = "AI_METADATA_ANALYSIS_SKIPPED"
AI_METADATA_ANALYSIS_REVIEW_REQUIRED = "AI_METADATA_ANALYSIS_REVIEW_REQUIRED"


@dataclass(frozen=True)
class MetadataToolRunResult:
    evidence: dict[str, Any]
    deterministic_facts: tuple[dict[str, Any], ...]
    component_invocations: tuple[dict[str, Any], ...]
    review_markers: tuple[dict[str, Any], ...]
    caveats: tuple[str, ...]


@dataclass(frozen=True)
class MetadataObjectDepth:
    object_profiles: tuple[dict[str, Any], ...]
    insight_groups: tuple[dict[str, Any], ...]
    dependency_graph: dict[str, Any]
    dto_readiness: tuple[dict[str, Any], ...]
    deterministic_facts: tuple[dict[str, Any], ...]


class MetadataAnalysisService:
    def __init__(
        self,
        *,
        model_gateway: ModelGateway | None = None,
        repository: WorkflowRepository | None = None,
    ) -> None:
        self.model_gateway = model_gateway or build_model_gateway_from_env()
        self.repository = repository

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
        object_depth = _build_metadata_object_depth(
            targets=targets,
            baseline_facts=baseline_facts,
            tool_evidence=tool_run.evidence,
        )
        deterministic_facts = [*deterministic_facts, *object_depth.deterministic_facts]
        metadata_payload["objectProfiles"] = list(object_depth.object_profiles)
        metadata_payload["insightGroups"] = list(object_depth.insight_groups)
        metadata_payload["dependencyGraph"] = object_depth.dependency_graph
        metadata_payload["dtoReadiness"] = list(object_depth.dto_readiness)
        metadata_payload["deterministicFacts"] = deterministic_facts
        all_caveats = _dedupe_strings([*caveats, *tool_run.caveats])
        review_markers = [*tool_run.review_markers]
        model_invocation: ModelInvocationSummary | None = None
        object_insights: list[MetadataAnalysisInsight] = []
        insight_groups: list[MetadataInsightGroup] = [
            MetadataInsightGroup.model_validate(group)
            for group in object_depth.insight_groups
        ]
        dto_readiness: list[MetadataDtoReadiness] = [
            MetadataDtoReadiness.model_validate(item)
            for item in object_depth.dto_readiness
        ]
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
                        *[str(fact["id"]) for fact in deterministic_facts],
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
                insight_groups = _merge_insight_groups(
                    [
                        *[group.to_response() for group in insight_groups],
                        *[
                            item
                            for item in output.get("insightGroups", [])
                            if isinstance(item, dict)
                        ],
                    ]
                )
                dto_readiness = _merge_dto_readiness(
                    [
                        *[item.to_response() for item in dto_readiness],
                        *[
                            item
                            for item in output.get("dtoReadiness", [])
                            if isinstance(item, dict)
                        ],
                    ]
                )
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
        dependency_graph_model = MetadataDependencyGraph.model_validate(
            object_depth.dependency_graph
        )
        analysis_payload = {
            "objectInsights": [item.to_response() for item in object_insights],
            "insightGroups": [group.to_response() for group in insight_groups],
            "dependencyGraph": dependency_graph_model.to_response(),
            "dtoReadiness": [item.to_response() for item in dto_readiness],
            "reviewMarkers": [marker.to_response() for marker in marker_models],
        }
        ai_tool_evidence = attach_planner_metrics_to_ai_tool_evidence(
            tool_run.evidence,
            deterministic_facts=deterministic_facts,
            component_invocations=tool_run.component_invocations,
            structured_output=analysis_payload,
        )
        response = MetadataAnalysisResponse(
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
            objectProfiles=[
                MetadataObjectProfile.model_validate(profile)
                for profile in object_depth.object_profiles
            ],
            insightGroups=insight_groups,
            dependencyGraph=dependency_graph_model,
            dtoReadiness=dto_readiness,
            aiToolEvidence=ai_tool_evidence,
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
        knowledge = persist_metadata_analysis_knowledge(
            repository=self.repository,
            request=request,
            response=response,
        )
        if knowledge.review_markers:
            response.review_markers = [
                *response.review_markers,
                *[
                    MetadataAnalysisReviewMarker.model_validate(marker)
                    for marker in knowledge.review_markers
                ],
            ]
        if knowledge.caveats:
            response.caveats = _dedupe_strings([*response.caveats, *knowledge.caveats])
        response.knowledge_assets = list(knowledge.assets)
        response.review_required = bool(
            response.review_required or response.review_markers or response.caveats
        )
        return response


def _build_metadata_object_depth(
    *,
    targets: list[MetadataSearchResult],
    baseline_facts: list[dict[str, Any]],
    tool_evidence: dict[str, Any],
) -> MetadataObjectDepth:
    profiles: dict[str, dict[str, Any]] = {}
    table_columns: dict[str, list[dict[str, Any]]] = {}
    table_constraints: dict[str, list[dict[str, Any]]] = {}
    table_indexes: dict[str, list[dict[str, Any]]] = {}
    source_fact_ids: dict[str, list[str]] = {}
    graph_nodes: dict[str, dict[str, Any]] = {}
    graph_edges: dict[tuple[str, str, str], dict[str, Any]] = {}
    unresolved: list[dict[str, Any]] = []
    dependency_insights: list[dict[str, Any]] = []

    baseline_fact_ids = [str(fact.get("id") or "") for fact in baseline_facts]
    for index, target in enumerate(targets):
        identity = target.object_identity
        object_ref = f"{identity.schema_name}.{identity.name}"
        fact_id = baseline_fact_ids[index] if index < len(baseline_fact_ids) else ""
        profile = _profile_for(profiles, object_ref, identity.type)
        profile["reviewRequired"] = bool(target.review_required)
        if fact_id:
            _append_unique(source_fact_ids, object_ref, fact_id)
        _graph_node(
            graph_nodes,
            object_ref=object_ref,
            object_type=identity.type,
            status="REVIEW_REQUIRED" if target.review_required else "CONFIRMED",
            evidence_refs=[fact_id] if fact_id else [],
        )

    for result in _safe_tool_results(tool_evidence):
        tool_name = str(result.get("toolName") or "")
        fact_id = str(result.get("factId") or "")
        data = _safe_dict(result.get("data"))
        if tool_name == "get_table_schema":
            object_ref = _table_object_ref(data)
            if not object_ref:
                continue
            columns = _safe_dict_list(data.get("columns"))
            profile = _profile_for(profiles, object_ref, "TABLE")
            table_columns[object_ref] = columns
            profile["columnCount"] = len(columns)
            profile["descriptionCoverage"] = _description_coverage(data, columns)
            profile["reviewRequired"] = bool(
                profile["reviewRequired"] or profile["descriptionCoverage"] < 1
            )
            _append_unique(source_fact_ids, object_ref, fact_id)
            _graph_node(
                graph_nodes,
                object_ref=object_ref,
                object_type="TABLE",
                status="REVIEW_REQUIRED" if profile["reviewRequired"] else "CONFIRMED",
                evidence_refs=[fact_id],
            )
        elif tool_name == "get_table_constraints":
            object_ref = _table_object_ref(data)
            if not object_ref:
                continue
            constraints = _safe_dict_list(data.get("constraints"))
            profile = _profile_for(profiles, object_ref, "TABLE")
            table_constraints[object_ref] = constraints
            profile["constraintCount"] = len(constraints)
            profile["primaryKeyCount"] = _constraint_count(constraints, "PK")
            profile["foreignKeyCount"] = _constraint_count(constraints, "FK")
            _append_unique(source_fact_ids, object_ref, fact_id)
            for constraint in constraints:
                if str(constraint.get("constraintType") or "") != "FK":
                    continue
                referenced = _safe_dict(constraint.get("referencedObject"))
                ref_schema = str(referenced.get("schema") or "").strip()
                ref_table = str(referenced.get("tableName") or "").strip()
                if not ref_schema or not ref_table:
                    unresolved.append(
                        {
                            "objectRef": object_ref,
                            "reason": "FK_REFERENCED_OBJECT_UNRESOLVED",
                            "evidenceRefs": [fact_id],
                        }
                    )
                    continue
                to_ref = f"{ref_schema}.{ref_table}"
                _graph_node(
                    graph_nodes,
                    object_ref=object_ref,
                    object_type="TABLE",
                    status="CONFIRMED",
                    evidence_refs=[fact_id],
                )
                _graph_node(
                    graph_nodes,
                    object_ref=to_ref,
                    object_type="TABLE",
                    status="CONFIRMED",
                    evidence_refs=[fact_id],
                )
                _graph_edge(
                    graph_edges,
                    from_ref=object_ref,
                    to_ref=to_ref,
                    relationship_type=str(constraint.get("name") or "FK"),
                    status="CONFIRMED",
                    evidence_refs=[fact_id],
                )
        elif tool_name == "get_table_indexes":
            object_ref = _table_object_ref(data)
            if not object_ref:
                continue
            indexes = _safe_dict_list(data.get("indexes"))
            profile = _profile_for(profiles, object_ref, "TABLE")
            table_indexes[object_ref] = indexes
            profile["indexCount"] = len(indexes)
            _append_unique(source_fact_ids, object_ref, fact_id)
        elif tool_name == "get_extended_properties":
            object_ref = _object_property_ref(data)
            if not object_ref:
                continue
            properties = _safe_dict_list(data.get("extendedProperties"))
            profile = _profile_for(
                profiles,
                object_ref,
                str(data.get("objectType") or "OBJECT"),
            )
            if not properties:
                profile["reviewRequired"] = True
            _append_unique(source_fact_ids, object_ref, fact_id)
        elif tool_name == "get_related_db_objects":
            source_ref = _related_source_ref(data)
            if not source_ref:
                continue
            object_type = str(data.get("objectType") or "OBJECT")
            _profile_for(profiles, source_ref, object_type)
            _append_unique(source_fact_ids, source_ref, fact_id)
            _graph_node(
                graph_nodes,
                object_ref=source_ref,
                object_type=object_type,
                status="CONFIRMED",
                evidence_refs=[fact_id],
            )
            for related in _safe_dict_list(data.get("relatedObjects")):
                related_ref = _dependency_ref(related)
                if not related_ref:
                    unresolved.append(
                        {
                            "objectRef": source_ref,
                            "reason": str(
                                related.get("resolutionStrategy")
                                or related.get("reviewStatus")
                                or "RELATED_OBJECT_UNRESOLVED"
                            ),
                            "evidenceRefs": [fact_id],
                        }
                    )
                    continue
                status = (
                    "REVIEW_REQUIRED"
                    if str(related.get("reviewStatus") or "") == "REVIEW_REQUIRED"
                    or bool(related.get("isAmbiguous"))
                    else "CONFIRMED"
                )
                _graph_node(
                    graph_nodes,
                    object_ref=related_ref,
                    object_type=str(related.get("objectType") or "OBJECT"),
                    status=status,
                    evidence_refs=[fact_id],
                )
                _graph_edge(
                    graph_edges,
                    from_ref=source_ref,
                    to_ref=related_ref,
                    relationship_type=str(related.get("dependencyType") or "RELATED"),
                    status=status,
                    evidence_refs=[fact_id],
                )
        elif tool_name == "get_dependency_closure":
            _merge_dependency_closure(
                data=data,
                fact_id=fact_id,
                graph_nodes=graph_nodes,
                graph_edges=graph_edges,
                unresolved=unresolved,
                dependency_insights=dependency_insights,
            )

    profile_facts: list[dict[str, Any]] = []
    object_profiles: list[dict[str, Any]] = []
    for object_ref, profile in profiles.items():
        profile["sourceFactIds"] = _dedupe_strings(source_fact_ids.get(object_ref, []))
        profile_fact = _profile_fact(profile)
        profile_facts.append(profile_fact)
        profile["sourceFactIds"] = _dedupe_strings(
            [*profile["sourceFactIds"], str(profile_fact["id"])]
        )
        profile["evidenceRefs"] = list(profile["sourceFactIds"])
        object_profiles.append(profile)

    dependency_graph = {
        "nodes": sorted(graph_nodes.values(), key=lambda item: item["id"]),
        "edges": sorted(
            graph_edges.values(),
            key=lambda item: (item["from"], item["to"], item["relationshipType"]),
        ),
        "unresolved": _dedupe_unresolved(unresolved),
    }
    graph_fact = _graph_fact(dependency_graph)
    graph_facts = [graph_fact] if dependency_graph["nodes"] or dependency_graph["edges"] else []
    if graph_facts:
        graph_ref = str(graph_facts[0]["id"])
        for node in dependency_graph["nodes"]:
            node["evidenceRefs"] = _dedupe_strings([*node["evidenceRefs"], graph_ref])
        for edge in dependency_graph["edges"]:
            edge["evidenceRefs"] = _dedupe_strings([*edge["evidenceRefs"], graph_ref])

    insight_groups = _build_insight_groups(
        profiles=object_profiles,
        table_columns=table_columns,
        table_constraints=table_constraints,
        table_indexes=table_indexes,
        dependency_insights=dependency_insights,
        graph_fact_ids=[str(fact["id"]) for fact in graph_facts],
    )
    dto_readiness = _build_dto_readiness(object_profiles, table_columns)
    return MetadataObjectDepth(
        object_profiles=tuple(object_profiles),
        insight_groups=tuple(insight_groups),
        dependency_graph=dependency_graph,
        dto_readiness=tuple(dto_readiness),
        deterministic_facts=tuple([*profile_facts, *graph_facts]),
    )


def _merge_insight_groups(items: list[dict[str, Any]]) -> list[MetadataInsightGroup]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    seen: set[tuple[str, str, str]] = set()
    for item in items:
        category = str(item.get("category") or "").strip()
        if not category:
            continue
        for insight in item.get("insights", []) or []:
            if not isinstance(insight, dict):
                continue
            key = (
                category,
                str(insight.get("code") or ""),
                str(insight.get("objectRef") or ""),
            )
            if key in seen:
                continue
            seen.add(key)
            grouped.setdefault(category, []).append(insight)
    return [
        MetadataInsightGroup.model_validate({"category": category, "insights": insights})
        for category, insights in grouped.items()
        if insights
    ]


def _merge_dto_readiness(items: list[dict[str, Any]]) -> list[MetadataDtoReadiness]:
    by_ref: dict[str, dict[str, Any]] = {}
    for item in items:
        object_ref = str(item.get("objectRef") or "").strip()
        if not object_ref:
            continue
        existing = by_ref.get(object_ref)
        if existing is None or int(item.get("fieldCount") or 0) > int(
            existing.get("fieldCount") or 0
        ):
            by_ref[object_ref] = item
            continue
        existing["reviewReasons"] = _dedupe_strings(
            [
                *[str(reason) for reason in existing.get("reviewReasons", [])],
                *[str(reason) for reason in item.get("reviewReasons", [])],
            ]
        )
        existing["evidenceRefs"] = _dedupe_strings(
            [
                *[str(ref) for ref in existing.get("evidenceRefs", [])],
                *[str(ref) for ref in item.get("evidenceRefs", [])],
            ]
        )
    return [MetadataDtoReadiness.model_validate(item) for item in by_ref.values()]


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
    planned_request_count = 0
    deduped_request_count = 0
    failed_tool_call_count = 0
    budget_exhausted = False
    max_tool_calls, max_rounds, budget_reduced = effective_ai_tool_budget(db_profile_id)
    if budget_reduced:
        review_markers.append(
            _review_marker(
                "AI_TOOL_BUDGET_REDUCED",
                (
                    "AI metadata analysis planning rounds were reduced for live PPM "
                    "latency and cost control."
                ),
                evidence_refs=_fallback_fact_refs(metadata.get("deterministicFacts", [])),
            )
        )
        caveats.append("AI_TOOL_BUDGET_REDUCED")

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
            planned_request_count=0,
            failed_tool_call_count=0,
            deduped_request_count=0,
            budget_exhausted=False,
        )

    for round_index in range(1, max_rounds + 1):
        if len(tool_results) >= max_tool_calls:
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
            max_tool_calls=max_tool_calls - len(tool_results),
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
        planned_request_count += len(plan.tool_requests)
        executable_this_round = 0
        cache_hit_this_round = False
        for marker in plan.review_markers:
            marker_payload = marker.model_dump(by_alias=True, mode="json")
            if not marker_payload.get("evidenceRefs"):
                marker_payload["evidenceRefs"] = _fallback_fact_refs(
                    [*metadata.get("deterministicFacts", []), *deterministic_facts]
                )
            review_markers.append(marker_payload)
        for request in plan.tool_requests:
            if len(tool_results) >= max_tool_calls:
                caveats.append("AI_TOOL_CALL_BUDGET_EXHAUSTED")
                budget_exhausted = True
                review_markers.append(
                    _review_marker(
                        "AI_TOOL_CALL_BUDGET_EXHAUSTED",
                        (
                            "AI metadata analysis tool call budget was exhausted before "
                            "all planned requests ran."
                        ),
                        evidence_refs=_fallback_fact_refs(
                            [*metadata.get("deterministicFacts", []), *deterministic_facts]
                        ),
                    )
                )
                break
            decision = policy.decide(tool_name=request.tool_name, arguments=request.arguments)
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
                failed_tool_call_count += 1
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
            cache_event = getattr(registry, "last_cache_event", None)
            cache_hit_this_round = cache_hit_this_round or (
                getattr(cache_event, "status", None) == "HIT"
            )
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
                    "evidenceRefs": _safe_dict_list(sanitized_payload.get("evidenceRefs")),
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
                    evidence_count=len(_safe_dict_list(sanitized_payload.get("evidenceRefs"))),
                    error_code=None,
                    cache_event=cache_event,
                )
            )
        if executable_this_round == 0:
            break
        if cache_hit_this_round and tool_results:
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
        planned_request_count=planned_request_count,
        failed_tool_call_count=failed_tool_call_count,
        deduped_request_count=deduped_request_count,
        budget_exhausted=budget_exhausted,
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
    planned_request_count: int | None = None,
    failed_tool_call_count: int | None = None,
    deduped_request_count: int | None = None,
    budget_exhausted: bool | None = None,
) -> MetadataToolRunResult:
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
    return MetadataToolRunResult(
        evidence=evidence,
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


def _safe_tool_results(tool_evidence: dict[str, Any]) -> list[dict[str, Any]]:
    results = tool_evidence.get("toolResults")
    if not isinstance(results, list):
        return []
    return [dict(item) for item in results if isinstance(item, dict)]


def _profile_for(
    profiles: dict[str, dict[str, Any]],
    object_ref: str,
    object_type: str,
) -> dict[str, Any]:
    return profiles.setdefault(
        object_ref,
        {
            "objectRef": object_ref,
            "objectType": object_type,
            "columnCount": 0,
            "primaryKeyCount": 0,
            "foreignKeyCount": 0,
            "indexCount": 0,
            "constraintCount": 0,
            "descriptionCoverage": 0.0,
            "reviewRequired": False,
            "evidenceRefs": [],
            "sourceFactIds": [],
        },
    )


def _append_unique(target: dict[str, list[str]], key: str, value: str) -> None:
    if not value:
        return
    target.setdefault(key, [])
    if value not in target[key]:
        target[key].append(value)


def _graph_node(
    nodes: dict[str, dict[str, Any]],
    *,
    object_ref: str,
    object_type: str,
    status: str,
    evidence_refs: list[str],
) -> None:
    if not object_ref:
        return
    node = nodes.setdefault(
        object_ref,
        {
            "id": object_ref,
            "objectRef": object_ref,
            "objectType": object_type,
            "status": status,
            "evidenceRefs": [],
        },
    )
    if node["status"] != "REVIEW_REQUIRED" and status == "REVIEW_REQUIRED":
        node["status"] = status
    node["evidenceRefs"] = _dedupe_strings(
        [*node.get("evidenceRefs", []), *evidence_refs]
    )


def _graph_edge(
    edges: dict[tuple[str, str, str], dict[str, Any]],
    *,
    from_ref: str,
    to_ref: str,
    relationship_type: str,
    status: str,
    evidence_refs: list[str],
) -> None:
    if not from_ref or not to_ref:
        return
    key = (from_ref, to_ref, relationship_type)
    edge = edges.setdefault(
        key,
        {
            "from": from_ref,
            "to": to_ref,
            "relationshipType": relationship_type,
            "status": status,
            "evidenceRefs": [],
        },
    )
    if edge["status"] != "REVIEW_REQUIRED" and status == "REVIEW_REQUIRED":
        edge["status"] = status
    edge["evidenceRefs"] = _dedupe_strings(
        [*edge.get("evidenceRefs", []), *evidence_refs]
    )


def _table_object_ref(data: dict[str, Any]) -> str:
    schema = str(data.get("schema") or "").strip()
    table_name = str(data.get("tableName") or data.get("name") or "").strip()
    return f"{schema}.{table_name}" if schema and table_name else ""


def _object_property_ref(data: dict[str, Any]) -> str:
    schema = str(data.get("schema") or "").strip()
    object_name = str(data.get("objectName") or "").strip()
    return f"{schema}.{object_name}" if schema and object_name else ""


def _related_source_ref(data: dict[str, Any]) -> str:
    schema = str(data.get("schema") or "").strip()
    object_name = str(data.get("objectName") or "").strip()
    return f"{schema}.{object_name}" if schema and object_name else ""


def _dependency_ref(value: dict[str, Any]) -> str:
    schema = str(value.get("schema") or "").strip()
    name = str(
        value.get("name")
        or value.get("tableName")
        or value.get("objectName")
        or value.get("procedureName")
        or ""
    ).strip()
    return f"{schema}.{name}" if schema and name else ""


def _description_coverage(table_data: dict[str, Any], columns: list[dict[str, Any]]) -> float:
    total = len(columns) + 1
    if total <= 0:
        return 0.0
    confirmed = 0
    if table_data.get("description") or table_data.get("descriptionStatus") == "CONFIRMED":
        confirmed += 1
    for column in columns:
        if column.get("description") or column.get("descriptionStatus") == "CONFIRMED":
            confirmed += 1
    return round(confirmed / total, 4)


def _constraint_count(constraints: list[dict[str, Any]], constraint_type: str) -> int:
    return sum(
        1
        for constraint in constraints
        if str(constraint.get("constraintType") or "") == constraint_type
    )


def _merge_dependency_closure(
    *,
    data: dict[str, Any],
    fact_id: str,
    graph_nodes: dict[str, dict[str, Any]],
    graph_edges: dict[tuple[str, str, str], dict[str, Any]],
    unresolved: list[dict[str, Any]],
    dependency_insights: list[dict[str, Any]],
) -> None:
    node_refs: dict[str, str] = {}
    for node in _safe_dict_list(data.get("nodes")):
        object_ref = _dependency_ref(node)
        node_id = str(node.get("id") or object_ref)
        if object_ref:
            node_refs[node_id] = object_ref
            _graph_node(
                graph_nodes,
                object_ref=object_ref,
                object_type=str(node.get("objectType") or "OBJECT"),
                status=str(node.get("reviewStatus") or "CONFIRMED"),
                evidence_refs=[fact_id],
            )
    for edge in _safe_dict_list(data.get("edges")):
        from_ref = node_refs.get(str(edge.get("from") or ""), str(edge.get("from") or ""))
        to_ref = node_refs.get(str(edge.get("to") or ""), str(edge.get("to") or ""))
        status = (
            "REVIEW_REQUIRED"
            if str(edge.get("resolutionStatus") or "") == "REVIEW_REQUIRED"
            else "CONFIRMED"
        )
        _graph_edge(
            graph_edges,
            from_ref=from_ref,
            to_ref=to_ref,
            relationship_type=str(edge.get("dependencyType") or "DEPENDENCY"),
            status=status,
            evidence_refs=[fact_id],
        )
    for item in _safe_dict_list(data.get("unresolved")):
        unresolved.append(
            {
                "objectRef": _dependency_ref(item) or str(item.get("name") or "unresolved"),
                "reason": str(
                    item.get("resolutionStrategy")
                    or item.get("unresolvedReason")
                    or item.get("reviewStatus")
                    or "DEPENDENCY_REVIEW_REQUIRED"
                ),
                "evidenceRefs": [fact_id],
            }
        )
    summary = _safe_dict(data.get("summary"))
    if summary:
        root = _safe_dict(data.get("rootObject"))
        object_ref = _dependency_ref(root) or "metadata.dependencyGraph"
        dependency_insights.append(
            _insight(
                code="DEPENDENCY_GRAPH_SUMMARY",
                object_ref=object_ref,
                summary=(
                    "Dependency closure contains "
                    f"{summary.get('nodeCount', 0)} nodes, "
                    f"{summary.get('edgeCount', 0)} edges, and "
                    f"{summary.get('reviewRequiredCount', 0)} review-required items."
                ),
                status=(
                    "REVIEW_REQUIRED"
                    if int(summary.get("reviewRequiredCount") or 0) > 0
                    else "INFERRED_DESCRIPTION"
                ),
                evidence_refs=[fact_id],
            )
        )


def _profile_fact(profile: dict[str, Any]) -> dict[str, Any]:
    payload = {
        key: value
        for key, value in profile.items()
        if key not in {"evidenceRefs", "sourceFactIds"}
    }
    fact_id = f"metadata.profile.{stable_json_hash(payload)[:12]}"
    return {
        "id": fact_id,
        "type": "MSSQL_METADATA_OBJECT_PROFILE",
        "fact_type": "MSSQL_METADATA_OBJECT_PROFILE",
        "summary": (
            f"Object profile for {profile['objectType']} {profile['objectRef']} "
            f"with {profile['columnCount']} columns, {profile['constraintCount']} "
            f"constraints, and {profile['indexCount']} indexes."
        ),
        "evidenceRefs": [],
    }


def _graph_fact(dependency_graph: dict[str, Any]) -> dict[str, Any]:
    fact_id = f"metadata.profile.{stable_json_hash(dependency_graph)[:12]}"
    return {
        "id": fact_id,
        "type": "MSSQL_METADATA_DEPENDENCY_GRAPH_PROFILE",
        "fact_type": "MSSQL_METADATA_DEPENDENCY_GRAPH_PROFILE",
        "summary": (
            "Metadata dependency graph profile with "
            f"{len(dependency_graph.get('nodes', []))} nodes, "
            f"{len(dependency_graph.get('edges', []))} edges, and "
            f"{len(dependency_graph.get('unresolved', []))} unresolved items."
        ),
        "evidenceRefs": [],
    }


def _dedupe_unresolved(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[str, str], dict[str, Any]] = {}
    for item in items:
        object_ref = str(item.get("objectRef") or "")
        reason = str(item.get("reason") or "")
        key = (object_ref, reason)
        if key not in deduped:
            deduped[key] = {
                "objectRef": object_ref,
                "reason": reason,
                "evidenceRefs": [],
            }
        deduped[key]["evidenceRefs"] = _dedupe_strings(
            [
                *deduped[key].get("evidenceRefs", []),
                *[str(ref) for ref in item.get("evidenceRefs", [])],
            ]
        )
    return list(deduped.values())


def _build_insight_groups(
    *,
    profiles: list[dict[str, Any]],
    table_columns: dict[str, list[dict[str, Any]]],
    table_constraints: dict[str, list[dict[str, Any]]],
    table_indexes: dict[str, list[dict[str, Any]]],
    dependency_insights: list[dict[str, Any]],
    graph_fact_ids: list[str],
) -> list[dict[str, Any]]:
    groups: dict[str, list[dict[str, Any]]] = {}
    for profile in profiles:
        object_ref = str(profile["objectRef"])
        refs = list(profile.get("sourceFactIds") or profile.get("evidenceRefs") or [])
        columns = table_columns.get(object_ref, [])
        constraints = table_constraints.get(object_ref, [])
        indexes = table_indexes.get(object_ref, [])
        if columns:
            missing_descriptions = [
                str(column.get("name") or "")
                for column in columns
                if not column.get("description")
                and column.get("descriptionStatus") != "CONFIRMED"
            ]
            nullable_columns = [
                str(column.get("name") or "")
                for column in columns
                if bool(column.get("isNullable"))
            ]
            if missing_descriptions or float(profile["descriptionCoverage"]) < 1:
                groups.setdefault("DOCUMENTATION_GAP", []).append(
                    _insight(
                        code="COLUMN_DESCRIPTION_GAP",
                        object_ref=object_ref,
                        summary=(
                            f"{len(missing_descriptions)} columns need confirmed "
                            "descriptions or logical names."
                        ),
                        status="REVIEW_REQUIRED",
                        evidence_refs=refs,
                    )
                )
            if nullable_columns or missing_descriptions:
                groups.setdefault("COLUMN_RISK", []).append(
                    _insight(
                        code="COLUMN_NULLABILITY_OR_DOMAIN_REVIEW",
                        object_ref=object_ref,
                        summary=(
                            f"{len(nullable_columns)} nullable columns and "
                            f"{len(missing_descriptions)} review-required descriptions "
                            "need DTO field review."
                        ),
                        status="REVIEW_REQUIRED",
                        evidence_refs=refs,
                    )
                )
        if constraints:
            groups.setdefault("CONSTRAINT", []).append(
                _insight(
                    code="TABLE_CONSTRAINT_SUMMARY",
                    object_ref=object_ref,
                    summary=(
                        f"Table has {profile['primaryKeyCount']} PK, "
                        f"{profile['foreignKeyCount']} FK, and "
                        f"{profile['constraintCount']} total constraints."
                    ),
                    status="INFERRED_DESCRIPTION",
                    evidence_refs=refs,
                )
            )
            for constraint in constraints:
                if str(constraint.get("constraintType") or "") != "FK":
                    continue
                referenced = _safe_dict(constraint.get("referencedObject"))
                ref_schema = str(referenced.get("schema") or "").strip()
                ref_table = str(referenced.get("tableName") or "").strip()
                if ref_schema and ref_table:
                    groups.setdefault("RELATIONSHIP", []).append(
                        _insight(
                            code="FOREIGN_KEY_RELATIONSHIP",
                            object_ref=object_ref,
                            summary=(
                                f"{constraint.get('name')} references "
                                f"{ref_schema}.{ref_table}."
                            ),
                            status="INFERRED_DESCRIPTION",
                            evidence_refs=refs,
                        )
                    )
        elif profile["objectType"] == "TABLE" and profile["columnCount"]:
            groups.setdefault("CONSTRAINT", []).append(
                _insight(
                    code="CONSTRAINT_METADATA_MISSING",
                    object_ref=object_ref,
                    summary="Constraint metadata was not available for this table profile.",
                    status="REVIEW_REQUIRED",
                    evidence_refs=refs,
                )
            )
        if indexes:
            groups.setdefault("INDEX", []).append(
                _insight(
                    code="TABLE_INDEX_SUMMARY",
                    object_ref=object_ref,
                    summary=f"Table has {len(indexes)} indexes in metadata evidence.",
                    status="INFERRED_DESCRIPTION",
                    evidence_refs=refs,
                )
            )
        elif profile["objectType"] == "TABLE" and profile["columnCount"]:
            groups.setdefault("INDEX", []).append(
                _insight(
                    code="INDEX_METADATA_MISSING",
                    object_ref=object_ref,
                    summary="Index metadata was not available for this table profile.",
                    status="REVIEW_REQUIRED",
                    evidence_refs=refs,
                )
            )
    for insight in dependency_insights:
        insight_refs = _dedupe_strings([*insight.get("evidenceRefs", []), *graph_fact_ids])
        insight["evidenceRefs"] = insight_refs
        groups.setdefault("DEPENDENCY", []).append(insight)
    return [
        {"category": category, "insights": insights}
        for category, insights in groups.items()
        if insights
    ]


def _build_dto_readiness(
    profiles: list[dict[str, Any]],
    table_columns: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    readiness = []
    for profile in profiles:
        object_ref = str(profile["objectRef"])
        columns = table_columns.get(object_ref, [])
        reasons = []
        if profile["objectType"] != "TABLE":
            reasons.append("DTO readiness v1 is deepest for TABLE objects.")
        if not columns:
            reasons.append("Column metadata was not available.")
        if profile["primaryKeyCount"] == 0 and profile["objectType"] == "TABLE":
            reasons.append("Primary key metadata was not confirmed.")
        if float(profile["descriptionCoverage"]) < 1 and columns:
            reasons.append("Column or table descriptions need review.")
        if profile["objectType"] == "TABLE" and columns and not reasons:
            status = "READY"
        elif columns:
            status = "PARTIAL"
        else:
            status = "REVIEW_REQUIRED"
        readiness.append(
            {
                "objectRef": object_ref,
                "status": status,
                "fieldCount": int(profile["columnCount"]),
                "reviewReasons": reasons,
                "evidenceRefs": list(profile.get("sourceFactIds") or profile["evidenceRefs"]),
            }
        )
    return readiness


def _insight(
    *,
    code: str,
    object_ref: str,
    summary: str,
    status: str,
    evidence_refs: list[str],
) -> dict[str, Any]:
    return {
        "code": code,
        "objectRef": object_ref,
        "summary": summary,
        "status": status,
        "evidenceRefs": _dedupe_strings(evidence_refs),
    }


def _fallback_fact_refs(facts: Any) -> list[str]:
    if isinstance(facts, list):
        for fact in facts:
            if isinstance(fact, dict) and str(fact.get("id") or "").strip():
                return [str(fact["id"])]
    return ["metadata.analysis.no_fact"]
