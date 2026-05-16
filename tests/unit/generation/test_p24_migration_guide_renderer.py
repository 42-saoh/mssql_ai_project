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
    evaluate_p24_migration_guide_quality,
    render_artifact,
)
from ai_agent_generation.migration_guide import P24_SECTION_TITLES

ROOT = Path(__file__).resolve().parents[3]
FIXTURE = ROOT / "fixtures" / "eval" / "sp_migration_guide_quality_p24_v1.yaml"


def test_p24_analysis_doc_emits_required_sections_and_evidence_refs() -> None:
    scenario = _scenario("p24_complex_dynamic_cross_db_extract")
    artifact = render_artifact(ArtifactType.SP_ANALYSIS_DOC, _context_from_scenario(scenario))

    for section_id in P24_REQUIRED_SECTION_IDS:
        assert f"<!-- section:{section_id} -->" in artifact.content
        assert f"## {P24_SECTION_TITLES[section_id]}" not in artifact.content
    assert "## 1. SP 개요 및 기본 정보" in artifact.content
    assert "## sp_overview" not in artifact.content
    assert "| 항목 | 값 | 상태 | 근거 |" in artifact.content
    assert "| 기능/분기 | 조건/트리거 | 상태 | 요약 | 근거 |" in artifact.content
    assert "ev_p24_complex_dynamic_sql" in artifact.content
    assert "ev_p24_complex_cross_db" in artifact.content
    assert "UNSUPPORTED_CROSS_DB_CLAIM_REVIEW" in artifact.content
    assert "status=REVIEW_REQUIRED" in artifact.content


def test_p24_migration_strategy_uses_llm_guide_and_conversion_insights() -> None:
    scenario = _scenario("p24_simple_read_only_lookup")
    context = _context_from_scenario(
        scenario,
        llm_analysis={
            "conversionGuidance": [
                {
                    "code": "DTO_FIELD_MAPPING",
                    "summary": "read-only projection field를 DTO 초안 메모에 매핑합니다.",
                    "status": "REVIEW_REQUIRED",
                    "evidenceRefs": ["ev_p24_simple_proc"],
                }
            ],
            "migrationGuideInsights": [
                {
                    "section": "migration_strategy",
                    "summary": "전환 출력은 draft-only readiness note로 유지합니다.",
                    "status": "REVIEW_REQUIRED",
                    "evidenceRefs": ["ev_p24_simple_proc"],
                    "whatToExtractNext": "metadata-only appendix 결과를 확인합니다.",
                }
            ],
        },
    )
    artifact = render_artifact(ArtifactType.SP_ANALYSIS_DOC, context)

    assert "llmInsightBoundary: `LLM_INFERENCE_REVIEW_REQUIRED`" in artifact.content
    assert "llmConversionGuidance: DTO_FIELD_MAPPING" in artifact.content
    assert "llmMigrationGuideInsight: migration_strategy" in artifact.content
    assert "whatToExtractNext=metadata-only appendix 결과를 확인합니다." in artifact.content
    assert "generated_source_application: `not_performed`" in artifact.content


def test_p24_llm_guide_insights_are_placed_in_matching_sections() -> None:
    scenario = _scenario("p24_complex_dynamic_cross_db_extract")
    context = _context_from_scenario(
        scenario,
        llm_analysis={
            "migrationGuideInsights": [
                {
                    "section": "dependency_inventory",
                    "summary": "dynamic SQL 의존성은 확정 dependency가 아니라 검토 항목입니다.",
                    "status": "REVIEW_REQUIRED",
                    "evidenceRefs": ["ev_p24_complex_dynamic_sql"],
                    "whatToExtractNext": "dependency closure evidence를 확인합니다.",
                }
            ],
        },
    )
    artifact = render_artifact(ArtifactType.SP_ANALYSIS_DOC, context)
    dependency_section = artifact.content.split("<!-- section:dependency_inventory -->", 1)[1]
    dependency_section = dependency_section.split("<!-- section:dml_impact_matrix -->", 1)[0]

    assert "llmInsightBoundary: `LLM_INFERENCE_REVIEW_REQUIRED`" in dependency_section
    assert "llmMigrationGuideInsight: dependency_inventory" in dependency_section
    assert "dependency closure evidence를 확인합니다." in dependency_section


def test_p24_dependency_report_includes_dml_call_flow_and_readiness_note() -> None:
    scenario = _scenario("p24_medium_transactional_branching_dml")
    artifact = render_artifact(ArtifactType.DEPENDENCY_REPORT, _context_from_scenario(scenario))

    assert "## dependency_table" in artifact.content
    assert "<!-- section:dependency_inventory -->" in artifact.content
    assert "## 의존성 상세 목록" in artifact.content
    assert "<!-- section:dml_impact_matrix -->" in artifact.content
    assert "## 테이블별 DML 영향" in artifact.content
    assert "<!-- section:call_flow -->" in artifact.content
    assert "## 분기별 호출 흐름" in artifact.content
    assert "PPM.dbo.P24_ShipmentDecisionAudit" in artifact.content
    assert "TRANSACTIONAL_DML_REVIEW_REQUIRED" in artifact.content
    assert "generated_source_application: `not_performed`" not in artifact.content


def test_p24_renderer_emits_confirmed_needs_verification_metrics_and_manual_queries() -> None:
    scenario = _scenario("p24_complex_dynamic_cross_db_extract")
    artifact = render_artifact(ArtifactType.SP_ANALYSIS_DOC, _context_from_scenario(scenario))

    assert "### 확인됨" in artifact.content
    assert "### 검증 필요" in artifact.content
    assert "다음 추출 항목" in artifact.content
    assert "| 테이블 | SELECT | INSERT | UPDATE | DELETE | MERGE |" in artifact.content
    assert "| Phase | 주요 읽기 | 주요 쓰기 | 위험/검토점 | 상태 | 근거 |" in artifact.content
    assert "DYNAMIC_SQL_SIGNAL" in artifact.content
    assert "CROSS_DB_REFERENCE" in artifact.content
    assert "<!-- section:metadata_extraction_appendix -->" in artifact.content
    assert "## 10. 수동 메타데이터 추출 부록" in artifact.content
    assert "definition_hash_length" in artifact.content
    assert "sys.dm_sql_referenced_entities" in artifact.content
    assert "CREATE PROCEDURE" not in artifact.content


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
    assert report["status"] == "PASSED"
    assert report["productionReady"] is False
    assert report["storageSafetyFindings"] == []
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


def _fixture() -> dict[str, Any]:
    return yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))


def _scenario(fixture_id: str) -> dict[str, Any]:
    return {
        scenario["fixture_id"]: scenario
        for scenario in _fixture()["scenarios"]
    }[fixture_id]


def _context_from_scenario(
    scenario: Mapping[str, Any],
    *,
    llm_analysis: Mapping[str, Any] | None = None,
) -> GenerationContext:
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
                "llmAnalysis": llm_analysis or {},
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
