from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_p22_openapi_declares_llm_options_trace_and_evidence_type() -> None:
    openapi = yaml.safe_load(
        (ROOT / "spec" / "openapi" / "ai_agent_platform_openapi_v1.yaml").read_text(
            encoding="utf-8"
        )
    )
    schemas = openapi["components"]["schemas"]

    assert "/api/v1/jobs/{jobId}/agent-runs" in openapi["paths"]
    options = schemas["SPAnalysisOptions"]["properties"]
    assert options["useLlmAnalysis"]["default"] is True
    assert options["llmProfileId"]["enum"] == [
        "openai_sp_semantic_analysis",
        "openai_fast_test",
    ]
    assert options["allowSpDefinitionToModel"]["default"] is True
    assert options["usePlatformToolOrchestration"]["default"] is True
    assert "LLM_INFERENCE" in schemas["EvidenceRef"]["properties"]["type"]["enum"]
    assert "AgentRunSummary" in schemas
    assert "ModelInvocationSummary" in schemas
    assert "componentInvocations" in schemas["ModelInvocationSummary"]["properties"]
    assert "MODEL" in schemas["RegistryVersion"]["properties"]["registryType"]["enum"]
    assert "SCHEMA" in schemas["RegistryVersion"]["properties"]["registryType"]["enum"]


def test_p22_schema_v3_has_agent_runtime_tables_without_raw_text_columns() -> None:
    ddl = (ROOT / "db" / "schema" / "ai_agent_platform_schema_v3_agent_runtime.sql").read_text(
        encoding="utf-8"
    )
    upper = ddl.upper()

    assert "CREATE TABLE DBO.AGENT_RUNS" in upper
    assert "CREATE TABLE DBO.MODEL_INVOCATIONS" in upper
    assert "STRUCTURED_OUTPUT_JSON" in upper
    assert "INPUT_HASH_SHA256_VAL" in upper
    assert "PROMPT_HASH_SHA256_VAL" in upper
    assert "OUTPUT_HASH_SHA256_VAL" in upper
    for forbidden in (
        "RAW_PROMPT",
        "RAW_SQL",
        "SP_DEFINITION_TXT",
        "RESPONSE_TEXT",
        "PRVDR_REQ_ID",
        "ERR_CNTNT",
    ):
        assert forbidden not in upper


def test_p22_env_sample_contains_llm_gates_without_secret_values() -> None:
    env_text = (ROOT / ".env.example").read_text(encoding="utf-8")

    for name in (
        "LLM_REMOTE_PROVIDER=openai",
        "OPENAI_RESPONSES_URL=",
        "OPENAI_MODEL_ANALYSIS=gpt-5.5",
        "OPENAI_MODEL_FAST_TEST=gpt-5-nano",
        "PGPT_MODEL_ANALYSIS=gpt-4o",
        "PGPT_MODEL_FAST_TEST=gpt-4o-mini",
        "LLM_ENABLE_REMOTE=0",
        "LLM_ALLOW_SP_TEXT=0",
        "LLM_LIVE_GATE=0",
        "LLM_SP_CONCURRENCY=2",
        "PLATFORM_TOOL_MAX_CALLS=3",
    ):
        assert name in env_text
    assert "OPENAI_API_KEY=\n" in env_text
    assert "sk-" not in env_text


def test_p22_registry_route_exposes_model_prompt_and_schema_bindings(monkeypatch) -> None:
    from api_app.routes.registry import active_registry_bindings

    monkeypatch.delenv("LLM_REMOTE_PROVIDER", raising=False)
    monkeypatch.delenv("PGPT_MODEL_FAST_TEST", raising=False)
    monkeypatch.setenv("OPENAI_MODEL_FAST_TEST", "gpt-5.4-mini")
    versions = {binding.version for binding in active_registry_bindings()}

    assert "model:openai_sp_semantic_analysis@0.1.0" in versions
    assert "model:openai_fast_test@gpt-5.4-mini@0.1.0" in versions
    assert "prompt:sp_semantic_analysis@0.4.0" in versions
    assert "schema:llm_semantic_analysis@0.4.0" in versions
    assert "prompt:platform_tool_planner@0.1.0" in versions
    assert "schema:platform_tool_plan@0.1.0" in versions
