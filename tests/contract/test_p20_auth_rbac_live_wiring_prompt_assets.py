from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
PROMPT = (
    ROOT
    / "ops"
    / "codex-parallel"
    / "prompts"
    / "20_auth_rbac_live_wiring_verification.md"
)
MANIFEST = ROOT / "ops" / "codex-parallel" / "REQUEST_MANIFEST.yaml"

REQUIRED_SECTIONS = (
    "## 목표",
    "## 읽어야 할 기준 파일",
    "## 허용 수정 경로",
    "## 금지 경로",
    "## 구현 범위",
    "## 검증 명령",
    "## Blocker 보고 기준",
)


def test_p20_prompt_preserves_auth_live_wiring_safety_contract() -> None:
    text = PROMPT.read_text(encoding="utf-8")

    assert text.startswith("# P20 Auth/RBAC Live Wiring Verification")
    for section in REQUIRED_SECTIONS:
        assert section in text

    required_fragments = (
        "AUTH_RBAC_LIVE_IDP_PLF_WIRING_UNVERIFIED",
        "AUTH_RBAC_LIVE_GATE=1",
        "AUTH_RBAC_ENFORCEMENT=1",
        "OIDC_ISSUER",
        "OIDC_AUDIENCE",
        "OIDC_JWKS_URL",
        "OIDC_USER_BEARER_TOKEN",
        "PLATFORM_DB_*",
        "OidcJwtVerifier",
        "MssqlPlatformRepository.resolve_actor_roles()",
        "tests/eval/test_p20_auth_rbac_live_gate.py",
        "apps/api/scripts/auth_rbac_live_probe.py",
    )
    for fragment in required_fragments:
        assert fragment in text

    forbidden_boundaries = (
        "row data",
        "procedure execution",
        "DDL/DML",
        "workflow write",
        "audit write",
        "raw JWT claims",
        "token/secret",
        "mock header",
        "fixture token",
        "PLF fallback",
    )
    for fragment in forbidden_boundaries:
        assert fragment in text

    assert "PFL" not in text
    assert "production-ready: true" not in text
    assert "OIDC_REVIEWER_BEARER_TOKEN" not in text
    assert "OIDC_USER_BEARER_TOKEN=" not in text


def test_p20_manifest_declares_post_p18b_live_wiring_track() -> None:
    manifest = _yaml(MANIFEST)
    tracks = _tracks(manifest)
    track = tracks["P20"]

    assert track["prompt"] == "prompts/20_auth_rbac_live_wiring_verification.md"
    assert track["worktree"] == "../wt/p20-auth-rbac-live-wiring"
    assert track["depends_on"] == ["P18B"]
    assert track["role"] == "platform_worker"
    assert "apps/api/" in track["target_paths"]
    assert "tests/eval/" in track["target_paths"]
    assert "fixtures/eval/productization_gap_closure_p18_v1.yaml" in track[
        "target_paths"
    ]
    assert ".env.example" in track["target_paths"]
    assert "config/mssql/local_docker_profiles.yaml" in track["readonly_paths"]
    assert "fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml" in track[
        "readonly_paths"
    ]
    assert any("AUTH_RBAC_LIVE_GATE=1" in command for command in track["verify"])

    order = manifest["merge_order"]
    assert order.index("P18B") < order.index("P20")


def _yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _tracks(manifest: dict[str, Any]) -> dict[str, dict[str, Any]]:
    tracks: dict[str, dict[str, Any]] = {}
    for wave in manifest["waves"]:
        for track in wave["tracks"]:
            tracks[track["id"]] = track
    return tracks
