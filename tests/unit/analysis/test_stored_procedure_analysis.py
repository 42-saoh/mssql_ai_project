from __future__ import annotations

import json
from pathlib import Path

import pytest

from ai_agent_analysis import (
    analyze_stored_procedure,
    load_schema_search_fixture,
    to_canonical_candidate,
)


ROOT = Path(__file__).resolve().parents[3]
EXPECTED = json.loads(
    (ROOT / "fixtures" / "analysis" / "expected_sp_analysis_core_v1.json").read_text(
        encoding="utf-8"
    )
)

SQL_FIXTURES = {
    "sp_simple_crud": ROOT / "fixtures" / "mssql" / "sp_simple_crud.sql",
    "sp_txn_with_try_catch": ROOT / "fixtures" / "mssql" / "sp_txn_with_try_catch.sql",
    "sp_with_dynamic_sql": ROOT / "fixtures" / "mssql" / "sp_with_dynamic_sql.sql",
    "sp_with_temp_table": ROOT / "fixtures" / "mssql" / "sp_with_temp_table.sql",
}


@pytest.mark.parametrize("fixture_name", sorted(SQL_FIXTURES))
def test_analysis_core_matches_expected_fixture(fixture_name: str) -> None:
    expected = EXPECTED["fixtures"][fixture_name]
    sql_path = SQL_FIXTURES[fixture_name]
    schema_fixture_path = ROOT / "fixtures" / "metadata" / "schema_search_order_domain.json"
    schema_fixture = (
        load_schema_search_fixture(schema_fixture_path)
        if "metadataEnrichment" in expected
        else None
    )

    result = analyze_stored_procedure(
        sql_path.read_text(encoding="utf-8"),
        source_name=str(sql_path),
        schema_search_fixture=schema_fixture,
    )

    assert result.analysis_version == EXPECTED["analysisVersion"]
    assert len(result.source_hash_sha256) == 64
    assert result.procedure.identifier.full_name == expected["procedureFullName"]
    assert _parameters(result) == expected["parameters"]
    assert _table_references(result) == expected["tableReferences"]
    assert _called_procedures(result) == expected["calledProcedures"]
    assert _patterns(result) == expected["patterns"]
    assert result.canonical_conversion_blockers[0].code == "DOMAIN_CONTRACT_MISSING"

    if "tempTables" in expected:
        assert _temp_tables(result) == expected["tempTables"]
    if "metadataEnrichment" in expected:
        assert _metadata_enrichment(result) == expected["metadataEnrichment"]
    if "reviewMarkers" in expected:
        assert [marker.code for marker in result.review_markers] == expected["reviewMarkers"]


def test_dynamic_sql_dependencies_are_not_inferred_from_string_literals() -> None:
    sql_path = SQL_FIXTURES["sp_with_dynamic_sql"]
    result = analyze_stored_procedure(
        sql_path.read_text(encoding="utf-8"),
        source_name=str(sql_path),
    )

    assert result.patterns.dynamic_sql.detected is True
    assert result.patterns.dynamic_sql.status.value == "REVIEW_REQUIRED"
    assert result.dependencies.table_references == []
    assert result.dependencies.called_procedures[0].full_name == "sp_executesql"
    assert result.dependencies.called_procedures[0].status.value == "REVIEW_REQUIRED"


def test_schema_search_fixture_enriches_known_order_table() -> None:
    sql_path = SQL_FIXTURES["sp_simple_crud"]
    schema_fixture = load_schema_search_fixture(
        ROOT / "fixtures" / "metadata" / "schema_search_order_domain.json"
    )

    result = analyze_stored_procedure(
        sql_path.read_text(encoding="utf-8"),
        source_name=str(sql_path),
        schema_search_fixture=schema_fixture,
    )

    assert _metadata_enrichment(result) == [
        {
            "tableFullName": "dbo.TB_ORDER",
            "candidateFullName": "dbo.TB_ORDER",
            "status": "OBSERVED",
        }
    ]


def test_canonical_candidate_reports_domain_contract_blocker() -> None:
    sql_path = SQL_FIXTURES["sp_simple_crud"]
    result = analyze_stored_procedure(
        sql_path.read_text(encoding="utf-8"),
        source_name=str(sql_path),
    )

    candidate = to_canonical_candidate(result)

    assert candidate["target_contract"] == "CanonicalAnalysisModel"
    assert candidate["status"] == "REVIEW_REQUIRED"
    assert candidate["blockers"][0]["code"] == "DOMAIN_CONTRACT_MISSING"
    identifier = candidate["analysis_local"]["procedure"]["identifier"]
    assert identifier["full_name"] == "dbo.usp_OrderSelect"


def _parameters(result) -> list[dict[str, str]]:
    return [
        {
            "name": parameter.name,
            "dataType": parameter.data_type,
            "direction": parameter.direction.value,
        }
        for parameter in result.procedure.parameters
    ]


def _table_references(result) -> list[dict[str, str]]:
    return [
        {
            "fullName": reference.full_name,
            "objectType": reference.object_type.value,
            "operation": reference.operation.value,
        }
        for reference in result.dependencies.table_references
    ]


def _called_procedures(result) -> list[dict[str, object]]:
    return [
        {
            "fullName": call.full_name,
            "objectType": call.object_type.value,
            "status": call.status.value,
            "isDynamicSqlExecutor": call.is_dynamic_sql_executor,
        }
        for call in result.dependencies.called_procedures
    ]


def _patterns(result) -> dict[str, bool]:
    return {
        "transaction": result.patterns.transaction.detected,
        "tryCatch": result.patterns.try_catch.detected,
        "dynamicSql": result.patterns.dynamic_sql.detected,
        "tempTable": result.patterns.temp_table.detected,
    }


def _temp_tables(result) -> list[dict[str, object]]:
    return [
        {"name": temp_table.name, "columns": temp_table.columns}
        for temp_table in result.dependencies.temp_tables
    ]


def _metadata_enrichment(result) -> list[dict[str, str]]:
    return [
        {
            "tableFullName": enrichment.table_full_name,
            "candidateFullName": f"{enrichment.candidate_schema}.{enrichment.candidate_name}",
            "status": enrichment.status.value,
        }
        for enrichment in result.metadata_enrichment
    ]
