from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


ANALYSIS_VERSION = "analysis-local-v0.1"
CANONICAL_TARGET = "CanonicalAnalysisModel-compatible-local-v0.1"


class EvidenceStatus(StrEnum):
    OBSERVED = "OBSERVED"
    INFERRED_DESCRIPTION = "INFERRED_DESCRIPTION"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class ObjectType(StrEnum):
    PROCEDURE = "PROCEDURE"
    SYSTEM_PROCEDURE = "SYSTEM_PROCEDURE"
    TABLE = "TABLE"
    TEMP_TABLE = "TEMP_TABLE"


class DependencyOperation(StrEnum):
    READ = "READ"
    WRITE = "WRITE"
    EXECUTE = "EXECUTE"
    DECLARE = "DECLARE"
    UNKNOWN = "UNKNOWN"


class ParameterDirection(StrEnum):
    INPUT = "INPUT"
    OUTPUT = "OUTPUT"
    INPUT_OUTPUT = "INPUT_OUTPUT"


class EvidenceRef(BaseModel):
    source: str
    line: int | None = None
    snippet: str
    status: EvidenceStatus = EvidenceStatus.OBSERVED


class ReviewMarker(BaseModel):
    code: str
    message: str
    status: EvidenceStatus = EvidenceStatus.REVIEW_REQUIRED
    evidence: list[EvidenceRef] = Field(default_factory=list)


class ProcedureIdentifier(BaseModel):
    schema_name: str | None = None
    procedure_name: str
    full_name: str


class ProcedureParameter(BaseModel):
    name: str
    data_type: str
    default: str | None = None
    direction: ParameterDirection = ParameterDirection.INPUT
    evidence: list[EvidenceRef] = Field(default_factory=list)


class ProcedureSignature(BaseModel):
    identifier: ProcedureIdentifier
    parameters: list[ProcedureParameter] = Field(default_factory=list)
    evidence: list[EvidenceRef] = Field(default_factory=list)


class ObjectReference(BaseModel):
    schema_name: str | None = None
    object_name: str
    full_name: str
    object_type: ObjectType
    operation: DependencyOperation
    status: EvidenceStatus = EvidenceStatus.OBSERVED
    evidence: list[EvidenceRef] = Field(default_factory=list)


class ProcedureCall(BaseModel):
    schema_name: str | None = None
    procedure_name: str
    full_name: str
    object_type: ObjectType = ObjectType.PROCEDURE
    operation: DependencyOperation = DependencyOperation.EXECUTE
    is_dynamic_sql_executor: bool = False
    status: EvidenceStatus = EvidenceStatus.OBSERVED
    evidence: list[EvidenceRef] = Field(default_factory=list)
    review_notes: list[str] = Field(default_factory=list)


class TempTableFinding(BaseModel):
    name: str
    columns: list[str] = Field(default_factory=list)
    operation: DependencyOperation = DependencyOperation.DECLARE
    status: EvidenceStatus = EvidenceStatus.OBSERVED
    evidence: list[EvidenceRef] = Field(default_factory=list)


class PatternFinding(BaseModel):
    name: str
    detected: bool
    status: EvidenceStatus = EvidenceStatus.OBSERVED
    evidence: list[EvidenceRef] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class PatternSummary(BaseModel):
    transaction: PatternFinding
    try_catch: PatternFinding
    dynamic_sql: PatternFinding
    temp_table: PatternFinding


class DependencySummary(BaseModel):
    table_references: list[ObjectReference] = Field(default_factory=list)
    called_procedures: list[ProcedureCall] = Field(default_factory=list)
    temp_tables: list[TempTableFinding] = Field(default_factory=list)


class MetadataEnrichmentCandidate(BaseModel):
    table_full_name: str
    candidate_schema: str | None = None
    candidate_name: str | None = None
    source_fixture: str
    matched_fields: list[str] = Field(default_factory=list)
    status: EvidenceStatus = EvidenceStatus.OBSERVED
    note: str | None = None


class CanonicalConversionBlocker(BaseModel):
    code: str
    message: str
    target_path: str
    status: EvidenceStatus = EvidenceStatus.REVIEW_REQUIRED


class StoredProcedureAnalysisResult(BaseModel):
    analysis_version: str = ANALYSIS_VERSION
    contract_target: str = CANONICAL_TARGET
    source_name: str
    source_hash_sha256: str
    procedure: ProcedureSignature
    dependencies: DependencySummary
    patterns: PatternSummary
    metadata_enrichment: list[MetadataEnrichmentCandidate] = Field(default_factory=list)
    review_markers: list[ReviewMarker] = Field(default_factory=list)
    canonical_conversion_blockers: list[CanonicalConversionBlocker] = Field(default_factory=list)
