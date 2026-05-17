## Role
template_engineer with `contract-to-code` and `eval-fixture-authoring`.

## Task
P41A: establish the SP operation model renewal groundwork for `PCO_GU_ManageBond_PRC`.
Create or maintain `SpOperationModel.v0.1`, the P41 eval contract, sanitized fixture,
contract/eval tests, and task brief. Keep `production_ready: false`.

## Scope
- Model `CRUDFlag` branches `R/A/C/U/D/VENDOR_U/ONLINE_U`.
- Capture statement evidence, branch condition, DTO blueprint, and `REVIEW_REQUIRED` markers.
- Make the current single `DTO_DRAFT` collapse visible without changing the production generator.
- Use `D:/migration/test_mcp_server_with_codex/MIGRATION_GUIDE.md` only as a quality reference.

## Constraints
- Do not store raw SP definition, raw prompt, raw provider response, row data, secrets, or executable SQL.
- Do not allow procedure execution, row data queries, DDL/DML apply, deploy, or generated-source writes.
- Do not add OpenAI SDK dependencies in P41A.
- Keep public artifact types unchanged: `DTO_DRAFT`, `SERVICE_DRAFT`, `MAPPER_INTERFACE`, `MAPPER_XML`.

## Acceptance
- `SpOperationModel.v0.1` validates the manage-bond fixture.
- The fixture has at least 9 DTO blueprints and all required CRUD flags.
- Cross-DB write, called procedure I/O, and uncertain TVF/procedure kind remain `REVIEW_REQUIRED`.
- Targeted P41 tests pass through the Git Bash `make test` path.
