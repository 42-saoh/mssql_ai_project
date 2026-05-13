from __future__ import annotations

from ai_agent_runtime.gateway import FakeModelGateway
from api_app.metadata_gateway import MetadataCollectionResult
from api_app.platform_tool_orchestrator import PlatformToolOrchestrator

from tests.unit.api.fake_repository import MemoryWorkflowRepository


def _repo_request_job(options: dict | None = None):
    repository = MemoryWorkflowRepository()
    request = repository.create_request(
        db_profile_id="master",
        target={"type": "PROCEDURE", "schema": "dbo", "name": "usp_GetOrderSummary"},
        outputs=("SP_ANALYSIS_DOCUMENT",),
        options={
            "useLlmAnalysis": True,
            "usePlatformToolOrchestration": True,
            "llmProfileId": "openai_fast_test",
            **(options or {}),
        },
        request_hash="hash",
        correlation_id="test",
        idempotency_key=None,
    )
    job = repository.create_job(request.request_id, correlation_id="test")
    return repository, request, job


def _metadata() -> MetadataCollectionResult:
    return MetadataCollectionResult(
        db_profile_id="master",
        object_ref="dbo.usp_GetOrderSummary",
        snapshot_id="snap_test",
        collected_at="2026-05-14T00:00:00+00:00",
        evidence_refs=(
            {
                "objectRef": "dbo.usp_GetOrderSummary",
                "locator": "fixture.metadata",
            },
        ),
    )


def test_platform_tool_orchestrator_falls_back_to_registry_versions() -> None:
    repository, request, job = _repo_request_job()
    orchestrator = PlatformToolOrchestrator(
        model_gateway=FakeModelGateway(),
        repository=repository,
    )

    result = orchestrator.run(
        job_id=job.job_id,
        request_record=request,
        metadata=_metadata(),
        static_analysis=None,
    )

    evidence = result.metadata.platform_tool_evidence
    assert evidence is not None
    assert evidence["status"] == "REVIEW_REQUIRED"
    assert evidence["toolCallCount"] == 1
    assert evidence["toolResults"][0]["factId"].startswith(
        "platform.list_registry_versions."
    )
    assert result.metadata.deterministic_facts[-1]["id"].startswith(
        "platform.list_registry_versions."
    )
    assert any(
        component["stage"] == "platform_tool_execution"
        for component in result.component_invocations
    )


def test_platform_tool_orchestrator_blocks_scope_switch_and_continues() -> None:
    repository, request, job = _repo_request_job()
    gateway = FakeModelGateway(
        platform_tool_plan_by_target_ref={
            "dbo.usp_GetOrderSummary": {
                "toolRequests": [
                    {
                        "toolName": "platform.list_job_artifacts",
                        "arguments": {"jobId": "job_elsewhere"},
                        "reason": "try switching jobs",
                        "expectedEvidenceUse": "should be blocked",
                    },
                    {
                        "toolName": "platform.list_registry_versions",
                        "arguments": {},
                        "reason": "safe fallback evidence",
                        "expectedEvidenceUse": "registry refs",
                    },
                ],
                "assumptions": [],
                "reviewMarkers": [],
            }
        }
    )
    orchestrator = PlatformToolOrchestrator(
        model_gateway=gateway,
        repository=repository,
    )

    result = orchestrator.run(
        job_id=job.job_id,
        request_record=request,
        metadata=_metadata(),
        static_analysis=None,
    )

    evidence = result.metadata.platform_tool_evidence
    assert evidence is not None
    assert evidence["toolCallCount"] == 1
    assert evidence["blockedRequests"][0]["code"] == "PLATFORM_TOOL_SCOPE_SWITCH_BLOCKED"
    assert "PLATFORM_TOOL_SCOPE_SWITCH_BLOCKED" in evidence["caveats"]


def test_platform_tool_orchestrator_respects_disable_and_budget() -> None:
    repository, disabled_request, job = _repo_request_job({"useLlmAnalysis": False})
    disabled = PlatformToolOrchestrator(
        model_gateway=FakeModelGateway(),
        repository=repository,
    ).run(
        job_id=job.job_id,
        request_record=disabled_request,
        metadata=_metadata(),
        static_analysis=None,
    )

    budget_repository, budget_request, budget_job = _repo_request_job()
    budgeted = PlatformToolOrchestrator(
        model_gateway=FakeModelGateway(),
        repository=budget_repository,
        max_tool_calls=0,
    ).run(
        job_id=budget_job.job_id,
        request_record=budget_request,
        metadata=_metadata(),
        static_analysis=None,
    )

    assert disabled.metadata.platform_tool_evidence is None
    assert budgeted.metadata.platform_tool_evidence is not None
    assert "PLATFORM_TOOL_CALL_BUDGET_EXHAUSTED" in budgeted.metadata.platform_tool_evidence[
        "caveats"
    ]
