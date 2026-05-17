# P38A Metadata Design Contract Assets

## Role

architect with contract-to-code and eval-fixture-authoring.

## Task

Read `PROJECT.md`, `AGENTS.md`, `ARCHITECTURE.md`, `POLICY.md`, `EVAL_SPEC.md`, and `TASK_TEMPLATE.md`.

Implement the contract slice for P38 metadata design chat:

- Add `tasks/0038-metadata-design-chat.md`.
- Add `spec/eval/p38_metadata_design_chat_contract.yaml`.
- Add OpenAPI schemas and paths for metadata design run submit, poll, and conversation read.
- Add v10 manual SQL for `dbo.METADATA_DESIGN_RUNS`.

## Constraints

Manual DDL only, no row data, no procedure execution, no automatic apply, no workflow artifact persistence, and no retired artifact type revival.

## Acceptance

Contract assets, task brief, OpenAPI surface, v10 manual SQL, and sequential manifest wiring are present with production_ready=false.
