from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mssql_mcp_app.errors import MetadataToolError
from mssql_mcp_app.profiles import load_db_profiles
from mssql_mcp_app.registry import build_tool_registry
from mssql_mcp_app.repositories import FixtureMetadataRepository
from mssql_mcp_app.settings import load_live_metadata_settings

from api_app.metadata_service import repo_root


@dataclass(frozen=True)
class MetadataCollectionResult:
    db_profile_id: str
    object_ref: str
    snapshot_id: str | None
    collected_at: str | None
    evidence_refs: tuple[dict[str, Any], ...]
    procedure_definition: dict[str, Any] | None = None
    procedure_parameters: dict[str, Any] | None = None
    procedure_dependencies: dict[str, Any] | None = None
    table_schemas: tuple[dict[str, Any], ...] = ()
    status: str = "COLLECTED"
    notes: tuple[str, ...] = ()
    errors: tuple[dict[str, str], ...] = ()

    @property
    def primary_table(self) -> dict[str, Any] | None:
        return self.table_schemas[0] if self.table_schemas else None

    @property
    def source_names(self) -> tuple[str, ...]:
        names = [self.object_ref]
        names.extend(
            f"{table.get('schema', '')}.{table.get('tableName', '')}"
            for table in self.table_schemas
            if table.get("schema") and table.get("tableName")
        )
        return tuple(dict.fromkeys(names))

    def as_dict(self) -> dict[str, Any]:
        return {
            "dbProfileId": self.db_profile_id,
            "objectRef": self.object_ref,
            "snapshotId": self.snapshot_id,
            "collectedAt": self.collected_at,
            "evidenceRefs": list(self.evidence_refs),
            "procedureDefinition": self.procedure_definition,
            "procedureParameters": self.procedure_parameters,
            "procedureDependencies": self.procedure_dependencies,
            "tableSchemas": list(self.table_schemas),
            "status": self.status,
            "notes": list(self.notes),
            "errors": list(self.errors),
        }


class MetadataGateway:
    def collect_procedure_metadata(
        self,
        *,
        db_profile_id: str,
        schema: str,
        procedure_name: str,
    ) -> MetadataCollectionResult:
        raise NotImplementedError


@dataclass
class McpMetadataGateway(MetadataGateway):
    fixture_repository: FixtureMetadataRepository = field(default_factory=FixtureMetadataRepository)

    def collect_procedure_metadata(
        self,
        *,
        db_profile_id: str,
        schema: str,
        procedure_name: str,
    ) -> MetadataCollectionResult:
        object_ref = f"{schema}.{procedure_name}"
        settings = load_live_metadata_settings()
        profiles = load_db_profiles(settings, repo_root=repo_root())
        registry = build_tool_registry(repository=self.fixture_repository, profiles=profiles)
        evidence_refs: list[dict[str, Any]] = []
        errors: list[dict[str, str]] = []

        definition = self._invoke(
            registry,
            "get_procedure_definition",
            {
                "dbProfileId": db_profile_id,
                "schema": schema,
                "procedureName": procedure_name,
            },
            evidence_refs,
            errors,
        )
        parameters = self._invoke(
            registry,
            "get_procedure_parameters",
            {
                "dbProfileId": db_profile_id,
                "schema": schema,
                "procedureName": procedure_name,
            },
            evidence_refs,
            errors,
        )
        dependencies = self._invoke(
            registry,
            "get_procedure_dependencies",
            {
                "dbProfileId": db_profile_id,
                "schema": schema,
                "procedureName": procedure_name,
            },
            evidence_refs,
            errors,
        )
        table_schemas = tuple(
            table_schema
            for table_schema in (
                self._invoke(
                    registry,
                    "get_table_schema",
                    {
                        "dbProfileId": db_profile_id,
                        "schema": str(dependency.get("schema", schema)),
                        "tableName": str(dependency.get("name", "")),
                    },
                    evidence_refs,
                    errors,
                )
                for dependency in _table_dependencies(dependencies)
            )
            if table_schema is not None
        )

        payloads = [item for item in (definition, parameters, dependencies) if item]
        snapshot_id = _first_value(payloads, "snapshotId")
        collected_at = _first_value(payloads, "collectedAt")
        if errors and not payloads:
            return MetadataCollectionResult(
                db_profile_id=db_profile_id,
                object_ref=object_ref,
                snapshot_id=None,
                collected_at=None,
                evidence_refs=(
                    {
                        "type": "USER_INPUT",
                        "objectRef": object_ref,
                        "locator": "request.target",
                    },
                ),
                status="REVIEW_REQUIRED",
                notes=(
                    "Metadata MCP fixture has no matching procedure; workflow continues "
                    "with request-scoped review-required evidence.",
                ),
                errors=tuple(errors),
            )

        notes = ["Metadata collected through MSSQL MCP tool registry boundary."]
        if errors:
            notes.append(
                "Some metadata tool calls returned documented errors; "
                "manual review remains required."
            )

        return MetadataCollectionResult(
            db_profile_id=db_profile_id,
            object_ref=object_ref,
            snapshot_id=snapshot_id,
            collected_at=collected_at,
            evidence_refs=tuple(_api_evidence_refs(evidence_refs)),
            procedure_definition=definition["data"] if definition else None,
            procedure_parameters=parameters["data"] if parameters else None,
            procedure_dependencies=dependencies["data"] if dependencies else None,
            table_schemas=tuple(item["data"] for item in table_schemas),
            status="COLLECTED" if not errors else "REVIEW_REQUIRED",
            notes=tuple(notes),
            errors=tuple(errors),
        )

    @staticmethod
    def _invoke(
        registry,
        tool_name: str,
        arguments: dict[str, Any],
        evidence_refs: list[dict[str, Any]],
        errors: list[dict[str, str]],
    ) -> dict[str, Any] | None:
        try:
            payload = registry.invoke_payload(tool_name, {"arguments": arguments})
        except MetadataToolError as exc:
            errors.append({"toolName": tool_name, "code": exc.code, "message": exc.message})
            return None
        evidence_refs.extend(payload.get("evidenceRefs", []))
        return payload


def _table_dependencies(payload: dict[str, Any] | None) -> tuple[dict[str, Any], ...]:
    if not payload:
        return ()
    dependencies = payload.get("data", {}).get("dependencies", [])
    return tuple(
        dependency
        for dependency in dependencies
        if dependency.get("objectType") == "TABLE" and dependency.get("name")
    )


def _first_value(payloads: list[dict[str, Any]], key: str) -> str | None:
    for payload in payloads:
        value = payload.get(key)
        if value:
            return str(value)
    return None


def _api_evidence_refs(evidence_refs: list[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    converted = []
    seen: set[tuple[str, str, str]] = set()
    for ref in evidence_refs:
        object_name = ref.get("objectName") or ref.get("id") or "metadata"
        object_ref = str(object_name)
        object_type = ref.get("objectType")
        if object_type and ref.get("objectName"):
            object_ref = str(ref["objectName"])
        locator = str(ref.get("path", "mssql-mcp"))
        item = {
            "type": "MSSQL_METADATA",
            "objectRef": object_ref,
            "locator": locator,
        }
        dedupe_key = (item["type"], item["objectRef"], item["locator"])
        if dedupe_key not in seen:
            converted.append(item)
            seen.add(dedupe_key)
    return tuple(converted)
