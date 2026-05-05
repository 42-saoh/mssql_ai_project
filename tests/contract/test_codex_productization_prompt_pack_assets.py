from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
PROMPTS = ROOT / "ops" / "codex-parallel" / "prompts"
MANIFEST = ROOT / "ops" / "codex-parallel" / "REQUEST_MANIFEST.yaml"
GAP_ANALYSIS = ROOT / "docs" / "productization-architecture-gap-analysis.md"
RELEASE_BACKLOG = ROOT / "ops" / "codex-parallel" / "PRODUCTIZATION_RELEASE_BACKLOG.md"
READINESS_FIXTURE = ROOT / "fixtures" / "eval" / "productization_readiness_v1.yaml"
PILOT_MANIFEST = ROOT / "fixtures" / "pilot" / "ppm_object_selection_v1" / "selected_objects.yaml"

PRODUCTIZATION_PROMPTS = {
    "P08A": "08a_ppm_pilot_object_discovery_selection.md",
    "P08": "08_product_architecture_release_backlog.md",
    "P09": "09_api_workflow_productization.md",
    "P10": "10_mssql_mcp_productization.md",
    "P11": "11_sp_analysis_evidence_engine.md",
    "P12": "12_java_mybatis_generation_factory.md",
    "P13": "13_validation_approval_audit.md",
    "P14": "14_web_product_ui.md",
    "P15": "15_eval_observability_security_ops.md",
    "P16": "16_pilot_release_readiness.md",
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


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _manifest() -> dict:
    return yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))


def _tracks() -> dict[str, dict]:
    tracks: dict[str, dict] = {}
    for wave in _manifest()["waves"]:
        for track in wave["tracks"]:
            tracks[track["id"]] = track
    return tracks


def test_productization_prompts_exist_with_worker_contract_sections() -> None:
    for track_id, filename in PRODUCTIZATION_PROMPTS.items():
        text = _read(PROMPTS / filename)
        assert text.startswith(f"# {track_id}"), filename
        for section in REQUIRED_SECTIONS:
            assert section in text, f"{filename} missing {section}"
        assert "공유 contract/policy/common 파일 수정이 필요하면" in text
        assert "coordinator" in text
        assert "blocker" in text.lower()
        assert "PPM" in text
        assert "PLF" in text
        assert "PFL" not in text


def test_productization_worker_prompts_reference_p08_gap_backlog_and_readiness_fixture() -> None:
    required_refs = (
        "docs/productization-architecture-gap-analysis.md",
        "ops/codex-parallel/PRODUCTIZATION_RELEASE_BACKLOG.md",
        "fixtures/eval/productization_readiness_v1.yaml",
    )

    for track_id in ("P09", "P10", "P11", "P12", "P13", "P14", "P15", "P16"):
        text = _read(PROMPTS / PRODUCTIZATION_PROMPTS[track_id])
        for ref in required_refs:
            assert ref in text, f"{track_id} prompt missing {ref}"


def test_manifest_declares_productization_tracks_and_merge_order() -> None:
    manifest = _manifest()
    assert manifest["plan_id"] == "codex-parallel-local-v3-productization"
    assert "fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml" in manifest["basis"]
    assert "config/mssql/local_docker_profiles.yaml" in manifest["basis"]

    tracks = _tracks()
    for track_id, filename in PRODUCTIZATION_PROMPTS.items():
        assert track_id in tracks
        assert tracks[track_id]["prompt"] == f"prompts/{filename}"
        assert tracks[track_id]["worktree"].startswith("../wt/")
        assert tracks[track_id]["target_paths"] is not None
        assert tracks[track_id]["verify"] is not None

    merge_order = manifest["merge_order"]
    assert merge_order.index("P08A") < merge_order.index("P08") < merge_order.index("P16")


def test_productization_tracks_treat_pilot_manifest_as_read_only_after_p08a() -> None:
    tracks = _tracks()
    pilot_manifest = "fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml"
    assert any(path.startswith("fixtures/pilot/ppm_object_selection_v1/") for path in tracks["P08A"]["target_paths"])

    for track_id in ("P08", "P09", "P10", "P11", "P12", "P13", "P14", "P15", "P16"):
        readonly_paths = tracks[track_id].get("readonly_paths", [])
        assert pilot_manifest in readonly_paths, f"{track_id} must not rewrite selected_objects.yaml"


def test_productization_runbook_documents_plf_ppm_roles() -> None:
    runbook = _read(ROOT / "ops" / "codex-parallel" / "PARALLEL_RUNBOOK.md")
    readme = _read(ROOT / "ops" / "codex-parallel" / "README.md")
    plan = _read(ROOT / "ops" / "codex-parallel" / "PARALLEL_REQUEST_PLAN.md")

    for text in (runbook, readme, plan):
        assert "PLF" in text
        assert "PPM" in text
        assert "PLF로 대체하지" in text
        assert "PFL" not in text

    for text in (runbook, readme, plan):
        assert "docs/productization-architecture-gap-analysis.md" in text
        assert "PRODUCTIZATION_RELEASE_BACKLOG.md" in text
        assert "fixtures/eval/productization_readiness_v1.yaml" in text


def test_p08a_can_own_minimum_metadata_discovery_surface_without_running_full_p10() -> None:
    tracks = _tracks()
    p08a = tracks["P08A"]
    target_paths = set(p08a["target_paths"])
    prompt_text = _read(PROMPTS / PRODUCTIZATION_PROMPTS["P08A"])

    assert "최소 metadata discovery surface" in prompt_text
    assert "P10 전체" in prompt_text
    assert "MIN_METADATA_DISCOVERY_SURFACE_INSUFFICIENT" in prompt_text
    assert "spec/mcp/mssql_metadata_tool_catalog.yaml" in target_paths
    assert "services/mssql-mcp/mssql_mcp_app/metadata_discovery.py" in target_paths
    assert "services/mssql-mcp/mssql_mcp_app/repositories.py" in target_paths
    assert any(path.startswith("tests/contract/mcp") for path in target_paths)
    assert any(path.startswith("tests/unit/mcp") for path in target_paths)
    assert "apps/**" in prompt_text
    assert "spec/openapi/**" in prompt_text
    assert "db/schema/**" in prompt_text


def test_p08_gap_analysis_exists_and_does_not_overclaim_production_ready() -> None:
    text = _read(GAP_ANALYSIS)
    assert "# P08 Productization Architecture Gap Analysis" in text
    assert "No current surface is classified as `production-ready`" in text

    for status in ("skeleton", "stub", "fixture-first", "optional-live", "production-ready"):
        assert f"`{status}`" in text

    current_matrix = text.split("## Current State Matrix", 1)[1].split(
        "## Contract Drift Matrix", 1
    )[0]
    assert "| `production-ready` |" not in current_matrix
    assert "DEPENDENCY_METADATA_INCOMPLETE" in text
    assert "PPM" in text
    assert "PLF" in text
    assert "PLF fallback" in text
    assert "PFL" not in text


def test_productization_release_backlog_covers_p09_to_p16_acceptance_and_verification() -> None:
    text = _read(RELEASE_BACKLOG)
    assert "# P08 Productization Release Backlog" in text
    assert "PPM must not fall back to PLF" in text

    for track_id in ("P09", "P10", "P11", "P12", "P13", "P14", "P15", "P16"):
        section = text.split(f"## {track_id} ", 1)[1]
        next_marker = "\n## P"
        if next_marker in section:
            section = section.split(next_marker, 1)[0]
        assert "Acceptance criteria:" in section
        assert "Verification:" in section
        assert "Blockers:" in section
        assert "make test" in section or "make test-web-smoke" in section

    lower_text = text.lower()
    forbidden_terms = ("row-data reads", "procedure execution", "automatic ddl/dml")
    for term in forbidden_terms:
        assert term in lower_text
    assert "PFL" not in text


def test_productization_readiness_fixture_links_pilot_manifest_to_release_gates() -> None:
    readiness = yaml.safe_load(READINESS_FIXTURE.read_text(encoding="utf-8"))
    pilot = yaml.safe_load(PILOT_MANIFEST.read_text(encoding="utf-8"))

    assert readiness["version"] == "productization_readiness_v1"
    assert readiness["source_manifest"] == "fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml"
    assert set(readiness["mode_policy"]) == {"live_metadata", "template_only"}
    assert readiness["mode_policy"]["template_only"]["can_reference_selected_object_identities"] is False
    assert readiness["mode_policy"]["live_metadata"]["can_reference_selected_object_identities"] is True
    assert "DEPENDENCY_METADATA_INCOMPLETE" in readiness["current_manifest_expectations"][
        "active_blockers_to_carry_forward"
    ]
    assert pilot["selection_mode"] in readiness["current_manifest_expectations"][
        "allowed_selection_modes"
    ]

    for track_id in ("P09", "P10", "P11", "P12", "P13", "P14", "P15", "P16"):
        milestone = readiness["milestones"][track_id]
        assert milestone["readiness_gate"]
        assert milestone["verification"]
        assert milestone["blocker_if"]

    combined = READINESS_FIXTURE.read_text(encoding="utf-8")
    forbidden_terms = ("sample_rows", "row_sample", "SELECT * FROM PPM", "COUNT(*)", "PFL")
    for term in forbidden_terms:
        assert term not in combined
