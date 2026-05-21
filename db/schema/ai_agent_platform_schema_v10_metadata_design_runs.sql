/*
  MSSQL Analysis Agent Platform
  Platform DB DDL Draft v10: Durable Metadata Design Runs

  Manual apply only. Codex must not execute this file automatically.
  This schema stores sanitized metadata design chat request/result state for
  public submit/polling APIs. It does not store row data, raw SQL text, raw SP
  definitions, procedure execution output, secrets, raw prompts, raw provider
  responses, publish/deploy/apply controls, approval decisions, reviewer
  identities, or human review records.

  Table script output stored in RESULT_JSON is a non-executable preview string
  for manual schema review. It is not workflow artifact storage, is not an
  artifact record, and does not revive retired DDL_DRAFT artifact contracts.
*/

SET ANSI_NULLS ON;
SET QUOTED_IDENTIFIER ON;
GO

CREATE TABLE dbo.METADATA_DESIGN_RUNS (
    RUN_ID NVARCHAR(80) NOT NULL,
    CONVERSATION_ID NVARCHAR(80) NOT NULL,
    STAT_CD NVARCHAR(30) NOT NULL,
    REQUEST_JSON NVARCHAR(MAX) NOT NULL,
    RESULT_JSON NVARCHAR(MAX) NULL,
    ERR_JSON NVARCHAR(MAX) NULL,
    SUBMITTED_DTM DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
    START_DTM DATETIME2(3) NULL,
    COMPLETED_DTM DATETIME2(3) NULL,
    UPD_DTM DATETIME2(3) NOT NULL DEFAULT SYSUTCDATETIME(),
    CONSTRAINT PK_METADATA_DESIGN_RUNS PRIMARY KEY CLUSTERED (RUN_ID),
    CONSTRAINT CHK_METADATA_DESIGN_RUNS_STATUS CHECK (
        STAT_CD IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED')
    ),
    CONSTRAINT CHK_METADATA_DESIGN_RUNS_REQUEST_JSON CHECK (ISJSON(REQUEST_JSON) = 1),
    CONSTRAINT CHK_METADATA_DESIGN_RUNS_RESULT_JSON CHECK (
        RESULT_JSON IS NULL OR ISJSON(RESULT_JSON) = 1
    ),
    CONSTRAINT CHK_METADATA_DESIGN_RUNS_ERR_JSON CHECK (
        ERR_JSON IS NULL OR ISJSON(ERR_JSON) = 1
    )
);
GO

CREATE INDEX IX_METADATA_DESIGN_RUNS_STATUS
    ON dbo.METADATA_DESIGN_RUNS(STAT_CD, UPD_DTM DESC);
GO

CREATE INDEX IX_METADATA_DESIGN_RUNS_CONVERSATION
    ON dbo.METADATA_DESIGN_RUNS(CONVERSATION_ID, SUBMITTED_DTM DESC);
GO

CREATE INDEX IX_METADATA_DESIGN_RUNS_SUBMITTED
    ON dbo.METADATA_DESIGN_RUNS(SUBMITTED_DTM DESC);
GO
