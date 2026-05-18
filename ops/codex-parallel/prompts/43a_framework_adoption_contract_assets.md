## Role
architect / template_engineer with `contract-to-code`, `eval-fixture-authoring`, and `docs-sync`.

## Task
P43A: establish the framework-adoption readiness groundwork for complex SP
analysis and Java/MyBatis AI Draft Pack generation. Keep `production_ready: false`.

## Scope
- Review P42/P42H behavior and decide whether framework adoption should be
  evaluated through an adapter-first spike.
- Maintain `spec/eval/p43_framework_adoption_contract.yaml`,
  `fixtures/eval/framework_adoption_p43_manage_bond_v1.yaml`,
  `tasks/0043-framework-adoption-readiness.md`, prompt pack, manifest wiring, and
  static tests.
- Treat `PCO_GU_ManageBond_PRC` as a benchmark fixture only.
- Compare candidates conceptually: current Responses/httpx gateway baseline,
  OpenAI Agents SDK, and LangGraph.

## Constraints
- Do not install OpenAI Agents SDK, LangGraph, or another framework in P43A.
- Do not change public API, DB schema, UI, public MCP routes, or public artifact types.
- Do not store raw SP definition, raw guide body, raw prompt, raw provider response,
  row data, or secrets.
- Do not run stored procedures, allow procedure execution, query row data, apply
  business DB DDL/DML, write generated source into application trees, or deploy.
- Do not add ManageBond-specific production-runtime hardcoding.

## Acceptance
- P43 contract and fixture exist and keep `production_ready: false`.
- P43A-F prompts are wired sequentially in the manifest.
- Contract states adapter-first evaluation and a baseline-vs-candidate decision gate.
- ManageBond is documented as a benchmark, not a runtime answer key.
- Static tests pass through the Git Bash `make test` path.
