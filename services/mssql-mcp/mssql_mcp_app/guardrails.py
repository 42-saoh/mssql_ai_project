from __future__ import annotations

from typing import Any

from mssql_mcp_app.errors import MetadataToolError, READ_ONLY_VIOLATION


FORBIDDEN_ARGUMENT_KEYS = frozenset({"sql", "query", "statement", "command", "ddl"})


def enforce_read_only_arguments(value: Any, *, path: str = "arguments") -> None:
    if isinstance(value, dict):
        for key, nested_value in value.items():
            key_text = str(key).strip()
            if key_text.lower() in FORBIDDEN_ARGUMENT_KEYS:
                raise MetadataToolError(
                    READ_ONLY_VIOLATION,
                    "Free-form SQL or write-capable command arguments are not allowed.",
                    {"argumentPath": f"{path}.{key_text}", "argumentKey": key_text},
                )
            enforce_read_only_arguments(nested_value, path=f"{path}.{key_text}")
        return

    if isinstance(value, list):
        for index, nested_value in enumerate(value):
            enforce_read_only_arguments(nested_value, path=f"{path}[{index}]")
