## Role
template_engineer with `contract-to-code`, `eval-fixture-authoring`, and `docs-sync`.

## Task
P42A: establish the AI Draft Pack renewal groundwork for `PCO_GU_ManageBond_PRC`.
Create or maintain the P42 contract, sanitized ManageBond fixture, prompt pack,
task brief, manifest wiring, and static tests. Keep `production_ready: false`.

## Scope
- Audit `job_6864d2734e` as a fallback-skeleton failure, not a valid ManageBond draft.
- Define `AiJavaMyBatisDraftPack.v0.1` and required file inventory.
- Require multiple DTO files while keeping Service, Mapper interface, and Mapper XML single files.
- Use `D:/migration/test_mcp_server_with_codex/MIGRATION_GUIDE.md` only as a quality reference.

## Constraints
- Do not store raw SP definition, raw guide body, raw prompt, raw provider response, row data, or secrets.
- Do not allow procedure execution, row data queries, DDL/DML apply, deploy, or generated-source writes.
- Do not add OpenAI SDK dependencies in P42A.
- Keep public artifact types unchanged: `DTO_DRAFT`, `SERVICE_DRAFT`, `MAPPER_INTERFACE`, `MAPPER_XML`.

## Acceptance
- P42 contract and fixture reject `OperationModelReviewRequired*`, `ManageBondDTO`, blank content, and DTO collapse.
- Required ManageBond DTOs and branch/use-case methods are represented.
- Cross-DB write, called procedure I/O, and TVF/procedure uncertainty stay `REVIEW_REQUIRED`.
- P42A-F prompts are wired sequentially in the manifest.
- Targeted P42A tests pass through the Git Bash `make test` path.
