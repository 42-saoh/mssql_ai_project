from __future__ import annotations

import re
import time
from dataclasses import dataclass
from typing import Any

from ai_agent_generation.utils import (
    ensure_trailing_newline,
    java_imports_for_types,
    java_type_for_db_type,
    snake_to_lower_camel,
    upper_first,
)
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
    AI_TOOL_PLANNER_DETERMINISTIC_FALLBACK,
    REVIEW_STATUS,
    SKIPPED_STATUS,
    SUCCEEDED_STATUS,
    AgentToolPolicy,
    _blocked_request,
    _build_internal_registry,
    _dedupe_markers,
    _dedupe_strings,
    _deterministic_fact,
    _fallback_tool_plan,
    _review_marker,
    _safe_dict,
    _safe_dict_list,
    _sanitize_tool_payload,
    _tool_capabilities,
    _tool_content_hash,
    _tool_component,
    deterministic_fallback_tool_requests,
    effective_ai_tool_budget,
)
from api_app.knowledge_service import persist_metadata_analysis_knowledge
from api_app.metadata_service import (
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
    MetadataGeneratedDraft,
    MetadataInsightGroup,
    MetadataObjectIdentity,
    MetadataObjectProfile,
    MetadataSearchBlocker,
    MetadataSearchResult,
    ModelInvocationSummary,
)
from api_app.target_keys import target_key_for_ref, target_key_for_target
from api_app.repositories import WorkflowRepository

AI_METADATA_ANALYSIS_SKIPPED = "AI_METADATA_ANALYSIS_SKIPPED"
AI_METADATA_ANALYSIS_REVIEW_REQUIRED = "AI_METADATA_ANALYSIS_REVIEW_REQUIRED"
METADATA_DTO_DRAFT_REVIEW_REQUIRED = "METADATA_DTO_DRAFT_REVIEW_REQUIRED"
DEFAULT_METADATA_ANALYSIS_OBJECT_TYPES = ("PROCEDURE", "TABLE", "VIEW", "FUNCTION")
_JAVA_IDENTIFIER_CLEANUP = re.compile(r"[^0-9A-Za-z_]+")
_JAVA_RESERVED_WORDS = frozenset(
    {
        "abstract",
        "assert",
        "boolean",
        "break",
        "byte",
        "case",
        "catch",
        "char",
        "class",
        "const",
        "continue",
        "default",
        "do",
        "double",
        "else",
        "enum",
        "extends",
        "final",
        "finally",
        "float",
        "for",
        "goto",
        "if",
        "implements",
        "import",
        "instanceof",
        "int",
        "interface",
        "long",
        "native",
        "new",
        "package",
        "private",
        "protected",
        "public",
        "return",
        "short",
        "static",
        "strictfp",
        "super",
        "switch",
        "synchronized",
        "this",
        "throw",
        "throws",
        "transient",
        "try",
        "void",
        "volatile",
        "while",
    }
)


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
    table_columns: dict[str, tuple[dict[str, Any], ...]]
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
        _attach_metadata_target_keys(
            object_depth,
            db_profile_id=request.db_profile_id,
            source_database=source_database,
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
        generated_drafts: list[MetadataGeneratedDraft] = []
        assumptions: list[str] = []
        summary = "결정론적 근거가 없어 metadata analysis를 실행하지 않았습니다."

        if not options.use_llm_analysis:
            review_markers.append(
                _review_marker(
                    AI_METADATA_ANALYSIS_SKIPPED,
                    "useLlmAnalysis=false 요청 옵션으로 Metadata LLM analysis를 건너뛰었습니다.",
                    evidence_refs=_fallback_fact_refs(deterministic_facts),
                )
            )
            all_caveats = _dedupe_strings([*all_caveats, AI_METADATA_ANALYSIS_SKIPPED])
            summary = "요청 옵션에 따라 Metadata LLM analysis를 건너뛰었습니다."
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
                            "Metadata LLM analysis가 실패해 응답에는 결정론적 metadata만 포함합니다. "
                            f"code={getattr(exc, 'code', exc.__class__.__name__)}"
                        ),
                        evidence_refs=_fallback_fact_refs(deterministic_facts),
                    )
                )
                all_caveats = _dedupe_strings([*all_caveats, AI_METADATA_ANALYSIS_SKIPPED])
                summary = "model gateway 실패 후 Metadata LLM analysis를 건너뛰었습니다."
        else:
            review_markers.append(
                _review_marker(
                    AI_METADATA_ANALYSIS_SKIPPED,
                    "deterministic fact id가 없어 Metadata LLM analysis를 건너뛰었습니다.",
                    evidence_refs=["metadata.analysis.no_fact"],
                )
            )
            all_caveats = _dedupe_strings([*all_caveats, AI_METADATA_ANALYSIS_SKIPPED])

        if options.generate_dto_drafts:
            generated_drafts = _build_metadata_generated_drafts(
                object_profiles=[
                    dict(profile) for profile in object_depth.object_profiles
                ],
                table_columns=object_depth.table_columns,
                dto_readiness=[item.to_response() for item in dto_readiness],
            )
            if not generated_drafts:
                review_markers.append(
                    _review_marker(
                        METADATA_DTO_DRAFT_REVIEW_REQUIRED,
                        (
                            "generateDtoDrafts=true request could not produce a "
                            "DTO_DRAFT preview because TABLE/VIEW column metadata "
                            "was unavailable."
                        ),
                        evidence_refs=_fallback_fact_refs(deterministic_facts),
                    )
                )
                all_caveats = _dedupe_strings(
                    [*all_caveats, METADATA_DTO_DRAFT_REVIEW_REQUIRED]
                )

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
                request.object_types or DEFAULT_METADATA_ANALYSIS_OBJECT_TYPES
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
            generatedDrafts=generated_drafts,
            aiToolEvidence=ai_tool_evidence,
            deterministicFacts=deterministic_facts,
            reviewMarkers=marker_models,
            assumptions=assumptions,
            caveats=all_caveats,
            reviewRequired=bool(
                blockers
                or all_caveats
                or marker_models
                or any(draft.review_required for draft in generated_drafts)
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
            profile = _profile_for(
                profiles,
                object_ref,
                str(data.get("objectType") or "TABLE"),
            )
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
        table_columns={
            object_ref: tuple(columns)
            for object_ref, columns in table_columns.items()
        },
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
            object_types=tuple(request.object_types or DEFAULT_METADATA_ANALYSIS_OBJECT_TYPES),
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
            "요청 옵션으로 AI metadata tool orchestration을 건너뛰었습니다.",
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
            "설정된 model gateway가 metadata tool planning을 제공하지 않습니다.",
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
                    "live PPM latency와 비용 제어를 위해 AI metadata analysis planning round를 "
                    "줄였습니다."
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
            f"metadata analysis용 internal MCP registry 설정이 실패했습니다: {exc.__class__.__name__}.",
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
            fallback_requests = deterministic_fallback_tool_requests(
                db_profile_id=db_profile_id,
                target=_analysis_target(metadata),
                tool_names=policy.tool_names,
                max_tool_calls=max_tool_calls - len(tool_results),
            )
            component_invocations.append(
                {
                    "stage": "ai_metadata_tool_planning",
                    "toolName": "metadata_tool_planner",
                    "status": REVIEW_STATUS,
                    "latencyMs": 0,
                    "evidenceCount": 0,
                    "toolRequestCount": len(fallback_requests),
                    "errorCode": getattr(exc, "code", exc.__class__.__name__),
                }
            )
            if not fallback_requests:
                review_markers.append(
                    _review_marker(
                        AI_METADATA_ANALYSIS_SKIPPED,
                        (
                            "Metadata tool planning이 실패해 baseline metadata로 분석을 계속했습니다. "
                            f"code={getattr(exc, 'code', exc.__class__.__name__)}"
                        ),
                        evidence_refs=_fallback_fact_refs(
                            [*metadata.get("deterministicFacts", []), *deterministic_facts]
                        ),
                    )
                )
                caveats.append(AI_METADATA_ANALYSIS_SKIPPED)
                break
            plan = _fallback_tool_plan(
                fallback_requests,
                evidence_refs=_fallback_fact_refs(
                    [*metadata.get("deterministicFacts", []), *deterministic_facts]
                ),
                detail_code=getattr(exc, "code", exc.__class__.__name__),
            )
            caveats.append(AI_TOOL_PLANNER_DETERMINISTIC_FALLBACK)
        else:
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
            if not plan.tool_requests and not tool_results:
                fallback_requests = deterministic_fallback_tool_requests(
                    db_profile_id=db_profile_id,
                    target=_analysis_target(metadata),
                    tool_names=policy.tool_names,
                    max_tool_calls=max_tool_calls - len(tool_results),
                )
                if fallback_requests:
                    plan = _fallback_tool_plan(
                        fallback_requests,
                        evidence_refs=_fallback_fact_refs(
                            [*metadata.get("deterministicFacts", []), *deterministic_facts]
                        ),
                        detail_code="EMPTY_TOOL_PLAN",
                    )
                    caveats.append(AI_TOOL_PLANNER_DETERMINISTIC_FALLBACK)
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
                            "계획된 요청을 모두 실행하기 전에 AI metadata analysis tool call budget을 "
                            "소진했습니다."
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
                        str(decision.message or "AI metadata tool request가 차단되었습니다."),
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
                        f"AI metadata tool invocation이 MCP error {exc.code}로 실패했습니다.",
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


def _analysis_target(metadata: dict[str, Any]) -> dict[str, Any] | None:
    target = metadata.get("target")
    if isinstance(target, dict):
        return target
    targets = metadata.get("targets")
    if isinstance(targets, list) and targets and isinstance(targets[0], dict):
        identity = targets[0].get("objectIdentity")
        if isinstance(identity, dict):
            return identity
    return None


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
                    f"Metadata search로 {identity.type} "
                    f"{identity.schema_name}.{identity.name}을 확인했습니다."
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
        targetKey=target_key_for_target(
            source_profile or db_profile_id,
            {"type": target.type, "schema": target.schema_name, "name": target.name},
            database=source_database or db_profile_id,
        ),
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


def _attach_metadata_target_keys(
    object_depth: MetadataObjectDepth,
    *,
    db_profile_id: str,
    source_database: str,
) -> None:
    for profile in object_depth.object_profiles:
        profile["targetKey"] = target_key_for_ref(
            db_profile_id=db_profile_id,
            database=source_database,
            object_type=str(profile.get("objectType") or "OBJECT"),
            target_ref=str(profile.get("objectRef") or ""),
        )
    graph = object_depth.dependency_graph
    for node in graph.get("nodes", []):
        if not isinstance(node, dict):
            continue
        node["targetKey"] = target_key_for_ref(
            db_profile_id=db_profile_id,
            database=source_database,
            object_type=str(node.get("objectType") or "OBJECT"),
            target_ref=str(node.get("objectRef") or ""),
        )
    for item in object_depth.dto_readiness:
        item["targetKey"] = target_key_for_ref(
            db_profile_id=db_profile_id,
            database=source_database,
            object_type="TABLE",
            target_ref=str(item.get("objectRef") or ""),
        )


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
                    "의존성 closure에 "
                    f"노드 {summary.get('nodeCount', 0)}개, "
                    f"엣지 {summary.get('edgeCount', 0)}개, "
                    f"근거 보강 필요 항목 {summary.get('reviewRequiredCount', 0)}개가 있습니다."
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
            f"{profile['objectType']} {profile['objectRef']} 오브젝트 프로파일입니다. "
            f"컬럼 {profile['columnCount']}개, constraint {profile['constraintCount']}개, "
            f"index {profile['indexCount']}개를 포함합니다."
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
            "Metadata dependency graph 프로파일입니다. "
            f"노드 {len(dependency_graph.get('nodes', []))}개, "
            f"엣지 {len(dependency_graph.get('edges', []))}개, "
            f"미해결 항목 {len(dependency_graph.get('unresolved', []))}개를 포함합니다."
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
                            f"컬럼 {len(missing_descriptions)}개에 확정된 description 또는 "
                            "logical name이 필요합니다."
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
                            f"nullable column {len(nullable_columns)}개와 "
                            f"review-required description {len(missing_descriptions)}개는 "
                            "DTO field 검토가 필요합니다."
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
                        f"테이블에 PK {profile['primaryKeyCount']}개, "
                        f"FK {profile['foreignKeyCount']}개, "
                        f"constraint 총 {profile['constraintCount']}개가 있습니다."
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
                                f"{constraint.get('name')} constraint가 "
                                f"{ref_schema}.{ref_table}을 참조합니다."
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
                    summary="이 table 프로파일에는 constraint metadata가 없습니다.",
                    status="REVIEW_REQUIRED",
                    evidence_refs=refs,
                )
            )
        if indexes:
            groups.setdefault("INDEX", []).append(
                _insight(
                    code="TABLE_INDEX_SUMMARY",
                    object_ref=object_ref,
                    summary=f"metadata evidence 기준 index {len(indexes)}개가 있습니다.",
                    status="INFERRED_DESCRIPTION",
                    evidence_refs=refs,
                )
            )
        elif profile["objectType"] == "TABLE" and profile["columnCount"]:
            groups.setdefault("INDEX", []).append(
                _insight(
                    code="INDEX_METADATA_MISSING",
                    object_ref=object_ref,
                    summary="이 table 프로파일에는 index metadata가 없습니다.",
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
            reasons.append("DTO readiness v1은 TABLE object를 가장 깊게 평가합니다.")
        if not columns:
            reasons.append("Column metadata를 사용할 수 없습니다.")
        if profile["primaryKeyCount"] == 0 and profile["objectType"] == "TABLE":
            reasons.append("Primary key metadata가 확정되지 않았습니다.")
        if float(profile["descriptionCoverage"]) < 1 and columns:
            reasons.append("Column 또는 table description 검토가 필요합니다.")
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


def _build_metadata_generated_drafts(
    *,
    object_profiles: list[dict[str, Any]],
    table_columns: dict[str, tuple[dict[str, Any], ...]],
    dto_readiness: list[dict[str, Any]],
) -> list[MetadataGeneratedDraft]:
    readiness_by_ref = {
        str(item.get("objectRef") or ""): item
        for item in dto_readiness
        if str(item.get("objectRef") or "").strip()
    }
    drafts: list[MetadataGeneratedDraft] = []
    for profile in object_profiles:
        object_ref = str(profile.get("objectRef") or "").strip()
        object_type = str(profile.get("objectType") or "").strip()
        if object_type not in {"TABLE", "VIEW"}:
            continue
        columns = [dict(column) for column in table_columns.get(object_ref, ())]
        if not object_ref or not columns:
            continue
        readiness = readiness_by_ref.get(object_ref, {})
        evidence_refs = _dedupe_strings(
            [
                *[str(ref) for ref in profile.get("sourceFactIds", [])],
                *[str(ref) for ref in profile.get("evidenceRefs", [])],
                *[str(ref) for ref in readiness.get("evidenceRefs", [])],
            ]
        )
        review_reasons = _metadata_dto_review_reasons(
            profile=profile,
            columns=columns,
            readiness=readiness,
        )
        class_name = _metadata_dto_class_name(object_ref)
        drafts.append(
            MetadataGeneratedDraft.model_validate(
                {
                    "artifactType": "DTO_DRAFT",
                    "objectRef": object_ref,
                    "targetKey": profile.get("targetKey"),
                    "fileName": f"{class_name}.java",
                    "language": "java",
                    "content": _render_metadata_dto_draft(
                        object_ref=object_ref,
                        target_key=str(profile.get("targetKey") or ""),
                        object_type=object_type,
                        class_name=class_name,
                        columns=columns,
                        evidence_refs=evidence_refs,
                        review_reasons=review_reasons,
                    ),
                    "evidenceRefs": evidence_refs,
                    "reviewRequired": bool(review_reasons or profile.get("reviewRequired")),
                    "reviewReasons": review_reasons,
                }
            )
        )
    return drafts


def _metadata_dto_review_reasons(
    *,
    profile: dict[str, Any],
    columns: list[dict[str, Any]],
    readiness: dict[str, Any],
) -> list[str]:
    reasons = [str(reason) for reason in readiness.get("reviewReasons", [])]
    object_type = str(profile.get("objectType") or "")
    if object_type == "VIEW":
        reasons.append("VIEW DTO draft requires SELECT shape and updateability review.")
    if object_type == "TABLE" and int(profile.get("primaryKeyCount") or 0) == 0:
        reasons.append("Primary key metadata is not confirmed.")
    for column in columns:
        name = str(column.get("name") or "UNKNOWN_COLUMN")
        db_type = str(column.get("dataType") or column.get("typeName") or "").strip()
        if not db_type:
            reasons.append(f"{name} has no DB type evidence.")
        elif not _known_metadata_db_type(db_type):
            reasons.append(f"{name} uses DB type {db_type}; Java type mapping needs review.")
        if _metadata_bool(column.get("isNullable")):
            reasons.append(f"{name} is nullable; business null handling needs review.")
        if not str(column.get("description") or "").strip() and str(
            column.get("descriptionStatus") or ""
        ) != "CONFIRMED":
            reasons.append(f"{name} has no confirmed description.")
    return _dedupe_strings(reasons)


def _render_metadata_dto_draft(
    *,
    object_ref: str,
    target_key: str,
    object_type: str,
    class_name: str,
    columns: list[dict[str, Any]],
    evidence_refs: list[str],
    review_reasons: list[str],
) -> str:
    field_specs = _metadata_dto_field_specs(columns)
    java_types = {str(field["javaType"]) for field in field_specs}
    lines = [
        "/**",
        " * Metadata DTO draft generated from sanitized MSSQL metadata.",
        " * artifactType=DTO_DRAFT",
        f" * objectRef={_java_comment_text(object_ref)}",
        f" * objectType={_java_comment_text(object_type)}",
    ]
    if target_key:
        lines.append(f" * targetKey={_java_comment_text(target_key)}")
    lines.extend(
        [
            f" * evidenceRefs={_java_comment_text(', '.join(evidence_refs[:5]) or 'none')}",
            " * REVIEW_REQUIRED: validate package, naming, domain semantics, "
            "and null handling before use.",
            " */",
        ]
    )
    imports = java_imports_for_types(java_types)
    for import_name in imports:
        lines.append(f"import {import_name};")
    if imports:
        lines.append("")
    lines.append(f"public class {class_name} {{")
    if review_reasons:
        lines.append("")
        lines.append("    /**")
        lines.append("     * REVIEW_REQUIRED:")
        for reason in review_reasons[:8]:
            lines.append(f"     * - {_java_comment_text(reason)}")
        lines.append("     */")
    for field in field_specs:
        lines.append("")
        lines.append(
            "    /** "
            f"DB column={_java_comment_text(str(field['physicalName']))}; "
            f"dbType={_java_comment_text(str(field['dbType']))}; "
            f"nullable={str(field['nullable']).lower()}; "
            f"primaryKey={str(field['primaryKey']).lower()}; "
            f"evidence={_java_comment_text(', '.join(evidence_refs[:3]) or 'none')}; "
            f"{_java_comment_text(str(field['review']))} */"
        )
        lines.append(f"    private {field['javaType']} {field['fieldName']};")
    for field in field_specs:
        field_name = str(field["fieldName"])
        java_type = str(field["javaType"])
        method_suffix = upper_first(field_name)
        lines.extend(
            [
                "",
                f"    public {java_type} get{method_suffix}() {{",
                f"        return {field_name};",
                "    }",
                "",
                f"    public void set{method_suffix}({java_type} {field_name}) {{",
                f"        this.{field_name} = {field_name};",
                "    }",
            ]
        )
    lines.append("}")
    return ensure_trailing_newline("\n".join(lines))


def _metadata_dto_field_specs(columns: list[dict[str, Any]]) -> list[dict[str, Any]]:
    specs: list[dict[str, Any]] = []
    seen_fields: set[str] = set()
    for index, column in enumerate(columns, start=1):
        physical_name = str(column.get("name") or f"COLUMN_{index}").strip()
        field_name = _metadata_java_field_name(physical_name)
        if field_name in seen_fields:
            field_name = f"{field_name}{index}"
        seen_fields.add(field_name)
        raw_db_type = str(column.get("dataType") or column.get("typeName") or "").strip()
        db_type = raw_db_type or "nvarchar"
        review_notes = []
        if _metadata_bool(column.get("isNullable")):
            review_notes.append("REVIEW_REQUIRED nullable")
        if not str(column.get("description") or "").strip() and str(
            column.get("descriptionStatus") or ""
        ) != "CONFIRMED":
            review_notes.append("REVIEW_REQUIRED description")
        if not raw_db_type:
            review_notes.append("REVIEW_REQUIRED type missing")
        elif not _known_metadata_db_type(db_type):
            review_notes.append("REVIEW_REQUIRED type mapping")
        specs.append(
            {
                "physicalName": physical_name,
                "fieldName": field_name,
                "dbType": db_type,
                "javaType": java_type_for_db_type(db_type),
                "nullable": _metadata_bool(column.get("isNullable")),
                "primaryKey": _metadata_bool(column.get("isPrimaryKey")),
                "review": "; ".join(review_notes) or "metadata-backed candidate",
            }
        )
    return specs


def _metadata_dto_class_name(object_ref: str) -> str:
    object_name = object_ref.rsplit(".", 1)[-1]
    cleaned = _JAVA_IDENTIFIER_CLEANUP.sub("_", object_name.strip("[]"))
    parts = [part for part in cleaned.split("_") if part]
    if not parts:
        return "MetadataDto"
    return "".join(part[:1].upper() + part[1:].lower() for part in parts) + "Dto"


def _metadata_java_field_name(physical_name: str) -> str:
    cleaned = _JAVA_IDENTIFIER_CLEANUP.sub("_", physical_name.strip().strip("[]"))
    if "_" in cleaned or cleaned.isupper():
        field_name = snake_to_lower_camel(cleaned)
    else:
        field_name = cleaned[:1].lower() + cleaned[1:]
    if not field_name:
        field_name = "reviewRequiredField"
    if field_name[0].isdigit():
        field_name = f"field{field_name}"
    if field_name in _JAVA_RESERVED_WORDS:
        field_name = f"{field_name}Value"
    return field_name


def _known_metadata_db_type(db_type: str) -> bool:
    normalized = db_type.strip().lower().split("(", 1)[0]
    return normalized in {
        "bigint",
        "binary",
        "bit",
        "char",
        "date",
        "datetime",
        "datetime2",
        "decimal",
        "image",
        "int",
        "money",
        "nchar",
        "ntext",
        "numeric",
        "nvarchar",
        "smallint",
        "smallmoney",
        "smalldatetime",
        "text",
        "time",
        "tinyint",
        "uniqueidentifier",
        "varbinary",
        "varchar",
    }


def _metadata_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "y"}
    return bool(value)


def _java_comment_text(value: str) -> str:
    return value.replace("*/", "* /").replace("\r", " ").replace("\n", " ").strip()


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
