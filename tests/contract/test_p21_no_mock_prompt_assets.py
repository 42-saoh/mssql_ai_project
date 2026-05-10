from __future__ import annotations

from pathlib import Path

import yaml
from scripts.p21_live_portal_probe import run_probe

ROOT = Path(__file__).resolve().parents[2]
PROMPTS = ROOT / "ops" / "codex-parallel" / "prompts"
MANIFEST = ROOT / "ops" / "codex-parallel" / "REQUEST_MANIFEST.yaml"
FIXTURE = ROOT / "fixtures" / "eval" / "live_portal_no_mock_p21_v1.yaml"
WEB_ROOT = ROOT / "apps" / "web"


def _active_python_baseline_docs() -> list[Path]:
    explicit_files = [
        ROOT / "PROJECT.md",
        ROOT / "TOOLS.md",
        ROOT / "EVAL_SPEC.md",
        ROOT / "docker" / "test" / "README.md",
        ROOT / "requirements" / "lock" / "README.md",
        ROOT / "ops" / "codex-parallel" / "REQUEST_MANIFEST.yaml",
    ]
    recursive_roots = [
        ROOT / "docs",
        ROOT / "ops" / "codex-parallel",
    ]
    files = {path for path in explicit_files if path.exists()}
    for base in recursive_roots:
        files.update(path for path in base.rglob("*") if path.suffix in {".md", ".yaml", ".yml"})
    return sorted(files)


def test_p21_prompts_capture_required_contract_sections() -> None:
    prompt_names = (
        "21a_python314_environment_baseline.md",
        "21b_live_api_mcp_backend_closure.md",
        "21c_web_no_mock_functional_portal.md",
        "21d_eval_docs_readiness.md",
    )
    required_sections = (
        "## 공통 운영 철학",
        "## 목표",
        "## 읽어야 할 기준 파일",
        "## 허용 수정 경로",
        "## 금지 경로",
        "## 구현 범위",
        "## 검증 명령",
        "## Blocker 보고 기준",
    )
    for name in prompt_names:
        text = (PROMPTS / name).read_text(encoding="utf-8")
        for section in required_sections:
            assert section in text
        assert "Python 3.14" in text or "python3.14" in text
        assert "`PLF`" in text
        assert "`PPM`" in text
        assert "PLF 로 대체하지 않는다" in text or "PLF fallback" in text
        assert "production_ready: false" in text


def test_p21_manifest_tracks_follow_p20_merge_order() -> None:
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    tracks = {
        track["id"]: track
        for wave in manifest["waves"]
        for track in wave["tracks"]
    }

    assert manifest["reproducibility"]["python_lock"] == "requirements/lock/py314-dev.txt"
    assert ["P20", "P21A", "P21B", "P21C", "P21D"] == [
        item
        for item in manifest["merge_order"]
        if item in {"P20", "P21A", "P21B", "P21C", "P21D"}
    ]
    for track_id, prompt_name in {
        "P21A": "prompts/21a_python314_environment_baseline.md",
        "P21B": "prompts/21b_live_api_mcp_backend_closure.md",
        "P21C": "prompts/21c_web_no_mock_functional_portal.md",
        "P21D": "prompts/21d_eval_docs_readiness.md",
    }.items():
        assert tracks[track_id]["prompt"] == prompt_name
    assert tracks["P21A"]["depends_on"] == ["P20"]
    assert tracks["P21B"]["depends_on"] == ["P21A"]
    assert tracks["P21C"]["depends_on"] == ["P21B"]
    assert tracks["P21D"]["depends_on"] == ["P21C"]


def test_p21_fixture_declares_no_mock_live_portal_contract() -> None:
    fixture = yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))

    assert fixture["python_baseline"]["runtime_version"] == "3.14"
    assert fixture["python_baseline"]["lock_file"] == "requirements/lock/py314-dev.txt"
    assert fixture["database_boundaries"]["platform_db"]["acronym"] == "PLF"
    assert fixture["database_boundaries"]["metadata_target_db"]["acronym"] == "PPM"
    assert fixture["database_boundaries"]["plf_fallback_for_ppm_allowed"] is False
    assert fixture["web_contract"]["api_transport"] == "HTTP_ONLY"
    assert fixture["web_contract"]["runtime_mock_adapter_allowed"] is False
    assert fixture["readiness_boundaries"]["production_ready"] is False
    assert "AUTH_RBAC_LIVE_IDP_PLF_WIRING_UNVERIFIED" in {
        item["code"] for item in fixture["deferred_future_hardening"]
    }
    assert fixture["web_contract"]["required_functional_pages"] == [
        "/",
        "/requests/new",
        "/metadata/search",
        "/jobs/[jobId]",
        "/artifacts/[artifactId]",
        "/review/decision",
    ]


def test_p21_python314_assets_are_active_baseline() -> None:
    makefile = (ROOT / "Makefile").read_text(encoding="utf-8")
    pyproject = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    dockerfile = (ROOT / "docker" / "test" / "Dockerfile.python").read_text(encoding="utf-8")
    lock_readme = (ROOT / "requirements" / "lock" / "README.md").read_text(encoding="utf-8")

    assert "PYTHON ?= python3.14" in makefile
    assert "PYTHON_LOCK_FILE ?= requirements/lock/py314-dev.txt" in makefile
    assert "$(PYTHON) -m uvicorn" in makefile
    assert "$(PYTHON) -m ruff" in makefile
    assert 'requires-python = ">=3.14"' in pyproject
    assert 'target-version = "py314"' in pyproject
    assert "python:3.14-slim" in dockerfile
    assert "py314-dev.txt" in lock_readme
    assert (ROOT / "requirements" / "lock" / "py314-dev.txt").exists()
    assert sorted(
        path.name for path in (ROOT / "requirements" / "lock").glob("py*-dev.txt")
    ) == ["py314-dev.txt"]


def test_p21_active_docs_do_not_reference_legacy_python_baselines() -> None:
    forbidden_snippets = (
        "py311-dev.txt",
        "py312-dev.txt",
        "py313-dev.txt",
        "Python 3.11",
        "Python 3.12",
        "Python 3.13",
        "python3.11",
        "python3.12",
        "python3.13",
        "PYTHON=python3",
        "python3 -m compileall",
        "python3 tests/",
        "python3 apps/",
        "python -m pytest",
        "python -m compileall",
        "python - <<",
        "python3 - <<",
        "python -c",
        "python3 -c",
    )
    offenders: list[str] = []
    for path in _active_python_baseline_docs():
        text = path.read_text(encoding="utf-8")
        for snippet in forbidden_snippets:
            if snippet in text:
                offenders.append(f"{path.relative_to(ROOT)} contains {snippet!r}")

    assert offenders == []


def test_p21_web_no_mock_runtime_contract() -> None:
    client = (WEB_ROOT / "lib" / "api" / "client.ts").read_text(encoding="utf-8")
    http_client = (WEB_ROOT / "lib" / "api" / "http-client.ts").read_text(encoding="utf-8")
    functional_source = "\n".join(
        path.read_text(encoding="utf-8")
        for root in (WEB_ROOT / "app", WEB_ROOT / "components", WEB_ROOT / "lib" / "api")
        for path in root.rglob("*")
        if path.suffix in {".ts", ".tsx"} and path.name != "mock-adapter.ts"
    )

    assert "mock-adapter" not in client
    assert 'process.env.PORTAL_API_MODE ?? "http"' in client
    assert "PORTAL_API_BASE_URL is required for the P21 no-mock portal" in client
    assert "/api/v1/jobs" in http_client
    assert "/validation/latest" in http_client
    for demo_id in ("job_demo_", "art_demo_", "approval_preview_"):
        assert demo_id not in functional_source
    assert "api.createSPAnalysisRequest" in functional_source
    assert "api.getLatestValidation" in functional_source
    assert "api.createApprovalDecision" in functional_source


def test_p21_env_compose_and_probe_missing_prerequisites(monkeypatch) -> None:
    env_text = (ROOT / ".env.example").read_text(encoding="utf-8")
    compose_text = (ROOT / "docker" / "test" / "docker-compose.yml").read_text(encoding="utf-8")

    for name in (
        "P21_LIVE_PORTAL_GATE",
        "PORTAL_API_MODE",
        "PORTAL_API_BASE_URL",
        "P21_METADATA_SEARCH_QUERY",
        "P21_APPROVAL_REVIEWER_LOGIN",
    ):
        assert f"{name}=" in env_text
        assert name in compose_text or name.startswith("P21_")

    for name in (
        "P21_LIVE_PORTAL_GATE",
        "PLATFORM_DB_HOST",
        "PLATFORM_DB_PORT",
        "PLATFORM_DB_USER",
        "PLATFORM_DB_PASSWORD",
        "PLATFORM_DB_NAME",
        "MSSQL_ENABLE_LIVE_METADATA",
        "MSSQL_METADATA_HOST",
        "MSSQL_METADATA_PORT",
        "MSSQL_METADATA_USER",
        "MSSQL_METADATA_PASSWORD",
        "MSSQL_METADATA_PROFILE_FILE",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("P21_LIVE_PORTAL_GATE", "1")

    result = run_probe(load_dotenv=False)

    assert result["status"] == "failed"
    assert result["productionReady"] is False
    assert result["blockerCode"] == "P21_LIVE_PORTAL_REQUIRED_ENV_MISSING"
    assert result["redaction"]["plfRows"] == "not_returned"
    assert result["redaction"]["ppmRows"] == "not_returned"
