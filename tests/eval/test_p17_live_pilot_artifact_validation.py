from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from ai_agent_validation import (
    selected_object_refs,
    validate_live_pilot_artifact_package,
)

ROOT = Path(__file__).resolve().parents[2]
P17B_FIXTURE = ROOT / "fixtures" / "eval" / "live_pilot_artifact_validation_p17_v1.yaml"
P17C_FIXTURE = ROOT / "fixtures" / "eval" / "draft_quality_audit_p17_v1.yaml"
P17_BLOCKER_FIXTURE = (
    ROOT / "fixtures" / "eval" / "live_pilot_blocker_closure_p17_v1.yaml"
)
GENERATION_MANIFEST = (
    ROOT / "fixtures" / "generation" / "live_pilot_artifacts_p17_v1" / "manifest.yaml"
)
PILOT_MANIFEST = ROOT / "fixtures" / "pilot" / "ppm_object_selection_v1" / "selected_objects.yaml"
ANALYSIS_EVIDENCE = ROOT / "fixtures" / "analysis" / "ppm_selected_sp_evidence_v1.yaml"


def test_p17b_fixture_context_keeps_ppm_plf_and_no_fallback_boundaries() -> None:
    fixture = _yaml(P17B_FIXTURE)
    manifest = _yaml(PILOT_MANIFEST)
    analysis = _yaml(ANALYSIS_EVIDENCE)

    assert fixture["version"] == "live_pilot_artifact_validation_p17_v1"
    assert fixture["source_db"] == "PPM"
    assert fixture["platform_db_context"] == "PLF"
    assert fixture["selection_mode"] == "live_metadata"
    assert fixture["validation_status"] == "PASSED"

    assert manifest["selection_mode"] == "live_metadata"
    assert manifest["source_db"] == "PPM"
    assert manifest["platform_db_context"] == "PLF"
    assert manifest["active_blockers"] == []
    assert manifest["dependency_evidence_gate"]["status"] == (
        "PASSED_WITH_COMPLEX_SENTINEL_RESIDUAL_REVIEW"
    )

    assert analysis["activeBlockers"] == []
    assert "DEPENDENCY_METADATA_INCOMPLETE" in analysis["closedBlockers"]
    assert fixture["policy_boundaries"]["metadata_only"] is True
    assert fixture["policy_boundaries"]["row_data_allowed"] is False
    assert fixture["policy_boundaries"]["procedure_execution_allowed"] is False
    assert fixture["policy_boundaries"]["ddl_dml_allowed"] is False
    assert fixture["policy_boundaries"]["plf_fallback_allowed"] is False
    assert fixture["policy_boundaries"]["publish_or_export_allowed"] is False


def test_p17b_artifacts_are_draft_metadata_only_and_manifest_bound() -> None:
    fixture = _yaml(P17B_FIXTURE)
    generation_manifest = _yaml(GENERATION_MANIFEST)
    selected_manifest = _yaml(PILOT_MANIFEST)

    summary = validate_live_pilot_artifact_package(
        fixture,
        selected_manifest=selected_manifest,
        generation_manifest=generation_manifest,
    )

    assert summary.passed, summary.issues
    assert summary.selected_object_coverage == 1.0
    assert summary.remaining_release_decision == "NO_GO"

    expected_refs = selected_object_refs(selected_manifest)
    covered_refs = _covered_refs(fixture["artifacts"])
    generation_artifacts = {
        artifact["artifact_id"]: artifact for artifact in generation_manifest["artifacts"]
    }
    assert covered_refs == expected_refs
    assert set(generation_artifacts) == {
        artifact["artifact_id"] for artifact in fixture["artifacts"]
    }

    for artifact in fixture["artifacts"]:
        assert artifact["artifact_status"] == "DRAFT"
        assert artifact["draft_only"] is True
        assert artifact["metadata_only"] is True
        assert artifact["evidence_refs"]
        assert artifact["selected_object_refs"]
        assert artifact["generation_manifest_ref"].startswith(fixture["source_generation_manifest"])
        assert artifact["artifact_version"] == generation_artifacts[artifact["artifact_id"]][
            "artifact_version"
        ]
        assert artifact["artifact_type"] == generation_artifacts[artifact["artifact_id"]][
            "artifact_type"
        ]


def test_p17b_release_critical_validation_items_all_pass_without_overclaim() -> None:
    fixture = _yaml(P17B_FIXTURE)

    required_fields = {
        "rule_id",
        "severity",
        "status",
        "releaseCritical",
        "artifact_ref",
        "evidence_refs",
    }
    release_critical = [
        item for item in fixture["validation_results"] if item["releaseCritical"] is True
    ]
    assert release_critical
    for item in fixture["validation_results"]:
        assert required_fields <= set(item)
        assert item["evidence_refs"]
        if item["releaseCritical"]:
            assert item["status"] == "PASSED"

    assert fixture["quality_report"]["release_critical_validation_status"] == "PASSED"
    assert fixture["quality_report"]["release_critical_failed_count"] == 0
    assert fixture["quality_report"]["release_critical_review_required_count"] == 0
    assert fixture["live_release_decision_after_p17b"]["decision"] == "NO_GO"
    assert fixture["active_blockers_after_p17b"] == ["DRAFT_QUALITY_EVIDENCE_MISSING"]
    assert "production-ready: true" not in P17B_FIXTURE.read_text(encoding="utf-8")
    assert "PUBLISHED" not in P17B_FIXTURE.read_text(encoding="utf-8")


def test_p17c_draft_quality_binds_p17b_targets_and_closes_blocker() -> None:
    fixture = _yaml(P17C_FIXTURE)
    p17b = _yaml(P17B_FIXTURE)

    assert fixture["version"] == "draft_quality_audit_p17_v1"
    assert fixture["track"] == "P17C"
    assert fixture["source_p17b_validation_package"] == (
        "fixtures/eval/live_pilot_artifact_validation_p17_v1.yaml"
    )
    assert fixture["source_db"] == "PPM"
    assert fixture["platform_db_context"] == "PLF"
    assert fixture["draftQualityDecision"] == "ACCEPT_DRAFT"
    assert fixture["draft_quality_status"] == "EVIDENCE_BOUND"
    assert fixture["active_blockers_after_p17c"] == []
    assert "DRAFT_QUALITY_EVIDENCE_MISSING" in fixture["closed_blockers_after_p17c"]
    assert fixture["completion_status"]["blocker_closed"] is True
    assert fixture["completion_status"]["no_go_preserved"] is True
    assert fixture["live_release_decision_after_p17c"]["decision"] == "NO_GO"
    assert fixture["known_limitations"][0]["code"] == "P17D_RELEASE_DECISION_PENDING"

    quality = fixture["draft_quality_record"]
    assert quality["quality_ref"] == "p17c-draft-quality-saoh-20260510"
    assert quality["decision"] == "ACCEPT_DRAFT"
    assert quality["actor"] == "saoh"
    assert quality["timestamp"] == "2026-05-10T13:15:00+09:00"
    assert quality["correlation_id"] == "corr-p17c-draft-quality-20260510"
    assert quality["not_synthesized"] is True
    assert quality["bound_artifact_set"] == {
        "artifactSetId": "p17b-live-pilot-artifact-set",
        "artifactSetVersion": "2026-05-06.p17b.v1",
        "validationReportId": "p17b-live-pilot-artifact-validation-report",
    }

    binding = fixture["validation_package_binding"]
    assert binding["validation_status"] == p17b["validation_status"]
    assert binding["artifact_set_ref"]["artifact_set_id"] == p17b["artifact_set"][
        "artifact_set_id"
    ]
    assert binding["artifact_set_ref"]["artifact_set_version"] == p17b["artifact_set"][
        "artifact_set_version"
    ]
    assert binding["validation_ref"]["validation_report_id"] == p17b["artifact_set"][
        "validation_report_id"
    ]

    p17b_artifacts = {artifact["artifact_id"]: artifact for artifact in p17b["artifacts"]}
    binding_targets = {
        target["artifact_id"]: target for target in fixture["binding_targets"]
    }
    assert set(binding_targets) == set(p17b_artifacts)
    for artifact_id, target in binding_targets.items():
        source = p17b_artifacts[artifact_id]
        assert target["artifact_version"] == source["artifact_version"]
        assert target["artifact_type"] == source["artifact_type"]
        assert target["validation_report_id"] == p17b["artifact_set"][
            "validation_report_id"
        ]
        assert target["selected_object_refs"] == source["selected_object_refs"]
        assert set(target["evidence_refs"]) == {
            ref["evidence_id"] for ref in source["evidence_refs"]
        }

    audit = fixture["audit_event_binding"]
    assert audit["action"] == "DRAFT_QUALITY_EVIDENCE_RECORDED"
    assert audit["actor"] == "saoh"
    assert audit["quality_ref"] == quality["quality_ref"]
    assert audit["validation_ref"] == p17b["artifact_set"]["validation_report_id"]
    assert audit["correlation_id"] == quality["correlation_id"]
    assert set(audit["artifact_refs"]) == {
        f"{target['artifact_id']}@{target['artifact_version']}"
        for target in fixture["binding_targets"]
    }
    assert audit["selected_object_refs_source"] == "binding_targets.selected_object_refs"
    assert audit["evidence_refs_source"] == "binding_targets.evidence_refs"
    assert audit["audit_trail"]
    required_audit_fields = set(audit["required_fields"])
    assert {
        "actor",
        "action",
        "artifactRef",
        "artifactVersion",
        "validationRef",
        "qualityRef",
        "selectedObjectRefs",
        "evidenceRefs",
        "timestamp",
        "correlationId",
    } <= required_audit_fields

    text = P17C_FIXTURE.read_text(encoding="utf-8")
    assert "production-ready: true" not in text
    assert "PUBLISHED" not in text


def test_p17_blocker_fixture_references_p17c_draft_quality_binding() -> None:
    fixture = _yaml(P17_BLOCKER_FIXTURE)

    assert fixture["current_state"]["p17c_draft_quality_audit_fixture"] == (
        "fixtures/eval/draft_quality_audit_p17_v1.yaml"
    )
    assert fixture["current_state"]["p17c_draft_quality_status"] == "EVIDENCE_BOUND"
    assert fixture["current_state"]["p17c_blocker_closed"] is True
    assert fixture["current_state"]["p17d_release_decision_pending"] is False
    assert fixture["current_state"]["p17d_release_decision_completed"] is True
    assert fixture["current_state"]["p17d_final_decision"] == "CONDITIONAL_GO"
    assert fixture["current_state"]["active_blockers_to_close"] == []
    assert "DRAFT_QUALITY_EVIDENCE_MISSING" in fixture["current_state"][
        "blockers_closed"
    ]


def test_p17d_conditional_go_requires_all_bound_evidence_and_hard_live_gates() -> None:
    fixture = _yaml(P17_BLOCKER_FIXTURE)
    p17b = _yaml(P17B_FIXTURE)
    p17c = _yaml(P17C_FIXTURE)

    assert fixture["current_state"]["live_pilot_release_decision"] == "CONDITIONAL_GO"
    assert fixture["final_decision_policy"]["current_decision"] == "CONDITIONAL_GO"
    assert fixture["final_decision_policy"]["conditional_go_scope"] == (
        "scoped_live_pilot_candidate_only"
    )

    requirements = fixture["conditional_go_requires"]
    assert requirements["dependency_metadata"]["blocker_closed"] in fixture["current_state"][
        "blockers_closed"
    ]
    assert p17b["validation_status"] == requirements["validation"]["required_status"]
    assert requirements["validation"]["release_critical_review_required_allowed"] is False
    assert p17c["draftQualityDecision"] == requirements["draft_quality"]["required_decision"]
    assert p17c["draft_quality_record"]["not_synthesized"] is True
    assert p17c["validation_package_binding"]["validation_ref"][
        "validation_report_id"
    ] == p17b["artifact_set"]["validation_report_id"]

    verification = fixture["p17d_hard_live_verification"]
    assert verification["status"] == "PASSED"
    assert len(verification["commands"]) == 2
    assert all(command["status"] == "PASSED" for command in verification["commands"])
    assert any(
        'PYTEST_ARGS="tests/e2e tests/eval"' in command["command"]
        for command in verification["commands"]
    )
    assert any(
        'PYTEST_ARGS="tests/e2e tests/eval tests/contract"' in command["command"]
        for command in verification["commands"]
    )
    assert {
        "raw_logs",
        "secrets",
        "row_data",
        "procedure_execution",
        "raw_definition_text",
    } <= set(verification["forbidden_evidence_excluded"])

    boundaries = set(fixture["final_decision_policy"]["conditional_go_boundaries"])
    assert {
        "generated_artifacts_are_draft_only",
        "metadata_only_ppm_profile",
        "no_plf_fallback",
        "no_publish_or_export",
        "no_row_data",
        "no_procedure_execution",
        "no_auto_ddl_or_dml",
    } <= boundaries


def _yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _covered_refs(artifacts: list[dict[str, Any]]) -> set[str]:
    refs: set[str] = set()
    for artifact in artifacts:
        refs.update(artifact["selected_object_refs"])
    return refs
