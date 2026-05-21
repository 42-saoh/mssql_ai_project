/*
  MSSQL Analysis Agent Platform
  Platform DB Required Seed Draft v11

  Manual apply only. Codex and the API must not execute this file automatically.
  Review and replace host placeholders before applying in a live environment.
  This file stores only profile identifiers, placeholder host names, role names,
  and local bootstrap actor metadata.
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

MERGE dbo.AUTH_ROLES AS tgt
USING (
    VALUES
        (N'USER', N'General platform user'),
        (N'ADMIN', N'Platform administrator'),
        (N'AUDITOR', N'Audit log reader')
) AS src (AUTH_GRP_NM, AUTH_GRP_DESC)
ON tgt.AUTH_GRP_NM = src.AUTH_GRP_NM
WHEN MATCHED THEN
    UPDATE SET AUTH_GRP_DESC = src.AUTH_GRP_DESC
WHEN NOT MATCHED THEN
    INSERT (AUTH_GRP_NM, AUTH_GRP_DESC)
    VALUES (src.AUTH_GRP_NM, src.AUTH_GRP_DESC);
GO

DECLARE @RequesterLogin NVARCHAR(100) = N'codex-api-local';
DECLARE @RequesterName NVARCHAR(200) = N'Codex API Local';

MERGE dbo.AUTH_USERS AS tgt
USING (
    VALUES (@RequesterLogin, @RequesterName, NULL, N'ACTIVE')
) AS src (LGN_ID, USR_NM, EML_ADR, STAT_CD)
ON tgt.LGN_ID = src.LGN_ID
WHEN MATCHED THEN
    UPDATE SET
        USR_NM = src.USR_NM,
        STAT_CD = src.STAT_CD,
        UPD_DTM = SYSUTCDATETIME()
WHEN NOT MATCHED THEN
    INSERT (LGN_ID, USR_NM, EML_ADR, STAT_CD)
    VALUES (src.LGN_ID, src.USR_NM, src.EML_ADR, src.STAT_CD);
GO

DECLARE @RequesterUserId UNIQUEIDENTIFIER;
DECLARE @UserRoleId UNIQUEIDENTIFIER;

SELECT @RequesterUserId = USR_ID
FROM dbo.AUTH_USERS
WHERE LGN_ID = N'codex-api-local';

SELECT @UserRoleId = AUTH_GRP_ID
FROM dbo.AUTH_ROLES
WHERE AUTH_GRP_NM = N'USER';

IF @RequesterUserId IS NOT NULL
   AND @UserRoleId IS NOT NULL
   AND NOT EXISTS (
       SELECT 1
       FROM dbo.AUTH_USER_ROLES
       WHERE USR_ID = @RequesterUserId
         AND AUTH_GRP_ID = @UserRoleId
   )
BEGIN
    INSERT INTO dbo.AUTH_USER_ROLES (USR_ID, AUTH_GRP_ID, GRT_USR_ID)
    VALUES (@RequesterUserId, @UserRoleId, @RequesterUserId);
END;
GO

DECLARE @PlfHost NVARCHAR(255) = N'REVIEW_REQUIRED_PLF_HOST';
DECLARE @MetadataHost NVARCHAR(255) = N'REVIEW_REQUIRED_METADATA_HOST';
DECLARE @SqlServerPort INT = 1433;
DECLARE @SeedMetaJson NVARCHAR(MAX) = N'{"seedVersion":"v11","seedStatus":"REVIEW_REQUIRED","note":"Review host placeholders before live use."}';

MERGE dbo.CORE_DB_PROFILES AS tgt
USING (
    VALUES
        (N'plf', N'MSSQL', @PlfHost, @SqlServerPort, N'PLF', @SeedMetaJson, NULL, N'Y', N'ACTIVE'),
        (N'master', N'MSSQL', @MetadataHost, @SqlServerPort, N'master', @SeedMetaJson, NULL, N'Y', N'ACTIVE'),
        (N'ppm', N'MSSQL', @MetadataHost, @SqlServerPort, N'PPM', @SeedMetaJson, NULL, N'Y', N'ACTIVE')
) AS src (
    DB_PRFL_NM,
    DBMS_TP_CD,
    HOST_NM,
    PORT_NO,
    DB_NM,
    CONNECTION_META_JSON,
    SCRT_REF_ID,
    READ_ONLY_YN,
    STAT_CD
)
ON tgt.DB_PRFL_NM = src.DB_PRFL_NM
WHEN MATCHED THEN
    UPDATE SET
        DBMS_TP_CD = src.DBMS_TP_CD,
        HOST_NM = src.HOST_NM,
        PORT_NO = src.PORT_NO,
        DB_NM = src.DB_NM,
        CONNECTION_META_JSON = src.CONNECTION_META_JSON,
        SCRT_REF_ID = src.SCRT_REF_ID,
        READ_ONLY_YN = src.READ_ONLY_YN,
        STAT_CD = src.STAT_CD,
        UPD_DTM = SYSUTCDATETIME()
WHEN NOT MATCHED THEN
    INSERT (
        DB_PRFL_NM,
        DBMS_TP_CD,
        HOST_NM,
        PORT_NO,
        DB_NM,
        CONNECTION_META_JSON,
        SCRT_REF_ID,
        READ_ONLY_YN,
        STAT_CD
    )
    VALUES (
        src.DB_PRFL_NM,
        src.DBMS_TP_CD,
        src.HOST_NM,
        src.PORT_NO,
        src.DB_NM,
        src.CONNECTION_META_JSON,
        src.SCRT_REF_ID,
        src.READ_ONLY_YN,
        src.STAT_CD
    );
GO

MERGE dbo.CORE_DB_PROFILE_ALLOWED_SCHEMAS AS tgt
USING (
    SELECT p.DB_PRFL_ID, v.SCHM_NM
    FROM dbo.CORE_DB_PROFILES AS p
    JOIN (VALUES (N'plf', N'dbo'), (N'master', N'dbo'), (N'ppm', N'dbo')) AS v (DB_PRFL_NM, SCHM_NM)
      ON v.DB_PRFL_NM = p.DB_PRFL_NM
) AS src (DB_PRFL_ID, SCHM_NM)
ON tgt.DB_PRFL_ID = src.DB_PRFL_ID
   AND tgt.SCHM_NM = src.SCHM_NM
WHEN NOT MATCHED THEN
    INSERT (DB_PRFL_ID, SCHM_NM)
    VALUES (src.DB_PRFL_ID, src.SCHM_NM);
GO
