from __future__ import annotations

import importlib.util
import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[2]
LOCAL_ARTIFACT_PATHS = (
    ".codex-docker-localappdata",
    "buildx",
    ".token_seed",
    ".token_seed.lock",
)


def _load_pytest_selection_runner():
    runner_path = ROOT / "scripts" / "run_pytest_selection.py"
    spec = importlib.util.spec_from_file_location("run_pytest_selection", runner_path)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_pytest_suite_aliases_expand_to_existing_test_files() -> None:
    runner = _load_pytest_selection_runner()
    suites = runner._load_suites()

    assert set(suites) == {"core", "quality", "web", "live-confidence"}
    assert "tests/eval/test_p35_knowledge_live_confidence_gate.py" in suites[
        "live-confidence"
    ]
    assert "tests/eval/test_p42_live_ai_draft_pack_replay_gate.py" in suites[
        "live-confidence"
    ]

    web_targets = runner.expand_targets(["@web"])
    core_targets = runner.expand_targets(["@core"])

    assert "tests/unit/web/test_p14_product_ui_static.py" in web_targets
    assert "tests/e2e/test_web_http_adapter_smoke.py" in web_targets
    assert "tests/contract/test_workspace_cleanup_assets.py" in core_targets
    assert all((ROOT / target.partition("::")[0]).exists() for target in web_targets)


def test_makefile_exposes_safe_consolidated_test_gates() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")

    for target in (
        "test-fixture:",
        "test-core:",
        "test-quality:",
        "test-web:",
        "test-live-confidence:",
    ):
        assert target in makefile

    assert 'PYTEST_ARGS="@core"' in makefile
    assert 'PYTEST_ARGS="@quality"' in makefile
    assert 'PYTEST_ARGS="@web"' in makefile
    assert 'PYTEST_ARGS="@live-confidence"' in makefile
    for forced_off in (
        "P21_LIVE_PORTAL_GATE=0",
        "P27_HARD_LIVE_GATE=0",
        "P35_KNOWLEDGE_LIVE_GATE=0",
        "P42_LIVE_REPLAY_GATE=0",
        "AUTH_RBAC_LIVE_GATE=0",
        "LLM_ENABLE_REMOTE=0",
        "MSSQL_ENABLE_LIVE_METADATA=0",
    ):
        assert forced_off in makefile


def test_environment_templates_are_first_class_and_secret_free() -> None:
    env_sample = (ROOT / ".env.example").read_text(encoding="utf-8")
    mac_template = (ROOT / "config" / "env" / "mac-docker-openai.env.example").read_text(
        encoding="utf-8"
    )
    windows_template = (
        ROOT / "config" / "env" / "windows-sandbox-pgpt.env.example"
    ).read_text(encoding="utf-8")

    for removed_name in (
        "OPENAI_MODEL=",
        "PLATFORM_DB_PROFILE_FILE=",
        "PLATFORM_DB_ENCRYPT=",
        "PLATFORM_DB_TRUST_SERVER_CERT=",
        "MSSQL_METADATA_ENCRYPT=",
        "MSSQL_METADATA_TRUST_SERVER_CERT=",
        "TEST_DOCKER_COMPOSE_FILE=",
        "TEST_PYTHON_SERVICE=",
        "TEST_WEB_SERVICE=",
    ):
        assert removed_name not in env_sample

    assert "config/env/mac-docker-openai.env.example" in env_sample
    assert "config/env/windows-sandbox-pgpt.env.example" in env_sample
    assert "LLM_REMOTE_PROVIDER=openai" in mac_template
    assert "OPENAI_MODEL_ANALYSIS=gpt-5.5" in mac_template
    assert "LLM_REMOTE_PROVIDER=pgpt" in windows_template
    assert "PGPT_MODEL_ANALYSIS=gpt-4o" in windows_template
    assert "MSSQL_METADATA_HOST=" in windows_template
    for text in (env_sample, mac_template, windows_template):
        assert "OPENAI_API_KEY=\n" in text
        assert "sk-" not in text
        assert "PFL" not in text


def test_local_runtime_artifacts_are_ignored_and_not_tracked() -> None:
    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    dockerignore = (ROOT / ".dockerignore").read_text(encoding="utf-8")

    for path in LOCAL_ARTIFACT_PATHS:
        assert path in gitignore
        assert path in dockerignore

    if shutil.which("git") is None:
        pytest.skip("git is not available in this test runner")

    result = subprocess.run(
        ["git", "ls-files", *LOCAL_ARTIFACT_PATHS],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    still_present = [
        tracked_path
        for tracked_path in result.stdout.splitlines()
        if (ROOT / tracked_path).exists()
    ]
    assert still_present == []
