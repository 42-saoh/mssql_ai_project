from __future__ import annotations

from pathlib import Path

import yaml


ROOT = Path(__file__).resolve().parents[2]

GENERATION_GOLDENS = (
    ("java_mybatis_sp_wrapper_order_request_v1", "spWrapper", "OrderRequest"),
    ("java_mybatis_dto_model_order_metadata_v1", "metadataObject", "OrderMetadata"),
)


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
    assert (ROOT / "requirements" / "lock" / "py314-dev.txt").exists()

    web_package = yaml.safe_load((ROOT / "apps" / "web" / "package.json").read_text(encoding="utf-8"))
    assert web_package["packageManager"] == "pnpm@10.33.0"

    runbook = (ROOT / "ops" / "codex-parallel" / "PARALLEL_RUNBOOK.md").read_text(encoding="utf-8")
    assert "make dev-ports" in runbook
    assert "pnpm-lock.yaml" in runbook
    assert "WORKTREE_PORT_SLOT=21 make dev-ports" in runbook


def test_generation_golden_samples_exist_and_are_consistent() -> None:
    for sample_name, generation_mode, entity_name in GENERATION_GOLDENS:
        sample_dir = ROOT / "fixtures" / "generation" / "golden" / sample_name
        assert sample_dir.exists()

        input_data = yaml.safe_load((sample_dir / "input.yaml").read_text(encoding="utf-8"))
        manifest = yaml.safe_load(
            (sample_dir / "expected_manifest.yaml").read_text(encoding="utf-8")
        )
        expected_output = (sample_dir / "expected_output.md").read_text(encoding="utf-8")

        assert input_data["request"]["generationMode"] == generation_mode
        assert input_data["request"]["entityName"] == entity_name
        assert manifest["generationMode"] == generation_mode
        assert "generator_metadata_present" in manifest["checks"]
        assert "## generator_metadata" in expected_output
        assert "## evidence_summary" in expected_output
        assert "## assumptions_and_todo" in expected_output
        assert "## review_checklist" in expected_output

        for relative_path in manifest["expectedFiles"]:
            assert (sample_dir / relative_path).exists(), relative_path
