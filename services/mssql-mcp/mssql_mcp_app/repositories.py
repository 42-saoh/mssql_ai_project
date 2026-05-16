from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Protocol

from mssql_mcp_app.catalog import repo_root
from mssql_mcp_app.errors import (
    DEPENDENCY_METADATA_INCOMPLETE,
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


EXTERNAL_CATALOG_LOCK_TIMEOUT_MS = 1000


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
        data = _attach_snapshot_to_results(data, self.snapshot_id)
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
            procedure_item = {
                **procedure,
                "dependencies": _fixture_dependency_items(
                    self,
                    procedure.get("dependencies", []),
                    base_path=f"/procedures/{index}/dependencies",
                    source_database=source_database_for_profile(
                        arguments["dbProfileId"],
                        payload=self.payload,
                    ),
                ),
            }
            procedures.append(procedure_inventory_item(procedure_item, evidence_refs=[evidence]))
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

    def _handle_search_metadata_objects(self, arguments: dict[str, Any]) -> MetadataToolResult:
        query = arguments["query"]
        object_types = _search_object_types(arguments)
        limit = _search_limit(arguments)
        context = source_context(arguments, payload=self.payload)
        results: list[dict[str, Any]] = []

        if "PROCEDURE" in object_types:
            for index, procedure in enumerate(self.payload.get("procedures", [])):
                evidence = self._evidence(
                    "procedure-search",
                    "PROCEDURE",
                    procedure["schema"],
                    procedure["name"],
                    f"/procedures/{index}",
                )
                procedure_item = {
                    **procedure,
                    "dependencies": _fixture_dependency_items(
                        self,
                        procedure.get("dependencies", []),
                        base_path=f"/procedures/{index}/dependencies",
                        source_database=context["sourceDatabase"],
                    ),
                }
                item = procedure_inventory_item(procedure_item, evidence_refs=[evidence])
                score = _metadata_search_score(item, query)
                if score > 0:
                    item["score"] = score
                    results.append(_metadata_search_result_item(item, context=context))

        if "TABLE" in object_types:
            for index, table in enumerate(self.payload.get("tables", [])):
                evidence = self._evidence(
                    "table-search",
                    "TABLE",
                    table["schema"],
                    table["name"],
                    f"/tables/{index}",
                )
                item = table_inventory_item(
                    table,
                    related_procedures=self._related_for_table(table["schema"], table["name"]),
                    evidence_refs=[evidence],
                )
                score = _metadata_search_score(item, query)
                if score > 0:
                    item["score"] = score
                    results.append(_metadata_search_result_item(item, context=context))

        if "VIEW" in object_types:
            for index, view in enumerate(self.payload.get("views", [])):
                evidence = self._evidence(
                    "view-search",
                    "VIEW",
                    view["schema"],
                    view["name"],
                    f"/views/{index}",
                )
                item = module_inventory_item(view, object_type="VIEW", evidence_refs=[evidence])
                score = _metadata_search_score(item, query)
                if score > 0:
                    item["score"] = score
                    results.append(_metadata_search_result_item(item, context=context))

        if "FUNCTION" in object_types:
            for index, function in enumerate(self.payload.get("functions", [])):
                evidence = self._evidence(
                    "function-search",
                    "FUNCTION",
                    function["schema"],
                    function["name"],
                    f"/functions/{index}",
                )
                item = module_inventory_item(
                    function,
                    object_type="FUNCTION",
                    evidence_refs=[evidence],
                )
                score = _metadata_search_score(item, query)
                if score > 0:
                    item["score"] = score
                    results.append(_metadata_search_result_item(item, context=context))

        results.sort(
            key=lambda item: (
                -item["score"],
                item["objectIdentity"]["type"],
                item["objectIdentity"]["schema"],
                item["objectIdentity"]["name"],
            )
        )
        results = [_without_score(item) for item in results[:limit]]
        caveats = _metadata_search_caveats(results)
        blockers = _blockers_for_caveats(caveats)
        evidence = self._evidence(
            "metadata-object-search",
            "CATALOG",
            "*",
            "metadata_objects",
            "/",
        )
        data = {
            **context,
            "query": query,
            "objectTypes": object_types,
            "limit": limit,
            "results": results,
            "caveats": caveats,
            "reviewRequired": bool(caveats or blockers),
            "blockers": blockers,
        }
        return self._result(data=data, evidence_refs=[evidence])

    def _handle_get_procedure_definition(self, arguments: dict[str, Any]) -> MetadataToolResult:
        referenced_database = arguments.get("referencedDatabase")
        source_database = source_database_for_profile(
            arguments["dbProfileId"],
            payload=self.payload,
        )
        lookup_database = (
            referenced_database
            if referenced_database and not _same(referenced_database, source_database)
            else None
        )
        procedure, index = self._find_procedure(
            arguments["schema"],
            arguments["procedureName"],
            database=lookup_database,
        )
        definition_database = procedure.get("database") or referenced_database or source_database
        source_scope = (
            "SAME_SERVER_CROSS_DATABASE"
            if referenced_database and not _same(referenced_database, source_database)
            else "SAME_DATABASE"
        )
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
            "database": definition_database,
            "schema": procedure["schema"],
            "procedureName": procedure["name"],
            "referencedDatabase": referenced_database,
            "sourceScope": source_scope,
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
        dependencies = _fixture_dependency_items(
            self,
            procedure.get("dependencies", []),
            base_path=f"/procedures/{index}/dependencies",
            source_database=source_database_for_profile(
                arguments["dbProfileId"],
                payload=self.payload,
            ),
        )
        evidence = self._evidence(
            "procedure-dependencies",
            "PROCEDURE",
            procedure["schema"],
            procedure["name"],
            f"/procedures/{index}/dependencies",
        )
        caveats = _dependency_caveats(dependencies)
        data = {
            "schema": procedure["schema"],
            "procedureName": procedure["name"],
            "dependencies": dependencies,
            "dependencySummary": procedure_dependency_summary(dependencies),
            "caveats": caveats,
            "reviewRequired": bool(caveats),
            "snapshotMode": arguments.get("snapshotMode", "LATEST"),
        }
        return self._result(data=data, evidence_refs=[evidence])

    def _handle_get_dependency_closure(self, arguments: dict[str, Any]) -> MetadataToolResult:
        source_database = source_database_for_profile(
            arguments["dbProfileId"],
            payload=self.payload,
        )
        source, index = self._find_dependency_source(
            arguments["objectType"],
            arguments["schema"],
            arguments["objectName"],
        )
        root_evidence = self._evidence(
            "dependency-closure-root",
            arguments["objectType"],
            source["schema"],
            source["name"],
            f"/{_collection_name(arguments['objectType'])}/{index}",
        )

        def fetch_dependencies(object_type: str, schema: str, name: str) -> list[dict[str, Any]]:
            dependency_source, dependency_index = self._find_dependency_source(
                object_type,
                schema,
                name,
            )
            return _fixture_dependency_items(
                self,
                dependency_source.get("dependencies", []),
                base_path=f"/{_collection_name(object_type)}/{dependency_index}/dependencies",
                source_database=source_database,
            )

        data = _dependency_closure_payload(
            root_object={
                "database": source_database,
                "server": None,
                "schema": source["schema"],
                "name": source["name"],
                "objectType": arguments["objectType"],
            },
            root_evidence_refs=[root_evidence],
            fetch_dependencies=fetch_dependencies,
            max_depth=arguments.get("maxDepth", 2),
            include_review_required=arguments.get("includeReviewRequired", True),
        )
        return self._result(data=data, evidence_refs=[root_evidence])

    def _handle_resolve_dependency_reference(
        self,
        arguments: dict[str, Any],
    ) -> MetadataToolResult:
        source_object = arguments["sourceObject"]
        source_database = source_object.get("database") or source_database_for_profile(
            arguments["dbProfileId"],
            payload=self.payload,
        )
        source, index = self._find_dependency_source(
            source_object["objectType"],
            source_object["schema"],
            source_object["name"],
        )
        dependencies = _fixture_dependency_items(
            self,
            source.get("dependencies", []),
            base_path=f"/{_collection_name(source_object['objectType'])}/{index}/dependencies",
            source_database=source_database,
        )
        evidence = self._evidence(
            "dependency-reference-resolver",
            source_object["objectType"],
            source["schema"],
            source["name"],
            f"/{_collection_name(source_object['objectType'])}/{index}/dependencies",
        )
        data = _dependency_reference_resolution_payload(
            dependencies,
            referenced_name=arguments["referencedName"],
            referenced_schema=arguments.get("referencedSchema"),
            referenced_database=arguments.get("referencedDatabase"),
            referenced_server=arguments.get("referencedServer"),
            fallback_evidence_refs=[evidence],
        )
        return self._result(data=data, evidence_refs=data["evidenceRefs"] or [evidence])

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

    def _find_procedure(
        self,
        schema: str,
        name: str,
        *,
        database: str | None = None,
    ) -> tuple[dict[str, Any], int]:
        return self._find_in_collection("procedures", schema, name, "PROCEDURE", database=database)

    def _find_table(self, schema: str, name: str) -> tuple[dict[str, Any], int]:
        return self._find_in_collection("tables", schema, name, "TABLE")

    def _find_view(self, schema: str, name: str) -> tuple[dict[str, Any], int]:
        return self._find_in_collection("views", schema, name, "VIEW")

    def _find_function(self, schema: str, name: str) -> tuple[dict[str, Any], int]:
        return self._find_in_collection("functions", schema, name, "FUNCTION")

    def _find_dependency_source(
        self,
        object_type: str,
        schema: str,
        name: str,
    ) -> tuple[dict[str, Any], int]:
        if object_type == "PROCEDURE":
            return self._find_procedure(schema, name)
        if object_type == "VIEW":
            return self._find_view(schema, name)
        if object_type == "FUNCTION":
            return self._find_function(schema, name)
        raise MetadataToolError(
            OBJECT_NOT_FOUND,
            "Dependency evidence source must be a procedure, view, or function.",
            {"objectType": object_type, "schema": schema, "name": name},
        )

    def _find_in_collection(
        self,
        collection: str,
        schema: str,
        name: str,
        object_type: str,
        *,
        database: str | None = None,
    ) -> tuple[dict[str, Any], int]:
        for index, item in enumerate(self.payload.get(collection, [])):
            if database and not _same(item.get("database"), database):
                continue
            if _same(item.get("schema"), schema) and _same(item.get("name"), name):
                return item, index
        raise MetadataToolError(
            OBJECT_NOT_FOUND,
            "Requested metadata object was not found in the active repository.",
            {
                "objectType": object_type,
                "database": database,
                "schema": schema,
                "name": name,
            },
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
        self._catalog_database_cache: dict[str, dict[str, Any]] = {}
        self._external_dependency_cache: dict[tuple[str, str | None, str], dict[str, Any]] = {}

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
        top_k = int(arguments.get("topK", 100))
        selected_procedures_cte = f"""
            WITH selected_procedures AS (
                SELECT TOP (%s)
                    s.name AS schema_name,
                    p.name AS object_name,
                    p.object_id
                FROM sys.procedures AS p
                INNER JOIN sys.schemas AS s ON p.schema_id = s.schema_id
                WHERE p.is_ms_shipped = 0{schema_filter}
                ORDER BY s.name, p.name
            )
        """
        selected_procedure_params = [top_k, *params]
        rows = self._query(
            profile.database,
            f"""
            {selected_procedures_cte}
            SELECT
                sp.schema_name,
                sp.object_name,
                sp.object_id,
                CONVERT(int, OBJECTPROPERTY(sp.object_id, 'IsEncrypted')) AS is_encrypted,
                m.definition
            FROM selected_procedures AS sp
            LEFT JOIN sys.sql_modules AS m ON sp.object_id = m.object_id
            ORDER BY sp.schema_name, sp.object_name
            """,
            selected_procedure_params,
            tool_name="list_procedures",
            profile=profile,
        )
        parameter_rows = self._query(
            profile.database,
            f"""
            {selected_procedures_cte}
            SELECT
                sp.object_id,
                prm.name,
                TYPE_NAME(prm.user_type_id) AS data_type,
                prm.parameter_id AS ordinal,
                prm.is_output,
                prm.has_default_value,
                CONVERT(nvarchar(4000), prm.default_value) AS default_value
            FROM selected_procedures AS sp
            INNER JOIN sys.parameters AS prm ON sp.object_id = prm.object_id
            ORDER BY sp.object_id, prm.parameter_id
            """,
            selected_procedure_params,
            tool_name="list_procedures",
            profile=profile,
        )
        dependency_rows = self._query(
            profile.database,
            f"""
            {selected_procedures_cte}
            SELECT
                sp.object_id,
                dep.referenced_id,
                dep.referenced_server_name,
                dep.referenced_database_name,
                dep.referenced_schema_name,
                dep.referenced_entity_name,
                dep.referenced_class_desc,
                dep.is_ambiguous,
                dep.is_caller_dependent,
                direct_s.name AS direct_schema_name,
                direct_o.name AS direct_object_name,
                direct_o.type AS direct_object_type,
                match_info.match_count AS catalog_match_count,
                match_s.name AS matched_schema_name,
                match_o.name AS matched_object_name,
                match_o.type AS matched_object_type,
                syn_s.name AS synonym_schema_name,
                syn.name AS synonym_name,
                syn.base_object_name AS synonym_base_object_name
            FROM selected_procedures AS sp
            INNER JOIN sys.sql_expression_dependencies AS dep
                ON sp.object_id = dep.referencing_id
            LEFT JOIN sys.objects AS direct_o ON dep.referenced_id = direct_o.object_id
            LEFT JOIN sys.schemas AS direct_s ON direct_o.schema_id = direct_s.schema_id
            OUTER APPLY (
                SELECT
                    COUNT(*) AS match_count,
                    MIN(candidate.object_id) AS match_object_id
                FROM sys.objects AS candidate
                INNER JOIN sys.schemas AS candidate_schema
                    ON candidate.schema_id = candidate_schema.schema_id
                WHERE dep.referenced_server_name IS NULL
                    AND dep.referenced_database_name IS NULL
                    AND dep.referenced_entity_name IS NOT NULL
                    AND candidate.is_ms_shipped = 0
                    AND candidate.type IN (
                        'U', 'V', 'P', 'PC', 'FN', 'IF', 'TF', 'FS', 'FT', 'SN'
                    )
                    AND candidate.name = dep.referenced_entity_name
                    AND (
                        dep.referenced_schema_name IS NULL
                        OR candidate_schema.name = dep.referenced_schema_name
                    )
            ) AS match_info
            LEFT JOIN sys.objects AS match_o
                ON match_info.match_count = 1
                AND match_o.object_id = match_info.match_object_id
            LEFT JOIN sys.schemas AS match_s ON match_o.schema_id = match_s.schema_id
            LEFT JOIN sys.synonyms AS syn
                ON syn.object_id = COALESCE(direct_o.object_id, match_o.object_id)
            LEFT JOIN sys.schemas AS syn_s ON syn.schema_id = syn_s.schema_id
            ORDER BY
                sp.object_id,
                COALESCE(direct_s.name, match_s.name, dep.referenced_schema_name),
                COALESCE(direct_o.name, match_o.name, dep.referenced_entity_name)
            """,
            selected_procedure_params,
            tool_name="list_procedures",
            profile=profile,
        )
        parameters_by_object = _group_parameters(parameter_rows)
        dependency_rows = self._resolve_external_dependency_rows(
            profile,
            dependency_rows,
            tool_name="list_procedures",
        )
        dependencies_by_object = _group_live_dependencies(
            dependency_rows,
            source_database=profile.database,
        )
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
                "procedures": procedures,
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

    def _handle_search_metadata_objects(self, arguments: dict[str, Any]) -> MetadataToolResult:
        profile = self._profile(arguments["dbProfileId"])
        object_types = _search_object_types(arguments)
        limit = _search_limit(arguments)
        type_codes = _search_sql_type_codes(object_types)
        type_placeholders = ", ".join(["%s"] * len(type_codes))
        pattern = f"%{arguments['query']}%"
        rows = self._query(
            profile.database,
            f"""
            SELECT
                o.object_id,
                o.type AS object_type,
                s.name AS schema_name,
                o.name AS object_name,
                CONVERT(nvarchar(4000), ep.value) AS description,
                COALESCE(rs.name, dep_rs.name, dep.referenced_schema_name) AS dep_schema_name,
                COALESCE(ro.name, dep_ro.name, dep.referenced_entity_name) AS dep_object_name,
                COALESCE(ro.type, dep_ro.type) AS dep_referenced_type,
                dep.referenced_class_desc,
                dep.is_ambiguous
            FROM sys.objects AS o
            INNER JOIN sys.schemas AS s ON o.schema_id = s.schema_id
            LEFT JOIN sys.extended_properties AS ep
                ON ep.major_id = o.object_id
                AND ep.minor_id = 0
                AND ep.name = 'MS_Description'
            LEFT JOIN sys.sql_expression_dependencies AS dep
                ON o.object_id = dep.referencing_id
            LEFT JOIN sys.objects AS ro ON dep.referenced_id = ro.object_id
            LEFT JOIN sys.schemas AS rs ON ro.schema_id = rs.schema_id
            LEFT JOIN sys.schemas AS dep_rs ON dep.referenced_schema_name = dep_rs.name
            LEFT JOIN sys.objects AS dep_ro
                ON dep_rs.schema_id = dep_ro.schema_id
                AND dep.referenced_entity_name = dep_ro.name
            WHERE o.is_ms_shipped = 0
                AND o.type IN ({type_placeholders})
                AND (
                    s.name LIKE %s
                    OR o.name LIKE %s
                    OR CONVERT(nvarchar(4000), ep.value) LIKE %s
                )
            ORDER BY s.name, o.name
            """,
            [*type_codes, pattern, pattern, pattern],
            tool_name="search_metadata_objects",
            profile=profile,
        )
        context = {"sourceProfile": profile.id, "sourceDatabase": profile.database}
        results = [
            _metadata_search_result_item(item, context=context)
            for item in _metadata_search_items_from_live_rows(self, rows)
        ]
        results.sort(
            key=lambda item: (
                item["objectIdentity"]["type"],
                item["objectIdentity"]["schema"],
                item["objectIdentity"]["name"],
            )
        )
        results = [_without_score(item) for item in results[:limit]]
        caveats = _metadata_search_caveats(results)
        blockers = _blockers_for_caveats(caveats)
        evidence = self._live_evidence(
            "metadata-object-search",
            "CATALOG",
            "*",
            "metadata_objects",
            "sys.objects,sys.schemas,sys.extended_properties,sys.sql_expression_dependencies",
        )
        return self._live_result(
            arguments,
            data={
                **context,
                "query": arguments["query"],
                "objectTypes": object_types,
                "limit": limit,
                "results": results,
                "caveats": caveats,
                "reviewRequired": bool(caveats or blockers),
                "blockers": blockers,
            },
            evidence_refs=[evidence],
        )

    def _handle_get_procedure_definition(
        self,
        arguments: dict[str, Any],
    ) -> MetadataToolResult:
        profile = self._profile(arguments["dbProfileId"])
        referenced_database = arguments.get("referencedDatabase")
        query_database = profile.database
        if referenced_database and not _same(referenced_database, profile.database):
            database_result = self._catalog_database(
                str(referenced_database),
                profile=profile,
                tool_name="get_procedure_definition",
            )
            query_database = str(database_result["external_database_name"])
        source_scope = (
            "SAME_SERVER_CROSS_DATABASE"
            if referenced_database and not _same(referenced_database, profile.database)
            else "SAME_DATABASE"
        )
        row = self._single_row(
            self._query(
                query_database,
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
                "database": query_database,
                "schema": row["schema_name"],
                "procedureName": row["object_name"],
                "referencedDatabase": referenced_database,
                "sourceScope": source_scope,
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
        object_id = self._ensure_object_id(
            profile,
            schema=arguments["schema"],
            name=arguments["procedureName"],
            object_type="PROCEDURE",
            tool_name="get_procedure_dependencies",
        )
        dependencies = self._dependencies_for_object(
            profile,
            object_id=object_id,
            tool_name="get_procedure_dependencies",
        )
        definition_info = self._module_dependency_metadata(
            profile,
            object_id=object_id,
            tool_name="get_procedure_dependencies",
        )
        module_evidence = self._live_evidence(
            "procedure-dependency-module-metadata",
            "PROCEDURE",
            arguments["schema"],
            arguments["procedureName"],
            "sys.sql_modules:hash-pattern",
        )
        if "dynamic_sql" in definition_info.get("detectedPatterns", []):
            dependencies.append(_dynamic_sql_dependency_item(module_evidence))
        evidence = self._live_evidence(
            "procedure-dependencies",
            "PROCEDURE",
            arguments["schema"],
            arguments["procedureName"],
            "sys.sql_expression_dependencies",
        )
        caveats = _dependency_caveats(dependencies)
        if definition_info.get("hasDefinitionAccess") is False:
            caveats.append("definition_unavailable")
        return self._live_result(
            arguments,
            data={
                "schema": arguments["schema"],
                "procedureName": arguments["procedureName"],
                "dependencies": dependencies,
                "definitionMetadata": definition_info,
                "dependencySummary": procedure_dependency_summary(dependencies),
                "caveats": list(dict.fromkeys(caveats)),
                "reviewRequired": bool(caveats),
                "snapshotMode": arguments.get("snapshotMode", "LATEST"),
            },
            evidence_refs=[evidence, module_evidence],
        )

    def _handle_get_dependency_closure(
        self,
        arguments: dict[str, Any],
    ) -> MetadataToolResult:
        profile = self._profile(arguments["dbProfileId"])
        root_object_id = self._ensure_object_id(
            profile,
            schema=arguments["schema"],
            name=arguments["objectName"],
            object_type=arguments["objectType"],
            tool_name="get_dependency_closure",
        )
        root_evidence = self._live_evidence(
            "dependency-closure-root",
            arguments["objectType"],
            arguments["schema"],
            arguments["objectName"],
            "sys.objects",
        )

        def fetch_dependencies(object_type: str, schema: str, name: str) -> list[dict[str, Any]]:
            object_id = (
                root_object_id
                if (
                    object_type == arguments["objectType"]
                    and _same(schema, arguments["schema"])
                    and _same(name, arguments["objectName"])
                )
                else self._ensure_object_id(
                    profile,
                    schema=schema,
                    name=name,
                    object_type=object_type,
                    tool_name="get_dependency_closure",
                )
            )
            dependencies = self._dependencies_for_object(
                profile,
                object_id=object_id,
                tool_name="get_dependency_closure",
            )
            if object_type == "PROCEDURE":
                definition_info = self._module_dependency_metadata(
                    profile,
                    object_id=object_id,
                    tool_name="get_dependency_closure",
                )
                if "dynamic_sql" in definition_info.get("detectedPatterns", []):
                    dependencies.append(
                        _dynamic_sql_dependency_item(
                            self._live_evidence(
                                "dependency-closure-module-metadata",
                                object_type,
                                schema,
                                name,
                                "sys.sql_modules:hash-pattern",
                            )
                        )
                    )
            return dependencies

        data = _dependency_closure_payload(
            root_object={
                "database": profile.database,
                "server": None,
                "schema": arguments["schema"],
                "name": arguments["objectName"],
                "objectType": arguments["objectType"],
            },
            root_evidence_refs=[root_evidence],
            fetch_dependencies=fetch_dependencies,
            max_depth=arguments.get("maxDepth", 2),
            include_review_required=arguments.get("includeReviewRequired", True),
        )
        return self._live_result(arguments, data=data, evidence_refs=[root_evidence])

    def _handle_resolve_dependency_reference(
        self,
        arguments: dict[str, Any],
    ) -> MetadataToolResult:
        profile = self._profile(arguments["dbProfileId"])
        source_object = arguments["sourceObject"]
        object_id = self._ensure_object_id(
            profile,
            schema=source_object["schema"],
            name=source_object["name"],
            object_type=source_object["objectType"],
            tool_name="resolve_dependency_reference",
        )
        dependencies = self._dependencies_for_object(
            profile,
            object_id=object_id,
            tool_name="resolve_dependency_reference",
        )
        if source_object["objectType"] == "PROCEDURE":
            definition_info = self._module_dependency_metadata(
                profile,
                object_id=object_id,
                tool_name="resolve_dependency_reference",
            )
            if "dynamic_sql" in definition_info.get("detectedPatterns", []):
                dependencies.append(
                    _dynamic_sql_dependency_item(
                        self._live_evidence(
                            "dependency-reference-module-metadata",
                            source_object["objectType"],
                            source_object["schema"],
                            source_object["name"],
                            "sys.sql_modules:hash-pattern",
                        )
                    )
                )
        evidence = self._live_evidence(
            "dependency-reference-resolver",
            source_object["objectType"],
            source_object["schema"],
            source_object["name"],
            "sys.sql_expression_dependencies",
        )
        data = _dependency_reference_resolution_payload(
            dependencies,
            referenced_name=arguments["referencedName"],
            referenced_schema=arguments.get("referencedSchema"),
            referenced_database=arguments.get("referencedDatabase"),
            referenced_server=arguments.get("referencedServer"),
            fallback_evidence_refs=[evidence],
        )
        return self._live_result(
            arguments,
            data=data,
            evidence_refs=data["evidenceRefs"] or [evidence],
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
                dep.referenced_id,
                dep.referenced_server_name,
                dep.referenced_database_name,
                dep.referenced_schema_name,
                dep.referenced_entity_name,
                dep.referenced_class_desc,
                dep.is_ambiguous,
                dep.is_caller_dependent,
                direct_s.name AS direct_schema_name,
                direct_o.name AS direct_object_name,
                direct_o.type AS direct_object_type,
                match_info.match_count AS catalog_match_count,
                match_s.name AS matched_schema_name,
                match_o.name AS matched_object_name,
                match_o.type AS matched_object_type,
                syn_s.name AS synonym_schema_name,
                syn.name AS synonym_name,
                syn.base_object_name AS synonym_base_object_name
            FROM sys.sql_expression_dependencies AS dep
            LEFT JOIN sys.objects AS direct_o ON dep.referenced_id = direct_o.object_id
            LEFT JOIN sys.schemas AS direct_s ON direct_o.schema_id = direct_s.schema_id
            OUTER APPLY (
                SELECT
                    COUNT(*) AS match_count,
                    MIN(candidate.object_id) AS match_object_id
                FROM sys.objects AS candidate
                INNER JOIN sys.schemas AS candidate_schema
                    ON candidate.schema_id = candidate_schema.schema_id
                WHERE dep.referenced_server_name IS NULL
                    AND dep.referenced_database_name IS NULL
                    AND dep.referenced_entity_name IS NOT NULL
                    AND candidate.is_ms_shipped = 0
                    AND candidate.type IN (
                        'U', 'V', 'P', 'PC', 'FN', 'IF', 'TF', 'FS', 'FT', 'SN'
                    )
                    AND candidate.name = dep.referenced_entity_name
                    AND (
                        dep.referenced_schema_name IS NULL
                        OR candidate_schema.name = dep.referenced_schema_name
                    )
            ) AS match_info
            LEFT JOIN sys.objects AS match_o
                ON match_info.match_count = 1
                AND match_o.object_id = match_info.match_object_id
            LEFT JOIN sys.schemas AS match_s ON match_o.schema_id = match_s.schema_id
            LEFT JOIN sys.synonyms AS syn
                ON syn.object_id = COALESCE(direct_o.object_id, match_o.object_id)
            LEFT JOIN sys.schemas AS syn_s ON syn.schema_id = syn_s.schema_id
            WHERE dep.referencing_id = %s
            ORDER BY
                COALESCE(direct_s.name, match_s.name, dep.referenced_schema_name),
                COALESCE(direct_o.name, match_o.name, dep.referenced_entity_name)
            """,
            [object_id],
            tool_name=tool_name,
            profile=profile,
        )
        rows = self._resolve_external_dependency_rows(profile, rows, tool_name=tool_name)
        return [
            item
            for values in _group_live_dependencies(
                rows,
                source_database=profile.database,
            ).values()
            for item in values
        ]

    def _resolve_external_dependency_rows(
        self,
        profile: DbProfile,
        rows: list[dict[str, Any]],
        *,
        tool_name: str,
    ) -> list[dict[str, Any]]:
        database_names: list[str] = []
        seen_database_names: set[str] = set()
        for row in rows:
            database_name = row.get("referenced_database_name")
            if database_name and not row.get("referenced_server_name"):
                normalized_database_name = str(database_name).lower()
                if normalized_database_name not in seen_database_names:
                    seen_database_names.add(normalized_database_name)
                    database_names.append(str(database_name))
        for database_name in database_names:
            self._catalog_database(
                database_name,
                profile=profile,
                tool_name=tool_name,
            )

        resolved = []
        for row in rows:
            item = dict(row)
            database_name = item.get("referenced_database_name")
            if database_name and not item.get("referenced_server_name"):
                item.update(
                    self._external_dependency_resolution(
                        profile,
                        database_name=str(database_name),
                        schema_name=item.get("referenced_schema_name"),
                        entity_name=item.get("referenced_entity_name"),
                        tool_name=tool_name,
                    )
                )
            resolved.append(item)
        return resolved

    def _external_dependency_resolution(
        self,
        profile: DbProfile,
        *,
        database_name: str,
        schema_name: Any,
        entity_name: Any,
        tool_name: str,
    ) -> dict[str, Any]:
        entity = str(entity_name or "").strip()
        schema = str(schema_name).strip() if schema_name else None
        cache_key = (database_name.lower(), schema.lower() if schema else None, entity.lower())
        if cache_key in self._external_dependency_cache:
            return dict(self._external_dependency_cache[cache_key])

        if not entity:
            result = {
                "external_resolution_status": "REVIEW_REQUIRED",
                "external_resolution_strategy": "CROSS_DATABASE_UNRESOLVED_ENTITY",
            }
            self._external_dependency_cache[cache_key] = result
            return dict(result)

        database_result = self._catalog_database(
            database_name,
            profile=profile,
            tool_name=tool_name,
        )

        catalog_database = str(database_result["external_database_name"])
        quoted_database = _quote_mssql_identifier(catalog_database)
        try:
            rows = self._query(
                profile.database,
                f"""
                SELECT
                    match_info.match_count AS external_catalog_match_count,
                    match_s.name AS external_matched_schema_name,
                    match_o.name AS external_matched_object_name,
                    match_o.type AS external_matched_object_type,
                    syn_s.name AS external_synonym_schema_name,
                    syn.name AS external_synonym_name,
                    syn.base_object_name AS external_synonym_base_object_name
                FROM (SELECT 1 AS marker) AS seed
                OUTER APPLY (
                    SELECT
                        COUNT(*) AS match_count,
                        MIN(candidate.object_id) AS match_object_id
                    FROM {quoted_database}.sys.objects AS candidate
                    INNER JOIN {quoted_database}.sys.schemas AS candidate_schema
                        ON candidate.schema_id = candidate_schema.schema_id
                    WHERE candidate.is_ms_shipped = 0
                        AND candidate.type IN (
                            'U', 'V', 'P', 'PC', 'FN', 'IF', 'TF', 'FS', 'FT', 'SN'
                        )
                        AND candidate.name = %s
                        AND (
                            %s IS NULL
                            OR candidate_schema.name = %s
                        )
                ) AS match_info
                LEFT JOIN {quoted_database}.sys.objects AS match_o
                    ON match_info.match_count = 1
                    AND match_o.object_id = match_info.match_object_id
                LEFT JOIN {quoted_database}.sys.schemas AS match_s
                    ON match_o.schema_id = match_s.schema_id
                LEFT JOIN {quoted_database}.sys.synonyms AS syn
                    ON syn.object_id = match_o.object_id
                LEFT JOIN {quoted_database}.sys.schemas AS syn_s
                    ON syn.schema_id = syn_s.schema_id
                """,
                [entity, schema, schema],
                tool_name=tool_name,
                profile=profile,
                lock_timeout_ms=EXTERNAL_CATALOG_LOCK_TIMEOUT_MS,
            )
        except MetadataToolError as exc:
            raise self._external_catalog_error(
                exc,
                profile=profile,
                tool_name=tool_name,
                external_database=catalog_database,
                stage="object_lookup",
            ) from exc

        row = rows[0] if rows else {}
        result = {
            **database_result,
            "external_catalog_match_count": int(row.get("external_catalog_match_count") or 0),
            "external_matched_schema_name": row.get("external_matched_schema_name"),
            "external_matched_object_name": row.get("external_matched_object_name"),
            "external_matched_object_type": row.get("external_matched_object_type"),
            "external_synonym_schema_name": row.get("external_synonym_schema_name"),
            "external_synonym_name": row.get("external_synonym_name"),
            "external_synonym_base_object_name": row.get("external_synonym_base_object_name"),
        }
        self._external_dependency_cache[cache_key] = result
        return dict(result)

    def _catalog_database(
        self,
        database_name: str,
        *,
        profile: DbProfile,
        tool_name: str,
    ) -> dict[str, Any]:
        cache_key = database_name.lower()
        if cache_key in self._catalog_database_cache:
            return dict(self._catalog_database_cache[cache_key])
        try:
            rows = self._query(
                profile.database,
                """
                SELECT
                    name,
                    state_desc
                FROM sys.databases
                WHERE name = %s
                """,
                [database_name],
                tool_name=tool_name,
                profile=profile,
                lock_timeout_ms=EXTERNAL_CATALOG_LOCK_TIMEOUT_MS,
            )
        except MetadataToolError as exc:
            raise self._external_catalog_error(
                exc,
                profile=profile,
                tool_name=tool_name,
                external_database=database_name,
                stage="database_lookup",
            ) from exc

        if not rows:
            raise self._external_catalog_blocker(
                profile=profile,
                tool_name=tool_name,
                external_database=database_name,
                stage="database_lookup",
                reason="not_found",
            )

        row = rows[0]
        if row.get("state_desc") and str(row["state_desc"]).upper() != "ONLINE":
            raise self._external_catalog_blocker(
                profile=profile,
                tool_name=tool_name,
                external_database=str(row["name"]),
                stage="database_state",
                reason="not_online",
                state_desc=str(row["state_desc"]),
            )

        result = {"external_database_name": row["name"]}
        self._catalog_database_cache[cache_key] = result
        return dict(result)

    def _external_catalog_error(
        self,
        exc: MetadataToolError,
        *,
        profile: DbProfile,
        tool_name: str,
        external_database: str,
        stage: str,
    ) -> MetadataToolError:
        code = (
            METADATA_READ_ONLY_PERMISSION_INSUFFICIENT
            if exc.code == METADATA_READ_ONLY_PERMISSION_INSUFFICIENT
            else LIVE_METADATA_UNAVAILABLE
        )
        details = {
            "toolName": tool_name,
            "dbProfileId": profile.id,
            "database": profile.database,
            "externalDatabase": external_database,
            "externalCatalogStage": stage,
            "timeoutSeconds": self.settings.connect_timeout_seconds,
            "attempt": 1,
            "rootErrorCode": exc.code,
        }
        if exc.details.get("errorClass"):
            details["errorClass"] = str(exc.details["errorClass"])
        return MetadataToolError(
            code,
            "External cross-database catalog metadata could not be confirmed.",
            details,
        )

    def _external_catalog_blocker(
        self,
        *,
        profile: DbProfile,
        tool_name: str,
        external_database: str,
        stage: str,
        reason: str,
        state_desc: str | None = None,
    ) -> MetadataToolError:
        details: dict[str, Any] = {
            "toolName": tool_name,
            "dbProfileId": profile.id,
            "database": profile.database,
            "externalDatabase": external_database,
            "externalCatalogStage": stage,
            "externalCatalogReason": reason,
            "timeoutSeconds": self.settings.connect_timeout_seconds,
            "attempt": 1,
        }
        if state_desc:
            details["externalDatabaseState"] = state_desc
        return MetadataToolError(
            LIVE_METADATA_UNAVAILABLE,
            "External cross-database catalog metadata could not be confirmed.",
            details,
        )

    def _module_dependency_metadata(
        self,
        profile: DbProfile,
        *,
        object_id: int,
        tool_name: str,
    ) -> dict[str, Any]:
        rows = self._query(
            profile.database,
            """
            SELECT
                CONVERT(
                    varchar(64),
                    HASHBYTES('SHA2_256', CONVERT(varbinary(max), m.definition)),
                    2
                ) AS definition_hash,
                LEN(m.definition) AS definition_length,
                CASE WHEN m.definition IS NULL THEN 0 ELSE 1 END AS has_definition_access,
                CASE
                    WHEN CHARINDEX('sp_executesql', m.definition) > 0
                        OR CHARINDEX('EXEC (', m.definition) > 0
                        OR CHARINDEX('EXEC(', m.definition) > 0
                        OR CHARINDEX('EXECUTE (', m.definition) > 0
                        OR CHARINDEX('EXECUTE(', m.definition) > 0
                    THEN 1
                    ELSE 0
                END AS has_dynamic_sql,
                CASE WHEN CHARINDEX('#', m.definition) > 0 THEN 1 ELSE 0 END AS has_temp_table
            FROM sys.sql_modules AS m
            WHERE m.object_id = %s
            """,
            [object_id],
            tool_name=tool_name,
            profile=profile,
        )
        if not rows:
            return {
                "hash": None,
                "length": None,
                "detectedPatterns": [],
                "hasDefinitionAccess": False,
            }
        row = rows[0]
        patterns = []
        if row.get("has_dynamic_sql"):
            patterns.append("dynamic_sql")
        if row.get("has_temp_table"):
            patterns.append("temp_table")
        return {
            "hash": str(row["definition_hash"]).lower()
            if row.get("definition_hash")
            else None,
            "length": row.get("definition_length"),
            "detectedPatterns": patterns,
            "hasDefinitionAccess": bool(row.get("has_definition_access")),
        }

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
                dsn=self.settings.metadata_host,
                port=self.settings.metadata_port,
                database=database,
                user=self.settings.metadata_user,
                password=self.settings.metadata_password,
                login_timeout=self.settings.connect_timeout_seconds,
                timeout=self.settings.connect_timeout_seconds,
                tds_version=self.settings.metadata_tds_version,
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
        lock_timeout_ms: int | None = None,
    ) -> list[dict[str, Any]]:
        connection = self._connect(database, profile=profile, tool_name=tool_name)
        cursor = None
        try:
            cursor = connection.cursor()
            if lock_timeout_ms is not None:
                cursor.execute(f"SET LOCK_TIMEOUT {int(lock_timeout_ms)}", ())
            cursor.execute(sql, self._prepare_query_params(params))
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

    def _prepare_query_params(self, params: list[Any]) -> tuple[Any, ...]:
        if self.settings.metadata_tds_version != 1879048192:
            return tuple(params)
        try:
            from pytds import tds_base, tds_types  # type: ignore[import-not-found]
        except Exception:  # pragma: no cover - dependency/runtime issue
            return tuple(params)

        prepared: list[Any] = []
        for param in params:
            if isinstance(param, str):
                size = min(max(len(param), 1), 4000)
                prepared.append(
                    tds_base.Param(
                        type=tds_types.NVarCharType(size),
                        value=param,
                    )
                )
            else:
                prepared.append(param)
        return tuple(prepared)

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
            if (
                "access" in text
                or "permission" in text
                or "denied" in text
                or "login failed" in text
            ):
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
        data = _attach_snapshot_to_results(data, snapshot_id)
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


def _fixture_dependency_items(
    repository: FixtureMetadataRepository,
    dependencies: list[dict[str, Any]],
    *,
    base_path: str,
    source_database: str | None,
) -> list[dict[str, Any]]:
    items = []
    for index, dependency in enumerate(dependencies):
        item = dict(dependency)
        item.setdefault("database", source_database)
        item.setdefault("server", None)
        item.setdefault("referencedDatabase", None)
        item.setdefault("referencedServer", None)
        item.setdefault("sourceScope", "SAME_DATABASE" if source_database else None)
        item.setdefault("dependencyType", "REFERENCE")
        item["isAmbiguous"] = bool(item.get("isAmbiguous"))
        if _dependency_needs_review(item):
            item["reviewStatus"] = "REVIEW_REQUIRED"
            item.setdefault("resolutionStatus", "REVIEW_REQUIRED")
            if not item.get("name") or item.get("objectType") in {None, "", "UNKNOWN"}:
                item.setdefault("resolutionStrategy", "FIXTURE_UNRESOLVED")
            elif item["isAmbiguous"]:
                item.setdefault("resolutionStrategy", "FIXTURE_AMBIGUOUS")
            else:
                item.setdefault("resolutionStrategy", "FIXTURE_REVIEW_REQUIRED")
        else:
            item.setdefault("reviewStatus", "CONFIRMED")
            item.setdefault("resolutionStatus", "CONFIRMED")
            item.setdefault("resolutionStrategy", "FIXTURE_CONFIRMED")
        item.setdefault(
            "evidenceRefs",
            [
                repository._evidence(
                    "procedure-dependency-item",
                    item.get("objectType") or "UNKNOWN",
                    item.get("schema") or "*",
                    item.get("name") or f"dependency-{index}",
                    f"{base_path}/{index}",
                )
            ],
        )
        _decorate_dependency_resolution(item)
        items.append(item)
    return items


def _group_live_dependencies(
    rows: list[dict[str, Any]],
    *,
    source_database: str | None,
) -> dict[Any, list[dict[str, Any]]]:
    grouped: dict[Any, list[dict[str, Any]]] = {}
    for row in rows:
        item = _live_dependency_item(row, source_database=source_database)
        grouped.setdefault(row["object_id"], []).append(item)
    return grouped


def _live_dependency_item(row: dict[str, Any], *, source_database: str | None) -> dict[str, Any]:
    referenced_name = row.get("referenced_entity_name")
    referenced_schema = row.get("referenced_schema_name")
    server_name = row.get("referenced_server_name")
    database_name = row.get("referenced_database_name")
    catalog_match_count = int(row.get("catalog_match_count") or 0)
    is_ambiguous = bool(row.get("is_ambiguous"))
    evidence_refs = [
        _dependency_evidence_ref(
            row,
            path="sys.sql_expression_dependencies",
            object_type="DEPENDENCY",
        )
    ]

    if server_name:
        return _dependency_item(
            row,
            database=database_name,
            server=server_name,
            referenced_database=database_name,
            referenced_server=server_name,
            schema=referenced_schema,
            name=referenced_name,
            object_type=_map_object_type(row.get("direct_object_type")),
            is_ambiguous=is_ambiguous,
            resolution_status="REVIEW_REQUIRED",
            resolution_strategy="CROSS_SERVER_REFERENCE",
            source_scope=None,
            evidence_refs=evidence_refs,
        )

    if database_name:
        source_scope = (
            "SAME_DATABASE"
            if _same(database_name, source_database)
            else "SAME_SERVER_CROSS_DATABASE"
        )
        evidence_refs.append(
            _dependency_evidence_ref(
                row,
                path="sys.databases",
                object_type="DATABASE",
                schema=None,
                name=database_name,
            )
        )
        external_strategy = row.get("external_resolution_strategy")
        if external_strategy:
            return _dependency_item(
                row,
                database=row.get("external_database_name") or database_name,
                server=None,
                referenced_database=database_name,
                referenced_server=None,
                schema=referenced_schema,
                name=referenced_name,
                object_type=_map_object_type(row.get("external_matched_object_type")),
                is_ambiguous=is_ambiguous,
                resolution_status="REVIEW_REQUIRED",
                resolution_strategy=external_strategy,
                source_scope=source_scope,
                evidence_refs=evidence_refs,
            )
        external_match_count = int(row.get("external_catalog_match_count") or 0)
        if external_match_count == 1 and row.get("external_matched_object_name"):
            matched_type = _map_object_type(row.get("external_matched_object_type"))
            evidence_refs.append(
                _dependency_evidence_ref(
                    row,
                    path=(
                        f"{row.get('external_database_name') or database_name}"
                        ".sys.objects,sys.schemas:name_resolution"
                    ),
                    object_type=matched_type,
                    schema=row.get("external_matched_schema_name"),
                    name=row.get("external_matched_object_name"),
                )
            )
            strategy = (
                "SAME_DATABASE_EXPLICIT_DATABASE_CATALOG"
                if source_scope == "SAME_DATABASE"
                else "SAME_SERVER_CROSS_DATABASE_CATALOG"
            )
            return _resolved_catalog_dependency_item(
                row,
                database=row.get("external_database_name") or database_name,
                server=None,
                referenced_database=database_name,
                referenced_server=None,
                schema=row.get("external_matched_schema_name"),
                name=row.get("external_matched_object_name"),
                object_type=matched_type,
                is_ambiguous=is_ambiguous,
                strategy=strategy,
                source_scope=source_scope,
                evidence_refs=evidence_refs,
                synonym_schema=row.get("external_synonym_schema_name"),
                synonym_name=row.get("external_synonym_name"),
            )
        if external_match_count > 1:
            return _dependency_item(
                row,
                database=row.get("external_database_name") or database_name,
                server=None,
                referenced_database=database_name,
                referenced_server=None,
                schema=referenced_schema,
                name=referenced_name,
                object_type="UNKNOWN",
                is_ambiguous=True,
                resolution_status="REVIEW_REQUIRED",
                resolution_strategy="AMBIGUOUS_CROSS_DATABASE_CATALOG_NAME",
                source_scope=source_scope,
                evidence_refs=evidence_refs,
            )
        return _dependency_item(
            row,
            database=row.get("external_database_name") or database_name,
            server=None,
            referenced_database=database_name,
            referenced_server=None,
            schema=referenced_schema,
            name=referenced_name,
            object_type="UNKNOWN",
            is_ambiguous=is_ambiguous,
            resolution_status="REVIEW_REQUIRED",
            resolution_strategy="CROSS_DATABASE_CATALOG_OBJECT_NOT_FOUND",
            source_scope=source_scope,
            evidence_refs=evidence_refs,
        )

    direct_name = row.get("direct_object_name")
    direct_type = _map_object_type(row.get("direct_object_type"))
    if direct_name:
        evidence_refs.append(
            _dependency_evidence_ref(
                row,
                path="sys.objects,sys.schemas:referenced_id",
                object_type=direct_type,
                schema=row.get("direct_schema_name"),
                name=direct_name,
            )
        )
        return _resolved_catalog_dependency_item(
            row,
            database=source_database,
            server=None,
            referenced_database=database_name,
            referenced_server=server_name,
            schema=row.get("direct_schema_name"),
            name=direct_name,
            object_type=direct_type,
            is_ambiguous=is_ambiguous,
            strategy="REFERENCED_ID",
            source_scope="SAME_DATABASE",
            evidence_refs=evidence_refs,
        )

    if catalog_match_count == 1 and row.get("matched_object_name"):
        matched_type = _map_object_type(row.get("matched_object_type"))
        evidence_refs.append(
            _dependency_evidence_ref(
                row,
                path="sys.objects,sys.schemas:name_resolution",
                object_type=matched_type,
                schema=row.get("matched_schema_name"),
                name=row.get("matched_object_name"),
            )
        )
        strategy = (
            "SAME_DATABASE_SCHEMA_NAME"
            if referenced_schema
            else "SAME_DATABASE_UNIQUE_NAME"
        )
        return _resolved_catalog_dependency_item(
            row,
            database=source_database,
            server=None,
            referenced_database=database_name,
            referenced_server=server_name,
            schema=row.get("matched_schema_name"),
            name=row.get("matched_object_name"),
            object_type=matched_type,
            is_ambiguous=is_ambiguous,
            strategy=strategy,
            source_scope="SAME_DATABASE",
            evidence_refs=evidence_refs,
        )

    if catalog_match_count > 1:
        return _dependency_item(
            row,
            database=source_database,
            server=None,
            referenced_database=database_name,
            referenced_server=server_name,
            schema=referenced_schema,
            name=referenced_name,
            object_type="UNKNOWN",
            is_ambiguous=True,
            resolution_status="REVIEW_REQUIRED",
            resolution_strategy="AMBIGUOUS_CATALOG_NAME",
            source_scope="SAME_DATABASE",
            evidence_refs=evidence_refs,
        )

    strategy = "CALLER_DEPENDENT_REFERENCE" if row.get("is_caller_dependent") else "UNRESOLVED"
    return _dependency_item(
        row,
        database=source_database,
        server=None,
        referenced_database=database_name,
        referenced_server=server_name,
        schema=referenced_schema,
        name=referenced_name,
        object_type="UNKNOWN",
        is_ambiguous=is_ambiguous,
        resolution_status="REVIEW_REQUIRED",
        resolution_strategy=strategy,
        source_scope="SAME_DATABASE",
        evidence_refs=evidence_refs,
    )


def _resolved_catalog_dependency_item(
    row: dict[str, Any],
    *,
    database: Any,
    server: Any,
    referenced_database: Any,
    referenced_server: Any,
    schema: Any,
    name: Any,
    object_type: str,
    is_ambiguous: bool,
    strategy: str,
    source_scope: str | None,
    evidence_refs: list[dict[str, Any]],
    synonym_schema: Any | None = None,
    synonym_name: Any | None = None,
) -> dict[str, Any]:
    if object_type == "SYNONYM":
        evidence_refs.append(
            _dependency_evidence_ref(
                row,
                path="sys.synonyms",
                object_type="SYNONYM",
                schema=synonym_schema or row.get("synonym_schema_name") or schema,
                name=synonym_name or row.get("synonym_name") or name,
            )
        )
        return _dependency_item(
            row,
            database=database,
            server=server,
            referenced_database=referenced_database,
            referenced_server=referenced_server,
            schema=schema,
            name=name,
            object_type=object_type,
            is_ambiguous=True,
            resolution_status="REVIEW_REQUIRED",
            resolution_strategy="SYNONYM_TARGET_REVIEW_REQUIRED",
            source_scope=source_scope,
            evidence_refs=evidence_refs,
        )
    if object_type == "UNKNOWN":
        return _dependency_item(
            row,
            database=database,
            server=server,
            referenced_database=referenced_database,
            referenced_server=referenced_server,
            schema=schema,
            name=name,
            object_type=object_type,
            is_ambiguous=is_ambiguous,
            resolution_status="REVIEW_REQUIRED",
            resolution_strategy="UNSUPPORTED_OBJECT_TYPE",
            source_scope=source_scope,
            evidence_refs=evidence_refs,
        )
    return _dependency_item(
        row,
        database=database,
        server=server,
        referenced_database=referenced_database,
        referenced_server=referenced_server,
        schema=schema,
        name=name,
        object_type=object_type,
        is_ambiguous=is_ambiguous,
        resolution_status="REVIEW_REQUIRED" if is_ambiguous else "CONFIRMED",
        resolution_strategy="AMBIGUOUS_SQL_EXPRESSION" if is_ambiguous else strategy,
        source_scope=source_scope,
        evidence_refs=evidence_refs,
    )


def _dependency_item(
    row: dict[str, Any],
    *,
    database: Any,
    server: Any,
    referenced_database: Any,
    referenced_server: Any,
    schema: Any,
    name: Any,
    object_type: str,
    is_ambiguous: bool,
    resolution_status: str,
    resolution_strategy: str,
    source_scope: str | None,
    evidence_refs: list[dict[str, Any]],
) -> dict[str, Any]:
    return _decorate_dependency_resolution(
        {
            "objectType": object_type,
            "database": database,
            "server": server,
            "schema": schema,
            "name": name,
            "referencedDatabase": referenced_database,
            "referencedServer": referenced_server,
            "sourceScope": source_scope,
            "dependencyType": "REFERENCE",
            "isAmbiguous": bool(is_ambiguous),
            "reviewStatus": "CONFIRMED"
            if resolution_status == "CONFIRMED"
            else "REVIEW_REQUIRED",
            "resolutionStatus": resolution_status,
            "resolutionStrategy": resolution_strategy,
            "evidenceRefs": evidence_refs,
        }
    )


def _dynamic_sql_dependency_item(evidence_ref: dict[str, Any]) -> dict[str, Any]:
    return _decorate_dependency_resolution(
        {
            "objectType": "UNKNOWN",
            "database": None,
            "server": None,
            "schema": None,
            "name": None,
            "referencedDatabase": None,
            "referencedServer": None,
            "sourceScope": None,
            "dependencyType": "DYNAMIC_SQL",
            "isAmbiguous": True,
            "reviewStatus": "REVIEW_REQUIRED",
            "resolutionStatus": "REVIEW_REQUIRED",
            "resolutionStrategy": "DYNAMIC_SQL_PATTERN",
            "evidenceRefs": [evidence_ref],
        }
    )


def _dependency_closure_payload(
    *,
    root_object: dict[str, Any],
    root_evidence_refs: list[dict[str, Any]],
    fetch_dependencies: Callable[[str, str, str], list[dict[str, Any]]],
    max_depth: int,
    include_review_required: bool,
) -> dict[str, Any]:
    max_depth = min(max(int(max_depth), 0), 3)
    root_id = _dependency_node_id(root_object)
    nodes: dict[str, dict[str, Any]] = {
        root_id: _dependency_node(root_object, root_evidence_refs, review_status="CONFIRMED")
    }
    edges: list[dict[str, Any]] = []
    unresolved: list[dict[str, Any]] = []
    visited_sources: set[str] = set()
    queue: list[tuple[dict[str, Any], int]] = [(root_object, 0)]

    while queue:
        source, depth = queue.pop(0)
        source_id = _dependency_node_id(source)
        if source_id in visited_sources:
            continue
        visited_sources.add(source_id)
        dependencies = fetch_dependencies(
            str(source["objectType"]),
            str(source["schema"]),
            str(source["name"]),
        )
        for dependency in dependencies:
            needs_review = _dependency_needs_review(dependency)
            if needs_review:
                unresolved.append(dependency)
            target_id = _dependency_node_id_from_dependency(dependency)
            if target_id is None or (needs_review and not include_review_required):
                continue
            nodes.setdefault(target_id, _dependency_node_from_dependency(dependency))
            edges.append(_dependency_edge(source_id, target_id, dependency))
            if (
                depth < max_depth
                and _is_expandable_dependency(dependency, root_database=root_object.get("database"))
                and target_id not in visited_sources
            ):
                queue.append(
                    (
                        {
                            "database": dependency.get("database"),
                            "server": dependency.get("server"),
                            "schema": dependency.get("schema"),
                            "name": dependency.get("name"),
                            "objectType": dependency.get("objectType"),
                        },
                        depth + 1,
                    )
                )

    return {
        "rootObject": {
            "database": root_object["database"],
            "schema": root_object["schema"],
            "name": root_object["name"],
            "objectType": root_object["objectType"],
        },
        "nodes": list(nodes.values()),
        "edges": edges,
        "unresolved": unresolved,
        "summary": {
            "maxDepth": max_depth,
            "nodeCount": len(nodes),
            "edgeCount": len(edges),
            "reviewRequiredCount": len(unresolved),
        },
        "caveats": ["DEPENDENCY_METADATA_INCOMPLETE"] if unresolved else [],
        "reviewRequired": bool(unresolved),
    }


def _dependency_reference_resolution_payload(
    dependencies: list[dict[str, Any]],
    *,
    referenced_name: str,
    referenced_schema: str | None,
    referenced_database: str | None,
    referenced_server: str | None,
    fallback_evidence_refs: list[dict[str, Any]],
) -> dict[str, Any]:
    candidates = [
        _dependency_candidate(dependency)
        for dependency in dependencies
        if _dependency_matches_reference(
            dependency,
            referenced_name=referenced_name,
            referenced_schema=referenced_schema,
            referenced_database=referenced_database,
            referenced_server=referenced_server,
        )
    ]
    confirmed_candidates = [
        candidate
        for candidate in candidates
        if candidate.get("resolutionStatus") == "CONFIRMED"
        and candidate.get("resolutionConfidence") == "HIGH"
    ]
    selected = (
        confirmed_candidates[0]
        if len(candidates) == 1 and len(confirmed_candidates) == 1
        else None
    )
    evidence_refs = _dedupe_evidence_refs(
        [
            ref
            for candidate in candidates
            for ref in candidate.get("evidenceRefs", [])
        ]
    )
    if not evidence_refs:
        evidence_refs = fallback_evidence_refs
    if selected is not None:
        status = "CONFIRMED"
        strategy = "UNIQUE_CATALOG_MATCH"
        confidence = "HIGH"
        evidence_kind = selected.get("resolutionEvidenceKind", "CATALOG_OBJECT_ID")
        unresolved_reason = None
        caveats: list[str] = []
    elif candidates:
        status = "REVIEW_REQUIRED"
        strategy = "AMBIGUOUS_OR_UNCONFIRMED_CANDIDATES"
        confidence = "LOW"
        evidence_kind = "NAME_MATCH_CANDIDATE"
        unresolved_reason = strategy
        caveats = ["DEPENDENCY_METADATA_INCOMPLETE"]
    else:
        status = "REVIEW_REQUIRED"
        strategy = "NO_CATALOG_CANDIDATE"
        confidence = "UNKNOWN"
        evidence_kind = "UNRESOLVED"
        unresolved_reason = strategy
        caveats = ["DEPENDENCY_METADATA_INCOMPLETE"]
    return {
        "candidates": candidates,
        "selectedResolution": selected,
        "resolutionStatus": status,
        "resolutionStrategy": strategy,
        "resolutionConfidence": confidence,
        "resolutionEvidenceKind": evidence_kind,
        "unresolvedReason": unresolved_reason,
        "resolutionChain": [
            {
                "step": strategy,
                "evidenceKind": evidence_kind,
                "status": status,
                "evidenceRefs": evidence_refs,
            }
        ],
        "evidenceRefs": evidence_refs,
        "caveats": caveats,
        "reviewRequired": bool(caveats),
    }


def _dependency_node_id(source: dict[str, Any]) -> str:
    return "|".join(
        str(source.get(key) or "")
        for key in ("server", "database", "schema", "name", "objectType")
    )


def _dependency_node_id_from_dependency(dependency: dict[str, Any]) -> str | None:
    if not dependency.get("name") or not dependency.get("schema"):
        return None
    return _dependency_node_id(
        {
            "server": dependency.get("server"),
            "database": dependency.get("database"),
            "schema": dependency.get("schema"),
            "name": dependency.get("name"),
            "objectType": dependency.get("objectType"),
        }
    )


def _dependency_node(
    source: dict[str, Any],
    evidence_refs: list[dict[str, Any]],
    *,
    review_status: str,
) -> dict[str, Any]:
    return {
        "id": _dependency_node_id(source),
        "database": source.get("database"),
        "server": source.get("server"),
        "schema": source.get("schema"),
        "name": source.get("name"),
        "objectType": source.get("objectType"),
        "sourceScope": source.get("sourceScope"),
        "referencedDatabase": source.get("referencedDatabase"),
        "referencedServer": source.get("referencedServer"),
        "reviewStatus": review_status,
        "evidenceRefs": evidence_refs,
    }


def _dependency_node_from_dependency(dependency: dict[str, Any]) -> dict[str, Any]:
    return _dependency_node(
        dependency,
        dependency.get("evidenceRefs", []),
        review_status=dependency.get("reviewStatus", "REVIEW_REQUIRED"),
    )


def _dependency_edge(source_id: str, target_id: str, dependency: dict[str, Any]) -> dict[str, Any]:
    return {
        "from": source_id,
        "to": target_id,
        "dependencyType": dependency.get("dependencyType", "REFERENCE"),
        "resolutionStatus": dependency.get("resolutionStatus", "REVIEW_REQUIRED"),
        "resolutionStrategy": dependency.get("resolutionStrategy", "UNRESOLVED"),
        "resolutionConfidence": dependency.get("resolutionConfidence", "UNKNOWN"),
        "resolutionEvidenceKind": dependency.get("resolutionEvidenceKind", "UNRESOLVED"),
        "unresolvedReason": dependency.get("unresolvedReason"),
        "resolutionChain": dependency.get("resolutionChain", []),
        "evidenceRefs": dependency.get("evidenceRefs", []),
    }


def _is_expandable_dependency(dependency: dict[str, Any], *, root_database: Any) -> bool:
    return (
        dependency.get("objectType") in {"PROCEDURE", "VIEW", "FUNCTION"}
        and dependency.get("resolutionStatus") == "CONFIRMED"
        and dependency.get("server") in {None, ""}
        and _same(dependency.get("database"), root_database)
        and bool(dependency.get("schema"))
        and bool(dependency.get("name"))
    )


def _dependency_candidate(dependency: dict[str, Any]) -> dict[str, Any]:
    return {
        "database": dependency.get("database"),
        "server": dependency.get("server"),
        "schema": dependency.get("schema"),
        "name": dependency.get("name"),
        "objectType": dependency.get("objectType"),
        "sourceScope": dependency.get("sourceScope"),
        "resolutionStatus": dependency.get("resolutionStatus", "REVIEW_REQUIRED"),
        "resolutionStrategy": dependency.get("resolutionStrategy", "UNRESOLVED"),
        "resolutionConfidence": dependency.get("resolutionConfidence", "UNKNOWN"),
        "resolutionEvidenceKind": dependency.get("resolutionEvidenceKind", "UNRESOLVED"),
        "unresolvedReason": dependency.get("unresolvedReason"),
        "resolutionChain": dependency.get("resolutionChain", []),
        "evidenceRefs": dependency.get("evidenceRefs", []),
    }


def _dependency_matches_reference(
    dependency: dict[str, Any],
    *,
    referenced_name: str,
    referenced_schema: str | None,
    referenced_database: str | None,
    referenced_server: str | None,
) -> bool:
    if not _same(dependency.get("name"), referenced_name):
        return False
    if referenced_schema and not _same(dependency.get("schema"), referenced_schema):
        return False
    if referenced_database and not _same(
        dependency.get("referencedDatabase") or dependency.get("database"),
        referenced_database,
    ):
        return False
    if referenced_server and not _same(
        dependency.get("referencedServer") or dependency.get("server"),
        referenced_server,
    ):
        return False
    return True


def _decorate_dependency_resolution(item: dict[str, Any]) -> dict[str, Any]:
    status = item.get("resolutionStatus", "REVIEW_REQUIRED")
    strategy = item.get("resolutionStrategy", "UNRESOLVED")
    evidence_kind = item.get("resolutionEvidenceKind") or _resolution_evidence_kind(
        strategy,
        item.get("objectType"),
        item.get("dependencyType"),
    )
    item.setdefault("resolutionConfidence", "HIGH" if status == "CONFIRMED" else "UNKNOWN")
    item.setdefault("resolutionEvidenceKind", evidence_kind)
    if status != "CONFIRMED":
        item.setdefault("unresolvedReason", strategy)
    else:
        item.setdefault("unresolvedReason", None)
    item.setdefault(
        "resolutionChain",
        [
            {
                "step": strategy,
                "evidenceKind": evidence_kind,
                "status": status,
                "evidenceRefs": item.get("evidenceRefs", []),
            }
        ],
    )
    return item


def _resolution_evidence_kind(strategy: Any, object_type: Any, dependency_type: Any) -> str:
    strategy_text = str(strategy or "")
    if dependency_type == "DYNAMIC_SQL" or strategy_text == "DYNAMIC_SQL_PATTERN":
        return "DYNAMIC_SQL_MARKER"
    if object_type == "SYNONYM" or "SYNONYM" in strategy_text:
        return "SYNONYM_METADATA"
    if "AMBIGUOUS" in strategy_text or "NAME" in strategy_text:
        return "NAME_MATCH_CANDIDATE"
    if strategy_text in {
        "REFERENCED_ID",
        "SAME_DATABASE_SCHEMA_NAME",
        "SAME_DATABASE_UNIQUE_NAME",
        "SAME_DATABASE_EXPLICIT_DATABASE_CATALOG",
        "SAME_SERVER_CROSS_DATABASE_CATALOG",
        "FIXTURE_CONFIRMED",
    }:
        return "CATALOG_OBJECT_ID"
    if strategy_text == "UNRESOLVED" or "NOT_FOUND" in strategy_text:
        return "UNRESOLVED"
    return "EXPRESSION_DEPENDENCY"


def _dedupe_evidence_refs(evidence_refs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: dict[tuple[Any, Any, Any], dict[str, Any]] = {}
    for ref in evidence_refs:
        deduped.setdefault((ref.get("id"), ref.get("source"), ref.get("path")), ref)
    return list(deduped.values())


def _dependency_evidence_ref(
    row: dict[str, Any],
    *,
    path: str,
    object_type: str,
    schema: Any | None = None,
    name: Any | None = None,
) -> dict[str, Any]:
    schema = schema if schema is not None else row.get("referenced_schema_name")
    name = name if name is not None else row.get("referenced_entity_name")
    object_name = _dependency_object_name(schema, name)
    return {
        "id": f"ev:live:dependency:{row.get('object_id')}:{path}:{object_name}",
        "source": "live-mssql-metadata",
        "path": path,
        "objectType": object_type,
        "objectName": object_name,
    }


def _dependency_object_name(schema: Any, name: Any) -> str:
    if schema and name:
        return f"{schema}.{name}"
    if name:
        return str(name)
    return "unresolved"


def _dependency_needs_review(dependency: dict[str, Any]) -> bool:
    return (
        dependency.get("reviewStatus") == "REVIEW_REQUIRED"
        or dependency.get("resolutionStatus") == "REVIEW_REQUIRED"
        or dependency.get("isAmbiguous") is True
        or dependency.get("objectType") in {None, "", "UNKNOWN"}
        or not dependency.get("name")
    )


def _map_object_type(sql_server_type: Any) -> str:
    normalized = str(sql_server_type or "").strip().upper()
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
        "SN": "SYNONYM",
    }.get(normalized, "UNKNOWN")


def _quote_mssql_identifier(identifier: str) -> str:
    if not identifier or len(identifier) > 128:
        raise ValueError("MSSQL identifiers must be non-empty and at most 128 characters.")
    return f"[{identifier.replace(']', ']]')}]"


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


def _search_object_types(arguments: dict[str, Any]) -> list[str]:
    values = arguments.get("objectTypes") or ["PROCEDURE", "TABLE", "VIEW", "FUNCTION"]
    object_types = list(dict.fromkeys(str(value).upper() for value in values))
    return object_types or ["PROCEDURE", "TABLE", "VIEW", "FUNCTION"]


def _search_limit(arguments: dict[str, Any]) -> int:
    return min(max(int(arguments.get("limit", 20)), 1), 100)


def _search_sql_type_codes(object_types: list[str]) -> list[str]:
    codes: list[str] = []
    mapping = {
        "PROCEDURE": ["P", "PC"],
        "TABLE": ["U"],
        "VIEW": ["V"],
        "FUNCTION": ["FN", "IF", "TF", "FS", "FT"],
    }
    for object_type in object_types:
        codes.extend(mapping.get(object_type, []))
    return codes or ["P", "PC", "U", "V", "FN", "IF", "TF", "FS", "FT"]


def _metadata_search_score(item: dict[str, Any], query: str) -> int:
    needle = query.casefold()
    score = 0
    values = [
        item.get("schema"),
        item.get("name"),
        item.get("objectType"),
        item.get("logicalName"),
        item.get("description"),
        item.get("descriptionStatus"),
    ]
    identity = ".".join(str(value) for value in (item.get("schema"), item.get("name")) if value)
    values.append(identity)
    dependency_summary = item.get("dependencySummary")
    if isinstance(dependency_summary, dict):
        for dependencies in dependency_summary.values():
            if isinstance(dependencies, list):
                values.extend(dependency.get("name") for dependency in dependencies)
    for value in values:
        if value is None:
            continue
        text = str(value).casefold()
        if text == needle:
            score += 100
        elif needle in text:
            score += 20
    return score


def _metadata_search_result_item(
    item: dict[str, Any],
    *,
    context: dict[str, Any],
) -> dict[str, Any]:
    caveats = _dedupe(item.get("caveats", []))
    blockers = _blockers_for_caveats(caveats)
    return {
        "objectIdentity": {
            "schema": item.get("schema"),
            "name": item.get("name"),
            "type": item.get("objectType"),
        },
        "sourceProfile": context["sourceProfile"],
        "sourceDatabase": context["sourceDatabase"],
        "snapshotId": item.get("snapshotId"),
        "evidenceRefs": item.get("evidenceRefs", []),
        "caveats": caveats,
        "reviewRequired": bool(item.get("reviewRequired") or caveats or blockers),
        "blockers": blockers,
        "score": int(item.get("score", 0)),
    }


def _metadata_search_items_from_live_rows(
    repository: Any,
    rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    grouped: dict[Any, dict[str, Any]] = {}
    for index, row in enumerate(rows):
        item = grouped.setdefault(
            row["object_id"],
            {
                "schema": row["schema_name"],
                "name": row["object_name"],
                "objectType": _map_object_type(row.get("object_type")),
                "description": row.get("description"),
                "descriptionStatus": "CONFIRMED"
                if row.get("description")
                else "REVIEW_REQUIRED",
                "dependencies": [],
                "evidenceRefs": [
                    repository._live_evidence(
                        "metadata-object-search",
                        _map_object_type(row.get("object_type")),
                        row["schema_name"],
                        row["object_name"],
                        f"sys.objects[{index}]",
                    )
                ],
            },
        )
        if row.get("dep_object_name"):
            item["dependencies"].append(
                {
                    "objectType": _map_object_type(row.get("dep_referenced_type")),
                    "schema": row.get("dep_schema_name"),
                    "name": row.get("dep_object_name"),
                    "dependencyType": "REFERENCE",
                    "isAmbiguous": bool(row.get("is_ambiguous")),
                    "reviewStatus": "REVIEW_REQUIRED"
                    if row.get("is_ambiguous")
                    else "CONFIRMED",
                }
            )
    items = []
    for item in grouped.values():
        caveats = _dependency_caveats(item["dependencies"])
        if item["objectType"] == "TABLE" and item.get("descriptionStatus") == "REVIEW_REQUIRED":
            caveats.append("description_review_required")
        item["caveats"] = list(dict.fromkeys(caveats))
        item["reviewRequired"] = bool(item["caveats"])
        items.append(item)
    return items


def _metadata_search_caveats(results: list[dict[str, Any]]) -> list[str]:
    return _dedupe(caveat for result in results for caveat in result.get("caveats", []))


def _blockers_for_caveats(caveats: list[str]) -> list[dict[str, str]]:
    messages = {
        DEPENDENCY_METADATA_INCOMPLETE: (
            "Dependency metadata is incomplete; treat dependency links as evidence caveats until confirmed."
        )
    }
    return [
        {"code": caveat, "message": messages[caveat]}
        for caveat in caveats
        if caveat in messages
    ]


def _dedupe(items: Any) -> list[str]:
    return list(dict.fromkeys(str(item) for item in items if str(item)))


def _without_score(item: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(item)
    cleaned.pop("score", None)
    return cleaned


def _attach_snapshot_to_results(data: dict[str, Any], snapshot_id: str) -> dict[str, Any]:
    results = data.get("results")
    if not isinstance(results, list):
        return data
    copied = dict(data)
    copied["results"] = [
        {**result, "snapshotId": result.get("snapshotId") or snapshot_id}
        if isinstance(result, dict)
        else result
        for result in results
    ]
    return copied


def _is_empty_search(arguments: dict[str, Any]) -> bool:
    return not any(value for key, value in arguments.items() if key not in {"dbProfileId", "topK"})


def _dependency_caveats(dependencies: list[dict[str, Any]]) -> list[str]:
    for dependency in dependencies:
        if _dependency_needs_review(dependency):
            return ["DEPENDENCY_METADATA_INCOMPLETE"]
    return []
