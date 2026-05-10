from __future__ import annotations

import json
import os

import pytest
from scripts import p21_live_portal_probe

REQUIRED_ENV = (
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
)

EXPECTED_REDACTION = {
    "tokens": "not_returned",
    "rawJwtClaims": "not_returned",
    "plfRows": "not_returned",
    "ppmRows": "not_returned",
    "connectionStrings": "not_returned",
}


def test_p21_gate_disabled_returns_skip_without_plf_or_ppm_access(monkeypatch) -> None:
    for name in REQUIRED_ENV:
        monkeypatch.delenv(name, raising=False)

    def fail_on_live_access(*_args, **_kwargs):
        raise AssertionError("P21 default eval must not initialize PLF/PPM live access.")

    monkeypatch.setattr(
        p21_live_portal_probe,
        "reset_application_state",
        fail_on_live_access,
    )
    monkeypatch.setattr(p21_live_portal_probe, "TestClient", fail_on_live_access)

    result = p21_live_portal_probe.run_probe(load_dotenv=False)

    assert result["status"] == "skipped"
    assert result["productionReady"] is False
    assert result["blockerCode"] is None
    assert result["checks"] == []
    assert result["redaction"] == EXPECTED_REDACTION
    assert "default eval did not access PLF" in result["summary"]


def test_p21_gate_enabled_missing_prerequisites_returns_blocker_failure(
    monkeypatch,
) -> None:
    for name in REQUIRED_ENV:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("P21_LIVE_PORTAL_GATE", "1")

    def fail_on_live_access(*_args, **_kwargs):
        raise AssertionError("Missing prerequisites must fail before PLF/PPM access.")

    monkeypatch.setattr(
        p21_live_portal_probe,
        "reset_application_state",
        fail_on_live_access,
    )
    monkeypatch.setattr(p21_live_portal_probe, "TestClient", fail_on_live_access)

    result = p21_live_portal_probe.run_probe(load_dotenv=False)

    assert result["status"] == "failed"
    assert result["productionReady"] is False
    assert result["blockerCode"] == "P21_LIVE_PORTAL_REQUIRED_ENV_MISSING"
    assert result["redaction"] == EXPECTED_REDACTION
    assert result["checks"][0]["status"] == "fail"
    assert result["checks"][0]["blockerCode"] == "P21_LIVE_PORTAL_REQUIRED_ENV_MISSING"
    assert "MSSQL_ENABLE_LIVE_METADATA=1" in result["checks"][0]["summary"]


def test_p21_live_portal_gate() -> None:
    if os.getenv("P21_LIVE_PORTAL_GATE") != "1":
        pytest.skip("P21_LIVE_PORTAL_GATE is not enabled; no PLF/PPM live access attempted.")

    result = p21_live_portal_probe.run_probe(load_dotenv=True)
    if result["status"] != "passed":
        pytest.fail(json.dumps(result, ensure_ascii=False, sort_keys=True))

    assert result["productionReady"] is False
    assert result["blockerCode"] is None
    assert result["redaction"] == EXPECTED_REDACTION
