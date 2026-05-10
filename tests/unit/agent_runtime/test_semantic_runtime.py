from __future__ import annotations

from typing import Any

from ai_agent_runtime import FakeModelGateway, build_semantic_analysis_run
from ai_agent_runtime.gateway import model_profile_from_env
from ai_agent_runtime.models import semantic_output_schema
from ai_agent_runtime.quality_eval import evaluate_p23_semantic_quality
from ai_agent_runtime.prompts import render_semantic_analysis_prompt


def test_prompt_renderer_hashes_inputs_and_sanitizes_metadata_copy() -> None:
    prompt = render_semantic_analysis_prompt(
        target_ref="dbo.usp_Demo",
        metadata={
            "procedureDefinition": {
                "definition": "CREATE PROCEDURE dbo.usp_Demo AS SELECT 1",
                "definitionHash": "abc",
            }
        },
        static_analysis={"procedure": {"identifier": {"full_name": "dbo.usp_Demo"}}},
        procedure_definition="CREATE PROCEDURE dbo.usp_Demo AS SELECT 1",
    )

    assert len(prompt.input_hash) == 64
    assert len(prompt.prompt_hash) == 64
    assert "CREATE PROCEDURE dbo.usp_Demo" in prompt.user_prompt
    assert '"definitionHash": "abc"' in prompt.user_prompt


def test_fake_gateway_returns_schema_valid_sanitized_invocation() -> None:
    prompt = render_semantic_analysis_prompt(
        target_ref="dbo.usp_Demo",
        metadata={"procedureDefinition": {"definitionHash": "abc"}},
        static_analysis=None,
        procedure_definition=None,
    )
    profile = model_profile_from_env("openai_fast_test")
    result = FakeModelGateway().invoke_semantic_analysis(prompt=prompt, profile=profile)

    assert result.model == "gpt-5-nano"
    assert result.model_profile_id == "openai_fast_test"
    assert result.status == "SUCCEEDED"
    assert "businessRules" in result.structured_output
    assert "CREATE PROCEDURE" not in str(result.to_storage_dict())


def test_fast_test_profile_model_is_fixed_to_gpt_5_nano(monkeypatch: Any) -> None:
    monkeypatch.setenv("OPENAI_MODEL_FAST_TEST", "not-a-contract-model")

    profile = model_profile_from_env("openai_fast_test")

    assert profile.model == "gpt-5-nano"
    assert profile.profile_id == "openai_fast_test"


def test_fake_gateway_can_return_fixture_output_by_target_ref() -> None:
    prompt = render_semantic_analysis_prompt(
        target_ref="dbo.usp_Demo",
        metadata={},
        static_analysis=None,
        procedure_definition=None,
    )
    profile = model_profile_from_env("openai_fast_test")
    result = FakeModelGateway(
        output_by_target_ref={
            "dbo.usp_Demo": {
                "businessRules": [
                    {
                        "category": "CUSTOM_FIXTURE_RULE",
                        "summary": "Fixture-provided output for deterministic eval.",
                        "status": "INFERRED_DESCRIPTION",
                        "evidenceRefs": ["fact_demo"],
                    }
                ],
                "modernizationPoints": [],
                "riskFlags": [],
                "reviewMarkers": [],
                "assumptions": [],
            }
        }
    ).invoke_semantic_analysis(prompt=prompt, profile=profile)

    assert result.structured_output["businessRules"][0]["category"] == "CUSTOM_FIXTURE_RULE"
    assert result.model == "gpt-5-nano"


def test_semantic_output_schema_is_strict_for_responses_api() -> None:
    schema = semantic_output_schema()

    assert schema["additionalProperties"] is False
    assert schema["required"] == [
        "businessRules",
        "modernizationPoints",
        "riskFlags",
        "reviewMarkers",
        "assumptions",
    ]
    business_rule_schema = schema["properties"]["businessRules"]["items"]
    assert business_rule_schema["additionalProperties"] is False
    assert business_rule_schema["required"] == [
        "category",
        "summary",
        "status",
        "evidenceRefs",
    ]


def test_semantic_run_payload_excludes_raw_prompt_and_sql_from_storage() -> None:
    payload = build_semantic_analysis_run(
        target_ref="dbo.usp_Demo",
        metadata={"procedureDefinition": {"definitionHash": "abc"}},
        static_analysis=None,
        procedure_definition="CREATE PROCEDURE dbo.usp_Demo AS SELECT 1",
        model_gateway=FakeModelGateway(),
        profile_id="openai_fast_test",
    )

    stored = payload.to_storage_dict()
    assert stored["modelInvocation"]["model"] == "gpt-5-nano"
    assert "prompt" not in stored["modelInvocation"]
    assert "CREATE PROCEDURE" not in str(stored)


def test_p23_quality_report_flags_unsafe_payload_without_leaking_raw_field_name() -> None:
    run = build_semantic_analysis_run(
        target_ref="dbo.usp_Demo",
        metadata={},
        static_analysis=None,
        procedure_definition=None,
        model_gateway=FakeModelGateway(
            output_by_target_ref={
                "dbo.usp_Demo": {
                    "businessRules": [
                        {
                            "category": "DEMO_RULE",
                            "summary": "Demo rule.",
                            "status": "INFERRED_DESCRIPTION",
                            "evidenceRefs": ["fact_demo"],
                        }
                    ],
                    "modernizationPoints": [],
                    "riskFlags": [],
                    "reviewMarkers": [],
                    "assumptions": [],
                }
            }
        ),
        profile_id="openai_fast_test",
    )

    report = evaluate_p23_semantic_quality(
        scenario={
            "fixture_id": "demo",
            "target_ref": "dbo.usp_Demo",
            "deterministic_facts": [{"id": "fact_demo"}],
            "transient_model_input": {"procedure_definition": "CREATE PROCEDURE demo"},
            "golden_expected_semantic_output": {
                "business_rules": [
                    {
                        "category": "DEMO_RULE",
                        "summary": "Demo rule.",
                        "status": "INFERRED_DESCRIPTION",
                        "evidence_refs": ["fact_demo"],
                    }
                ],
                "modernization_points": [],
                "risk_flags": [],
                "review_markers": [],
                "assumptions": [],
            },
            "unsupported_claim_expectations": [],
        },
        run=run,
        thresholds={
            "semantic_recall_min": 0.75,
            "evidence_discipline_min": 0.9,
            "unreviewed_overclaims_max": 0,
            "storage_safety_findings_max": 0,
        },
        additional_storage_payloads=({"raw_prompt": "redacted by report"},),
    )

    serialized = str(report)
    assert report["status"] == "FAILED"
    assert report["storageSafety"]["findingCount"] == 1
    assert "raw_prompt" not in serialized
    assert "redacted by report" not in serialized
