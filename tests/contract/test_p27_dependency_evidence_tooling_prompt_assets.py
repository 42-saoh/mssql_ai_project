from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
PROMPT = ROOT / "ops" / "codex-parallel" / "prompts" / (
    "27_dependency_evidence_tooling_design.md"
)
MANIFEST = ROOT / "ops" / "codex-parallel" / "REQUEST_MANIFEST.yaml"
CONTRACT = ROOT / "spec" / "eval" / "p27_dependency_evidence_tooling_contract.yaml"

P27_MANIFEST_DEFAULT_VERIFY = (
    'make test PYTEST_ARGS="tests/unit/test_mcp_catalog.py '
    "tests/unit/mcp/test_tool_registry.py "
    "tests/contract/mcp/test_tool_invocation_contract.py "
    "tests/contract/test_p27_dependency_evidence_tooling_prompt_assets.py "
    "tests/unit/api/test_metadata_service.py "
    'tests/integration/api/test_api_workflow_routes.py"'
)
P29_CONTRACT_DEFAULT_VERIFY = (
    'make test PYTEST_ARGS="tests/unit/test_mcp_catalog.py '
    "tests/unit/mcp/test_tool_registry.py "
    "tests/contract/mcp/test_tool_invocation_contract.py "
    "tests/contract/test_p27_dependency_evidence_tooling_prompt_assets.py "
    "tests/unit/api/test_metadata_service.py "
    "tests/unit/api/test_metadata_gateway.py "
    "tests/unit/api/test_workflow_service.py "
    "tests/unit/api/test_route_surface.py "
    "tests/unit/web/test_p14_product_ui_static.py "
    "tests/integration/api/test_api_workflow_routes.py "
    "tests/e2e/test_fixture_workflow_happy_path.py "
    'tests/contract/test_openapi_and_env_sample_assets.py"'
)
P27_HARD_LIVE_VERIFY = (
    "P27_HARD_LIVE_GATE=1 MSSQL_ENABLE_LIVE_METADATA=1 make test "
    'PYTEST_ARGS="tests/eval/test_p27_dependency_evidence_hard_live_gate.py"'
)

REQUIRED_PROMPT_MARKERS = (
    "P27",
    "production_ready: false",
    "get_procedure_dependencies",
    "resolutionConfidence",
    "resolutionEvidenceKind",
    "unresolvedReason",
    "resolutionChain",
    "get_dependency_closure",
    "resolve_dependency_reference",
    "active: true",
    "readOnly: true",
    "structured-input-only",
    "fixture_first_hardened_with_explicit_live_gate",
    "P27_HARD_LIVE_GATE",
    "snapshotId",
    "collectedAt",
    "evidenceRefs",
    "REVIEW_REQUIRED",
    "PLF fallback",
    "raw prompt",
    "raw SP definition",
    "raw OpenAI response text",
    "raw provider response text",
    "row data",
    "procedure execution",
    "business DB DDL/DML",
    "free-form SQL",
    "fixture-first",
    "API",
    "Web UI",
    "workflow wiring",
)


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_p27_prompt_exists_and_captures_fixture_first_boundaries() -> None:
    text = PROMPT.read_text(encoding="utf-8")

    for marker in REQUIRED_PROMPT_MARKERS:
        assert marker in text


def test_p27_manifest_declares_prompt_track_and_merge_order() -> None:
    manifest = _load_yaml(MANIFEST)
    tracks = {
        track["id"]: track
        for wave in manifest["waves"]
        for track in wave["tracks"]
    }

    assert "spec/eval/p27_dependency_evidence_tooling_contract.yaml" in manifest["basis"]
    assert manifest["merge_order"][-1] == "P27"
    assert "P27" in tracks
    track = tracks["P27"]
    assert track["prompt"] == "prompts/27_dependency_evidence_tooling_design.md"
    assert track["role"] == "mcp_engineer"
    assert track["skills"] == [
        "mcp-tooling-design",
        "eval-fixture-authoring",
        "quality-gate-review",
        "docs-sync",
    ]
    assert track["depends_on"] == ["P24D"]
    assert "tests/contract/test_p27_dependency_evidence_tooling_prompt_assets.py" in track[
        "target_paths"
    ]
    assert "tests/eval/test_p27_dependency_evidence_hard_live_gate.py" in track[
        "target_paths"
    ]
    assert ".env.example" in track["target_paths"]
    assert "fixtures/mcp/metadata_snapshot.json" in track["target_paths"]
    assert "docker/test/docker-compose.yml" in track["target_paths"]
    assert track["optional_verify"] == [
        P27_HARD_LIVE_VERIFY,
    ]
    assert track["verify"] == [
        P27_MANIFEST_DEFAULT_VERIFY,
        "git diff --check",
    ]


def test_p27_contract_tracks_p28_api_and_p29_web_workflow_slices() -> None:
    contract = _load_yaml(CONTRACT)
    text = PROMPT.read_text(encoding="utf-8")

    assert contract["contract_id"] == "p27_dependency_evidence_tooling@0.3.0"
    assert contract["phase"] == "P27"
    assert contract["status"] == "fixture_first_hardened_with_explicit_live_gate"
    assert contract["production_ready"] is False
    assert contract["scope"]["excluded"] == [
        "persisted artifact type changes",
        "default live metadata or OpenAI gate requirements",
        "DB schema changes",
    ]
    assert contract["api_invocation_route"]["path"] == (
        "/api/v1/metadata/tools/{toolName}/invoke"
    )
    assert contract["api_invocation_route"]["status"] == "p28_safe_fixture_first_enabled"
    assert contract["api_invocation_route"]["allowlisted_tools"] == [
        "get_dependency_closure",
        "resolve_dependency_reference",
    ]
    assert contract["api_invocation_route"]["excluded"] == [
        "input schema exposure through /api/v1/metadata/tools",
        "persisted artifact type changes",
        "DB schema changes",
    ]
    assert contract["web_diagnostic_ui"]["route"] == "/metadata/dependencies"
    assert contract["web_diagnostic_ui"]["status"] == "p29_fixture_first_enabled"
    assert contract["workflow_evidence_wiring"]["status"] == "p29_fixture_first_enabled"
    assert contract["workflow_evidence_wiring"]["automatic_tool"] == [
        "get_dependency_closure",
    ]
    assert contract["workflow_evidence_wiring"]["manual_only_tools"] == [
        "resolve_dependency_reference",
    ]
    boundary = contract["p29b_deferred_boundary"]
    assert boundary["status"] == "confirmed_deferred"
    assert boundary["db_migration"] == "deferred"
    assert boundary["persisted_artifact_type"] == "deferred"
    assert boundary["workflow_state_transition"] == "deferred"
    assert boundary["live_ppm_hard_gate"] == "explicit_env_only"
    assert any("sanitized dependencyEvidence" in item for item in boundary["storage_shape"])
    assert any("VALIDATION_COMPLETE" in item for item in boundary["workflow_shape"])
    assert any("P27_HARD_LIVE_GATE=1" in item for item in boundary["verification_boundary"])
    assert contract["verification"]["default"] == [
        P29_CONTRACT_DEFAULT_VERIFY,
        "git diff --check",
    ]
    assert contract["verification"]["hard_live"] == [
        P27_HARD_LIVE_VERIFY,
    ]
    assert contract["implemented_tools"]["get_dependency_closure"]["active"] is True
    assert contract["implemented_tools"]["get_dependency_closure"]["readOnly"] is True
    assert (
        contract["implemented_tools"]["get_dependency_closure"]["implementationStatus"]
        == "fixture_first_hardened_with_explicit_live_gate"
    )
    assert contract["implemented_tools"]["resolve_dependency_reference"]["active"] is True
    assert contract["implemented_tools"]["resolve_dependency_reference"]["readOnly"] is True
    assert (
        contract["implemented_tools"]["resolve_dependency_reference"][
            "implementationStatus"
        ]
        == "fixture_first_hardened_with_explicit_live_gate"
    )
    assert "fixture-first hardening" in text
    assert "P27_HARD_LIVE_GATE=1" in text


def test_p27_prompt_forbids_unsafe_tooling_expansion() -> None:
    text = PROMPT.read_text(encoding="utf-8")

    blocker_markers = (
        "free-form SQL, row data, procedure execution",
        "business DB DDL/DML",
        "raw definition storage",
        "raw prompt/provider response storage",
        "P27_HARD_LIVE_GATE=1",
    )
    for marker in blocker_markers:
        assert marker in text

    assert "planned_p27_design_only" not in text
