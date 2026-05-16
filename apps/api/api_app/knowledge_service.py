from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass
from typing import Any

from ai_agent_runtime.models import stable_json_hash

from api_app.metadata_gateway import MetadataCollectionResult
from api_app.repositories import (
    AgentRunRecord,
    KnowledgeAssetRecord,
    KnowledgeEdgeRecord,
    KnowledgeExportRecord,
    KnowledgeFactRecord,
    KnowledgeFactSearchRecord,
    KnowledgePersistenceError,
    WorkflowRepository,
    KNOWLEDGE_LIFECYCLE_STATUSES,
    prefixed_id,
)
from api_app.schemas import (
    KnowledgeAssetSummary,
    KnowledgeAssetVersion,
    KnowledgeEdge,
    KnowledgeExportRequest,
    KnowledgeExportResponse,
    KnowledgeFact,
    KnowledgeFactGraph,
    KnowledgeFactSearchResult,
)

KNOWLEDGE_ASSET_KINDS = {
    "SP_ANALYSIS",
    "DEPENDENCY_EVIDENCE",
    "METADATA_PROFILE",
    "DTO_READINESS",
    "CANONICAL_ANALYSIS",
}
KNOWLEDGE_EDGE_TYPES = {
    "DEPENDS_ON",
    "DERIVED_FROM",
    "SUPPORTS",
    "READS",
    "WRITES",
    "CALLS",
    "FK_TO",
    "DTO_FIELD_OF",
}
KNOWLEDGE_STORAGE_SANITIZED = "KNOWLEDGE_STORAGE_SANITIZED"
KNOWLEDGE_PERSISTENCE_SKIPPED = "KNOWLEDGE_PERSISTENCE_SKIPPED"
KNOWLEDGE_EXPORT_UNSUPPORTED_FORMAT = "KNOWLEDGE_EXPORT_UNSUPPORTED_FORMAT"
KNOWLEDGE_EXPORT_VERSION_SELECTION_INVALID = "KNOWLEDGE_EXPORT_VERSION_SELECTION_INVALID"
KNOWLEDGE_SEARCH_FILTER_REQUIRED = "KNOWLEDGE_SEARCH_FILTER_REQUIRED"
KNOWLEDGE_LIFECYCLE_TRANSITION_INVALID = "KNOWLEDGE_LIFECYCLE_TRANSITION_INVALID"

_SECRET_KEY_RE = re.compile(
    r"(password|passwd|pwd|secret|token|api[_-]?key|credential|connection[_-]?string)",
    re.IGNORECASE,
)
_RAW_KEY_RE = re.compile(
    r"^(definition|rawDefinition|rawSql|sqlText|rawPrompt|prompt|providerResponse|rawResponse)$",
    re.IGNORECASE,
)
_ROW_KEY_RE = re.compile(r"^(rowData|rows|records|dataRecords|sampleRows)$", re.IGNORECASE)
_SQL_TEXT_RE = re.compile(
    r"(?is)\b(create|alter)\s+(proc|procedure|function|view)\b|"
    r"\b(select|insert|update|delete|merge)\b.{0,240}\b(from|into|set|values)\b"
)


@dataclass(frozen=True)
class KnowledgePersistResult:
    assets: tuple[KnowledgeAssetSummary, ...]
    review_markers: tuple[dict[str, Any], ...] = ()
    caveats: tuple[str, ...] = ()


@dataclass(frozen=True)
class KnowledgeAssetSpec:
    asset_kind: str
    target: dict[str, str]
    payload: dict[str, Any]
    facts: list[dict[str, Any]]
    edges: list[dict[str, Any]]
    content_hash: str


def knowledge_assetization_enabled() -> bool:
    return os.getenv("KNOWLEDGE_ASSETIZATION_ENABLED", "1").strip().lower() not in {
        "0",
        "false",
        "no",
    }


def persist_sp_workflow_knowledge(
    *,
    repository: WorkflowRepository,
    job_id: str,
    request_record,
    metadata: MetadataCollectionResult,
    static_analysis: dict[str, Any] | None,
    agent_run: AgentRunRecord | None,
) -> KnowledgePersistResult:
    if not bool(request_record.options.get("persistKnowledge", True)):
        return _skipped_result("요청 옵션으로 SP workflow knowledge persistence를 건너뛰었습니다.")
    if not knowledge_assetization_enabled():
        return _skipped_result("환경 설정에서 knowledge assetization이 비활성화되어 있습니다.")

    target = {
        "type": str(request_record.target.get("type") or "PROCEDURE"),
        "schema": str(request_record.target.get("schema") or ""),
        "name": str(request_record.target.get("name") or ""),
    }
    static_analysis = static_analysis or {}
    specs = [
        _asset_spec(
            asset_kind="SP_ANALYSIS",
            target=target,
            payload={
                "target": target,
                "staticAnalysis": static_analysis,
                "semanticAnalysis": agent_run.structured_output if agent_run else {},
                "modelInvocation": _model_invocation_summary(agent_run),
                "snapshotId": metadata.snapshot_id,
            },
            facts=[
                *_facts_from_static_analysis(target, static_analysis),
                *_facts_from_structured_output(
                    target=target,
                    structured_output=agent_run.structured_output if agent_run else {},
                ),
            ],
            edges=[],
        ),
        _asset_spec(
            asset_kind="DEPENDENCY_EVIDENCE",
            target=target,
            payload={
                "target": target,
                "dependencyEvidence": metadata.dependency_evidence or {},
                "procedureDependencies": metadata.procedure_dependencies or {},
                "aiToolEvidence": metadata.ai_tool_evidence or {},
            },
            facts=[
                *_facts_from_dependency_evidence(target, metadata.dependency_evidence or {}),
                *_facts_from_deterministic_facts(
                    target=target,
                    facts=metadata.deterministic_facts,
                    fallback_type="MCP_FACT",
                ),
            ],
            edges=_edges_from_dependency_evidence(metadata.dependency_evidence or {}),
        ),
        _asset_spec(
            asset_kind="METADATA_PROFILE",
            target=target,
            payload={
                "target": target,
                "tableSchemas": list(metadata.table_schemas),
                "evidenceRefs": list(metadata.evidence_refs),
            },
            facts=_facts_from_table_schemas(target, metadata.table_schemas),
            edges=[],
        ),
        _asset_spec(
            asset_kind="DTO_READINESS",
            target=target,
            payload={
                "target": target,
                "tableSchemas": list(metadata.table_schemas),
                "status": "REVIEW_REQUIRED",
            },
            facts=_facts_from_dto_readiness(target, metadata.table_schemas),
            edges=[],
        ),
        _asset_spec(
            asset_kind="CANONICAL_ANALYSIS",
            target=target,
            payload=_canonical_asset_payload(
                target=target,
                metadata=metadata,
                static_analysis=static_analysis,
                agent_run=agent_run,
            ),
            facts=_canonical_facts(
                target=target,
                metadata=metadata,
                static_analysis=static_analysis,
                agent_run=agent_run,
            ),
            edges=[],
        ),
    ]
    return _persist_specs(
        repository=repository,
        job_id=job_id,
        db_profile_id=request_record.db_profile_id,
        specs=specs,
    )


def persist_metadata_analysis_knowledge(
    *,
    repository: WorkflowRepository | None,
    request,
    response,
) -> KnowledgePersistResult:
    if not bool(getattr(request.options, "persist_knowledge", True)):
        return _skipped_result("요청 옵션으로 metadata analysis knowledge persistence를 건너뛰었습니다.")
    if not knowledge_assetization_enabled():
        return _skipped_result("환경 설정에서 knowledge assetization이 비활성화되어 있습니다.")
    if repository is None:
        return KnowledgePersistResult(assets=())

    target = _metadata_target(request, response)
    specs = [
        _asset_spec(
            asset_kind="METADATA_PROFILE",
            target=target,
            payload={
                "objectProfiles": [item.to_response() for item in response.object_profiles],
                "insightGroups": [item.to_response() for item in response.insight_groups],
                "deterministicFacts": list(response.deterministic_facts),
            },
            facts=[
                *_facts_from_profiles(response.object_profiles),
                *_facts_from_metadata_profile_deterministic_facts(
                    target=target,
                    facts=response.deterministic_facts,
                ),
            ],
            edges=[],
        ),
        _asset_spec(
            asset_kind="DEPENDENCY_EVIDENCE",
            target=target,
            payload={
                "dependencyGraph": response.dependency_graph.to_response(),
                "aiToolEvidence": response.ai_tool_evidence,
            },
            facts=_facts_from_dependency_graph(response.dependency_graph.to_response()),
            edges=_edges_from_dependency_graph(response.dependency_graph.to_response()),
        ),
        _asset_spec(
            asset_kind="DTO_READINESS",
            target=target,
            payload={
                "dtoReadiness": [item.to_response() for item in response.dto_readiness],
            },
            facts=_facts_from_metadata_dto(response.dto_readiness),
            edges=[],
        ),
    ]
    return _persist_specs(
        repository=repository,
        job_id=None,
        db_profile_id=request.db_profile_id,
        specs=specs,
    )


def export_knowledge(
    *,
    repository: WorkflowRepository,
    request: KnowledgeExportRequest,
) -> KnowledgeExportResponse:
    export_format = request.format
    if export_format not in {"JSONL", "GRAPH_JSON"}:
        raise KnowledgePersistenceError(
            f"Unsupported knowledge export format: {export_format}",
            code=KNOWLEDGE_EXPORT_UNSUPPORTED_FORMAT,
            status_code=422,
        )
    versions = _selected_versions(repository, request.asset_ids, request.version_ids)
    if export_format == "JSONL":
        content_type = "application/x-ndjson"
        lines: list[str] = []
        for asset, version in versions:
            for fact in version.facts:
                lines.append(
                    json.dumps(
                        {
                            "assetId": asset.asset_id,
                            "assetKind": asset.asset_kind,
                            "versionId": version.version_id,
                            "versionNo": version.version_no,
                            "fact": present_knowledge_fact(fact).to_response(),
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                )
        content = "\n".join(lines)
    else:
        content_type = "application/json"
        graph = {
            "assets": [present_knowledge_asset(asset).to_response() for asset, _ in versions],
            "versions": [
                present_knowledge_version(version).to_response() for _, version in versions
            ],
            "nodes": [
                present_knowledge_fact(fact).to_response()
                for _, version in versions
                for fact in version.facts
            ],
            "edges": [
                present_knowledge_edge(edge).to_response()
                for _, version in versions
                for edge in version.edges
            ],
        }
        content = json.dumps(graph, ensure_ascii=False, sort_keys=True)
    content_hash = stable_json_hash({"format": export_format, "content": content})
    record = repository.save_knowledge_export(
        export_format=export_format,
        content_type=content_type,
        content=content,
        content_hash=content_hash,
        asset_ids=list(request.asset_ids),
    )
    return KnowledgeExportResponse(
        exportId=record.export_id,
        format=record.format,
        contentType=record.content_type,
        content=record.content,
        contentHash=record.content_hash,
        assetIds=record.asset_ids,
        createdAt=record.created_at,
    )


def present_knowledge_asset(record: KnowledgeAssetRecord) -> KnowledgeAssetSummary:
    lifecycle_status = _knowledge_lifecycle_status(record.lifecycle_status)
    return KnowledgeAssetSummary(
        assetId=record.asset_id,
        assetKind=record.asset_kind,
        dbProfileId=record.db_profile_id,
        targetType=record.target_type,
        targetSchema=record.target_schema,
        targetName=record.target_name,
        logicalKey=record.logical_key,
        currentVersionId=record.current_version_id,
        currentVersionNo=record.current_version_no,
        contentHash=record.content_hash,
        sourceJobId=record.source_job_id,
        lifecycleStatus=lifecycle_status,
        archivedAt=record.archived_at,
        createdAt=record.created_at,
        updatedAt=record.updated_at,
    )


def present_knowledge_version(record) -> KnowledgeAssetVersion:
    lifecycle_status = _knowledge_lifecycle_status(record.lifecycle_status)
    return KnowledgeAssetVersion(
        versionId=record.version_id,
        assetId=record.asset_id,
        versionNo=record.version_no,
        contentHash=record.content_hash,
        payload=record.payload,
        factCount=len(record.facts),
        edgeCount=len(record.edges),
        sourceJobId=record.source_job_id,
        lifecycleStatus=lifecycle_status,
        archivedAt=record.archived_at,
        createdAt=record.created_at,
    )


def present_knowledge_fact(record: KnowledgeFactRecord) -> KnowledgeFact:
    status = (
        record.status
        if record.status in {"OBSERVED", "INFERRED_DESCRIPTION", "REVIEW_REQUIRED"}
        else "REVIEW_REQUIRED"
    )
    return KnowledgeFact(
        factId=record.fact_id,
        versionId=record.version_id,
        assetId=record.asset_id,
        factType=record.fact_type,
        objectRef=record.object_ref,
        summary=record.summary,
        status=status,
        evidenceRefs=record.evidence_refs,
        payload=record.payload,
        contentHash=record.content_hash,
        createdAt=record.created_at,
    )


def present_knowledge_edge(record: KnowledgeEdgeRecord) -> KnowledgeEdge:
    edge_type = record.edge_type if record.edge_type in KNOWLEDGE_EDGE_TYPES else "DERIVED_FROM"
    return KnowledgeEdge(
        edgeId=record.edge_id,
        versionId=record.version_id,
        assetId=record.asset_id,
        fromFactId=record.from_fact_id,
        toFactId=record.to_fact_id,
        edgeType=edge_type,
        evidenceRefs=record.evidence_refs,
        payload=record.payload,
        createdAt=record.created_at,
    )


def present_fact_graph(
    *,
    asset_id: str,
    version_id: str,
    facts: list[KnowledgeFactRecord],
    edges: list[KnowledgeEdgeRecord],
) -> KnowledgeFactGraph:
    return KnowledgeFactGraph(
        assetId=asset_id,
        versionId=version_id,
        facts=[present_knowledge_fact(fact) for fact in facts],
        edges=[present_knowledge_edge(edge) for edge in edges],
    )


def present_fact_search_result(record: KnowledgeFactSearchRecord) -> KnowledgeFactSearchResult:
    return KnowledgeFactSearchResult(
        assetId=record.asset_id,
        assetKind=record.asset_kind,
        versionId=record.version_id,
        lifecycleStatus=_knowledge_lifecycle_status(record.lifecycle_status),
        fact=present_knowledge_fact(record.fact),
    )


def ensure_knowledge_search_filter(**filters: str | None) -> None:
    if any(str(value or "").strip() for value in filters.values()):
        return
    raise KnowledgePersistenceError(
        "Knowledge fact search requires at least one filter.",
        code=KNOWLEDGE_SEARCH_FILTER_REQUIRED,
        status_code=422,
    )


def _persist_specs(
    *,
    repository: WorkflowRepository,
    job_id: str | None,
    db_profile_id: str,
    specs: list[KnowledgeAssetSpec],
) -> KnowledgePersistResult:
    assets: list[KnowledgeAssetSummary] = []
    markers: list[dict[str, Any]] = []
    caveats: list[str] = []
    for spec in specs:
        if spec.asset_kind not in KNOWLEDGE_ASSET_KINDS:
            continue
        try:
            version = repository.upsert_knowledge_asset(
                job_id=job_id,
                db_profile_id=db_profile_id,
                asset_kind=spec.asset_kind,
                target=spec.target,
                payload=spec.payload,
                facts=spec.facts,
                edges=spec.edges,
                content_hash=spec.content_hash,
            )
        except KnowledgePersistenceError:
            raise
        except Exception as exc:  # pragma: no cover - adapter defensive guard
            raise KnowledgePersistenceError(
                f"{spec.asset_kind} knowledge persistence가 실패했습니다: {exc.__class__.__name__}",
                code="KNOWLEDGE_PERSISTENCE_FAILED",
                status_code=503,
            ) from exc
        asset = repository.get_knowledge_asset(version.asset_id)
        if asset is not None:
            assets.append(present_knowledge_asset(asset))
        if _has_sanitized_marker(spec.payload):
            markers.append(
                _review_marker(
                    KNOWLEDGE_STORAGE_SANITIZED,
                    f"{spec.asset_kind} knowledge payload는 저장 전에 sanitize되었습니다.",
                )
            )
            caveats.append(KNOWLEDGE_STORAGE_SANITIZED)
    return KnowledgePersistResult(
        assets=tuple(assets),
        review_markers=tuple(_dedupe_markers(markers)),
        caveats=tuple(dict.fromkeys(caveats)),
    )


def _asset_spec(
    *,
    asset_kind: str,
    target: dict[str, str],
    payload: dict[str, Any],
    facts: list[dict[str, Any]],
    edges: list[dict[str, Any]],
) -> KnowledgeAssetSpec:
    facts = _dedupe_facts(facts)
    edges = _dedupe_edges(edges)
    sanitized_payload, payload_markers = sanitize_knowledge_payload(payload)
    sanitized_facts, fact_markers = sanitize_knowledge_payload(facts)
    sanitized_edges, edge_markers = sanitize_knowledge_payload(edges)
    all_markers = [*payload_markers, *fact_markers, *edge_markers]
    if all_markers:
        existing = list(sanitized_payload.get("reviewMarkers", []))
        sanitized_payload["reviewMarkers"] = [
            *existing,
            *[
                _review_marker(
                    KNOWLEDGE_STORAGE_SANITIZED,
                    "안전하지 않은 raw knowledge field를 저장 전에 제거했습니다.",
                )
                for _ in all_markers[:1]
            ],
        ]
    content_hash = stable_json_hash(
        {
            "assetKind": asset_kind,
            "target": target,
            "payload": sanitized_payload,
            "facts": sanitized_facts,
            "edges": sanitized_edges,
        }
    )
    return KnowledgeAssetSpec(
        asset_kind=asset_kind,
        target=target,
        payload=sanitized_payload,
        facts=[dict(item) for item in sanitized_facts if isinstance(item, dict)],
        edges=[dict(item) for item in sanitized_edges if isinstance(item, dict)],
        content_hash=content_hash,
    )


def sanitize_knowledge_payload(value: Any) -> tuple[Any, list[str]]:
    markers: list[str] = []

    def sanitize(item: Any, key: str | None = None) -> Any:
        if isinstance(item, dict):
            sanitized: dict[str, Any] = {}
            for child_key, child_value in item.items():
                key_text = str(child_key)
                if (
                    _SECRET_KEY_RE.search(key_text)
                    or _RAW_KEY_RE.match(key_text)
                    or _ROW_KEY_RE.match(key_text)
                ):
                    markers.append(key_text)
                    sanitized[f"redactedField{len(markers)}"] = _redacted_value(child_value)
                    continue
                sanitized[key_text] = sanitize(child_value, key_text)
            return sanitized
        if isinstance(item, list):
            if key and key.lower() in {"rowdata", "rows", "records", "datarecords"}:
                markers.append(key)
                return [
                    {"redacted": True, "reason": "row-like collection removed", "count": len(item)}
                ]
            return [sanitize(child, key) for child in item]
        if isinstance(item, str):
            if key and (_SECRET_KEY_RE.search(key) or _RAW_KEY_RE.match(key)):
                markers.append(key)
                return _redacted_value(item)
            if len(item) > 40 and _SQL_TEXT_RE.search(item):
                markers.append(key or "sqlText")
                return _redacted_value(item)
        return item

    return sanitize(value), markers


def _redacted_value(value: Any) -> dict[str, Any]:
    return {
        "redacted": True,
        "reason": "unsafe knowledge field removed",
        "code": KNOWLEDGE_STORAGE_SANITIZED,
    }


def _unsafe_free_text(value: str) -> bool:
    lowered = value.lower()
    if _SQL_TEXT_RE.search(value):
        return True
    return any(
        marker in lowered
        for marker in (
            "password",
            "passwd",
            "pwd=",
            "secret",
            "token",
            "api_key",
            "apikey",
            "credential",
            "connection string",
        )
    )


def _facts_from_static_analysis(
    target: dict[str, str],
    static_analysis: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    static_analysis = static_analysis or {}
    for key in ("patterns", "dependencies", "resultSets"):
        value = static_analysis.get(key)
        if value:
            facts.append(
                _fact(
                    fact_id=_canonical_fact_id(key, {"target": target, "value": value}),
                    fact_type=f"STATIC_{key.upper()}",
                    object_ref=_target_ref(target),
                    summary=f"정적 분석이 {key} 결과를 생성했습니다.",
                    status="OBSERVED",
                    evidence_refs=_fact_refs(value),
                    payload={key: value},
                )
            )
    return facts


def _facts_from_structured_output(
    *,
    target: dict[str, str],
    structured_output: dict[str, Any],
) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for key, fact_type in (
        ("businessRules", "BUSINESS_RULE"),
        ("modernizationPoints", "MODERNIZATION_POINT"),
        ("riskFlags", "RISK_FLAG"),
        ("conversionGuidance", "CONVERSION_GUIDANCE"),
        ("migrationGuideInsights", "MIGRATION_GUIDE_INSIGHT"),
        ("reviewMarkers", "REVIEW_MARKER"),
    ):
        for item in _dict_items(structured_output.get(key)):
            facts.append(
                _fact(
                    fact_id=_canonical_fact_id(fact_type.lower(), item),
                    fact_type=fact_type,
                    object_ref=_target_ref(target),
                    summary=_ensure_korean_summary(
                        item.get("summary") or item.get("message") or fact_type,
                        fallback=f"{fact_type} 요약입니다.",
                    ),
                    status=str(item.get("status") or "REVIEW_REQUIRED"),
                    evidence_refs=[str(ref) for ref in item.get("evidenceRefs", [])],
                    payload=item,
                )
            )
    return facts


def _facts_from_dependency_evidence(
    target: dict[str, str],
    dependency_evidence: dict[str, Any],
) -> list[dict[str, Any]]:
    nodes = _dict_items(dependency_evidence.get("nodes"))
    facts = [
        _fact(
            fact_id=_canonical_fact_id("dependency_summary", dependency_evidence.get("summary", {})),
            fact_type="DEPENDENCY_SUMMARY",
            object_ref=_target_ref(target),
            summary="의존성 closure 요약입니다.",
            status="REVIEW_REQUIRED" if dependency_evidence.get("reviewRequired") else "OBSERVED",
            evidence_refs=_fact_refs(dependency_evidence),
            payload=dict(dependency_evidence.get("summary") or {}),
        )
    ]
    known_refs: set[str] = set()
    for node in nodes:
        object_ref = _node_ref(node) or _target_ref(target)
        known_refs.add(object_ref)
        if node.get("id"):
            known_refs.add(str(node.get("id")))
        facts.append(
            _fact(
                fact_id=_canonical_fact_id("dependency_node", node),
                fact_type="DEPENDENCY_NODE",
                object_ref=object_ref,
                summary=f"의존성 node {object_ref}입니다.",
                status=_status_from_review(node.get("reviewStatus")),
                evidence_refs=_fact_refs(node),
                payload=node,
            )
        )
    for edge in _dict_items(dependency_evidence.get("edges")):
        for endpoint_key in ("from", "to"):
            endpoint = _edge_endpoint_ref(edge.get(endpoint_key))
            if endpoint in known_refs:
                continue
            known_refs.add(endpoint)
            facts.append(
                _fact(
                    fact_id=_dependency_endpoint_fact_id(endpoint),
                    fact_type="DEPENDENCY_ENDPOINT",
                    object_ref=endpoint,
                    summary=f"의존성 endpoint {endpoint}는 검토가 필요합니다.",
                    status="REVIEW_REQUIRED",
                    evidence_refs=_fact_refs(edge),
                    payload={"objectRef": endpoint, "source": "dependencyEdge"},
                )
            )
    return facts


def _edges_from_dependency_evidence(dependency_evidence: dict[str, Any]) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    node_fact_ids = _dependency_node_fact_id_by_ref(dependency_evidence)
    for edge in _dict_items(dependency_evidence.get("edges")):
        edge_type = _dependency_edge_type(str(edge.get("dependencyType") or "DEPENDS_ON"))
        from_ref = _edge_endpoint_ref(edge.get("from"))
        to_ref = _edge_endpoint_ref(edge.get("to"))
        edges.append(
            {
                "edgeId": _canonical_fact_id("dependency_edge", edge),
                "fromFactId": node_fact_ids.get(from_ref) or _dependency_endpoint_fact_id(from_ref),
                "toFactId": node_fact_ids.get(to_ref) or _dependency_endpoint_fact_id(to_ref),
                "edgeType": edge_type,
                "evidenceRefs": _fact_refs(edge),
                "payload": edge,
            }
        )
    return edges


def _facts_from_table_schemas(
    target: dict[str, str],
    table_schemas,
) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for table in table_schemas:
        object_ref = _table_ref(table) or _target_ref(target)
        columns = _dict_items(table.get("columns"))
        facts.append(
            _fact(
                fact_id=_canonical_fact_id("metadata_profile", table),
                fact_type="METADATA_PROFILE",
                object_ref=object_ref,
                summary=f"{object_ref} 프로파일에는 컬럼 {len(columns)}개가 있습니다.",
                status="OBSERVED" if columns else "REVIEW_REQUIRED",
                evidence_refs=_fact_refs(table),
                payload={
                    "columnCount": len(columns),
                    "columns": columns,
                    "schema": table.get("schema"),
                    "tableName": table.get("tableName"),
                },
            )
        )
    return facts


def _facts_from_dto_readiness(
    target: dict[str, str],
    table_schemas,
) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for table in table_schemas:
        object_ref = _table_ref(table) or _target_ref(target)
        columns = _dict_items(table.get("columns"))
        nullable_without_description = [
            str(column.get("name") or "")
            for column in columns
            if not str(column.get("description") or "").strip()
        ]
        facts.append(
            _fact(
                fact_id=_canonical_fact_id("dto_readiness", table),
                fact_type="DTO_READINESS",
                object_ref=object_ref,
                summary=f"{object_ref}에는 DTO 후보 필드 {len(columns)}개가 있습니다.",
                status="PARTIAL" if nullable_without_description else "OBSERVED",
                evidence_refs=_fact_refs(table),
                payload={
                    "fieldCount": len(columns),
                    "reviewReasons": (
                        ["COLUMN_DESCRIPTION_GAP"] if nullable_without_description else []
                    ),
                },
            )
        )
    return facts


def _facts_from_deterministic_facts(
    *,
    target: dict[str, str],
    facts,
    fallback_type: str,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for fact in facts or []:
        if not isinstance(fact, dict):
            continue
        fact_id = str(fact.get("id") or "")
        if not fact_id:
            continue
        output.append(
            _fact(
                fact_id=fact_id,
                fact_type=str(fact.get("type") or fallback_type),
                object_ref=str(fact.get("objectRef") or _target_ref(target)),
                summary=_ensure_korean_summary(
                    fact.get("summary") or fact_id,
                    fallback=f"{fact_id} fact 요약입니다.",
                ),
                status=str(fact.get("status") or "OBSERVED"),
                evidence_refs=_fact_refs(fact),
                payload=fact,
            )
        )
    return output


def _facts_from_metadata_profile_deterministic_facts(
    *,
    target: dict[str, str],
    facts,
) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    for fact in facts or []:
        if not isinstance(fact, dict):
            continue
        fact_id = str(fact.get("id") or "")
        if not fact_id.startswith("metadata.profile."):
            continue
        output.append(
            _fact(
                fact_id=fact_id,
                fact_type="METADATA_PROFILE",
                object_ref=str(fact.get("objectRef") or _target_ref(target)),
                summary=_ensure_korean_summary(
                    fact.get("summary") or fact_id,
                    fallback=f"{fact_id} fact 요약입니다.",
                ),
                status=str(fact.get("status") or "OBSERVED"),
                evidence_refs=_fact_refs(fact),
                payload=fact,
            )
        )
    return output


def _facts_from_profiles(profiles) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for profile in profiles:
        payload = profile.to_response()
        fact_id = next(
            (ref for ref in payload.get("sourceFactIds", []) if ref.startswith("metadata.profile.")),
            _canonical_fact_id("metadata_profile", payload),
        )
        facts.append(
            _fact(
                fact_id=fact_id,
                fact_type="METADATA_PROFILE",
                object_ref=str(payload.get("objectRef") or ""),
                summary=(
                    f"{payload.get('objectRef')}에는 컬럼 {payload.get('columnCount', 0)}개가 있습니다."
                ),
                status="REVIEW_REQUIRED" if payload.get("reviewRequired") else "OBSERVED",
                evidence_refs=[str(ref) for ref in payload.get("evidenceRefs", [])],
                payload=payload,
            )
        )
    return facts


_KOREAN_TEXT_RE = re.compile(r"[\uac00-\ud7a3]")


def _ensure_korean_summary(value: Any, *, fallback: str) -> str:
    summary = str(value or "").strip()
    if summary and _KOREAN_TEXT_RE.search(summary):
        return summary
    if summary:
        return f"{fallback} 기존 요약: {summary}"
    return fallback


def _facts_from_dependency_graph(graph: dict[str, Any]) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    nodes = _dict_items(graph.get("nodes"))
    known_refs = {str(node.get("objectRef") or "") for node in nodes}
    for node in nodes:
        facts.append(
            _fact(
                fact_id=_canonical_fact_id("graph_node", node),
                fact_type="DEPENDENCY_NODE",
                object_ref=str(node.get("objectRef") or ""),
                summary=f"의존성 graph node {node.get('objectRef')}입니다.",
                status="REVIEW_REQUIRED" if node.get("status") == "REVIEW_REQUIRED" else "OBSERVED",
                evidence_refs=[str(ref) for ref in node.get("evidenceRefs", [])],
                payload=node,
            )
        )
    for edge in _dict_items(graph.get("edges")):
        for endpoint_key in ("from", "to"):
            endpoint = _edge_endpoint_ref(edge.get(endpoint_key))
            if endpoint in known_refs:
                continue
            known_refs.add(endpoint)
            facts.append(
                _fact(
                    fact_id=_graph_endpoint_fact_id(endpoint),
                    fact_type="DEPENDENCY_ENDPOINT",
                    object_ref=endpoint,
                summary=f"의존성 graph endpoint {endpoint}는 근거 보강이 필요합니다.",
                    status="REVIEW_REQUIRED",
                    evidence_refs=[str(ref) for ref in edge.get("evidenceRefs", [])],
                    payload={"objectRef": endpoint, "source": "dependencyGraphEdge"},
                )
            )
    return facts


def _edges_from_dependency_graph(graph: dict[str, Any]) -> list[dict[str, Any]]:
    edges: list[dict[str, Any]] = []
    node_fact_ids = _graph_node_fact_id_by_ref(graph)
    for edge in _dict_items(graph.get("edges")):
        from_ref = _edge_endpoint_ref(edge.get("from"))
        to_ref = _edge_endpoint_ref(edge.get("to"))
        edges.append(
            {
                "edgeId": _canonical_fact_id("graph_edge", edge),
                "fromFactId": node_fact_ids.get(from_ref) or _graph_endpoint_fact_id(from_ref),
                "toFactId": node_fact_ids.get(to_ref) or _graph_endpoint_fact_id(to_ref),
                "edgeType": _dependency_edge_type(str(edge.get("relationshipType") or "")),
                "evidenceRefs": [str(ref) for ref in edge.get("evidenceRefs", [])],
                "payload": edge,
            }
        )
    return edges


def _facts_from_metadata_dto(items) -> list[dict[str, Any]]:
    facts: list[dict[str, Any]] = []
    for item in items:
        payload = item.to_response()
        facts.append(
            _fact(
                fact_id=_canonical_fact_id("dto_readiness", payload),
                fact_type="DTO_READINESS",
                object_ref=str(payload.get("objectRef") or ""),
                summary=(
                    f"{payload.get('objectRef')} DTO readiness 상태는 {payload.get('status')}입니다."
                ),
                status=str(payload.get("status") or "REVIEW_REQUIRED"),
                evidence_refs=[str(ref) for ref in payload.get("evidenceRefs", [])],
                payload=payload,
            )
        )
    return facts


def _canonical_asset_payload(
    *,
    target: dict[str, str],
    metadata: MetadataCollectionResult,
    static_analysis: dict[str, Any],
    agent_run: AgentRunRecord | None,
) -> dict[str, Any]:
    return {
        "schemaVersion": "CanonicalAnalysisModel.v2",
        "analysisSubject": {
            "type": target["type"],
            "schema": target["schema"],
            "name": target["name"],
            "fullName": _target_ref(target),
        },
        "snapshotId": metadata.snapshot_id,
        "registryVersionRefs": [
            {"registryType": "GENERATOR", "version": "knowledge_assetization@0.1.0"}
        ],
        "staticAnalysis": static_analysis,
        "semanticAnalysis": agent_run.structured_output if agent_run else {},
        "metadataProfiles": list(metadata.table_schemas),
        "dependencyEvidence": metadata.dependency_evidence or {},
        "dtoReadiness": [
            fact["payload"] for fact in _facts_from_dto_readiness(target, metadata.table_schemas)
        ],
        "factGraph": {
            "facts": [
                fact["factId"]
                for fact in _canonical_facts(
                    target=target,
                    metadata=metadata,
                    static_analysis=static_analysis,
                    agent_run=agent_run,
                )
            ],
            "edges": _edges_from_dependency_evidence(metadata.dependency_evidence or {}),
        },
    }


def _canonical_facts(
    *,
    target: dict[str, str],
    metadata: MetadataCollectionResult,
    static_analysis: dict[str, Any],
    agent_run: AgentRunRecord | None,
) -> list[dict[str, Any]]:
    facts = [
        *_facts_from_static_analysis(target, static_analysis),
        *_facts_from_structured_output(
            target=target,
            structured_output=agent_run.structured_output if agent_run else {},
        ),
        *_facts_from_dependency_evidence(target, metadata.dependency_evidence or {}),
        *_facts_from_table_schemas(target, metadata.table_schemas),
        *_facts_from_dto_readiness(target, metadata.table_schemas),
    ]
    return _dedupe_facts(facts)


def _selected_versions(
    repository: WorkflowRepository,
    asset_ids: list[str],
    version_ids: list[str],
) -> list[tuple[KnowledgeAssetRecord, Any]]:
    if version_ids and len(version_ids) != len(asset_ids):
        raise KnowledgePersistenceError(
            "versionIds must be empty or have the same length as assetIds.",
            code=KNOWLEDGE_EXPORT_VERSION_SELECTION_INVALID,
            status_code=422,
        )
    selected: list[tuple[KnowledgeAssetRecord, Any]] = []
    version_by_asset = dict(zip(asset_ids, version_ids, strict=False))
    for asset_id in asset_ids:
        asset = repository.get_knowledge_asset(asset_id)
        if asset is None:
            raise KnowledgePersistenceError(
                f"Unknown knowledge asset: {asset_id}",
                code="KNOWLEDGE_ASSET_NOT_FOUND",
                status_code=404,
            )
        version_id = version_by_asset.get(asset_id) or asset.current_version_id
        if not version_id:
            raise KnowledgePersistenceError(
                f"Knowledge asset has no current version: {asset_id}",
                code="KNOWLEDGE_ASSET_NOT_FOUND",
                status_code=404,
            )
        version = repository.get_knowledge_asset_version(asset_id, version_id)
        if version is None:
            raise KnowledgePersistenceError(
                f"Unknown knowledge asset version: {version_id}",
                code="KNOWLEDGE_ASSET_NOT_FOUND",
                status_code=404,
            )
        selected.append((asset, version))
    return selected


def _metadata_target(request, response) -> dict[str, str]:
    target = request.target
    if target is None and response.targets:
        target = response.targets[0].object_identity
    if target is None:
        name = str(request.query or "query")
        return {"type": "QUERY", "schema": "", "name": name}
    return {
        "type": target.type,
        "schema": target.schema_name,
        "name": target.name,
    }


def _model_invocation_summary(agent_run: AgentRunRecord | None) -> dict[str, Any]:
    if agent_run is None:
        return {}
    invocation = dict(agent_run.model_invocation)
    return {
        key: invocation.get(key)
        for key in (
            "provider",
            "model",
            "modelProfileId",
            "modelRegistryRef",
            "reasoningEffort",
            "promptVersion",
            "outputSchemaVersion",
            "inputHash",
            "promptHash",
            "outputHash",
            "status",
            "tokenUsage",
            "latencyMs",
            "componentInvocations",
        )
        if key in invocation
    }


def _fact(
    *,
    fact_id: str,
    fact_type: str,
    object_ref: str,
    summary: str,
    status: str,
    evidence_refs: list[str],
    payload: dict[str, Any],
) -> dict[str, Any]:
    normalized_status = status if status in {"OBSERVED", "INFERRED_DESCRIPTION"} else "REVIEW_REQUIRED"
    content_hash = stable_json_hash(
        {
            "factId": fact_id,
            "factType": fact_type,
            "objectRef": object_ref,
            "payload": payload,
        }
    )
    return {
        "factId": fact_id,
        "factType": fact_type,
        "objectRef": object_ref,
        "summary": summary[:1000],
        "status": normalized_status,
        "evidenceRefs": list(dict.fromkeys(evidence_refs)),
        "payload": payload,
        "contentHash": content_hash,
    }


def _canonical_fact_id(kind: str, payload: Any) -> str:
    return f"canonical.{kind}.{stable_json_hash(payload)[:12]}"


def _dependency_node_fact_id_by_ref(dependency_evidence: dict[str, Any]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for node in _dict_items(dependency_evidence.get("nodes")):
        fact_id = _canonical_fact_id("dependency_node", node)
        object_ref = _node_ref(node)
        if object_ref:
            mapping[object_ref] = fact_id
        node_id = str(node.get("id") or "")
        if node_id:
            mapping[node_id] = fact_id
    return mapping


def _dependency_endpoint_fact_id(object_ref: str) -> str:
    return _canonical_fact_id("dependency_endpoint_review", {"objectRef": object_ref})


def _graph_node_fact_id_by_ref(graph: dict[str, Any]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for node in _dict_items(graph.get("nodes")):
        object_ref = str(node.get("objectRef") or "")
        if object_ref:
            mapping[object_ref] = _canonical_fact_id("graph_node", node)
    return mapping


def _graph_endpoint_fact_id(object_ref: str) -> str:
    return _canonical_fact_id("graph_endpoint_review", {"objectRef": object_ref})


def _edge_endpoint_ref(value: Any) -> str:
    return str(value or "").strip() or "UNKNOWN_ENDPOINT"


def _target_ref(target: dict[str, str]) -> str:
    schema = str(target.get("schema") or "").strip()
    name = str(target.get("name") or "").strip()
    return f"{schema}.{name}" if schema else name


def _table_ref(table: dict[str, Any]) -> str:
    schema = str(table.get("schema") or "").strip()
    name = str(table.get("tableName") or table.get("name") or "").strip()
    return f"{schema}.{name}" if schema and name else ""


def _node_ref(node: dict[str, Any]) -> str:
    schema = str(node.get("schema") or "").strip()
    name = str(node.get("name") or node.get("objectName") or "").strip()
    return f"{schema}.{name}" if schema and name else str(node.get("id") or "")


def _dependency_edge_type(value: str) -> str:
    normalized = value.upper()
    if "WRITE" in normalized:
        return "WRITES"
    if "CALL" in normalized or "EXEC" in normalized:
        return "CALLS"
    if "READ" in normalized:
        return "READS"
    if "FK" in normalized or "FOREIGN" in normalized:
        return "FK_TO"
    if "SUPPORT" in normalized:
        return "SUPPORTS"
    return "DEPENDS_ON"


def _status_from_review(value: Any) -> str:
    return "REVIEW_REQUIRED" if str(value or "").upper() == "REVIEW_REQUIRED" else "OBSERVED"


def _knowledge_lifecycle_status(value: Any) -> str:
    status = str(value or "DRAFT").strip().upper()
    return status if status in KNOWLEDGE_LIFECYCLE_STATUSES else "DRAFT"


def _fact_refs(value: Any) -> list[str]:
    refs: list[str] = []
    if isinstance(value, dict):
        for key in ("evidenceRefs", "sourceFactIds"):
            raw = value.get(key)
            if isinstance(raw, list):
                for item in raw:
                    if isinstance(item, str):
                        refs.append(item)
                    elif isinstance(item, dict):
                        refs.append(
                            str(
                                item.get("id")
                                or item.get("objectRef")
                                or item.get("locator")
                                or item
                            )
                        )
        for child in value.values():
            refs.extend(_fact_refs(child))
    elif isinstance(value, list | tuple):
        for child in value:
            refs.extend(_fact_refs(child))
    return list(dict.fromkeys(ref for ref in refs if ref))


def _dict_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list | tuple):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _dedupe_facts(facts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    output: list[dict[str, Any]] = []
    for fact in facts:
        fact_id = str(fact.get("factId") or "")
        if not fact_id or fact_id in seen:
            continue
        seen.add(fact_id)
        output.append(fact)
    return output


def _dedupe_edges(edges: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    output: list[dict[str, Any]] = []
    for edge in edges:
        edge_id = str(edge.get("edgeId") or "")
        if not edge_id:
            edge_id = "|".join(
                str(edge.get(key) or "")
                for key in ("fromFactId", "from", "toFactId", "to", "edgeType", "type")
            )
        if not edge_id or edge_id in seen:
            continue
        seen.add(edge_id)
        output.append(edge)
    return output


def _dedupe_markers(markers: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    output: list[dict[str, Any]] = []
    for marker in markers:
        key = str(marker.get("code") or marker.get("message") or "")
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(marker)
    return output


def _review_marker(code: str, message: str) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "status": "REVIEW_REQUIRED",
        "evidenceRefs": [],
    }


def _skipped_result(message: str) -> KnowledgePersistResult:
    return KnowledgePersistResult(
        assets=(),
        review_markers=(_review_marker(KNOWLEDGE_PERSISTENCE_SKIPPED, message),),
        caveats=(KNOWLEDGE_PERSISTENCE_SKIPPED,),
    )


def _has_sanitized_marker(payload: dict[str, Any]) -> bool:
    return any(
        isinstance(marker, dict) and marker.get("code") == KNOWLEDGE_STORAGE_SANITIZED
        for marker in payload.get("reviewMarkers", [])
    )
