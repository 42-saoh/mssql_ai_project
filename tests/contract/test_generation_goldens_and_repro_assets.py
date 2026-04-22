from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]


def test_dev_port_and_repro_assets_exist() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    assert "resolve_dev_ports.sh" in makefile
    assert "install_python_locked.sh" in makefile
    assert "install_web_workspace.sh" in makefile
    assert "APP_PORT ?=" in makefile
    assert "MCP_PORT ?=" in makefile
    assert "WEB_PORT ?=" in makefile
    assert "dev-ports" in makefile

    assert (ROOT / "scripts" / "resolve_dev_ports.sh").exists()
    assert (ROOT / "scripts" / "install_python_locked.sh").exists()
    assert (ROOT / "scripts" / "install_web_workspace.sh").exists()
    assert (ROOT / "requirements" / "lock" / "py311-dev.txt").exists()

    web_package = yaml.safe_load((ROOT / "apps" / "web" / "package.json").read_text(encoding="utf-8"))
    assert web_package["packageManager"] == "pnpm@10.0.0"

    runbook = (ROOT / "ops" / "codex-parallel" / "PARALLEL_RUNBOOK.md").read_text(encoding="utf-8")
    assert "make dev-ports" in runbook
    assert "pnpm-lock.yaml" in runbook
    assert "WORKTREE_PORT_SLOT=21 make dev-ports" in runbook


def test_generation_golden_sample_exists_and_is_consistent() -> None:
    sample_dir = ROOT / "fixtures" / "generation" / "golden" / "java_mybatis_sp_wrapper_order_request_v1"
    assert sample_dir.exists()

    input_data = yaml.safe_load((sample_dir / "input.yaml").read_text(encoding="utf-8"))
    manifest = yaml.safe_load((sample_dir / "expected_manifest.yaml").read_text(encoding="utf-8"))
    expected_output = (sample_dir / "expected_output.md").read_text(encoding="utf-8")

    assert input_data["request"]["generationMode"] == "spWrapper"
    assert input_data["request"]["entityName"] == "OrderRequest"
    assert manifest["generationMode"] == "spWrapper"
    assert "## evidence_summary" in expected_output
    assert "## assumptions_and_todo" in expected_output
    assert "## review_checklist" in expected_output

    for relative_path in manifest["expectedFiles"]:
        assert (sample_dir / relative_path).exists(), relative_path
