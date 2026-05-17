from __future__ import annotations

from ai_agent_analysis import extract_statement_evidence

SANITIZED_MANAGE_BOND_SQL = """
CREATE PROCEDURE PPM.dbo.PCO_GU_ManageBond_PRC
    @CRUDFlag varchar(20),
    @GUBUNFlag varchar(1),
    @ContractNum varchar(10),
    @OrdNum smallint,
    @BondKindCode varchar(3),
    @Sequence smallint,
    @ApprovalYN varchar(1),
    @CurrencyInsureAmt decimal(18,3),
    @UserID varchar(50),
    @SValue varchar(max)
AS
BEGIN
    IF @CRUDFlag = 'R'
    BEGIN
        SELECT CTRT_NO, ORDR_NO, GUAR_TP_CD, GUAR_ST_CD
        FROM PPM.dbo.PCO_GUAR
        WHERE CTRT_NO = @ContractNum AND ORDR_NO = @OrdNum;
    END

    IF @CRUDFlag = 'A'
    BEGIN
        UPDATE PPM.dbo.PCO_GUAR
        SET GUAR_APRV_YN = @ApprovalYN, GUAR_ST_CD = '060'
        WHERE CTRT_NO = @ContractNum AND ORDR_NO = @OrdNum;

        UPDATE ERP.dbo.XXEAI_TRX_HEADER_II
        SET DUE_DATE = GETDATE()
        WHERE INVOICE_NUM = @Sequence;

        EXEC PPM.dbo.PCS_PY_SaveInvoicePrepaidReg_PRC @ContractNum, @OrdNum, @UserID;
    END

    IF @CRUDFlag = 'C'
    BEGIN
        INSERT INTO PPM.dbo.PCO_GUAR (CTRT_NO, ORDR_NO, GUAR_TP_CD, GUAR_AMT)
        SELECT @ContractNum, @OrdNum, @BondKindCode, @CurrencyInsureAmt;

        UPDATE PPM.dbo.PCS_RTNM_PAYRPT
        SET RTNM_GUAR_SEQ_NO = @Sequence
        WHERE CTRT_NO = @ContractNum;
    END

    IF @CRUDFlag = 'U'
    BEGIN
        UPDATE PPM.dbo.PCO_GUAR
        SET GUAR_AMT = @CurrencyInsureAmt, MODF_USR_ID = @UserID
        WHERE CTRT_NO = @ContractNum AND GUAR_SEQ = @Sequence;
    END

    IF @CRUDFlag = 'D'
    BEGIN
        DELETE FROM PPM.dbo.PCO_ATTC_FIL_DTL WHERE ATTC_FIL_ID = @Sequence;
        DELETE FROM PPM.dbo.PCO_GUAR WHERE CTRT_NO = @ContractNum AND GUAR_SEQ = @Sequence;
    END

    IF @CRUDFlag = 'VENDOR_U'
    BEGIN
        UPDATE PPM.dbo.PCS_ADVM_PAYRPT
        SET VNDR_GUAR_NO = @SValue
        WHERE CTRT_NO = @ContractNum AND @GUBUNFlag = 'J';
    END

    IF @CRUDFlag = 'ONLINE_U'
    BEGIN
        UPDATE PPM.dbo.PCS_PAY_CMPD_RPT
        SET ONLINE_GUAR_NO = @SValue
        WHERE CTRT_NO = @ContractNum AND @GUBUNFlag = 'G';
    END
END
""".strip()


def test_extractor_produces_sanitized_statement_evidence_for_manage_bond_branches() -> None:
    result = extract_statement_evidence(
        SANITIZED_MANAGE_BOND_SQL,
        target_ref="PPM.dbo.PCO_GU_ManageBond_PRC",
        source_name="sanitized_p41_manage_bond.sql",
    )

    operations = {statement.operation.value for statement in result.statement_evidence}
    phases = {statement.phase for statement in result.statement_evidence}

    assert {"SELECT", "INSERT", "UPDATE", "DELETE", "EXECUTE"} <= operations
    assert {
        "crud_r_select",
        "crud_a_update",
        "crud_c_insert",
        "crud_u_update",
        "crud_d_delete",
        "crud_vendor_u_update",
        "crud_online_u_update",
    } <= phases
    assert len(result.statement_evidence) >= 10
    assert result.production_ready is False


def test_extractor_keeps_cross_db_and_called_procedure_uncertainty_review_required() -> None:
    result = extract_statement_evidence(
        SANITIZED_MANAGE_BOND_SQL,
        target_ref="PPM.dbo.PCO_GU_ManageBond_PRC",
        source_name="sanitized_p41_manage_bond.sql",
    )

    erp_statement = next(
        statement for statement in result.statement_evidence if statement.target_ref.startswith("ERP.")
    )
    call_statement = next(
        statement
        for statement in result.statement_evidence
        if statement.operation.value == "EXECUTE"
    )

    assert erp_statement.cross_database is True
    assert erp_statement.status.value == "REVIEW_REQUIRED"
    assert "CROSS_DB_WRITE_REVIEW_REQUIRED" in erp_statement.review_markers
    assert call_statement.status.value == "REVIEW_REQUIRED"
    assert "CALLED_PROCEDURE_IO_REVIEW_REQUIRED" in call_statement.review_markers


def test_extractor_storage_payload_does_not_persist_raw_sql_text() -> None:
    result = extract_statement_evidence(
        SANITIZED_MANAGE_BOND_SQL,
        target_ref="PPM.dbo.PCO_GU_ManageBond_PRC",
        source_name="sanitized_p41_manage_bond.sql",
    )

    payload = result.to_storage_dict()
    serialized = str(payload)

    assert payload["statementEvidence"]
    assert "CREATE PROCEDURE" not in serialized
    assert "SET GUAR_APRV_YN" not in serialized
    assert "WHERE CTRT_NO" not in serialized
    assert all(statement["evidenceRefs"] for statement in payload["statementEvidence"])
