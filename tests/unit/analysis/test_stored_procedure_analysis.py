from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml
from ai_agent_analysis import (
    analyze_stored_procedure,
    complexity_metrics,
    extract_dml_operations,
    load_schema_search_fixture,
    migration_guide_static_metrics,
    to_canonical_analysis_model,
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

CANONICAL_SNAPSHOT_ID = "mcp-fixture-snapshot-0001"
CANONICAL_REGISTRY_REFS = [
    {"registry_type": "PROMPT", "version": "prompt:sp_analysis@0.1.0", "active": True},
    {"registry_type": "TEMPLATE", "version": "template:sp_analysis_doc@0.1.0", "active": True},
    {"registry_type": "POLICY", "version": "policy:analysis_static_rules@0.1.0", "active": True},
]


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
    assert [todo.code for todo in result.todos] == _expected_todo_codes(
        expected["todoCodes"]
    )
    assert result.overall_confidence.status.value == expected["confidence"]["status"]
    assert result.overall_confidence.score == _expected_confidence_score(
        expected["confidence"]["score"],
        expected["todoCodes"],
    )
    assert result.evidence_assessment.review_required is True
    assert [blocker.code for blocker in result.canonical_conversion_blockers] == [
        "SNAPSHOT_ID_BINDING_MISSING",
        "REGISTRY_VERSION_REFS_MISSING",
    ]

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
        "SNAPSHOT_ID_BINDING_MISSING",
        "REGISTRY_VERSION_REFS_MISSING",
    ]


def test_migration_guide_dml_operations_keep_exact_verbs_and_ignore_string_literals() -> None:
    sql = """
    CREATE PROCEDURE dbo.usp_GuideDml
    AS
    BEGIN
        SELECT a.Id FROM dbo.SourceA a JOIN ERP.dbo.SourceB b ON b.Id = a.Id;
        INSERT INTO dbo.AuditA (Id) SELECT Id FROM dbo.SourceA;
        UPDATE dbo.TargetA SET StatusCode = 'DONE';
        DELETE FROM dbo.TargetB WHERE IsExpired = 1;
        MERGE INTO dbo.TargetC AS target USING dbo.SourceA AS src ON src.Id = target.Id
        WHEN MATCHED THEN UPDATE SET StatusCode = 'MERGED';
        DECLARE @sql nvarchar(max) = N'SELECT * FROM dbo.HiddenTable';
        EXEC sp_executesql @sql;
    END
    """

    operations = extract_dml_operations(sql, source_name="guide-dml.sql")
    operation_pairs = {(item["operation"], item["targetRef"]) for item in operations}

    assert ("SELECT", "dbo.SourceA") in operation_pairs
    assert ("SELECT", "ERP.dbo.SourceB") in operation_pairs
    assert ("INSERT", "dbo.AuditA") in operation_pairs
    assert ("UPDATE", "dbo.TargetA") in operation_pairs
    assert ("DELETE", "dbo.TargetB") in operation_pairs
    assert ("MERGE", "dbo.TargetC") in operation_pairs
    assert all("HiddenTable" not in item["targetRef"] for item in operations)


def test_static_dependency_parser_preserves_mssql_three_part_table_names() -> None:
    sql = """
    CREATE PROCEDURE dbo.usp_FullTableRefs
    AS
    BEGIN
        SELECT c.ContractNum
        FROM PPM.dbo.PCS_CTRT c
        JOIN [ERP].[dbo].[XXEAI_TRX_HEADER_II] h ON h.ContractNum = c.ContractNum
        JOIN dbo.LocalLookup l ON l.ContractNum = c.ContractNum;

        UPDATE dbo.LocalTarget SET StatusCode = 'DONE';
    END
    """

    result = analyze_stored_procedure(sql, source_name="full-table-refs.sql")
    references = {
        (item["fullName"], item["operation"]) for item in _table_references(result)
    }

    assert ("PPM.dbo.PCS_CTRT", "READ") in references
    assert ("ERP.dbo.XXEAI_TRX_HEADER_II", "READ") in references
    assert ("dbo.LocalLookup", "READ") in references
    assert ("dbo.LocalTarget", "WRITE") in references


def test_migration_guide_complexity_metrics_are_deterministic_counts() -> None:
    sql = """
    CREATE PROCEDURE dbo.usp_GuideMetrics
    AS
    BEGIN
        BEGIN TRY
            BEGIN TRAN;
            IF @Mode = 'A'
                SELECT CASE WHEN Flag = 1 THEN 1 ELSE 0 END FROM ERP.dbo.SourceA;
            WHILE @i < 3
                SET @i = @i + 1;
            DECLARE cur CURSOR FOR SELECT Id FROM dbo.SourceB;
            OPEN cur;
            FETCH NEXT FROM cur;
            CLOSE cur;
            DEALLOCATE cur;
            EXEC(@sql);
            COMMIT TRAN;
            RETURN;
        END TRY
        BEGIN CATCH
            ROLLBACK TRAN;
            GOTO ErrorHandler;
        END CATCH
    ErrorHandler:
        RETURN;
    END
    """

    metrics = {item["metric"]: item["count"] for item in complexity_metrics(sql)}
    guide_metrics = migration_guide_static_metrics(sql, source_name="guide-metrics.sql")

    assert metrics["BEGIN_END_BLOCK"] >= 3
    assert metrics["IF"] == 1
    assert metrics["WHILE"] == 1
    assert metrics["CASE"] == 1
    assert metrics["GOTO"] == 1
    assert metrics["RETURN"] == 2
    assert metrics["CURSOR_SIGNAL"] >= 5
    assert metrics["TRY_CATCH_BLOCK"] == 2
    assert metrics["TRANSACTION_SIGNAL"] == 3
    assert metrics["DYNAMIC_SQL_SIGNAL"] == 1
    assert metrics["CROSS_DB_REFERENCE"] == 1
    assert guide_metrics["crossDatabaseReferences"] == ["ERP.dbo.SourceA"]


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
        "SNAPSHOT_ID_BINDING_MISSING",
        "REGISTRY_VERSION_REFS_MISSING",
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


def test_canonical_candidate_reports_binding_blockers_by_default() -> None:
    sql_path = SQL_FIXTURES["sp_simple_crud"]
    result = analyze_stored_procedure(
        sql_path.read_text(encoding="utf-8"),
        source_name=str(sql_path),
    )

    candidate = to_canonical_candidate(result)

    assert candidate["target_contract"] == "CanonicalAnalysisModel"
    assert candidate["status"] == "REVIEW_REQUIRED"
    assert [blocker["code"] for blocker in candidate["blockers"]] == [
        "SNAPSHOT_ID_BINDING_MISSING",
        "REGISTRY_VERSION_REFS_MISSING",
    ]
    assert "canonical_model" not in candidate
    assert candidate["evidenceRefs"]
    assert {ref["type"] for ref in candidate["evidenceRefs"]} == {"STATIC_ANALYSIS"}
    assert {ref["objectRef"] for ref in candidate["evidenceRefs"]} == {
        "dbo.usp_OrderSelect"
    }
    identifier = candidate["analysis_local"]["procedure"]["identifier"]
    assert identifier["full_name"] == "dbo.usp_OrderSelect"
    assert "overall_confidence" in candidate["analysis_local"]
    assert "todos" in candidate["analysis_local"]


def test_canonical_candidate_builds_domain_model_when_bindings_exist() -> None:
    sql_path = SQL_FIXTURES["sp_simple_crud"]
    result = analyze_stored_procedure(
        sql_path.read_text(encoding="utf-8"),
        source_name=str(sql_path),
        snapshot_id=CANONICAL_SNAPSHOT_ID,
        registry_version_refs=CANONICAL_REGISTRY_REFS,
    )

    canonical_model = to_canonical_analysis_model(result)
    candidate = to_canonical_candidate(result)

    assert result.canonical_conversion_blockers == []
    assert canonical_model.schema_version == "CanonicalAnalysisModel.v2"
    assert canonical_model.snapshot_id == CANONICAL_SNAPSHOT_ID
    assert [ref.version for ref in canonical_model.registry_version_refs] == [
        ref["version"] for ref in CANONICAL_REGISTRY_REFS
    ]
    assert canonical_model.procedure.identifier.full_name == "dbo.usp_OrderSelect"
    assert canonical_model.evidence_refs
    assert candidate["status"] == "CONTRACT_CLOSED"
    assert candidate["blockers"] == []
    assert candidate["canonical_model"]["snapshot_id"] == CANONICAL_SNAPSHOT_ID


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


def _expected_todo_codes(codes: list[str]) -> list[str]:
    expanded: list[str] = []
    for code in codes:
        if code == "DOMAIN_CONTRACT_MISSING":
            expanded.extend(
                [
                    "SNAPSHOT_ID_BINDING_MISSING",
                    "REGISTRY_VERSION_REFS_MISSING",
                ]
            )
        else:
            expanded.append(code)
    return expanded


def _expected_confidence_score(score: float, todo_codes: list[str]) -> float:
    return round(score - 0.03, 2) if "DOMAIN_CONTRACT_MISSING" in todo_codes else score
