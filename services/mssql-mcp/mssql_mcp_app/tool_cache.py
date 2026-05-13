from __future__ import annotations

import copy
import hashlib
import itertools
import json
import os
import time
import weakref
from collections import OrderedDict
from dataclasses import dataclass
from threading import Lock
from typing import Any


_CUSTOM_REPOSITORY_IDS: weakref.WeakKeyDictionary[object, int] = weakref.WeakKeyDictionary()
_CUSTOM_REPOSITORY_ID_COUNTER = itertools.count(1)
_CUSTOM_REPOSITORY_ID_LOCK = Lock()


@dataclass(frozen=True)
class MetadataToolCacheEvent:
    status: str
    cache_key_hash: str | None = None
    cache_age_ms: int | None = None

    def summary(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"cacheStatus": self.status}
        if self.cache_key_hash:
            payload["cacheKeyHash"] = self.cache_key_hash
        if self.cache_age_ms is not None:
            payload["cacheAgeMs"] = self.cache_age_ms
        return payload


@dataclass(frozen=True)
class MetadataToolCacheSettings:
    enabled: bool = True
    ttl_seconds: int = 300
    max_entries: int = 1024


@dataclass(frozen=True)
class _CacheEntry:
    stored_at: float
    payload: dict[str, Any]


def _env_flag(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or not value.strip():
        return default
    try:
        return int(value)
    except ValueError:
        return default


def load_cache_settings() -> MetadataToolCacheSettings:
    return MetadataToolCacheSettings(
        enabled=_env_flag("MCP_TOOL_RESULT_CACHE_ENABLED", True),
        ttl_seconds=max(_env_int("MCP_TOOL_RESULT_CACHE_TTL_SECONDS", 300), 0),
        max_entries=max(_env_int("MCP_TOOL_RESULT_CACHE_MAX_ENTRIES", 1024), 0),
    )


def stable_json_hash(value: Any) -> str:
    normalized = json.dumps(
        value,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
        default=str,
    )
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def cache_key_for_metadata_tool(
    *,
    tool_name: str,
    arguments: dict[str, Any],
    db_profile_id: str,
    source_database: str,
    repository_mode: str,
    catalog_version: str,
) -> str:
    return stable_json_hash(
        {
            "toolName": tool_name,
            "arguments": _normalize_value(arguments),
            "dbProfileId": db_profile_id,
            "sourceDatabase": source_database,
            "repositoryMode": repository_mode,
            "catalogVersion": catalog_version,
        }
    )


def repository_mode(repository: object) -> str:
    class_name = repository.__class__.__name__
    if class_name == "LiveMetadataRepository":
        return "live"
    fixture_path = getattr(repository, "fixture_path", None)
    if fixture_path:
        return f"fixture:{class_name}:{fixture_path}"
    return f"fixture:{class_name}:{_custom_repository_id(repository)}"


def _custom_repository_id(repository: object) -> int:
    with _CUSTOM_REPOSITORY_ID_LOCK:
        assigned = next(_CUSTOM_REPOSITORY_ID_COUNTER)
        try:
            existing = _CUSTOM_REPOSITORY_IDS.get(repository)
            if existing is not None:
                return existing
            _CUSTOM_REPOSITORY_IDS[repository] = assigned
        except TypeError:
            existing_attr = getattr(repository, "_mcp_cache_identity", None)
            if isinstance(existing_attr, int):
                return existing_attr
            try:
                setattr(repository, "_mcp_cache_identity", assigned)
            except Exception:
                pass
        return assigned


def payload_is_cacheable(payload: dict[str, Any]) -> bool:
    return bool(payload.get("ok") is True) and not _contains_forbidden_cache_value(payload)


class MetadataToolResultCache:
    def __init__(self) -> None:
        self._entries: OrderedDict[str, _CacheEntry] = OrderedDict()
        self._lock = Lock()

    def clear(self) -> None:
        with self._lock:
            self._entries.clear()

    def get(self, cache_key: str) -> tuple[dict[str, Any] | None, MetadataToolCacheEvent]:
        settings = load_cache_settings()
        key_hash = stable_json_hash(cache_key)[:16]
        if not settings.enabled or settings.max_entries <= 0:
            return None, MetadataToolCacheEvent("DISABLED", key_hash)

        now = time.monotonic()
        with self._lock:
            entry = self._entries.get(cache_key)
            if entry is None:
                return None, MetadataToolCacheEvent("MISS", key_hash)
            age_ms = int((now - entry.stored_at) * 1000)
            if settings.ttl_seconds <= 0 or now - entry.stored_at > settings.ttl_seconds:
                self._entries.pop(cache_key, None)
                return None, MetadataToolCacheEvent("MISS", key_hash)
            self._entries.move_to_end(cache_key)
            return copy.deepcopy(entry.payload), MetadataToolCacheEvent("HIT", key_hash, age_ms)

    def put(self, cache_key: str, payload: dict[str, Any]) -> MetadataToolCacheEvent:
        settings = load_cache_settings()
        key_hash = stable_json_hash(cache_key)[:16]
        if not settings.enabled or settings.max_entries <= 0:
            return MetadataToolCacheEvent("DISABLED", key_hash)
        if not payload_is_cacheable(payload):
            return MetadataToolCacheEvent("BYPASS", key_hash)

        with self._lock:
            self._entries[cache_key] = _CacheEntry(
                stored_at=time.monotonic(),
                payload=copy.deepcopy(payload),
            )
            self._entries.move_to_end(cache_key)
            while len(self._entries) > settings.max_entries:
                self._entries.popitem(last=False)
        return MetadataToolCacheEvent("MISS", key_hash)


_CACHE = MetadataToolResultCache()


def metadata_tool_result_cache() -> MetadataToolResultCache:
    return _CACHE


def clear_metadata_tool_result_cache() -> None:
    _CACHE.clear()


def _normalize_value(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _normalize_value(value[key])
            for key in sorted(value, key=lambda item: str(item))
        }
    if isinstance(value, list):
        return [_normalize_value(item) for item in value]
    return value


def _contains_forbidden_cache_value(value: Any, *, key: str = "") -> bool:
    normalized_key = key.replace("-", "_").lower()
    if normalized_key in {
        "raw_definition",
        "rawsql",
        "raw_sql",
        "sqltext",
        "sql_text",
        "rowdata",
        "row_data",
        "rows",
        "records",
        "password",
        "secret",
        "token",
        "apikey",
        "api_key",
        "connectionstring",
        "connection_string",
        "credential",
    }:
        return True
    if isinstance(value, dict):
        return any(
            _contains_forbidden_cache_value(item, key=str(item_key))
            for item_key, item in value.items()
        )
    if isinstance(value, list):
        return any(_contains_forbidden_cache_value(item) for item in value)
    if normalized_key == "definition" and isinstance(value, str):
        return _looks_like_raw_sql_definition(value)
    if isinstance(value, str) and normalized_key in {"sql", "statement", "command"}:
        return _looks_like_raw_sql_definition(value)
    return False


def _looks_like_raw_sql_definition(value: str) -> bool:
    text = value.strip().lower()
    if not text:
        return False
    return any(
        marker in text
        for marker in (
            "create procedure",
            "alter procedure",
            "create proc",
            "alter proc",
            "create view",
            "alter view",
            "create function",
            "alter function",
            "select ",
            "insert ",
            "update ",
            "delete ",
            "merge ",
            "exec ",
            "execute ",
        )
    )
