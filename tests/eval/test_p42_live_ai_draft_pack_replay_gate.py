from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from scripts import p42_live_ai_draft_pack_probe

ROOT = Path(__file__).resolve().parents[2]
REQUIRED_ENV = (
    "P42_LIVE_REPLAY_GATE",
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
    "ppmRows": "not_returned",
    "connectionStrings": "not_returned",
    "rawSpDefinitions": "not_returned",
    "rawPrompts": "not_returned",
    "rawProviderResponses": "not_returned",
    "generatedSourceWrites": "not_performed",
}


def test_p42_live_gate_disabled_does_not_initialize_live_access(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in REQUIRED_ENV:
        monkeypatch.delenv(name, raising=False)

    def fail_on_live_access(*_args, **_kwargs):
        raise AssertionError("Disabled P42G gate must not initialize PPM/OpenAI access.")

    monkeypatch.setattr(
        p42_live_ai_draft_pack_probe,
        "reset_application_state",
        fail_on_live_access,
    )
    monkeypatch.setattr(p42_live_ai_draft_pack_probe, "TestClient", fail_on_live_access)
    monkeypatch.setattr(
        p42_live_ai_draft_pack_probe,
        "McpMetadataGateway",
        fail_on_live_access,
    )

    result = p42_live_ai_draft_pack_probe.run_probe(load_dotenv=False)

    assert result["status"] == "skipped"
    assert result["productionReady"] is False
    assert result["blockerCode"] is None
    assert result["checks"] == []
    assert result["artifactSummary"] == {}
    assert result["redaction"] == EXPECTED_REDACTION


def test_p42_live_gate_enabled_missing_prerequisites_returns_blocker_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    for name in (*REQUIRED_ENV, "OPENAI_BASE_URL", "OPENAI_RESPONSES_URL"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("P42_LIVE_REPLAY_GATE", "1")

    def fail_on_live_access(*_args, **_kwargs):
        raise AssertionError("Missing P42G prerequisites must fail before live access.")

    monkeypatch.setattr(
        p42_live_ai_draft_pack_probe,
        "reset_application_state",
        fail_on_live_access,
    )
    monkeypatch.setattr(p42_live_ai_draft_pack_probe, "TestClient", fail_on_live_access)
    monkeypatch.setattr(
        p42_live_ai_draft_pack_probe,
        "McpMetadataGateway",
        fail_on_live_access,
    )

    result = p42_live_ai_draft_pack_probe.run_probe(load_dotenv=False)

    assert result["status"] == "failed"
    assert result["productionReady"] is False
    assert result["blockerCode"] == "P42_LIVE_REPLAY_REQUIRED"
    assert result["checks"][0]["name"] == "required_env"
    assert "OPENAI_API_KEY" in result["checks"][0]["summary"]
    assert "LLM_ALLOW_SP_TEXT=1" in result["checks"][0]["summary"]
    assert result["redaction"] == EXPECTED_REDACTION


def test_p42_env_sample_and_docker_compose_forward_live_gate_name() -> None:
    env_text = (ROOT / ".env.example").read_text(encoding="utf-8")
    compose_text = (ROOT / "docker" / "test" / "docker-compose.yml").read_text(
        encoding="utf-8"
    )
    suites_text = (ROOT / "tests" / "suites.yaml").read_text(encoding="utf-8")

    assert "P42_LIVE_REPLAY_GATE=0" in env_text
    assert "P42_LIVE_REPLAY_GATE" in compose_text
    assert "tests/eval/test_p42_live_ai_draft_pack_replay_gate.py" in suites_text


def test_p42_live_ai_draft_pack_replay_gate() -> None:
    if os.getenv("P42_LIVE_REPLAY_GATE", "").strip() != "1":
        pytest.skip(
            "P42 live AI Draft Pack replay requires P42_LIVE_REPLAY_GATE=1. "
            "Default eval remains fixture-first and does not call PPM or OpenAI."
        )

    result = p42_live_ai_draft_pack_probe.run_probe(load_dotenv=True)
    if result["status"] != "passed":
        pytest.fail(json.dumps(result, ensure_ascii=True, sort_keys=True))

    assert result["productionReady"] is False
    assert result["blockerCode"] is None
    assert result["redaction"] == EXPECTED_REDACTION
    checks = {item["name"]: item for item in result["checks"]}
    assert checks["workflow_submit"]["status"] == "pass"
    assert checks["p42_quality_gate"]["status"] == "pass"
    assert result["artifactSummary"]["counts"]["DTO_DRAFT"] >= 11
    assert result["artifactSummary"]["counts"]["SERVICE_DRAFT"] == 1
    assert result["artifactSummary"]["counts"]["MAPPER_INTERFACE"] == 1
    assert result["artifactSummary"]["counts"]["MAPPER_XML"] == 1
