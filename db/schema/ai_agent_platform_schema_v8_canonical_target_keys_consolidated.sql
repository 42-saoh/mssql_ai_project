/*
  MSSQL Analysis Agent Platform
  Platform DB DDL Draft v8: Canonical Target Keys

  Manual apply only. Codex must not execute this file automatically.
  This consolidated draft carries forward the current v2/v3/v4/v6/v7 platform
  contract and adds server-derived canonical target keys to root requests, jobs,
  agent runs, draft artifacts, and knowledge assets.

  Canonical format:
    mssql:<dbProfileId>:<database|->:<objectType>:<schema>.<name>

  The schema continues to omit approval/review decision tables, publish/deploy
  controls, SQL execution, DDL/DML apply actions, row-data storage, raw prompts,
  raw provider traces, raw SP definitions, and secrets.
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

IF COL_LENGTH('dbo.CORE_WORK_REQUESTS', 'CANON_TRGT_KEY_TXT') IS NULL
BEGIN
    ALTER TABLE dbo.CORE_WORK_REQUESTS
        ADD CANON_TRGT_KEY_TXT NVARCHAR(300) NULL;
END;
GO

IF COL_LENGTH('dbo.CORE_JOBS', 'CANON_TRGT_KEY_TXT') IS NULL
BEGIN
    ALTER TABLE dbo.CORE_JOBS
        ADD CANON_TRGT_KEY_TXT NVARCHAR(300) NULL;
END;
GO

IF COL_LENGTH('dbo.AGENT_RUNS', 'CANON_TRGT_KEY_TXT') IS NULL
BEGIN
    ALTER TABLE dbo.AGENT_RUNS
        ADD CANON_TRGT_KEY_TXT NVARCHAR(300) NULL;
END;
GO

IF COL_LENGTH('dbo.ARTIFACTS', 'CANON_TRGT_KEY_TXT') IS NULL
BEGIN
    ALTER TABLE dbo.ARTIFACTS
        ADD CANON_TRGT_KEY_TXT NVARCHAR(300) NULL;
END;
GO

IF COL_LENGTH('dbo.KNOWLEDGE_ASSETS', 'CANON_TRGT_KEY_TXT') IS NULL
BEGIN
    ALTER TABLE dbo.KNOWLEDGE_ASSETS
        ADD CANON_TRGT_KEY_TXT NVARCHAR(300) NULL;
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = 'IX_CORE_WORK_REQUESTS_CANON_TARGET_SUBMITTED'
      AND object_id = OBJECT_ID('dbo.CORE_WORK_REQUESTS')
)
BEGIN
    CREATE INDEX IX_CORE_WORK_REQUESTS_CANON_TARGET_SUBMITTED
        ON dbo.CORE_WORK_REQUESTS(CANON_TRGT_KEY_TXT, SUBMITTED_DTM DESC)
        WHERE CANON_TRGT_KEY_TXT IS NOT NULL;
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = 'IX_CORE_JOBS_CANON_TARGET_CREATED'
      AND object_id = OBJECT_ID('dbo.CORE_JOBS')
)
BEGIN
    CREATE INDEX IX_CORE_JOBS_CANON_TARGET_CREATED
        ON dbo.CORE_JOBS(CANON_TRGT_KEY_TXT, CRE_DTM DESC)
        WHERE CANON_TRGT_KEY_TXT IS NOT NULL;
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = 'IX_AGENT_RUNS_JOB_CANON_TARGET'
      AND object_id = OBJECT_ID('dbo.AGENT_RUNS')
)
BEGIN
    CREATE INDEX IX_AGENT_RUNS_JOB_CANON_TARGET
        ON dbo.AGENT_RUNS(JOB_ID, CANON_TRGT_KEY_TXT, CRE_DTM DESC)
        WHERE CANON_TRGT_KEY_TXT IS NOT NULL;
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = 'IX_ARTIFACTS_JOB_CANON_TARGET'
      AND object_id = OBJECT_ID('dbo.ARTIFACTS')
)
BEGIN
    CREATE INDEX IX_ARTIFACTS_JOB_CANON_TARGET
        ON dbo.ARTIFACTS(JOB_ID, CANON_TRGT_KEY_TXT, CRE_DTM DESC)
        WHERE CANON_TRGT_KEY_TXT IS NOT NULL;
END;
GO

IF NOT EXISTS (
    SELECT 1
    FROM sys.indexes
    WHERE name = 'IX_KNOWLEDGE_ASSETS_CANON_TARGET'
      AND object_id = OBJECT_ID('dbo.KNOWLEDGE_ASSETS')
)
BEGIN
    CREATE INDEX IX_KNOWLEDGE_ASSETS_CANON_TARGET
        ON dbo.KNOWLEDGE_ASSETS(CANON_TRGT_KEY_TXT, UPD_DTM DESC)
        WHERE CANON_TRGT_KEY_TXT IS NOT NULL;
END;
GO
