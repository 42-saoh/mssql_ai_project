from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from mssql_mcp_app.errors import MetadataToolError
from mssql_mcp_app.registry import build_tool_registry
from mssql_mcp_app.repositories import FixtureMetadataRepository, LiveMetadataRepository
from mssql_mcp_app.settings import load_live_metadata_settings

import api_app.metadata_service as metadata_service
from api_app.live_gate import P21_LIVE_PPM_REQUIRED
from api_app.metadata_service import (
    METADATA_BLOCKER_MESSAGES,
    PPM_MANIFEST_TEMPLATE_ONLY,
    MetadataSearchDependencyError,
    load_profiles_for_metadata_request,
    p21_live_portal_enabled,
)


class P21LivePortalPrerequisiteError(RuntimeError):
    def __init__(
        self,
        detail: str | None = None,
        *,
        code: str = P21_LIVE_PPM_REQUIRED,
    ) -> None:
        super().__init__(detail or METADATA_BLOCKER_MESSAGES[P21_LIVE_PPM_REQUIRED])
        self.code = code


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
    dependency_evidence: dict[str, Any] | None = None
    ai_tool_evidence: dict[str, Any] | None = None
    platform_tool_evidence: dict[str, Any] | None = None
    deterministic_facts: tuple[dict[str, Any], ...] = ()
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
            "dependencyEvidence": self.dependency_evidence,
            "aiToolEvidence": self.ai_tool_evidence,
            "platformToolEvidence": self.platform_tool_evidence,
            "deterministicFacts": list(self.deterministic_facts),
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
        is_p21_live = p21_live_portal_enabled()
        try:
            profiles = load_profiles_for_metadata_request(settings, db_profile_id=db_profile_id)
        except MetadataSearchDependencyError as exc:
            raise P21LivePortalPrerequisiteError(exc.detail, code=exc.code) from exc
        if (
            db_profile_id == "ppm"
            and metadata_service.ppm_manifest_selection_mode() != "live_metadata"
        ):
            raise P21LivePortalPrerequisiteError(
                METADATA_BLOCKER_MESSAGES[PPM_MANIFEST_TEMPLATE_ONLY],
                code=PPM_MANIFEST_TEMPLATE_ONLY,
            )
        repository = (
            LiveMetadataRepository(settings=settings, profiles=profiles)
            if settings.live_metadata_enabled
            else self.fixture_repository
        )
        registry = build_tool_registry(repository=repository, profiles=profiles)
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
        dependency_closure = self._invoke(
            registry,
            "get_dependency_closure",
            {
                "dbProfileId": db_profile_id,
                "schema": schema,
                "objectName": procedure_name,
                "objectType": "PROCEDURE",
                "maxDepth": 2,
                "includeReviewRequired": False,
            },
            evidence_refs,
            errors,
        )
        if dependency_closure is not None:
            evidence_refs.extend(_raw_dependency_evidence_refs(dependency_closure))
        if is_p21_live and (
            definition is None or parameters is None or dependencies is None
        ):
            error = errors[0] if errors else {}
            code = str(error.get("code") or P21_LIVE_PPM_REQUIRED)
            tool_name = str(error.get("toolName") or "required_procedure_metadata")
            raise P21LivePortalPrerequisiteError(
                (
                    "P21 live portal gate requires live PPM procedure metadata; "
                    f"{tool_name} failed with {code}."
                ),
                code=code,
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

        payloads = [
            item
            for item in (definition, parameters, dependencies, dependency_closure)
            if item
        ]
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
            dependency_evidence=_dependency_evidence_digest(dependency_closure),
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
    seen: set[tuple[str, str, str, str | None]] = set()
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
        snapshot_id = ref.get("snapshotId")
        if snapshot_id:
            item["snapshotId"] = str(snapshot_id)
        dedupe_key = (
            item["type"],
            item["objectRef"],
            item["locator"],
            item.get("snapshotId"),
        )
        if dedupe_key not in seen:
            converted.append(item)
            seen.add(dedupe_key)
    return tuple(converted)


def _dependency_evidence_digest(payload: dict[str, Any] | None) -> dict[str, Any] | None:
    if not payload:
        return None
    data = dict(payload.get("data") or {})
    snapshot_id = str(payload.get("snapshotId") or "") or None
    root_object = _safe_dependency_identity(data.get("rootObject") or {})
    raw_evidence_refs = _raw_dependency_evidence_refs(payload)
    evidence_refs = list(_api_evidence_refs(raw_evidence_refs))
    return {
        "toolName": str(payload.get("toolName") or "get_dependency_closure"),
        "dbProfileId": str(payload.get("dbProfileId") or ""),
        "snapshotId": snapshot_id,
        "collectedAt": str(payload.get("collectedAt") or ""),
        "rootObject": root_object,
        "summary": _safe_dependency_summary(data.get("summary") or {}),
        "nodes": [
            _safe_dependency_node(item, snapshot_id=snapshot_id)
            for item in _dict_items(data.get("nodes"))
        ],
        "edges": [
            _safe_dependency_edge(item, snapshot_id=snapshot_id)
            for item in _dict_items(data.get("edges"))
        ],
        "unresolved": [
            _safe_dependency_unresolved(item, snapshot_id=snapshot_id)
            for item in _dict_items(data.get("unresolved"))
        ],
        "evidenceRefs": evidence_refs,
        "caveats": [str(item) for item in data.get("caveats", []) if str(item)],
        "reviewRequired": bool(data.get("reviewRequired")),
    }


def _raw_dependency_evidence_refs(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = dict(payload.get("data") or {})
    raw_refs: list[dict[str, Any]] = []
    raw_refs.extend(_dict_items(payload.get("evidenceRefs")))
    for collection in ("nodes", "edges", "unresolved", "candidates"):
        for item in _dict_items(data.get(collection)):
            raw_refs.extend(_dict_items(item.get("evidenceRefs")))
            for step in _dict_items(item.get("resolutionChain")):
                raw_refs.extend(_dict_items(step.get("evidenceRefs")))
    selected = data.get("selectedResolution")
    if isinstance(selected, dict):
        raw_refs.extend(_dict_items(selected.get("evidenceRefs")))
        for step in _dict_items(selected.get("resolutionChain")):
            raw_refs.extend(_dict_items(step.get("evidenceRefs")))
    for ref in raw_refs:
        if payload.get("snapshotId") and not ref.get("snapshotId"):
            ref["snapshotId"] = str(payload["snapshotId"])
    return raw_refs


def _safe_dependency_summary(value: dict[str, Any]) -> dict[str, int]:
    return {
        "maxDepth": int(value.get("maxDepth") or 0),
        "nodeCount": int(value.get("nodeCount") or 0),
        "edgeCount": int(value.get("edgeCount") or 0),
        "reviewRequiredCount": int(value.get("reviewRequiredCount") or 0),
    }


def _safe_dependency_identity(value: Any) -> dict[str, Any]:
    item = dict(value) if isinstance(value, dict) else {}
    return {
        key: item.get(key)
        for key in (
            "database",
            "server",
            "schema",
            "name",
            "objectType",
            "sourceScope",
            "referencedDatabase",
            "referencedServer",
        )
        if item.get(key) is not None
    }


def _safe_dependency_node(item: dict[str, Any], *, snapshot_id: str | None) -> dict[str, Any]:
    return {
        **_safe_dependency_identity(item),
        "id": str(item.get("id") or ""),
        "reviewStatus": str(item.get("reviewStatus") or "REVIEW_REQUIRED"),
        "evidenceRefs": list(
            _api_evidence_refs(_refs_with_snapshot(item.get("evidenceRefs"), snapshot_id))
        ),
    }


def _safe_dependency_edge(item: dict[str, Any], *, snapshot_id: str | None) -> dict[str, Any]:
    return {
        "from": str(item.get("from") or ""),
        "to": str(item.get("to") or ""),
        "dependencyType": str(item.get("dependencyType") or "REFERENCE"),
        "resolutionStatus": str(item.get("resolutionStatus") or "REVIEW_REQUIRED"),
        "resolutionStrategy": str(item.get("resolutionStrategy") or "UNRESOLVED"),
        "resolutionConfidence": str(item.get("resolutionConfidence") or "UNKNOWN"),
        "resolutionEvidenceKind": str(item.get("resolutionEvidenceKind") or "UNRESOLVED"),
        "unresolvedReason": item.get("unresolvedReason"),
        "evidenceRefs": list(
            _api_evidence_refs(_refs_with_snapshot(item.get("evidenceRefs"), snapshot_id))
        ),
    }


def _safe_dependency_unresolved(item: dict[str, Any], *, snapshot_id: str | None) -> dict[str, Any]:
    return {
        **_safe_dependency_identity(item),
        "dependencyType": str(item.get("dependencyType") or "REFERENCE"),
        "isAmbiguous": bool(item.get("isAmbiguous")),
        "reviewStatus": str(item.get("reviewStatus") or "REVIEW_REQUIRED"),
        "resolutionStatus": str(item.get("resolutionStatus") or "REVIEW_REQUIRED"),
        "resolutionStrategy": str(item.get("resolutionStrategy") or "UNRESOLVED"),
        "resolutionConfidence": str(item.get("resolutionConfidence") or "UNKNOWN"),
        "resolutionEvidenceKind": str(item.get("resolutionEvidenceKind") or "UNRESOLVED"),
        "unresolvedReason": item.get("unresolvedReason"),
        "evidenceRefs": list(
            _api_evidence_refs(_refs_with_snapshot(item.get("evidenceRefs"), snapshot_id))
        ),
    }


def _refs_with_snapshot(value: Any, snapshot_id: str | None) -> list[dict[str, Any]]:
    refs = _dict_items(value)
    if not snapshot_id:
        return refs
    return [{**ref, "snapshotId": ref.get("snapshotId") or snapshot_id} for ref in refs]


def _dict_items(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]
