from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

from mssql_mcp_app.catalog import repo_root
from mssql_mcp_app.errors import (
    LIVE_METADATA_UNAVAILABLE,
    METADATA_READ_ONLY_PERMISSION_INSUFFICIENT,
    OBJECT_NOT_FOUND,
    PPM_DB_ACCESS_DENIED,
    PPM_DB_NOT_FOUND,
    SP_DEFINITION_ACCESS_DENIED,
    MetadataToolError,
)
from mssql_mcp_app.metadata_discovery import (
    definition_metadata,
    module_inventory_item,
    procedure_dependency_summary,
    procedure_inventory_item,
    source_context,
    source_database_for_profile,
    table_inventory_item,
)
from mssql_mcp_app.profiles import DbProfile, load_db_profiles
from mssql_mcp_app.settings import LiveMetadataSettings, load_live_metadata_settings


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

    def _handle_check_database_exists(self, arguments: dict[str, Any]) -> MetadataToolResult:
        database_name = arguments.get("databaseName") or source_database_for_profile(
            arguments["dbProfileId"],
            payload=self.payload,
        )
        profile_databases = set(self.payload.get("profileDatabases", {}).values())
        exists = database_name in profile_databases
        evidence = self._evidence(
            "database-exists",
            "DATABASE",
            "*",
            database_name,
            "/profileDatabases",
        )
        data = {
            **source_context(arguments, payload=self.payload),
            "databaseName": database_name,
            "exists": exists,
            "accessible": exists,
            "metadataPermission": "fixture",
            "caveats": [],
            "reviewRequired": not exists,
        }
        return self._result(data=data, evidence_refs=[evidence])

    def _handle_list_procedures(self, arguments: dict[str, Any]) -> MetadataToolResult:
        top_k = arguments.get("topK", 100)
        schema = arguments.get("schema")
        procedures = []
        for index, procedure in enumerate(self.payload.get("procedures", [])):
            if schema and not _same(schema, procedure["schema"]):
                continue
            evidence = self._evidence(
                "procedure-inventory",
                "PROCEDURE",
                procedure["schema"],
                procedure["name"],
                f"/procedures/{index}",
            )
            procedures.append(procedure_inventory_item(procedure, evidence_refs=[evidence]))
        procedures.sort(key=lambda item: (item["schema"], item["name"]))
        evidence = self._evidence(
            "procedure-inventory",
            "CATALOG",
            "*",
            "procedures",
            "/procedures",
        )
        data = {
            **source_context(arguments, payload=self.payload),
            "schema": schema,
            "procedures": procedures[:top_k],
            "caveats": [],
            "reviewRequired": False,
        }
        return self._result(data=data, evidence_refs=[evidence])

    def _handle_list_tables(self, arguments: dict[str, Any]) -> MetadataToolResult:
        top_k = arguments.get("topK", 100)
        schema = arguments.get("schema")
        tables = []
        for index, table in enumerate(self.payload.get("tables", [])):
            if schema and not _same(schema, table["schema"]):
                continue
            evidence = self._evidence(
                "table-inventory",
                "TABLE",
                table["schema"],
                table["name"],
                f"/tables/{index}",
            )
            tables.append(
                table_inventory_item(
                    table,
                    related_procedures=self._related_for_table(table["schema"], table["name"]),
                    evidence_refs=[evidence],
                )
            )
        tables.sort(key=lambda item: (item["schema"], item["name"]))
        evidence = self._evidence("table-inventory", "CATALOG", "*", "tables", "/tables")
        data = {
            **source_context(arguments, payload=self.payload),
            "schema": schema,
            "tables": tables[:top_k],
            "caveats": [],
            "reviewRequired": False,
        }
        return self._result(data=data, evidence_refs=[evidence])

    def _handle_list_views(self, arguments: dict[str, Any]) -> MetadataToolResult:
        top_k = arguments.get("topK", 100)
        schema = arguments.get("schema")
        views = []
        for index, view in enumerate(self.payload.get("views", [])):
            if schema and not _same(schema, view["schema"]):
                continue
            evidence = self._evidence(
                "view-inventory",
                "VIEW",
                view["schema"],
                view["name"],
                f"/views/{index}",
            )
            views.append(module_inventory_item(view, object_type="VIEW", evidence_refs=[evidence]))
        views.sort(key=lambda item: (item["schema"], item["name"]))
        evidence = self._evidence("view-inventory", "CATALOG", "*", "views", "/views")
        data = {
            **source_context(arguments, payload=self.payload),
            "schema": schema,
            "views": views[:top_k],
            "caveats": [],
            "reviewRequired": False,
        }
        return self._result(data=data, evidence_refs=[evidence])

    def _handle_list_functions(self, arguments: dict[str, Any]) -> MetadataToolResult:
        top_k = arguments.get("topK", 100)
        schema = arguments.get("schema")
        functions = []
        for index, function in enumerate(self.payload.get("functions", [])):
            if schema and not _same(schema, function["schema"]):
                continue
            evidence = self._evidence(
                "function-inventory",
                "FUNCTION",
                function["schema"],
                function["name"],
                f"/functions/{index}",
            )
            functions.append(
                module_inventory_item(function, object_type="FUNCTION", evidence_refs=[evidence])
            )
        functions.sort(key=lambda item: (item["schema"], item["name"]))
        evidence = self._evidence("function-inventory", "CATALOG", "*", "functions", "/functions")
        data = {
            **source_context(arguments, payload=self.payload),
            "schema": schema,
            "functions": functions[:top_k],
            "caveats": [],
            "reviewRequired": False,
        }
        return self._result(data=data, evidence_refs=[evidence])

    def _handle_get_procedure_definition(self, arguments: dict[str, Any]) -> MetadataToolResult:
        procedure, index = self._find_procedure(arguments["schema"], arguments["procedureName"])
        definition = procedure.get("definition")
        definition_info = definition_metadata(
            definition,
            is_encrypted=bool(procedure.get("isEncrypted", False)),
        )
        caveats = [] if definition_info["available"] else ["definition_unavailable"]
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
            "definitionHash": definition_info["hash"],
            "definitionLength": definition_info["length"],
            "detectedPatterns": definition_info["detectedPatterns"],
            "isEncrypted": definition_info["isEncrypted"],
            "hasDefinitionAccess": definition_info["available"],
            "caveats": caveats,
            "reviewRequired": bool(caveats),
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
        definition = view.get("definition")
        definition_info = definition_metadata(definition)
        dependencies = view.get("dependencies", [])
        caveats = _dependency_caveats(dependencies)
        if not definition_info["available"]:
            caveats.append("definition_unavailable")
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
            "definitionHash": definition_info["hash"],
            "definitionLength": definition_info["length"],
            "detectedPatterns": definition_info["detectedPatterns"],
            "hasDefinitionAccess": definition_info["available"],
            "dependencies": dependencies,
            "dependencySummary": procedure_dependency_summary(dependencies),
            "caveats": list(dict.fromkeys(caveats)),
            "reviewRequired": bool(caveats),
            "snapshotMode": arguments.get("snapshotMode", "LATEST"),
        }
        return self._result(data=data, evidence_refs=[evidence])

    def _handle_get_function_definition(self, arguments: dict[str, Any]) -> MetadataToolResult:
        function, index = self._find_function(arguments["schema"], arguments["functionName"])
        definition = function.get("definition")
        definition_info = definition_metadata(definition)
        dependencies = function.get("dependencies", [])
        caveats = _dependency_caveats(dependencies)
        if not definition_info["available"]:
            caveats.append("definition_unavailable")
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
            "definitionHash": definition_info["hash"],
            "definitionLength": definition_info["length"],
            "detectedPatterns": definition_info["detectedPatterns"],
            "hasDefinitionAccess": definition_info["available"],
            "dependencies": dependencies,
            "dependencySummary": procedure_dependency_summary(dependencies),
            "caveats": list(dict.fromkeys(caveats)),
            "reviewRequired": bool(caveats),
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
    def __init__(
        self,
        *,
        settings: LiveMetadataSettings | None = None,
        profiles: list[DbProfile] | None = None,
    ) -> None:
        self.settings = settings or load_live_metadata_settings()
        self.profiles = profiles

    def invoke(self, tool_name: str, arguments: dict[str, Any]) -> MetadataToolResult:
        handler = getattr(self, f"_handle_{tool_name}", None)
        if handler is not None:
            return handler(arguments)
        raise MetadataToolError(
            LIVE_METADATA_UNAVAILABLE,
            "Live metadata tool execution is behind the adapter boundary "
            "and is not implemented yet.",
            {
                "toolName": tool_name,
                "dbProfileId": arguments.get("dbProfileId"),
            },
        )

    def _handle_check_database_exists(self, arguments: dict[str, Any]) -> MetadataToolResult:
        profile = self._profile(arguments["dbProfileId"])
        database_name = arguments.get("databaseName") or profile.database
        rows = self._query(
            "master",
            """
            SELECT
                name,
                state_desc,
                is_read_only,
                user_access_desc,
                collation_name
            FROM sys.databases
            WHERE name = %s
            """,
            [database_name],
            tool_name="check_database_exists",
            profile=profile,
        )
        exists = bool(rows)
        accessible = False
        caveats = []
        if exists:
            try:
                connection = self._connect(
                    database_name,
                    profile=profile,
                    tool_name="check_database_exists",
                )
                connection.close()
                accessible = True
            except MetadataToolError as exc:
                caveats.append(exc.code)

        row = rows[0] if rows else {}
        evidence = self._live_evidence(
            "database-exists",
            "DATABASE",
            "*",
            database_name,
            "sys.databases",
        )
        return self._live_result(
            arguments,
            data={
                **source_context(arguments),
                "databaseName": database_name,
                "exists": exists,
                "accessible": accessible,
                "state": row.get("state_desc"),
                "readOnly": row.get("is_read_only"),
                "userAccess": row.get("user_access_desc"),
                "collation": row.get("collation_name"),
                "caveats": caveats,
                "reviewRequired": not exists or not accessible,
            },
            evidence_refs=[evidence],
        )

    def _handle_list_procedures(self, arguments: dict[str, Any]) -> MetadataToolResult:
        profile = self._profile(arguments["dbProfileId"])
        schema_filter, params = _schema_filter(arguments)
        rows = self._query(
            profile.database,
            f"""
            SELECT
                s.name AS schema_name,
                p.name AS object_name,
                p.object_id,
                CONVERT(int, OBJECTPROPERTY(p.object_id, 'IsEncrypted')) AS is_encrypted,
                m.definition
            FROM sys.procedures AS p
            INNER JOIN sys.schemas AS s ON p.schema_id = s.schema_id
            LEFT JOIN sys.sql_modules AS m ON p.object_id = m.object_id
            WHERE p.is_ms_shipped = 0{schema_filter}
            ORDER BY s.name, p.name
            """,
            params,
            tool_name="list_procedures",
            profile=profile,
        )
        parameter_rows = self._query(
            profile.database,
            f"""
            SELECT
                p.object_id,
                prm.name,
                TYPE_NAME(prm.user_type_id) AS data_type,
                prm.parameter_id AS ordinal,
                prm.is_output,
                prm.has_default_value,
                CONVERT(nvarchar(4000), prm.default_value) AS default_value
            FROM sys.procedures AS p
            INNER JOIN sys.schemas AS s ON p.schema_id = s.schema_id
            INNER JOIN sys.parameters AS prm ON p.object_id = prm.object_id
            WHERE p.is_ms_shipped = 0{schema_filter}
            ORDER BY p.object_id, prm.parameter_id
            """,
            params,
            tool_name="list_procedures",
            profile=profile,
        )
        dependency_rows = self._query(
            profile.database,
            f"""
            SELECT
                p.object_id,
                COALESCE(rs.name, dep_rs.name, dep.referenced_schema_name) AS schema_name,
                COALESCE(ro.name, dep_ro.name, dep.referenced_entity_name) AS object_name,
                COALESCE(ro.type, dep_ro.type) AS referenced_type,
                dep.referenced_class_desc,
                dep.is_ambiguous
            FROM sys.procedures AS p
            INNER JOIN sys.schemas AS s ON p.schema_id = s.schema_id
            LEFT JOIN sys.sql_expression_dependencies AS dep
                ON p.object_id = dep.referencing_id
            LEFT JOIN sys.objects AS ro ON dep.referenced_id = ro.object_id
            LEFT JOIN sys.schemas AS rs ON ro.schema_id = rs.schema_id
            LEFT JOIN sys.schemas AS dep_rs ON dep.referenced_schema_name = dep_rs.name
            LEFT JOIN sys.objects AS dep_ro
                ON dep_rs.schema_id = dep_ro.schema_id
                AND dep.referenced_entity_name = dep_ro.name
            WHERE p.is_ms_shipped = 0{schema_filter}
            ORDER BY p.object_id, schema_name, object_name
            """,
            params,
            tool_name="list_procedures",
            profile=profile,
        )
        parameters_by_object = _group_parameters(parameter_rows)
        dependencies_by_object = _group_dependencies(dependency_rows)
        procedures = []
        for row in rows:
            object_id = row["object_id"]
            evidence = self._live_evidence(
                "procedure-inventory",
                "PROCEDURE",
                row["schema_name"],
                row["object_name"],
                "sys.procedures",
            )
            procedure = {
                "schema": row["schema_name"],
                "name": row["object_name"],
                "isEncrypted": bool(row.get("is_encrypted")),
                "definition": row.get("definition"),
                "parameters": parameters_by_object.get(object_id, []),
                "dependencies": dependencies_by_object.get(object_id, []),
            }
            procedures.append(procedure_inventory_item(procedure, evidence_refs=[evidence]))
        return self._live_result(
            arguments,
            data={
                **source_context(arguments),
                "schema": arguments.get("schema"),
                "procedures": procedures[: arguments.get("topK", 100)],
                "caveats": [],
                "reviewRequired": False,
            },
            evidence_refs=[
                self._live_evidence(
                    "procedure-inventory",
                    "CATALOG",
                    "*",
                    "procedures",
                    "sys.procedures",
                )
            ],
        )

    def _handle_list_tables(self, arguments: dict[str, Any]) -> MetadataToolResult:
        profile = self._profile(arguments["dbProfileId"])
        schema_filter, params = _schema_filter(arguments)
        rows = self._query(
            profile.database,
            f"""
            SELECT
                s.name AS schema_name,
                t.name AS object_name,
                t.object_id,
                CONVERT(nvarchar(4000), ep.value) AS description,
                (
                    SELECT COUNT(1)
                    FROM sys.columns AS c
                    WHERE c.object_id = t.object_id
                ) AS column_count,
                (
                    SELECT COUNT(1)
                    FROM sys.key_constraints AS kc
                    WHERE kc.parent_object_id = t.object_id
                ) AS key_constraint_count,
                (
                    SELECT COUNT(1)
                    FROM sys.foreign_keys AS fk
                    WHERE fk.parent_object_id = t.object_id
                ) AS foreign_key_count,
                (
                    SELECT COUNT(1)
                    FROM sys.check_constraints AS cc
                    WHERE cc.parent_object_id = t.object_id
                ) AS check_constraint_count,
                (
                    SELECT COUNT(1)
                    FROM sys.indexes AS i
                    WHERE i.object_id = t.object_id
                        AND i.index_id > 0
                        AND i.is_hypothetical = 0
                ) AS index_count,
                (
                    SELECT COUNT(1)
                    FROM sys.extended_properties AS all_ep
                    WHERE all_ep.major_id = t.object_id
                ) AS extended_property_count
            FROM sys.tables AS t
            INNER JOIN sys.schemas AS s ON t.schema_id = s.schema_id
            LEFT JOIN sys.extended_properties AS ep
                ON ep.major_id = t.object_id
                AND ep.minor_id = 0
                AND ep.name = 'MS_Description'
            WHERE t.is_ms_shipped = 0{schema_filter}
            ORDER BY s.name, t.name
            """,
            params,
            tool_name="list_tables",
            profile=profile,
        )
        tables = []
        for row in rows[: arguments.get("topK", 100)]:
            evidence = self._live_evidence(
                "table-inventory",
                "TABLE",
                row["schema_name"],
                row["object_name"],
                "sys.tables",
            )
            has_description = bool(row.get("description"))
            tables.append(
                {
                    "schema": row["schema_name"],
                    "name": row["object_name"],
                    "objectType": "TABLE",
                    "logicalName": None,
                    "descriptionStatus": "CONFIRMED" if has_description else "REVIEW_REQUIRED",
                    "columnCount": int(row.get("column_count") or 0),
                    "keyIndexConstraintSummary": {
                        "primaryKey": None,
                        "foreignKeyCount": int(row.get("foreign_key_count") or 0),
                        "indexCount": int(row.get("index_count") or 0),
                        "constraintCount": int(row.get("key_constraint_count") or 0)
                        + int(row.get("foreign_key_count") or 0)
                        + int(row.get("check_constraint_count") or 0),
                    },
                    "extendedPropertyCount": int(row.get("extended_property_count") or 0),
                    "relatedProcedures": [],
                    "caveats": [] if has_description else ["description_review_required"],
                    "reviewRequired": not has_description,
                    "evidenceRefs": [evidence],
                }
            )
        return self._live_result(
            arguments,
            data={
                **source_context(arguments),
                "schema": arguments.get("schema"),
                "tables": tables,
                "caveats": [],
                "reviewRequired": False,
            },
            evidence_refs=[
                self._live_evidence("table-inventory", "CATALOG", "*", "tables", "sys.tables")
            ],
        )

    def _handle_list_views(self, arguments: dict[str, Any]) -> MetadataToolResult:
        return self._handle_list_modules(arguments, object_kind="VIEW")

    def _handle_list_functions(self, arguments: dict[str, Any]) -> MetadataToolResult:
        return self._handle_list_modules(arguments, object_kind="FUNCTION")

    def _handle_get_procedure_definition(
        self,
        arguments: dict[str, Any],
    ) -> MetadataToolResult:
        profile = self._profile(arguments["dbProfileId"])
        row = self._single_row(
            self._query(
                profile.database,
                """
                SELECT
                    s.name AS schema_name,
                    p.name AS object_name,
                    CONVERT(int, OBJECTPROPERTY(p.object_id, 'IsEncrypted')) AS is_encrypted,
                    m.definition
                FROM sys.procedures AS p
                INNER JOIN sys.schemas AS s ON p.schema_id = s.schema_id
                LEFT JOIN sys.sql_modules AS m ON p.object_id = m.object_id
                WHERE p.is_ms_shipped = 0
                    AND s.name = %s
                    AND p.name = %s
                """,
                [arguments["schema"], arguments["procedureName"]],
                tool_name="get_procedure_definition",
                profile=profile,
            ),
            object_type="PROCEDURE",
            schema=arguments["schema"],
            name=arguments["procedureName"],
        )
        definition = row.get("definition")
        definition_info = definition_metadata(
            definition,
            is_encrypted=bool(row.get("is_encrypted")),
        )
        caveats = [] if definition_info["available"] else ["definition_unavailable"]
        evidence = self._live_evidence(
            "procedure-definition",
            "PROCEDURE",
            row["schema_name"],
            row["object_name"],
            "sys.sql_modules",
        )
        return self._live_result(
            arguments,
            data={
                "schema": row["schema_name"],
                "procedureName": row["object_name"],
                "definition": definition,
                "definitionHash": definition_info["hash"],
                "definitionLength": definition_info["length"],
                "detectedPatterns": definition_info["detectedPatterns"],
                "isEncrypted": definition_info["isEncrypted"],
                "hasDefinitionAccess": definition_info["available"],
                "caveats": caveats,
                "reviewRequired": bool(caveats),
                "snapshotMode": arguments.get("snapshotMode", "LATEST"),
            },
            evidence_refs=[evidence],
        )

    def _handle_get_procedure_parameters(
        self,
        arguments: dict[str, Any],
    ) -> MetadataToolResult:
        profile = self._profile(arguments["dbProfileId"])
        self._ensure_object_id(
            profile,
            schema=arguments["schema"],
            name=arguments["procedureName"],
            object_type="PROCEDURE",
            tool_name="get_procedure_parameters",
        )
        rows = self._query(
            profile.database,
            """
            SELECT
                p.object_id,
                prm.name,
                TYPE_NAME(prm.user_type_id) AS data_type,
                prm.parameter_id AS ordinal,
                prm.is_output,
                prm.has_default_value,
                CONVERT(nvarchar(4000), prm.default_value) AS default_value
            FROM sys.procedures AS p
            INNER JOIN sys.schemas AS s ON p.schema_id = s.schema_id
            INNER JOIN sys.parameters AS prm ON p.object_id = prm.object_id
            WHERE p.is_ms_shipped = 0
                AND s.name = %s
                AND p.name = %s
            ORDER BY prm.parameter_id
            """,
            [arguments["schema"], arguments["procedureName"]],
            tool_name="get_procedure_parameters",
            profile=profile,
        )
        parameters = [item for values in _group_parameters(rows).values() for item in values]
        evidence = self._live_evidence(
            "procedure-parameters",
            "PROCEDURE",
            arguments["schema"],
            arguments["procedureName"],
            "sys.parameters",
        )
        return self._live_result(
            arguments,
            data={
                "schema": arguments["schema"],
                "procedureName": arguments["procedureName"],
                "parameters": parameters,
                "snapshotMode": arguments.get("snapshotMode", "LATEST"),
            },
            evidence_refs=[evidence],
        )

    def _handle_get_procedure_dependencies(
        self,
        arguments: dict[str, Any],
    ) -> MetadataToolResult:
        profile = self._profile(arguments["dbProfileId"])
        self._ensure_object_id(
            profile,
            schema=arguments["schema"],
            name=arguments["procedureName"],
            object_type="PROCEDURE",
            tool_name="get_procedure_dependencies",
        )
        rows = self._query(
            profile.database,
            """
            SELECT
                p.object_id,
                COALESCE(rs.name, dep_rs.name, dep.referenced_schema_name) AS schema_name,
                COALESCE(ro.name, dep_ro.name, dep.referenced_entity_name) AS object_name,
                COALESCE(ro.type, dep_ro.type) AS referenced_type,
                dep.referenced_class_desc,
                dep.is_ambiguous
            FROM sys.procedures AS p
            INNER JOIN sys.schemas AS s ON p.schema_id = s.schema_id
            LEFT JOIN sys.sql_expression_dependencies AS dep
                ON p.object_id = dep.referencing_id
            LEFT JOIN sys.objects AS ro ON dep.referenced_id = ro.object_id
            LEFT JOIN sys.schemas AS rs ON ro.schema_id = rs.schema_id
            LEFT JOIN sys.schemas AS dep_rs ON dep.referenced_schema_name = dep_rs.name
            LEFT JOIN sys.objects AS dep_ro
                ON dep_rs.schema_id = dep_ro.schema_id
                AND dep.referenced_entity_name = dep_ro.name
            WHERE p.is_ms_shipped = 0
                AND s.name = %s
                AND p.name = %s
            ORDER BY schema_name, object_name
            """,
            [arguments["schema"], arguments["procedureName"]],
            tool_name="get_procedure_dependencies",
            profile=profile,
        )
        dependencies = [item for values in _group_dependencies(rows).values() for item in values]
        evidence = self._live_evidence(
            "procedure-dependencies",
            "PROCEDURE",
            arguments["schema"],
            arguments["procedureName"],
            "sys.sql_expression_dependencies",
        )
        return self._live_result(
            arguments,
            data={
                "schema": arguments["schema"],
                "procedureName": arguments["procedureName"],
                "dependencies": dependencies,
                "dependencySummary": procedure_dependency_summary(dependencies),
                "caveats": _dependency_caveats(dependencies),
                "reviewRequired": bool(_dependency_caveats(dependencies)),
                "snapshotMode": arguments.get("snapshotMode", "LATEST"),
            },
            evidence_refs=[evidence],
        )

    def _handle_get_related_db_objects(self, arguments: dict[str, Any]) -> MetadataToolResult:
        profile = self._profile(arguments["dbProfileId"])
        object_type = arguments["objectType"]
        schema = arguments["schema"]
        object_name = arguments["objectName"]
        object_id = self._ensure_object_id(
            profile,
            schema=schema,
            name=object_name,
            object_type=object_type,
            tool_name="get_related_db_objects",
        )
        if object_type == "TABLE":
            related = self._referrers_for_object(
                profile,
                object_id=object_id,
                schema=schema,
                name=object_name,
                tool_name="get_related_db_objects",
            )
        else:
            related = self._dependencies_for_object(
                profile,
                object_id=object_id,
                tool_name="get_related_db_objects",
            )
        related = related[: arguments.get("topK", 20)]
        caveats = _dependency_caveats(related)
        evidence = self._live_evidence(
            "related-objects",
            object_type,
            schema,
            object_name,
            "sys.sql_expression_dependencies",
        )
        return self._live_result(
            arguments,
            data={
                "schema": schema,
                "objectName": object_name,
                "objectType": object_type,
                "relatedObjects": related,
                "caveats": caveats,
                "reviewRequired": bool(caveats),
            },
            evidence_refs=[evidence],
        )

    def _handle_get_table_schema(self, arguments: dict[str, Any]) -> MetadataToolResult:
        profile = self._profile(arguments["dbProfileId"])
        rows = self._query(
            profile.database,
            """
            SELECT
                s.name AS schema_name,
                t.name AS table_name,
                c.name AS column_name,
                ty.name AS type_name,
                c.max_length,
                c.precision,
                c.scale,
                c.column_id,
                c.is_nullable,
                c.is_identity,
                CONVERT(nvarchar(4000), table_ep.value) AS table_description,
                CONVERT(nvarchar(4000), ep.value) AS description,
                CASE WHEN pk.column_id IS NULL THEN 0 ELSE 1 END AS is_primary_key
            FROM sys.tables AS t
            INNER JOIN sys.schemas AS s ON t.schema_id = s.schema_id
            INNER JOIN sys.columns AS c ON t.object_id = c.object_id
            INNER JOIN sys.types AS ty ON c.user_type_id = ty.user_type_id
            LEFT JOIN sys.extended_properties AS table_ep
                ON table_ep.major_id = t.object_id
                AND table_ep.minor_id = 0
                AND table_ep.name = 'MS_Description'
            LEFT JOIN sys.extended_properties AS ep
                ON ep.major_id = c.object_id
                AND ep.minor_id = c.column_id
                AND ep.name = 'MS_Description'
            LEFT JOIN (
                SELECT ic.object_id, ic.column_id
                FROM sys.indexes AS i
                INNER JOIN sys.index_columns AS ic
                    ON i.object_id = ic.object_id
                    AND i.index_id = ic.index_id
                WHERE i.is_primary_key = 1
            ) AS pk ON c.object_id = pk.object_id AND c.column_id = pk.column_id
            WHERE t.is_ms_shipped = 0
                AND s.name = %s
                AND t.name = %s
            ORDER BY c.column_id
            """,
            [arguments["schema"], arguments["tableName"]],
            tool_name="get_table_schema",
            profile=profile,
        )
        if not rows:
            raise _object_not_found("TABLE", arguments["schema"], arguments["tableName"])
        columns = [
            {
                "name": row["column_name"],
                "logicalName": None,
                "description": row.get("description"),
                "descriptionStatus": "CONFIRMED"
                if row.get("description")
                else "REVIEW_REQUIRED",
                "dataType": _format_data_type(row),
                "ordinal": row["column_id"],
                "isNullable": bool(row.get("is_nullable")),
                "isIdentity": bool(row.get("is_identity")),
                "isPrimaryKey": bool(row.get("is_primary_key")),
            }
            for row in rows
        ]
        evidence = self._live_evidence(
            "table-schema",
            "TABLE",
            arguments["schema"],
            arguments["tableName"],
            "sys.columns",
        )
        return self._live_result(
            arguments,
            data={
                "schema": arguments["schema"],
                "tableName": arguments["tableName"],
                "logicalName": None,
                "description": rows[0].get("table_description"),
                "descriptionStatus": "CONFIRMED"
                if rows[0].get("table_description")
                else "REVIEW_REQUIRED",
                "columns": columns,
            },
            evidence_refs=[evidence],
        )

    def _handle_get_table_constraints(self, arguments: dict[str, Any]) -> MetadataToolResult:
        profile = self._profile(arguments["dbProfileId"])
        self._ensure_object_id(
            profile,
            schema=arguments["schema"],
            name=arguments["tableName"],
            object_type="TABLE",
            tool_name="get_table_constraints",
        )
        key_rows = self._query(
            profile.database,
            """
            SELECT
                kc.name,
                kc.type,
                c.name AS column_name,
                ic.key_ordinal
            FROM sys.tables AS t
            INNER JOIN sys.schemas AS s ON t.schema_id = s.schema_id
            INNER JOIN sys.key_constraints AS kc ON t.object_id = kc.parent_object_id
            INNER JOIN sys.index_columns AS ic
                ON kc.parent_object_id = ic.object_id
                AND kc.unique_index_id = ic.index_id
            INNER JOIN sys.columns AS c
                ON ic.object_id = c.object_id
                AND ic.column_id = c.column_id
            WHERE s.name = %s AND t.name = %s
            ORDER BY kc.name, ic.key_ordinal
            """,
            [arguments["schema"], arguments["tableName"]],
            tool_name="get_table_constraints",
            profile=profile,
        )
        fk_rows = self._query(
            profile.database,
            """
            SELECT
                fk.name,
                pc.name AS column_name,
                rs.name AS referenced_schema,
                rt.name AS referenced_table,
                rc.name AS referenced_column,
                fkc.constraint_column_id
            FROM sys.tables AS t
            INNER JOIN sys.schemas AS s ON t.schema_id = s.schema_id
            INNER JOIN sys.foreign_keys AS fk ON t.object_id = fk.parent_object_id
            INNER JOIN sys.foreign_key_columns AS fkc
                ON fk.object_id = fkc.constraint_object_id
            INNER JOIN sys.columns AS pc
                ON fkc.parent_object_id = pc.object_id
                AND fkc.parent_column_id = pc.column_id
            INNER JOIN sys.tables AS rt ON fkc.referenced_object_id = rt.object_id
            INNER JOIN sys.schemas AS rs ON rt.schema_id = rs.schema_id
            INNER JOIN sys.columns AS rc
                ON fkc.referenced_object_id = rc.object_id
                AND fkc.referenced_column_id = rc.column_id
            WHERE s.name = %s AND t.name = %s
            ORDER BY fk.name, fkc.constraint_column_id
            """,
            [arguments["schema"], arguments["tableName"]],
            tool_name="get_table_constraints",
            profile=profile,
        )
        check_rows = self._query(
            profile.database,
            """
            SELECT
                cc.name,
                cc.definition
            FROM sys.tables AS t
            INNER JOIN sys.schemas AS s ON t.schema_id = s.schema_id
            INNER JOIN sys.check_constraints AS cc ON t.object_id = cc.parent_object_id
            WHERE s.name = %s AND t.name = %s
            ORDER BY cc.name
            """,
            [arguments["schema"], arguments["tableName"]],
            tool_name="get_table_constraints",
            profile=profile,
        )
        constraints = (
            _group_key_constraints(key_rows)
            + _group_foreign_keys(fk_rows)
            + _group_check_constraints(check_rows)
        )
        evidence = self._live_evidence(
            "table-constraints",
            "TABLE",
            arguments["schema"],
            arguments["tableName"],
            "sys.key_constraints,sys.foreign_keys,sys.check_constraints",
        )
        return self._live_result(
            arguments,
            data={
                "schema": arguments["schema"],
                "tableName": arguments["tableName"],
                "constraints": constraints,
            },
            evidence_refs=[evidence],
        )

    def _handle_get_table_indexes(self, arguments: dict[str, Any]) -> MetadataToolResult:
        profile = self._profile(arguments["dbProfileId"])
        self._ensure_object_id(
            profile,
            schema=arguments["schema"],
            name=arguments["tableName"],
            object_type="TABLE",
            tool_name="get_table_indexes",
        )
        rows = self._query(
            profile.database,
            """
            SELECT
                i.name,
                i.is_unique,
                i.type_desc,
                ic.is_included_column,
                ic.key_ordinal,
                c.name AS column_name
            FROM sys.tables AS t
            INNER JOIN sys.schemas AS s ON t.schema_id = s.schema_id
            INNER JOIN sys.indexes AS i ON t.object_id = i.object_id
            INNER JOIN sys.index_columns AS ic
                ON i.object_id = ic.object_id
                AND i.index_id = ic.index_id
            INNER JOIN sys.columns AS c
                ON ic.object_id = c.object_id
                AND ic.column_id = c.column_id
            WHERE s.name = %s
                AND t.name = %s
                AND i.index_id > 0
                AND i.is_hypothetical = 0
            ORDER BY i.name, ic.key_ordinal, ic.index_column_id
            """,
            [arguments["schema"], arguments["tableName"]],
            tool_name="get_table_indexes",
            profile=profile,
        )
        indexes = _group_indexes(rows)
        evidence = self._live_evidence(
            "table-indexes",
            "TABLE",
            arguments["schema"],
            arguments["tableName"],
            "sys.indexes",
        )
        return self._live_result(
            arguments,
            data={
                "schema": arguments["schema"],
                "tableName": arguments["tableName"],
                "indexes": indexes,
            },
            evidence_refs=[evidence],
        )

    def _handle_get_extended_properties(self, arguments: dict[str, Any]) -> MetadataToolResult:
        profile = self._profile(arguments["dbProfileId"])
        object_name = arguments["objectName"]
        object_type = arguments.get("objectType")
        table_name = object_name
        column_name = None
        minor_filter = "AND ep.minor_id = 0"
        params: list[Any] = [arguments["schema"], table_name]
        if object_type == "COLUMN":
            if "." not in object_name:
                raise _object_not_found("COLUMN", arguments["schema"], object_name)
            table_name, column_name = object_name.split(".", 1)
            self._ensure_column_exists(
                profile,
                schema=arguments["schema"],
                table_name=table_name,
                column_name=column_name,
                tool_name="get_extended_properties",
            )
            minor_filter = "AND c.name = %s"
            params = [arguments["schema"], table_name, column_name]
        else:
            self._ensure_object_id(
                profile,
                schema=arguments["schema"],
                name=table_name,
                object_type=object_type,
                tool_name="get_extended_properties",
            )
        rows = self._query(
            profile.database,
            f"""
            SELECT
                ep.name,
                CONVERT(nvarchar(4000), ep.value) AS value,
                CASE WHEN ep.minor_id = 0 THEN 'OBJECT' ELSE 'COLUMN' END AS level_name,
                c.name AS column_name
            FROM sys.objects AS o
            INNER JOIN sys.schemas AS s ON o.schema_id = s.schema_id
            INNER JOIN sys.extended_properties AS ep ON o.object_id = ep.major_id
            LEFT JOIN sys.columns AS c
                ON ep.major_id = c.object_id
                AND ep.minor_id = c.column_id
            WHERE s.name = %s
                AND o.name = %s
                {minor_filter}
            ORDER BY ep.name
            """,
            params,
            tool_name="get_extended_properties",
            profile=profile,
        )
        resolved_name = f"{table_name}.{column_name}" if column_name else table_name
        extended_properties = [
            {
                "name": row["name"],
                "value": row.get("value"),
                "level": row.get("level_name"),
                "source": "LIVE_METADATA",
                "reviewStatus": "CONFIRMED",
            }
            for row in rows
        ]
        evidence = self._live_evidence(
            "extended-properties",
            object_type or "OBJECT",
            arguments["schema"],
            resolved_name,
            "sys.extended_properties",
        )
        return self._live_result(
            arguments,
            data={
                "schema": arguments["schema"],
                "objectName": resolved_name,
                "objectType": object_type or "OBJECT",
                "extendedProperties": extended_properties,
            },
            evidence_refs=[evidence],
        )

    def _handle_search_tables(self, arguments: dict[str, Any]) -> MetadataToolResult:
        profile = self._profile(arguments["dbProfileId"])
        top_k = arguments.get("topK", 5)
        candidates = []
        for index, table in enumerate(
            self._searchable_live_tables(profile, tool_name="search_tables")
        ):
            score = _score_table_match(table, arguments)
            if score > 0 or _is_empty_search(arguments):
                candidates.append(_live_table_candidate(self, table, score, index))
        candidates.sort(key=lambda item: (-item["score"], item["schema"], item["tableName"]))
        evidence = self._live_evidence("table-search", "CATALOG", "*", "tables", "sys.tables")
        return self._live_result(
            arguments,
            data={
                "criteria": _criteria(arguments),
                "candidates": candidates[:top_k],
                "caveats": [],
                "reviewRequired": False,
            },
            evidence_refs=[evidence],
        )

    def _handle_search_columns(self, arguments: dict[str, Any]) -> MetadataToolResult:
        profile = self._profile(arguments["dbProfileId"])
        top_k = arguments.get("topK", 5)
        candidates = []
        for table in self._searchable_live_tables(profile, tool_name="search_columns"):
            if arguments.get("tableName") and not _matches(arguments["tableName"], table["name"]):
                continue
            for column in table.get("columns", []):
                score = _score_column_match(column, table, arguments)
                if score > 0 or _is_empty_search(arguments):
                    candidate = _column_candidate(table, column, score)
                    candidate["evidenceRefs"] = [
                        self._live_evidence(
                            "column-search",
                            "COLUMN",
                            table["schema"],
                            f"{table['name']}.{column['name']}",
                            "sys.columns",
                        )
                    ]
                    candidates.append(candidate)
        candidates.sort(
            key=lambda item: (-item["score"], item["schema"], item["tableName"], item["columnName"])
        )
        evidence = self._live_evidence("column-search", "CATALOG", "*", "columns", "sys.columns")
        return self._live_result(
            arguments,
            data={
                "criteria": _criteria(arguments),
                "candidates": candidates[:top_k],
                "caveats": [],
                "reviewRequired": False,
            },
            evidence_refs=[evidence],
        )

    def _handle_find_similar_tables(self, arguments: dict[str, Any]) -> MetadataToolResult:
        profile = self._profile(arguments["dbProfileId"])
        top_k = arguments.get("topK", 5)
        candidates = []
        for index, table in enumerate(
            self._searchable_live_tables(profile, tool_name="find_similar_tables")
        ):
            score, matched_columns = _score_similar_table(table, arguments)
            if score > 0:
                candidate = _live_table_candidate(self, table, score, index)
                candidate["matchedColumns"] = matched_columns
                candidates.append(candidate)
        candidates.sort(key=lambda item: (-item["score"], item["schema"], item["tableName"]))
        evidence = self._live_evidence(
            "similar-table-search",
            "CATALOG",
            "*",
            "tables",
            "sys.tables,sys.columns",
        )
        return self._live_result(
            arguments,
            data={
                "criteria": _criteria(arguments),
                "candidates": candidates[:top_k],
                "caveats": [],
                "reviewRequired": False,
            },
            evidence_refs=[evidence],
        )

    def _handle_get_view_definition(self, arguments: dict[str, Any]) -> MetadataToolResult:
        return self._handle_get_module_definition(
            arguments,
            object_kind="VIEW",
            name_key="viewName",
            name_value=arguments["viewName"],
        )

    def _handle_get_function_definition(self, arguments: dict[str, Any]) -> MetadataToolResult:
        return self._handle_get_module_definition(
            arguments,
            object_kind="FUNCTION",
            name_key="functionName",
            name_value=arguments["functionName"],
        )

    def _handle_get_module_definition(
        self,
        arguments: dict[str, Any],
        *,
        object_kind: str,
        name_key: str,
        name_value: str,
    ) -> MetadataToolResult:
        profile = self._profile(arguments["dbProfileId"])
        type_filter = "= 'V'" if object_kind == "VIEW" else "IN ('FN', 'IF', 'TF', 'FS', 'FT')"
        row = self._single_row(
            self._query(
                profile.database,
                f"""
                SELECT
                    s.name AS schema_name,
                    o.name AS object_name,
                    o.object_id,
                    m.definition
                FROM sys.objects AS o
                INNER JOIN sys.schemas AS s ON o.schema_id = s.schema_id
                LEFT JOIN sys.sql_modules AS m ON o.object_id = m.object_id
                WHERE o.type {type_filter}
                    AND o.is_ms_shipped = 0
                    AND s.name = %s
                    AND o.name = %s
                """,
                [arguments["schema"], name_value],
                tool_name=f"get_{object_kind.lower()}_definition",
                profile=profile,
            ),
            object_type=object_kind,
            schema=arguments["schema"],
            name=name_value,
        )
        definition = row.get("definition")
        definition_info = definition_metadata(definition)
        dependencies = self._dependencies_for_object(
            profile,
            object_id=row["object_id"],
            tool_name=f"get_{object_kind.lower()}_definition",
        )
        caveats = _dependency_caveats(dependencies)
        if not definition_info["available"]:
            caveats.append("definition_unavailable")
        evidence = self._live_evidence(
            f"{object_kind.lower()}-definition",
            object_kind,
            row["schema_name"],
            row["object_name"],
            "sys.sql_modules",
        )
        return self._live_result(
            arguments,
            data={
                "schema": row["schema_name"],
                name_key: row["object_name"],
                "definition": definition,
                "definitionHash": definition_info["hash"],
                "definitionLength": definition_info["length"],
                "detectedPatterns": definition_info["detectedPatterns"],
                "hasDefinitionAccess": definition_info["available"],
                "dependencies": dependencies,
                "dependencySummary": procedure_dependency_summary(dependencies),
                "caveats": list(dict.fromkeys(caveats)),
                "reviewRequired": bool(caveats),
                "snapshotMode": arguments.get("snapshotMode", "LATEST"),
            },
            evidence_refs=[evidence],
        )

    def _handle_list_modules(
        self,
        arguments: dict[str, Any],
        *,
        object_kind: str,
    ) -> MetadataToolResult:
        profile = self._profile(arguments["dbProfileId"])
        schema_filter, params = _schema_filter(arguments)
        if object_kind == "VIEW":
            source = "sys.views"
            type_filter = "= 'V'"
            sql = f"""
            SELECT
                s.name AS schema_name,
                v.name AS object_name,
                v.object_id,
                m.definition
            FROM sys.views AS v
            INNER JOIN sys.schemas AS s ON v.schema_id = s.schema_id
            LEFT JOIN sys.sql_modules AS m ON v.object_id = m.object_id
            WHERE v.is_ms_shipped = 0{schema_filter}
            ORDER BY s.name, v.name
            """
        else:
            source = "sys.objects"
            type_filter = "IN ('FN', 'IF', 'TF', 'FS', 'FT')"
            sql = f"""
            SELECT
                s.name AS schema_name,
                o.name AS object_name,
                o.object_id,
                m.definition
            FROM sys.objects AS o
            INNER JOIN sys.schemas AS s ON o.schema_id = s.schema_id
            LEFT JOIN sys.sql_modules AS m ON o.object_id = m.object_id
            WHERE o.type IN ('FN', 'IF', 'TF', 'FS', 'FT')
                AND o.is_ms_shipped = 0{schema_filter}
            ORDER BY s.name, o.name
            """
        rows = self._query(
            profile.database,
            sql,
            params,
            tool_name=f"list_{object_kind.lower()}s",
            profile=profile,
        )
        dependency_rows = self._query(
            profile.database,
            f"""
            SELECT
                o.object_id,
                COALESCE(rs.name, dep_rs.name, dep.referenced_schema_name) AS schema_name,
                COALESCE(ro.name, dep_ro.name, dep.referenced_entity_name) AS object_name,
                COALESCE(ro.type, dep_ro.type) AS referenced_type,
                dep.referenced_class_desc,
                dep.is_ambiguous
            FROM sys.objects AS o
            INNER JOIN sys.schemas AS s ON o.schema_id = s.schema_id
            LEFT JOIN sys.sql_expression_dependencies AS dep
                ON o.object_id = dep.referencing_id
            LEFT JOIN sys.objects AS ro ON dep.referenced_id = ro.object_id
            LEFT JOIN sys.schemas AS rs ON ro.schema_id = rs.schema_id
            LEFT JOIN sys.schemas AS dep_rs ON dep.referenced_schema_name = dep_rs.name
            LEFT JOIN sys.objects AS dep_ro
                ON dep_rs.schema_id = dep_ro.schema_id
                AND dep.referenced_entity_name = dep_ro.name
            WHERE o.type {type_filter}
                AND o.is_ms_shipped = 0{schema_filter}
            ORDER BY o.object_id, schema_name, object_name
            """,
            params,
            tool_name=f"list_{object_kind.lower()}s",
            profile=profile,
        )
        dependencies_by_object = _group_dependencies(dependency_rows)
        modules = []
        for row in rows[: arguments.get("topK", 100)]:
            evidence = self._live_evidence(
                f"{object_kind.lower()}-inventory",
                object_kind,
                row["schema_name"],
                row["object_name"],
                source,
            )
            module = {
                "schema": row["schema_name"],
                "name": row["object_name"],
                "definition": row.get("definition"),
                "dependencies": dependencies_by_object.get(row["object_id"], []),
            }
            modules.append(
                module_inventory_item(
                    module,
                    object_type=object_kind,
                    evidence_refs=[evidence],
                )
            )
        key = "views" if object_kind == "VIEW" else "functions"
        return self._live_result(
            arguments,
            data={
                **source_context(arguments),
                "schema": arguments.get("schema"),
                key: modules,
                "caveats": [],
                "reviewRequired": False,
            },
            evidence_refs=[
                self._live_evidence(
                    f"{object_kind.lower()}-inventory",
                    "CATALOG",
                    "*",
                    key,
                    source,
                )
            ],
        )

    def _ensure_object_id(
        self,
        profile: DbProfile,
        *,
        schema: str,
        name: str,
        object_type: str | None,
        tool_name: str,
    ) -> int:
        type_filter = _object_type_filter(object_type)
        rows = self._query(
            profile.database,
            f"""
            SELECT
                o.object_id
            FROM sys.objects AS o
            INNER JOIN sys.schemas AS s ON o.schema_id = s.schema_id
            WHERE s.name = %s
                AND o.name = %s
                {type_filter}
                AND o.is_ms_shipped = 0
            """,
            [schema, name],
            tool_name=tool_name,
            profile=profile,
        )
        if not rows:
            raise _object_not_found(object_type or "OBJECT", schema, name)
        return int(rows[0]["object_id"])

    def _ensure_column_exists(
        self,
        profile: DbProfile,
        *,
        schema: str,
        table_name: str,
        column_name: str,
        tool_name: str,
    ) -> None:
        rows = self._query(
            profile.database,
            """
            SELECT
                c.column_id
            FROM sys.tables AS t
            INNER JOIN sys.schemas AS s ON t.schema_id = s.schema_id
            INNER JOIN sys.columns AS c ON t.object_id = c.object_id
            WHERE s.name = %s
                AND t.name = %s
                AND c.name = %s
                AND t.is_ms_shipped = 0
            """,
            [schema, table_name, column_name],
            tool_name=tool_name,
            profile=profile,
        )
        if not rows:
            raise _object_not_found("COLUMN", schema, f"{table_name}.{column_name}")

    def _dependencies_for_object(
        self,
        profile: DbProfile,
        *,
        object_id: int,
        tool_name: str,
    ) -> list[dict[str, Any]]:
        rows = self._query(
            profile.database,
            """
            SELECT
                dep.referencing_id AS object_id,
                COALESCE(rs.name, dep_rs.name, dep.referenced_schema_name) AS schema_name,
                COALESCE(ro.name, dep_ro.name, dep.referenced_entity_name) AS object_name,
                COALESCE(ro.type, dep_ro.type) AS referenced_type,
                dep.referenced_class_desc,
                dep.is_ambiguous
            FROM sys.sql_expression_dependencies AS dep
            LEFT JOIN sys.objects AS ro ON dep.referenced_id = ro.object_id
            LEFT JOIN sys.schemas AS rs ON ro.schema_id = rs.schema_id
            LEFT JOIN sys.schemas AS dep_rs ON dep.referenced_schema_name = dep_rs.name
            LEFT JOIN sys.objects AS dep_ro
                ON dep_rs.schema_id = dep_ro.schema_id
                AND dep.referenced_entity_name = dep_ro.name
            WHERE dep.referencing_id = %s
            ORDER BY schema_name, object_name
            """,
            [object_id],
            tool_name=tool_name,
            profile=profile,
        )
        return [item for values in _group_dependencies(rows).values() for item in values]

    def _referrers_for_object(
        self,
        profile: DbProfile,
        *,
        object_id: int,
        schema: str,
        name: str,
        tool_name: str,
    ) -> list[dict[str, Any]]:
        rows = self._query(
            profile.database,
            """
            SELECT DISTINCT
                s.name AS schema_name,
                o.name AS object_name,
                o.type AS object_type,
                dep.is_ambiguous
            FROM sys.sql_expression_dependencies AS dep
            INNER JOIN sys.objects AS o ON dep.referencing_id = o.object_id
            INNER JOIN sys.schemas AS s ON o.schema_id = s.schema_id
            WHERE dep.referenced_id = %s
                OR (
                    dep.referenced_schema_name = %s
                    AND dep.referenced_entity_name = %s
                )
            ORDER BY s.name, o.name
            """,
            [object_id, schema, name],
            tool_name=tool_name,
            profile=profile,
        )
        return [
            {
                "objectType": _map_object_type(row.get("object_type")),
                "schema": row.get("schema_name"),
                "name": row.get("object_name"),
                "relationship": "REFERENCED_BY",
                "dependencyType": "REFERENCE",
                "isAmbiguous": bool(row.get("is_ambiguous")),
                "reviewStatus": "REVIEW_REQUIRED"
                if row.get("is_ambiguous")
                else "CONFIRMED",
            }
            for row in rows
        ]

    def _searchable_live_tables(
        self,
        profile: DbProfile,
        *,
        tool_name: str,
    ) -> list[dict[str, Any]]:
        rows = self._query(
            profile.database,
            """
            SELECT
                t.object_id,
                s.name AS schema_name,
                t.name AS table_name,
                CONVERT(nvarchar(4000), table_ep.value) AS table_description,
                c.name AS column_name,
                ty.name AS type_name,
                c.max_length,
                c.precision,
                c.scale,
                c.column_id,
                c.is_nullable,
                c.is_identity,
                CONVERT(nvarchar(4000), column_ep.value) AS column_description
            FROM sys.tables AS t
            INNER JOIN sys.schemas AS s ON t.schema_id = s.schema_id
            INNER JOIN sys.columns AS c ON t.object_id = c.object_id
            INNER JOIN sys.types AS ty ON c.user_type_id = ty.user_type_id
            LEFT JOIN sys.extended_properties AS table_ep
                ON table_ep.major_id = t.object_id
                AND table_ep.minor_id = 0
                AND table_ep.name = 'MS_Description'
            LEFT JOIN sys.extended_properties AS column_ep
                ON column_ep.major_id = c.object_id
                AND column_ep.minor_id = c.column_id
                AND column_ep.name = 'MS_Description'
            WHERE t.is_ms_shipped = 0
            ORDER BY s.name, t.name, c.column_id
            """,
            [],
            tool_name=tool_name,
            profile=profile,
        )
        tables: dict[int, dict[str, Any]] = {}
        for row in rows:
            table = tables.setdefault(
                int(row["object_id"]),
                {
                    "schema": row["schema_name"],
                    "name": row["table_name"],
                    "logicalName": None,
                    "description": row.get("table_description"),
                    "descriptionStatus": "CONFIRMED"
                    if row.get("table_description")
                    else "REVIEW_REQUIRED",
                    "columns": [],
                },
            )
            table["columns"].append(
                {
                    "name": row["column_name"],
                    "logicalName": None,
                    "description": row.get("column_description"),
                    "descriptionStatus": "CONFIRMED"
                    if row.get("column_description")
                    else "REVIEW_REQUIRED",
                    "dataType": _format_data_type(row),
                    "ordinal": row["column_id"],
                    "isNullable": bool(row.get("is_nullable")),
                    "isIdentity": bool(row.get("is_identity")),
                    "isPrimaryKey": False,
                }
            )
        return list(tables.values())

    @staticmethod
    def _single_row(
        rows: list[dict[str, Any]],
        *,
        object_type: str,
        schema: str,
        name: str,
    ) -> dict[str, Any]:
        if not rows:
            raise _object_not_found(object_type, schema, name)
        return rows[0]

    def _profile(self, profile_id: str) -> DbProfile:
        profiles = self.profiles or load_db_profiles(self.settings, repo_root=repo_root())
        for profile in profiles:
            if profile.id == profile_id:
                return profile
        raise MetadataToolError(
            OBJECT_NOT_FOUND,
            "Unknown dbProfileId in live metadata repository.",
            {"dbProfileId": profile_id},
        )

    def _connect(self, database: str, *, profile: DbProfile, tool_name: str) -> Any:
        missing = []
        if not self.settings.metadata_host:
            missing.append("MSSQL_METADATA_HOST")
        if not self.settings.metadata_user:
            missing.append("MSSQL_METADATA_USER")
        if not self.settings.metadata_password:
            missing.append("MSSQL_METADATA_PASSWORD")
        if missing:
            raise MetadataToolError(
                LIVE_METADATA_UNAVAILABLE,
                "Missing live metadata configuration.",
                {
                    "toolName": tool_name,
                    "dbProfileId": profile.id,
                    "database": database,
                    "missingSettingsCount": len(missing),
                    "timeoutSeconds": self.settings.connect_timeout_seconds,
                    "attempt": 1,
                },
            )
        try:
            import pytds
        except Exception as exc:  # pragma: no cover - dependency/runtime issue
            raise MetadataToolError(
                LIVE_METADATA_UNAVAILABLE,
                "python-tds is required for live MSSQL metadata connectivity.",
                {
                    "toolName": tool_name,
                    "dbProfileId": profile.id,
                    "database": database,
                    "timeoutSeconds": self.settings.connect_timeout_seconds,
                    "attempt": 1,
                },
            ) from exc
        try:
            return pytds.connect(
                server=self.settings.metadata_host,
                port=self.settings.metadata_port,
                database=database,
                user=self.settings.metadata_user,
                password=self.settings.metadata_password,
                login_timeout=self.settings.connect_timeout_seconds,
                timeout=self.settings.connect_timeout_seconds,
                readonly=True,
                autocommit=True,
                appname="mssql-mcp-metadata-discovery",
                use_mars=False,
            )
        except Exception as exc:  # pragma: no cover - requires live SQL Server
            self._raise_connection_error(
                exc,
                database=database,
                profile=profile,
                tool_name=tool_name,
            )

    def _query(
        self,
        database: str,
        sql: str,
        params: list[Any],
        *,
        tool_name: str,
        profile: DbProfile,
    ) -> list[dict[str, Any]]:
        connection = self._connect(database, profile=profile, tool_name=tool_name)
        cursor = None
        try:
            cursor = connection.cursor()
            cursor.execute(sql, tuple(params))
            columns = [column[0] for column in cursor.description or []]
            return [dict(zip(columns, row, strict=False)) for row in cursor.fetchall()]
        except Exception as exc:  # pragma: no cover - requires live SQL Server
            text = str(exc).lower()
            if "definition" in text and "denied" in text:
                code = SP_DEFINITION_ACCESS_DENIED
            elif "permission" in text or "denied" in text:
                code = METADATA_READ_ONLY_PERMISSION_INSUFFICIENT
            else:
                code = LIVE_METADATA_UNAVAILABLE
            raise MetadataToolError(
                code,
                "Live metadata catalog query failed.",
                {
                    "toolName": tool_name,
                    "dbProfileId": profile.id,
                    "database": database,
                    "timeoutSeconds": self.settings.connect_timeout_seconds,
                    "attempt": 1,
                    "errorClass": exc.__class__.__name__,
                },
            ) from exc
        finally:
            if cursor is not None:
                cursor.close()
            connection.close()

    def _raise_connection_error(
        self,
        exc: Exception,
        *,
        database: str,
        profile: DbProfile,
        tool_name: str,
    ) -> None:
        text = str(exc).lower()
        code = LIVE_METADATA_UNAVAILABLE
        if profile.id == "ppm":
            if "not exist" in text or "not found" in text or "cannot open database" in text:
                code = PPM_DB_NOT_FOUND
            if "access" in text or "permission" in text or "denied" in text:
                code = PPM_DB_ACCESS_DENIED
        raise MetadataToolError(
            code,
            "Live metadata connection could not be established.",
            {
                "toolName": tool_name,
                "dbProfileId": profile.id,
                "database": database,
                "timeoutSeconds": self.settings.connect_timeout_seconds,
                "attempt": 1,
                "errorClass": exc.__class__.__name__,
            },
        ) from exc

    def _live_result(
        self,
        arguments: dict[str, Any],
        *,
        data: dict[str, Any],
        evidence_refs: list[dict[str, Any]],
    ) -> MetadataToolResult:
        collected_at = datetime.now(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")
        snapshot_id = f"live:{arguments['dbProfileId']}:{collected_at}"
        return MetadataToolResult(
            snapshot_id=snapshot_id,
            collected_at=collected_at,
            evidence_refs=evidence_refs,
            data=data,
        )

    @staticmethod
    def _live_evidence(
        evidence_id: str,
        object_type: str,
        schema: str,
        name: str,
        source: str,
    ) -> dict[str, Any]:
        object_name = f"{schema}.{name}" if schema != "*" else name
        return {
            "id": f"ev:live:{evidence_id}:{object_name}",
            "source": "live-mssql-metadata",
            "path": source,
            "objectType": object_type,
            "objectName": object_name,
        }


def _schema_filter(arguments: dict[str, Any]) -> tuple[str, list[Any]]:
    schema = arguments.get("schema")
    if schema:
        return " AND s.name = %s", [schema]
    return "", []


def _group_parameters(rows: list[dict[str, Any]]) -> dict[Any, list[dict[str, Any]]]:
    grouped: dict[Any, list[dict[str, Any]]] = {}
    for row in rows:
        grouped.setdefault(row["object_id"], []).append(
            {
                "name": row["name"],
                "dataType": row["data_type"],
                "direction": "OUT" if row.get("is_output") else "IN",
                "ordinal": row["ordinal"],
                "isNullable": None,
                "hasDefault": bool(row.get("has_default_value")),
                "defaultValue": row.get("default_value"),
            }
        )
    return grouped


def _group_dependencies(rows: list[dict[str, Any]]) -> dict[Any, list[dict[str, Any]]]:
    grouped: dict[Any, list[dict[str, Any]]] = {}
    for row in rows:
        if not row.get("object_name"):
            continue
        grouped.setdefault(row["object_id"], []).append(
            {
                "objectType": _map_object_type(row.get("referenced_type")),
                "schema": row.get("schema_name"),
                "name": row.get("object_name"),
                "dependencyType": "REFERENCE",
                "isAmbiguous": bool(row.get("is_ambiguous")),
                "reviewStatus": "REVIEW_REQUIRED"
                if row.get("is_ambiguous")
                else "CONFIRMED",
            }
        )
    return grouped


def _map_object_type(sql_server_type: Any) -> str:
    return {
        "U": "TABLE",
        "V": "VIEW",
        "P": "PROCEDURE",
        "PC": "PROCEDURE",
        "FN": "FUNCTION",
        "IF": "FUNCTION",
        "TF": "FUNCTION",
        "FS": "FUNCTION",
        "FT": "FUNCTION",
    }.get(str(sql_server_type), "UNKNOWN")


def _object_type_filter(object_type: str | None) -> str:
    if object_type is None:
        return ""
    return {
        "TABLE": "AND o.type = 'U'",
        "VIEW": "AND o.type = 'V'",
        "PROCEDURE": "AND o.type IN ('P', 'PC')",
        "FUNCTION": "AND o.type IN ('FN', 'IF', 'TF', 'FS', 'FT')",
    }.get(str(object_type).upper(), "")


def _format_data_type(row: dict[str, Any]) -> str:
    type_name = str(row["type_name"]).upper()
    max_length = row.get("max_length")
    precision = row.get("precision")
    scale = row.get("scale")
    if type_name in {"VARCHAR", "CHAR", "VARBINARY", "BINARY"}:
        length = "MAX" if max_length == -1 else str(max_length)
        return f"{type_name}({length})"
    if type_name in {"NVARCHAR", "NCHAR"}:
        length = "MAX" if max_length == -1 else str(int(max_length or 0) // 2)
        return f"{type_name}({length})"
    if type_name in {"DECIMAL", "NUMERIC"}:
        return f"{type_name}({precision},{scale})"
    if type_name in {"DATETIME2", "TIME", "DATETIMEOFFSET"} and scale is not None:
        return f"{type_name}({scale})"
    return type_name


def _group_key_constraints(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        constraint = grouped.setdefault(
            row["name"],
            {
                "name": row["name"],
                "constraintType": "PK" if row["type"] == "PK" else "UQ",
                "columns": [],
                "referencedObject": None,
            },
        )
        constraint["columns"].append(row["column_name"])
    return list(grouped.values())


def _group_foreign_keys(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        constraint = grouped.setdefault(
            row["name"],
            {
                "name": row["name"],
                "constraintType": "FK",
                "columns": [],
                "referencedObject": {
                    "schema": row["referenced_schema"],
                    "tableName": row["referenced_table"],
                    "columns": [],
                },
            },
        )
        constraint["columns"].append(row["column_name"])
        constraint["referencedObject"]["columns"].append(row["referenced_column"])
    return list(grouped.values())


def _group_check_constraints(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "name": row["name"],
            "constraintType": "CHECK",
            "columns": [],
            "referencedObject": None,
            "definition": row.get("definition"),
        }
        for row in rows
    ]


def _group_indexes(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for row in rows:
        index = grouped.setdefault(
            row["name"],
            {
                "name": row["name"],
                "isUnique": bool(row.get("is_unique")),
                "indexType": row.get("type_desc"),
                "keyColumns": [],
                "includedColumns": [],
            },
        )
        target = "includedColumns" if row.get("is_included_column") else "keyColumns"
        index[target].append(row["column_name"])
    return list(grouped.values())


def _object_not_found(object_type: str, schema: str, name: str) -> MetadataToolError:
    return MetadataToolError(
        OBJECT_NOT_FOUND,
        "Requested metadata object was not found in the active repository.",
        {"objectType": object_type, "schema": schema, "name": name},
    )


def _same(left: Any, right: Any) -> bool:
    return str(left).lower() == str(right).lower()


def _matches(needle: str, value: Any) -> bool:
    return needle.lower() in str(value).lower()


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


def _live_table_candidate(
    repository: Any,
    table: dict[str, Any],
    score: int,
    index: int,
) -> dict[str, Any]:
    return {
        "schema": table["schema"],
        "tableName": table["name"],
        "logicalName": table.get("logicalName"),
        "description": table.get("description"),
        "descriptionStatus": table.get("descriptionStatus", "CONFIRMED"),
        "score": score,
        "evidenceRefs": [
            repository._live_evidence(
                "table",
                "TABLE",
                table["schema"],
                table["name"],
                f"sys.tables[{index}]",
            )
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


def _dependency_caveats(dependencies: list[dict[str, Any]]) -> list[str]:
    for dependency in dependencies:
        if dependency.get("reviewStatus") == "REVIEW_REQUIRED":
            return ["DEPENDENCY_METADATA_INCOMPLETE"]
        if dependency.get("isAmbiguous") is True:
            return ["DEPENDENCY_METADATA_INCOMPLETE"]
        if dependency.get("objectType") in {None, "", "UNKNOWN"}:
            return ["DEPENDENCY_METADATA_INCOMPLETE"]
        if not dependency.get("name"):
            return ["DEPENDENCY_METADATA_INCOMPLETE"]
    return []
