from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from mssql_mcp_app.catalog import repo_root
from mssql_mcp_app.errors import (
    LIVE_METADATA_UNAVAILABLE,
    OBJECT_NOT_FOUND,
    MetadataToolError,
)


@dataclass(frozen=True)
class MetadataToolResult:
    snapshot_id: str
    collected_at: str
    evidence_refs: list[dict[str, Any]]
    data: dict[str, Any]


class MetadataRepository(Protocol):
    def invoke(self, tool_name: str, arguments: dict[str, Any]) -> MetadataToolResult:
        ...


class FixtureMetadataRepository:
    def __init__(self, fixture_path: Path | None = None) -> None:
        self.fixture_path = (
            fixture_path or repo_root() / "fixtures" / "mcp" / "metadata_snapshot.json"
        )
        self._payload: dict[str, Any] | None = None

    def invoke(self, tool_name: str, arguments: dict[str, Any]) -> MetadataToolResult:
        handler = getattr(self, f"_handle_{tool_name}", None)
        if handler is None:
            raise MetadataToolError(
                OBJECT_NOT_FOUND,
                "Fixture repository has no data handler for the requested tool.",
                {"toolName": tool_name},
            )
        return handler(arguments)

    @property
    def payload(self) -> dict[str, Any]:
        if self._payload is None:
            self._payload = json.loads(self.fixture_path.read_text(encoding="utf-8"))
        return self._payload

    @property
    def snapshot_id(self) -> str:
        return str(self.payload["snapshotId"])

    @property
    def collected_at(self) -> str:
        return str(self.payload["collectedAt"])

    def _result(
        self,
        *,
        data: dict[str, Any],
        evidence_refs: list[dict[str, Any]],
    ) -> MetadataToolResult:
        return MetadataToolResult(
            snapshot_id=self.snapshot_id,
            collected_at=self.collected_at,
            evidence_refs=evidence_refs,
            data=data,
        )

    def _handle_get_procedure_definition(self, arguments: dict[str, Any]) -> MetadataToolResult:
        procedure, index = self._find_procedure(arguments["schema"], arguments["procedureName"])
        definition = str(procedure["definition"])
        evidence = self._evidence(
            "procedure-definition",
            "PROCEDURE",
            procedure["schema"],
            procedure["name"],
            f"/procedures/{index}/definition",
        )
        data = {
            "schema": procedure["schema"],
            "procedureName": procedure["name"],
            "definition": definition,
            "definitionHash": _sha256(definition),
            "isEncrypted": bool(procedure.get("isEncrypted", False)),
            "snapshotMode": arguments.get("snapshotMode", "LATEST"),
        }
        return self._result(data=data, evidence_refs=[evidence])

    def _handle_get_procedure_parameters(self, arguments: dict[str, Any]) -> MetadataToolResult:
        procedure, index = self._find_procedure(arguments["schema"], arguments["procedureName"])
        evidence = self._evidence(
            "procedure-parameters",
            "PROCEDURE",
            procedure["schema"],
            procedure["name"],
            f"/procedures/{index}/parameters",
        )
        data = {
            "schema": procedure["schema"],
            "procedureName": procedure["name"],
            "parameters": procedure.get("parameters", []),
            "snapshotMode": arguments.get("snapshotMode", "LATEST"),
        }
        return self._result(data=data, evidence_refs=[evidence])

    def _handle_get_procedure_dependencies(self, arguments: dict[str, Any]) -> MetadataToolResult:
        procedure, index = self._find_procedure(arguments["schema"], arguments["procedureName"])
        evidence = self._evidence(
            "procedure-dependencies",
            "PROCEDURE",
            procedure["schema"],
            procedure["name"],
            f"/procedures/{index}/dependencies",
        )
        data = {
            "schema": procedure["schema"],
            "procedureName": procedure["name"],
            "dependencies": procedure.get("dependencies", []),
            "snapshotMode": arguments.get("snapshotMode", "LATEST"),
        }
        return self._result(data=data, evidence_refs=[evidence])

    def _handle_get_related_db_objects(self, arguments: dict[str, Any]) -> MetadataToolResult:
        top_k = arguments.get("topK", 20)
        object_type = arguments["objectType"]
        schema = arguments["schema"]
        object_name = arguments["objectName"]

        if object_type == "PROCEDURE":
            source, index = self._find_procedure(schema, object_name)
            related = source.get("dependencies", [])
            evidence_path = f"/procedures/{index}/dependencies"
        elif object_type == "TABLE":
            source, index = self._find_table(schema, object_name)
            related = self._related_for_table(source["schema"], source["name"])
            evidence_path = f"/tables/{index}"
        elif object_type == "VIEW":
            source, index = self._find_view(schema, object_name)
            related = source.get("dependencies", [])
            evidence_path = f"/views/{index}/dependencies"
        else:
            source, index = self._find_function(schema, object_name)
            related = source.get("dependencies", [])
            evidence_path = f"/functions/{index}/dependencies"

        evidence = self._evidence(
            "related-objects",
            object_type,
            schema,
            source["name"],
            evidence_path,
        )
        data = {
            "schema": schema,
            "objectName": source["name"],
            "objectType": object_type,
            "relatedObjects": related[:top_k],
        }
        return self._result(data=data, evidence_refs=[evidence])

    def _handle_get_table_schema(self, arguments: dict[str, Any]) -> MetadataToolResult:
        table, index = self._find_table(arguments["schema"], arguments["tableName"])
        evidence = self._evidence(
            "table-schema",
            "TABLE",
            table["schema"],
            table["name"],
            f"/tables/{index}/columns",
        )
        data = {
            "schema": table["schema"],
            "tableName": table["name"],
            "logicalName": table.get("logicalName"),
            "description": table.get("description"),
            "descriptionStatus": table.get("descriptionStatus", "CONFIRMED"),
            "columns": table.get("columns", []),
        }
        return self._result(data=data, evidence_refs=[evidence])

    def _handle_get_table_constraints(self, arguments: dict[str, Any]) -> MetadataToolResult:
        table, index = self._find_table(arguments["schema"], arguments["tableName"])
        evidence = self._evidence(
            "table-constraints",
            "TABLE",
            table["schema"],
            table["name"],
            f"/tables/{index}/constraints",
        )
        data = {
            "schema": table["schema"],
            "tableName": table["name"],
            "constraints": table.get("constraints", []),
        }
        return self._result(data=data, evidence_refs=[evidence])

    def _handle_get_table_indexes(self, arguments: dict[str, Any]) -> MetadataToolResult:
        table, index = self._find_table(arguments["schema"], arguments["tableName"])
        evidence = self._evidence(
            "table-indexes",
            "TABLE",
            table["schema"],
            table["name"],
            f"/tables/{index}/indexes",
        )
        data = {
            "schema": table["schema"],
            "tableName": table["name"],
            "indexes": table.get("indexes", []),
        }
        return self._result(data=data, evidence_refs=[evidence])

    def _handle_get_extended_properties(self, arguments: dict[str, Any]) -> MetadataToolResult:
        schema = arguments["schema"]
        object_name = arguments["objectName"]
        object_type = arguments.get("objectType")
        source, _index, resolved_type, evidence_path = self._find_object_with_extended_properties(
            schema,
            object_name,
            object_type,
        )
        evidence = self._evidence(
            "extended-properties",
            resolved_type,
            source["schema"],
            source["name"],
            evidence_path,
        )
        data = {
            "schema": source["schema"],
            "objectName": source["name"],
            "objectType": resolved_type,
            "extendedProperties": source.get("extendedProperties", []),
        }
        return self._result(data=data, evidence_refs=[evidence])

    def _handle_get_view_definition(self, arguments: dict[str, Any]) -> MetadataToolResult:
        view, index = self._find_view(arguments["schema"], arguments["viewName"])
        definition = str(view["definition"])
        evidence = self._evidence(
            "view-definition",
            "VIEW",
            view["schema"],
            view["name"],
            f"/views/{index}/definition",
        )
        data = {
            "schema": view["schema"],
            "viewName": view["name"],
            "definition": definition,
            "definitionHash": _sha256(definition),
            "snapshotMode": arguments.get("snapshotMode", "LATEST"),
        }
        return self._result(data=data, evidence_refs=[evidence])

    def _handle_get_function_definition(self, arguments: dict[str, Any]) -> MetadataToolResult:
        function, index = self._find_function(arguments["schema"], arguments["functionName"])
        definition = str(function["definition"])
        evidence = self._evidence(
            "function-definition",
            "FUNCTION",
            function["schema"],
            function["name"],
            f"/functions/{index}/definition",
        )
        data = {
            "schema": function["schema"],
            "functionName": function["name"],
            "definition": definition,
            "definitionHash": _sha256(definition),
            "snapshotMode": arguments.get("snapshotMode", "LATEST"),
        }
        return self._result(data=data, evidence_refs=[evidence])

    def _handle_search_tables(self, arguments: dict[str, Any]) -> MetadataToolResult:
        top_k = arguments.get("topK", 5)
        candidates = []
        for index, table in enumerate(self.payload.get("tables", [])):
            score = _score_table_match(table, arguments)
            if score > 0 or _is_empty_search(arguments):
                candidates.append(_table_candidate(table, score, index))
        candidates.sort(key=lambda item: (-item["score"], item["schema"], item["tableName"]))
        evidence = self._evidence("table-search", "CATALOG", "*", "tables", "/tables")
        data = {
            "criteria": _criteria(arguments),
            "candidates": candidates[:top_k],
        }
        return self._result(data=data, evidence_refs=[evidence])

    def _handle_search_columns(self, arguments: dict[str, Any]) -> MetadataToolResult:
        top_k = arguments.get("topK", 5)
        candidates = []
        for table in self.payload.get("tables", []):
            if arguments.get("tableName") and not _matches(arguments["tableName"], table["name"]):
                continue
            for column in table.get("columns", []):
                score = _score_column_match(column, table, arguments)
                if score > 0 or _is_empty_search(arguments):
                    candidates.append(_column_candidate(table, column, score))
        candidates.sort(
            key=lambda item: (-item["score"], item["schema"], item["tableName"], item["columnName"])
        )
        evidence = self._evidence("column-search", "CATALOG", "*", "columns", "/tables/*/columns")
        data = {
            "criteria": _criteria(arguments),
            "candidates": candidates[:top_k],
        }
        return self._result(data=data, evidence_refs=[evidence])

    def _handle_find_similar_tables(self, arguments: dict[str, Any]) -> MetadataToolResult:
        top_k = arguments.get("topK", 5)
        candidates = []
        for index, table in enumerate(self.payload.get("tables", [])):
            score, matched_columns = _score_similar_table(table, arguments)
            if score > 0:
                candidate = _table_candidate(table, score, index)
                candidate["matchedColumns"] = matched_columns
                candidates.append(candidate)
        candidates.sort(key=lambda item: (-item["score"], item["schema"], item["tableName"]))
        evidence = self._evidence("similar-table-search", "CATALOG", "*", "tables", "/tables")
        data = {
            "criteria": _criteria(arguments),
            "candidates": candidates[:top_k],
        }
        return self._result(data=data, evidence_refs=[evidence])

    def _find_procedure(self, schema: str, name: str) -> tuple[dict[str, Any], int]:
        return self._find_in_collection("procedures", schema, name, "PROCEDURE")

    def _find_table(self, schema: str, name: str) -> tuple[dict[str, Any], int]:
        return self._find_in_collection("tables", schema, name, "TABLE")

    def _find_view(self, schema: str, name: str) -> tuple[dict[str, Any], int]:
        return self._find_in_collection("views", schema, name, "VIEW")

    def _find_function(self, schema: str, name: str) -> tuple[dict[str, Any], int]:
        return self._find_in_collection("functions", schema, name, "FUNCTION")

    def _find_in_collection(
        self,
        collection: str,
        schema: str,
        name: str,
        object_type: str,
    ) -> tuple[dict[str, Any], int]:
        for index, item in enumerate(self.payload.get(collection, [])):
            if _same(item.get("schema"), schema) and _same(item.get("name"), name):
                return item, index
        raise MetadataToolError(
            OBJECT_NOT_FOUND,
            "Requested metadata object was not found in the active repository.",
            {"objectType": object_type, "schema": schema, "name": name},
        )

    def _find_object_with_extended_properties(
        self,
        schema: str,
        name: str,
        object_type: str | None,
    ) -> tuple[dict[str, Any], int, str, str]:
        if object_type == "COLUMN":
            source, table_index, column_index = self._find_column(schema, name)
            return source, column_index, "COLUMN", f"/tables/{table_index}/columns/{column_index}"

        collections = {
            "PROCEDURE": ("procedures", self._find_procedure),
            "TABLE": ("tables", self._find_table),
            "VIEW": ("views", self._find_view),
            "FUNCTION": ("functions", self._find_function),
        }
        if object_type and object_type in collections:
            source, index = collections[object_type][1](schema, name)
            return (
                source,
                index,
                object_type,
                f"/{_collection_name(object_type)}/{index}/extendedProperties",
            )

        for candidate_type, (_collection, finder) in collections.items():
            try:
                source, index = finder(schema, name)
                return (
                    source,
                    index,
                    candidate_type,
                    f"/{_collection_name(candidate_type)}/{index}/extendedProperties",
                )
            except MetadataToolError:
                continue

        raise MetadataToolError(
            OBJECT_NOT_FOUND,
            "Requested metadata object was not found in the active repository.",
            {"schema": schema, "name": name, "objectType": object_type},
        )

    def _find_column(self, schema: str, object_name: str) -> tuple[dict[str, Any], int, int]:
        if "." not in object_name:
            raise MetadataToolError(
                OBJECT_NOT_FOUND,
                "Column extended properties require objectName in TABLE.COLUMN form.",
                {"schema": schema, "objectName": object_name, "objectType": "COLUMN"},
            )
        table_name, column_name = object_name.split(".", 1)
        table, table_index = self._find_table(schema, table_name)
        for column_index, column in enumerate(table.get("columns", [])):
            if _same(column.get("name"), column_name):
                extended_properties = column.get("extendedProperties") or [
                    {
                        "name": "MS_Description",
                        "value": column.get("description"),
                        "level": "COLUMN",
                        "source": "FIXTURE",
                        "reviewStatus": column.get("descriptionStatus", "CONFIRMED"),
                    }
                ]
                return {
                    "schema": schema,
                    "name": f"{table['name']}.{column['name']}",
                    "extendedProperties": extended_properties,
                }, table_index, column_index
        raise MetadataToolError(
            OBJECT_NOT_FOUND,
            "Requested metadata column was not found in the active repository.",
            {"schema": schema, "tableName": table_name, "columnName": column_name},
        )

    def _related_for_table(self, schema: str, name: str) -> list[dict[str, Any]]:
        related = []
        for procedure in self.payload.get("procedures", []):
            for dependency in procedure.get("dependencies", []):
                if _same(dependency.get("schema"), schema) and _same(dependency.get("name"), name):
                    related.append(
                        {
                            "objectType": "PROCEDURE",
                            "schema": procedure["schema"],
                            "name": procedure["name"],
                            "relationship": "REFERENCED_BY",
                        }
                    )
        return related

    @staticmethod
    def _evidence(
        evidence_id: str,
        object_type: str,
        schema: str,
        name: str,
        path: str,
    ) -> dict[str, Any]:
        object_name = f"{schema}.{name}" if schema != "*" else name
        return {
            "id": f"ev:fixture:{evidence_id}:{object_name}",
            "source": "fixture",
            "path": f"fixtures/mcp/metadata_snapshot.json#{path}",
            "objectType": object_type,
            "objectName": object_name,
        }


class LiveMetadataRepository:
    def invoke(self, tool_name: str, arguments: dict[str, Any]) -> MetadataToolResult:
        raise MetadataToolError(
            LIVE_METADATA_UNAVAILABLE,
            "Live metadata tool execution is behind the adapter boundary "
            "and is not implemented yet.",
            {
                "toolName": tool_name,
                "dbProfileId": arguments.get("dbProfileId"),
            },
        )


def _same(left: Any, right: Any) -> bool:
    return str(left).lower() == str(right).lower()


def _matches(needle: str, value: Any) -> bool:
    return needle.lower() in str(value).lower()


def _sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _collection_name(object_type: str) -> str:
    return {
        "PROCEDURE": "procedures",
        "TABLE": "tables",
        "VIEW": "views",
        "FUNCTION": "functions",
    }[object_type]


def _score_table_match(table: dict[str, Any], arguments: dict[str, Any]) -> int:
    score = 0
    if arguments.get("physicalName") and _matches(arguments["physicalName"], table["name"]):
        score += 40
    if arguments.get("logicalName") and _matches(
        arguments["logicalName"], table.get("logicalName", "")
    ):
        score += 30
    if arguments.get("description") and _matches(
        arguments["description"], table.get("description", "")
    ):
        score += 20
    requested_columns = {column.lower() for column in arguments.get("columns", [])}
    table_columns = {str(column.get("name", "")).lower() for column in table.get("columns", [])}
    score += len(requested_columns & table_columns) * 10
    return score


def _score_column_match(
    column: dict[str, Any],
    table: dict[str, Any],
    arguments: dict[str, Any],
) -> int:
    score = 0
    if arguments.get("physicalName") and _matches(arguments["physicalName"], column["name"]):
        score += 40
    if arguments.get("logicalName") and _matches(
        arguments["logicalName"], column.get("logicalName", "")
    ):
        score += 30
    if arguments.get("description") and _matches(
        arguments["description"], column.get("description", "")
    ):
        score += 20
    if arguments.get("tableName") and _matches(arguments["tableName"], table["name"]):
        score += 5
    return score


def _score_similar_table(
    table: dict[str, Any],
    arguments: dict[str, Any],
) -> tuple[int, list[str]]:
    score = 0
    matched_columns = []
    table_columns = {
        str(column.get("name", "")).lower(): column for column in table.get("columns", [])
    }
    for requested in arguments.get("columns", []):
        requested_name = str(requested.get("name", "")).lower()
        table_column = table_columns.get(requested_name)
        if table_column is None:
            continue
        matched_columns.append(table_column["name"])
        score += 10
        if requested.get("type") and _same(requested["type"], table_column.get("dataType")):
            score += 4
    if arguments.get("description") and _matches(
        arguments["description"], table.get("description", "")
    ):
        score += 5
    return score, matched_columns


def _table_candidate(table: dict[str, Any], score: int, fixture_index: int) -> dict[str, Any]:
    return {
        "schema": table["schema"],
        "tableName": table["name"],
        "logicalName": table.get("logicalName"),
        "description": table.get("description"),
        "descriptionStatus": table.get("descriptionStatus", "CONFIRMED"),
        "score": score,
        "evidenceRefs": [
            {
                "id": f"ev:fixture:table:{table['schema']}.{table['name']}",
                "source": "fixture",
                "path": f"fixtures/mcp/metadata_snapshot.json#/tables/{fixture_index}",
                "objectType": "TABLE",
                "objectName": f"{table['schema']}.{table['name']}",
            }
        ],
    }


def _column_candidate(table: dict[str, Any], column: dict[str, Any], score: int) -> dict[str, Any]:
    return {
        "schema": table["schema"],
        "tableName": table["name"],
        "columnName": column["name"],
        "logicalName": column.get("logicalName"),
        "description": column.get("description"),
        "descriptionStatus": column.get("descriptionStatus", "CONFIRMED"),
        "dataType": column.get("dataType"),
        "score": score,
    }


def _criteria(arguments: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in arguments.items() if key != "dbProfileId"}


def _is_empty_search(arguments: dict[str, Any]) -> bool:
    return not any(value for key, value in arguments.items() if key not in {"dbProfileId", "topK"})
