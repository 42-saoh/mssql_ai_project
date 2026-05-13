from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from scripts import p35_knowledge_live_probe

ROOT = Path(__file__).resolve().parents[2]
REQUIRED_ENV = (
    "P35_KNOWLEDGE_LIVE_GATE",
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
    "LLM_LIVE_GATE",
    "LLM_ENABLE_REMOTE",
    "LLM_ALLOW_SP_TEXT",
    "OPENAI_API_KEY",
)
EXPECTED_REDACTION = {
    "tokens": "not_returned",
    "rawJwtClaims": "not_returned",
    "plfRows": "not_returned",
    "ppmRows": "not_returned",
    "connectionStrings": "not_returned",
    "rawPrompts": "not_returned",
    "rawProviderResponses": "not_returned",
}


def test_p35_gate_disabled_does_not_initialize_live_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in REQUIRED_ENV:
        monkeypatch.delenv(name, raising=False)

    def fail_on_live_access(*_args, **_kwargs):
        raise AssertionError("Disabled P35 gate must not initialize PLF/PPM/OpenAI access.")

    monkeypatch.setattr(
        p35_knowledge_live_probe,
        "reset_application_state",
        fail_on_live_access,
    )
    monkeypatch.setattr(p35_knowledge_live_probe, "TestClient", fail_on_live_access)

    result = p35_knowledge_live_probe.run_probe(load_dotenv=False)

    assert result["status"] == "skipped"
    assert result["productionReady"] is False
    assert result["blockerCode"] is None
    assert result["checks"] == []
    assert result["redaction"] == EXPECTED_REDACTION


def test_p35_gate_enabled_missing_prerequisites_returns_blocker_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (*REQUIRED_ENV, "AUTH_RBAC_ENFORCEMENT", "OIDC_REVIEWER_BEARER_TOKEN"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("P35_KNOWLEDGE_LIVE_GATE", "1")

    def fail_on_live_access(*_args, **_kwargs):
        raise AssertionError("Missing P35 prerequisites must fail before live access.")

    monkeypatch.setattr(
        p35_knowledge_live_probe,
        "reset_application_state",
        fail_on_live_access,
    )
    monkeypatch.setattr(p35_knowledge_live_probe, "TestClient", fail_on_live_access)

    result = p35_knowledge_live_probe.run_probe(load_dotenv=False)

    assert result["status"] == "failed"
    assert result["productionReady"] is False
    assert result["blockerCode"] == "P35_KNOWLEDGE_LIVE_REQUIRED"
    assert result["checks"][0]["name"] == "required_env"
    assert "OPENAI_API_KEY" in result["checks"][0]["summary"]
    assert "LLM_ALLOW_SP_TEXT=1" in result["checks"][0]["summary"]
    assert result["redaction"] == EXPECTED_REDACTION


def test_p35_env_sample_and_docker_compose_forward_live_gate_names() -> None:
    env_text = (ROOT / ".env.example").read_text(encoding="utf-8")
    compose_text = (ROOT / "docker" / "test" / "docker-compose.yml").read_text(
        encoding="utf-8"
    )

    for name in ("P32_LIVE_CONFIDENCE_GATE", "P35_KNOWLEDGE_LIVE_GATE"):
        assert f"{name}=" in env_text
        assert name in compose_text


def test_p35_knowledge_live_confidence_gate() -> None:
    if os.getenv("P35_KNOWLEDGE_LIVE_GATE", "").strip() != "1":
        pytest.skip(
            "P35 knowledge live confidence gate requires P35_KNOWLEDGE_LIVE_GATE=1. "
            "Default eval remains fixture-first and does not call PLF, PPM, or OpenAI."
        )

    result = p35_knowledge_live_probe.run_probe(load_dotenv=True)
    if result["status"] != "passed":
        pytest.fail(json.dumps(result, ensure_ascii=True, sort_keys=True))

    assert result["productionReady"] is False
    assert result["blockerCode"] is None
    assert result["redaction"] == EXPECTED_REDACTION
    checks = {item["name"]: item for item in result["checks"]}
    assert checks["knowledge_review"]["status"] == "pass"
    assert checks["knowledge_export"]["status"] == "pass"
