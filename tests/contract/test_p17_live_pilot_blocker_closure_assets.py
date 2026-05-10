from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml


ROOT = Path(__file__).resolve().parents[2]
PROMPTS = ROOT / "ops" / "codex-parallel" / "prompts"
MANIFEST = ROOT / "ops" / "codex-parallel" / "REQUEST_MANIFEST.yaml"
P17_FIXTURE = ROOT / "fixtures" / "eval" / "live_pilot_blocker_closure_p17_v1.yaml"
P17_PLAN = ROOT / "docs" / "live-pilot-blocker-closure-plan.md"
P16_FIXTURE = ROOT / "fixtures" / "eval" / "pilot_release_readiness_p16_v1.yaml"
PILOT_MANIFEST = ROOT / "fixtures" / "pilot" / "ppm_object_selection_v1" / "selected_objects.yaml"

P17_PROMPTS = {
    "P17A": "17a_dependency_metadata_evidence_closure.md",
    "P17B": "17b_live_artifact_validation_closure.md",
    "P17C": "17c_manual_approval_audit_binding.md",
    "P17D": "17d_pilot_release_go_decision.md",
}

REQUIRED_SECTIONS = (
    "## 목표",
    "## 읽어야 할 기준 파일",
    "## 허용 수정 경로",
    "## 금지 경로",
    "## 구현 범위",
    "## 검증 명령",
    "## Blocker 보고 기준",
)


def test_p17_prompts_exist_and_preserve_release_safety_contract() -> None:
    for track_id, filename in P17_PROMPTS.items():
        text = (PROMPTS / filename).read_text(encoding="utf-8")
        assert text.startswith(f"# {track_id}"), filename
        for section in REQUIRED_SECTIONS:
            assert section in text, f"{filename} missing {section}"
        assert "PPM" in text
        assert "PLF" in text
        assert "PFL" not in text
        assert "row data" in text
        assert "procedure execution" in text
        assert "coordinator" in text
        assert "blocker" in text.lower()


def test_p17_manifest_declares_ordered_blocker_closure_wave() -> None:
    manifest = _yaml(MANIFEST)
    tracks = _tracks(manifest)

    for track_id, filename in P17_PROMPTS.items():
        assert track_id in tracks
        assert tracks[track_id]["prompt"] == f"prompts/{filename}"
        assert tracks[track_id]["worktree"].startswith("../wt/p17")
        assert tracks[track_id]["target_paths"]
        assert tracks[track_id]["verify"]

    assert tracks["P17A"]["depends_on"] == ["P16"]
    assert tracks["P17B"]["depends_on"] == ["P17A"]
    assert tracks["P17C"]["depends_on"] == ["P17B"]
    assert tracks["P17D"]["depends_on"] == ["P17C"]

    order = manifest["merge_order"]
    assert order.index("P16") < order.index("P17A") < order.index("P17B") < order.index("P17C") < order.index("P17D")

    assert "fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml" in tracks["P17A"]["target_paths"]
    for track_id in ("P17B", "P17C", "P17D"):
        assert "fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml" in tracks[track_id].get(
            "readonly_paths", []
        )


def test_p17_fixture_records_conditional_go_after_all_release_evidence_is_bound() -> None:
    fixture = _yaml(P17_FIXTURE)
    p16 = _yaml(P16_FIXTURE)
    pilot = _yaml(PILOT_MANIFEST)

    assert fixture["version"] == "live_pilot_blocker_closure_p17_v1"
    assert fixture["source_p16_fixture"] == "fixtures/eval/pilot_release_readiness_p16_v1.yaml"
    assert fixture["source_pilot_manifest"] == "fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml"
    assert fixture["current_state"]["live_pilot_release_decision"] == p16["release_recommendation"]["live_pilot_release"]["decision"]
    assert fixture["current_state"]["live_pilot_release_decision"] == "CONDITIONAL_GO"
    assert fixture["current_state"]["source_db"] == "PPM"
    assert fixture["current_state"]["platform_db_context"] == "PLF"
    assert pilot["selection_mode"] == fixture["current_state"]["selection_mode_required"]

    blockers = set(fixture["current_state"]["active_blockers_to_close"])
    assert "MANUAL_APPROVAL_EVIDENCE_MISSING" not in blockers
    assert "DEPENDENCY_METADATA_INCOMPLETE" not in blockers
    assert "MANUAL_APPROVAL_EVIDENCE_MISSING" in set(
        fixture["current_state"].get("blockers_closed", [])
    )
    assert "DEPENDENCY_METADATA_INCOMPLETE" in set(
        fixture["current_state"].get("blockers_closed", [])
    )
    assert fixture["current_state"]["p17c_manual_approval_status"] == "HUMAN_APPROVED"
    assert fixture["current_state"]["p17c_blocker_closed"] is True
    assert fixture["current_state"]["p17d_release_decision_pending"] is False
    assert fixture["current_state"]["p17d_release_decision_completed"] is True
    assert fixture["current_state"]["p17d_final_decision"] == "CONDITIONAL_GO"

    assert fixture["policy_boundaries"]["metadata_only"] is True
    assert fixture["policy_boundaries"]["row_data_allowed"] is False
    assert fixture["policy_boundaries"]["procedure_execution_allowed"] is False
    assert fixture["policy_boundaries"]["raw_definition_text_allowed_in_evidence"] is False
    assert fixture["policy_boundaries"]["plf_fallback_allowed"] is False

    assert fixture["final_decision_policy"]["current_decision"] == "CONDITIONAL_GO"
    assert fixture["final_decision_policy"]["conditional_go_scope"] == (
        "scoped_live_pilot_candidate_only"
    )
    assert set(fixture["final_decision_policy"]["allowed_decisions"]) == {"NO_GO", "CONDITIONAL_GO"}
    assert "no_publish_or_export" in fixture["final_decision_policy"]["conditional_go_boundaries"]
    assert fixture["p17d_hard_live_verification"]["status"] == "PASSED"
    assert "production-ready: true" in fixture["final_decision_policy"]["overclaim_forbidden"]


def test_p17_closure_sequence_has_dependency_validation_approval_and_hard_live_gates() -> None:
    fixture = _yaml(P17_FIXTURE)
    sequence = fixture["closure_sequence"]

    assert sequence["P17A"]["primary_blocker"] == "DEPENDENCY_METADATA_INCOMPLETE"
    assert "metadata-only evidence refs" in sequence["P17A"]["objective"]
    assert sequence["P17B"]["primary_gap"] == "live_release_validation_missing"
    assert "validationStatus is PASSED" in sequence["P17B"]["exit_criteria"]
    assert sequence["P17C"]["primary_blocker"] == "MANUAL_APPROVAL_EVIDENCE_MISSING"
    assert "not synthesized" in sequence["P17C"]["exit_criteria"]
    assert sequence["P17D"]["primary_decision"] == "live_pilot_release_go_no_go"

    hard_live_commands = fixture["conditional_go_requires"]["hard_live_gate"]["commands"]
    assert any("P15_HARD_LIVE_GATE=1" in command for command in hard_live_commands)
    assert any("MSSQL_ENABLE_LIVE_METADATA=1" in command for command in hard_live_commands)

    forbidden = set(fixture["forbidden_evidence"])
    assert {
        "row_data",
        "sample_rows",
        "procedure_execution",
        "sql_definition_text",
        "committed_secret",
        "auto_ddl_or_dml",
        "plf_fallback_for_ppm",
        "unapproved_publish_or_export",
    } <= forbidden


def test_p17_docs_explain_what_to_do_without_claiming_go() -> None:
    text = P17_PLAN.read_text(encoding="utf-8")
    runbook = (ROOT / "ops" / "codex-parallel" / "PARALLEL_RUNBOOK.md").read_text(
        encoding="utf-8"
    )
    readme = (ROOT / "ops" / "codex-parallel" / "README.md").read_text(encoding="utf-8")
    plan = (ROOT / "ops" / "codex-parallel" / "PARALLEL_REQUEST_PLAN.md").read_text(
        encoding="utf-8"
    )
    combined = "\n".join([text, runbook, readme, plan])

    assert "P17 Live Pilot Blocker Closure" in text
    assert "Current live pilot decision is `CONDITIONAL_GO`" in text
    assert "P17A -> P17B -> P17C -> P17D" in runbook
    assert "CONDITIONAL_GO" in combined
    assert "DEPENDENCY_METADATA_INCOMPLETE" in combined
    assert "MANUAL_APPROVAL_EVIDENCE_MISSING" in combined
    assert "approvalDecision: APPROVE" in text
    assert "not a production-ready platform claim" in text
    assert "draft-only" in text
    assert "PLF로 대체하지" in combined or "PLF로 대체" in combined
    assert "PFL" not in combined

    forbidden_fragments = (
        "SELECT * FROM PPM",
        "COUNT(*)",
        "sample_rows:",
        "row_sample",
        "automatic DDL execution is supported",
        "production-ready: true",
        "unconditional GO",
    )
    for fragment in forbidden_fragments:
        assert fragment not in combined


def _yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _tracks(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    tracks: dict[str, dict[str, Any]] = {}
    for wave in manifest["waves"]:
        for track in wave["tracks"]:
            tracks[track["id"]] = track
    return tracks
