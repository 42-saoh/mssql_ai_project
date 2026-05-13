from __future__ import annotations

from ai_agent_domain import ArtifactType
from api_app.platform_tool_registry import (
    PlatformToolPolicy,
    PlatformToolRegistry,
    load_platform_tool_catalog,
)

from tests.unit.api.fake_repository import MemoryWorkflowRepository


def _repo_request_job() -> tuple[MemoryWorkflowRepository, object, object]:
    repository = MemoryWorkflowRepository()
    request = repository.create_request(
        db_profile_id="master",
        target={"type": "PROCEDURE", "schema": "dbo", "name": "usp_GetOrderSummary"},
        outputs=("SP_ANALYSIS_DOCUMENT",),
        options={"useLlmAnalysis": True, "usePlatformToolOrchestration": True},
        request_hash="hash",
        correlation_id="test",
        idempotency_key=None,
    )
    job = repository.create_job(request.request_id, correlation_id="test")
    return repository, request, job


def test_platform_tool_catalog_is_internal_read_only() -> None:
    tools = load_platform_tool_catalog()

    names = {tool.name for tool in tools}

    assert {
        "platform.search_knowledge_facts",
        "platform.list_knowledge_assets",
        "platform.get_knowledge_version_graph",
        "platform.list_job_artifacts",
        "platform.get_latest_validation_report",
        "platform.list_job_agent_runs",
        "platform.list_registry_versions",
    } <= names
    assert all(tool.active for tool in tools)
    assert all(tool.read_only for tool in tools)
    assert all(tool.internal_only for tool in tools)


def test_platform_tool_policy_clamps_limits_and_blocks_scope_or_unsafe_arguments() -> None:
    _repository, request, job = _repo_request_job()
    policy = PlatformToolPolicy(
        tools=load_platform_tool_catalog(),
        request_record=request,
        job_id=job.job_id,
    )

    allowed = policy.decide(
        tool_name="platform.list_job_agent_runs",
        arguments={"jobId": job.job_id, "limit": 99},
    )
    invalid_limit = policy.decide(
        tool_name="platform.list_job_agent_runs",
        arguments={"jobId": job.job_id, "limit": "many"},
    )
    low_limit = policy.decide(
        tool_name="platform.list_job_agent_runs",
        arguments={"jobId": job.job_id, "limit": 0},
    )
    switched_job = policy.decide(
        tool_name="platform.list_job_artifacts",
        arguments={"jobId": "job_elsewhere"},
    )
    unsafe = policy.decide(
        tool_name="platform.search_knowledge_facts",
        arguments={"targetName": "usp_GetOrderSummary", "sql": "DROP TABLE dbo.T"},
    )
    freeform_sql = policy.decide(
        tool_name="platform.search_knowledge_facts",
        arguments={"targetName": "SELECT * FROM dbo.T"},
    )

    assert allowed.allowed is True
    assert allowed.arguments["limit"] == 20
    assert invalid_limit.allowed is True
    assert invalid_limit.arguments["limit"] == 20
    assert low_limit.allowed is True
    assert low_limit.arguments["limit"] == 1
    assert switched_job.allowed is False
    assert switched_job.code == "PLATFORM_TOOL_SCOPE_SWITCH_BLOCKED"
    assert unsafe.allowed is False
    assert unsafe.code == "PLATFORM_TOOL_FORBIDDEN_ARGUMENT"
    assert freeform_sql.allowed is False
    assert freeform_sql.code == "PLATFORM_TOOL_FREEFORM_SQL_BLOCKED"


def test_platform_tool_registry_returns_sanitized_presenter_payloads() -> None:
    repository, request, job = _repo_request_job()
    artifact = repository.add_artifact(
        job_id=job.job_id,
        artifact_type=ArtifactType.SP_ANALYSIS_DOC,
        title="SP analysis",
        content="full artifact content must not be returned by summary tools",
        evidence_refs=[
            {
                "type": "MSSQL_METADATA",
                "objectRef": "dbo.usp_GetOrderSummary",
                "locator": "fixture",
            }
        ],
        generator_version="test-generator",
        registry_refs=("template:test",),
        assumptions=("draft",),
        review_required=True,
    )
    repository.save_validation_report(
        artifact_id=artifact.artifact_id,
        status="REVIEW_REQUIRED",
        checks=[
            {
                "ruleId": "evidence.required",
                "severity": "WARNING",
                "result": "REVIEW_REQUIRED",
                "message": "review",
            }
        ],
        missing_evidence=[],
        manual_review_points=["review"],
    )
    registry = PlatformToolRegistry(
        repository=repository,
        request_record=request,
        job_id=job.job_id,
    )

    artifacts = registry.invoke_payload(
        "platform.list_job_artifacts",
        {"arguments": {"jobId": job.job_id}},
    )
    validation = registry.invoke_payload(
        "platform.get_latest_validation_report",
        {"arguments": {"artifactId": artifact.artifact_id}},
    )
    registry_versions = registry.invoke_payload(
        "platform.list_registry_versions",
        {"arguments": {}},
    )

    assert artifacts["ok"] is True
    assert artifacts["data"]["artifacts"][0]["artifactId"] == artifact.artifact_id
    assert "content" not in str(artifacts["data"]).lower()
    assert validation["data"]["status"] == "REVIEW_REQUIRED"
    assert registry_versions["data"]["versions"]
    assert "password" not in str(registry_versions).lower()
