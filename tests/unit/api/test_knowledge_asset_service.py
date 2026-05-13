from __future__ import annotations

import json

import pytest
from api_app.knowledge_service import (
    export_knowledge,
    persist_sp_workflow_knowledge,
    sanitize_knowledge_review_note,
    sanitize_knowledge_payload,
)
from api_app.metadata_gateway import MetadataCollectionResult
from api_app.repositories import AgentRunRecord, KnowledgePersistenceError
from api_app.schemas import KnowledgeExportRequest
from tests.unit.api.fake_repository import MemoryWorkflowRepository


def _request_and_job(repository: MemoryWorkflowRepository):
    request = repository.create_request(
        db_profile_id="master",
        target={"type": "PROCEDURE", "schema": "dbo", "name": "usp_Order"},
        outputs=("SP_ANALYSIS_DOCUMENT",),
        options={"persistKnowledge": True},
        request_hash="hash",
        correlation_id="corr-knowledge",
        idempotency_key=None,
    )
    job = repository.create_job(request.request_id, correlation_id="corr-knowledge")
    return request, job


def _metadata() -> MetadataCollectionResult:
    return MetadataCollectionResult(
        db_profile_id="master",
        object_ref="dbo.usp_Order",
        snapshot_id="snap-1",
        collected_at="2026-05-13T00:00:00Z",
        evidence_refs=(
            {"type": "MSSQL_METADATA", "objectRef": "dbo.usp_Order", "locator": "mcp"},
        ),
        procedure_definition={"definition": "CREATE PROCEDURE dbo.usp_Order AS SELECT 1"},
        procedure_dependencies={"dependencies": [{"objectType": "TABLE", "schema": "dbo", "name": "TB_ORDER"}]},
        dependency_evidence={
            "summary": {"nodeCount": 2, "edgeCount": 1},
            "nodes": [
                {
                    "id": "dbo.usp_Order",
                    "schema": "dbo",
                    "name": "usp_Order",
                    "objectType": "PROCEDURE",
                    "reviewStatus": "CONFIRMED",
                    "evidenceRefs": ["mcp.dep.1"],
                },
                {
                    "id": "dbo.TB_ORDER",
                    "schema": "dbo",
                    "name": "TB_ORDER",
                    "objectType": "TABLE",
                    "reviewStatus": "CONFIRMED",
                    "evidenceRefs": ["mcp.dep.1"],
                },
            ],
            "edges": [
                {
                    "from": "dbo.usp_Order",
                    "to": "dbo.TB_ORDER",
                    "dependencyType": "READS",
                    "evidenceRefs": ["mcp.dep.1"],
                }
            ],
            "evidenceRefs": [{"objectRef": "dbo.TB_ORDER", "locator": "mcp"}],
        },
        ai_tool_evidence={"toolResults": [], "plannerMetrics": {}},
        deterministic_facts=(
            {
                "id": "mcp.get_table_schema.abc123",
                "type": "MCP_FACT",
                "objectRef": "dbo.TB_ORDER",
                "summary": "table schema",
                "evidenceRefs": ["mcp.schema.1"],
            },
        ),
        table_schemas=(
            {
                "schema": "dbo",
                "tableName": "TB_ORDER",
                "columns": [
                    {"name": "ORDER_ID", "dataType": "int", "description": "PK"},
                    {"name": "SECRET_NOTE", "dataType": "varchar", "secret": "hidden"},
                ],
            },
        ),
    )


def _agent_run(job_id: str) -> AgentRunRecord:
    return AgentRunRecord(
        agent_run_id="agent_knowledge",
        job_id=job_id,
        agent_type="sp_semantic_analysis",
        status="SUCCEEDED",
        target_ref="dbo.usp_Order",
        summary="semantic summary",
        structured_output={
            "businessRules": [
                {
                    "category": "ORDER",
                    "summary": "Loads order rows.",
                    "status": "INFERRED_DESCRIPTION",
                    "evidenceRefs": ["mcp.get_table_schema.abc123"],
                }
            ],
            "reviewMarkers": [],
        },
        model_invocation={
            "provider": "fake",
            "model": "fake",
            "promptHash": "prompt-hash",
            "outputHash": "output-hash",
            "rawResponse": "CREATE PROCEDURE dbo.leak AS SELECT 1",
        },
    )


def test_knowledge_sanitizer_removes_raw_sql_row_data_and_secret_fields() -> None:
    sanitized, markers = sanitize_knowledge_payload(
        {
            "definition": "CREATE PROCEDURE dbo.leak AS SELECT * FROM dbo.Secret",
            "rowData": [{"id": 1}],
            "apiToken": "secret-value",
            "safe": "metadata profile",
        }
    )

    serialized = json.dumps(sanitized, sort_keys=True)
    assert markers
    assert "CREATE PROCEDURE" not in serialized
    assert "secret-value" not in serialized
    assert "contentHash" not in serialized
    assert "length" not in serialized
    assert "snippet" not in serialized
    assert "metadata profile" in serialized


def test_sp_workflow_knowledge_persists_versions_reuses_hash_and_exports_graph() -> None:
    repository = MemoryWorkflowRepository()
    request, job = _request_and_job(repository)
    metadata = _metadata()
    agent_run = _agent_run(job.job_id)
    static_analysis = {"patterns": {"dynamicSql": False}, "dependencies": ["dbo.TB_ORDER"]}

    first = persist_sp_workflow_knowledge(
        repository=repository,
        job_id=job.job_id,
        request_record=request,
        metadata=metadata,
        static_analysis=static_analysis,
        agent_run=agent_run,
    )
    second = persist_sp_workflow_knowledge(
        repository=repository,
        job_id=job.job_id,
        request_record=request,
        metadata=metadata,
        static_analysis=static_analysis,
        agent_run=agent_run,
    )

    assert {asset.asset_kind for asset in first.assets} == {
        "SP_ANALYSIS",
        "DEPENDENCY_EVIDENCE",
        "METADATA_PROFILE",
        "DTO_READINESS",
        "CANONICAL_ANALYSIS",
    }
    assert [asset.current_version_no for asset in second.assets] == [1, 1, 1, 1, 1]
    assets = repository.list_job_knowledge_assets(job.job_id)
    assert assets is not None
    dependency_asset = next(asset for asset in assets if asset.asset_kind == "DEPENDENCY_EVIDENCE")
    assert dependency_asset.lifecycle_status == "DRAFT"
    facts = repository.list_knowledge_facts(
        dependency_asset.asset_id,
        dependency_asset.current_version_id or "",
    )
    assert facts is not None
    assert any(fact.fact_id.startswith("mcp.") for fact in facts[0])
    assert any(edge.edge_type == "READS" for edge in facts[1])
    fact_ids = {fact.fact_id for fact in facts[0]}
    assert all(edge.from_fact_id in fact_ids for edge in facts[1])
    assert all(edge.to_fact_id in fact_ids for edge in facts[1])

    graph_export = export_knowledge(
        repository=repository,
        request=KnowledgeExportRequest.model_validate(
            {"assetIds": [dependency_asset.asset_id], "format": "GRAPH_JSON"}
        ),
    )
    jsonl_export = export_knowledge(
        repository=repository,
        request=KnowledgeExportRequest.model_validate(
            {"assetIds": [dependency_asset.asset_id], "format": "JSONL"}
        ),
    )
    serialized = f"{graph_export.content}\n{jsonl_export.content}"
    assert graph_export.content_type == "application/json"
    assert jsonl_export.content_type == "application/x-ndjson"
    assert "mcp.get_table_schema.abc123" in serialized
    assert "CREATE PROCEDURE" not in serialized
    assert "hidden" not in serialized


def test_same_content_version_reuse_still_links_each_job() -> None:
    repository = MemoryWorkflowRepository()
    request1, job1 = _request_and_job(repository)
    request2, job2 = _request_and_job(repository)
    metadata = _metadata()
    agent_run1 = _agent_run(job1.job_id)
    agent_run2 = _agent_run(job2.job_id)
    static_analysis = {"patterns": {"dynamicSql": False}, "dependencies": ["dbo.TB_ORDER"]}

    persist_sp_workflow_knowledge(
        repository=repository,
        job_id=job1.job_id,
        request_record=request1,
        metadata=metadata,
        static_analysis=static_analysis,
        agent_run=agent_run1,
    )
    persist_sp_workflow_knowledge(
        repository=repository,
        job_id=job2.job_id,
        request_record=request2,
        metadata=metadata,
        static_analysis=static_analysis,
        agent_run=agent_run2,
    )

    job1_assets = repository.list_job_knowledge_assets(job1.job_id)
    job2_assets = repository.list_job_knowledge_assets(job2.job_id)

    assert job1_assets is not None
    assert job2_assets is not None
    assert {asset.asset_kind for asset in job1_assets} == {
        "SP_ANALYSIS",
        "DEPENDENCY_EVIDENCE",
        "METADATA_PROFILE",
        "DTO_READINESS",
        "CANONICAL_ANALYSIS",
    }
    assert {asset.asset_kind for asset in job2_assets} == {
        "SP_ANALYSIS",
        "DEPENDENCY_EVIDENCE",
        "METADATA_PROFILE",
        "DTO_READINESS",
        "CANONICAL_ANALYSIS",
    }
    job1_sp = next(asset for asset in job1_assets if asset.asset_kind == "SP_ANALYSIS")
    job2_sp = next(asset for asset in job2_assets if asset.asset_kind == "SP_ANALYSIS")
    assert job1_sp.asset_id == job2_sp.asset_id
    assert job1_sp.current_version_id == job2_sp.current_version_id
    assert job1_sp.current_version_no == job2_sp.current_version_no == 1
    assert job2_sp.source_job_id == job1.job_id
    review = repository.review_knowledge_asset_version(
        asset_id=job1_sp.asset_id,
        version_id=job1_sp.current_version_id or "",
        status="REVIEWED",
        reason_code="CURATED_FOR_REUSE",
        note={"comment": "reviewed fixture knowledge"},
        reviewer="reviewer@example.com",
    )
    assert review is not None
    reused = repository.list_job_knowledge_assets(job2.job_id)
    assert reused is not None
    reused_sp = next(asset for asset in reused if asset.asset_kind == "SP_ANALYSIS")
    assert reused_sp.lifecycle_status == "REVIEWED"


def test_changed_content_creates_new_knowledge_version() -> None:
    repository = MemoryWorkflowRepository()
    request, job = _request_and_job(repository)
    metadata = _metadata()
    agent_run = _agent_run(job.job_id)
    persist_sp_workflow_knowledge(
        repository=repository,
        job_id=job.job_id,
        request_record=request,
        metadata=metadata,
        static_analysis={"patterns": {"dynamicSql": False}},
        agent_run=agent_run,
    )
    reviewed_asset = next(
        asset
        for asset in repository.list_job_knowledge_assets(job.job_id) or []
        if asset.asset_kind == "SP_ANALYSIS"
    )
    repository.review_knowledge_asset_version(
        asset_id=reviewed_asset.asset_id,
        version_id=reviewed_asset.current_version_id or "",
        status="REVIEWED",
        reason_code="FIRST_REVIEW",
        note={},
        reviewer="reviewer@example.com",
    )
    persist_sp_workflow_knowledge(
        repository=repository,
        job_id=job.job_id,
        request_record=request,
        metadata=metadata,
        static_analysis={"patterns": {"dynamicSql": True}},
        agent_run=agent_run,
    )

    assets = repository.list_job_knowledge_assets(job.job_id)
    assert assets is not None
    sp_asset = next(asset for asset in assets if asset.asset_kind == "SP_ANALYSIS")
    assert sp_asset.current_version_no == 2
    assert sp_asset.lifecycle_status == "DRAFT"


def test_knowledge_review_history_archived_terminal_and_sanitized_note() -> None:
    repository = MemoryWorkflowRepository()
    request, job = _request_and_job(repository)
    persist_sp_workflow_knowledge(
        repository=repository,
        job_id=job.job_id,
        request_record=request,
        metadata=_metadata(),
        static_analysis={"patterns": {"dynamicSql": False}},
        agent_run=_agent_run(job.job_id),
    )
    asset = next(
        item
        for item in repository.list_job_knowledge_assets(job.job_id) or []
        if item.asset_kind == "SP_ANALYSIS"
    )
    note = sanitize_knowledge_review_note(
        "CREATE PROCEDURE dbo.leak AS SELECT secret-value FROM dbo.Secret"
    )

    review = repository.review_knowledge_asset_version(
        asset_id=asset.asset_id,
        version_id=asset.current_version_id or "",
        status="ARCHIVED",
        reason_code="STALE_DRAFT",
        note=note,
        reviewer="reviewer@example.com",
    )

    assert review is not None
    reviews = repository.list_knowledge_reviews(asset.asset_id)
    assert reviews is not None
    assert reviews[0].to_status == "ARCHIVED"
    serialized = json.dumps(reviews[0].note, sort_keys=True)
    assert "CREATE PROCEDURE" not in serialized
    assert "secret-value" not in serialized
    assert "contentHash" not in serialized
    assert "length" not in serialized
    assert "snippet" not in serialized
    with pytest.raises(KnowledgePersistenceError) as exc_info:
        repository.review_knowledge_asset_version(
            asset_id=asset.asset_id,
            version_id=asset.current_version_id or "",
            status="REVIEWED",
            reason_code="REOPEN_NOT_ALLOWED",
            note={},
            reviewer="reviewer@example.com",
        )
    assert exc_info.value.code == "KNOWLEDGE_LIFECYCLE_TRANSITION_INVALID"
    assert exc_info.value.status_code == 409


def test_knowledge_asset_and_fact_search_filters_and_excludes_archived_by_default() -> None:
    repository = MemoryWorkflowRepository()
    request, job = _request_and_job(repository)
    persist_sp_workflow_knowledge(
        repository=repository,
        job_id=job.job_id,
        request_record=request,
        metadata=_metadata(),
        static_analysis={"patterns": {"dynamicSql": False}},
        agent_run=_agent_run(job.job_id),
    )
    sp_asset = next(
        item
        for item in repository.list_job_knowledge_assets(job.job_id) or []
        if item.asset_kind == "SP_ANALYSIS"
    )
    repository.review_knowledge_asset_version(
        asset_id=sp_asset.asset_id,
        version_id=sp_asset.current_version_id or "",
        status="ARCHIVED",
        reason_code="SEARCH_EXCLUSION",
        note={},
        reviewer="reviewer@example.com",
    )

    active_assets = repository.list_knowledge_assets(asset_kind="SP_ANALYSIS")
    archived_assets = repository.list_knowledge_assets(
        asset_kind="SP_ANALYSIS",
        lifecycle_status="ARCHIVED",
    )
    active_facts = repository.search_knowledge_facts(object_ref="TB_ORDER")
    archived_facts = repository.search_knowledge_facts(
        object_ref="usp_Order",
        lifecycle_status="ARCHIVED",
    )

    assert sp_asset.asset_id not in {asset.asset_id for asset in active_assets}
    assert sp_asset.asset_id in {asset.asset_id for asset in archived_assets}
    assert all(result.lifecycle_status != "ARCHIVED" for result in active_facts)
    assert any(result.lifecycle_status == "ARCHIVED" for result in archived_facts)


def test_export_rejects_mismatched_asset_and_version_selection() -> None:
    repository = MemoryWorkflowRepository()

    with pytest.raises(KnowledgePersistenceError) as exc_info:
        export_knowledge(
            repository=repository,
            request=KnowledgeExportRequest.model_validate(
                {
                    "assetIds": ["know_1"],
                    "versionIds": ["knowv_1", "knowv_2"],
                    "format": "JSONL",
                }
            ),
        )

    assert exc_info.value.code == (
        "KNOWLEDGE_EXPORT_VERSION_SELECTION_INVALID"
    )
    assert exc_info.value.status_code == 422
