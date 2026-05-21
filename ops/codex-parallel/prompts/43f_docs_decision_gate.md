## Role
docs_curator / reviewer with `docs-sync`, `quality-gate-review`, and `eval-fixture-authoring`.

## Task
P43F: synchronize docs and produce the framework adoption decision gate after
P43A-E are complete. Keep `production_ready: false`.

## Scope
- Update `PROJECT.md`, `ARCHITECTURE.md`, `POLICY.md`, `TOOLS.md`, `EVAL_SPEC.md`,
  generation docs, and eval docs.
- Report whether the recommendation is `adopt`, `pilot`, or `defer`.
- Include changed files, verification commands, quality comparison results,
  policy findings, rollback path, and residual `REVIEW_REQUIRED` items.

## Constraints
- No UI changes, DB schema changes, public API expansion, public MCP route expansion,
  public artifact type changes, or generated source apply/deploy.
- Treat row data access and procedure execution as forbidden behavior.
- Do not claim production readiness or automatic conversion approval.
- Keep raw SP definitions, raw guide body, raw prompts, raw provider responses,
  row data, and secrets out of docs, fixtures, traces, and artifacts.

## Acceptance
- Docs match implemented P43 behavior and do not overstate readiness.
- Quality gate reports baseline-vs-candidate evidence and residual risks.
- Framework adoption decision is evidence-backed and reversible.
- P43 leaves explicit `REVIEW_REQUIRED` markers for unsupported or weak facts.
