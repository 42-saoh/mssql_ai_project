from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from ai_agent_runtime import FakeModelGateway, build_semantic_analysis_run
from ai_agent_runtime.models import LlmSemanticAnalysisOutput

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "fixtures" / "eval" / "llm_sp_analysis_quality_p23_v1.yaml"

EXPECTED_SCENARIOS = {
    "p23_simple_read_only_lookup": "simple",
    "p23_medium_branching_transaction": "medium",
    "p23_complex_dynamic_sql_cross_db": "complex",
}
GOLDEN_OUTPUT_FIELDS = {
    "business_rules",
    "modernization_points",
    "risk_flags",
    "review_markers",
    "assumptions",
}
OUTPUT_LIST_FIELDS = (
    "business_rules",
    "modernization_points",
    "risk_flags",
    "review_markers",
)


def test_p23b_fixture_covers_required_simple_medium_complex_scenarios() -> None:
    fixture = _fixture()
    scenarios = _scenarios(fixture)

    assert fixture["production_ready"] is False
    assert fixture["status"] == "authored_p23b"
    assert fixture["model_profiles"]["fast_test"]["default_model"] == "gpt-5-nano"
    assert {scenario["fixture_id"] for scenario in scenarios} == set(EXPECTED_SCENARIOS)
    assert {
        scenario["fixture_id"]: scenario["complexity"] for scenario in scenarios
    } == EXPECTED_SCENARIOS
    assert all(
        scenario["fixture_authoring_status"] == "authored_p23b"
        for scenario in scenarios
    )


def test_p23b_golden_outputs_are_schema_valid_and_minimum_complete() -> None:
    for scenario in _scenarios(_fixture()):
        output = scenario["golden_expected_semantic_output"]
        minimums = scenario["required_expected_outputs"]

        assert set(output) == GOLDEN_OUTPUT_FIELDS
        LlmSemanticAnalysisOutput.model_validate(output)
        assert len(output["business_rules"]) >= minimums["business_rules_min"]
        assert len(output["modernization_points"]) >= minimums["modernization_points_min"]
        assert len(output["risk_flags"]) >= minimums["risk_flags_min"]
        assert len(output["review_markers"]) >= minimums["review_markers_min"]
        assert len(output["assumptions"]) >= minimums["assumptions_min"]


def test_p23b_golden_evidence_refs_point_to_deterministic_facts() -> None:
    for scenario in _scenarios(_fixture()):
        fact_ids = {fact["id"] for fact in scenario["deterministic_facts"]}
        assert fact_ids
        assert scenario["llm_evidence_expectation"]["evidence_type"] == "LLM_INFERENCE"
        assert scenario["llm_evidence_expectation"]["accepted_without_review"] is False

        for field_name in OUTPUT_LIST_FIELDS:
            for item in scenario["golden_expected_semantic_output"][field_name]:
                evidence_refs = item["evidence_refs"]
                assert evidence_refs, (scenario["fixture_id"], field_name, item)
                assert set(evidence_refs) <= fact_ids


def test_p23b_unsupported_dependency_table_function_claims_stay_review_required() -> None:
    complex_scenario = _scenario("p23_complex_dynamic_sql_cross_db")
    marker_status_by_code = {
        marker["code"]: marker["status"]
        for marker in complex_scenario["golden_expected_semantic_output"][
            "review_markers"
        ]
    }

    claim_types = {
        claim["claim_type"] for claim in complex_scenario["unsupported_claim_expectations"]
    }
    assert claim_types == {"dependency", "function", "table"}
    for claim in complex_scenario["unsupported_claim_expectations"]:
        assert claim["expected_status"] == "REVIEW_REQUIRED"
        assert marker_status_by_code[claim["claim_code"]] == "REVIEW_REQUIRED"


def test_p23b_target_context_uses_ppm_without_plf_fallback() -> None:
    for scenario in _scenarios(_fixture()):
        context = scenario["db_context"]

        assert context["metadata_profile_id"] == "ppm"
        assert context["target_db"] == "PPM"
        assert context["platform_db"] == "PLF"
        assert context["plf_fallback"] == "forbidden"
        assert scenario["target_ref"].startswith("PPM.")
        assert scenario["transient_model_input"]["target_ref"].startswith("PPM.")


def test_p23b_trace_expectations_exclude_raw_payload_fields() -> None:
    fixture = _fixture()
    forbidden = set(fixture["trace_expectations"]["forbidden_trace_payload_fields"])

    for scenario in _scenarios(fixture):
        trace_expectations = scenario["trace_storage_expectations"]
        procedure_definition = scenario["transient_model_input"]["procedure_definition"]
        serialized_trace = json.dumps(trace_expectations, sort_keys=True)

        assert procedure_definition not in serialized_trace
        assert trace_expectations["stored_prompt_text"] is False
        assert trace_expectations["stored_procedure_definition_text"] is False
        assert trace_expectations["stored_provider_response_text"] is False
        assert forbidden.isdisjoint(trace_expectations["model_invocation_summary_fields"])
        assert forbidden.isdisjoint(trace_expectations["agent_run_summary_fields"])


def test_p23b_default_runtime_path_uses_fake_gateway_and_sanitized_storage(
    monkeypatch: Any,
) -> None:
    monkeypatch.delenv("OPENAI_MODEL_FAST_TEST", raising=False)

    for scenario in _scenarios(_fixture()):
        run = build_semantic_analysis_run(
            target_ref=scenario["target_ref"],
            metadata={
                "dbContext": scenario["db_context"],
                "deterministicFacts": scenario["deterministic_facts"],
            },
            static_analysis=scenario["transient_model_input"]["static_analysis"],
            procedure_definition=scenario["transient_model_input"][
                "procedure_definition"
            ],
            model_gateway=FakeModelGateway(),
            profile_id="openai_fast_test",
        )

        stored = run.to_storage_dict()
        model_invocation = stored["modelInvocation"]
        expected_invocation = scenario["trace_storage_expectations"][
            "expected_model_invocation"
        ]
        serialized = json.dumps(stored, sort_keys=True)

        assert model_invocation["provider"] == expected_invocation["provider"]
        assert model_invocation["model"] == expected_invocation["model"]
        assert model_invocation["modelProfileId"] == expected_invocation[
            "model_profile_id"
        ]
        assert scenario["transient_model_input"]["procedure_definition"] not in serialized
        assert "CREATE OR ALTER PROCEDURE" not in serialized
        assert "raw_prompt" not in serialized
        assert "raw_sp_definition" not in serialized
        assert "raw_openai_response_text" not in serialized


def _fixture() -> dict[str, Any]:
    return yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))


def _scenarios(fixture: dict[str, Any]) -> list[dict[str, Any]]:
    return list(fixture["scenarios"])


def _scenario(fixture_id: str) -> dict[str, Any]:
    scenarios = {
        scenario["fixture_id"]: scenario for scenario in _scenarios(_fixture())
    }
    return scenarios[fixture_id]
