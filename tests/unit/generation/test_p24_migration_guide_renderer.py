from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import yaml
from ai_agent_domain import ArtifactType
from ai_agent_generation import (
    P24_REQUIRED_SECTION_IDS,
    GenerationContext,
    build_migration_guide_payload,
    evaluate_p24_migration_guide_quality,
    render_artifact,
)

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "fixtures" / "eval" / "sp_migration_guide_quality_p24_v1.yaml"


def test_p24_analysis_doc_keeps_hidden_anchors_inside_p36_flow() -> None:
    scenario = _scenario("p24_complex_dynamic_cross_db_extract")
    artifact = render_artifact(ArtifactType.SP_ANALYSIS_DOC, _context_from_scenario(scenario))

    for section_id in P24_REQUIRED_SECTION_IDS:
        assert f"<!-- section:{section_id} -->" in artifact.content
    assert "## 1. SP 개요 (Overview)" in artifact.content
    assert "## 6. Appendix" in artifact.content
    assert "ev_p24_complex_dynamic_sql" in artifact.content
    assert "CREATE PROCEDURE" not in artifact.content


def test_p24_dependency_report_is_p36_evidence_dossier() -> None:
    scenario = _scenario("p24_medium_transactional_branching_dml")
    artifact = render_artifact(ArtifactType.DEPENDENCY_REPORT, _context_from_scenario(scenario))

    assert "## generation_evidence_summary" in artifact.content
    assert "## sql_statement_evidence" in artifact.content
    assert "PPM.dbo.P24_ShipmentDecisionAudit" in artifact.content
    assert "full SP definition" in artifact.content


def test_p24_quality_report_contract_is_exact_and_sanitized() -> None:
    fixture = _fixture()
    scenario = _scenario("p24_simple_read_only_lookup")
    context = _context_from_scenario(scenario)
    artifacts = (
        render_artifact(ArtifactType.SP_ANALYSIS_DOC, context),
        render_artifact(ArtifactType.DEPENDENCY_REPORT, context),
    )

    report = evaluate_p24_migration_guide_quality(
        scenario=scenario,
        artifacts=artifacts,
        thresholds=fixture["quality_thresholds"],
    )
    serialized = json.dumps(report, ensure_ascii=False, sort_keys=True)

    assert list(report) == fixture["report_contract"]["fields"]
    assert report["productionReady"] is False
    assert "raw_prompt" not in serialized
    assert "raw_sp_definition" not in serialized
    assert "raw_openai_response_text" not in serialized
    assert "CREATE PROCEDURE" not in serialized


def test_p24_quality_report_flags_raw_sql_marker_without_echoing_text() -> None:
    fixture = _fixture()
    scenario = _scenario("p24_simple_read_only_lookup")
    context = _context_from_scenario(scenario)
    artifact = render_artifact(ArtifactType.SP_ANALYSIS_DOC, context)

    report = evaluate_p24_migration_guide_quality(
        scenario=scenario,
        artifacts=(artifact,),
        thresholds=fixture["quality_thresholds"],
        additional_storage_payloads=({"safe_field": "CREATE PROCEDURE dbo.demo"},),
    )
    serialized = json.dumps(report, ensure_ascii=False, sort_keys=True)

    assert report["status"] == "FAILED"
    assert report["storageSafetyFindings"] == ["PROCEDURE_TEXT_MARKER_PRESENT"]
    assert "CREATE PROCEDURE dbo.demo" not in serialized


def test_dependency_inventory_renders_full_table_names_and_descriptions() -> None:
    guide = build_migration_guide_payload(
        target_ref="dbo.usp_FullInventory",
        db_profile_id="ppm",
        metadata={
            "evidenceRefs": [
                {
                    "type": "MSSQL_METADATA",
                    "objectRef": "dbo.usp_FullInventory",
                    "locator": "fixture#/procedure",
                }
            ],
            "tableSchemas": [
                {
                    "schema": "dbo",
                    "tableName": "PCS_CTRT",
                    "description": "Contract master table",
                    "descriptionStatus": "CONFIRMED",
                    "columns": [],
                }
            ],
        },
        static_analysis={
            "dependencies": {"table_references": []},
            "migrationGuideStaticMetrics": {
                "dmlOperations": [
                    {
                        "operation": "SELECT",
                        "targetRef": "PPM.dbo.PCS_CTRT",
                        "evidenceRef": "static.dml.select.ppm_dbo_pcs_ctrt",
                    },
                    {
                        "operation": "UPDATE",
                        "targetRef": "PPM.dbo.PCS_CTRT",
                        "evidenceRef": "static.dml.update.ppm_dbo_pcs_ctrt",
                    },
                    {
                        "operation": "SELECT",
                        "targetRef": "ERP.dbo.XXEAI_TRX_HEADER_II",
                        "evidenceRef": "static.dml.select.erp_dbo_xxeai_trx_header_ii",
                    },
                    {
                        "operation": "SELECT",
                        "targetRef": "ERP.dbo.PCS_CTRT",
                        "evidenceRef": "static.dml.select.erp_dbo_pcs_ctrt",
                    },
                ],
                "complexityMetrics": [],
            },
        },
        llm_analysis={},
        input_params=[],
        result_shape=[],
        sample_id="full-inventory",
    )
    context = GenerationContext.from_mapping(
        {
            "sampleId": "full-inventory",
            "request": {
                "entityName": "FullInventory",
                "spName": "dbo.usp_FullInventory",
                "description": "fixture",
                "migrationGuide": guide,
                "inputParams": [],
                "resultShape": [],
                "llmAnalysis": {},
            },
        }
    )

    artifact = render_artifact(ArtifactType.SP_ANALYSIS_DOC, context)

    assert "| 종류 | 객체 | description | operation |" in artifact.content
    assert "`PPM.dbo.PCS_CTRT`" in artifact.content
    assert "Contract master table" in artifact.content
    assert "SELECT, UPDATE" in artifact.content
    assert "`ERP.dbo.XXEAI_TRX_HEADER_II`" in artifact.content
    assert "| table | `ERP.dbo.XXEAI_TRX_HEADER_II` | REVIEW_REQUIRED | SELECT |" in artifact.content
    assert "| table | `ERP.dbo.PCS_CTRT` | REVIEW_REQUIRED | SELECT |" in artifact.content


def _fixture() -> dict[str, Any]:
    return yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))


def _scenario(fixture_id: str) -> dict[str, Any]:
    return {
        scenario["fixture_id"]: scenario
        for scenario in _fixture()["scenarios"]
    }[fixture_id]


def _context_from_scenario(scenario: Mapping[str, Any]) -> GenerationContext:
    appendix = scenario.get("appendix_mappings", {}) or {}
    return GenerationContext.from_mapping(
        {
            "sampleId": scenario["fixture_id"],
            "request": {
                "systemCode": "P24",
                "businessCodeLv1": "migration",
                "businessCodeLv2": scenario["complexity"],
                "entityName": _entity_name(str(scenario["target_ref"])),
                "resourceName": scenario["fixture_id"].replace("_", "-"),
                "description": "P24 sanitized SP migration guide fixture",
                "generationMode": "migrationGuide",
                "tableName": scenario["target_ref"],
                "spName": scenario["target_ref"],
                "inputParams": [
                    {
                        "name": parameter["name"],
                        "dbType": parameter["sanitized_type"],
                        "required": False,
                    }
                    for parameter in appendix.get("parameters", []) or []
                ],
                "resultShape": [
                    field["name"] for field in appendix.get("result_fields", []) or []
                ],
                "migrationGuide": scenario,
                "llmAnalysis": {},
            },
            "evidence": {
                "sources": [
                    {
                        "type": ref["type"],
                        "name": ref["object_ref"],
                        "reason": ref["id"],
                        "locator": ref["locator"],
                    }
                    for ref in scenario["evidence_refs"]
                ],
                "assumptions": ["P24 fixture-first renderer test."],
            },
        }
    )


def _entity_name(target_ref: str) -> str:
    raw_name = target_ref.rsplit(".", 1)[-1]
    return "".join(part[:1].upper() + part[1:] for part in raw_name.split("_") if part)
