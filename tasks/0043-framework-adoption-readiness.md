# Task 0043: Framework Adoption Readiness

## Status

P43 is the groundwork and decision track for introducing a new agent or workflow
framework. It does not install a framework, switch production runtime behavior,
or claim production readiness. The goal is to decide whether a framework improves
general complex-SP analysis and Java/MyBatis AI Draft Pack quality enough to
justify adoption.

## Recommendation

Introducing a framework is reasonable only behind an adapter and only after an
A/B quality gate. The current internal Responses/httpx gateway remains the
baseline. OpenAI Agents SDK is the first candidate to evaluate because it is
closest to the existing Responses-oriented runtime and supports agent loops,
tools, and tracing. LangGraph is a second candidate if explicit graph state and
durable orchestration become more important than the current workflow service.

P43 must not solve quality by hardcoding `PCO_GU_ManageBond_PRC`. ManageBond is
a benchmark fixture that exposes the class of failure we care about: complex
branch/use-case logic collapsing into too few DTOs or misleading fallback
skeletons. The production workflow must continue deriving inventory from
sanitized operation contracts, statement evidence, branch responsibilities, and
review markers.

## Goal

Define the framework adoption contract, fixture, prompt pack, and sequential
work plan for deciding whether to adopt, pilot, or defer a new framework.

## Context

- Current Java/MyBatis renewal path: P42 `AiJavaMyBatisDraftPack.v0.1`
- Current gateway baseline: `packages/agent-runtime` Responses/httpx model gateway
- Benchmark target: `PPM.dbo.PCO_GU_ManageBond_PRC`
- External quality reference: `D:/migration/test_mcp_server_with_codex/MIGRATION_GUIDE.md`

## In Scope

- Compare the current internal gateway with candidate framework adapters.
- Define `AiGenerationFrameworkAdapter.v0.1` as an internal adapter boundary.
- Keep P42 deterministic inventory, validation, repair, artifact persistence, and
  no-fallback rules as mandatory gates.
- Add P43A-F sequential prompt pack and manifest wiring.
- Add static contract tests for P43 assets.

## Out of Scope

- UI changes.
- Public API, DB schema, public MCP route, or public artifact type changes.
- OpenAI SDK, Agents SDK, LangGraph, or other framework dependency installation in P43A.
- Live OpenAI/live PPM default testing.
- Stored procedure execution, row-data query, business DB DDL/DML, generated source
  apply, or deploy.

## Sequential Slices

1. **P43A: Contract Assets And Decision Frame**
   - Create the P43 contract, ManageBond benchmark fixture, task brief, prompt
     pack, manifest wiring, and static tests.
   - Document the recommendation: adapter-first evaluation, not immediate migration.
2. **P43B: Adapter Contract And Harness**
   - Add an internal adapter protocol and fake adapter tests that can compare the
     existing gateway with candidate framework behavior.
   - Do not install a new framework unless the slice explicitly proves the need
     and policy tests are ready.
3. **P43C: AI Draft Pack Framework Spike**
   - Run P42 AI Draft Pack stages through the adapter path while preserving P42
     schema, quality validator, repair, and no-fallback behavior.
4. **P43D: Tool And Trace Policy Gate**
   - Validate framework tool calls and traces are sanitized. Store trace hashes,
     counts, and stage summaries only.
5. **P43E: Benchmark Replay Comparison**
   - Compare baseline and candidate adapter paths with the ManageBond benchmark
     and at least one synthetic complex-SP inventory-collapse case.
6. **P43F: Docs And Adoption Decision**
   - Produce an adopt/pilot/defer recommendation with test evidence, policy
     caveats, and rollback strategy.

## Candidate Frameworks

- `baseline_internal_responses_gateway`: current control path.
- `openai_agents_sdk`: first candidate for staged agent loops, tool calls, and
  traceable repair if sensitive tracing can be disabled or sanitized.
- `langgraph`: second candidate for explicit graph orchestration if durable
  state adds measurable value.

## Constraints

- `production_ready: false`
- No raw SP definition, raw guide body, raw prompt, raw provider response, row
  data, or secrets in repo fixtures, traces, docs, or platform storage.
- Weak or inferred facts remain `REVIEW_REQUIRED`.
- Framework adoption must improve general inventory and draft quality. It must
  not introduce target-specific hardcoding for ManageBond.

## Deliverables

- `spec/eval/p43_framework_adoption_contract.yaml`
- `fixtures/eval/framework_adoption_p43_manage_bond_v1.yaml`
- P43A-F prompt pack under `ops/codex-parallel/prompts`
- Manifest wiring for sequential P43 execution
- `tests/contract/test_p43_framework_adoption_prompt_assets.py`

## Verification

- `make test PYTEST_ARGS="tests/contract/test_p43_framework_adoption_prompt_assets.py"`
- Later P43 final gate:
  `make test PYTEST_ARGS="tests/contract/test_p43_framework_adoption_prompt_assets.py tests/eval/test_p42_manage_bond_ai_draft_quality.py tests/eval/test_p41_sp_operation_model.py tests/eval/test_p36_output_renewal_quality.py"`
- `git diff --check`

## Done Definition

- P43 assets exist and are wired in the manifest after P42.
- Prompt pack forces sequential work and keeps framework adoption behind an
  adapter.
- ManageBond is documented as a quality benchmark, not a hardcoded runtime key.
- The contract blocks raw trace/prompt/SP/provider/row-data/secret storage.
- The final decision must be evidence-backed and may be `adopt`, `pilot`, or
  `defer`.

## Residual Risks

- A framework may not improve output quality enough to justify dependency and
  operational complexity.
- Built-in framework tracing can be useful but risky unless sensitive data
  capture is disabled and independently scanned.
- Live OpenAI/live PPM confidence remains opt-in and does not imply production
  readiness.
