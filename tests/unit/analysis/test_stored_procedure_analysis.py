from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

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
    "sp_complex_patterns_v1": ROOT / "fixtures" / "analysis" / "sp_complex_patterns_v1.sql",
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
    assert _view_references(result) == expected["viewReferences"]
    assert _function_references(result) == expected["functionReferences"]
    assert _called_procedures(result) == expected["calledProcedures"]
    assert _call_graph(result) == expected["callGraph"]
    assert _result_sets(result) == expected["resultSets"]
    assert _patterns(result) == expected["patterns"]
    assert [todo.code for todo in result.todos] == expected["todoCodes"]
    assert result.overall_confidence.status.value == expected["confidence"]["status"]
    assert result.overall_confidence.score == expected["confidence"]["score"]
    assert result.evidence_assessment.review_required is True
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
    assert result.dependencies.view_references == []
    assert result.dependencies.function_references == []
    assert result.dependencies.called_procedures[0].full_name == "sp_executesql"
    assert result.dependencies.called_procedures[0].status.value == "REVIEW_REQUIRED"
    assert result.result_sets == []
    assert [todo.code for todo in result.todos] == [
        "DYNAMIC_SQL_DEPENDENCY_REVIEW",
        "DOMAIN_CONTRACT_MISSING",
    ]


def test_complex_fixture_detects_calls_functions_cursor_and_multi_result_sets() -> None:
    sql_path = SQL_FIXTURES["sp_complex_patterns_v1"]
    result = analyze_stored_procedure(
        sql_path.read_text(encoding="utf-8"),
        source_name=str(sql_path),
    )

    expected = EXPECTED["fixtures"]["sp_complex_patterns_v1"]
    assert _view_references(result) == expected["viewReferences"]
    assert _function_references(result) == expected["functionReferences"]
    assert result.patterns.cursor.detected is True
    assert result.patterns.multi_result_set.detected is True
    assert result.result_sets[0].columns[1].name == "STATUS_NM"
    assert result.result_sets[1].columns[0].status.value == "REVIEW_REQUIRED"
    assert result.call_graph[0].callee == "dbo.usp_GetOrderSummary"
    assert {summary.category for summary in result.business_rules} >= {
        "CALL_GRAPH",
        "DEPENDENCY",
        "PATTERN",
        "RESULT_SET",
    }


def test_cte_alias_is_not_table_dependency_and_cte_body_is_not_result_set() -> None:
    sql = """
    CREATE PROCEDURE dbo.usp_OrderCte
    AS
    BEGIN
        WITH order_cte AS (
            SELECT ORDER_ID, CUSTOMER_ID
            FROM dbo.TB_ORDER
        )
        SELECT ORDER_ID
        FROM order_cte;

        SELECT 1 AS STATIC_STATUS;
    END
    """

    result = analyze_stored_procedure(sql, source_name="cte-regression.sql")

    assert _table_references(result) == [
        {
            "fullName": "dbo.TB_ORDER",
            "objectType": "TABLE",
            "operation": "READ",
            "status": "OBSERVED",
        }
    ]
    assert _result_sets(result) == [
        {
            "ordinal": 1,
            "status": "OBSERVED",
            "columns": [{"name": "ORDER_ID", "status": "OBSERVED"}],
        },
        {
            "ordinal": 2,
            "status": "OBSERVED",
            "columns": [{"name": "STATIC_STATUS", "status": "OBSERVED"}],
        },
    ]
    assert result.patterns.multi_result_set.detected is True


def test_cte_alias_scope_does_not_hide_later_table_reference() -> None:
    sql = """
    CREATE PROCEDURE dbo.usp_OrderCteScope
    AS
    BEGIN
        WITH base_cte AS (
            SELECT ORDER_ID
            FROM dbo.TB_ORDER
        ),
        order_cte AS (
            SELECT ORDER_ID
            FROM base_cte
        )
        SELECT ORDER_ID
        FROM order_cte;

        SELECT ORDER_ID
        FROM order_cte;
    END
    """

    result = analyze_stored_procedure(sql, source_name="cte-scope-regression.sql")

    assert _table_references(result) == [
        {
            "fullName": "dbo.TB_ORDER",
            "objectType": "TABLE",
            "operation": "READ",
            "status": "OBSERVED",
        },
        {
            "fullName": "order_cte",
            "objectType": "TABLE",
            "operation": "READ",
            "status": "OBSERVED",
        },
    ]


def test_plain_variable_assignment_does_not_trigger_dynamic_sql() -> None:
    sql = """
    CREATE PROCEDURE dbo.usp_OrderCount
    AS
    BEGIN
        DECLARE @COUNT INT;
        SELECT @COUNT = COUNT(*)
        FROM dbo.TB_ORDER;

        SELECT @COUNT AS ORDER_COUNT;
    END
    """

    result = analyze_stored_procedure(sql, source_name="assignment-regression.sql")

    assert result.patterns.dynamic_sql.detected is False
    assert result.dependencies.called_procedures == []
    assert _table_references(result) == [
        {
            "fullName": "dbo.TB_ORDER",
            "objectType": "TABLE",
            "operation": "READ",
            "status": "OBSERVED",
        }
    ]
    assert _result_sets(result) == [
        {
            "ordinal": 1,
            "status": "OBSERVED",
            "columns": [{"name": "ORDER_COUNT", "status": "OBSERVED"}],
        }
    ]


def test_exec_parenthesized_variable_is_review_required_dynamic_sql() -> None:
    sql = """
    CREATE PROCEDURE dbo.usp_OrderDynamicExec
    AS
    BEGIN
        DECLARE @SQL NVARCHAR(MAX);
        SET @SQL = N'SELECT * FROM dbo.TB_ORDER';
        EXEC(@SQL);
    END
    """

    result = analyze_stored_procedure(sql, source_name="exec-dynamic-regression.sql")

    assert result.patterns.dynamic_sql.detected is True
    assert result.patterns.dynamic_sql.status.value == "REVIEW_REQUIRED"
    assert _called_procedures(result) == [
        {
            "fullName": "@SQL",
            "objectType": "PROCEDURE",
            "status": "REVIEW_REQUIRED",
            "isDynamicSqlExecutor": True,
        }
    ]
    assert result.dependencies.table_references == []
    assert result.result_sets == []
    assert [todo.code for todo in result.todos] == [
        "DYNAMIC_SQL_DEPENDENCY_REVIEW",
        "DOMAIN_CONTRACT_MISSING",
    ]


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
    assert candidate["evidenceRefs"]
    assert {ref["type"] for ref in candidate["evidenceRefs"]} == {"STATIC_ANALYSIS"}
    assert {ref["objectRef"] for ref in candidate["evidenceRefs"]} == {
        "dbo.usp_OrderSelect"
    }
    identifier = candidate["analysis_local"]["procedure"]["identifier"]
    assert identifier["full_name"] == "dbo.usp_OrderSelect"
    assert "overall_confidence" in candidate["analysis_local"]
    assert "todos" in candidate["analysis_local"]


def test_ppm_selected_sp_evidence_fixture_is_metadata_only() -> None:
    fixture_path = ROOT / "fixtures" / "analysis" / "ppm_selected_sp_evidence_v1.yaml"
    payload = yaml.safe_load(fixture_path.read_text(encoding="utf-8"))

    assert payload["selectionMode"] == "live_metadata"
    assert (
        payload["sourceManifest"]
        == "fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml"
    )
    assert payload["activeBlockers"] == []
    assert "DEPENDENCY_METADATA_INCOMPLETE" in payload["closedBlockers"]
    assert payload["dependencyEvidenceGate"]["status"] == (
        "PASSED_WITH_COMPLEX_SENTINEL_RESIDUAL_REVIEW"
    )
    assert [procedure["complexity"] for procedure in payload["storedProcedures"]] == [
        "simple",
        "medium",
        "complex",
        "medium",
        "medium",
        "complex",
        "complex",
    ]
    assert {
        f"{procedure['schema']}.{procedure['name']}" for procedure in payload["storedProcedures"]
    } == {
        "dbo.GetInspItemsCd",
        "dbo.PAD_GET_BAT_LIST_PRC",
        "dbo.PCS_PY_ManageInvoiceFldSchd_PRC",
        "dbo.PAD_REG_BAT_HIS_PRC",
        "dbo.PAD_SAVE_COM_CD_DTL_PRC",
        "dbo.PCO_BAT_CallDlvgPayAdjCyMail_PRC",
        "dbo.PCO_BAT_CallSendMail_PRC",
    }
    assert all(procedure["reviewRequired"] is False for procedure in payload["storedProcedures"])
    assert _secret_like_values(payload) == []
    forbidden_text = fixture_path.read_text(encoding="utf-8").lower()
    assert "definition:" not in forbidden_text
    assert "row_data" not in forbidden_text
    assert "password" not in forbidden_text


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
            "status": reference.status.value,
        }
        for reference in result.dependencies.table_references
    ]


def _view_references(result) -> list[dict[str, str]]:
    return [
        {
            "fullName": reference.full_name,
            "objectType": reference.object_type.value,
            "operation": reference.operation.value,
            "status": reference.status.value,
        }
        for reference in result.dependencies.view_references
    ]


def _function_references(result) -> list[dict[str, str]]:
    return [
        {
            "fullName": reference.full_name,
            "objectType": reference.object_type.value,
            "operation": reference.operation.value,
            "status": reference.status.value,
        }
        for reference in result.dependencies.function_references
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
        "cursor": result.patterns.cursor.detected,
        "multiResultSet": result.patterns.multi_result_set.detected,
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


def _call_graph(result) -> list[dict[str, str]]:
    return [
        {
            "caller": edge.caller,
            "callee": edge.callee,
            "status": edge.status.value,
        }
        for edge in result.call_graph
    ]


def _result_sets(result) -> list[dict[str, object]]:
    return [
        {
            "ordinal": result_set.ordinal,
            "status": result_set.status.value,
            "columns": [
                {
                    "name": column.name,
                    "status": column.status.value,
                }
                for column in result_set.columns
            ],
        }
        for result_set in result.result_sets
    ]


def _secret_like_values(payload, path: str = "$") -> list[str]:
    offenders: list[str] = []
    if isinstance(payload, dict):
        for key, value in payload.items():
            key_text = str(key).lower()
            nested_path = f"{path}.{key}"
            if any(marker in key_text for marker in ("password", "secret", "token", "api_key")):
                if value not in ("", None, 0):
                    offenders.append(nested_path)
            offenders.extend(_secret_like_values(value, nested_path))
    elif isinstance(payload, list):
        for index, item in enumerate(payload):
            offenders.extend(_secret_like_values(item, f"{path}[{index}]"))
    return offenders
