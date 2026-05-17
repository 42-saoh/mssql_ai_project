from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "spec" / "eval" / "p38_metadata_design_chat_contract.yaml"
TASK = ROOT / "tasks" / "0038-metadata-design-chat.md"
MANIFEST = ROOT / "ops" / "codex-parallel" / "REQUEST_MANIFEST.yaml"
PROMPT_DIR = ROOT / "ops" / "codex-parallel" / "prompts"


def _yaml(path: Path) -> dict:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_p38_contract_declares_metadata_design_boundaries() -> None:
    contract = _yaml(CONTRACT)

    assert contract["contract_id"] == "p38_metadata_design_chat"
    assert contract["production_ready"] is False
    assert contract["required_paths"] == [
        "/api/v1/metadata/design-runs",
        "/api/v1/metadata/design-runs/{runId}",
        "/api/v1/metadata/design-conversations/{conversationId}",
    ]
    assert contract["storage"]["manual_sql"] == (
        "db/schema/ai_agent_platform_schema_v10_metadata_design_runs.sql"
    )
    assert contract["outputs"]["table_script_field"] == "createTableScriptPreview"
    assert contract["outputs"]["dto_preview_artifact_type"] == "DTO_DRAFT"
    assert contract["outputs"]["not_workflow_artifacts"] is True
    assert {
        "search_columns",
        "search_tables",
        "find_similar_tables",
        "platform_db_standardization_rules_for_ai",
    } <= set(contract["required_evidence"])
    assert "workflowArtifactPersistence" in contract["forbidden"]
    assert "retiredArtifactTypeRevival" in contract["forbidden"]


def test_p38_task_brief_records_scope_and_guardrails() -> None:
    text = TASK.read_text(encoding="utf-8")

    for required in (
        "P38 Metadata Design Chat",
        "POST /api/v1/metadata/design-runs",
        "GET /api/v1/metadata/design-runs/{runId}",
        "GET /api/v1/metadata/design-conversations/{conversationId}",
        "METADATA_DESIGN_RUNS",
        "createTableScriptPreview",
        "DTO_DRAFT",
        "No row data access",
        "No automatic DDL apply",
    ):
        assert required in text


def test_p38_prompt_pack_exists_and_is_sequential() -> None:
    prompts = [
        "38a_metadata_design_contract_assets.md",
        "38b_metadata_design_backend_runs.md",
        "38c_metadata_design_generation_service.md",
        "38d_metadata_design_web_ui.md",
        "38e_metadata_design_eval_docs_readiness.md",
    ]

    for name in prompts:
        text = (PROMPT_DIR / name).read_text(encoding="utf-8")
        assert "## Role" in text
        assert "## Task" in text
        assert "## Constraints" in text
        assert "## Acceptance" in text
        assert "production_ready" in text or name.endswith("_web_ui.md")


def test_p38_manifest_wires_after_p36_and_keeps_order() -> None:
    manifest = _yaml(MANIFEST)

    assert "spec/eval/p38_metadata_design_chat_contract.yaml" in set(manifest["basis"])
    p38_waves = [wave for wave in manifest["waves"] if wave["wave"] == "W16_P38_metadata_design_chat"]
    assert len(p38_waves) == 1
    tracks = p38_waves[0]["tracks"]
    assert [track["id"] for track in tracks] == [
        "P38A",
        "P38B",
        "P38C",
        "P38D",
        "P38E",
    ]
    assert [track.get("depends_on", []) for track in tracks] == [
        ["P36E"],
        ["P38A"],
        ["P38B"],
        ["P38C"],
        ["P38D"],
    ]
    merge_order = manifest["merge_order"]
    p38_order = ["P38A", "P38B", "P38C", "P38D", "P38E"]
    p38_start = merge_order.index("P38A")
    assert merge_order[p38_start : p38_start + len(p38_order)] == p38_order
    assert merge_order.index("P36E") < merge_order.index("P38A")
