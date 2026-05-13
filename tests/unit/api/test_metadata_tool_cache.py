from __future__ import annotations

from typing import Any

import pytest
from api_app.ai_tool_orchestrator import _deterministic_fact, _sanitize_tool_payload
from mssql_mcp_app.catalog import TOOL_CATALOG
from mssql_mcp_app.profiles import DbProfile
from mssql_mcp_app.registry import build_tool_registry
from mssql_mcp_app.repositories import MetadataToolResult
from mssql_mcp_app.tool_cache import (
    MetadataToolResultCache,
    clear_metadata_tool_result_cache,
    stable_json_hash,
)


class CountingMetadataRepository:
    def __init__(self, data_by_tool: dict[str, dict[str, Any]]) -> None:
        self.data_by_tool = data_by_tool
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def invoke(self, tool_name: str, arguments: dict[str, Any]) -> MetadataToolResult:
        self.calls.append((tool_name, dict(arguments)))
        return MetadataToolResult(
            snapshot_id=f"snapshot-{len(self.calls)}",
            collected_at=f"2026-05-12T00:00:0{len(self.calls)}Z",
            evidence_refs=[
                {
                    "id": "fixture-cache",
                    "source": "fixture",
                    "path": "#/tables/0",
                    "objectType": "TABLE",
                    "objectName": "dbo.TB_ORDER",
                }
            ],
            data=dict(self.data_by_tool[tool_name]),
        )


@pytest.fixture(autouse=True)
def cache_env(monkeypatch: pytest.MonkeyPatch) -> None:
    clear_metadata_tool_result_cache()
    monkeypatch.setenv("MCP_TOOL_RESULT_CACHE_ENABLED", "1")
    monkeypatch.setenv("MCP_TOOL_RESULT_CACHE_TTL_SECONDS", "300")
    monkeypatch.setenv("MCP_TOOL_RESULT_CACHE_MAX_ENTRIES", "1024")
    monkeypatch.setenv("MSSQL_METADATA_MAX_CONCURRENCY", "4")
    monkeypatch.setenv("BACKPRESSURE_WAIT_MS", "0")


def _tool(name: str):
    return [tool for tool in TOOL_CATALOG if tool.name == name]


def _profiles() -> list[DbProfile]:
    return [
        DbProfile(
            id="master",
            label="Master",
            database="master",
            purpose="fixture",
            read_only=True,
            is_default=True,
        )
    ]


def test_metadata_tool_result_cache_hits_successful_read_only_payloads() -> None:
    repository = CountingMetadataRepository(
        {
            "get_table_schema": {
                "schema": "dbo",
                "tableName": "TB_ORDER",
                "columns": [{"name": "ORDER_ID", "dataType": "int"}],
            }
        }
    )
    registry = build_tool_registry(
        repository=repository,
        profiles=_profiles(),
        catalog=_tool("get_table_schema"),
    )
    arguments = {"dbProfileId": "master", "schema": "dbo", "tableName": "TB_ORDER"}

    first = registry.invoke_payload("get_table_schema", {"arguments": arguments})
    first_event = registry.last_cache_event
    second = registry.invoke_payload("get_table_schema", {"arguments": dict(arguments)})
    second_event = registry.last_cache_event

    assert len(repository.calls) == 1
    assert first["snapshotId"] == second["snapshotId"] == "snapshot-1"
    assert first_event.status == "MISS"
    assert second_event.status == "HIT"
    assert second_event.cache_key_hash
    assert isinstance(second_event.cache_age_ms, int)


def test_metadata_tool_cache_can_be_disabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MCP_TOOL_RESULT_CACHE_ENABLED", "0")
    repository = CountingMetadataRepository(
        {
            "get_table_schema": {
                "schema": "dbo",
                "tableName": "TB_ORDER",
                "columns": [],
            }
        }
    )
    registry = build_tool_registry(
        repository=repository,
        profiles=_profiles(),
        catalog=_tool("get_table_schema"),
    )
    arguments = {"dbProfileId": "master", "schema": "dbo", "tableName": "TB_ORDER"}

    registry.invoke_payload("get_table_schema", {"arguments": arguments})
    registry.invoke_payload("get_table_schema", {"arguments": arguments})

    assert len(repository.calls) == 2
    assert registry.last_cache_event.status == "DISABLED"


def test_metadata_tool_cache_bypasses_raw_definition_payloads() -> None:
    repository = CountingMetadataRepository(
        {
            "get_procedure_definition": {
                "schema": "dbo",
                "procedureName": "usp_Leak",
                "definition": "CREATE PROCEDURE dbo.usp_Leak AS SELECT 1",
                "definitionHash": "abc",
                "definitionLength": 42,
            }
        }
    )
    registry = build_tool_registry(
        repository=repository,
        profiles=_profiles(),
        catalog=_tool("get_procedure_definition"),
    )
    arguments = {"dbProfileId": "master", "schema": "dbo", "procedureName": "usp_Leak"}

    registry.invoke_payload("get_procedure_definition", {"arguments": arguments})
    registry.invoke_payload("get_procedure_definition", {"arguments": arguments})

    assert len(repository.calls) == 2
    assert registry.last_cache_event.status == "BYPASS"


def test_metadata_tool_cache_ttl_and_lru(monkeypatch: pytest.MonkeyPatch) -> None:
    now = 10.0
    monkeypatch.setenv("MCP_TOOL_RESULT_CACHE_TTL_SECONDS", "5")
    monkeypatch.setenv("MCP_TOOL_RESULT_CACHE_MAX_ENTRIES", "1")
    monkeypatch.setattr("mssql_mcp_app.tool_cache.time.monotonic", lambda: now)
    cache = MetadataToolResultCache()

    assert cache.get("one")[1].status == "MISS"
    assert cache.put("one", {"ok": True, "data": {"value": 1}}).status == "MISS"
    assert cache.put("two", {"ok": True, "data": {"value": 2}}).status == "MISS"
    assert cache.get("one")[1].status == "MISS"
    assert cache.get("two")[1].status == "HIT"

    now = 20.0
    assert cache.get("two")[1].status == "MISS"


def test_mcp_fact_id_ignores_volatile_snapshot_envelope() -> None:
    payload_one = _sanitize_tool_payload(
        {
            "ok": True,
            "toolName": "get_table_schema",
            "snapshotId": "snapshot-1",
            "collectedAt": "2026-05-12T00:00:00Z",
            "evidenceRefs": [{"snapshotId": "snapshot-1", "objectName": "dbo.TB_ORDER"}],
            "data": {"schema": "dbo", "tableName": "TB_ORDER", "columns": [{"name": "ID"}]},
        }
    )
    payload_two = {
        **payload_one,
        "snapshotId": "snapshot-2",
        "collectedAt": "2026-05-12T00:01:00Z",
        "evidenceRefs": [{"snapshotId": "snapshot-2", "objectName": "dbo.TB_ORDER"}],
    }
    argument_hash = stable_json_hash(
        {"dbProfileId": "master", "schema": "dbo", "tableName": "TB_ORDER"}
    )

    fact_one = _deterministic_fact(
        "get_table_schema",
        payload_one,
        argument_hash=argument_hash,
    )
    fact_two = _deterministic_fact(
        "get_table_schema",
        payload_two,
        argument_hash=argument_hash,
    )

    assert fact_one["id"] == fact_two["id"]
    assert fact_one["contentHash"] == fact_two["contentHash"]
