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

P43 does not change generation artifact types or generated source locations. It routes the AI
Draft Pack planner through an optional internal adapter spike in tests, compares baseline and fake
candidate framework adapters, and keeps the P42 static validator as the authority before any draft
artifact is persisted. P43F records a `pilot` decision only; the existing Responses/httpx path
remains rollback and no framework dependency or runtime switch is introduced.

P44 changes the internal AI Draft Pack runtime but still does not change generation artifact types
or generated source locations. OpenAI remote generation now uses OpenAI Agents SDK behind the
adapter contract, and LangGraph orchestrates `file_inventory`, `file_content`, `quality_gate`,
`repair`, and `final` in process with no persistent checkpointer. Generated Java/MyBatis artifacts
remain draft-only with `productionReady=false`; source apply, deploy, procedure execution, row data
access, raw prompt/provider response storage, and raw SP/guide storage remain forbidden.

P45/P46 do not change this package boundary. P45 live evidence is optional and sanitized, and P46
keeps `responses_httpx` only for P-GPT compatibility plus emergency rollback while OpenAI defaults
to OpenAI Agents SDK plus LangGraph.

P47 improves AI Draft Pack quality through generic evidence, not benchmark hardcoding. The planner
now renders `DraftPackEvidenceBundle.v0.1`, operation coverage, DTO responsibility, review marker,
and mapper coverage matrices into `prompt:ai_java_mybatis_draft_pack@0.2.0`. ManageBond DTO and
method names remain benchmark comparison signals only; generic generation quality is judged by
operation coverage, DTO separation, mapper wiring, schema validation, and required
`REVIEW_REQUIRED` markers.

Retired outputs are no longer public generation targets:

- `DTO_MODEL_DRAFT`
- `VO_DRAFT`
- `MODEL_DRAFT`
- `DDL_DRAFT`

All generation remains evidence-bound and validation-first. The package must not store full SP
definitions, raw model responses, secrets, or row data.
