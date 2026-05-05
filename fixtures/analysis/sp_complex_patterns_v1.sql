CREATE PROCEDURE dbo.usp_OrderComplex
    @ORDER_ID INT
AS
BEGIN
    SET NOCOUNT ON;

    DECLARE order_cursor CURSOR FOR
        SELECT ORDER_ID
        FROM dbo.TB_ORDER;

    OPEN order_cursor;
    FETCH NEXT FROM order_cursor INTO @ORDER_ID;
    CLOSE order_cursor;
    DEALLOCATE order_cursor;

    SELECT
        o.ORDER_ID,
        dbo.fn_NormalizeOrderStatus(o.STATUS_CD) AS STATUS_NM
    FROM dbo.TB_ORDER AS o
    WHERE o.ORDER_ID = @ORDER_ID;

    SELECT *
    FROM dbo.VW_ORDER_SUMMARY
    WHERE ORDER_ID = @ORDER_ID;

    EXEC dbo.usp_GetOrderSummary @OrderId = @ORDER_ID;
END
