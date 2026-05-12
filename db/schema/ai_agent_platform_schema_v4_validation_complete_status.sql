/*
P25 manual DDL draft: allow validation-complete workflow status.

This file is review/manual-apply only. Repository tooling and Codex must not
execute it automatically against PLF or any business database.
*/

IF EXISTS (
    SELECT 1
    FROM sys.check_constraints
    WHERE name = 'CHK_CORE_WORK_REQUESTS_CURRENT_STATUS_CD'
      AND parent_object_id = OBJECT_ID('dbo.CORE_WORK_REQUESTS')
)
BEGIN
    ALTER TABLE dbo.CORE_WORK_REQUESTS
    DROP CONSTRAINT CHK_CORE_WORK_REQUESTS_CURRENT_STATUS_CD;
END;
GO

ALTER TABLE dbo.CORE_WORK_REQUESTS
ADD CONSTRAINT CHK_CORE_WORK_REQUESTS_CURRENT_STATUS_CD CHECK (
    CUR_STAT_CD IN (
        'SUBMITTED',
        'COLLECTING_METADATA',
        'ANALYZING',
        'GENERATING',
        'VALIDATING',
        'VALIDATION_COMPLETE',
        'REVIEW_PENDING',
        'APPROVED',
        'REJECTED',
        'PUBLISHED',
        'FAILED',
        'CANCELED'
    )
);
GO

IF EXISTS (
    SELECT 1
    FROM sys.check_constraints
    WHERE name = 'CHK_CORE_JOBS_CURRENT_STATUS_CD'
      AND parent_object_id = OBJECT_ID('dbo.CORE_JOBS')
)
BEGIN
    ALTER TABLE dbo.CORE_JOBS
    DROP CONSTRAINT CHK_CORE_JOBS_CURRENT_STATUS_CD;
END;
GO

ALTER TABLE dbo.CORE_JOBS
ADD CONSTRAINT CHK_CORE_JOBS_CURRENT_STATUS_CD CHECK (
    CUR_STAT_CD IN (
        'SUBMITTED',
        'COLLECTING_METADATA',
        'ANALYZING',
        'GENERATING',
        'VALIDATING',
        'VALIDATION_COMPLETE',
        'REVIEW_PENDING',
        'APPROVED',
        'REJECTED',
        'PUBLISHED',
        'FAILED',
        'CANCELED'
    )
);
GO
