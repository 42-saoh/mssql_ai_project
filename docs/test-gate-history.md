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
make test PYTEST_ARGS="tests/eval/test_p43_framework_adapter_replay.py tests/unit/agent_runtime/test_framework_adapter.py tests/unit/api/test_workflow_service.py tests/unit/validation/test_ai_draft_pack_validator.py tests/contract/test_p43_framework_adoption_prompt_assets.py tests/eval/test_p42_manage_bond_ai_draft_quality.py tests/eval/test_p41_sp_operation_model.py tests/eval/test_p36_output_renewal_quality.py"
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
P21_LIVE_PORTAL_GATE=1 P27_HARD_LIVE_GATE=1 P32_LIVE_CONFIDENCE_GATE=1 P35_KNOWLEDGE_LIVE_GATE=1 LLM_LIVE_GATE=1 LLM_ENABLE_REMOTE=1 LLM_ALLOW_SP_TEXT=1 MSSQL_ENABLE_LIVE_METADATA=1 MSSQL_METADATA_CONNECT_TIMEOUT_SECONDS=20 PLATFORM_DB_CONNECT_TIMEOUT_SECONDS=20 make test PYTEST_ARGS="tests/eval/test_p21_live_portal_no_mock_gate.py tests/eval/test_p22_openai_live_agent_gate.py tests/eval/test_p23_openai_quality_live_gate.py tests/eval/test_p27_dependency_evidence_hard_live_gate.py tests/eval/test_p32_live_confidence_planner_effectiveness.py tests/eval/test_p35_knowledge_live_confidence_gate.py"
```

## Interpretation

- Fixture-first gates never require live PLF, live PPM, OpenAI, P-GPT, or IdP/JWKS.
- Optional live gates are confidence evidence only and must not be used as production readiness, publish/deploy approval, DDL apply approval, or automatic conversion approval.
- PPM metadata failure must remain a blocker or skip according to the explicit gate mode; it must never fall back to PLF.
- P43F records a `pilot` framework decision from fixture-first replay only. Real framework dependency approval, OpenAI Agents SDK trace redaction, LangGraph persistence redaction, and optional live evidence remain future `REVIEW_REQUIRED` items.
