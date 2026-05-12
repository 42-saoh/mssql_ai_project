from __future__ import annotations

from typing import Any

from mssql_mcp_app.catalog import ToolSpec
from mssql_mcp_app.errors import INVALID_ARGUMENTS, MetadataToolError


def validate_tool_arguments(tool: ToolSpec, arguments: dict[str, Any]) -> dict[str, Any]:
    schema = tool.input_schema
    if schema.get("type") != "object":
        raise MetadataToolError(
            INVALID_ARGUMENTS,
            "Tool input schema must be an object.",
            {"toolName": tool.name},
        )
    return _validate_object(schema, arguments, path="arguments", required=True)


def _validate_object(
    schema: dict[str, Any],
    value: Any,
    *,
    path: str,
    required: bool,
) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise _invalid(path, "must be an object")

    properties = schema.get("properties", {})
    if not isinstance(properties, dict):
        raise _invalid(path, "schema properties must be an object")

    required_keys = set(schema.get("required", []))
    unknown_keys = set(value) - set(properties)
    if unknown_keys:
        raise _invalid(path, f"contains unsupported arguments: {sorted(unknown_keys)}")

    normalized = dict(value)
    for key, property_schema in properties.items():
        if (
            key not in normalized
            and isinstance(property_schema, dict)
            and "default" in property_schema
        ):
            normalized[key] = property_schema["default"]

    missing = [
        key
        for key in required_keys
        if key not in normalized or normalized[key] is None or normalized[key] == ""
    ]
    if missing:
        raise _invalid(path, f"missing required arguments: {missing}")

    for key, nested_value in list(normalized.items()):
        property_schema = properties[key]
        normalized[key] = _validate_value(
            property_schema,
            nested_value,
            path=f"{path}.{key}",
            required=key in required_keys,
        )

    return normalized


def _validate_value(
    schema: dict[str, Any],
    value: Any,
    *,
    path: str,
    required: bool,
) -> Any:
    expected_type = schema.get("type")
    if expected_type == "string":
        if not isinstance(value, str):
            raise _invalid(path, "must be a string")
        normalized = value.strip()
        if required and not normalized:
            raise _invalid(path, "must not be empty")
        _validate_enum(schema, normalized, path)
        return normalized

    if expected_type == "integer":
        if not isinstance(value, int) or isinstance(value, bool):
            raise _invalid(path, "must be an integer")
        maximum = schema.get("maximum")
        if maximum is not None and value > maximum:
            raise _invalid(path, f"must be less than or equal to {maximum}")
        _validate_enum(schema, value, path)
        return value

    if expected_type == "boolean":
        if not isinstance(value, bool):
            raise _invalid(path, "must be a boolean")
        return value

    if expected_type == "array":
        if not isinstance(value, list):
            raise _invalid(path, "must be an array")
        item_schema = schema.get("items", {})
        if not isinstance(item_schema, dict):
            raise _invalid(path, "schema items must be an object")
        return [
            _validate_value(item_schema, item, path=f"{path}[{index}]", required=True)
            for index, item in enumerate(value)
        ]

    if expected_type == "object":
        return _validate_object(schema, value, path=path, required=required)

    raise _invalid(path, f"has unsupported schema type: {expected_type}")


def _validate_enum(schema: dict[str, Any], value: Any, path: str) -> None:
    enum_values = schema.get("enum")
    if enum_values is not None and value not in enum_values:
        raise _invalid(path, f"must be one of {enum_values}")


def _invalid(path: str, reason: str) -> MetadataToolError:
    return MetadataToolError(INVALID_ARGUMENTS, "Invalid tool arguments.", {path: reason})
