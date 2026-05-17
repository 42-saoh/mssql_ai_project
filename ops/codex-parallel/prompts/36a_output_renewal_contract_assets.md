# P36A Output Renewal Contract Assets

## Role

template_engineer

## Context

Read `PROJECT.md`, `AGENTS.md`, `ARCHITECTURE.md`, `TOOLS.md`, `POLICY.md`, `EVAL_SPEC.md`, `TASK_TEMPLATE.md`, and `spec/eval/p36_output_renewal_contract.yaml` before editing.

## Task

Create and maintain the P36 output-renewal contract assets:

- `spec/eval/p36_output_renewal_contract.yaml`
- `tasks/0036-output-renewal.md`
- prompt pack entries `36a` through `36e`
- contract tests for the contract, task brief, prompt pack, and sequential manifest wiring

## Constraints

- Do not run phases in parallel.
- Do not change public API behavior in this step.
- Preserve `production_ready: false`.
- Do not store raw prompts, raw provider responses, secrets, full SP definitions, or row data.

## Acceptance

- P36A assets describe a sequential `P36A -> P36B -> P36C -> P36D -> P36E` flow.
- Removed artifact/requested-output names are explicit in the P36 contract.
- Contract test verifies prompt pack and manifest wiring.
