from __future__ import annotations

import json
import os

import pytest
from ai_agent_runtime import (
    AI_GENERATION_RUNTIME_OPENAI_AGENTS,
    framework_runtime_config_from_env,
)
from api_app.memory_repository import MemoryWorkflowRepository
from api_app.schemas import SPAnalysisRequest
from api_app.workflow import WorkflowService


def _request() -> SPAnalysisRequest:
    return SPAnalysisRequest.model_validate(
        {
            "dbProfileId": "master",
            "target": {"type": "PROCEDURE", "schema": "dbo", "name": "usp_GetOrderSummary"},
            "outputs": ["SP_ANALYSIS_DOCUMENT"],
            "options": {
                "useLlmAnalysis": True,
                "llmProfileId": "openai_fast_test",
                "allowSpDefinitionToModel": True,
            },
        }
    )


def test_p22_gate_disabled_does_not_require_openai_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ("LLM_LIVE_GATE", "LLM_ENABLE_REMOTE", "LLM_ALLOW_SP_TEXT", "OPENAI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("P21_LIVE_PORTAL_GATE", "0")
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")

    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)
    _request_record, job = service.submit_sp_analysis(_request())

    runs = repository.list_agent_runs(job.job_id)
    assert runs is not None
    assert runs[0].model_invocation["provider"] == "fake-openai-compatible"


def test_p22_openai_live_agent_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    if os.getenv("LLM_LIVE_GATE") != "1":
        pytest.skip("LLM_LIVE_GATE is not enabled; no external OpenAI API call attempted.")
    monkeypatch.setenv("P21_LIVE_PORTAL_GATE", "0")
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")
    missing = [
        name
        for name in ("LLM_ENABLE_REMOTE", "LLM_ALLOW_SP_TEXT", "OPENAI_API_KEY")
        if not os.getenv(name)
    ]
    if missing:
        pytest.fail(f"Missing P22 OpenAI live gate env: {', '.join(missing)}")

    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)
    _request_record, job = service.submit_sp_analysis(_request())
    runs = repository.list_agent_runs(job.job_id)
    if not runs or runs[0].status != "SUCCEEDED":
        pytest.fail(
            json.dumps(
                [run.__dict__ for run in runs or []],
                ensure_ascii=False,
                default=str,
            )
        )
    assert runs[0].model_invocation["provider"] == _expected_remote_provider()
    assert "CREATE PROCEDURE" not in str(runs[0].model_invocation)


def _expected_remote_provider() -> str:
    if (
        framework_runtime_config_from_env().structured_llm_runtime
        == AI_GENERATION_RUNTIME_OPENAI_AGENTS
    ):
        return "openai-agents-sdk"
    provider = os.getenv("LLM_REMOTE_PROVIDER", "openai").strip().lower()
    if provider in {"pgpt", "p-gpt", "private-gpt"}:
        return "pgpt"
    return "openai"
