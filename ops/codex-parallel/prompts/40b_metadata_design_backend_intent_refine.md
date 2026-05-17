## Role

platform_worker with contract-to-code and quality-gate-review.

## Task

Extend `MetadataDesignChatService` with a sanitized intent extraction stage and
multi-turn `REFINE_CURRENT` baseline handling. Deterministic Korean/English
fallback must support field extraction, add/remove/type-change instructions, and
review markers for ambiguous requests.

## Constraints

- Use only existing read-only metadata evidence flow.
- Do not store raw prompt/provider response or secret-like values.
- Do not execute DDL/DML or procedures.
- Keep generated previews inside metadata design run JSON only.

## Acceptance

- `NEW_DESIGN` natural-language messages produce field candidates.
- `REFINE_CURRENT` uses the latest `SUCCEEDED` run in the conversation.
- Missing baseline and ambiguous refinement return `REVIEW_REQUIRED`.
- Unit and integration tests pass.
