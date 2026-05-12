from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
PROMPT = ROOT / "ops" / "codex-parallel" / "prompts" / "27_dependency_evidence_tooling_design.md"
MANIFEST = ROOT / "ops" / "codex-parallel" / "REQUEST_MANIFEST.yaml"
CONTRACT = ROOT / "spec" / "eval" / "p27_dependency_evidence_tooling_contract.yaml"

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
    "active: false",
    "readOnly: true",
    "structured-input-only",
    "planned_p27_design_only",
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
    "MCP handler",
    "API 또는 Web wiring",
)


def _load_yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_p27_prompt_exists_and_captures_design_only_boundaries() -> None:
    text = PROMPT.read_text(encoding="utf-8")

    for section in REQUIRED_PROMPT_SECTIONS:
        assert section in text
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
    assert track["skills"] == ["mcp-tooling-design", "quality-gate-review", "docs-sync"]
    assert track["depends_on"] == ["P24D"]
    assert "tests/contract/test_p27_dependency_evidence_tooling_prompt_assets.py" in track[
        "target_paths"
    ]
    assert track["verify"] == [
        'make test PYTEST_ARGS="tests/contract/test_p27_dependency_evidence_tooling_prompt_assets.py tests/unit/test_mcp_catalog.py tests/contract/mcp/test_tool_invocation_contract.py"',
        "git diff --check",
    ]


def test_p27_contract_and_prompt_remain_contract_only() -> None:
    contract = _load_yaml(CONTRACT)
    text = PROMPT.read_text(encoding="utf-8")

    assert contract["contract_id"] == "p27_dependency_evidence_tooling_design@0.1.0"
    assert contract["phase"] == "P27"
    assert contract["production_ready"] is False
    assert contract["scope"]["excluded"] == [
        "MCP handler implementation",
        "API or Web wiring",
        "runtime workflow changes",
        "persisted artifact type changes",
        "fixture suite expansion beyond contract checks",
        "live metadata or OpenAI gate requirements",
    ]
    assert contract["verification"]["default"] == [
        'make test PYTEST_ARGS="tests/contract/test_p27_dependency_evidence_tooling_prompt_assets.py tests/unit/test_mcp_catalog.py tests/contract/mcp/test_tool_invocation_contract.py"',
        "git diff --check",
    ]
    assert contract["planned_tools"]["get_dependency_closure"]["active"] is False
    assert contract["planned_tools"]["get_dependency_closure"]["readOnly"] is True
    assert contract["planned_tools"]["resolve_dependency_reference"]["active"] is False
    assert contract["planned_tools"]["resolve_dependency_reference"]["readOnly"] is True
    assert "MCP handler 구현이 아니라" in text
    assert "새 MCP handler/API/Web wiring 은 만들지 않는다" in text


def test_p27_prompt_forbids_unsafe_tooling_expansion() -> None:
    text = PROMPT.read_text(encoding="utf-8")

    blocker_markers = (
        "planned dependency tool 이 active/invokable default 로 바뀜",
        "free-form SQL, row data, procedure execution",
        "business DB DDL/DML",
        "raw definition storage",
        "raw prompt/provider response storage",
        "PLF fallback 을 허용함",
        "catalog confirmation 없이 deterministic fact 로 승격함",
    )
    for marker in blocker_markers:
        assert marker in text

    assert "production_ready: true 를 유지한다" not in text
    assert "active: true 상태로만 catalog 에 둔다" not in text
