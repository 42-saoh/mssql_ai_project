## Role
architect / template_engineer with `contract-to-code`.

## Task
P41B: turn the P41A groundwork into a code-generation planning schema. Define the
strict structured schema and prompt contract that maps statement evidence to operation
contracts and DTO blueprints. Keep `production_ready: false`.

## Scope
- Extend the operation planner schema from `SpOperationModel.v0.1` without changing public API.
- Preserve `DTO_DRAFT` as the public artifact type while allowing a multi-file internal bundle.
- Define how LLM output may name operations and DTOs from deterministic evidence.
- Add fake-gateway tests for schema validation and invalid-output repair boundaries.

## Constraints
- No row data, procedure execution, business DB DDL/DML, source apply, raw prompt storage, or raw provider response storage.
- LLM output may not confirm table/procedure/function facts without deterministic evidence.
- Unsupported or ambiguous facts must remain `REVIEW_REQUIRED`.

## Acceptance
- The P41B schema can represent the P41A manage-bond fixture without single DTO collapse.
- Invalid DTO blueprint roles or missing evidence refs fail deterministically.
- Existing P36 public artifact contract remains unchanged.
