from __future__ import annotations

import sys
from dataclasses import replace
from types import SimpleNamespace

import pytest
from mssql_mcp_app.errors import PPM_DB_ACCESS_DENIED, MetadataToolError
from mssql_mcp_app.live_connection import probe_profile_connection
from mssql_mcp_app.profiles import DbProfile
from mssql_mcp_app.repositories import LiveMetadataRepository
from mssql_mcp_app.settings import LiveMetadataSettings


class FakeConnection:
    def __init__(self) -> None:
        self.closed = False
        self.cursor_instance: FakeCursor | None = None

    def cursor(self) -> "FakeCursor":
        self.cursor_instance = FakeCursor()
        return self.cursor_instance

    def close(self) -> None:
        self.closed = True


class FakeCursor:
    def __init__(self) -> None:
        self.description: list[object] = []
        self.execute_params: tuple[object, ...] = ()
        self.closed = False

    def execute(self, _sql: str, params: tuple[object, ...]) -> None:
        self.execute_params = params

    def fetchall(self) -> list[object]:
        return []

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
    settings = _settings()

    def fake_connect(**kwargs: object) -> FakeConnection:
        captured.update(kwargs)
        return fake_connection

    monkeypatch.setitem(sys.modules, "pytds", SimpleNamespace(connect=fake_connect))

    result = probe_profile_connection(_profile(), settings)

    assert result["connection"] == "ok"
    assert fake_connection.closed is True
    assert captured["dsn"] == "127.0.0.1"
    assert captured["port"] == 1433
    assert "server" not in captured
    assert captured["database"] == "PPM"
    assert captured["tds_version"] == settings.metadata_tds_version


def test_live_metadata_repository_maps_ppm_login_failed_to_access_denied(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = _profile()
    repository = LiveMetadataRepository(settings=_settings(), profiles=[profile])

    def fake_connect(**_kwargs: object) -> FakeConnection:
        raise RuntimeError("Login failed for user 'ppmdevuser'.")

    monkeypatch.setitem(sys.modules, "pytds", SimpleNamespace(connect=fake_connect))

    with pytest.raises(MetadataToolError) as exc_info:
        repository._connect("PPM", profile=profile, tool_name="list_procedures")

    assert exc_info.value.code == PPM_DB_ACCESS_DENIED


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
    assert captured["tds_version"] == _settings().metadata_tds_version


def test_live_metadata_repository_wraps_tds70_string_params_as_nvarchar(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from pytds import tds_base, tds_types

    fake_connection = FakeConnection()
    profile = _profile()
    repository = LiveMetadataRepository(
        settings=replace(_settings(), metadata_tds_version=1879048192),
        profiles=[profile],
    )
    monkeypatch.setattr(repository, "_connect", lambda *_args, **_kwargs: fake_connection)

    assert repository._query(
        "PPM",
        "SELECT 1 WHERE name = %s AND object_id = %s",
        ["GetInspItemsCd", 1703182059],
        tool_name="get_dependency_closure",
        profile=profile,
    ) == []

    assert fake_connection.closed is True
    assert fake_connection.cursor_instance is not None
    string_param, int_param = fake_connection.cursor_instance.execute_params
    assert isinstance(string_param, tds_base.Param)
    assert isinstance(string_param.type, tds_types.NVarCharType)
    assert string_param.value == "GetInspItemsCd"
    assert int_param == 1703182059
