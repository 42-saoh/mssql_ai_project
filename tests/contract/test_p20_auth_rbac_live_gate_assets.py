from __future__ import annotations

from pathlib import Path

from scripts.auth_rbac_live_probe import run_probe

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "apps" / "api" / "scripts" / "auth_rbac_live_probe.py"
ENV_SAMPLE = ROOT / ".env.example"
COMPOSE = ROOT / "docker" / "test" / "docker-compose.yml"
API_README = ROOT / "apps" / "api" / "README.md"
AUTH_DOC = ROOT / "docs" / "admin-guide" / "auth-rbac-production-source.md"
EVAL_README = ROOT / "tests" / "eval" / "README.md"


def test_p20_live_probe_asset_is_read_only_and_redacted() -> None:
    text = SCRIPT.read_text(encoding="utf-8")

    assert "OidcJwtVerifier" in text
    assert "MssqlPlatformRepository" in text
    assert "resolve_actor_roles" in text
    assert "/validation" not in text
    assert "/approval-decisions" not in text
    assert "record_audit_event" not in text
    assert "create_request(" not in text
    assert "create_job(" not in text
    assert "OIDC_REVIEWER_BEARER_TOKEN=" not in text
    assert "OIDC_USER_BEARER_TOKEN=" not in text
    for redacted_field in ("tokens", "rawJwtClaims", "plfRows", "connectionStrings"):
        assert redacted_field in text


def test_p20_live_probe_reports_missing_env_as_deferred_prerequisite(
    monkeypatch,
) -> None:
    for name in (
        "AUTH_RBAC_LIVE_GATE",
        "AUTH_RBAC_ENFORCEMENT",
        "OIDC_ISSUER",
        "OIDC_AUDIENCE",
        "OIDC_JWKS_URL",
        "OIDC_REVIEWER_BEARER_TOKEN",
        "OIDC_USER_BEARER_TOKEN",
        "PLATFORM_DB_HOST",
        "PLATFORM_DB_PORT",
        "PLATFORM_DB_USER",
        "PLATFORM_DB_PASSWORD",
        "PLATFORM_DB_NAME",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AUTH_RBAC_LIVE_GATE", "1")

    result = run_probe(load_dotenv=False)

    assert result["status"] == "failed"
    assert result["deferredItem"] == "AUTH_RBAC_LIVE_IDP_PLF_WIRING_UNVERIFIED"
    assert result["productizationBlocking"] is False
    assert result["blockerCode"] == "AUTH_RBAC_LIVE_REQUIRED_ENV_MISSING"
    assert "primaryBlocker" not in result
    assert result["redaction"] == {
        "tokens": "not_returned",
        "rawJwtClaims": "not_returned",
        "plfRows": "not_returned",
        "connectionStrings": "not_returned",
    }


def test_p20_env_sample_and_docker_compose_forward_live_gate_names() -> None:
    env_text = ENV_SAMPLE.read_text(encoding="utf-8")
    compose_text = COMPOSE.read_text(encoding="utf-8")

    for name in (
        "AUTH_RBAC_LIVE_GATE",
        "AUTH_RBAC_ENFORCEMENT",
        "OIDC_ISSUER",
        "OIDC_AUDIENCE",
        "OIDC_JWKS_URL",
        "OIDC_REVIEWER_BEARER_TOKEN",
        "OIDC_USER_BEARER_TOKEN",
    ):
        assert f"{name}=" in env_text
        assert name in compose_text

    assert "OIDC_REVIEWER_BEARER_TOKEN=\n" in env_text
    assert "OIDC_USER_BEARER_TOKEN=\n" in env_text


def test_p20_docs_describe_assisted_login_and_no_overclaim() -> None:
    combined = "\n".join(
        path.read_text(encoding="utf-8") for path in (API_README, AUTH_DOC, EVAL_README)
    )

    for phrase in (
        "AUTH_RBAC_LIVE_GATE=1",
        "apps/api/scripts/auth_rbac_live_probe.py",
        "Playwright MCP",
        "Assisted login",
        "AUTH_RBAC_LIVE_IDP_PLF_WIRING_UNVERIFIED",
        "future hardening",
        "deferred",
    ):
        assert phrase in combined

    required_guardrails = (
        "localStorage scraping",
        "cookie scraping",
        "storage-state files",
        "token-bearing screenshots",
        "chat-pasted secrets",
    )
    for fragment in required_guardrails:
        assert fragment in combined
    assert "productization remains `NO_GO` until" not in combined
    assert "production-ready: true" not in combined
