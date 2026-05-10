from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, Field


ANALYSIS_VERSION = "analysis-local-v0.2"
CANONICAL_TARGET = "CanonicalAnalysisModel"


class EvidenceStatus(StrEnum):
    OBSERVED = "OBSERVED"
    INFERRED_DESCRIPTION = "INFERRED_DESCRIPTION"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class ObjectType(StrEnum):
    PROCEDURE = "PROCEDURE"
    SYSTEM_PROCEDURE = "SYSTEM_PROCEDURE"
    TABLE = "TABLE"
    VIEW = "VIEW"
    FUNCTION = "FUNCTION"
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


class ConfidenceScore(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    status: EvidenceStatus = EvidenceStatus.OBSERVED
    rationale: str
    factors: list[str] = Field(default_factory=list)


class TodoItem(BaseModel):
    code: str
    message: str
    status: EvidenceStatus = EvidenceStatus.REVIEW_REQUIRED
    evidence: list[EvidenceRef] = Field(default_factory=list)


class EvidenceAssessment(BaseModel):
    status: EvidenceStatus = EvidenceStatus.OBSERVED
    review_required: bool = False
    evidence_ref_count: int = 0
    observed_ref_count: int = 0
    review_required_ref_count: int = 0
    todo_count: int = 0
    notes: list[str] = Field(default_factory=list)


class RegistryVersionRef(BaseModel):
    registry_type: str
    version: str
    active: bool = True


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
    cursor: PatternFinding
    multi_result_set: PatternFinding


class DependencySummary(BaseModel):
    table_references: list[ObjectReference] = Field(default_factory=list)
    view_references: list[ObjectReference] = Field(default_factory=list)
    function_references: list[ObjectReference] = Field(default_factory=list)
    called_procedures: list[ProcedureCall] = Field(default_factory=list)
    temp_tables: list[TempTableFinding] = Field(default_factory=list)


class ResultSetColumnHint(BaseModel):
    name: str | None = None
    expression: str
    status: EvidenceStatus = EvidenceStatus.OBSERVED
    evidence: list[EvidenceRef] = Field(default_factory=list)
    review_notes: list[str] = Field(default_factory=list)


class ResultSetHint(BaseModel):
    ordinal: int
    source: str = "STATIC_SELECT"
    columns: list[ResultSetColumnHint] = Field(default_factory=list)
    status: EvidenceStatus = EvidenceStatus.OBSERVED
    evidence: list[EvidenceRef] = Field(default_factory=list)
    review_notes: list[str] = Field(default_factory=list)


class CallGraphEdge(BaseModel):
    caller: str
    callee: str
    operation: DependencyOperation = DependencyOperation.EXECUTE
    status: EvidenceStatus = EvidenceStatus.OBSERVED
    evidence: list[EvidenceRef] = Field(default_factory=list)
    review_notes: list[str] = Field(default_factory=list)


class BusinessRuleSummary(BaseModel):
    category: str
    summary: str
    status: EvidenceStatus = EvidenceStatus.OBSERVED
    evidence: list[EvidenceRef] = Field(default_factory=list)
    inferred_from: list[str] = Field(default_factory=list)


class ModernizationPoint(BaseModel):
    code: str
    summary: str
    status: EvidenceStatus = EvidenceStatus.REVIEW_REQUIRED
    evidence: list[EvidenceRef] = Field(default_factory=list)
    inferred_from: list[str] = Field(default_factory=list)


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
    snapshot_id: str | None = None
    registry_version_refs: list[RegistryVersionRef] = Field(default_factory=list)
    procedure: ProcedureSignature
    dependencies: DependencySummary
    patterns: PatternSummary
    result_sets: list[ResultSetHint] = Field(default_factory=list)
    call_graph: list[CallGraphEdge] = Field(default_factory=list)
    business_rules: list[BusinessRuleSummary] = Field(default_factory=list)
    modernization_points: list[ModernizationPoint] = Field(default_factory=list)
    todos: list[TodoItem] = Field(default_factory=list)
    evidence_assessment: EvidenceAssessment = Field(default_factory=EvidenceAssessment)
    overall_confidence: ConfidenceScore = Field(
        default_factory=lambda: ConfidenceScore(
            score=0.0,
            status=EvidenceStatus.REVIEW_REQUIRED,
            rationale="Analysis confidence has not been calculated.",
        )
    )
    metadata_enrichment: list[MetadataEnrichmentCandidate] = Field(default_factory=list)
    review_markers: list[ReviewMarker] = Field(default_factory=list)
    canonical_conversion_blockers: list[CanonicalConversionBlocker] = Field(default_factory=list)
