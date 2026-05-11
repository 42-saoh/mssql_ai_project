from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
PROMPTS = ROOT / "ops" / "codex-parallel" / "prompts"
MANIFEST = ROOT / "ops" / "codex-parallel" / "REQUEST_MANIFEST.yaml"
CONTRACT = ROOT / "spec" / "eval" / "p24_sp_migration_guide_quality_contract.yaml"
TASK = ROOT / "tasks" / "0024-sp-migration-guide-quality.md"
P24_FIXTURE = ROOT / "fixtures" / "eval" / "sp_migration_guide_quality_p24_v1.yaml"

P24_PROMPTS = {
    "P24A": "24a_sp_migration_guide_contract_assets.md",
    "P24B": "24b_sp_migration_guide_fixture_suite.md",
    "P24C": "24c_sp_migration_guide_renderer_eval.md",
    "P24D": "24d_sp_migration_guide_docs_readiness.md",
}

REQUIRED_PROMPT_SECTIONS = (
    "## 공통 운영 철학",
    "## 목표",
    "## 읽어야 할 기준 파일",
    "## 허용 수정 경로",
    "## 금지 경로",
    "## 구현 범위",
    "## 검증 명령",
    "## Blocker 보고 기준",
)

REQUIRED_GUIDE_SECTIONS = {
    "sp_overview",
    "feature_branch_taxonomy",
    "dependency_inventory",
    "dml_impact_matrix",
    "call_flow",
    "critical_phase_analysis",
    "complexity_risk_metrics",
    "migration_strategy",
    "appendix_mappings",
    "evidence_assumptions_review",
}

FORBIDDEN_STORAGE_FIELDS = [
    "raw_prompt",
    "raw_sp_definition",
    "raw_openai_response_text",
    "row_data",
    "secrets",
]


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_p24_contract_declares_migration_guide_quality_boundaries() -> None:
    contract = _load_yaml(CONTRACT)

    assert contract["contract_id"] == "p24_sp_migration_guide_quality@0.1.0"
    assert contract["phase"] == "P24"
    assert contract["production_ready"] is False
    assert contract["status"] == "contract_ready"
    assert contract["reference_policy"]["user_reference_name"] == "MIGRATION_GUIDE.md"
    assert contract["reference_policy"]["usage"] == "structure_and_quality_reference_only"
    assert contract["reference_policy"]["copy_reference_content_to_repo"] is False
    assert contract["reference_policy"]["copy_raw_sp_text_to_repo"] is False
    assert contract["runtime_profiles"]["fast_test"]["default_model"] == "gpt-5-nano"
    assert contract["scope"]["existing_artifact_types"] == [
        "SP_ANALYSIS_DOC",
        "DEPENDENCY_REPORT",
    ]
    assert contract["scope"]["new_persisted_artifact_types_allowed"] is False
    assert contract["scope"]["java_mybatis_output_policy"] == "draft_only_readiness_notes"


def test_p24_contract_required_sections_and_thresholds_match_plan() -> None:
    contract = _load_yaml(CONTRACT)
    thresholds = contract["quality_thresholds"]

    assert {item["id"] for item in contract["scope"]["required_sections"]} == (
        REQUIRED_GUIDE_SECTIONS
    )
    assert thresholds["required_section_coverage_min"] == 1.0
    assert thresholds["evidence_linked_claim_coverage_min"] == 0.9
    assert thresholds["dml_matrix_coverage_min"] == 0.9
    assert thresholds["branch_call_flow_coverage_min"] == 0.85
    assert thresholds["unsupported_claim_review_required_ratio_min"] == 1.0
    assert thresholds["forbidden_storage_findings_max"] == 0
    assert contract["dependency_inventory_requirements"]["operation_fields"] == [
        "SELECT",
        "INSERT",
        "UPDATE",
        "DELETE",
    ]


def test_p24_contract_report_fields_and_review_required_obligations() -> None:
    contract = _load_yaml(CONTRACT)

    assert contract["scope"]["report_fields"] == [
        "status",
        "productionReady",
        "scores",
        "thresholds",
        "evidenceRefs",
        "sectionCoverage",
        "reviewRequiredFindings",
        "storageSafetyFindings",
    ]
    assert contract["validator_obligation"] == {
        "unsupported_dependency_claims": "REVIEW_REQUIRED",
        "unsupported_table_claims": "REVIEW_REQUIRED",
        "unsupported_function_claims": "REVIEW_REQUIRED",
        "unsupported_cross_database_claims": "REVIEW_REQUIRED",
        "low_evidence_business_rule_claims": "REVIEW_REQUIRED",
    }
    assert contract["storage_policy"]["forbidden_payload_fields"] == FORBIDDEN_STORAGE_FIELDS
    for field in FORBIDDEN_STORAGE_FIELDS:
        assert field not in contract["storage_policy"]["allowed_trace_fields"]
    assert all(contract["forbidden_behavior"].values())


def test_p24_prompts_capture_split_contract_and_policy_rules() -> None:
    for prompt_name in P24_PROMPTS.values():
        text = (PROMPTS / prompt_name).read_text(encoding="utf-8")
        for section in REQUIRED_PROMPT_SECTIONS:
            assert section in text
        assert "P24" in text
        assert "production_ready: false" in text
        assert "`gpt-5-nano`" in text
        assert "`PLF`" in text
        assert "`PPM`" in text
        assert "PLF fallback" in text
        assert "raw prompt" in text
        assert "raw SP definition" in text
        assert "raw OpenAI response text" in text
        assert "REVIEW_REQUIRED" in text
        assert "SP_ANALYSIS_DOC" in text or prompt_name.endswith("docs_readiness.md")
        assert "DEPENDENCY_REPORT" in text or prompt_name.endswith("docs_readiness.md")


def test_p24_manifest_declares_split_tracks_and_merge_order() -> None:
    manifest = _load_yaml(MANIFEST)
    tracks = {
        track["id"]: track
        for wave in manifest["waves"]
        for track in wave["tracks"]
    }

    assert "spec/eval/p24_sp_migration_guide_quality_contract.yaml" in manifest["basis"]
    assert [item for item in manifest["merge_order"] if item.startswith("P24")] == [
        "P24A",
        "P24B",
        "P24C",
        "P24D",
    ]
    assert tracks["P24A"]["depends_on"] == ["P23D"]
    assert tracks["P24B"]["depends_on"] == ["P24A"]
    assert tracks["P24C"]["depends_on"] == ["P24B"]
    assert tracks["P24D"]["depends_on"] == ["P24C"]
    for track_id, prompt_name in P24_PROMPTS.items():
        assert tracks[track_id]["prompt"] == f"prompts/{prompt_name}"


def test_p24_task_brief_records_contract_only_slice() -> None:
    text = TASK.read_text(encoding="utf-8")

    assert "spec/eval/p24_sp_migration_guide_quality_contract.yaml" in text
    assert "tests/contract/test_p24_sp_migration_guide_contract_prompt_assets.py" in text
    assert "production_ready: false" in text
    assert "MIGRATION_GUIDE.md" in text
    assert "structure/quality reference" in text
    assert "renderer/eval runner 구현" in text
    assert "raw SP definition" in text
    assert "PLF fallback" in text


def test_p24b_fixture_asset_records_fixture_only_boundaries() -> None:
    fixture = _load_yaml(P24_FIXTURE)

    assert fixture["fixture_suite_id"] == "sp_migration_guide_quality_p24_v1"
    assert fixture["contract_ref"] == "p24_sp_migration_guide_quality@0.1.0"
    assert fixture["phase"] == "P24"
    assert fixture["status"] == "authored_p24b"
    assert fixture["production_ready"] is False
    assert fixture["model_profiles"]["fast_test"]["default_model"] == "gpt-5-nano"
    assert fixture["artifact_scope"]["existing_artifact_types"] == [
        "SP_ANALYSIS_DOC",
        "DEPENDENCY_REPORT",
    ]
    assert fixture["artifact_scope"]["new_persisted_artifact_types_allowed"] is False
    assert [scenario["complexity"] for scenario in fixture["scenarios"]] == [
        "simple",
        "medium",
        "complex",
    ]
    for scenario in fixture["scenarios"]:
        assert scenario["db_context"]["target_db"] == "PPM"
        assert scenario["db_context"]["platform_db"] == "PLF"
        assert scenario["db_context"]["plf_fallback"] == "forbidden"


def test_p24_assets_do_not_copy_user_reference_content_or_raw_sql() -> None:
    asset_paths = [
        CONTRACT,
        TASK,
        P24_FIXTURE,
        *(PROMPTS / prompt for prompt in P24_PROMPTS.values()),
    ]
    forbidden_markers = [
        "CREATE OR ALTER PROCEDURE",
        "CREATE PROCEDURE",
        "CREATE PROC",
        "ALTER PROCEDURE",
    ]

    for path in asset_paths:
        text = path.read_text(encoding="utf-8")
        for marker in forbidden_markers:
            assert marker not in text
