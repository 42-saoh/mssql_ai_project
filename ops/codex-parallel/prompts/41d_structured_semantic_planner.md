## Role
platform_worker / template_engineer with `contract-to-code`.

## Task
P41D: implement the structured semantic planner that consumes deterministic statement
evidence and returns operation contracts plus DTO blueprints. Keep `production_ready: false`.

## Scope
- Use the existing Responses/httpx gateway first; do not migrate to OpenAI SDK in this slice.
- Add strict structured-output tests with fake gateway fixtures.
- Ensure the planner names DTOs by business operation rather than merging all params/results.
- Record low-evidence business naming as `REVIEW_REQUIRED`.

## Constraints
- No row data, procedure execution, business DB DDL/DML, generated source apply, raw prompt storage, or raw provider response storage.
- LLM inference is not metadata evidence.
- Unsupported dependencies and uncertain called procedure contracts remain `REVIEW_REQUIRED`.

## Acceptance
- The planner produces a valid `SpOperationModel.v0.1` payload for the manage-bond fixture.
- Invalid evidence refs are repaired or rejected deterministically.
- The output keeps separate query/result/command/batch DTO blueprints.
