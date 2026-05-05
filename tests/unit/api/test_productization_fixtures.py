from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[3]


def test_ppm_api_productization_fixture_follows_manifest_mode() -> None:
    fixture_path = ROOT / "fixtures" / "eval" / "api_productization_ppm_workflow_v1.yaml"
    manifest_path = (
        ROOT / "fixtures" / "pilot" / "ppm_object_selection_v1" / "selected_objects.yaml"
    )
    fixture = yaml.safe_load(fixture_path.read_text(encoding="utf-8"))
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))

    assert fixture["source_manifest"] == str(
        Path("fixtures") / "pilot" / "ppm_object_selection_v1" / "selected_objects.yaml"
    )
    assert fixture["selection_mode"] == manifest["selection_mode"]
    assert "DEPENDENCY_METADATA_INCOMPLETE" in fixture["active_blockers"]
    assert fixture["profile_policy"]["analysis_db_profile_id"] == "ppm"
    assert fixture["profile_policy"]["plf_fallback_allowed"] is False

    request_names = {
        (
            sample["request"]["target"]["schema"],
            sample["request"]["target"]["name"],
        )
        for sample in fixture["sample_requests"]
    }
    if manifest["selection_mode"] == "live_metadata":
        manifest_names = {
            (item["schema"], item["name"]) for item in manifest["stored_procedures"]
        }
        assert request_names
        assert request_names <= manifest_names
    else:
        assert request_names == set()


def test_ppm_api_productization_fixture_has_no_forbidden_evidence() -> None:
    fixture_path = ROOT / "fixtures" / "eval" / "api_productization_ppm_workflow_v1.yaml"
    fixture = yaml.safe_load(fixture_path.read_text(encoding="utf-8"))
    serialized = str(fixture).lower()

    assert "create procedure" not in serialized
    assert "procedure_definition" not in serialized
    assert fixture["forbidden_evidence"] == [
        "row_data",
        "procedure_execution",
        "sql_definition_text",
        "committed_secret",
        "auto_ddl_or_dml",
        "plf_fallback_for_ppm",
    ]
    for sample in _walk_samples(fixture):
        assert sample["expected"]["job_status"] == "REVIEW_PENDING"
        assert "PUBLISHED" in sample["expected"]["artifact_statuses_forbidden"]


def test_p13_validation_approval_audit_fixture_uses_live_manifest_identities() -> None:
    fixture_path = ROOT / "fixtures" / "eval" / "validation_approval_audit_p13_v1.yaml"
    manifest_path = (
        ROOT / "fixtures" / "pilot" / "ppm_object_selection_v1" / "selected_objects.yaml"
    )
    fixture = yaml.safe_load(fixture_path.read_text(encoding="utf-8"))
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))

    assert fixture["source_manifest"] == str(
        Path("fixtures") / "pilot" / "ppm_object_selection_v1" / "selected_objects.yaml"
    )
    assert fixture["selection_mode"] == manifest["selection_mode"]
    assert fixture["storage_contract"]["schema_change_required"] is False
    assert "DEPENDENCY_METADATA_INCOMPLETE" in fixture["active_blockers"]
    assert fixture["profile_policy"]["analysis_db_profile_id"] == "ppm"
    assert fixture["profile_policy"]["plf_fallback_allowed"] is False

    scenario_names = {
        (
            scenario["request"]["target"]["schema"],
            scenario["request"]["target"]["name"],
        )
        for scenario in fixture["sample_scenarios"]
    }
    if manifest["selection_mode"] == "live_metadata":
        manifest_names = {
            (item["schema"], item["name"]) for item in manifest["stored_procedures"]
        }
        assert scenario_names
        assert scenario_names <= manifest_names
    else:
        assert scenario_names == set()


def test_p13_validation_approval_audit_fixture_locks_gate_expectations() -> None:
    fixture_path = ROOT / "fixtures" / "eval" / "validation_approval_audit_p13_v1.yaml"
    fixture = yaml.safe_load(fixture_path.read_text(encoding="utf-8"))
    scenario = fixture["sample_scenarios"][0]
    expected = scenario["expected"]

    assert fixture["public_api_contract"]["approval_checklist_exposed_as_response_fields"] is False
    assert fixture["public_api_contract"]["audit_events_exposed_as_response_fields"] is False
    assert expected["approval_decision_log"]["validation_report_binding"] == (
        "auto_fill_latest_validation_report_id"
    )
    assert expected["audit_event_shape"]["expected_stages"] == [
        "REQUEST",
        "JOB",
        "METADATA",
        "ARTIFACT",
        "VALIDATION",
        "APPROVAL",
    ]
    assert "PUBLISHED" in expected["forbidden_artifact_statuses"]
    assert "unapproved_publish_or_export" in fixture["forbidden_evidence"]


def _walk_samples(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    return list(fixture["sample_requests"])
