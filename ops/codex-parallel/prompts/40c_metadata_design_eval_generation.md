## Role

template_engineer with mcp-tooling-design, contract-to-code, and
eval-fixture-authoring.

## Task

Add fixture-first P40 evals for natural-language metadata design. Cover Korean
new design, follow-up refinement, and no-metadata fallback with standard policy
and `REVIEW_REQUIRED`.

## Constraints

- Metadata facts must come from read-only MCP-style fixture responses.
- Table output is `createTableScriptPreview`, not `DDL_DRAFT`.
- DTO output is a preview `DTO_DRAFT`, not a workflow artifact.
- No row data, full definitions, or secrets in expected payloads.

## Acceptance

- P40 eval contract and fixture align.
- Eval confirms metadata evidence, standardization mappings, table preview, DTO
  preview, interpreted intent, and applied changes.
- Forbidden fragments are absent from serialized results.
