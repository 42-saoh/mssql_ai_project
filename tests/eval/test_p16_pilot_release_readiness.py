from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
EVAL_DIR = ROOT / "fixtures" / "eval"
P16_FIXTURE = EVAL_DIR / "pilot_release_readiness_p16_v1.yaml"
PILOT_MANIFEST = ROOT / "fixtures" / "pilot" / "ppm_object_selection_v1" / "selected_objects.yaml"
P16_REPORT = ROOT / "docs" / "pilot-release-readiness.md"
P16_HANDOFF = ROOT / "ops" / "codex-parallel" / "P16_PILOT_RELEASE_HANDOFF.md"


def test_p16_fixture_matches_live_manifest_and_conditional_go_decision() -> None:
    fixture = _yaml(P16_FIXTURE)
    manifest = _yaml(PILOT_MANIFEST)

    assert fixture["version"] == "pilot_release_readiness_p16_v1"
    assert fixture["source_manifest"] == str(
        Path("fixtures") / "pilot" / "ppm_object_selection_v1" / "selected_objects.yaml"
    )
    assert fixture["current_manifest"]["selection_mode"] == manifest["selection_mode"]
    assert fixture["current_manifest"]["source_db"] == "PPM"
    assert fixture["current_manifest"]["platform_db_context"] == "PLF"
    assert fixture["profile_policy"]["analysis_db_profile_id"] == "ppm"
    assert fixture["profile_policy"]["plf_fallback_allowed"] is False

    assert fixture["release_recommendation"]["live_pilot_release"]["decision"] == (
        "CONDITIONAL_GO"
    )
    assert (
        fixture["release_recommendation"]["fixture_first_demo_handoff"]["decision"]
        == "GO_WITH_LIMITATIONS"
    )
    assert "DEPENDENCY_METADATA_INCOMPLETE" not in _blocker_codes(fixture)
    assert "DEPENDENCY_METADATA_INCOMPLETE" not in {
        blocker["code"] for blocker in manifest["active_blockers"]
    }
    assert "DRAFT_QUALITY_EVIDENCE_MISSING" not in _blocker_codes(fixture)


def test_p16_representative_objects_are_manifest_backed_when_live() -> None:
    fixture = _yaml(P16_FIXTURE)
    manifest = _yaml(PILOT_MANIFEST)
    representative = fixture["representative_objects"]

    assert (
        fixture["mode_policy"]["live_metadata"]["can_reference_selected_object_identities"]
        is True
    )
    assert (
        fixture["mode_policy"]["template_only"]["can_reference_selected_object_identities"]
        is False
    )
    assert (
        fixture["mode_policy"]["template_only"]["object_identity_rule"]
        == "do_not_invent_object_names"
    )

    if manifest["selection_mode"] == "live_metadata":
        manifest_proc_names = {item["name"] for item in manifest["stored_procedures"]}
        manifest_table_names = {item["name"] for item in manifest["tables"]}
        manifest_view_names = {item["name"] for item in manifest["views"]}
        manifest_function_names = {item["name"] for item in manifest["functions"]}

        assert {item["name"] for item in representative["stored_procedures"]} <= manifest_proc_names
        assert {item["name"] for item in representative["tables"]} <= manifest_table_names
        assert {item["name"] for item in representative["views"]} <= manifest_view_names
        assert {item["name"] for item in representative["functions"]} <= manifest_function_names
        assert {item["complexity"] for item in representative["stored_procedures"]} == {
            "simple",
            "medium",
            "complex",
        }

    for procedure in representative["stored_procedures"]:
        assert procedure["dependency_status"] in {
            "CONFIRMED",
            "COMPLEX_SENTINEL_RESIDUAL_REVIEW_ALLOWED",
        }
        assert procedure["review_required"] is False
    for table in representative["tables"]:
        assert table["linkage_status"] == "not_confirmed_as_selected_procedure_dependency"


def test_p16_quality_release_checklist_and_forbidden_boundaries() -> None:
    fixture = _yaml(P16_FIXTURE)

    checklist = {item["id"]: item for item in fixture["release_checklist"]}
    assert {
        "ppm_manifest_mode",
        "ppm_access_and_read_only_metadata",
        "dependency_evidence",
        "validation_result",
        "draft_quality_evidence",
        "audit_trace",
        "policy_forbidden_actions",
        "docs_status_taxonomy",
    } <= set(checklist)
    assert checklist["dependency_evidence"]["status"] == "PASS"
    assert checklist["validation_result"]["status"] == "PASS"
    assert checklist["draft_quality_evidence"]["status"] == "PASS"
    assert checklist["audit_trace"]["status"] == "PASS"
    assert checklist["hard_live_verification"]["status"] == "PASS"
    assert checklist["policy_forbidden_actions"]["status"] == "PASS"

    quality = fixture["quality_report"]
    assert quality["evidence_coverage"]["selected_object_identity_coverage"] == 1.0
    assert quality["evidence_coverage"]["confirmed_procedure_dependency_suite_coverage"] > 0.5
    assert quality["validation"]["passed_validation_for_live_release"] is True
    assert quality["validation"]["live_release_validation_status"] == "PASSED"
    assert quality["draft_quality_audit"]["draft_quality_status"] == "EVIDENCE_BOUND"
    assert quality["draft_quality_audit"]["audit_status"] == "BOUND"
    assert (
        quality["draft_quality_audit"]["publish_status"]
        == "no_publish_export_draft_only_conditional_go"
    )
    assert fixture["p17d_hard_live_verification"]["status"] == "PASSED"
    assert all(
        item["status"] == "PASSED"
        for item in fixture["p17d_hard_live_verification"]["commands"]
    )

    assert {
        "row_data",
        "procedure_execution",
        "sql_definition_text",
        "auto_ddl_or_dml",
        "plf_fallback_for_ppm",
        "publish_or_export_path",
    } <= set(fixture["forbidden_evidence"])
    assert fixture["profile_policy"]["row_data_allowed"] is False
    assert fixture["profile_policy"]["procedure_execution_allowed"] is False
    assert fixture["profile_policy"]["ddl_dml_allowed"] is False


def test_p16_docs_align_with_conditional_go_and_do_not_overclaim() -> None:
    fixture = _yaml(P16_FIXTURE)
    report = P16_REPORT.read_text(encoding="utf-8")
    handoff = P16_HANDOFF.read_text(encoding="utf-8")
    combined = f"{report}\n{handoff}"

    assert "Live pilot release: CONDITIONAL_GO" in report
    assert "Fixture-first/demo handoff: GO WITH LIMITATIONS" in report
    assert "DEPENDENCY_METADATA_INCOMPLETE" in combined
    assert "scoped live pilot candidate" in combined
    assert "No surface is production-ready" in report
    assert fixture["handoff_package"]["primary_report"] in combined
    assert fixture["handoff_package"]["eval_fixture"] in combined
    assert "draft-only" in combined
    assert "no PLF fallback" in combined or "PLF fallback" in combined

    forbidden_fragments = (
        "PFL",
        "SELECT * FROM PPM",
        "COUNT(*)",
        "sample_rows",
        "row_sample",
        "automatic DDL execution is supported",
        "production-ready: true",
        "unconditional GO",
    )
    for fragment in forbidden_fragments:
        assert fragment not in combined


def _yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _blocker_codes(payload: dict[str, Any]) -> set[str]:
    return {str(blocker["code"]) for blocker in payload["active_blockers"]}
