## Role
platform_worker with `contract-to-code` and `quality-gate-review`.

## Task
P42D: wire AI Draft Pack generation into the `JAVA_MYBATIS_DRAFT` workflow path and
artifact persistence. Keep `production_ready: false`.

## Scope
- Call the AI Draft Pack planner for Java/MyBatis draft generation before persisting artifacts.
- Persist each DTO file as a separate `DTO_DRAFT` artifact row.
- Persist exactly one `SERVICE_DRAFT`, one `MAPPER_INTERFACE`, and one `MAPPER_XML` artifact.
- Add artifact `extra` metadata: `aiDraftPackSchema`, `aiFileRole`, `operationIds`, `dtoRole`, and `qualityScore`.
- On pack failure, persist explicit review/failure status rather than misleading Java fallback skeletons.

## Constraints
- Do not modify existing completed jobs such as `job_6864d2734e`.
- No public API, UI, DB schema, or public MCP route expansion.
- No row data access, procedure execution, business DB DDL/DML, generated source apply, or deploy.

## Acceptance
- Unit tests prove `GenerationContext` or equivalent workflow input receives the validated AI Draft Pack.
- Artifact storage keeps DTO rows per file path and single rows for Service/Mapper/XML.
- Failure cases surface `P42_AI_DRAFT_PACK_FAILED` or `P42_AI_DRAFT_PACK_REVIEW_REQUIRED` without Java fallback artifacts.
