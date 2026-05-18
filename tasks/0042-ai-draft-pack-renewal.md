# Task 0042: AI Draft Pack Renewal

## P42A Status

P42A is the groundwork slice for replacing the failed P41 operation-model-first
Java/MyBatis workflow with an AI Draft Pack path. The motivating live audit is
`job_6864d2734e`: its Java/MyBatis artifacts were not byte-empty, but all four
were `OperationModelReviewRequired*` fallback skeletons because the operation
planner failed with `SP_OPERATION_MODEL_PLANNER_FAILED:ModelGatewayError`.

P42 does not claim production readiness. It defines the contract, fixture,
quality blockers, and sequential prompt pack needed before implementation.

## P42C Status

P42C adds a deterministic, static-only Java/MyBatis draft pack validator. It
validates the `AiJavaMyBatisDraftPack.v0.1` schema first, then checks DTO class
separation, required field tokens, Service/Mapper/Mapper XML DTO references,
branch/use-case method tokens, Mapper XML statement ids, forbidden payload
markers, and required `REVIEW_REQUIRED` markers. It never executes Java, SQL,
Mapper XML, stored procedures, database access, source apply, or deploy actions.

## Goal

Create the P42 foundation for `PPM.dbo.PCO_GU_ManageBond_PRC` so the next slices
can generate a multi-file DTO pack plus single Service, Mapper interface, and
Mapper XML directly from sanitized analysis evidence.

## Context

- Related docs: `PROJECT.md`, `ARCHITECTURE.md`, `TOOLS.md`, `POLICY.md`, `EVAL_SPEC.md`
- Contract: `spec/eval/p42_ai_draft_pack_contract.yaml`
- Fixture: `fixtures/eval/ai_draft_pack_p42_manage_bond_v1.yaml`
- Previous approach: `SpOperationModel.v0.1` and P41 multi-DTO renderer
- Reference guide: `D:/migration/test_mcp_server_with_codex/MIGRATION_GUIDE.md`

## In Scope

- Define `AiJavaMyBatisDraftPack.v0.1` as an internal draft-pack contract.
- Keep public artifact types unchanged: `DTO_DRAFT`, `SERVICE_DRAFT`,
  `MAPPER_INTERFACE`, and `MAPPER_XML`.
- Record the required ManageBond DTO inventory and branch/use-case method wiring.
- Add P42A-F prompt pack and manifest wiring for sequential execution only.
- Add fixture-first tests that reject fallback skeletons, blank files, and single
  `ManageBondDTO` collapse.

## Out of Scope

- UI changes.
- Actual DB row data access, stored procedure execution, or business DB DDL/DML.
- Generated source apply, deploy, publish, or production readiness.
- OpenAI SDK dependency installation.
- Full workflow/generator implementation before P42B-D.

## Inputs

- Target object: `PPM.dbo.PCO_GU_ManageBond_PRC`
- Reference quality target: external `MIGRATION_GUIDE.md`
- Current artifact contract: P36 six final artifact types
- P41 failure audit: `job_6864d2734e`

## Constraints

- `production_ready: false`
- Raw SP definitions, raw guide body, raw prompts, raw provider responses, row
  data, and secrets must not be stored in repo fixtures or platform storage.
- Weak or inferred facts must remain `REVIEW_REQUIRED`.
- P42 execution is sequential: `P42A -> P42B -> P42C -> P42D -> P42E -> P42F`.

## Deliverables

- `p42_ai_draft_pack@0.1.0` eval contract.
- ManageBond AI Draft Pack quality fixture.
- P42 prompt pack and manifest tracks.
- Contract and eval tests for P42 groundwork.
- P42C deterministic validation report for fixture-like Java/MyBatis draft packs.
- Minimal docs sync describing the intended P42 path.

## Recommended Skills

- P42B schema/gateway: use `ai-draft-pack-authoring` with `contract-to-code`.
- P42C validator: use `java-mybatis-draft-validator` with `eval-fixture-authoring`.
- P42D workflow wiring: use `ai-draft-pack-authoring` and `quality-gate-review`.
- P42E replay gate: use `sp-business-logic-migration-eval` and `java-mybatis-draft-validator`.
- P42F docs/gate: use `docs-sync`, `quality-gate-review`, and `sp-business-logic-migration-eval`.

## Verification

- `make test PYTEST_ARGS="tests/contract/test_p42_ai_draft_pack_prompt_assets.py tests/eval/test_p42_manage_bond_ai_draft_quality.py"`
- `git diff --check`

## Done Definition

- The required ManageBond DTO file inventory is explicit and cannot collapse into
  one DTO.
- Service, Mapper interface, and Mapper XML remain single files but must reference
  branch/use-case DTOs.
- `OperationModelReviewRequired*`, `ManageBondDTO`, blank content, and fallback
  skeleton persistence are quality blockers.
- P42B can continue directly into schema, prompt renderer, and fake gateway tests.

## Notes / Risks

- P42A does not implement the AI Draft Pack runtime path.
- P-GPT/Responses structured output drift remains a P42B risk; the contract
  therefore recommends inventory, file content, validation, and repair stages.
- Cross-database writes, uncertain TVF/procedure kind, called procedure I/O, and
  transaction boundary uncertainty remain `REVIEW_REQUIRED`.
