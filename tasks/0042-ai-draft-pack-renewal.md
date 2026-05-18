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

## P42D Status

P42D wires the AI Draft Pack path into `JAVA_MYBATIS_DRAFT` workflow generation.
The workflow plans an `LLM_AI_DRAFT_PACK_PLANNER` run from sanitized context,
applies the P42C static quality gate, and persists only validated pack files.
Each DTO file is stored as a separate `DTO_DRAFT` artifact row keyed by
`bundleFilePath`; Service, Mapper interface, and Mapper XML remain one row each.

Pack failures are terminal draft failures, not successful skeleton output:
`P42_AI_DRAFT_PACK_FAILED` or `P42_AI_DRAFT_PACK_REVIEW_REQUIRED` is recorded on
the agent run/job, and no `OperationModelReviewRequired*` Java/MyBatis artifacts
are persisted.

## P42E Status

P42E adds a local API workflow replay gate for `PCO_GU_ManageBond_PRC`. The gate
uses sanitized ManageBond fixtures, a fake metadata gateway, and a fake model
gateway to submit a new `JAVA_MYBATIS_DRAFT` job through `/api/v1/requests/sp-analysis`.
The historical `job_6864d2734e` remains audit evidence only and is not an
acceptance result.

The replay must produce non-empty multi-DTO AI Draft Pack artifacts: eleven
`DTO_DRAFT` rows and exactly one `SERVICE_DRAFT`, `MAPPER_INTERFACE`, and
`MAPPER_XML` row. Persisted artifacts are reconstructed into an
`AiJavaMyBatisDraftPack.v0.1` payload and revalidated by the P42C static quality
gate. Cross-database write, called procedure I/O, uncertain TVF/procedure kind,
and transaction boundary uncertainty remain `REVIEW_REQUIRED`.

## P42F Status

P42F closes the AI Draft Pack renewal slice with docs synchronization and a final
quality gate. The synchronized docs describe the implemented P42 behavior:
draft-only AI Draft Pack planning, deterministic Java/XML validation, workflow
artifact persistence, explicit failure markers, local ManageBond route replay,
and the remaining `REVIEW_REQUIRED` uncertainty items.

P42F does not add UI, public API fields, DB schema, public MCP routes, public
artifact types, source apply/deploy behavior, row-data access, procedure
execution, live OpenAI requirements, or live PPM requirements. The final gate is
P42 targeted tests plus P41 targeted tests, P36 generation regression, targeted
Ruff for changed Python files when applicable, and `git diff --check`.

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
- P42D workflow wiring from `JAVA_MYBATIS_DRAFT` to validated AI Draft Pack
  artifact persistence.
- P42E route-level ManageBond replay gate proving new jobs persist non-empty
  multi-DTO AI Draft Pack artifacts and satisfy the fixture quality contract.
- P42F docs sync and final quality-gate report describing changed files,
  verification, and residual risks.

## Recommended Skills

- P42B schema/gateway: use `ai-draft-pack-authoring` with `contract-to-code`.
- P42C validator: use `java-mybatis-draft-validator` with `eval-fixture-authoring`.
- P42D workflow wiring: use `ai-draft-pack-authoring` and `quality-gate-review`.
- P42E replay gate: use `sp-business-logic-migration-eval` and `java-mybatis-draft-validator`.
- P42F docs/gate: use `docs-sync`, `quality-gate-review`, and `sp-business-logic-migration-eval`.

## Verification

- `make test PYTEST_ARGS="tests/contract/test_p42_ai_draft_pack_prompt_assets.py tests/eval/test_p42_manage_bond_ai_draft_quality.py"`
- `make test PYTEST_ARGS="tests/unit/api/test_workflow_service.py tests/unit/agent_runtime/test_ai_draft_pack_planner.py tests/unit/agent_runtime/test_ai_draft_pack_schema.py tests/unit/validation/test_ai_draft_pack_validator.py"`
- `make test PYTEST_ARGS="tests/integration/api/test_api_workflow_routes.py tests/unit/api/test_workflow_service.py tests/eval/test_p42_manage_bond_ai_draft_quality.py tests/unit/validation/test_ai_draft_pack_validator.py tests/eval/test_p36_output_renewal_quality.py tests/eval/test_p41_sp_operation_model.py"`
- `make test PYTEST_ARGS="tests/contract/test_p42_ai_draft_pack_prompt_assets.py tests/eval/test_p42_manage_bond_ai_draft_quality.py tests/unit/agent_runtime/test_ai_draft_pack_schema.py tests/unit/agent_runtime/test_ai_draft_pack_planner.py tests/unit/validation/test_ai_draft_pack_validator.py tests/unit/api/test_workflow_service.py tests/integration/api/test_api_workflow_routes.py tests/contract/test_p41_sp_operation_model_prompt_assets.py tests/eval/test_p41_sp_operation_model.py tests/unit/agent_runtime/test_sp_operation_model_schema.py tests/unit/agent_runtime/test_sp_operation_planner.py tests/unit/analysis/test_sp_statement_evidence_extractor.py tests/unit/generation tests/eval/test_p36_output_renewal_quality.py"`
- `git diff --check`

## Done Definition

- The required ManageBond DTO file inventory is explicit and cannot collapse into
  one DTO.
- Service, Mapper interface, and Mapper XML remain single files but must reference
  branch/use-case DTOs.
- `OperationModelReviewRequired*`, `ManageBondDTO`, blank content, and fallback
  skeleton persistence are quality blockers.
- P42D stores AI Draft Pack metadata in artifact `extra`: `aiDraftPackSchema`,
  `aiDraftPackTargetRef`, `aiDraftPackAgentRunId`, `aiFileRole`,
  `operationIds`, `dtoRole`, `qualityScore`, `bundleFilePath`,
  `aiEvidenceRefs`, and `reviewMarkers`.
- P42E replay proves a new API workflow job produces required ManageBond DTOs,
  single Service/Mapper/Mapper XML files, no fallback skeletons, no blank
  content, no `ManageBondDTO` collapse, and preserved `REVIEW_REQUIRED` markers.
- P42F docs match implemented behavior and the final gate reports no policy
  drift, no missing regression coverage, and no whitespace issues.

## Notes / Risks

- P-GPT/Responses structured output drift remains a P42B risk; the contract
  therefore recommends inventory, file content, validation, and repair stages.
- Cross-database writes, uncertain TVF/procedure kind, called procedure I/O, and
  transaction boundary uncertainty remain `REVIEW_REQUIRED`.
