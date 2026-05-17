# packages/generation

P36 status: output generation now targets six final artifact types:

- `SP_ANALYSIS_DOC`
- `DEPENDENCY_REPORT`
- `DTO_DRAFT`
- `SERVICE_DRAFT`
- `MAPPER_INTERFACE`
- `MAPPER_XML`

`SP_ANALYSIS_DOC` renders a migration-guide flow compatible with `MIGRATION_GUIDE.md`:
overview, dependency inventory, DML impact matrix, call flow, complexity analysis, and appendix.

`DEPENDENCY_REPORT` is an evidence dossier. It records SP analysis evidence, Java/MyBatis
generation evidence, bounded sanitized SQL statement evidence, caveats, and next evidence to
collect.

`JAVA_MYBATIS_DRAFT` expands only to DTO, service, mapper interface, and mapper XML. The
renderer accepts `spWrapper`, `spRebuild`, and `evidenceReconstructed`; production workflow uses
the evidence reconstruction path. Generated code is draft-only, includes `REVIEW_REQUIRED`
markers, and must not be auto-applied or deployed.

Retired outputs are no longer public generation targets:

- `DTO_MODEL_DRAFT`
- `VO_DRAFT`
- `MODEL_DRAFT`
- `DDL_DRAFT`

All generation remains evidence-bound and validation-first. The package must not store full SP
definitions, raw model responses, secrets, or row data.
