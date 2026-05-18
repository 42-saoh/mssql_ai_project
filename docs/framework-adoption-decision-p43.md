# P43 Framework Adoption Decision

## Decision

P43 decision: `pilot`.

This is not an adoption decision and not a runtime migration. P43B-E proved that
framework candidates can be represented behind `AiGenerationFrameworkAdapter.v0.1`
with sanitized tool context, hash/count/code trace summaries, and the same P42
schema and Java/MyBatis quality gates. P43 did not install OpenAI Agents SDK,
LangGraph, or another framework dependency, and it did not prove a real framework
adapter with live evidence.

`production_ready` remains false. P43 does not approve automatic conversion,
generated source apply, deploy, row-data access, stored procedure execution,
business DB DDL/DML, public API expansion, public MCP route expansion, UI changes,
DB schema changes, or public artifact type changes.

## Evidence

Changed files include the P43 adapter contract and planner spike, workflow
injection seam, static policy gates, replay fixtures, contract tests, and this
docs sync. The user-facing artifact surface remains unchanged.

Quality comparison result: fake candidate adapters preserve baseline quality.
The P43E replay compares the current Responses/httpx baseline adapter with fake
candidate adapters on the same deterministic inventory contract. ManageBond
benchmark artifacts reconstruct into `AiJavaMyBatisDraftPack.v0.1`, pass the P42
static validator, preserve 11 required DTO artifact rows, and keep required DTO,
Service method, Mapper method, and review marker coverage at 1.0. The synthetic
complex-SP replay passes without ManageBond DTO names, while the synthetic
two-DTO collapse case fails the same P42 validator as expected.

Policy findings: no raw trace leakage, public interface change, new framework
dependency, row-data access, procedure execution, source apply, or deploy path is
introduced. Framework trace summaries remain limited to adapter ids, candidate
framework, stage/status, component ids, counts, hashes, blocker/failure codes, and
numeric policy-safe metrics.

## Rollback

The rollback path is the existing Responses/httpx
`ModelGateway.draft_ai_java_mybatis_pack` flow and
`BaselineResponsesFrameworkAdapter`. If any future real framework adapter weakens
P42 schema validation, deterministic inventory checks, static Java/MyBatis quality
validation, storage policy, or no-fallback behavior, the workflow can continue to
use the current gateway path without a public contract change.

## Residual Review

Residual `REVIEW_REQUIRED` items:

- `P43_FRAMEWORK_DEPENDENCY_NOT_APPROVED`
- `P43_FRAMEWORK_LIVE_GATE_NOT_CONFIGURED`
- `OPENAI_AGENTS_SDK_TRACING_REDACTION_REVIEW_REQUIRED`
- `LANGGRAPH_PERSISTENCE_REDACTION_REVIEW_REQUIRED`
- `WEAK_OR_UNSUPPORTED_FRAMEWORK_FACTS_REVIEW_REQUIRED`

OpenAI Agents SDK remains blocked until tracing is disabled or configured to
exclude sensitive inputs and outputs. LangGraph remains blocked until graph-state
persistence and checkpointers have a proven redacted serializer/checkpointer
boundary. Optional live OpenAI/PPM replay remains confidence evidence only.

## Verification

P43F static/docs gate:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/win_git_bash.ps1 make test PYTEST_ARGS="tests/contract/test_p43_framework_adoption_prompt_assets.py"
```

Final P43 regression gate:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/win_git_bash.ps1 make test PYTEST_ARGS="tests/eval/test_p43_framework_adapter_replay.py tests/unit/agent_runtime/test_framework_adapter.py tests/unit/api/test_workflow_service.py tests/unit/validation/test_ai_draft_pack_validator.py tests/contract/test_p43_framework_adoption_prompt_assets.py tests/eval/test_p42_manage_bond_ai_draft_quality.py tests/eval/test_p41_sp_operation_model.py tests/eval/test_p36_output_renewal_quality.py"
```

Whitespace safety:

```powershell
git -c safe.directory=D:/wt/p35 diff --check
```
