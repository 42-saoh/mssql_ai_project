from __future__ import annotations

import json
import os
import uuid

import pytds


def main() -> None:
    conn = pytds.connect(
        dsn=os.environ["PLATFORM_DB_HOST"],
        port=int(os.environ["PLATFORM_DB_PORT"]),
        database=os.environ["PLATFORM_DB_NAME"],
        user=os.environ["PLATFORM_DB_USER"],
        password=os.environ["PLATFORM_DB_PASSWORD"],
        login_timeout=10,
        timeout=10,
        autocommit=False,
    )
    try:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT TABLE_NAME, COLUMN_NAME
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = 'dbo'
              AND COLUMN_NAME = 'CANON_TRGT_KEY_TXT'
            ORDER BY TABLE_NAME
            """,
        )
        print("CANON_COLUMNS", [tuple(row) for row in cur.fetchall()])

        requester = os.environ.get("PLATFORM_DB_REQUESTER_LOGIN", "codex-api-local")
        cur.execute(
            """
            SELECT TOP (1) CONVERT(NVARCHAR(36), USR_ID)
            FROM dbo.AUTH_USERS
            WHERE LGN_ID = %s OR EML_ADR = %s
            """,
            (requester, requester),
        )
        user = cur.fetchone()
        cur.execute(
            """
            SELECT TOP (1) CONVERT(NVARCHAR(36), DB_PRFL_ID)
            FROM dbo.CORE_DB_PROFILES
            WHERE DB_PRFL_NM = %s OR DB_NM = %s
            """,
            ("ppm", "ppm"),
        )
        profile = cur.fetchone()
        print("SEED", {"requester": bool(user), "ppmProfile": bool(profile)})
        if not user or not profile:
            return

        target_key = "mssql:ppm:-:procedure:dbo.getinspitemscd"
        cur.execute(
            """
            INSERT INTO dbo.CORE_WORK_REQUESTS(
                REQ_ID, REQ_TP_CD, REQR_USR_ID, DB_PRFL_ID, TRGT_PAYLD_JSON,
                DESIRED_RSLT_JSON, OPTN_PAYLD_JSON, CUR_STAT_CD, TRC_ID,
                CANON_TRGT_KEY_TXT, SUBMITTED_DTM, UPD_DTM
            )
            VALUES (
                %s, 'SP_ANALYSIS', %s, %s, %s, %s, %s, 'SUBMITTED', %s,
                %s, SYSUTCDATETIME(), SYSUTCDATETIME()
            )
            """,
            (
                str(uuid.uuid4()),
                user[0],
                profile[0],
                json.dumps({"type": "PROCEDURE", "schema": "dbo", "name": "GetInspItemsCd"}),
                json.dumps(["SP_ANALYSIS_DOCUMENT"]),
                json.dumps(
                    {
                        "__tracking": {
                            "dbProfileId": "ppm",
                            "correlationId": "diag",
                            "requestHash": "diag",
                            "targetKey": target_key,
                        }
                    }
                ),
                "diag_request",
                target_key,
            ),
        )
        print("INSERT_CHECK", "ok")
    finally:
        conn.rollback()
        conn.close()


if __name__ == "__main__":
    main()
