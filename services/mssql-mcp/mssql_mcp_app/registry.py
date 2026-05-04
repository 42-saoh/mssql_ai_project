from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from mssql_mcp_app.catalog import TOOL_CATALOG, ToolSpec
from mssql_mcp_app.errors import (
    INTERNAL_ERROR,
    PROFILE_NOT_FOUND,
    UNKNOWN_TOOL,
    MetadataToolError,
)
from mssql_mcp_app.guardrails import enforce_read_only_arguments
from mssql_mcp_app.profiles import DbProfile
from mssql_mcp_app.repositories import MetadataRepository
from mssql_mcp_app.schema_validation import validate_tool_arguments
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

    def invoke_payload(self, tool_name: str, payload: dict[str, Any] | None) -> dict[str, Any]:
        tool = self._get_tool(tool_name)
        request = self._parse_request(tool_name, payload)

        raw_arguments = request.arguments
        enforce_read_only_arguments(raw_arguments)
        arguments = validate_tool_arguments(tool, raw_arguments)
        self._validate_profile(arguments)

        result = self.repository.invoke(tool.name, arguments)
        return ToolResponse(
            ok=True,
            toolName=tool.name,
            dbProfileId=arguments["dbProfileId"],
            snapshotId=result.snapshot_id,
            collectedAt=result.collected_at,
            evidenceRefs=result.evidence_refs,
            data=result.data,
        ).model_dump(exclude_none=True)

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

    def _validate_profile(self, arguments: dict[str, Any]) -> None:
        profile_id = arguments.get("dbProfileId")
        if profile_id not in self._profile_ids:
            raise MetadataToolError(
                PROFILE_NOT_FOUND,
                "Unknown dbProfileId. Use one of the public profile registry ids.",
                {"dbProfileId": profile_id, "availableProfileIds": sorted(self._profile_ids)},
            )


def build_tool_registry(
    *,
    repository: MetadataRepository,
    profiles: list[DbProfile],
    catalog: list[ToolSpec] | None = None,
) -> ToolRegistry:
    return ToolRegistry(catalog=catalog or TOOL_CATALOG, repository=repository, profiles=profiles)


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
        evidenceRefs=[],
        error=ToolErrorPayload(
            code=error.code,
            message=error.message,
            details=error.details or None,
        ),
    )
    return payload.model_dump(exclude_none=True)


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
