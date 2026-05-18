## Role
template_engineer / platform_worker with `eval-fixture-authoring`, `sp-business-logic-migration-eval`, and `quality-gate-review`.

## Task
P43E: add a benchmark replay comparison proving framework adapters improve or at
least preserve P42 quality on complex SPs. Keep `production_ready: false`.

## Scope
- Use sanitized fixtures and fake adapters by default.
- Compare baseline internal gateway adapter vs candidate framework adapter on
  `PCO_GU_ManageBond_PRC` and at least one synthetic complex-SP collapse case.
- Verify the candidate does not rely on ManageBond-specific hardcoding.
- Reconstruct draft artifacts into `AiJavaMyBatisDraftPack.v0.1` and rerun the
  P42 static validator.

## Constraints
- Do not run the stored procedure, allow procedure execution, or query row data.
- Do not require live OpenAI or live PPM in default tests.
- Do not write generated source into application source trees.
- Do not weaken required `REVIEW_REQUIRED` markers.

## Acceptance
- Baseline and candidate results are compared with the same generic inventory contract.
- Candidate output has no `OperationModelReviewRequired*`, no blank content, no
  generic DTO collapse, and no raw trace leakage.
- ManageBond benchmark remains a quality target, not a production-runtime key.
- P36/P41/P42 regression tests still pass.
