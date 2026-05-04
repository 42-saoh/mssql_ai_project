from __future__ import annotations

import hashlib
from pathlib import Path

from ai_agent_analysis.canonical import canonical_conversion_blockers
from ai_agent_analysis.dependencies import extract_dependencies
from ai_agent_analysis.detectors import detect_patterns
from ai_agent_analysis.enrichment import (
    SchemaSearchFixture,
    enrich_table_references_with_schema_search,
    load_schema_search_fixture,
)
from ai_agent_analysis.models import EvidenceStatus, ReviewMarker, StoredProcedureAnalysisResult
from ai_agent_analysis.parser import parse_procedure_signature


def analyze_stored_procedure(
    sql_text: str,
    *,
    source_name: str = "<memory>",
    schema_search_fixture: SchemaSearchFixture | None = None,
) -> StoredProcedureAnalysisResult:
    procedure, parser_review_markers = parse_procedure_signature(sql_text, source_name=source_name)
    dependencies = extract_dependencies(sql_text, source_name=source_name)
    patterns = detect_patterns(sql_text, source_name=source_name)
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
    return StoredProcedureAnalysisResult(
        source_name=source_name,
        source_hash_sha256=hashlib.sha256(sql_text.encode("utf-8")).hexdigest(),
        procedure=procedure,
        dependencies=dependencies,
        patterns=patterns,
        metadata_enrichment=metadata_enrichment,
        review_markers=review_markers,
        canonical_conversion_blockers=canonical_conversion_blockers(),
    )


def analyze_stored_procedure_file(
    sql_path: str | Path,
    *,
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
        schema_search_fixture=fixture,
    )
