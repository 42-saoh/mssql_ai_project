from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "spec" / "eval" / "p42_ai_draft_pack_contract.yaml"
FIXTURE = ROOT / "fixtures" / "eval" / "ai_draft_pack_p42_manage_bond_v1.yaml"
TASK = ROOT / "tasks" / "0042-ai-draft-pack-renewal.md"
MANIFEST = ROOT / "ops" / "codex-parallel" / "REQUEST_MANIFEST.yaml"
PROMPT_DIR = ROOT / "ops" / "codex-parallel" / "prompts"

P42_PROMPTS = {
    "P42A": "42a_ai_draft_pack_contract_assets.md",
    "P42B": "42b_ai_draft_pack_schema_gateway.md",
    "P42C": "42c_ai_code_validator_quality_eval.md",
    "P42D": "42d_workflow_wiring_artifact_storage.md",
    "P42E": "42e_manage_bond_live_probe_replay.md",
    "P42F": "42f_docs_quality_gate.md",
}

REQUIRED_PROMPT_SECTIONS = (
    "## Role",
    "## Task",
    "## Scope",
    "## Constraints",
    "## Acceptance",
)

REQUIRED_DTOS = {
    "ManageBondSearchCriteria",
    "ManageBondSearchRow",
    "ApproveAdvanceBondCommand",
    "ApproveDefectBondCommand",
    "FinanceTransferCommand",
    "CreateBondCommand",
    "CreateRetentionBondBatchItem",
    "UpdateBondCommand",
    "DeleteBondCommand",
    "VendorBondUpdateCommand",
    "OnlineBondUpdateCommand",
}


def _yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_p42_contract_declares_ai_draft_pack_boundaries() -> None:
    contract = _yaml(CONTRACT)

    assert contract["contract_id"] == "p42_ai_draft_pack@0.1.0"
    assert contract["phase"] == "P42"
    assert contract["production_ready"] is False
    assert contract["execution_shape"]["mode"] == "sequential_only"
    assert contract["execution_shape"]["required_order"] == [
        "P42A",
        "P42B",
        "P42C",
        "P42D",
        "P42E",
        "P42F",
    ]
    assert contract["artifact_policy"]["new_public_artifact_type_allowed"] is False
    assert contract["artifact_policy"]["dto_draft_internal_shape"] == (
        "multi_file_rows_required"
    )
    draft_pack = contract["ai_draft_pack_contract"]
    assert draft_pack["schema_ref"] == "AiJavaMyBatisDraftPack.v0.1"
    assert draft_pack["source_policy"] == "sanitized_facts_only"
    assert "files" in draft_pack["required_top_level_fields"]
    assert "content" in draft_pack["required_file_fields"]


def test_p42_contract_records_job_audit_and_failure_policy() -> None:
    contract = _yaml(CONTRACT)

    audit = contract["job_6864d2734e_audit"]
    assert audit["target_ref"] == "PPM.dbo.PCO_GU_ManageBond_PRC"
    assert audit["observed_planner_marker"] == (
        "SP_OPERATION_MODEL_PLANNER_FAILED:ModelGatewayError"
    )
    assert all(
        title.startswith("OperationModelReviewRequired")
        for title in audit["observed_java_mybatis_titles"]
    )

    failure_policy = contract["failure_policy"]
    assert "OperationModelReviewRequired" in failure_policy["blocked_class_names"]
    assert "ManageBondDTO" in failure_policy["blocked_class_names"]
    assert failure_policy["empty_content_is_blocker"] is True
    assert failure_policy["dto_collapse_is_blocker"] is True
    assert failure_policy["fallback_java_skeleton_persistence_allowed_on_failure"] is False


def test_p42_contract_anchors_manage_bond_required_files() -> None:
    contract = _yaml(CONTRACT)
    target = contract["manage_bond_quality_target"]

    assert target["target_ref"] == "PPM.dbo.PCO_GU_ManageBond_PRC"
    assert target["copy_user_reference_content_to_repo"] is False
    assert target["copy_raw_sp_text_to_repo"] is False
    assert set(target["required_dto_files"]) == REQUIRED_DTOS
    assert target["required_single_files"] == {
        "service": "ManageBondService",
        "mapper_interface": "ManageBondMapper",
        "mapper_xml": "ManageBondMapperSQL",
    }
    assert target["required_crud_flags"] == [
        "R",
        "A",
        "C",
        "U",
        "D",
        "VENDOR_U",
        "ONLINE_U",
    ]
    assert all(contract["forbidden_behavior"].values())


def test_p42_fixture_asset_records_sanitized_reference_boundary() -> None:
    fixture = _yaml(FIXTURE)

    assert fixture["fixture_suite_id"] == "ai_draft_pack_p42_manage_bond_v1"
    assert fixture["contract_ref"] == "p42_ai_draft_pack@0.1.0"
    assert fixture["phase"] == "P42A"
    assert fixture["production_ready"] is False
    assert fixture["source_reference"]["target_ref"] == "PPM.dbo.PCO_GU_ManageBond_PRC"
    assert fixture["source_reference"]["copy_reference_content_to_repo"] is False
    assert fixture["source_reference"]["copy_raw_sp_text_to_repo"] is False
    assert fixture["job_audit"]["acceptance_status"] == "rejected_for_p42_target"
    assert fixture["expected_quality_report"]["productionReady"] is False


def test_p42_prompt_pack_exists_and_keeps_sequential_boundaries() -> None:
    for track_id, prompt_name in P42_PROMPTS.items():
        text = (PROMPT_DIR / prompt_name).read_text(encoding="utf-8")
        for section in REQUIRED_PROMPT_SECTIONS:
            assert section in text
        assert track_id in text
        assert "production_ready: false" in text
        assert "REVIEW_REQUIRED" in text
        assert "row data" in text
        assert "procedure execution" in text
        assert "DTO_DRAFT" in text or track_id in {"P42B", "P42C", "P42F"}


def test_p42_task_and_manifest_wire_sequential_tracks() -> None:
    task = TASK.read_text(encoding="utf-8")
    manifest = _yaml(MANIFEST)

    assert "Task 0042: AI Draft Pack Renewal" in task
    assert "PCO_GU_ManageBond_PRC" in task
    assert "AiJavaMyBatisDraftPack.v0.1" in task
    assert "tests/eval/test_p42_manage_bond_ai_draft_quality.py" in task

    assert "spec/eval/p42_ai_draft_pack_contract.yaml" in manifest["basis"]
    assert "fixtures/eval/ai_draft_pack_p42_manage_bond_v1.yaml" in manifest["basis"]
    tracks = {
        track["id"]: track
        for wave in manifest["waves"]
        for track in wave["tracks"]
        if track["id"].startswith("P42")
    }
    assert list(tracks) == ["P42A", "P42B", "P42C", "P42D", "P42E", "P42F"]
    assert [item for item in manifest["merge_order"] if item.startswith("P42")] == [
        "P42A",
        "P42B",
        "P42C",
        "P42D",
        "P42E",
        "P42F",
    ]
    assert tracks["P42A"]["depends_on"] == ["P41F"]
    assert tracks["P42B"]["depends_on"] == ["P42A"]
    assert tracks["P42F"]["depends_on"] == ["P42E"]
    for track_id, prompt_name in P42_PROMPTS.items():
        assert tracks[track_id]["prompt"] == f"prompts/{prompt_name}"


def test_p42_assets_do_not_copy_raw_stored_procedure_text() -> None:
    asset_paths = [
        CONTRACT,
        FIXTURE,
        TASK,
        *(PROMPT_DIR / prompt for prompt in P42_PROMPTS.values()),
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
