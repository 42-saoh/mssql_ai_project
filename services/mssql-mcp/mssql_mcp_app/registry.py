from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from pydantic import ValidationError

from mssql_mcp_app.backpressure import metadata_admission
from mssql_mcp_app.catalog import TOOL_CATALOG, ToolSpec
from mssql_mcp_app.errors import (
    INVALID_ARGUMENTS,
    INTERNAL_ERROR,
    PROFILE_NOT_FOUND,
    UNKNOWN_TOOL,
    MetadataToolError,
)
from mssql_mcp_app.guardrails import enforce_read_only_arguments
from mssql_mcp_app.profiles import DbProfile
from mssql_mcp_app.repositories import MetadataRepository
from mssql_mcp_app.schema_validation import validate_tool_arguments
from mssql_mcp_app.tool_cache import (
    cache_key_for_metadata_tool,
    metadata_tool_result_cache,
    repository_mode,
    stable_json_hash,
)
from mssql_mcp_app.tool_models import ToolErrorPayload, ToolInvokeRequest, ToolResponse


class ToolRegistry:
    def __init__(
        self,
        *,
        catalog: list[ToolSpec],
        repository: MetadataRepository,
        profiles: list[DbProfile],
    ) -> None:
        self.catalog = catalog
        self.repository = repository
        self.profiles = profiles
        self._tools = {tool.name: tool for tool in catalog}
        self._profile_ids = {profile.id for profile in profiles}
        self._catalog_version = stable_json_hash(
            [
                {
                    "name": tool.name,
                    "active": tool.active,
                    "readOnly": tool.read_only,
                    "inputSchema": tool.input_schema,
                }
                for tool in catalog
            ]
        )[:16]
        self.last_cache_event = None

    def invoke_payload(self, tool_name: str, payload: dict[str, Any] | None) -> dict[str, Any]:
        self.last_cache_event = None
        tool = self._get_tool(tool_name)
        request = self._parse_request(tool_name, payload)

        raw_arguments = request.arguments
        enforce_read_only_arguments(
            raw_arguments,
            allowed_argument_paths=_allowed_guardrail_paths(tool.name),
        )
        arguments = validate_tool_arguments(tool, raw_arguments)
        profile = self._validate_profile(tool.name, arguments)

        cache_key = cache_key_for_metadata_tool(
            tool_name=tool.name,
            arguments=arguments,
            db_profile_id=profile.id,
            source_database=profile.database,
            repository_mode=repository_mode(self.repository),
            catalog_version=self._catalog_version,
        )
        cache = metadata_tool_result_cache()
        cached, cache_event = cache.get(cache_key)
        self.last_cache_event = cache_event
        if cached is not None:
            return cached

        with metadata_admission(tool_name=tool.name, db_profile_id=profile.id):
            result = self.repository.invoke(tool.name, arguments)
        data = self._standardize_success_data(tool.name, arguments, result.data)
        response = ToolResponse(
            ok=True,
            toolName=tool.name,
            dbProfileId=arguments["dbProfileId"],
            snapshotId=result.snapshot_id,
            collectedAt=result.collected_at,
            evidenceRefs=result.evidence_refs,
            data=data,
        ).model_dump(exclude_none=True)
        self.last_cache_event = cache.put(cache_key, response)
        return response

    def _get_tool(self, tool_name: str) -> ToolSpec:
        tool = self._tools.get(tool_name)
        if tool is None:
            raise MetadataToolError(
                UNKNOWN_TOOL,
                "Requested MCP tool is not declared in the metadata catalog.",
                {"toolName": tool_name},
            )
        if not tool.read_only or not tool.active:
            raise MetadataToolError(
                INTERNAL_ERROR,
                "Requested MCP tool is not active as a read-only metadata tool.",
                {"toolName": tool_name, "readOnly": tool.read_only, "active": tool.active},
            )
        return tool

    @staticmethod
    def _parse_request(tool_name: str, payload: dict[str, Any] | None) -> ToolInvokeRequest:
        try:
            return ToolInvokeRequest.model_validate(payload or {})
        except ValidationError as exc:
            raise MetadataToolError(
                "INVALID_ARGUMENTS",
                "Tool invocation request must contain only an arguments object.",
                {"toolName": tool_name, "validationErrors": _safe_validation_errors(exc)},
            ) from exc

    def _validate_profile(self, tool_name: str, arguments: dict[str, Any]) -> DbProfile:
        profile_id = arguments.get("dbProfileId")
        profile = self._profile_by_id(profile_id)
        if profile is None:
            raise MetadataToolError(
                PROFILE_NOT_FOUND,
                "Unknown dbProfileId. Use one of the public profile registry ids.",
                {"dbProfileId": profile_id, "availableProfileIds": sorted(self._profile_ids)},
            )
        if tool_name == "check_database_exists":
            self._validate_database_probe_boundary(profile, arguments)
        return profile

    def _profile_by_id(self, profile_id: Any) -> DbProfile | None:
        for profile in self.profiles:
            if profile.id == profile_id:
                return profile
        return None

    @staticmethod
    def _validate_database_probe_boundary(
        profile: DbProfile,
        arguments: dict[str, Any],
    ) -> None:
        requested_database = arguments.get("databaseName")
        if not requested_database:
            return
        if profile.id == "master":
            return
        if str(requested_database).lower() == profile.database.lower():
            return
        raise MetadataToolError(
            INVALID_ARGUMENTS,
            "check_database_exists may only probe another database from the master profile.",
            {
                "dbProfileId": profile.id,
                "requestedDatabase": requested_database,
                "expectedDatabase": profile.database,
            },
        )

    def _standardize_success_data(
        self,
        tool_name: str,
        arguments: dict[str, Any],
        data: dict[str, Any],
    ) -> dict[str, Any]:
        standardized = dict(data)
        source_profile = str(arguments["dbProfileId"])
        source_database = self._database_for_profile(source_profile)
        caveats = _stable_caveats(standardized)

        standardized["sourceProfile"] = source_profile
        standardized["sourceDatabase"] = source_database
        standardized["objectIdentity"] = _object_identity_for_tool(
            tool_name,
            arguments,
            source_database=source_database,
        )
        standardized["caveats"] = caveats
        standardized["reviewRequired"] = bool(
            standardized.get("reviewRequired", False) or caveats
        )
        return standardized

    def _database_for_profile(self, profile_id: str) -> str:
        for profile in self.profiles:
            if profile.id == profile_id:
                return profile.database
        return profile_id


def build_tool_registry(
    *,
    repository: MetadataRepository,
    profiles: list[DbProfile],
    catalog: list[ToolSpec] | None = None,
) -> ToolRegistry:
    return ToolRegistry(catalog=catalog or TOOL_CATALOG, repository=repository, profiles=profiles)


def _allowed_guardrail_paths(tool_name: str) -> set[str]:
    if tool_name == "search_metadata_objects":
        return {"arguments.query"}
    return set()


def error_response(
    tool_name: str,
    error: MetadataToolError,
    *,
    arguments: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = ToolResponse(
        ok=False,
        toolName=tool_name,
        dbProfileId=_argument_value(arguments, "dbProfileId"),
        snapshotId=_argument_value(arguments, "snapshotId"),
        collectedAt=_utc_now(),
        evidenceRefs=[],
        error=ToolErrorPayload(
            code=error.code,
            message=error.message,
            details=error.details or None,
        ),
    )
    return payload.model_dump(exclude_none=True)


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _argument_value(arguments: dict[str, Any] | None, key: str) -> Any:
    if not isinstance(arguments, dict):
        return None
    value = arguments.get(key)
    if isinstance(value, str) and value.strip():
        return value.strip()
    return value


def _safe_validation_errors(exc: ValidationError) -> list[dict[str, Any]]:
    return [
        {
            "loc": list(error.get("loc", [])),
            "msg": error.get("msg"),
            "type": error.get("type"),
        }
        for error in exc.errors()
    ]


def _object_identity_for_tool(
    tool_name: str,
    arguments: dict[str, Any],
    *,
    source_database: str,
) -> dict[str, Any]:
    if tool_name == "check_database_exists":
        return _identity(
            source_database=arguments.get("databaseName") or source_database,
            object_type="DATABASE",
            name=arguments.get("databaseName") or source_database,
        )
    if tool_name == "list_procedures":
        return _identity(
            source_database=source_database,
            object_type="CATALOG",
            schema=arguments.get("schema"),
            name="procedures",
        )
    if tool_name == "list_tables":
        return _identity(
            source_database=source_database,
            object_type="CATALOG",
            schema=arguments.get("schema"),
            name="tables",
        )
    if tool_name == "list_views":
        return _identity(
            source_database=source_database,
            object_type="CATALOG",
            schema=arguments.get("schema"),
            name="views",
        )
    if tool_name == "list_functions":
        return _identity(
            source_database=source_database,
            object_type="CATALOG",
            schema=arguments.get("schema"),
            name="functions",
        )
    if tool_name.startswith("get_procedure_"):
        return _identity(
            source_database=source_database,
            object_type="PROCEDURE",
            schema=arguments.get("schema"),
            name=arguments.get("procedureName"),
        )
    if tool_name in {"get_table_schema", "get_table_constraints", "get_table_indexes"}:
        return _identity(
            source_database=source_database,
            object_type="TABLE",
            schema=arguments.get("schema"),
            name=arguments.get("tableName"),
        )
    if tool_name == "get_extended_properties":
        return _identity(
            source_database=source_database,
            object_type=arguments.get("objectType") or "OBJECT",
            schema=arguments.get("schema"),
            name=arguments.get("objectName"),
        )
    if tool_name == "get_view_definition":
        return _identity(
            source_database=source_database,
            object_type="VIEW",
            schema=arguments.get("schema"),
            name=arguments.get("viewName"),
        )
    if tool_name == "get_function_definition":
        return _identity(
            source_database=source_database,
            object_type="FUNCTION",
            schema=arguments.get("schema"),
            name=arguments.get("functionName"),
        )
    if tool_name == "get_related_db_objects":
        return _identity(
            source_database=source_database,
            object_type=arguments.get("objectType") or "OBJECT",
            schema=arguments.get("schema"),
            name=arguments.get("objectName"),
        )
    if tool_name == "get_dependency_closure":
        return _identity(
            source_database=source_database,
            object_type=arguments.get("objectType") or "OBJECT",
            schema=arguments.get("schema"),
            name=arguments.get("objectName"),
        )
    if tool_name == "resolve_dependency_reference":
        source_object = arguments.get("sourceObject") or {}
        return _identity(
            source_database=source_database,
            object_type="DEPENDENCY_REFERENCE",
            schema=source_object.get("schema"),
            name=arguments.get("referencedName"),
        )
    if tool_name in {
        "search_tables",
        "search_columns",
        "find_similar_tables",
        "search_metadata_objects",
    }:
        return _identity(
            source_database=source_database,
            object_type="CATALOG",
            name=tool_name,
        )
    return _identity(source_database=source_database, object_type="CATALOG", name=tool_name)


def _identity(
    *,
    source_database: str,
    object_type: str,
    name: Any,
    schema: Any | None = None,
) -> dict[str, Any]:
    return {
        "database": source_database,
        "schema": schema,
        "name": name,
        "objectType": object_type,
    }


def _stable_caveats(data: dict[str, Any]) -> list[str]:
    caveats = [str(item) for item in data.get("caveats", []) if str(item)]

    if data.get("hasDefinitionAccess") is False:
        caveats.append("definition_unavailable")

    dependencies = data.get("dependencies")
    if isinstance(dependencies, list) and _dependencies_need_review(dependencies):
        caveats.append("DEPENDENCY_METADATA_INCOMPLETE")

    if data.get("descriptionStatus") == "REVIEW_REQUIRED":
        caveats.append("description_review_required")

    return list(dict.fromkeys(caveats))


def _dependencies_need_review(dependencies: list[Any]) -> bool:
    for dependency in dependencies:
        if not isinstance(dependency, dict):
            continue
        if dependency.get("reviewStatus") == "REVIEW_REQUIRED":
            return True
        if dependency.get("resolutionStatus") == "REVIEW_REQUIRED":
            return True
        if dependency.get("isAmbiguous") is True:
            return True
        if dependency.get("objectType") in {None, "", "UNKNOWN"}:
            return True
        if not dependency.get("name"):
            return True
    return False
