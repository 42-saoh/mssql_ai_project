from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_openapi_skeleton_exists_and_parses() -> None:
    path = ROOT / "spec" / "openapi" / "ai_agent_platform_openapi_v1.yaml"
    assert path.exists()

    data = yaml.safe_load(path.read_text(encoding="utf-8"))

    assert data["openapi"] == "3.1.0"
    assert data["info"]["title"] == "MSSQL Analysis Agent Platform API"
    assert "/health" in data["paths"]
    assert "/api/v1/requests/sp-analysis" in data["paths"]
    assert "/api/v1/jobs/{jobId}" in data["paths"]
    assert "SPAnalysisRequest" in data["components"]["schemas"]
    assert "Artifact" in data["components"]["schemas"]
    assert "ValidationReport" in data["components"]["schemas"]


def test_env_sample_contains_worktree_port_defaults_without_secrets() -> None:
    path = ROOT / ".env.example"
    assert path.exists()

    text = path.read_text(encoding="utf-8")

    assert "WORKTREE_PORT_SLOT=\nAPP_PORT=\nMCP_PORT=\nWEB_PORT=" in text
    assert "Leave APP/MCP/WEB port empty" in text
    assert "PLATFORM_DB_PASSWORD=\n" in text
    assert "MSSQL_METADATA_PASSWORD=\n" in text
    assert "TPsaoh" not in text
