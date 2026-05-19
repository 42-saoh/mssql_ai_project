# Test Gate History

이 문서는 Pxx 시절의 세부 검증 명령을 evidence/history 로 보존한다. Active 운영 진입점은 `make test-core`, `make test-quality`, `make test-web`, `make test-live-confidence` 이며 alias 정의는 `tests/suites.yaml` 이 기준이다.

## Fixture-First History

```bash
make test PYTEST_ARGS="tests/e2e tests/eval"
make test PYTEST_ARGS="tests/eval/test_p23_llm_sp_analysis_quality.py tests/unit/agent_runtime tests/contract/test_p23_llm_eval_contract_prompt_assets.py"
make test PYTEST_ARGS="tests/eval/test_p24_sp_migration_guide_quality.py tests/contract/test_p24_sp_migration_guide_contract_prompt_assets.py"
make test PYTEST_ARGS="tests/unit/test_mcp_catalog.py tests/unit/mcp/test_tool_registry.py tests/contract/mcp/test_tool_invocation_contract.py tests/contract/test_p27_dependency_evidence_tooling_prompt_assets.py tests/unit/api/test_metadata_service.py tests/unit/api/test_metadata_gateway.py tests/unit/api/test_ai_tool_orchestrator.py tests/unit/api/test_workflow_service.py tests/unit/api/test_route_surface.py tests/unit/web/test_p14_product_ui_static.py tests/integration/api/test_api_workflow_routes.py tests/e2e/test_fixture_workflow_happy_path.py tests/contract/test_openapi_and_env_sample_assets.py"
make test PYTEST_ARGS="tests/unit/api/test_metadata_analysis_service.py tests/eval/test_p30_metadata_ai_mcp_analysis.py tests/integration/api/test_api_workflow_routes.py tests/contract/test_openapi_and_env_sample_assets.py tests/unit/web/test_p14_product_ui_static.py"
make test PYTEST_ARGS="tests/unit/api/test_metadata_analysis_service.py tests/eval/test_p30_metadata_ai_mcp_analysis.py tests/eval/test_p31_metadata_object_insight_depth.py tests/eval/test_p32_live_confidence_planner_effectiveness.py tests/integration/api/test_api_workflow_routes.py tests/contract/test_openapi_and_env_sample_assets.py tests/unit/web/test_p14_product_ui_static.py"
make test PYTEST_ARGS="tests/unit/api/test_metadata_tool_cache.py tests/unit/api/test_workflow_service.py tests/unit/api/test_metadata_analysis_service.py tests/unit/api/test_batch_sp_analysis.py tests/integration/api/test_api_workflow_routes.py tests/eval/test_p33_performance_scale.py tests/contract/test_openapi_and_env_sample_assets.py tests/unit/web/test_p14_product_ui_static.py"
make test PYTEST_ARGS="tests/unit/api/test_knowledge_asset_service.py tests/unit/api/test_workflow_service.py tests/unit/api/test_metadata_analysis_service.py tests/integration/api/test_api_workflow_routes.py tests/integration/api/test_api_auth_rbac.py tests/contract/test_openapi_and_env_sample_assets.py tests/eval/test_p34_knowledge_assetization.py tests/unit/web/test_p14_product_ui_static.py"
make test PYTEST_ARGS="@framework-contracts"
make test PYTEST_ARGS="tests/contract/test_p44_framework_runtime_adoption_assets.py tests/unit/agent_runtime/test_openai_agents_framework_adapter.py tests/unit/agent_runtime/test_langgraph_ai_draft_pack_orchestrator.py tests/unit/api/test_workflow_service.py tests/eval/test_p44_framework_runtime_replay.py tests/eval/test_p42_manage_bond_ai_draft_quality.py tests/eval/test_p41_sp_operation_model.py tests/eval/test_p36_output_renewal_quality.py"
make test PYTEST_ARGS="tests/contract/test_p47_generic_ai_draft_quality_uplift_assets.py tests/unit/agent_runtime/test_ai_draft_pack_planner.py tests/eval/test_p42_live_ai_draft_pack_replay_gate.py"
```

## Optional Live History

```bash
AUTH_RBAC_LIVE_GATE=1 AUTH_RBAC_ENFORCEMENT=1 make test PYTEST_ARGS="tests/eval/test_p20_auth_rbac_live_gate.py"
P21_LIVE_PORTAL_GATE=1 make test PYTEST_ARGS="tests/eval/test_p21_live_portal_no_mock_gate.py"
LLM_LIVE_GATE=1 LLM_ENABLE_REMOTE=1 LLM_ALLOW_SP_TEXT=1 make test PYTEST_ARGS="tests/eval/test_p22_openai_live_agent_gate.py"
LLM_LIVE_GATE=1 LLM_ENABLE_REMOTE=1 LLM_ALLOW_SP_TEXT=1 make test PYTEST_ARGS="tests/eval/test_p23_openai_quality_live_gate.py"
P27_HARD_LIVE_GATE=1 MSSQL_ENABLE_LIVE_METADATA=1 MSSQL_METADATA_CONNECT_TIMEOUT_SECONDS=20 make test PYTEST_ARGS="tests/eval/test_p27_dependency_evidence_hard_live_gate.py"
P32_LIVE_CONFIDENCE_GATE=1 LLM_LIVE_GATE=1 LLM_ENABLE_REMOTE=1 MSSQL_ENABLE_LIVE_METADATA=1 MSSQL_METADATA_CONNECT_TIMEOUT_SECONDS=20 make test PYTEST_ARGS="tests/eval/test_p32_live_confidence_planner_effectiveness.py"
P35_KNOWLEDGE_LIVE_GATE=1 LLM_LIVE_GATE=1 LLM_ENABLE_REMOTE=1 LLM_ALLOW_SP_TEXT=1 MSSQL_ENABLE_LIVE_METADATA=1 MSSQL_METADATA_CONNECT_TIMEOUT_SECONDS=20 PLATFORM_DB_CONNECT_TIMEOUT_SECONDS=20 make test PYTEST_ARGS="tests/eval/test_p35_knowledge_live_confidence_gate.py"
P44_OPENAI_AGENTS_LIVE_GATE=1 LLM_ENABLE_REMOTE=1 LLM_REMOTE_PROVIDER=openai OPENAI_API_KEY=<secret> OPENAI_AGENTS_DISABLE_TRACING=1 OPENAI_AGENTS_TRACE_INCLUDE_SENSITIVE_DATA=0 OPENAI_AGENTS_DONT_LOG_MODEL_DATA=1 OPENAI_AGENTS_DONT_LOG_TOOL_DATA=1 make test PYTEST_ARGS="tests/eval/test_p45_openai_agents_live_gate.py"
P44_OPENAI_AGENTS_LIVE_GATE=1 LLM_ENABLE_REMOTE=1 LLM_REMOTE_PROVIDER=openai OPENAI_API_KEY=<secret> OPENAI_MODEL_AI_DRAFT_PACK=<model> OPENAI_REASONING_EFFORT_AI_DRAFT_PACK=high OPENAI_AGENTS_DISABLE_TRACING=1 OPENAI_AGENTS_TRACE_INCLUDE_SENSITIVE_DATA=0 OPENAI_AGENTS_DONT_LOG_MODEL_DATA=1 OPENAI_AGENTS_DONT_LOG_TOOL_DATA=1 make test PYTEST_ARGS="tests/eval/test_p45_openai_agents_live_gate.py"
P44_OPENAI_AGENTS_LIVE_GATE=1 LLM_ENABLE_REMOTE=1 LLM_REMOTE_PROVIDER=pgpt AI_GENERATION_RUNTIME=openai_agents AI_DRAFT_PACK_ORCHESTRATOR=langgraph OPENAI_AGENTS_COMPATIBLE_API=responses OPENAI_API_KEY=<secret> OPENAI_BASE_URL=<compatible-base> OPENAI_AGENTS_DISABLE_TRACING=1 OPENAI_AGENTS_TRACE_INCLUDE_SENSITIVE_DATA=0 OPENAI_AGENTS_DONT_LOG_MODEL_DATA=1 OPENAI_AGENTS_DONT_LOG_TOOL_DATA=1 make test PYTEST_ARGS="tests/eval/test_p45_openai_agents_live_gate.py"
P21_LIVE_PORTAL_GATE=1 P27_HARD_LIVE_GATE=1 P32_LIVE_CONFIDENCE_GATE=1 P35_KNOWLEDGE_LIVE_GATE=1 LLM_LIVE_GATE=1 LLM_ENABLE_REMOTE=1 LLM_ALLOW_SP_TEXT=1 MSSQL_ENABLE_LIVE_METADATA=1 MSSQL_METADATA_CONNECT_TIMEOUT_SECONDS=20 PLATFORM_DB_CONNECT_TIMEOUT_SECONDS=20 make test PYTEST_ARGS="tests/eval/test_p21_live_portal_no_mock_gate.py tests/eval/test_p22_openai_live_agent_gate.py tests/eval/test_p23_openai_quality_live_gate.py tests/eval/test_p27_dependency_evidence_hard_live_gate.py tests/eval/test_p32_live_confidence_planner_effectiveness.py tests/eval/test_p35_knowledge_live_confidence_gate.py"
```

## Interpretation

- Fixture-first gates never require live PLF, live PPM, OpenAI, P-GPT, or IdP/JWKS.
- Optional live gates are confidence evidence only and must not be used as production readiness, publish/deploy approval, DDL apply approval, or automatic conversion approval.
- PPM metadata failure must remain a blocker or skip according to the explicit gate mode; it must never fall back to PLF.
- P43F records a `pilot` framework decision from fixture-first replay only. Real framework dependency approval, OpenAI Agents SDK trace redaction, LangGraph persistence redaction, and optional live evidence remain future `REVIEW_REQUIRED` items.
- P44 supersedes P43 as the active framework runtime adoption gate: OpenAI Agents SDK and LangGraph are adopted internally for AI Draft Pack generation/orchestration, while generated artifacts remain `production_ready: false` and procedure execution, row data, source apply, deploy, raw prompt/provider response storage, raw SP/guide storage, and LangGraph checkpoint persistence remain forbidden.
- P45 optional live evidence uses `P44_OPENAI_AGENTS_LIVE_GATE=1` with sanitized fixture inputs only; it must not require PPM row data or procedure execution. It accepts official OpenAI evidence or approved P-GPT-compatible SDK evidence when the runtime is explicit and P42/P44 validation passes. P46 keeps `responses_httpx` for P-GPT default compatibility and emergency rollback, not as the active OpenAI default.
- P47 adds generic AI Draft Pack quality uplift: `DraftPackEvidenceBundle.v0.1`, prompt `@0.2.0`, `openai_ai_draft_pack`, and benchmark-only ManageBond metrics. Live failures must be reported as sanitized stage/blocker diagnostics; P42 now has a sanitized fixture live mode that avoids raw SP external export, while `live_ppm` remains explicit confidence evidence only.
- 2026-05-19 P47 audit: P42 sanitized fixture replay passed without PPM/raw SP access and is the current accepted live replay gate. The earlier P42 `live_ppm` result remains historical confidence evidence and is not rerun without explicit raw-SP-to-remote-model approval. P45 compatible P-GPT SDK evidence passed through explicit `AI_GENERATION_RUNTIME=openai_agents`, LangGraph, trace locks, and sanitized fixture input. Earlier official OpenAI override reached `file_inventory` and failed with sanitized `P44_OPENAI_AGENTS_ADAPTER_FAILED` / `AuthenticationError`. No raw provider payload is recorded in repo docs.
