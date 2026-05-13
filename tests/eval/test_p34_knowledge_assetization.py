from __future__ import annotations

import json
from pathlib import Path

import yaml
from ai_agent_domain import CanonicalAnalysisModel
from api_app.knowledge_service import export_knowledge
from api_app.schemas import KnowledgeExportRequest, SPAnalysisRequest
from api_app.workflow import WorkflowService

from tests.unit.api.fake_repository import MemoryWorkflowRepository

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "fixtures" / "eval" / "knowledge_assetization_p34_v1.yaml"


def _fixture() -> dict:
    return yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))


def test_p34_fixture_declares_knowledge_assetization_contract() -> None:
    fixture = _fixture()
    assert fixture["version"] == "knowledge_assetization_p34_v1"
    assert fixture["production_ready"] is False
    scenarios = {scenario["id"]: scenario for scenario in fixture["scenarios"]}
    assert set(scenarios) == {
        "sp_workflow_knowledge_assets",
        "metadata_analysis_knowledge_assets",
        "adversarial_raw_leakage_blocked",
        "stable_version_reuse",
    }
    assert "CANONICAL_ANALYSIS" in scenarios["sp_workflow_knowledge_assets"][
        "expected_asset_kinds"
    ]


def test_p34_sp_workflow_materializes_sanitized_knowledge_assets_and_export(monkeypatch) -> None:
    monkeypatch.setenv("P21_LIVE_PORTAL_GATE", "0")
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")
    monkeypatch.setenv("LLM_ENABLE_REMOTE", "0")
    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)
    request = SPAnalysisRequest.model_validate(
        {
            "dbProfileId": "master",
            "target": {
                "type": "PROCEDURE",
                "schema": "dbo",
                "name": "usp_GetOrderSummary",
            },
            "outputs": ["SP_ANALYSIS_DOCUMENT", "DEPENDENCY_REPORT"],
            "options": {
                "llmProfileId": "openai_fast_test",
                "persistKnowledge": True,
            },
        }
    )

    _request, job = service.submit_sp_analysis(request)
    assert job.status.value == "VALIDATION_COMPLETE", f"{job.error_code}: {job.error_message}"
    assets = repository.list_job_knowledge_assets(job.job_id)

    assert assets is not None
    assert {asset.asset_kind for asset in assets} == {
        "SP_ANALYSIS",
        "DEPENDENCY_EVIDENCE",
        "METADATA_PROFILE",
        "DTO_READINESS",
        "CANONICAL_ANALYSIS",
    }
    dependency = next(asset for asset in assets if asset.asset_kind == "DEPENDENCY_EVIDENCE")
    fact_graph = repository.list_knowledge_facts(
        dependency.asset_id,
        dependency.current_version_id or "",
    )
    assert fact_graph is not None
    facts, edges = fact_graph
    assert facts
    assert any(fact.fact_id.startswith(("mcp.", "canonical.")) for fact in facts)
    assert edges
    fact_ids = {fact.fact_id for fact in facts}
    assert all(edge.from_fact_id in fact_ids for edge in edges)
    assert all(edge.to_fact_id in fact_ids for edge in edges)

    export = export_knowledge(
        repository=repository,
        request=KnowledgeExportRequest.model_validate(
            {"assetIds": [dependency.asset_id], "format": "GRAPH_JSON"}
        ),
    )
    payload = json.loads(export.content)
    assert payload["nodes"]
    assert payload["edges"]
    lowered = export.content.lower()
    assert "create procedure" not in lowered
    assert "rawresponse" not in lowered
    assert "rowdata" not in lowered
    assert "secret-value" not in lowered


def test_p34_canonical_analysis_model_v2_accepts_knowledge_extension() -> None:
    payload = {
        "schema_version": "CanonicalAnalysisModel.v2",
        "analysis_version": "analysis-local-v0.2",
        "snapshot_id": "snap-1",
        "registry_version_refs": [
            {"registry_type": "GENERATOR", "version": "knowledge_assetization@0.1.0"}
        ],
        "procedure": {
            "identifier": {
                "schema_name": "dbo",
                "procedure_name": "usp_Order",
                "full_name": "dbo.usp_Order",
            }
        },
        "dependencies": {},
        "patterns": {
            "transaction": {"name": "transaction", "detected": False},
            "try_catch": {"name": "try_catch", "detected": False},
            "dynamic_sql": {"name": "dynamic_sql", "detected": False},
            "temp_table": {"name": "temp_table", "detected": False},
            "cursor": {"name": "cursor", "detected": False},
            "multi_result_set": {"name": "multi_result_set", "detected": False},
        },
        "evidence_refs": [
            {"source": "mcp", "snippet": "dbo.usp_Order", "status": "OBSERVED"}
        ],
        "evidence_assessment": {
            "status": "OBSERVED",
            "evidence_ref_count": 1,
            "observed_ref_count": 1,
        },
        "overall_confidence": {
            "score": 0.7,
            "status": "REVIEW_REQUIRED",
            "rationale": "Draft knowledge asset.",
        },
        "analysisSubject": {
            "objectType": "PROCEDURE",
            "schema": "dbo",
            "name": "usp_Order",
            "fullName": "dbo.usp_Order",
        },
        "metadataProfiles": [
            {
                "objectRef": "dbo.TB_ORDER",
                "objectType": "TABLE",
                "metrics": {"columnCount": 2},
                "evidenceRefs": ["metadata.profile.abc"],
                "sourceFactIds": ["metadata.profile.abc"],
            }
        ],
        "dependencyEvidence": [
            {
                "factId": "mcp.get_dependency_closure.abc",
                "objectRef": "dbo.TB_ORDER",
                "dependencyType": "READS",
                "status": "OBSERVED",
                "evidenceRefs": ["mcp.dep.abc"],
            }
        ],
        "dtoReadiness": [
            {
                "objectRef": "dbo.TB_ORDER",
                "status": "PARTIAL",
                "fieldCount": 2,
                "reviewReasons": ["COLUMN_DESCRIPTION_GAP"],
                "evidenceRefs": ["metadata.profile.abc"],
            }
        ],
        "factGraph": {
            "nodes": [
                {
                    "factId": "metadata.profile.abc",
                    "factType": "METADATA_PROFILE",
                    "objectRef": "dbo.TB_ORDER",
                    "status": "OBSERVED",
                    "evidenceRefs": ["metadata.profile.abc"],
                }
            ],
            "edges": [],
        },
        "knowledgeAssetRefs": [
            {
                "assetId": "know_1",
                "versionId": "knowv_1",
                "assetKind": "CANONICAL_ANALYSIS",
                "contentHash": "abc",
            }
        ],
    }

    model = CanonicalAnalysisModel.model_validate(payload)

    assert model.schema_version == "CanonicalAnalysisModel.v2"
    assert model.analysis_subject is not None
    assert model.metadata_profiles[0].object_ref == "dbo.TB_ORDER"
    assert model.knowledge_asset_refs[0].asset_kind == "CANONICAL_ANALYSIS"
