## Role
template_engineer with `contract-to-code`, `eval-fixture-authoring`, and `quality-gate-review`.

## Task
P42C: implement deterministic validation for AI Draft Pack Java/XML files and
fixture-first quality evaluation. Keep `production_ready: false`.

## Scope
- Validate non-empty DTO, Service, Mapper interface, and Mapper XML content.
- Verify required ManageBond DTO files are separated and referenced by Service/Mapper/XML.
- Block `OperationModelReviewRequired`, single `ManageBondDTO` collapse, raw SP dumps, row-data wording, source apply/deploy claims, and missing `REVIEW_REQUIRED` markers.
- Add targeted unit/eval tests for validator behavior.

## Constraints
- Validator must not execute Java, SQL, mapper XML, stored procedures, or database access.
- Treat row data access and procedure execution as forbidden behavior.
- Do not infer metadata facts from generated code.
- Keep placeholder/sanitized SQL skeletons draft-only.

## Acceptance
- Valid fixture-like packs pass.
- Blank content, fallback skeletons, DTO collapse, missing DTO references, and forbidden payload markers fail.
- Cross-DB write, called procedure I/O, TVF/procedure uncertainty, and transaction boundary gaps remain `REVIEW_REQUIRED`.
