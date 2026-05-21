from __future__ import annotations

from ai_agent_analysis import build_context_packs, build_procedure_source_map

LARGE_SP = """
CREATE PROCEDURE dbo.usp_LargeConversion
    @OrderId int,
    @ActorId int
AS
BEGIN
    SET NOCOUNT ON;

    BEGIN TRY
        BEGIN TRAN;

        CREATE TABLE #Stage (OrderId int, StatusCode varchar(20));

        INSERT INTO #Stage (OrderId, StatusCode)
        SELECT o.OrderId, o.StatusCode
        FROM dbo.Orders o
        JOIN dbo.Customers c ON c.CustomerId = o.CustomerId
        WHERE o.OrderId = @OrderId;

        IF EXISTS (SELECT 1 FROM #Stage WHERE StatusCode = 'READY')
        BEGIN
            UPDATE dbo.Orders
            SET ProcessedBy = @ActorId
            WHERE OrderId = @OrderId;
        END;

        EXEC dbo.usp_RecalculateOrder @OrderId;

        DECLARE @sql nvarchar(max) = N'SELECT * FROM dbo.DynamicOnly WHERE OrderId = @p';
        EXEC sp_executesql @sql, N'@p int', @p = @OrderId;

        SELECT OrderId, StatusCode FROM #Stage;

        COMMIT;
    END TRY
    BEGIN CATCH
        ROLLBACK;
        THROW;
    END CATCH
END
""".strip()


def test_source_map_extracts_sanitized_spans_without_raw_sql_text() -> None:
    source_map = build_procedure_source_map(LARGE_SP, source_name="dbo.usp_LargeConversion")

    payload = source_map.to_storage_dict()
    kinds = {span["kind"] for span in payload["spans"]}
    serialized = str(payload)

    assert {"SIGNATURE", "PARAMETER_BLOCK", "DML", "RESULT_SET", "CALL"}.issubset(kinds)
    assert "TEMP_TABLE" in kinds
    assert "DYNAMIC_SQL" in kinds
    assert source_map.analysis_coverage["hasDynamicSql"] is True
    assert "SELECT o.OrderId" not in serialized
    assert "CREATE PROCEDURE" not in serialized
    assert any("dbo.Orders" in span["referencedObjects"] for span in payload["spans"])


def test_context_packs_bound_raw_text_to_selected_transient_spans() -> None:
    source_map = build_procedure_source_map(LARGE_SP, source_name="dbo.usp_LargeConversion")
    packs = build_context_packs(
        sql_text=LARGE_SP,
        source_map=source_map,
        target_ref="dbo.usp_LargeConversion",
        max_spans=3,
        source_token_budget=220,
    )

    pack = packs["conversion_readiness"]
    prompt_payload = pack.to_prompt_dict()
    storage_payload = pack.to_storage_dict()

    assert prompt_payload["selectedSpans"]
    assert any("text" in span for span in prompt_payload["selectedSpans"])
    assert all("text" not in span for span in storage_payload["selectedSpans"])
    assert storage_payload["skippedSpanCount"] > 0
    assert storage_payload["budgetStatus"] == "TRUNCATED_TO_BUDGET"
