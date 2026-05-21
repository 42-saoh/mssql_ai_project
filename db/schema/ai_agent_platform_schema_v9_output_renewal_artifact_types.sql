/*
P36 manual-apply artifact type storage renewal.

Why this script keeps retired values in the DB CHECK:
- P36 removes DTO_MODEL_DRAFT / VO_DRAFT / MODEL_DRAFT / DDL_DRAFT from new public
  request/API/UI/validation/generation contracts.
- Existing platform DBs can still contain historical ARTIFACTS rows with VO_DRAFT,
  MODEL_DRAFT, or DDL_DRAFT.
- Deleting those rows is unsafe because ARTIFACT_VERSIONS, validation reports, approval
  records, knowledge links, exports, and audit/history surfaces can reference them.

Therefore v9 is intentionally non-destructive:
- the storage CHECK allows historical retired artifact types;
- a trigger blocks new inserts or type changes into retired artifact types;
- optional archive UPDATE is left commented for operator review.

Manual apply only. Codex/API must not auto-run this script.
*/

SET XACT_ABORT ON;
BEGIN TRANSACTION;

SELECT
    ARTF_TP_CD,
    CUR_STAT_CD,
    COUNT_BIG(*) AS artifact_count
FROM dbo.ARTIFACTS
WHERE ARTF_TP_CD IN ('VO_DRAFT', 'MODEL_DRAFT', 'DDL_DRAFT')
GROUP BY ARTF_TP_CD, CUR_STAT_CD
ORDER BY ARTF_TP_CD, CUR_STAT_CD;

SELECT
    a.ARTF_ID,
    a.ARTF_TP_CD,
    a.CUR_STAT_CD,
    COUNT(DISTINCT av.ARTF_VER_ID) AS artifact_version_count,
    COUNT(DISTINCT vr.VLDT_RSLT_ID) AS validation_report_count,
    COUNT(DISTINCT ar.APRV_ID) AS approval_record_count
FROM dbo.ARTIFACTS AS a
LEFT JOIN dbo.ARTIFACT_VERSIONS AS av
  ON av.ARTF_ID = a.ARTF_ID
LEFT JOIN dbo.ARTIFACT_VALIDATION_REPORTS AS vr
  ON vr.ARTF_VER_ID = av.ARTF_VER_ID
LEFT JOIN dbo.ARTIFACT_APPROVAL_RECORDS AS ar
  ON ar.ARTF_VER_ID = av.ARTF_VER_ID
WHERE a.ARTF_TP_CD IN ('VO_DRAFT', 'MODEL_DRAFT', 'DDL_DRAFT')
GROUP BY a.ARTF_ID, a.ARTF_TP_CD, a.CUR_STAT_CD
ORDER BY a.ARTF_TP_CD, a.ARTF_ID;

/*
Optional operator action after review:

UPDATE dbo.ARTIFACTS
SET CUR_STAT_CD = 'ARCHIVED'
WHERE ARTF_TP_CD IN ('VO_DRAFT', 'MODEL_DRAFT', 'DDL_DRAFT')
  AND CUR_STAT_CD <> 'ARCHIVED';
*/

IF OBJECT_ID('dbo.TRG_ARTIFACTS_BLOCK_P36_RETIRED_TYPES', 'TR') IS NOT NULL
BEGIN
    DROP TRIGGER dbo.TRG_ARTIFACTS_BLOCK_P36_RETIRED_TYPES;
END;

IF EXISTS (
    SELECT 1
    FROM sys.check_constraints
    WHERE name = 'CHK_ARTIFACTS_TYPE_CD'
      AND parent_object_id = OBJECT_ID('dbo.ARTIFACTS')
)
BEGIN
    ALTER TABLE dbo.ARTIFACTS
    DROP CONSTRAINT CHK_ARTIFACTS_TYPE_CD;
END;

ALTER TABLE dbo.ARTIFACTS
ADD CONSTRAINT CHK_ARTIFACTS_TYPE_CD CHECK (
    ARTF_TP_CD IN (
        'SP_ANALYSIS_DOC',
        'DEPENDENCY_REPORT',
        'METADATA_QUERY_RESULT',
        'SCHEMA_ENRICHMENT_RESULT',
        'MAPPER_XML',
        'MAPPER_INTERFACE',
        'SERVICE_DRAFT',
        'DTO_DRAFT',
        'VALIDATION_REPORT',
        'APPROVAL_LOG',
        -- Historical-only values retained so FK-linked legacy artifacts survive v9.
        'VO_DRAFT',
        'MODEL_DRAFT',
        'DDL_DRAFT'
    )
);

COMMIT TRANSACTION;
GO

CREATE TRIGGER dbo.TRG_ARTIFACTS_BLOCK_P36_RETIRED_TYPES
ON dbo.ARTIFACTS
AFTER INSERT, UPDATE
AS
BEGIN
    SET NOCOUNT ON;

    IF EXISTS (
        SELECT 1
        FROM inserted AS i
        LEFT JOIN deleted AS d
          ON d.ARTF_ID = i.ARTF_ID
        WHERE i.ARTF_TP_CD IN ('VO_DRAFT', 'MODEL_DRAFT', 'DDL_DRAFT')
          AND (
              d.ARTF_ID IS NULL
              OR ISNULL(d.ARTF_TP_CD, '') <> i.ARTF_TP_CD
          )
    )
    BEGIN
        THROW 51036,
            'P36 retired artifact types are historical-only. New VO_DRAFT, MODEL_DRAFT, or DDL_DRAFT artifacts are blocked.',
            1;
    END;
END;
GO
