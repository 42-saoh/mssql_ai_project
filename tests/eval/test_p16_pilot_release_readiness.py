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


def test_p16_fixture_matches_live_manifest_and_no_go_decision() -> None:
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

    assert fixture["release_recommendation"]["live_pilot_release"]["decision"] == "NO_GO"
    assert (
        fixture["release_recommendation"]["fixture_first_demo_handoff"]["decision"]
        == "GO_WITH_LIMITATIONS"
    )
    assert "DEPENDENCY_METADATA_INCOMPLETE" in _blocker_codes(fixture)
    assert "DEPENDENCY_METADATA_INCOMPLETE" in {
        blocker["code"] for blocker in manifest["active_blockers"]
    }
    assert "MANUAL_APPROVAL_EVIDENCE_MISSING" in _blocker_codes(fixture)


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
        assert procedure["dependency_status"] == "REVIEW_REQUIRED"
        assert procedure["review_required"] is True
        assert "table_dependency_links_incomplete" in procedure["caveats"]
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
        "manual_approval",
        "audit_trace",
        "policy_forbidden_actions",
        "docs_status_taxonomy",
    } <= set(checklist)
    assert checklist["dependency_evidence"]["status"] == "BLOCKER"
    assert checklist["manual_approval"]["status"] == "BLOCKER"
    assert checklist["policy_forbidden_actions"]["status"] == "PASS"

    quality = fixture["quality_report"]
    assert quality["evidence_coverage"]["selected_object_identity_coverage"] == 1.0
    assert quality["evidence_coverage"]["confirmed_procedure_to_table_dependency_coverage"] == 0.0
    assert quality["validation"]["passed_validation_for_live_release"] is False
    assert quality["approval_audit"]["manual_approval_status"] == "MISSING_FOR_LIVE_RELEASE"
    assert (
        quality["approval_audit"]["publish_status"]
        == "no_publish_endpoint_or_approved_live_release"
    )

    assert {
        "row_data",
        "procedure_execution",
        "sql_definition_text",
        "auto_ddl_or_dml",
        "plf_fallback_for_ppm",
        "unapproved_publish_or_export",
    } <= set(fixture["forbidden_evidence"])
    assert fixture["profile_policy"]["row_data_allowed"] is False
    assert fixture["profile_policy"]["procedure_execution_allowed"] is False
    assert fixture["profile_policy"]["ddl_dml_allowed"] is False


def test_p16_docs_align_with_no_go_and_do_not_overclaim() -> None:
    fixture = _yaml(P16_FIXTURE)
    report = P16_REPORT.read_text(encoding="utf-8")
    handoff = P16_HANDOFF.read_text(encoding="utf-8")
    combined = f"{report}\n{handoff}"

    assert "Live pilot release: NO-GO" in report
    assert "Fixture-first/demo handoff: GO WITH LIMITATIONS" in report
    assert "DEPENDENCY_METADATA_INCOMPLETE" in combined
    assert "MANUAL_APPROVAL_EVIDENCE_MISSING" in combined
    assert "No surface is production-ready" in report
    assert fixture["handoff_package"]["primary_report"] in combined
    assert fixture["handoff_package"]["eval_fixture"] in combined

    forbidden_fragments = (
        "PFL",
        "SELECT * FROM PPM",
        "COUNT(*)",
        "sample_rows",
        "row_sample",
        "automatic DDL execution is supported",
        "production-ready: true",
    )
    for fragment in forbidden_fragments:
        assert fragment not in combined


def _yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _blocker_codes(payload: dict[str, Any]) -> set[str]:
    return {str(blocker["code"]) for blocker in payload["active_blockers"]}
