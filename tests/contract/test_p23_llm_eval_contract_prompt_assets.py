from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
PROMPTS = ROOT / "ops" / "codex-parallel" / "prompts"
MANIFEST = ROOT / "ops" / "codex-parallel" / "REQUEST_MANIFEST.yaml"
CONTRACT = ROOT / "spec" / "eval" / "p23_llm_sp_analysis_quality_contract.yaml"
FIXTURE = ROOT / "fixtures" / "eval" / "llm_sp_analysis_quality_p23_v1.yaml"

P23_PROMPTS = {
    "P23A": "23a_llm_sp_eval_contract_assets.md",
    "P23B": "23b_llm_sp_eval_fixture_suite.md",
    "P23C": "23c_llm_sp_eval_runner.md",
    "P23D": "23d_llm_sp_eval_docs_readiness.md",
}

REQUIRED_PROMPT_SECTIONS = (
    "## 공통 운영 철학",
    "## 목표",
    "## 읽어야 할 기준 파일",
    "## 허용 수정 경로",
    "## 금지 경로",
    "## 구현 범위",
    "## 검증 명령",
    "## Blocker 보고 기준",
)


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_p23_contract_declares_quality_eval_boundaries() -> None:
    contract = _load_yaml(CONTRACT)

    assert contract["contract_id"] == "p23_llm_sp_analysis_quality@0.1.0"
    assert contract["phase"] == "P23"
    assert contract["production_ready"] is False
    assert contract["runtime_profiles"]["fast_test"]["default_model"] == "gpt-5-nano"
    assert contract["runtime_profiles"]["fast_test"]["override_env"] == (
        "OPENAI_MODEL_FAST_TEST"
    )
    assert contract["runtime_profiles"]["semantic_analysis"]["default_model"] == "gpt-5.5"
    assert contract["runtime_profiles"]["semantic_analysis"]["override_env"] == (
        "OPENAI_MODEL_ANALYSIS"
    )
    assert "model:openai_fast_test@gpt-5-nano@0.1.0" in contract["depends_on"]
    assert contract["scope"]["required_evidence_type"] == "LLM_INFERENCE"
    assert contract["scope"]["validator_obligation"] == {
        "new_dependency_fact_claims": "REVIEW_REQUIRED",
        "new_table_fact_claims": "REVIEW_REQUIRED",
        "new_function_fact_claims": "REVIEW_REQUIRED",
        "low_evidence_business_rule_claims": "REVIEW_REQUIRED",
    }
    assert contract["scope"]["allowed_llm_enrichment_fields"] == [
        "business_rules",
        "modernization_points",
        "risk_flags",
        "review_markers",
        "conversion_guidance",
        "migration_guide_insights",
        "assumptions",
    ]
    assert contract["scope"]["staged_runtime"]["dynamic_evidence_schema"] is True
    assert contract["scope"]["staged_runtime"]["default_sp_concurrency"] == 2
    assert contract["scope"]["staged_runtime"]["high_quality_default"] is True
    assert all(contract["forbidden_behavior"].values())


def test_p23_contract_covers_simple_medium_complex_scenarios() -> None:
    contract = _load_yaml(CONTRACT)
    fixture = _load_yaml(FIXTURE)

    assert [item["complexity"] for item in contract["scenario_matrix"]] == [
        "simple",
        "medium",
        "complex",
    ]
    assert [item["complexity"] for item in fixture["scenarios"]] == [
        "simple",
        "medium",
        "complex",
    ]
    for scenario in fixture["scenarios"]:
        assert scenario["source_kind"] == "synthetic_contract_fixture"
        assert scenario["sp_definition_policy"] == "transient_model_input_only"
        assert "no_raw_trace_storage" in scenario["required_checks"]


def test_p23_fixture_keeps_no_raw_trace_and_fast_test_contract() -> None:
    fixture = _load_yaml(FIXTURE)

    assert fixture["production_ready"] is False
    assert fixture["model_profiles"]["fast_test"]["default_model"] == "gpt-5-nano"
    assert fixture["model_profiles"]["fast_test"]["override_env"] == "OPENAI_MODEL_FAST_TEST"
    assert fixture["model_profiles"]["semantic_analysis"]["override_env"] == (
        "OPENAI_MODEL_ANALYSIS"
    )
    assert fixture["prompt_contract"]["required_evidence_type"] == "LLM_INFERENCE"
    assert fixture["prompt_contract"]["unsupported_fact_status"] == "REVIEW_REQUIRED"
    assert fixture["prompt_contract"]["schema_ref"] == "schema:llm_semantic_analysis@0.3.0"
    assert fixture["prompt_contract"]["staged_runtime"]["sp_fan_out"] is True
    assert fixture["prompt_contract"]["staged_runtime"]["high_quality_default"] is True
    assert fixture["prompt_contract"]["allowed_output_fields"] == [
        "business_rules",
        "modernization_points",
        "risk_flags",
        "review_markers",
        "conversion_guidance",
        "migration_guide_insights",
        "assumptions",
    ]
    assert fixture["safety_expectations"]["forbidden_storage_fields"] == [
        "raw_prompt",
        "raw_sp_definition",
        "raw_openai_response_text",
        "row_data",
        "secrets",
    ]
    for forbidden in ("raw_prompt", "raw_sp_definition", "raw_openai_response_text"):
        assert (
            forbidden
            not in fixture["trace_expectations"]["model_invocation_summary_fields"]
        )
        assert (
            forbidden
            not in fixture["trace_expectations"]["agent_run_summary_fields"]
        )
    assert fixture["trace_expectations"]["forbidden_trace_payload_fields"] == [
        "raw_prompt",
        "raw_sp_definition",
        "raw_openai_response_text",
        "row_data",
        "secrets",
    ]


def test_p23_contract_trace_policy_forbids_raw_row_and_secret_payloads() -> None:
    contract = _load_yaml(CONTRACT)
    forbidden_fields = [
        "raw_prompt",
        "raw_sp_definition",
        "raw_openai_response_text",
        "row_data",
        "secrets",
    ]

    assert (
        contract["trace_policy"]["forbidden_trace_payload_fields"] == forbidden_fields
    )
    for field in forbidden_fields:
        assert field not in contract["trace_policy"]["allowed_model_invocation_fields"]
        assert field not in contract["trace_policy"]["allowed_agent_run_fields"]


def test_p23_prompts_capture_split_contract_and_policy_rules() -> None:
    for prompt_name in P23_PROMPTS.values():
        text = (PROMPTS / prompt_name).read_text(encoding="utf-8")
        for section in REQUIRED_PROMPT_SECTIONS:
            assert section in text
        assert "P23" in text
        assert "production_ready: false" in text
        assert "`gpt-5-nano`" in text
        assert "OPENAI_MODEL_FAST_TEST" in text
        assert "`PLF`" in text
        assert "`PPM`" in text
        assert "PLF fallback" in text
        assert "raw prompt" in text
        assert "raw SP definition" in text
        assert "raw OpenAI response text" in text
        assert "LLM_INFERENCE" in text
        assert "REVIEW_REQUIRED" in text


def test_p23_manifest_declares_split_tracks_and_merge_order() -> None:
    manifest = _load_yaml(MANIFEST)
    tracks = {
        track["id"]: track
        for wave in manifest["waves"]
        for track in wave["tracks"]
    }

    assert "spec/eval/p23_llm_sp_analysis_quality_contract.yaml" in manifest["basis"]
    assert "fixtures/eval/llm_sp_analysis_quality_p23_v1.yaml" in manifest["basis"]
    assert [item for item in manifest["merge_order"] if item.startswith("P23")] == [
        "P23A",
        "P23B",
        "P23C",
        "P23D",
    ]
    assert tracks["P23A"]["depends_on"] == ["P21D"]
    assert tracks["P23B"]["depends_on"] == ["P23A"]
    assert tracks["P23C"]["depends_on"] == ["P23B"]
    assert tracks["P23D"]["depends_on"] == ["P23C"]
    assert tracks["P23A"]["p22_prerequisite"] == (
        "OpenAI LLM Agent Runtime merged and verified"
    )
    for track_id, prompt_name in P23_PROMPTS.items():
        assert tracks[track_id]["prompt"] == f"prompts/{prompt_name}"


def test_p23_docs_reference_contract_prompt_slice() -> None:
    eval_spec = (ROOT / "EVAL_SPEC.md").read_text(encoding="utf-8")
    eval_status = (ROOT / "docs" / "integration-eval-status.md").read_text(
        encoding="utf-8"
    )
    task = (ROOT / "tasks" / "0023-llm-sp-analysis-quality-eval.md").read_text(
        encoding="utf-8"
    )

    for text in (eval_spec, eval_status, task):
        assert "spec/eval/p23_llm_sp_analysis_quality_contract.yaml" in text
        assert "fixtures/eval/llm_sp_analysis_quality_p23_v1.yaml" in text
        assert "gpt-5-nano" in text
        assert "OPENAI_MODEL_FAST_TEST" in text
        assert "production_ready: false" in text
