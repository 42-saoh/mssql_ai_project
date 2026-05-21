## Role
platform_worker / template_engineer with `contract-to-code`, `eval-fixture-authoring`, and `quality-gate-review`.

## Task
P42E: add a ManageBond replay gate proving new jobs can produce non-empty multi-DTO
AI Draft Pack artifacts. Keep `production_ready: false`.

## Scope
- Use the sanitized ManageBond fixture and local workflow tests to verify the P42 path.
- Treat `job_6864d2734e` as preserved audit history, not an acceptance result.
- Assert the new job output includes required `ManageBond*` `DTO_DRAFT` artifacts and single Service/Mapper/XML artifacts.
- Assert Service/Mapper/XML method wiring references branch/use-case DTOs.

## Constraints
- Do not run the stored procedure or query row data.
- Treat row data access and procedure execution as forbidden behavior.
- Do not write generated source into application source trees.
- Do not require live OpenAI or live PPM for default tests; use fake gateway fixtures.

## Acceptance
- Integration tests prove no `OperationModelReviewRequired*`, no `ManageBondDTO`, no blank content, and no DTO collapse.
- New replay output satisfies the P42 ManageBond quality fixture.
- Cross-DB write, called procedure I/O, and TVF/procedure uncertainty remain `REVIEW_REQUIRED`.
- Existing P36/P41 regression tests still pass.
