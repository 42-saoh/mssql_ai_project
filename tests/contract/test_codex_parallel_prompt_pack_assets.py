from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]
PROMPTS = ROOT / "ops" / "codex-parallel" / "prompts"


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_parallel_prompt_pack_references_current_baseline_assets() -> None:
    p00 = _read(PROMPTS / "00_coordinator_baseline.md")
    assert "spec/openapi/ai_agent_platform_openapi_v1.yaml" in p00
    assert "spec/policy/**" in p00
    assert ".env.example" in p00
    assert "pnpm-lock.yaml" in p00

    p01 = _read(PROMPTS / "01_mssql_mcp.md")
    assert "tasks/0002-metadata-mcp-mvp.md" in p01
    assert "get_procedure_parameters" in p01
    assert "MSSQL_ENABLE_LIVE_METADATA=1" in p01
    assert "config/mssql/local_docker_profiles.yaml" in p01

    p03 = _read(PROMPTS / "03_generation_validation.md")
    assert "project_ai_java_mybatis_generation_policy.yaml" in p03
    assert "platform_db_standardization_rules_for_ai.json" in p03
    assert "java_mybatis_sp_wrapper_order_request_v1" in p03
    assert "SP_ANALYSIS_DOCUMENT" in p03

    p05 = _read(PROMPTS / "05_api_workflow.md")
    assert "spec/openapi/ai_agent_platform_openapi_v1.yaml" in p05
    assert "request/job/artifact/validation/approval" in p05

    p07 = _read(PROMPTS / "07_final_review.md")
    assert ".env.example" in p07
    assert ".env.example" in p07
    assert "MCP catalog" in p07


def test_parallel_manifest_uses_env_sample_and_current_lockfiles() -> None:
    manifest_path = ROOT / "ops" / "codex-parallel" / "REQUEST_MANIFEST.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))

    assert manifest["plan_id"] == "codex-parallel-local-v2"
    assert ".env.example" in manifest["basis"]
    assert "pnpm-lock.yaml" in manifest["basis"]
    assert "cp .env.example .env" in manifest["preflight"]
    assert manifest["reproducibility"]["env_sample"] == ".env.example"

    p00 = manifest["waves"][0]["tracks"][0]
    assert ".env.example" in p00["target_paths"]
    assert "spec/policy/" in p00["target_paths"]
    assert "ops/codex-parallel/" in p00["target_paths"]


def test_parallel_runbook_prefers_env_sample_and_includes_final_review_worktree() -> None:
    runbook = _read(ROOT / "ops" / "codex-parallel" / "PARALLEL_RUNBOOK.md")

    assert "cp .env.example .env" in runbook
    assert "../wt/p07-final-review" in runbook
    assert "make dev-ports" in runbook
    assert "WORKTREE_PATH=/abs/path/to/worktree make test" in runbook
    assert "APP_PORT`, `MCP_PORT`, `WEB_PORT` 는 비워 두는 것이 기본" in runbook
