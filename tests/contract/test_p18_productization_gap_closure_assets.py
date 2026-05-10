from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import yaml
from ai_agent_domain import CanonicalAnalysisModel

ROOT = Path(__file__).resolve().parents[2]
PROMPTS = ROOT / "ops" / "codex-parallel" / "prompts"
MANIFEST = ROOT / "ops" / "codex-parallel" / "REQUEST_MANIFEST.yaml"
P18_FIXTURE = ROOT / "fixtures" / "eval" / "productization_gap_closure_p18_v1.yaml"
CANONICAL_CANDIDATE = ROOT / "fixtures" / "eval" / "canonical_analysis_candidate.json"
P18_PROMPTS = {
    "P18A": "18a_canonical_analysis_model_closure.md",
    "P18B": "18b_web_http_auth_rbac_evidence.md",
}

REQUIRED_SECTIONS = (
    "## 목표",
    "## 읽어야 할 기준 파일",
    "## 허용 수정 경로",
    "## 금지 경로",
    "## 구현 범위",
    "## 검증 명령",
    "## Blocker 보고 기준",
)


def test_p18_prompts_exist_and_preserve_productization_safety_contract() -> None:
    for track_id, filename in P18_PROMPTS.items():
        text = (PROMPTS / filename).read_text(encoding="utf-8")
        assert text.startswith(f"# {track_id}"), filename
        for section in REQUIRED_SECTIONS:
            assert section in text, f"{filename} missing {section}"
        assert "PPM" in text
        assert "PLF" in text
        assert "PFL" not in text
        assert "row data" in text
        assert "procedure execution" in text
        assert "blocker" in text.lower()
        assert "production-ready" in text


def test_p18_manifest_declares_parallel_post_p17_gap_closure_wave() -> None:
    manifest = _yaml(MANIFEST)
    tracks = _tracks(manifest)

    for track_id, filename in P18_PROMPTS.items():
        assert track_id in tracks
        assert tracks[track_id]["prompt"] == f"prompts/{filename}"
        assert tracks[track_id]["worktree"].startswith("../wt/p18")
        assert tracks[track_id]["depends_on"] == ["P17D"]
        assert tracks[track_id]["target_paths"]
        assert tracks[track_id]["readonly_paths"]
        assert tracks[track_id]["verify"]

    assert "packages/domain/" in tracks["P18A"]["target_paths"]
    assert "packages/analysis/" in tracks["P18A"]["target_paths"]
    assert "apps/web/" in tracks["P18B"]["target_paths"]
    assert "apps/api/" in tracks["P18B"]["target_paths"]
    assert "fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml" in tracks[
        "P18A"
    ]["readonly_paths"]
    assert "fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml" in tracks[
        "P18B"
    ]["readonly_paths"]

    order = manifest["merge_order"]
    assert order.index("P17D") < order.index("P18A")
    assert order.index("P17D") < order.index("P18B")


def test_p18_fixture_records_no_go_productization_until_web_and_auth_close() -> None:
    fixture = _yaml(P18_FIXTURE)

    assert fixture["version"] == "productization_gap_closure_p18_v1"
    assert fixture["source_p17_fixture"] == (
        "fixtures/eval/live_pilot_blocker_closure_p17_v1.yaml"
    )
    assert fixture["current_state"]["p17_scoped_live_pilot_decision"] == "CONDITIONAL_GO"
    assert fixture["current_state"]["p18_productization_decision"] == "NO_GO"
    assert fixture["current_state"]["production_ready"] is False

    assert fixture["p18a_canonical_analysis_model"]["current_status"] == "CONTRACT_CLOSED"
    assert fixture["p18a_canonical_analysis_model"]["current_blockers"] == []
    assert fixture["p18b_web_http_auth_rbac"]["auth_rbac"]["blocker"] == (
        "AUTH_RBAC_PRODUCTION_SOURCE_UNRESOLVED"
    )
    assert fixture["p18_final_gate"]["current_productization_decision"] == "NO_GO"
    assert "production_ready_claim_allowed" in fixture["policy_boundaries"]


def test_p18a_canonical_candidate_validates_versioned_domain_contract() -> None:
    candidate = json.loads(CANONICAL_CANDIDATE.read_text(encoding="utf-8"))
    model = CanonicalAnalysisModel.model_validate(candidate["analysis_local"])

    assert candidate["status"] == "CONTRACT_CLOSED"
    assert candidate["analysis_status"] == "REVIEW_REQUIRED"
    assert candidate["blockers"] == []
    assert model.schema_version == "CanonicalAnalysisModel.v1"
    assert model.snapshot_id == "mcp-fixture-snapshot-0001"
    assert {ref.registry_type for ref in model.registry_version_refs} == {
        "PROMPT",
        "TEMPLATE",
        "POLICY",
    }
    assert model.evidence_refs
    assert model.modernization_points == []
    assert model.dependencies.table_references[1].status == "REVIEW_REQUIRED"
    serialized = CANONICAL_CANDIDATE.read_text(encoding="utf-8").lower()
    assert "row_data" not in serialized
    assert "sample_rows" not in serialized
    assert "procedure_execution" not in serialized
    assert "raw_definition_text" not in serialized


def test_p18_docs_and_readiness_assets_reference_gap_closure_without_overclaim() -> None:
    readme = (ROOT / "ops" / "codex-parallel" / "README.md").read_text(encoding="utf-8")
    runbook = (ROOT / "ops" / "codex-parallel" / "PARALLEL_RUNBOOK.md").read_text(
        encoding="utf-8"
    )
    plan = (ROOT / "ops" / "codex-parallel" / "PARALLEL_REQUEST_PLAN.md").read_text(
        encoding="utf-8"
    )
    eval_readme = (ROOT / "fixtures" / "eval" / "README.md").read_text(encoding="utf-8")
    gap = (ROOT / "docs" / "productization-architecture-gap-analysis.md").read_text(
        encoding="utf-8"
    )
    combined = "\n".join([readme, runbook, plan, eval_readme, gap])

    assert "P18 Productization Gap Closure" in combined
    assert "productization_gap_closure_p18_v1.yaml" in combined
    assert "AUTH_RBAC_PRODUCTION_SOURCE_UNRESOLVED" in combined
    assert "CanonicalAnalysisModel" in combined
    assert "CONDITIONAL_GO" in combined
    assert "production-ready: true" not in combined
    assert "SELECT * FROM PPM" not in combined
    assert "COUNT(*)" not in combined
    assert "PFL" not in combined


def _yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _tracks(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    tracks: dict[str, dict[str, Any]] = {}
    for wave in manifest["waves"]:
        for track in wave["tracks"]:
            tracks[track["id"]] = track
    return tracks
