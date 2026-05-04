from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    input_schema: dict[str, Any]
    read_only: bool = True
    active: bool = True


def repo_root() -> Path:
    return Path(__file__).resolve().parents[3]


def catalog_path() -> Path:
    return repo_root() / "spec" / "mcp" / "mssql_metadata_tool_catalog.yaml"


def load_catalog_payload(path: Path | None = None) -> dict[str, Any]:
    source = path or catalog_path()
    return yaml.safe_load(source.read_text(encoding="utf-8")) or {}


def load_tool_catalog(path: Path | None = None) -> list[ToolSpec]:
    payload = load_catalog_payload(path)
    if payload.get("service") != "mssqlMetadata":
        raise ValueError("MSSQL metadata tool catalog must declare service=mssqlMetadata.")
    if payload.get("readOnly") is not True:
        raise ValueError("MSSQL metadata tool catalog must be read-only.")

    seen: set[str] = set()
    tools: list[ToolSpec] = []
    for record in payload.get("tools", []):
        name = str(record.get("name", "")).strip()
        if not name:
            raise ValueError("Each MCP tool requires a non-empty name.")
        if name in seen:
            raise ValueError(f"Duplicate MCP tool name: {name}")
        seen.add(name)

        input_schema = record.get("input")
        if not isinstance(input_schema, dict):
            raise ValueError(f"MCP tool {name} requires an object input schema.")

        tools.append(
            ToolSpec(
                name=name,
                description=str(record.get("description", "")).strip(),
                input_schema=input_schema,
                read_only=bool(record.get("readOnly", payload.get("readOnly", True))),
                active=bool(record.get("active", True)),
            )
        )

    if not tools:
        raise ValueError("MSSQL metadata tool catalog must declare at least one tool.")
    return tools


TOOL_CATALOG = load_tool_catalog()
TOOL_BY_NAME = {tool.name: tool for tool in TOOL_CATALOG}
