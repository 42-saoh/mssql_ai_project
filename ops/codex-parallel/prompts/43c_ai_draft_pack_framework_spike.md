## Role
template_engineer / platform_worker with `contract-to-code`, `ai-draft-pack-authoring`, and `java-mybatis-draft-validator`.

## Task
P43C: route P42 AI Draft Pack planning through the framework adapter spike while
keeping the current workflow behavior available as a rollback path. Keep
`production_ready: false`.

## Scope
- Connect staged `file_inventory`, `file_content`, and `repair` calls to the
  adapter contract from P43B.
- Reuse `AiJavaMyBatisDraftPack.v0.1`, deterministic inventory contract, and P42C
  static validator.
- Add A/B tests comparing baseline adapter and candidate adapter output on
  sanitized complex-SP fixtures.
- Preserve explicit failure markers instead of fallback Java skeletons.

## Constraints
- Do not hardcode ManageBond DTO inventory in production workflow.
- Do not execute generated Java, SQL, Mapper XML, stored procedures, allow
  procedure execution, or perform database access.
- Do not infer metadata facts from generated code.
- Do not persist raw prompts, raw provider responses, raw SP definitions, raw guide
  body, row data, secrets, or failed Java/XML payloads.
- Weak or unsupported framework-inferred facts must remain `REVIEW_REQUIRED`.

## Acceptance
- Adapter-routed planning can produce a valid draft pack for fixture-like complex SPs.
- Two-DTO collapse and missing operation coverage fail generically.
- Candidate adapter output is validated by the same P42 schema and quality gate as
  the baseline.
- Failure diagnostics are sanitized and stage-specific.
