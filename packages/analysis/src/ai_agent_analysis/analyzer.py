from __future__ import annotations

import hashlib
from pathlib import Path

from ai_agent_analysis.assessment import (
    assess_evidence,
    build_call_graph,
    build_todos,
    calculate_overall_confidence,
    summarize_business_rules,
    summarize_modernization_points,
)
from ai_agent_analysis.canonical import canonical_conversion_blockers
from ai_agent_analysis.dependencies import extract_dependencies
from ai_agent_analysis.detectors import detect_patterns
from ai_agent_analysis.enrichment import (
    SchemaSearchFixture,
    enrich_table_references_with_schema_search,
    load_schema_search_fixture,
)
from ai_agent_analysis.models import (
    EvidenceStatus,
    RegistryVersionRef,
    ReviewMarker,
    StoredProcedureAnalysisResult,
)
from ai_agent_analysis.parser import parse_procedure_signature
from ai_agent_analysis.result_sets import extract_result_set_hints


def analyze_stored_procedure(
    sql_text: str,
    *,
    source_name: str = "<memory>",
    snapshot_id: str | None = None,
    registry_version_refs: list[RegistryVersionRef | dict[str, object]] | None = None,
    schema_search_fixture: SchemaSearchFixture | None = None,
) -> StoredProcedureAnalysisResult:
    registry_refs = _normalize_registry_refs(registry_version_refs)
    procedure, parser_review_markers = parse_procedure_signature(sql_text, source_name=source_name)
    dependencies = extract_dependencies(sql_text, source_name=source_name)
    patterns = detect_patterns(sql_text, source_name=source_name)
    result_sets = extract_result_set_hints(sql_text, source_name=source_name)
    review_markers = [*parser_review_markers]
    if patterns.dynamic_sql.detected:
        review_markers.append(
            ReviewMarker(
                code="DYNAMIC_SQL_DEPENDENCY_REVIEW",
                message=(
                    "Dynamic SQL was detected; dependencies inside the generated SQL text are "
                    "not asserted by the static parser."
                ),
                evidence=patterns.dynamic_sql.evidence,
            )
        )
    if (
        not procedure.identifier.procedure_name
        or procedure.identifier.procedure_name == "REVIEW_REQUIRED"
    ):
        review_markers.append(
            ReviewMarker(
                code="PROCEDURE_NAME_REVIEW",
                message="Procedure name could not be resolved from static text.",
                status=EvidenceStatus.REVIEW_REQUIRED,
            )
        )
    metadata_enrichment = (
        enrich_table_references_with_schema_search(
            dependencies.table_references,
            schema_search_fixture,
        )
        if schema_search_fixture is not None
        else []
    )
    blockers = canonical_conversion_blockers(
        snapshot_id=snapshot_id,
        registry_version_refs=registry_refs,
    )
    call_graph = build_call_graph(procedure, dependencies)
    business_rules = summarize_business_rules(dependencies, patterns, result_sets)
    modernization_points = summarize_modernization_points(dependencies, patterns)
    todos = build_todos(dependencies, patterns, result_sets, blockers)
    overall_confidence = calculate_overall_confidence(
        dependencies,
        patterns,
        result_sets,
        review_markers,
        todos,
        blockers,
    )
    evidence_assessment = assess_evidence(
        [
            procedure,
            dependencies,
            patterns,
            result_sets,
            call_graph,
            business_rules,
            modernization_points,
            review_markers,
            blockers,
        ],
        todos,
    )
    return StoredProcedureAnalysisResult(
        source_name=source_name,
        source_hash_sha256=hashlib.sha256(sql_text.encode("utf-8")).hexdigest(),
        snapshot_id=snapshot_id,
        registry_version_refs=registry_refs,
        procedure=procedure,
        dependencies=dependencies,
        patterns=patterns,
        result_sets=result_sets,
        call_graph=call_graph,
        business_rules=business_rules,
        modernization_points=modernization_points,
        todos=todos,
        evidence_assessment=evidence_assessment,
        overall_confidence=overall_confidence,
        metadata_enrichment=metadata_enrichment,
        review_markers=review_markers,
        canonical_conversion_blockers=blockers,
    )


def analyze_stored_procedure_file(
    sql_path: str | Path,
    *,
    snapshot_id: str | None = None,
    registry_version_refs: list[RegistryVersionRef | dict[str, object]] | None = None,
    schema_search_fixture_path: str | Path | None = None,
) -> StoredProcedureAnalysisResult:
    path = Path(sql_path)
    fixture = (
        load_schema_search_fixture(schema_search_fixture_path)
        if schema_search_fixture_path is not None
        else None
    )
    return analyze_stored_procedure(
        path.read_text(encoding="utf-8"),
        source_name=str(path),
        snapshot_id=snapshot_id,
        registry_version_refs=registry_version_refs,
        schema_search_fixture=fixture,
    )


def _normalize_registry_refs(
    registry_version_refs: list[RegistryVersionRef | dict[str, object]] | None,
) -> list[RegistryVersionRef]:
    return [
        ref if isinstance(ref, RegistryVersionRef) else RegistryVersionRef.model_validate(ref)
        for ref in (registry_version_refs or [])
    ]
