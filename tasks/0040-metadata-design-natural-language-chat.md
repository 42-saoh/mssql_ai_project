# P40 Metadata Design Natural-Language Chat

## Summary

P40 turns `/metadata/design` from a field-row form into a natural-language chat
surface. Users describe a new table or a refinement in plain Korean or English,
and the platform extracts a sanitized intent, queries read-only metadata evidence,
and returns durable non-executable previews for `createTableScriptPreview` and
`DTO_DRAFT`.

## Scope

- Add `MetadataDesignOptions.conversationMode` with `NEW_DESIGN` and
  `REFINE_CURRENT`.
- Add sanitized `interpretedIntent` and `appliedChanges` to
  `MetadataDesignResult`.
- Keep `designInputs.fields` for public API compatibility only; remove field row
  inputs from the Web UI.
- In `REFINE_CURRENT`, use the latest `SUCCEEDED` run in the conversation as the
  baseline. If no baseline exists or the instruction is ambiguous, keep
  `REVIEW_REQUIRED`.
- Keep using P38 durable run storage. No v11 DDL is introduced.

## Guardrails

- No row data access.
- No stored procedure execution.
- No business DB DDL/DML.
- No automatic DDL apply, deployment, publish, or source writeback.
- No workflow artifact persistence for generated previews.
- No raw prompt, raw provider response, full SQL, or secret-like value storage.
- Do not revive `DDL_DRAFT`, `DTO_MODEL_DRAFT`, `VO_DRAFT`, or `MODEL_DRAFT`.

## Acceptance

- OpenAPI documents `conversationMode`, `interpretedIntent`, and
  `appliedChanges`.
- Korean natural-language input such as `고객명, 주소, 주문일이 있는 주문 요청 테이블`
  produces field candidates, metadata evidence calls, a table script preview, and
  a `DTO_DRAFT`.
- Follow-up input such as `배송메모 추가하고, 주문일은 날짜 타입으로 바꿔줘` applies add
  and type-change operations to the current conversation baseline.
- `/metadata/design` shows a chat transcript, metadata profile selector,
  conversation mode selector, natural-language message input, table name hint,
  result previews, and client-side `.sql`/`.java` downloads.
- The UI exposes no apply, execute, deploy, or publish controls.
- `production_ready` remains `false`.
