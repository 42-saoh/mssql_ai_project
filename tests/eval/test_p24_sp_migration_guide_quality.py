from __future__ import annotations

import json
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "spec" / "eval" / "p24_sp_migration_guide_quality_contract.yaml"
FIXTURE = ROOT / "fixtures" / "eval" / "sp_migration_guide_quality_p24_v1.yaml"

EXPECTED_SCENARIOS = {
    "p24_simple_read_only_lookup": "simple",
    "p24_medium_transactional_branching_dml": "medium",
    "p24_complex_dynamic_cross_db_extract": "complex",
}
EXPECTED_SCORE_FIELDS = {
    "requiredSectionCoverage",
    "evidenceLinkedClaimCoverage",
    "dmlMatrixCoverage",
    "branchCallFlowCoverage",
    "unsupportedClaimReviewRequiredRatio",
    "storageSafetyFindings",
}
THRESHOLD_FIELD_MAP = {
    "required_section_coverage_min": "requiredSectionCoverageMin",
    "evidence_linked_claim_coverage_min": "evidenceLinkedClaimCoverageMin",
    "dml_matrix_coverage_min": "dmlMatrixCoverageMin",
    "branch_call_flow_coverage_min": "branchCallFlowCoverageMin",
    "unsupported_claim_review_required_ratio_min": (
        "unsupportedClaimReviewRequiredRatioMin"
    ),
    "forbidden_storage_findings_max": "forbiddenStorageFindingsMax",
}
FORBIDDEN_TEXT_MARKERS = (
    "CREATE OR ALTER PROCEDURE",
    "CREATE PROCEDURE",
    "CREATE PROC",
    "ALTER PROCEDURE",
    "CREATE FUNCTION",
)


def test_p24b_fixture_declares_contract_boundaries() -> None:
    fixture = _fixture()
    contract = _contract()

    assert fixture["fixture_suite_id"] == "sp_migration_guide_quality_p24_v1"
    assert fixture["contract_ref"] == contract["contract_id"]
    assert fixture["phase"] == "P24"
    assert fixture["status"] == "authored_p24b"
    assert fixture["production_ready"] is False
    assert fixture["model_profiles"]["fast_test"]["default_model"] == "gpt-5-nano"
    assert fixture["artifact_scope"]["existing_artifact_types"] == contract["scope"][
        "existing_artifact_types"
    ]
    assert fixture["artifact_scope"]["new_persisted_artifact_types_allowed"] is False
    assert fixture["quality_thresholds"] == contract["quality_thresholds"]
    assert fixture["report_contract"]["fields"] == contract["scope"]["report_fields"]


def test_p24b_fixture_covers_simple_medium_complex_scenarios() -> None:
    scenarios = _scenarios(_fixture())

    assert {scenario["fixture_id"] for scenario in scenarios} == set(EXPECTED_SCENARIOS)
    assert {
        scenario["fixture_id"]: scenario["complexity"] for scenario in scenarios
    } == EXPECTED_SCENARIOS
    for scenario in scenarios:
        assert scenario["source_kind"] == "synthetic_contract_fixture"
        assert scenario["guide_source_policy"] == "sanitized_facts_only"
        assert scenario["fixture_authoring_status"] == "authored_p24b"
        assert scenario["artifacts_under_test"] == ["SP_ANALYSIS_DOC", "DEPENDENCY_REPORT"]


def test_p24b_required_sections_are_complete_for_every_scenario() -> None:
    contract = _contract()
    required_sections = _required_sections(contract)

    for scenario in _scenarios(_fixture()):
        sections = scenario["section_expectations"]
        section_ids = {section["id"] for section in sections}
        report = scenario["expected_quality_report"]
        scores = _score_scenario(scenario, contract)

        assert section_ids == required_sections
        assert set(report["sectionCoverage"]) == required_sections
        assert all(report["sectionCoverage"].values())
        assert scores["requiredSectionCoverage"] == 1.0
        for section in sections:
            assert section["title"]
            assert section["evidence_refs"], (scenario["fixture_id"], section["id"])
            assert section["claims"], (scenario["fixture_id"], section["id"])


def test_p24b_dependency_inventory_and_dml_matrix_cover_contract_operations() -> None:
    fixture = _fixture()
    contract = _contract()
    required_summary_fields = set(
        contract["dependency_inventory_requirements"]["required_summaries"]
    )
    required_object_kinds = set(
        contract["dependency_inventory_requirements"]["object_kinds"]
    )
    required_operations = set(
        contract["dependency_inventory_requirements"]["operation_fields"]
    )

    object_kinds = {
        item["object_kind"]
        for scenario in _scenarios(fixture)
        for item in scenario["dependency_inventory"]
    }
    operations = {
        operation
        for scenario in _scenarios(fixture)
        for item in scenario["dml_matrix"]
        for operation in [item["operation"]]
    }

    assert required_object_kinds <= object_kinds
    assert required_operations <= operations
    for scenario in _scenarios(fixture):
        for item in scenario["dependency_inventory"]:
            assert required_summary_fields <= set(item)
            assert item["evidence_refs"], (scenario["fixture_id"], item["object_ref"])
        scores = _score_scenario(scenario, contract)
        assert scores["dmlMatrixCoverage"] >= contract["quality_thresholds"][
            "dml_matrix_coverage_min"
        ]


def test_p24b_branch_call_flow_and_evidence_scores_meet_thresholds() -> None:
    fixture = _fixture()
    contract = _contract()
    thresholds = contract["quality_thresholds"]

    for scenario in _scenarios(fixture):
        scores = _score_scenario(scenario, contract)
        report_scores = scenario["expected_quality_report"]["scores"]

        assert set(report_scores) == EXPECTED_SCORE_FIELDS
        assert report_scores == scores
        assert scores["requiredSectionCoverage"] >= thresholds[
            "required_section_coverage_min"
        ]
        assert scores["evidenceLinkedClaimCoverage"] >= thresholds[
            "evidence_linked_claim_coverage_min"
        ]
        assert scores["dmlMatrixCoverage"] >= thresholds["dml_matrix_coverage_min"]
        assert scores["branchCallFlowCoverage"] >= thresholds[
            "branch_call_flow_coverage_min"
        ]
        assert scores["unsupportedClaimReviewRequiredRatio"] >= thresholds[
            "unsupported_claim_review_required_ratio_min"
        ]
        assert scores["storageSafetyFindings"] <= thresholds[
            "forbidden_storage_findings_max"
        ]


def test_p24b_expected_report_fields_match_contract_and_stay_draft_only() -> None:
    contract = _contract()
    expected_fields = set(contract["scope"]["report_fields"])
    expected_thresholds = {
        report_key: contract["quality_thresholds"][contract_key]
        for contract_key, report_key in THRESHOLD_FIELD_MAP.items()
    }

    for scenario in _scenarios(_fixture()):
        report = scenario["expected_quality_report"]

        assert set(report) == expected_fields
        assert report["status"] == "PASSED"
        assert report["productionReady"] is False
        assert report["thresholds"] == expected_thresholds
        assert report["evidenceRefs"]
        assert report["storageSafetyFindings"] == []


def test_p24b_review_required_obligations_match_contract() -> None:
    fixture = _fixture()
    contract = _contract()
    expected_obligations = set(contract["validator_obligation"])
    actual_obligations = {
        claim["obligation"]
        for scenario in _scenarios(fixture)
        for claim in scenario["unsupported_claim_expectations"]
    }

    assert actual_obligations == expected_obligations
    for scenario in _scenarios(fixture):
        expected_codes = {
            claim["claim_code"] for claim in scenario["unsupported_claim_expectations"]
        }
        assert expected_codes <= set(
            scenario["expected_quality_report"]["reviewRequiredFindings"]
        )
        for claim in scenario["unsupported_claim_expectations"]:
            assert claim["expected_status"] == "REVIEW_REQUIRED"
            assert claim["evidence_refs"]


def test_p24b_target_context_uses_ppm_without_plf_fallback() -> None:
    for scenario in _scenarios(_fixture()):
        context = scenario["db_context"]

        assert context["metadata_profile_id"] == "ppm"
        assert context["target_db"] == "PPM"
        assert context["platform_db"] == "PLF"
        assert context["plf_fallback"] == "forbidden"
        assert scenario["target_ref"].startswith("PPM.")


def test_p24b_storage_safety_payload_is_sanitized() -> None:
    fixture = _fixture()
    forbidden_fields = set(fixture["safety_expectations"]["forbidden_payload_fields"])
    serialized = json.dumps(fixture, ensure_ascii=False, sort_keys=True)

    for marker in FORBIDDEN_TEXT_MARKERS:
        assert marker not in serialized
    assert "MIGRATION_GUIDE.md" not in serialized
    assert forbidden_fields.isdisjoint(set(_iter_mapping_keys(fixture)))

    for scenario in _scenarios(fixture):
        assert "procedure_definition" not in set(_iter_mapping_keys(scenario))
        assert scenario["expected_quality_report"]["storageSafetyFindings"] == []


def _fixture() -> dict[str, Any]:
    return yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))


def _contract() -> dict[str, Any]:
    return yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))


def _scenarios(fixture: Mapping[str, Any]) -> list[dict[str, Any]]:
    return list(fixture["scenarios"])


def _required_sections(contract: Mapping[str, Any]) -> set[str]:
    return {item["id"] for item in contract["scope"]["required_sections"]}


def _score_scenario(
    scenario: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> dict[str, float | int]:
    required_sections = _required_sections(contract)
    section_ids = {section["id"] for section in scenario["section_expectations"]}
    expected_operations = set(scenario["expected_dml_operations"])
    matrix_operations = {
        item["operation"] for item in scenario["dml_matrix"] if item["evidence_refs"]
    }
    unsupported_claims = scenario["unsupported_claim_expectations"]
    branches = scenario["call_flow"]["branches"]
    evidence_claims = list(_iter_evidence_claims(scenario))

    return {
        "requiredSectionCoverage": _ratio(
            len(required_sections & section_ids),
            len(required_sections),
        ),
        "evidenceLinkedClaimCoverage": _ratio(
            sum(1 for item in evidence_claims if item.get("evidence_refs")),
            len(evidence_claims),
        ),
        "dmlMatrixCoverage": _ratio(
            len(expected_operations & matrix_operations),
            len(expected_operations),
        ),
        "branchCallFlowCoverage": _ratio(
            sum(1 for branch in branches if _branch_has_evidence(branch)),
            len(branches),
        ),
        "unsupportedClaimReviewRequiredRatio": _ratio(
            sum(
                1
                for claim in unsupported_claims
                if claim["expected_status"] == "REVIEW_REQUIRED"
            ),
            len(unsupported_claims),
        ),
        "storageSafetyFindings": len(
            scenario["expected_quality_report"]["storageSafetyFindings"]
        ),
    }


def _iter_evidence_claims(scenario: Mapping[str, Any]) -> Iterator[Mapping[str, Any]]:
    for fact in scenario["sanitized_facts"]:
        yield fact
    for section in scenario["section_expectations"]:
        yield section
        yield from section["claims"]
    yield from scenario["dependency_inventory"]
    yield from scenario["dml_matrix"]
    for branch in scenario["call_flow"]["branches"]:
        yield branch
        yield from branch["actions"]
    yield from scenario["phase_risk_metrics"]["risk_flags"]
    for parameter in scenario["appendix_mappings"]["parameters"]:
        yield parameter
    for result_field in scenario["appendix_mappings"]["result_fields"]:
        yield result_field
    yield from scenario["unsupported_claim_expectations"]


def _branch_has_evidence(branch: Mapping[str, Any]) -> bool:
    return bool(branch["evidence_refs"]) and all(
        action["evidence_refs"] for action in branch["actions"]
    )


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 1.0
    return numerator / denominator


def _iter_mapping_keys(value: Any) -> Sequence[str]:
    keys: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            keys.append(str(key))
            keys.extend(_iter_mapping_keys(item))
    elif isinstance(value, list | tuple):
        for item in value:
            keys.extend(_iter_mapping_keys(item))
    return keys
