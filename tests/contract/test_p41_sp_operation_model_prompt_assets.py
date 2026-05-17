from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "spec" / "eval" / "p41_sp_operation_model_contract.yaml"
FIXTURE = ROOT / "fixtures" / "eval" / "sp_operation_model_p41_manage_bond_v1.yaml"
TASK = ROOT / "tasks" / "0041-sp-operation-model-renewal.md"
MANIFEST = ROOT / "ops" / "codex-parallel" / "REQUEST_MANIFEST.yaml"
PROMPT_DIR = ROOT / "ops" / "codex-parallel" / "prompts"

P41_PROMPTS = {
    "P41A": "41a_sp_operation_model_contract_assets.md",
    "P41B": "41b_sp_operation_schema_prompt.md",
    "P41C": "41c_statement_evidence_extractor.md",
    "P41D": "41d_structured_semantic_planner.md",
    "P41E": "41e_multi_dto_java_mybatis_generator.md",
    "P41F": "41f_docs_quality_gate.md",
}

REQUIRED_PROMPT_SECTIONS = (
    "## Role",
    "## Task",
    "## Scope",
    "## Constraints",
    "## Acceptance",
)


def _yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_p41_contract_declares_operation_model_and_multi_dto_boundaries() -> None:
    contract = _yaml(CONTRACT)

    assert contract["contract_id"] == "p41_sp_operation_model@0.1.0"
    assert contract["phase"] == "P41"
    assert contract["production_ready"] is False
    assert contract["execution_shape"]["mode"] == "sequential_only"
    assert contract["execution_shape"]["required_order"] == [
        "P41A",
        "P41B",
        "P41C",
        "P41D",
        "P41E",
        "P41F",
    ]
    assert contract["artifact_policy"]["new_public_artifact_type_allowed"] is False
    assert contract["artifact_policy"]["dto_draft_internal_shape"] == (
        "multi_file_bundle_allowed"
    )
    assert contract["operation_model_contract"]["schema_ref"] == "SpOperationModel.v0.1"
    assert contract["generator_gap_expectation"]["current_behavior"] == "single_dto_file"
    assert contract["generator_gap_expectation"]["required_next_slice"] == "P41B"


def test_p41_contract_anchors_manage_bond_fixture_requirements() -> None:
    contract = _yaml(CONTRACT)
    reference = contract["p41a_reference_fixture"]

    assert reference["fixture"] == "fixtures/eval/sp_operation_model_p41_manage_bond_v1.yaml"
    assert reference["target_ref"] == "PPM.dbo.PCO_GU_ManageBond_PRC"
    assert reference["copy_user_reference_content_to_repo"] is False
    assert reference["copy_raw_sp_text_to_repo"] is False
    assert reference["required_crud_flags"] == [
        "R",
        "A",
        "C",
        "U",
        "D",
        "VENDOR_U",
        "ONLINE_U",
    ]
    assert reference["minimum_dto_blueprints"] >= 9
    assert "ManageBondSearchCriteria" in reference["must_include_dto_blueprints"]
    assert "OnlineBondUpdateCommand" in reference["must_include_dto_blueprints"]
    assert all(contract["forbidden_behavior"].values())


def test_p41_fixture_asset_records_sanitized_reference_boundary() -> None:
    fixture = _yaml(FIXTURE)

    assert fixture["fixture_suite_id"] == "sp_operation_model_p41_manage_bond_v1"
    assert fixture["contract_ref"] == "p41_sp_operation_model@0.1.0"
    assert fixture["phase"] == "P41A"
    assert fixture["production_ready"] is False
    assert fixture["source_reference"]["target_ref"] == "PPM.dbo.PCO_GU_ManageBond_PRC"
    assert fixture["source_reference"]["copy_reference_content_to_repo"] is False
    assert fixture["source_reference"]["copy_raw_sp_text_to_repo"] is False
    assert fixture["expected_quality_report"]["productionReady"] is False
    assert fixture["expected_quality_report"]["scores"]["currentGeneratorGapVisible"] is True


def test_p41_prompt_pack_exists_and_keeps_sequential_boundaries() -> None:
    for track_id, prompt_name in P41_PROMPTS.items():
        text = (PROMPT_DIR / prompt_name).read_text(encoding="utf-8")
        for section in REQUIRED_PROMPT_SECTIONS:
            assert section in text
        assert track_id in text
        assert "production_ready: false" in text
        assert "REVIEW_REQUIRED" in text
        assert "row data" in text
        assert "procedure execution" in text
        assert "DTO_DRAFT" in text or track_id in {"P41C", "P41D", "P41F"}


def test_p41_task_and_manifest_wire_sequential_tracks() -> None:
    task = TASK.read_text(encoding="utf-8")
    manifest = _yaml(MANIFEST)

    assert "Task 0041: SP Operation Model Renewal" in task
    assert "PCO_GU_ManageBond_PRC" in task
    assert "SpOperationModel.v0.1" in task
    assert "tests/eval/test_p41_sp_operation_model.py" in task

    assert "spec/eval/p41_sp_operation_model_contract.yaml" in manifest["basis"]
    assert "fixtures/eval/sp_operation_model_p41_manage_bond_v1.yaml" in manifest["basis"]
    tracks = {
        track["id"]: track
        for wave in manifest["waves"]
        for track in wave["tracks"]
        if track["id"].startswith("P41")
    }
    assert list(tracks) == ["P41A", "P41B", "P41C", "P41D", "P41E", "P41F"]
    assert [item for item in manifest["merge_order"] if item.startswith("P41")] == [
        "P41A",
        "P41B",
        "P41C",
        "P41D",
        "P41E",
        "P41F",
    ]
    assert tracks["P41A"]["depends_on"] == ["P40E"]
    assert tracks["P41B"]["depends_on"] == ["P41A"]
    assert tracks["P41F"]["depends_on"] == ["P41E"]
    for track_id, prompt_name in P41_PROMPTS.items():
        assert tracks[track_id]["prompt"] == f"prompts/{prompt_name}"


def test_p41_assets_do_not_copy_raw_stored_procedure_text() -> None:
    asset_paths = [
        CONTRACT,
        FIXTURE,
        TASK,
        *(PROMPT_DIR / prompt for prompt in P41_PROMPTS.values()),
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
