## Role
architect / template_engineer with `contract-to-code`.

## Task
P42B: implement the `AiJavaMyBatisDraftPack.v0.1` schema, prompt renderer, and fake
gateway tests in `packages/agent-runtime`. Keep `production_ready: false`.

## Scope
- Add a strict internal schema for file inventory, file content, evidence refs, review markers, and quality gates.
- Prefer staged model output: file inventory, file content, deterministic validation, then repair.
- Use the existing Responses/httpx model gateway first; decide on OpenAI SDK only if the existing gateway cannot support the P42 contract.
- Add fake-gateway tests for valid packs and schema failures.

## Constraints
- No public API, DB schema, public artifact type, UI, or MCP public route changes.
- No row data, procedure execution, business DB DDL/DML, source apply, raw prompt storage, or raw provider response storage.
- LLM-inferred business facts must remain draft-only and review-marked when evidence is weak.

## Acceptance
- The schema can represent the ManageBond fixture inventory and content contract.
- Invalid artifact type, missing content, missing evidence refs, invalid role, and fallback class names fail deterministically.
- Weak or unsupported facts remain `REVIEW_REQUIRED` in the draft pack.
- The gateway path stores only sanitized structured output and trace hashes.
