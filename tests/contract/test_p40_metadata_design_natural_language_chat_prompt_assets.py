from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "spec" / "eval" / "p40_metadata_design_natural_language_chat_contract.yaml"
TASK = ROOT / "tasks" / "0040-metadata-design-natural-language-chat.md"
MANIFEST = ROOT / "ops" / "codex-parallel" / "REQUEST_MANIFEST.yaml"
PROMPT_DIR = ROOT / "ops" / "codex-parallel" / "prompts"


def _yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_p40_contract_declares_natural_language_chat_boundaries() -> None:
    contract = _yaml(CONTRACT)

    assert contract["contract_id"] == "p40_metadata_design_natural_language_chat"
    assert contract["production_ready"] is False
    assert contract["storage"]["no_new_ddl"] is True
    assert contract["storage"]["reuse_manual_sql"].endswith(
        "ai_agent_platform_schema_v10_metadata_design_runs.sql"
    )
    assert contract["input_contract"]["conversation_modes"] == [
        "NEW_DESIGN",
        "REFINE_CURRENT",
    ]
    assert contract["input_contract"]["fields_api_compat_only"] is True
    assert contract["input_contract"]["web_field_rows_removed"] is True
    assert {
        "interpretedIntent",
        "appliedChanges",
        "tableProposal",
        "dtoDraft",
    } <= set(contract["result_contract"]["required_fields"])
    assert contract["result_contract"]["table_script_field"] == "createTableScriptPreview"
    assert contract["result_contract"]["dto_preview_artifact_type"] == "DTO_DRAFT"
    assert {
        "search_columns",
        "search_tables",
        "find_similar_tables",
        "get_table_schema",
        "platform_db_standardization_rules_for_ai",
    } <= set(contract["required_evidence"])
    assert "automaticDdlApply" in contract["forbidden"]
    assert "DDL_DRAFT" in contract["forbidden"]


def test_p40_task_brief_records_scope_and_guardrails() -> None:
    text = TASK.read_text(encoding="utf-8")

    for required in (
        "P40 Metadata Design Natural-Language Chat",
        "conversationMode",
        "interpretedIntent",
        "appliedChanges",
        "REFINE_CURRENT",
        "No row data access",
        "No automatic DDL apply",
        "production_ready",
    ):
        assert required in text


def test_p40_prompt_pack_exists_and_is_sequential() -> None:
    prompts = [
        "40a_metadata_design_nl_contract_assets.md",
        "40b_metadata_design_backend_intent_refine.md",
        "40c_metadata_design_eval_generation.md",
        "40d_metadata_design_web_chat_ui.md",
        "40e_metadata_design_docs_readiness.md",
    ]

    for name in prompts:
        text = (PROMPT_DIR / name).read_text(encoding="utf-8")
        assert "## Role" in text
        assert "## Task" in text
        assert "## Constraints" in text
        assert "## Acceptance" in text


def test_p40_manifest_wires_after_p38_and_keeps_order() -> None:
    manifest = _yaml(MANIFEST)

    assert "spec/eval/p40_metadata_design_natural_language_chat_contract.yaml" in set(
        manifest["basis"]
    )
    p40_waves = [
        wave
        for wave in manifest["waves"]
        if wave["wave"] == "W17_P40_metadata_design_natural_language_chat"
    ]
    assert len(p40_waves) == 1
    tracks = p40_waves[0]["tracks"]
    assert [track["id"] for track in tracks] == [
        "P40A",
        "P40B",
        "P40C",
        "P40D",
        "P40E",
    ]
    assert [track.get("depends_on", []) for track in tracks] == [
        ["P38E"],
        ["P40A"],
        ["P40B"],
        ["P40C"],
        ["P40D"],
    ]
    merge_order = manifest["merge_order"]
    p40_order = ["P40A", "P40B", "P40C", "P40D", "P40E"]
    p40_start = merge_order.index("P40A")
    assert merge_order[p40_start : p40_start + len(p40_order)] == p40_order
    assert merge_order.index("P38E") < merge_order.index("P40A")
