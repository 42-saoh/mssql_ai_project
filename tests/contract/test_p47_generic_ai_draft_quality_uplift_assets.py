from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from ai_agent_runtime import AI_JAVA_MYBATIS_DRAFT_PACK_PROMPT_VERSION
from ai_agent_runtime.gateway import model_profile_from_env
from ai_agent_runtime.prompts import render_ai_java_mybatis_draft_pack_prompt

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "spec" / "eval" / "p47_generic_ai_draft_quality_uplift_contract.yaml"
SKILLS = ROOT / ".agents" / "skills"
ENV_EXAMPLE = ROOT / ".env.example"
PROBE = ROOT / "apps" / "api" / "scripts" / "p42_live_ai_draft_pack_probe.py"
POLICY = ROOT / "POLICY.md"
TOOLS = ROOT / "TOOLS.md"
EVAL_SPEC = ROOT / "EVAL_SPEC.md"


def _yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_p47_contract_declares_generic_quality_uplift() -> None:
    contract = _yaml(CONTRACT)

    assert contract["contract_id"] == "p47_generic_ai_draft_quality_uplift@0.1.0"
    assert contract["decision"]["framework_runtime_status"] == "adopted"
    assert contract["decision"]["quality_strategy"] == "generic_coverage_first"
    assert contract["decision"]["generated_artifacts_production_ready"] is False
    assert contract["prompt_contract"]["prompt_version"] == (
        "prompt:ai_java_mybatis_draft_pack@0.2.0"
    )
    assert contract["prompt_contract"]["evidence_bundle"] == "DraftPackEvidenceBundle.v0.1"
    assert contract["quality_gates"]["manage_bond_role"] == (
        "benchmark_signal_only_not_runtime_answer_key"
    )
    assert contract["live_policy"]["latest_audit"]["p45_stage"] == "final"
    assert contract["live_policy"]["latest_audit"]["p45_blocker"] == "none"
    assert contract["live_policy"]["latest_audit"]["p45_current_env_status"] == (
        "compatible_pgpt_endpoint_passed_with_explicit_openai_agents_runtime"
    )
    assert contract["live_policy"]["latest_audit"]["p45_official_override_status"] == (
        "historical_blocked_authentication_error"
    )
    assert contract["live_policy"]["latest_audit"]["p42_status"] == (
        "passed_sanitized_fixture_live_mode"
    )
    assert contract["live_policy"]["latest_audit"]["p42_live_ppm_current_rerun_status"] == (
        "not_rerun_without_explicit_raw_sp_export_approval"
    )
    assert contract["live_policy"]["p42_raw_sp_external_export_status"] == (
        "resolved_by_sanitized_fixture_live_mode"
    )


def test_p47_prompt_contains_generic_evidence_bundle_without_raw_payloads() -> None:
    prompt = render_ai_java_mybatis_draft_pack_prompt(
        target_ref="PPM.dbo.SyntheticComplex_PRC",
        sanitized_draft_context={
            "targetRef": "PPM.dbo.SyntheticComplex_PRC",
            "operations": [
                {"operationId": "readItem", "statementRefs": ["stmt.select"]},
                {"operationId": "writeItem", "statementRefs": ["stmt.update"]},
            ],
            "statementEvidence": [
                {
                    "statementId": "stmt.select",
                    "operation": "readItem",
                    "evidenceRefs": ["ev.select"],
                },
                {
                    "statementId": "stmt.update",
                    "operation": "writeItem",
                    "evidenceRefs": ["ev.update"],
                    "reviewMarkers": ["TRANSACTION_BOUNDARY_REVIEW_REQUIRED"],
                },
            ],
            "dependencyEvidenceSummary": {"evidenceRefs": ["ev.dep"], "nodeCount": 2},
            "raw_sp_definition": "CREATE PROCEDURE must not appear",
            "row_data": [{"secret": "must not appear"}],
        },
        expected_inventory=[
            {
                "artifactType": "DTO_DRAFT",
                "path": "dto/SyntheticSearchCriteria.java",
                "role": "QUERY_DTO",
                "className": "SyntheticSearchCriteria",
                "operationIds": ["readItem"],
                "evidenceRefs": ["ev.select"],
            },
            {
                "artifactType": "DTO_DRAFT",
                "path": "dto/SyntheticUpdateCommand.java",
                "role": "COMMAND_DTO",
                "className": "SyntheticUpdateCommand",
                "operationIds": ["writeItem"],
                "evidenceRefs": ["ev.update"],
                "reviewMarkers": ["TRANSACTION_BOUNDARY_REVIEW_REQUIRED"],
            },
            {
                "artifactType": "SERVICE_DRAFT",
                "path": "service/SyntheticService.java",
                "role": "SERVICE",
                "className": "SyntheticService",
                "operationIds": ["readItem", "writeItem"],
                "references": ["SyntheticSearchCriteria", "SyntheticUpdateCommand"],
                "evidenceRefs": ["ev.select", "ev.update"],
            },
            {
                "artifactType": "MAPPER_INTERFACE",
                "path": "mapper/SyntheticMapper.java",
                "role": "MAPPER_INTERFACE",
                "className": "SyntheticMapper",
                "operationIds": ["readItem", "writeItem"],
                "references": ["SyntheticSearchCriteria", "SyntheticUpdateCommand"],
                "evidenceRefs": ["ev.select", "ev.update"],
            },
            {
                "artifactType": "MAPPER_XML",
                "path": "mapper/SyntheticMapper.xml",
                "role": "MAPPER_XML",
                "className": "SyntheticMapperSQL",
                "operationIds": ["readItem", "writeItem"],
                "references": ["SyntheticSearchCriteria", "SyntheticUpdateCommand"],
                "evidenceRefs": ["ev.select", "ev.update"],
            },
        ],
        quality_gates={
            "requiredServiceMethods": ["readItem", "writeItem"],
            "requiredMapperMethods": ["readItem", "writeItem"],
            "requiredReviewMarkers": ["TRANSACTION_BOUNDARY_REVIEW_REQUIRED"],
        },
        allowed_evidence_refs=["ev.select", "ev.update", "ev.dep"],
    )
    payload = json.loads(prompt.user_prompt)
    serialized = json.dumps(payload, ensure_ascii=False)

    assert prompt.prompt_version == AI_JAVA_MYBATIS_DRAFT_PACK_PROMPT_VERSION
    assert payload["draftPackEvidenceBundle"]["version"] == "DraftPackEvidenceBundle.v0.1"
    assert payload["operationCoverageMatrix"]
    assert payload["dtoResponsibilityMatrix"]
    assert payload["reviewMarkerContract"]["requiredMarkers"] == [
        "TRANSACTION_BOUNDARY_REVIEW_REQUIRED"
    ]
    assert payload["mapperCoverageContract"]["requiredMapperMethods"] == [
        "readItem",
        "writeItem",
    ]
    assert payload["filePolicy"]["benchmarkNamesAreNotAnswerKeys"] is True
    assert "CREATE PROCEDURE" not in serialized
    assert "row_data" not in serialized
    assert "must not appear" not in serialized


def test_p47_ai_draft_pack_model_profile_is_internal_high_quality(
    monkeypatch: Any,
) -> None:
    monkeypatch.delenv("LLM_REMOTE_PROVIDER", raising=False)
    monkeypatch.setenv("OPENAI_MODEL_ANALYSIS", "gpt-5.5")
    monkeypatch.delenv("OPENAI_MODEL_AI_DRAFT_PACK", raising=False)

    profile = model_profile_from_env("openai_ai_draft_pack")

    assert profile.profile_id == "openai_ai_draft_pack"
    assert profile.model == "gpt-5.5"
    assert profile.registry_ref == "model:openai_ai_draft_pack@gpt-5.5@0.1.0"


def test_p47_live_probe_treats_manage_bond_names_as_benchmark_metrics() -> None:
    source = PROBE.read_text(encoding="utf-8")

    assert "quality_signal_only_not_runtime_answer_key" in source
    assert "missingDtoSignals" in source
    assert "benchmark_missing" in source
    assert "if benchmark_missing" not in source


def test_p47_skill_assets_are_actual_adoption_and_generic_quality_first() -> None:
    skill_text = "\n".join(
        (SKILLS / skill / "SKILL.md").read_text(encoding="utf-8")
        for skill in (
            "framework-adapter-pilot",
            "ai-draft-pack-authoring",
            "java-mybatis-draft-validator",
            "sp-business-logic-migration-eval",
            "quality-gate-review",
            "docs-sync",
        )
    )

    assert "P44" in skill_text
    assert "actual" in skill_text.lower() or "adopted" in skill_text.lower()
    assert "benchmark" in skill_text
    assert "runtime answer key" in skill_text
    assert "generic" in skill_text.lower()
    assert "production_ready: true" not in skill_text


def test_p47_env_template_declares_ai_draft_pack_model_override() -> None:
    env_text = ENV_EXAMPLE.read_text(encoding="utf-8")

    assert "OPENAI_MODEL_AI_DRAFT_PACK=gpt-5.5" in env_text
    assert "OPENAI_REASONING_EFFORT_AI_DRAFT_PACK=high" in env_text


def test_p47_docs_record_live_risk_closure_without_readiness_claims() -> None:
    docs_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            POLICY,
            TOOLS,
            EVAL_SPEC,
        )
    )

    assert "P42_LIVE_REPLAY_MODE=sanitized_fixture" in docs_text
    assert "P42_LIVE_REPLAY_MODE=live_ppm" in docs_text
    assert "https://api.openai.com/v1" in docs_text
    assert "approved P-GPT-compatible" in docs_text
    assert "Generated Java/MyBatis artifacts remain draft-only" in docs_text
    assert "automatic conversion approval" in docs_text
