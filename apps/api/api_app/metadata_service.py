from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from mssql_mcp_app.errors import UNKNOWN_TOOL, MetadataToolError
from mssql_mcp_app.profiles import load_db_profiles
from mssql_mcp_app.registry import build_tool_registry
from mssql_mcp_app.repositories import FixtureMetadataRepository, LiveMetadataRepository
from mssql_mcp_app.settings import load_live_metadata_settings

from api_app.live_gate import P21_LIVE_PPM_REQUIRED, p21_live_portal_enabled
from api_app.schemas import (
    EvidenceRef,
    MetadataObjectIdentity,
    MetadataProfile,
    MetadataSearchBlocker,
    MetadataSearchResponse,
    MetadataSearchResult,
    MetadataToolInvokeResponse,
    MetadataToolSummary,
)
from api_app.target_keys import target_key_for_target

METADATA_SEARCH_MCP_TOOL_MISSING = "METADATA_SEARCH_MCP_TOOL_MISSING"
METADATA_TOOL_INVOCATION_NOT_ALLOWED = "METADATA_TOOL_INVOCATION_NOT_ALLOWED"
PPM_MANIFEST_TEMPLATE_ONLY = "PPM_MANIFEST_TEMPLATE_ONLY"
DEPENDENCY_METADATA_INCOMPLETE = "DEPENDENCY_METADATA_INCOMPLETE"

DEFAULT_METADATA_SEARCH_OBJECT_TYPES = ("PROCEDURE", "TABLE", "VIEW", "FUNCTION")
METADATA_SEARCH_TOOL_NAME = "search_metadata_objects"
PUBLIC_METADATA_TOOL_INVOCATION_ALLOWLIST = frozenset(
    {
        "get_dependency_closure",
        "resolve_dependency_reference",
    }
)
METADATA_BLOCKER_MESSAGES = {
    METADATA_SEARCH_MCP_TOOL_MISSING: (
        "Required read-only MSSQL MCP metadata search capability is unavailable."
    ),
    METADATA_TOOL_INVOCATION_NOT_ALLOWED: (
        "Requested metadata tool is not exposed through the public API invocation route."
    ),
    PPM_MANIFEST_TEMPLATE_ONLY: (
        "PPM pilot manifest is template_only, so real object names must not be returned."
    ),
    DEPENDENCY_METADATA_INCOMPLETE: (
        "Dependency metadata is incomplete; treat dependency links as evidence caveats until confirmed."
    ),
    P21_LIVE_PPM_REQUIRED: (
        "P21 live portal gate requires live read-only PPM metadata access; fixture "
        "metadata and PLF fallback are not allowed."
    ),
}


class MetadataSearchDependencyError(RuntimeError):
    def __init__(self, *, code: str, detail: str, status_code: int = 503) -> None:
        super().__init__(detail)
        self.code = code
        self.detail = detail
        self.status_code = status_code


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def list_safe_metadata_profiles() -> tuple[str, list[MetadataProfile]]:
    try:
        from mssql_mcp_app.profiles import get_default_profile, load_db_profiles
        from mssql_mcp_app.settings import load_live_metadata_settings

        settings = load_live_metadata_settings()
        profiles = load_db_profiles(settings, repo_root=repo_root())
        default_profile = get_default_profile(profiles)
        return default_profile.id, [
            MetadataProfile(
                id=profile.id,
                database=profile.database,
                description=f"{profile.label} ({profile.purpose})",
                readOnly=True,
            )
            for profile in profiles
        ]
    except ModuleNotFoundError:
        return _profiles_from_yaml()


def list_safe_metadata_tools() -> list[MetadataToolSummary]:
    try:
        from mssql_mcp_app.catalog import load_tool_catalog

        tools = load_tool_catalog()
        return [
            MetadataToolSummary(
                name=tool.name,
                description=tool.description,
                readOnly=True,
                invokable=tool.name in PUBLIC_METADATA_TOOL_INVOCATION_ALLOWLIST,
            )
            for tool in tools
            if tool.active and tool.read_only
        ]
    except ModuleNotFoundError:
        return _tools_from_yaml()


def invoke_metadata_tool(
    *,
    tool_name: str,
    arguments: dict[str, Any],
) -> MetadataToolInvokeResponse:
    normalized_tool_name = tool_name.strip()
    if normalized_tool_name not in PUBLIC_METADATA_TOOL_INVOCATION_ALLOWLIST:
        raise MetadataSearchDependencyError(
            code=METADATA_TOOL_INVOCATION_NOT_ALLOWED,
            detail=METADATA_BLOCKER_MESSAGES[METADATA_TOOL_INVOCATION_NOT_ALLOWED],
            status_code=403,
        )

    settings = load_live_metadata_settings()
    db_profile_id = str(arguments.get("dbProfileId") or "").strip()
    profiles = (
        load_profiles_for_metadata_request(settings, db_profile_id=db_profile_id)
        if db_profile_id
        else load_db_profiles(settings, repo_root=repo_root())
    )

    if db_profile_id == "ppm" and ppm_manifest_selection_mode() != "live_metadata":
        raise MetadataSearchDependencyError(
            code=PPM_MANIFEST_TEMPLATE_ONLY,
            detail=METADATA_BLOCKER_MESSAGES[PPM_MANIFEST_TEMPLATE_ONLY],
            status_code=503,
        )

    registry = build_tool_registry(
        repository=metadata_search_repository(settings, profiles),
        profiles=profiles,
    )
    payload = registry.invoke_payload(
        normalized_tool_name,
        {"arguments": arguments},
    )
    return MetadataToolInvokeResponse.model_validate(payload)


def search_metadata_objects(
    *,
    db_profile_id: str,
    query: str,
    object_types: tuple[str, ...] = DEFAULT_METADATA_SEARCH_OBJECT_TYPES,
    limit: int = 20,
) -> MetadataSearchResponse:
    normalized_query = query.strip()
    if not normalized_query:
        raise ValueError("metadata search query must not be blank.")
    normalized_types = normalize_metadata_search_object_types(object_types)
    normalized_limit = normalize_metadata_search_limit(limit)

    settings = load_live_metadata_settings()
    profiles = load_profiles_for_metadata_request(settings, db_profile_id=db_profile_id)

    if (
        db_profile_id == "ppm"
        and ppm_manifest_selection_mode() != "live_metadata"
        and not p21_live_portal_enabled()
    ):
        blocker = metadata_search_blocker(PPM_MANIFEST_TEMPLATE_ONLY)
        return MetadataSearchResponse(
            dbProfileId=db_profile_id,
            query=normalized_query,
            objectTypes=list(normalized_types),
            limit=normalized_limit,
            sourceProfile="ppm",
            sourceDatabase="PPM",
            results=[],
            caveats=[PPM_MANIFEST_TEMPLATE_ONLY],
            reviewRequired=True,
            blockers=[blocker],
        )

    registry = build_tool_registry(
        repository=metadata_search_repository(settings, profiles),
        profiles=profiles,
    )

    source_profile = db_profile_id
    source_database = _source_database_for_profile(db_profile_id, profiles)
    try:
        payload = registry.invoke_payload(
            METADATA_SEARCH_TOOL_NAME,
            {
                "arguments": {
                    "dbProfileId": db_profile_id,
                    "query": normalized_query,
                    "objectTypes": list(normalized_types),
                    "limit": normalized_limit,
                }
            },
        )
    except MetadataToolError as exc:
        if exc.code == UNKNOWN_TOOL:
            raise MetadataSearchDependencyError(
                code=METADATA_SEARCH_MCP_TOOL_MISSING,
                detail=METADATA_BLOCKER_MESSAGES[METADATA_SEARCH_MCP_TOOL_MISSING],
                status_code=503,
            ) from exc
        raise

    snapshot_id = str(payload.get("snapshotId") or "") or None
    collected_at = str(payload.get("collectedAt") or "") or None
    data = dict(payload.get("data") or {})
    source_profile = str(data.get("sourceProfile") or source_profile)
    source_database = str(data.get("sourceDatabase") or source_database)
    top_level_caveats = _dedupe(data.get("caveats", []))
    top_level_blockers = _dedupe_blockers(
        _metadata_search_blockers(data.get("blockers", []))
    )
    results = [
        _metadata_search_result(
            item=dict(item),
            source_profile=source_profile,
            source_database=source_database,
            payload_snapshot_id=snapshot_id,
            payload_evidence_refs=payload.get("evidenceRefs", []),
        )
        for item in data.get("results", [])
        if isinstance(item, dict)
    ]
    return MetadataSearchResponse(
        dbProfileId=db_profile_id,
        query=normalized_query,
        objectTypes=list(normalized_types),
        limit=normalized_limit,
        sourceProfile=source_profile,
        sourceDatabase=source_database,
        snapshotId=snapshot_id,
        collectedAt=collected_at,
        results=results,
        caveats=top_level_caveats,
        reviewRequired=bool(
            data.get("reviewRequired") or top_level_caveats or top_level_blockers
        ),
        blockers=top_level_blockers,
    )


def normalize_metadata_search_object_types(object_types: tuple[str, ...]) -> tuple[str, ...]:
    normalized = tuple(dict.fromkeys(str(item).upper() for item in object_types if str(item)))
    if not normalized:
        return DEFAULT_METADATA_SEARCH_OBJECT_TYPES
    unsupported = sorted(set(normalized) - set(DEFAULT_METADATA_SEARCH_OBJECT_TYPES))
    if unsupported:
        raise ValueError(f"Unsupported metadata objectTypes: {', '.join(unsupported)}")
    return normalized


def normalize_metadata_search_limit(limit: int) -> int:
    return min(max(int(limit), 1), 100)


def metadata_search_repository(settings: Any, profiles: list[Any]) -> Any:
    if settings.live_metadata_enabled:
        return LiveMetadataRepository(settings=settings, profiles=profiles)
    return FixtureMetadataRepository()


def load_profiles_for_metadata_request(settings: Any, *, db_profile_id: str) -> list[Any]:
    if not p21_live_portal_enabled():
        return load_db_profiles(settings, repo_root=repo_root())
    if not settings.live_metadata_enabled or db_profile_id != "ppm":
        raise p21_live_ppm_required()
    try:
        profiles = load_db_profiles(settings, repo_root=repo_root())
    except Exception as exc:
        raise p21_live_ppm_required() from exc
    ppm_profile = next((profile for profile in profiles if profile.id == "ppm"), None)
    if ppm_profile is None or str(ppm_profile.database).strip().upper() != "PPM":
        raise p21_live_ppm_required()
    if ppm_manifest_selection_mode() != "live_metadata":
        raise p21_live_ppm_required()
    return profiles


def p21_live_ppm_required() -> MetadataSearchDependencyError:
    return MetadataSearchDependencyError(
        code=P21_LIVE_PPM_REQUIRED,
        detail=METADATA_BLOCKER_MESSAGES[P21_LIVE_PPM_REQUIRED],
        status_code=503,
    )


def _profiles_from_yaml() -> tuple[str, list[MetadataProfile]]:
    path = repo_root() / "config" / "mssql" / "local_docker_profiles.yaml"
    payload: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    default_profile_id = str(payload.get("defaultProfileId", "plf"))
    profiles = [
        MetadataProfile(
            id=str(item["id"]),
            database=str(item["database"]),
            description=f"{item.get('label', item['id'])} ({item.get('purpose', 'metadata')})",
            readOnly=True,
        )
        for item in payload.get("profiles", [])
    ]
    return default_profile_id, profiles


def _tools_from_yaml() -> list[MetadataToolSummary]:
    path = repo_root() / "spec" / "mcp" / "mssql_metadata_tool_catalog.yaml"
    payload: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return [
        MetadataToolSummary(
            name=str(item["name"]),
            description=str(item.get("description", "")),
            readOnly=True,
            invokable=str(item["name"]) in PUBLIC_METADATA_TOOL_INVOCATION_ALLOWLIST,
        )
        for item in payload.get("tools", [])
        if item.get("active", True) and item.get("readOnly", payload.get("readOnly")) is True
    ]


def ppm_manifest_selection_mode() -> str:
    path = repo_root() / "fixtures" / "pilot" / "ppm_object_selection_v1" / "selected_objects.yaml"
    payload: dict[str, Any] = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return str(payload.get("selection_mode", "template_only"))


def metadata_search_blocker(code: str) -> MetadataSearchBlocker:
    return MetadataSearchBlocker(
        code=code,
        message=METADATA_BLOCKER_MESSAGES.get(code, code),
    )


def _source_database_for_profile(db_profile_id: str, profiles: list[Any]) -> str:
    for profile in profiles:
        if profile.id == db_profile_id:
            return str(profile.database)
    return db_profile_id


def _metadata_search_result(
    *,
    item: dict[str, Any],
    source_profile: str,
    source_database: str,
    payload_snapshot_id: str | None,
    payload_evidence_refs: list[dict[str, Any]],
) -> MetadataSearchResult:
    identity = dict(item.get("objectIdentity") or {})
    schema = str(identity.get("schema") or item.get("schema") or "")
    name = str(identity.get("name") or item.get("name") or "")
    object_type = str(identity.get("type") or item.get("objectType") or "")
    result_source_profile = str(item.get("sourceProfile") or source_profile)
    result_source_database = str(item.get("sourceDatabase") or source_database)
    result_snapshot_id = str(item.get("snapshotId") or payload_snapshot_id or "") or None
    caveats = _dedupe(str(value) for value in item.get("caveats", []) if value)
    blockers = _dedupe_blockers(
        [
            *_metadata_search_blockers(item.get("blockers", [])),
            *[
                metadata_search_blocker(caveat)
                for caveat in caveats
                if caveat in METADATA_BLOCKER_MESSAGES
            ],
        ]
    )
    evidence_refs = _metadata_search_evidence_refs(
        item.get("evidenceRefs") or payload_evidence_refs,
        snapshot_id=result_snapshot_id or "",
        default_object_ref=f"{result_source_database}.{schema}.{name}",
    )
    return MetadataSearchResult(
        objectIdentity=MetadataObjectIdentity(
            schema=schema,
            name=name,
            type=object_type,
        ),
        targetKey=target_key_for_target(
            result_source_profile,
            {"type": object_type, "schema": schema, "name": name},
            database=result_source_database,
        ),
        sourceProfile=result_source_profile,
        sourceDatabase=result_source_database,
        snapshotId=result_snapshot_id,
        evidenceRefs=evidence_refs,
        caveats=caveats,
        reviewRequired=bool(item.get("reviewRequired") or caveats or blockers),
        blockers=blockers,
    )


def _metadata_search_evidence_refs(
    evidence_refs: list[dict[str, Any]],
    *,
    snapshot_id: str,
    default_object_ref: str,
) -> list[EvidenceRef]:
    converted: list[EvidenceRef] = []
    seen: set[tuple[str, str]] = set()
    for ref in evidence_refs:
        object_ref = str(ref.get("objectName") or default_object_ref)
        locator = str(ref.get("path") or ref.get("source") or "mssql-mcp")
        dedupe_key = (object_ref, locator)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        converted.append(
            EvidenceRef(
                type="MSSQL_METADATA",
                objectRef=object_ref,
                locator=locator,
                snapshotId=snapshot_id or None,
            )
        )
    return converted


def _metadata_search_blockers(blockers: Any) -> list[MetadataSearchBlocker]:
    converted: list[MetadataSearchBlocker] = []
    for blocker in blockers or []:
        if isinstance(blocker, dict):
            code = str(blocker.get("code") or "")
            message = str(
                blocker.get("message") or METADATA_BLOCKER_MESSAGES.get(code, code)
            )
        else:
            code = str(blocker)
            message = METADATA_BLOCKER_MESSAGES.get(code, code)
        if code:
            converted.append(MetadataSearchBlocker(code=code, message=message))
    return converted


def _dedupe(items: Any) -> list[str]:
    return list(dict.fromkeys(str(item) for item in items if str(item)))


def _dedupe_blockers(blockers: list[MetadataSearchBlocker]) -> list[MetadataSearchBlocker]:
    deduped: dict[str, MetadataSearchBlocker] = {}
    for blocker in blockers:
        deduped.setdefault(blocker.code, blocker)
    return list(deduped.values())
