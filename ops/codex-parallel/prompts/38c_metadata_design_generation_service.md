# P38C Metadata Design Generation Service

## Role

template_engineer with mcp-tooling-design, contract-to-code, and eval-fixture-authoring.

## Task

Implement the metadata design chat generation service.

- Normalize user message, field names, descriptions, and table hints.
- Use bounded read-only MCP metadata tools: `search_columns`, `search_tables`, `find_similar_tables`, and `get_table_schema`.
- Use `platform_db_standardization_rules_for_ai.json` for standard names and types.
- Generate `createTableScriptPreview` and optional `DTO_DRAFT` preview.
- Keep uncertain naming, type, PK/FK, index, and description decisions as `REVIEW_REQUIRED`.

## Constraints

Do not create workflow artifacts or executable migration/apply controls.

## Acceptance

Fixture-first service tests prove metadata-backed candidates, standardization fallback, table preview, DTO_DRAFT preview, evidence refs, and redaction behavior with production_ready=false.
