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

P41 adds an operation-model generation path without changing public artifact types. When a
request includes `operationModel` (`SpOperationModel.v0.1`), `JavaMyBatisSpWrapperRenderer`
renders one `DTO_DRAFT` file per DTO blueprint and still emits exactly one `SERVICE_DRAFT`,
one `MAPPER_INTERFACE`, and one `MAPPER_XML`. When no `operationModel` is supplied, the
legacy single DTO draft behavior remains for backward compatibility and is treated as a
known gap for complex stored procedures.

The API workflow now supplies `operationModel` for `JAVA_MYBATIS_DRAFT` by running the
sanitized statement-evidence extractor and structured operation planner before rendering.
Persisted Java/MyBatis bundles store each DTO file as its own `DTO_DRAFT` artifact keyed by
`bundleFilePath`; the service, mapper interface, and mapper XML artifacts remain singletons.
If the planner cannot produce a branch-level model, the workflow emits
`OperationModelReviewRequired` with `P41_OPERATION_MODEL_REVIEW_REQUIRED` instead of treating
the legacy single DTO as adequate.

P42 adds the AI Draft Pack workflow path for complex SP Java/MyBatis drafts. For
`JAVA_MYBATIS_DRAFT`, the API workflow can call the `AiJavaMyBatisDraftPack.v0.1` planner,
validate the returned Java/XML content with the static P42 quality gate, and persist only
validated files: one `DTO_DRAFT` artifact per DTO path and one artifact each for Service, Mapper
interface, and Mapper XML. Pack artifacts remain draft-only; `OperationModelReviewRequired*`,
single-DTO collapse for complex SPs, blank content, and source apply/deploy claims are blockers.
Target-specific names such as `ManageBondDTO` are enforced by eval fixtures, while workflow
inventory is derived from sanitized operation contracts and DTO blueprints.

Retired outputs are no longer public generation targets:

- `DTO_MODEL_DRAFT`
- `VO_DRAFT`
- `MODEL_DRAFT`
- `DDL_DRAFT`

All generation remains evidence-bound and validation-first. The package must not store full SP
definitions, raw model responses, secrets, or row data.
