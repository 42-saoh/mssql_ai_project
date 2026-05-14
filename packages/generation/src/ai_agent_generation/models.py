from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

from ai_agent_domain import ArtifactStatus, ArtifactType

GENERATOR_VERSION = "generation-core-0.1.0"


@dataclass(frozen=True)
class EvidenceRef:
    type: str
    object_ref: str
    locator: str
    snapshot_id: str | None = None

    def as_dict(self) -> dict[str, str]:
        payload = {
            "type": self.type,
            "objectRef": self.object_ref,
            "locator": self.locator,
        }
        if self.snapshot_id:
            payload["snapshotId"] = self.snapshot_id
        return payload


@dataclass(frozen=True)
class EvidenceSource:
    type: str
    name: str
    reason: str
    locator: str = ""
    snapshot_id: str | None = None

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> EvidenceSource:
        return cls(
            type=str(payload.get("type", "unknown")),
            name=str(payload.get("name", payload.get("objectRef", ""))),
            reason=str(payload.get("reason", "")),
            locator=str(payload.get("locator", "")),
            snapshot_id=payload.get("snapshotId", payload.get("snapshot_id")),
        )

    @property
    def display_type(self) -> str:
        labels = {
            "storedProcedure": "저장 프로시저",
            "procedure": "저장 프로시저",
            "table": "테이블",
            "view": "뷰",
            "function": "함수",
            "dependencyEvidence": "의존성 근거",
            "llmInference": "LLM 추론",
            "policy": "정책",
        }
        return labels.get(self.type, self.type)

    @property
    def evidence_type(self) -> str:
        if self.type in {
            "storedProcedure",
            "procedure",
            "table",
            "view",
            "function",
            "dependencyEvidence",
        }:
            return "MSSQL_METADATA"
        if self.type == "llmInference":
            return "LLM_INFERENCE"
        if self.type == "policy":
            return "POLICY"
        return "USER_INPUT"


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    db_type: str
    nullable: bool = True
    description: str = ""

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> ColumnSpec:
        return cls(
            name=str(payload.get("name", "")),
            db_type=str(payload.get("dbType", payload.get("db_type", ""))),
            nullable=bool(payload.get("nullable", True)),
            description=str(payload.get("description", "")),
        )


@dataclass(frozen=True)
class ParameterSpec:
    name: str
    db_type: str
    required: bool = False

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> ParameterSpec:
        return cls(
            name=str(payload.get("name", "")),
            db_type=str(payload.get("dbType", payload.get("db_type", ""))),
            required=bool(payload.get("required", False)),
        )


@dataclass(frozen=True)
class GenerationContext:
    sample_id: str
    request: Mapping[str, Any]
    evidence_sources: tuple[EvidenceSource, ...] = ()
    evidence_assumptions: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, payload: Mapping[str, Any]) -> GenerationContext:
        evidence = payload.get("evidence", {}) or {}
        sources = tuple(
            EvidenceSource.from_mapping(item) for item in evidence.get("sources", []) or []
        )
        assumptions = tuple(str(item) for item in evidence.get("assumptions", []) or [])
        return cls(
            sample_id=str(payload.get("sampleId", "")),
            request=payload.get("request", {}) or {},
            evidence_sources=sources,
            evidence_assumptions=assumptions,
        )

    def value(self, key: str, default: Any = "") -> Any:
        value = self.request.get(key, default)
        return default if value is None else value

    @property
    def system_code(self) -> str:
        return str(self.value("systemCode"))

    @property
    def system_code_lower(self) -> str:
        return self.system_code.lower()

    @property
    def business_code_lv1(self) -> str:
        return str(self.value("businessCodeLv1"))

    @property
    def business_code_lv2(self) -> str:
        return str(self.value("businessCodeLv2"))

    @property
    def entity_name(self) -> str:
        return str(self.value("entityName"))

    @property
    def entity_name_lower(self) -> str:
        return "".join(char.lower() for char in self.entity_name if char.isalnum())

    @property
    def resource_name(self) -> str:
        return str(self.value("resourceName"))

    @property
    def description(self) -> str:
        return str(self.value("description"))

    @property
    def generation_mode(self) -> str:
        return str(self.value("generationMode"))

    @property
    def table_name(self) -> str:
        return str(self.value("tableName"))

    @property
    def sp_name(self) -> str:
        return str(self.value("spName"))

    @property
    def author_id(self) -> str:
        return str(self.value("authorId", "AI"))

    @property
    def message_prefix(self) -> str:
        return str(self.value("messagePrefix", self.resource_name.replace("-", ".")))

    @property
    def base_package(self) -> str:
        return (
            f"com.pec.{self.system_code_lower}."
            f"{self.business_code_lv1}.{self.business_code_lv2}"
        )

    @property
    def model_package(self) -> str:
        return f"{self.base_package}.model"

    @property
    def service_package(self) -> str:
        return f"{self.base_package}.service"

    @property
    def mapper_package(self) -> str:
        return f"{self.base_package}.mapper"

    @property
    def mapper_class_name(self) -> str:
        return f"{self.entity_name}Mapper"

    @property
    def dto_class_name(self) -> str:
        return f"{self.entity_name}DTO"

    @property
    def service_class_name(self) -> str:
        return f"{self.entity_name}Service"

    @property
    def mapper_method_name(self) -> str:
        return f"select{self.entity_name}List"

    @property
    def service_method_name(self) -> str:
        return f"retrieve{self.entity_name}List"

    @property
    def columns(self) -> tuple[ColumnSpec, ...]:
        return tuple(ColumnSpec.from_mapping(item) for item in self.value("columns", []) or [])

    @property
    def input_params(self) -> tuple[ParameterSpec, ...]:
        return tuple(
            ParameterSpec.from_mapping(item) for item in self.value("inputParams", []) or []
        )

    @property
    def result_shape(self) -> tuple[str, ...]:
        return tuple(str(item) for item in self.value("resultShape", []) or [])

    @property
    def pk_columns(self) -> tuple[str, ...]:
        return tuple(str(item) for item in self.value("pkColumns", []) or [])

    @property
    def evidence_refs(self) -> tuple[EvidenceRef, ...]:
        refs = []
        for source in self.evidence_sources:
            refs.append(
                EvidenceRef(
                    type=source.evidence_type,
                    object_ref=source.name,
                    locator=source.locator
                    or source.reason
                    or "generation-input.evidence.sources",
                    snapshot_id=source.snapshot_id,
                )
            )
        return tuple(refs)

    def sanitized_input_snapshot(self) -> dict[str, Any]:
        return {
            "sampleId": self.sample_id,
            "request": _sanitize_for_snapshot(self.request),
            "evidence": {
                "sources": [
                    _sanitize_for_snapshot(
                        {
                            "type": source.type,
                            "name": source.name,
                            "reason": source.reason,
                            "locator": source.locator,
                            "snapshotId": source.snapshot_id,
                        }
                    )
                    for source in self.evidence_sources
                ],
                "assumptions": list(self.evidence_assumptions),
            },
        }

    @property
    def input_snapshot_hash(self) -> str:
        snapshot = json.dumps(
            self.sanitized_input_snapshot(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(snapshot.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class DraftFile:
    path: str
    content: str
    artifact_type: ArtifactType


@dataclass(frozen=True)
class RenderedArtifact:
    artifact_type: ArtifactType | str
    title: str
    content: str
    evidence_refs: tuple[EvidenceRef, ...]
    generator_version: str = GENERATOR_VERSION
    registry_refs: tuple[str, ...] = ()
    assumptions: tuple[str, ...] = ()
    review_required: bool = True
    status: ArtifactStatus = ArtifactStatus.DRAFT
    extra: Mapping[str, Any] = field(default_factory=dict)

    @property
    def artifact_type_value(self) -> str:
        if hasattr(self.artifact_type, "value"):
            return self.artifact_type.value
        return str(self.artifact_type)

    @property
    def evidence_coverage(self) -> float:
        return 1.0 if self.evidence_refs else 0.0

    def as_validation_payload(self) -> dict[str, Any]:
        return {
            "artifactType": self.artifact_type_value,
            "title": self.title,
            "content": self.content,
            "evidenceRefs": [ref.as_dict() for ref in self.evidence_refs],
            "generatorVersion": self.generator_version,
            "registryRefs": list(self.registry_refs),
            "assumptions": list(self.assumptions),
            "reviewRequired": self.review_required,
            "status": self.status.value,
            "extra": dict(self.extra),
        }


@dataclass(frozen=True)
class RenderedBundle:
    requested_output_type: str
    manifest: RenderedArtifact
    files: tuple[DraftFile, ...]
    blockers: tuple[str, ...] = ()

    @property
    def artifact_types(self) -> tuple[str, ...]:
        return tuple(file.artifact_type.value for file in self.files)

    @property
    def file_map(self) -> dict[str, str]:
        return {file.path: file.content for file in self.files}


def _sanitize_for_snapshot(value: Any) -> Any:
    if isinstance(value, Mapping):
        sanitized = {}
        for key, item in value.items():
            key_text = str(key)
            if _looks_secret_key(key_text):
                sanitized[key_text] = "REDACTED"
            else:
                sanitized[key_text] = _sanitize_for_snapshot(item)
        return sanitized
    if isinstance(value, list | tuple):
        return [_sanitize_for_snapshot(item) for item in value]
    return value


def _looks_secret_key(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in ("password", "secret", "token", "credential"))
