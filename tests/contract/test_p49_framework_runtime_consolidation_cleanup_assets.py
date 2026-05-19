from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

import ai_agent_runtime
import tests.helpers.framework_adapters as test_framework_adapters

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "spec" / "eval" / "p49_framework_runtime_consolidation_cleanup.yaml"
P43_CONTRACT = ROOT / "spec" / "eval" / "p43_framework_adoption_contract.yaml"
SUITES = ROOT / "tests" / "suites.yaml"
FRAMEWORK_ADAPTER = (
    ROOT / "packages" / "agent-runtime" / "src" / "ai_agent_runtime" / "framework_adapter.py"
)
P43_REPLAY = ROOT / "tests" / "eval" / "test_p43_framework_adapter_replay.py"
DOC_PATHS = (
    ROOT / "PROJECT.md",
    ROOT / "ARCHITECTURE.md",
    ROOT / "POLICY.md",
    ROOT / "EVAL_SPEC.md",
    ROOT / "TOOLS.md",
    ROOT / "packages" / "agent-runtime" / "README.md",
)
LEGACY_ADAPTERS = (
    "BaselineResponsesFrameworkAdapter",
    "FakeAiGenerationFrameworkAdapter",
)


def _yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _flatten_suite(
    target: str,
    suites: dict[str, list[str]],
    stack: tuple[str, ...] = (),
) -> list[str]:
    if not target.startswith("@"):
        return [target]
    name = target[1:]
    assert name not in stack
    result: list[str] = []
    for child in suites[name]:
        result.extend(_flatten_suite(child, suites, (*stack, name)))
    return result


def _p49_section(text: str) -> str:
    for heading in ("## P49", "- P49 makes", "P49 consolidates"):
        if heading in text:
            start = text.index(heading)
            break
    else:
        start = text.index("P49")
    remainder = text[start:]
    next_heading = remainder.find("\n## ", len("P49"))
    if next_heading == -1:
        return remainder
    return remainder[:next_heading]


def test_p49_contract_declares_active_runtime_and_historical_boundary() -> None:
    contract = _yaml(CONTRACT)

    assert contract["contract_id"] == (
        "p49_framework_runtime_consolidation_cleanup@0.1.0"
    )
    assert contract["production_ready"] is False
    assert contract["active_runtime_matrix"]["structured_llm"]["contract"] == (
        "p48_unified_framework_runtime@0.1.0"
    )
    assert contract["active_runtime_matrix"]["structured_llm"]["adapter"] == (
        "OpenAIAgentsStructuredAdapter"
    )
    assert contract["active_runtime_matrix"]["ai_draft_pack"]["adapter"] == (
        "OpenAIAgentsFrameworkAdapter"
    )
    assert contract["active_runtime_matrix"]["ai_draft_pack"]["orchestrator"] == (
        "LangGraphAiDraftPackOrchestrator"
    )
    assert contract["historical_evidence"]["p43_framework_adoption"]["status"] == (
        "superseded_historical_only"
    )
    assert (
        contract["historical_evidence"]["p43_framework_adoption"]["active_runtime_gate"]
        is False
    )


def test_p49_retains_pgpt_and_emergency_responses_httpx_rollback() -> None:
    rollback = _yaml(CONTRACT)["retained_rollback"]

    assert rollback["responses_httpx"]["retained"] is True
    assert rollback["responses_httpx"]["active_openai_default"] is False
    assert rollback["responses_httpx"]["pgpt_structured_default"] is False
    assert rollback["responses_httpx"]["pgpt_generation_default"] is True
    assert rollback["responses_httpx"]["explicit_emergency_rollback"] is True
    assert rollback["openai_model_gateway"]["retained"] is True
    assert "responses_httpx" in _yaml(CONTRACT)["not_deleted"]


def test_p49_removes_legacy_adapter_symbols_from_production_exports() -> None:
    exported = set(ai_agent_runtime.__all__)
    source = FRAMEWORK_ADAPTER.read_text(encoding="utf-8")

    for name in LEGACY_ADAPTERS:
        assert name not in exported
        assert not hasattr(ai_agent_runtime, name)
        assert f"class {name}" not in source
        assert hasattr(test_framework_adapters, name)


def test_p49_production_code_has_no_legacy_adapter_imports() -> None:
    for root_name in ("packages", "apps"):
        for path in (ROOT / root_name).rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for name in LEGACY_ADAPTERS:
                assert name not in text, f"{name} remains in {path.relative_to(ROOT)}"


def test_p49_replaces_broad_p43_replay_gate_with_historical_asset_check() -> None:
    contract = _yaml(CONTRACT)
    p43 = _yaml(P43_CONTRACT)

    assert P43_REPLAY.exists() is False
    assert p43["superseded_by"] == "p44_framework_runtime_adoption@0.1.0"
    assert contract["deletion_approved"]["broad_historical_gates"] == [
        "tests/eval/test_p43_framework_adapter_replay.py"
    ]
    assert contract["historical_evidence"]["p43_framework_adoption"][
        "replacement_check"
    ] == "tests/contract/test_p43_framework_adoption_prompt_assets.py"


def test_p49_suite_aliases_focus_framework_runtime_without_p43_replay() -> None:
    suites = _yaml(SUITES)["suites"]

    assert "framework-contracts" in suites
    assert "framework-runtime" in suites
    runtime_targets = [
        target
        for suite_target in suites["framework-runtime"]
        for target in _flatten_suite(suite_target, suites)
    ]

    assert "tests/contract/test_p49_framework_runtime_consolidation_cleanup_assets.py" in (
        runtime_targets
    )
    assert "tests/contract/test_p48_unified_framework_runtime_assets.py" in runtime_targets
    assert "tests/eval/test_p44_framework_runtime_replay.py" in runtime_targets
    assert "tests/eval/test_p43_framework_adapter_replay.py" not in runtime_targets


def test_p49_public_surface_and_trace_policy_remain_locked() -> None:
    contract = _yaml(CONTRACT)

    assert all(value is False for value in contract["public_surface"].values())
    assert all(value is True for value in contract["forbidden_behavior"].values())
    assert contract["trace_policy"]["store_raw_prompt"] is False
    assert contract["trace_policy"]["store_raw_provider_response"] is False
    assert contract["trace_policy"]["store_raw_sp_definition"] is False
    assert contract["trace_policy"]["store_row_data"] is False


def test_p49_docs_are_synchronized_without_production_readiness_claim() -> None:
    for path in DOC_PATHS:
        text = path.read_text(encoding="utf-8")
        assert "P49" in text, f"P49 cleanup index missing from {path.relative_to(ROOT)}"
        p49_section = _p49_section(text)
        assert "production readiness claim" in p49_section or "production readiness" in (
            p49_section
        )
        assert "production_ready: true" not in p49_section
        assert "productionReady: true" not in p49_section
