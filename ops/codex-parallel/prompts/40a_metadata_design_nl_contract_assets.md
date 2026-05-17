## Role

architect with contract-to-code and eval-fixture-authoring.

## Task

Add P40 contract assets for metadata design natural-language chat. Update the
OpenAPI contract so `conversationMode`, `interpretedIntent`, and
`appliedChanges` are public, versioned, and bounded to sanitized structured
output.

## Constraints

- Reuse P38 v10 durable run storage; do not add DDL.
- Keep `production_ready: false`.
- Do not revive `DDL_DRAFT`, `DTO_MODEL_DRAFT`, `VO_DRAFT`, or `MODEL_DRAFT`.
- No row data, raw prompt, raw provider response, full SQL, apply, execute,
  deploy, publish, or workflow artifact persistence.

## Acceptance

- `tasks/0040-metadata-design-natural-language-chat.md` exists.
- `spec/eval/p40_metadata_design_natural_language_chat_contract.yaml` exists.
- `REQUEST_MANIFEST.yaml` wires P40A -> P40B -> P40C -> P40D -> P40E after P38E.
- Contract tests pass for P40 prompt assets and OpenAPI.
