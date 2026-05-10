from __future__ import annotations

import sys
from types import SimpleNamespace

import pytest
from mssql_mcp_app.live_connection import probe_profile_connection
from mssql_mcp_app.profiles import DbProfile
from mssql_mcp_app.repositories import LiveMetadataRepository
from mssql_mcp_app.settings import LiveMetadataSettings


class FakeConnection:
    def __init__(self) -> None:
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _settings() -> LiveMetadataSettings:
    return LiveMetadataSettings(
        live_metadata_enabled=True,
        metadata_host="127.0.0.1",
        metadata_port=1433,
        metadata_user="readonly_user",
        metadata_password="secret",
        metadata_db_fallback="master",
        default_profile_id="master",
        profile_file="config/mssql/local_docker_profiles.yaml",
        connect_timeout_seconds=7,
    )


def _profile() -> DbProfile:
    return DbProfile(
        id="ppm",
        label="Pilot Analysis Target DB (PPM)",
        database="PPM",
        purpose="pilot-analysis-target",
    )


def test_live_metadata_probe_uses_pytds_dsn_keyword(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}
    fake_connection = FakeConnection()

    def fake_connect(**kwargs: object) -> FakeConnection:
        captured.update(kwargs)
        return fake_connection

    monkeypatch.setitem(sys.modules, "pytds", SimpleNamespace(connect=fake_connect))

    result = probe_profile_connection(_profile(), _settings())

    assert result["connection"] == "ok"
    assert fake_connection.closed is True
    assert captured["dsn"] == "127.0.0.1"
    assert captured["port"] == 1433
    assert "server" not in captured
    assert captured["database"] == "PPM"


def test_live_metadata_repository_connect_uses_pytds_dsn_keyword(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, object] = {}
    fake_connection = FakeConnection()
    profile = _profile()
    repository = LiveMetadataRepository(settings=_settings(), profiles=[profile])

    def fake_connect(**kwargs: object) -> FakeConnection:
        captured.update(kwargs)
        return fake_connection

    monkeypatch.setitem(sys.modules, "pytds", SimpleNamespace(connect=fake_connect))

    assert repository._connect("PPM", profile=profile, tool_name="list_procedures") is fake_connection
    assert captured["dsn"] == "127.0.0.1"
    assert captured["port"] == 1433
    assert "server" not in captured
    assert captured["database"] == "PPM"
