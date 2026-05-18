from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
PROJECT = ROOT / "PROJECT.md"
CONTRACT = ROOT / "spec" / "eval" / "p43_framework_adoption_contract.yaml"
FIXTURE = ROOT / "fixtures" / "eval" / "framework_adoption_p43_manage_bond_v1.yaml"
TASK = ROOT / "tasks" / "0043-framework-adoption-readiness.md"
MANIFEST = ROOT / "ops" / "codex-parallel" / "REQUEST_MANIFEST.yaml"
PROMPT_DIR = ROOT / "ops" / "codex-parallel" / "prompts"
POLICY = ROOT / "POLICY.md"
ARCHITECTURE = ROOT / "ARCHITECTURE.md"
TOOLS = ROOT / "TOOLS.md"
EVAL_SPEC = ROOT / "EVAL_SPEC.md"
DECISION_REPORT = ROOT / "docs" / "framework-adoption-decision-p43.md"

P43_PROMPTS = {
    "P43A": "43a_framework_adoption_contract_assets.md",
    "P43B": "43b_framework_adapter_contract.md",
    "P43C": "43c_ai_draft_pack_framework_spike.md",
    "P43D": "43d_tool_trace_policy_gate.md",
    "P43E": "43e_manage_bond_framework_replay_gate.md",
    "P43F": "43f_docs_decision_gate.md",
}

REQUIRED_PROMPT_SECTIONS = (
    "## Role",
    "## Task",
    "## Scope",
    "## Constraints",
    "## Acceptance",
)


def _yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_p43_contract_declares_adapter_first_readiness_scope() -> None:
    contract = _yaml(CONTRACT)

    assert contract["contract_id"] == "p43_framework_adoption@0.1.0"
    assert contract["phase"] == "P43"
    assert contract["production_ready"] is False
    assert contract["scope"]["mode"] == "sequential_only"
    assert contract["scope"]["required_order"] == [
        "P43A",
        "P43B",
        "P43C",
        "P43D",
        "P43E",
        "P43F",
    ]
    assert contract["scope"]["implementation_posture"] == "adapter_first_evaluation"
    assert contract["scope"]["dependency_installation_allowed_in_p43a"] is False
    assert contract["scope"]["production_runtime_switch_allowed_in_p43a"] is False


def test_p43_contract_records_candidates_and_policy_boundaries() -> None:
    contract = _yaml(CONTRACT)
    candidates = contract["candidate_frameworks"]

    assert set(candidates) == {
        "baseline_internal_responses_gateway",
        "openai_agents_sdk",
        "langgraph",
    }
    assert candidates["baseline_internal_responses_gateway"]["current_stack"] is True
    assert "raw prompts" in " ".join(
        candidates["openai_agents_sdk"]["adoption_risks"]
    )
    assert "workflow" in candidates["langgraph"]["adoption_risks"][0]

    forbidden = contract["forbidden_behavior"]
    assert all(forbidden.values())
    assert "P43_FRAMEWORK_OVERFITS_MANAGE_BOND" in contract["blockers"]


def test_p43_contract_defines_framework_adapter_contract() -> None:
    adapter = _yaml(CONTRACT)["framework_adapter_contract"]

    assert adapter["name"] == "AiGenerationFrameworkAdapter.v0.1"
    assert adapter["required_methods"] == [
        "plan_file_inventory",
        "draft_file_content",
        "repair_draft_pack",
        "summarize_trace",
    ]
    assert "deterministic_inventory_contract" in adapter["required_inputs"]
    assert "sanitized_trace_hashes" in adapter["required_outputs"]
    assert "raw_prompt" in adapter["forbidden_outputs"]
    assert "raw_provider_response" in adapter["forbidden_outputs"]


def test_p43f_contract_records_pilot_decision_gate() -> None:
    contract = _yaml(CONTRACT)
    decision = contract["decision_gate"]

    assert decision["phase"] == "P43F"
    assert decision["decision"] == "pilot"
    assert decision["production_ready"] is False
    assert decision["decision_report"] == "docs/framework-adoption-decision-p43.md"
    assert "BaselineResponsesFrameworkAdapter" in decision["rollback_path"]
    assert decision["quality_comparison"]["outcome"] == "preserve_baseline_quality"
    assert decision["quality_comparison"]["manage_bond_expected_dto_artifact_rows"] == 11
    assert decision["quality_comparison"]["synthetic_complex_sp_hardcoding_guard"] == "passed"
    assert (
        decision["quality_comparison"]["synthetic_two_dto_collapse_guard"]
        == "failed_as_expected"
    )
    assert decision["policy_findings"]["new_framework_dependencies"] == 0
    assert decision["policy_findings"]["row_data_or_procedure_execution"] == 0
    assert "P43_FRAMEWORK_DEPENDENCY_NOT_APPROVED" in decision["residual_review_required"]
    assert "WEAK_OR_UNSUPPORTED_FRAMEWORK_FACTS_REVIEW_REQUIRED" in (
        decision["residual_review_required"]
    )


def test_p43d_contract_defines_tool_and_trace_policy_gates() -> None:
    contract = _yaml(CONTRACT)
    tool_policy = contract["framework_tool_policy"]
    trace_policy = contract["framework_trace_policy"]

    assert tool_policy["blocker"] == "P43_FRAMEWORK_TOOL_CONTEXT_BLOCKED"
    assert "target_ref_hash" in tool_policy["allowed_context"]
    assert "deterministic_inventory_contract" in tool_policy["allowed_context"]
    assert "failed_java_or_xml_payload" in tool_policy["forbidden_context"]
    assert trace_policy["blocker"] == "P43_FRAMEWORK_RAW_TRACE_BLOCKED"
    assert "raw_framework_events" in trace_policy["transient_only"]
    assert "numeric_policy_safe_metrics" in trace_policy["stored_summary_allowed_fields"]
    assert "tool_io" in trace_policy["stored_summary_forbidden_fields"]
    assert "P43_FRAMEWORK_TOOL_CONTEXT_BLOCKED" in contract["blockers"]


def test_p43d_docs_record_framework_tracing_and_persistence_blockers() -> None:
    docs = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (POLICY, ARCHITECTURE, TOOLS, EVAL_SPEC)
    )
    contract = _yaml(CONTRACT)

    assert "P43_FRAMEWORK_TOOL_CONTEXT_BLOCKED" in docs
    assert "P43_FRAMEWORK_RAW_TRACE_BLOCKED" in docs
    assert "hash/count/code" in docs or "hash/count/code" in str(contract)
    assert "OpenAI Agents SDK tracing" in docs
    assert "LangGraph persistence" in docs
    assert (
        contract["candidate_frameworks"]["openai_agents_sdk"]["policy_docs"]["tracing"]
        == "https://openai.github.io/openai-agents-python/tracing/"
    )
    assert (
        contract["candidate_frameworks"]["openai_agents_sdk"]["policy_docs"]["configuration"]
        == "https://openai.github.io/openai-agents-python/config/"
    )
    assert (
        contract["candidate_frameworks"]["langgraph"]["policy_docs"]["persistence"]
        == "https://docs.langchain.com/oss/python/langgraph/persistence"
    )


def test_p43_fixture_keeps_manage_bond_as_benchmark_only() -> None:
    fixture = _yaml(FIXTURE)
    replay = fixture["benchmark_replay"]
    decision = fixture["expected_decision_report"]

    assert fixture["fixture_suite_id"] == "framework_adoption_p43_manage_bond_v1"
    assert fixture["contract_ref"] == "p43_framework_adoption@0.1.0"
    assert fixture["production_ready"] is False
    assert fixture["source_reference"]["target_ref"] == "PPM.dbo.PCO_GU_ManageBond_PRC"
    assert fixture["source_reference"]["role"] == "complex_sp_benchmark_only"
    assert fixture["source_reference"]["copy_reference_content_to_repo"] is False
    assert fixture["source_reference"]["copy_raw_sp_text_to_repo"] is False
    assert fixture["expected_general_contract"]["reject_two_dto_collapse_for_complex_sp"] is True
    assert fixture["expected_general_contract"]["reject_raw_trace_or_prompt_storage"] is True
    assert replay["phase"] == "P43E"
    assert replay["default_mode"] == "fake_adapters_and_sanitized_fixtures_only"
    assert replay["reconstruct_artifacts_as"] == "AiJavaMyBatisDraftPack.v0.1"
    assert replay["comparison_contract"]["same_generic_inventory_contract_required"] is True
    assert replay["comparison_contract"]["candidate_quality_must_preserve_or_improve_baseline"]
    assert {
        case["id"] for case in replay["replay_cases"]
    } == {
        "manage_bond_baseline_vs_candidate",
        "synthetic_complex_sp_collapse_guard",
    }
    synthetic = next(
        case
        for case in replay["replay_cases"]
        if case["id"] == "synthetic_complex_sp_collapse_guard"
    )
    assert synthetic["role"] == "generic_hardcoding_guard"
    assert any("ManageBond DTO names" in signal for signal in synthetic["expected_signals"])
    assert decision["p43f_decision"] == "pilot"
    assert decision["decision_report_path"] == "docs/framework-adoption-decision-p43.md"
    assert decision["quality_comparison"]["baseline_vs_candidate_result"] == (
        "preserve_baseline_quality"
    )
    assert decision["quality_comparison"]["manage_bond_expected_dto_artifact_rows"] == 11
    assert "BaselineResponsesFrameworkAdapter" in decision["rollback_path"]
    assert "P43_FRAMEWORK_LIVE_GATE_NOT_CONFIGURED" in decision["residual_review_required"]


def test_p43f_decision_report_documents_evidence_and_boundaries() -> None:
    report = DECISION_REPORT.read_text(encoding="utf-8")
    docs = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (
            PROJECT,
            ARCHITECTURE,
            POLICY,
            TOOLS,
            EVAL_SPEC,
            ROOT / "packages" / "agent-runtime" / "README.md",
            ROOT / "packages" / "generation" / "README.md",
            ROOT / "fixtures" / "eval" / "README.md",
            ROOT / "tests" / "eval" / "README.md",
            ROOT / "docs" / "integration-eval-status.md",
            ROOT / "docs" / "test-gate-history.md",
        )
    )

    assert "P43 decision: `pilot`" in report
    assert "`production_ready` remains false" in report
    assert "BaselineResponsesFrameworkAdapter" in report
    assert "Quality comparison result" in report
    assert "Policy findings" in report
    assert "Residual `REVIEW_REQUIRED` items" in report
    assert "tests/eval/test_p43_framework_adapter_replay.py" in report
    assert "git -c safe.directory=D:/wt/p35 diff --check" in report
    assert "P43F records the framework adoption decision as `pilot`" in docs
    assert "P43F records the decision as `pilot`" in docs or "P43F records a `pilot`" in docs
    assert PROJECT.exists()


def test_p43_prompt_pack_exists_and_preserves_policy() -> None:
    for track_id, prompt_name in P43_PROMPTS.items():
        text = (PROMPT_DIR / prompt_name).read_text(encoding="utf-8")
        for section in REQUIRED_PROMPT_SECTIONS:
            assert section in text
        assert track_id in text
        assert "production_ready: false" in text
        assert "row data" in text
        assert "procedure execution" in text
        assert "REVIEW_REQUIRED" in text or track_id in {"P43A", "P43B"}


def test_p43_task_and_manifest_wire_sequential_tracks() -> None:
    task = TASK.read_text(encoding="utf-8")
    manifest = _yaml(MANIFEST)

    assert "Task 0043: Framework Adoption Readiness" in task
    assert "adapter" in task
    assert "PCO_GU_ManageBond_PRC" in task
    assert "OpenAI Agents SDK" in task
    assert "LangGraph" in task

    assert "spec/eval/p43_framework_adoption_contract.yaml" in manifest["basis"]
    assert "fixtures/eval/framework_adoption_p43_manage_bond_v1.yaml" in manifest["basis"]

    tracks = {
        track["id"]: track
        for wave in manifest["waves"]
        for track in wave["tracks"]
        if track["id"].startswith("P43")
    }
    assert list(tracks) == ["P43A", "P43B", "P43C", "P43D", "P43E", "P43F"]
    assert [item for item in manifest["merge_order"] if item.startswith("P43")] == [
        "P43A",
        "P43B",
        "P43C",
        "P43D",
        "P43E",
        "P43F",
    ]
    assert tracks["P43A"]["depends_on"] == ["P42F"]
    assert tracks["P43B"]["depends_on"] == ["P43A"]
    assert tracks["P43F"]["depends_on"] == ["P43E"]
    for track_id, prompt_name in P43_PROMPTS.items():
        assert tracks[track_id]["prompt"] == f"prompts/{prompt_name}"


def test_p43_assets_do_not_copy_raw_stored_procedure_or_prompt_text() -> None:
    asset_paths = [
        CONTRACT,
        FIXTURE,
        DECISION_REPORT,
        TASK,
        *(PROMPT_DIR / prompt for prompt in P43_PROMPTS.values()),
    ]
    forbidden_markers = [
        "CREATE OR ALTER PROCEDURE",
        "CREATE PROCEDURE",
        "CREATE PROC",
        "ALTER PROCEDURE",
        "BEGIN TRANSACTION raw",
        "provider_response_raw",
        "raw_provider_payload",
        "production_ready: true",
    ]

    for path in asset_paths:
        text = path.read_text(encoding="utf-8")
        for marker in forbidden_markers:
            assert marker not in text
