from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "spec" / "eval" / "p43_framework_adoption_contract.yaml"
FIXTURE = ROOT / "fixtures" / "eval" / "framework_adoption_p43_manage_bond_v1.yaml"
TASK = ROOT / "tasks" / "0043-framework-adoption-readiness.md"
MANIFEST = ROOT / "ops" / "codex-parallel" / "REQUEST_MANIFEST.yaml"
PROMPT_DIR = ROOT / "ops" / "codex-parallel" / "prompts"

P43_PROMPTS = {
    "P43A": "43a_framework_adoption_contract_assets.md",
    "P43B": "43b_framework_adapter_contract.md",
    "P43C": "43c_ai_draft_pack_framework_spike.md",
    "P43D": "43d_tool_trace_policy_gate.md",
    "P43E": "43e_manage_bond_framework_replay_gate.md",
    "P43F": "43f_docs_decision_gate.md",
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


def test_p43_contract_declares_adapter_first_readiness_scope() -> None:
    contract = _yaml(CONTRACT)

    assert contract["contract_id"] == "p43_framework_adoption@0.1.0"
    assert contract["phase"] == "P43"
    assert contract["production_ready"] is False
    assert contract["scope"]["mode"] == "sequential_only"
    assert contract["scope"]["required_order"] == [
        "P43A",
        "P43B",
        "P43C",
        "P43D",
        "P43E",
        "P43F",
    ]
    assert contract["scope"]["implementation_posture"] == "adapter_first_evaluation"
    assert contract["scope"]["dependency_installation_allowed_in_p43a"] is False
    assert contract["scope"]["production_runtime_switch_allowed_in_p43a"] is False


def test_p43_contract_records_candidates_and_policy_boundaries() -> None:
    contract = _yaml(CONTRACT)
    candidates = contract["candidate_frameworks"]

    assert set(candidates) == {
        "baseline_internal_responses_gateway",
        "openai_agents_sdk",
        "langgraph",
    }
    assert candidates["baseline_internal_responses_gateway"]["current_stack"] is True
    assert "raw prompts" in " ".join(
        candidates["openai_agents_sdk"]["adoption_risks"]
    )
    assert "workflow" in candidates["langgraph"]["adoption_risks"][0]

    forbidden = contract["forbidden_behavior"]
    assert all(forbidden.values())
    assert "P43_FRAMEWORK_OVERFITS_MANAGE_BOND" in contract["blockers"]


def test_p43_contract_defines_framework_adapter_contract() -> None:
    adapter = _yaml(CONTRACT)["framework_adapter_contract"]

    assert adapter["name"] == "AiGenerationFrameworkAdapter.v0.1"
    assert adapter["required_methods"] == [
        "plan_file_inventory",
        "draft_file_content",
        "repair_draft_pack",
        "summarize_trace",
    ]
    assert "deterministic_inventory_contract" in adapter["required_inputs"]
    assert "sanitized_trace_hashes" in adapter["required_outputs"]
    assert "raw_prompt" in adapter["forbidden_outputs"]
    assert "raw_provider_response" in adapter["forbidden_outputs"]


def test_p43_fixture_keeps_manage_bond_as_benchmark_only() -> None:
    fixture = _yaml(FIXTURE)

    assert fixture["fixture_suite_id"] == "framework_adoption_p43_manage_bond_v1"
    assert fixture["contract_ref"] == "p43_framework_adoption@0.1.0"
    assert fixture["production_ready"] is False
    assert fixture["source_reference"]["target_ref"] == "PPM.dbo.PCO_GU_ManageBond_PRC"
    assert fixture["source_reference"]["role"] == "complex_sp_benchmark_only"
    assert fixture["source_reference"]["copy_reference_content_to_repo"] is False
    assert fixture["source_reference"]["copy_raw_sp_text_to_repo"] is False
    assert fixture["expected_general_contract"]["reject_two_dto_collapse_for_complex_sp"] is True
    assert fixture["expected_general_contract"]["reject_raw_trace_or_prompt_storage"] is True


def test_p43_prompt_pack_exists_and_preserves_policy() -> None:
    for track_id, prompt_name in P43_PROMPTS.items():
        text = (PROMPT_DIR / prompt_name).read_text(encoding="utf-8")
        for section in REQUIRED_PROMPT_SECTIONS:
            assert section in text
        assert track_id in text
        assert "production_ready: false" in text
        assert "row data" in text
        assert "procedure execution" in text
        assert "REVIEW_REQUIRED" in text or track_id in {"P43A", "P43B"}


def test_p43_task_and_manifest_wire_sequential_tracks() -> None:
    task = TASK.read_text(encoding="utf-8")
    manifest = _yaml(MANIFEST)

    assert "Task 0043: Framework Adoption Readiness" in task
    assert "adapter" in task
    assert "PCO_GU_ManageBond_PRC" in task
    assert "OpenAI Agents SDK" in task
    assert "LangGraph" in task

    assert "spec/eval/p43_framework_adoption_contract.yaml" in manifest["basis"]
    assert "fixtures/eval/framework_adoption_p43_manage_bond_v1.yaml" in manifest["basis"]

    tracks = {
        track["id"]: track
        for wave in manifest["waves"]
        for track in wave["tracks"]
        if track["id"].startswith("P43")
    }
    assert list(tracks) == ["P43A", "P43B", "P43C", "P43D", "P43E", "P43F"]
    assert [item for item in manifest["merge_order"] if item.startswith("P43")] == [
        "P43A",
        "P43B",
        "P43C",
        "P43D",
        "P43E",
        "P43F",
    ]
    assert tracks["P43A"]["depends_on"] == ["P42F"]
    assert tracks["P43B"]["depends_on"] == ["P43A"]
    assert tracks["P43F"]["depends_on"] == ["P43E"]
    for track_id, prompt_name in P43_PROMPTS.items():
        assert tracks[track_id]["prompt"] == f"prompts/{prompt_name}"


def test_p43_assets_do_not_copy_raw_stored_procedure_or_prompt_text() -> None:
    asset_paths = [
        CONTRACT,
        FIXTURE,
        TASK,
        *(PROMPT_DIR / prompt for prompt in P43_PROMPTS.values()),
    ]
    forbidden_markers = [
        "CREATE OR ALTER PROCEDURE",
        "CREATE PROCEDURE",
        "CREATE PROC",
        "ALTER PROCEDURE",
        "BEGIN TRANSACTION raw",
        "provider_response_raw",
        "raw_provider_payload",
    ]

    for path in asset_paths:
        text = path.read_text(encoding="utf-8")
        for marker in forbidden_markers:
            assert marker not in text
