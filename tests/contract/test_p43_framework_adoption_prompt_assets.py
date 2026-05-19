from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
P43_CONTRACT = ROOT / "spec" / "eval" / "p43_framework_adoption_contract.yaml"
P43_FIXTURE = ROOT / "fixtures" / "eval" / "framework_adoption_p43_manage_bond_v1.yaml"
P43_DECISION = ROOT / "docs" / "framework-adoption-decision-p43.md"
P49_CONTRACT = (
    ROOT / "spec" / "eval" / "p49_framework_runtime_consolidation_cleanup.yaml"
)


def _yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_p43_assets_are_historical_evidence_superseded_by_p49() -> None:
    p43 = _yaml(P43_CONTRACT)
    p49 = _yaml(P49_CONTRACT)

    assert p43["contract_id"] == "p43_framework_adoption@0.1.0"
    assert p43["production_ready"] is False
    assert p43["superseded_by"] == "p44_framework_runtime_adoption@0.1.0"
    assert p49["historical_evidence"]["p43_framework_adoption"]["status"] == (
        "superseded_historical_only"
    )
    assert (
        p49["historical_evidence"]["p43_framework_adoption"]["active_runtime_gate"]
        is False
    )
    assert "P43" in p49["historical_evidence"]["p43_framework_adoption"]["retained_assets"]


def test_p43_historical_assets_keep_policy_safe_payloads_only() -> None:
    asset_paths = [P43_CONTRACT, P43_FIXTURE, P43_DECISION]
    forbidden_markers = (
        "CREATE OR ALTER PROCEDURE",
        "CREATE PROCEDURE",
        "CREATE PROC",
        "ALTER PROCEDURE",
        "provider_response_raw",
        "raw_provider_payload",
        "production_ready: true",
        "row_data_payload",
    )

    for path in asset_paths:
        text = path.read_text(encoding="utf-8")
        for marker in forbidden_markers:
            assert marker not in text


def test_p43_manage_bond_remains_benchmark_only_not_active_gate() -> None:
    fixture = _yaml(P43_FIXTURE)
    p49 = _yaml(P49_CONTRACT)

    assert fixture["source_reference"]["role"] == "complex_sp_benchmark_only"
    assert fixture["source_reference"]["copy_raw_sp_text_to_repo"] is False
    assert (
        p49["historical_evidence"]["p43_framework_adoption"][
            "manage_bond_role"
        ]
        == "benchmark_fixture_only"
    )
