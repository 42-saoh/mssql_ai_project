## Role
template_engineer with `contract-to-code` and `eval-fixture-authoring`.

## Task
P41E: update Java/MyBatis generation so `DTO_DRAFT` can render a multi-file DTO bundle
from `SpOperationModel.v0.1`, while Service, Mapper, and Mapper XML may remain single files.
Keep `production_ready: false`.

## Scope
- Generate DTO classes from DTO blueprints instead of merging all SP inputs/results.
- Connect Service and Mapper methods to the correct command/query/result DTOs.
- Keep SQL as sanitized skeletons with evidence refs and `REVIEW_REQUIRED` comments.
- Add manage-bond golden tests that prove DTOs do not collapse into one `ManageBondDTO`.

## Constraints
- Do not write generated source into an application repository.
- Do not allow row data queries, procedure execution, DDL, DML, or deployment.
- Do not introduce new public artifact types; `DTO_DRAFT` remains the bundle artifact.

## Acceptance
- Manage-bond generation emits multiple DTO files inside `DTO_DRAFT`.
- Mapper XML uses branch-specific parameter/result types.
- Existing P36 artifact type expansion remains unchanged.
