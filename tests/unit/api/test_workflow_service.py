from __future__ import annotations

import json

import pytest
from ai_agent_domain import ArtifactStatus, ArtifactType, JobStatus, WorkflowStepType
from ai_agent_runtime.gateway import ModelGatewayError, model_profile_from_env
from ai_agent_runtime.models import AgentRunStatus, ModelInvocationRecord, stable_json_hash
from api_app.lifecycle import WorkflowStateError
from api_app.schemas import SPAnalysisRequest
from api_app.tracking import IdempotencyConflictError, RequestTrackingContext
from api_app.workflow import (
    WORKFLOW_METADATA_NOTE,
    WorkflowService,
    dependency_procedure_candidates,
)

from tests.unit.api.fake_repository import MemoryWorkflowRepository


@pytest.fixture(autouse=True)
def fixture_metadata_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("P21_LIVE_PORTAL_GATE", "0")
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")
    monkeypatch.setenv("LLM_ENABLE_REMOTE", "0")


def _request(outputs: list[str] | None = None) -> SPAnalysisRequest:
    return SPAnalysisRequest.model_validate(
        {
            "dbProfileId": "master",
            "target": {
                "type": "PROCEDURE",
                "schema": "dbo",
                "name": "usp_OrderRequest_Select",
            },
            "outputs": outputs
            or [
                "SP_ANALYSIS_DOCUMENT",
                "DEPENDENCY_REPORT",
                "JAVA_MYBATIS_DRAFT",
            ],
            "options": {"includeEvidenceRefs": True},
        }
    )


def _llm_request(outputs: list[str] | None = None) -> SPAnalysisRequest:
    return SPAnalysisRequest.model_validate(
        {
            "dbProfileId": "master",
            "target": {
                "type": "PROCEDURE",
                "schema": "dbo",
                "name": "usp_GetOrderSummary",
            },
            "outputs": outputs or ["SP_ANALYSIS_DOCUMENT", "DEPENDENCY_REPORT"],
            "options": {
                "includeEvidenceRefs": True,
                "useLlmAnalysis": True,
                "llmProfileId": "openai_fast_test",
                "allowSpDefinitionToModel": True,
            },
        }
    )


def _fixture_request(outputs: list[str] | None = None) -> SPAnalysisRequest:
    return SPAnalysisRequest.model_validate(
        {
            "dbProfileId": "master",
            "target": {
                "type": "PROCEDURE",
                "schema": "dbo",
                "name": "usp_GetOrderSummary",
            },
            "outputs": outputs or ["SP_ANALYSIS_DOCUMENT", "TABLE_COLUMN_METADATA"],
            "options": {"includeEvidenceRefs": True},
        }
    )


def _passed_sp_analysis_content() -> str:
    return "\n".join(
        [
            "# Analysis",
            "",
            "## input_interpretation",
            "dbo.usp_demo",
            "",
            "## analysis_summary",
            "dbo.usp_demo는 metadata-only evidence로 표현됩니다.",
            "",
            "## procedure_signature",
            "dbo.usp_demo()",
            "",
            "## evidence_summary",
            "dbo.usp_demo",
            "",
            "## assumptions_and_todo",
            "없음.",
            "",
            "## review_checklist",
            "- [x] Evidence ref 확인 완료.",
            "",
        ]
    )


def _model_invocation(
    *,
    prompt,
    profile,
    provider: str,
    structured_output: dict,
) -> ModelInvocationRecord:
    return ModelInvocationRecord(
        provider=provider,
        model=profile.model,
        model_profile_id=profile.profile_id,
        model_registry_ref=profile.registry_ref,
        reasoning_effort=profile.reasoning_effort,
        prompt_version=prompt.prompt_version,
        output_schema_version=prompt.output_schema_version,
        input_hash=prompt.input_hash,
        prompt_hash=prompt.prompt_hash,
        output_hash=stable_json_hash(structured_output),
        status=AgentRunStatus.SUCCEEDED,
        structured_output=structured_output,
        token_usage={"inputTokens": 0, "outputTokens": 0, "totalTokens": 0},
        latency_ms=0,
    )


def test_sp_analysis_options_default_to_high_quality_ai_hybrid() -> None:
    request = SPAnalysisRequest.model_validate(
        {
            "dbProfileId": "master",
            "target": {
                "type": "PROCEDURE",
                "schema": "dbo",
                "name": "usp_OrderRequest_Select",
            },
            "outputs": ["SP_ANALYSIS_DOCUMENT"],
        }
    )

    assert request.options.use_llm_analysis is True
    assert request.options.use_ai_tool_orchestration is True
    assert request.options.use_platform_tool_orchestration is True
    assert request.options.allow_sp_definition_to_model is True
    assert request.options.source_context_mode == "RETRIEVED_SPANS"
    assert request.options.source_dependency_mode == "CONFIRMED_PROCEDURES"
    assert request.options.llm_profile_id == "openai_sp_semantic_analysis"


def test_llm_prompt_uses_retrieved_source_context_without_full_definition() -> None:
    class SourceContextSpyGateway:
        def __init__(self) -> None:
            self.prompt_payloads: list[dict] = []

        def invoke_semantic_analysis(self, *, prompt, profile) -> ModelInvocationRecord:
            payload = json.loads(prompt.user_prompt)
            self.prompt_payloads.append(payload)
            assert "sourceContext" in payload
            assert payload["sourceContextIncluded"] is True
            assert payload["procedureDefinitionIncluded"] is False
            assert "procedureDefinition" not in payload
            assert "selectedSpans" in payload["sourceContext"]
            evidence_refs = payload["evidenceRefContract"]["allowedFactIds"]
            ref = evidence_refs[0] if evidence_refs else "metadata.procedureDefinitionHash"
            structured_output = {
                "businessRules": [
                        {
                            "category": "SOURCE_CONTEXT_BOUND_RULE",
                            "summary": "선택된 source span을 transient context로 사용했습니다.",
                            "status": "INFERRED_DESCRIPTION",
                            "evidenceRefs": [ref],
                        }
                ],
                "modernizationPoints": [],
                "riskFlags": [],
                "reviewMarkers": [],
                "conversionGuidance": [],
                "migrationGuideInsights": [],
                "assumptions": [],
            }
            return _model_invocation(
                prompt=prompt,
                profile=profile,
                provider="spy-source-context",
                structured_output=structured_output,
            )

    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository, model_gateway=SourceContextSpyGateway())

    _request_record, job = service.submit_sp_analysis(_llm_request(["SP_ANALYSIS_DOCUMENT"]))

    run = repository.list_agent_runs(job.job_id)[0]
    metadata = next(iter(repository.metadata_collections.values()))
    artifact = next(iter(repository.artifacts.values()))

    assert run.model_invocation["sourceContextSummary"]["mode"] == "RETRIEVED_SPANS"
    assert run.model_invocation["analysisCoverage"]["spanCount"] > 0
    assert "CREATE PROCEDURE" not in str(metadata.payload)
    assert "CREATE PROCEDURE" not in artifact.content


def test_confirmed_dependency_procedure_creates_child_agent_run_and_reduces_root() -> None:
    class MultiSpSpyGateway:
        def __init__(self) -> None:
            self.prompt_payloads: list[dict] = []

        def invoke_semantic_analysis(self, *, prompt, profile) -> ModelInvocationRecord:
            payload = json.loads(prompt.user_prompt)
            self.prompt_payloads.append(payload)
            assert payload["procedureDefinitionIncluded"] is False
            assert "procedureDefinition" not in payload
            ref = (payload["evidenceRefContract"]["allowedFactIds"] or ["metadata.snapshot"])[0]
            target_ref = payload["targetRef"]
            structured_output = {
                "businessRules": [
                    {
                        "category": f"RULE_{target_ref.replace('.', '_')}",
                        "summary": f"{target_ref} semantic child/root 분석 결과입니다.",
                        "status": "INFERRED_DESCRIPTION",
                        "evidenceRefs": [ref],
                    }
                ],
                "modernizationPoints": [],
                "riskFlags": [],
                "reviewMarkers": [],
                "conversionGuidance": [],
                "migrationGuideInsights": [],
                "assumptions": [],
            }
            return _model_invocation(
                prompt=prompt,
                profile=profile,
                provider="spy-multi-sp",
                structured_output=structured_output,
            )

    repository = MemoryWorkflowRepository()
    spy_gateway = MultiSpSpyGateway()
    service = WorkflowService(repository, model_gateway=spy_gateway)
    request = SPAnalysisRequest.model_validate(
        {
            "dbProfileId": "master",
            "target": {
                "type": "PROCEDURE",
                "schema": "dbo",
                "name": "usp_ProcessOrderBatch",
            },
            "outputs": ["SP_ANALYSIS_DOCUMENT", "DEPENDENCY_REPORT", "JAVA_MYBATIS_DRAFT"],
            "options": {
                "includeEvidenceRefs": True,
                "useLlmAnalysis": True,
                "llmProfileId": "openai_fast_test",
                "allowSpDefinitionToModel": True,
            },
        }
    )

    _request_record, job = service.submit_sp_analysis(request)

    runs = repository.list_agent_runs(job.job_id)
    assert job.status == JobStatus.VALIDATION_COMPLETE
    assert runs is not None
    child_runs = [run for run in runs if run.agent_type == "LLM_SEMANTIC_ANALYST_DEPENDENCY"]
    root_runs = [run for run in runs if run.agent_type == "LLM_SEMANTIC_ANALYST"]
    assert {run.target_ref for run in child_runs} == {
        "OtherDB.dbo.usp_CrossDbOrderAudit",
        "dbo.usp_GetOrderSummary",
    }
    root_run = root_runs[0]
    dependency_summary = root_run.model_invocation["sourceContextSummary"]["dependencyAnalysis"]
    assert dependency_summary["analyzedCount"] == 2
    assert dependency_summary["childRunCount"] == 2
    assert dependency_summary["skippedCount"] >= 1
    assert any(
        item["code"] == "CALLED_PROCEDURE_STRATEGY_DBO_USP_GETORDERSUMMARY"
        for item in root_run.structured_output["conversionGuidance"]
    )
    assert any(
        item["code"] == "CALLED_PROCEDURE_STRATEGY_OTHERDB_DBO_USP_CROSSDBORDERAUDIT"
        for item in root_run.structured_output["conversionGuidance"]
    )
    combined_storage = (
        str([run.model_invocation for run in runs])
        + str([run.structured_output for run in runs])
        + str([artifact.content for artifact in repository.artifacts.values()])
    )
    assert "CREATE PROCEDURE" not in combined_storage
    assert "procedureDefinition" not in str(root_run.model_invocation)
    assert any(
        payload["targetRef"] == "dbo.usp_GetOrderSummary"
        for payload in spy_gateway.prompt_payloads
    )
    assert any(
        payload["targetRef"] == "OtherDB.dbo.usp_CrossDbOrderAudit"
        for payload in spy_gateway.prompt_payloads
    )


def test_dependency_child_context_error_records_failed_child_and_keeps_root_complete() -> None:
    class ChildFailureGateway:
        def invoke_semantic_analysis(self, *, prompt, profile) -> ModelInvocationRecord:
            payload = json.loads(prompt.user_prompt)
            if payload["targetRef"] == "dbo.usp_GetOrderSummary":
                raise ModelGatewayError(
                    "Input exceeded provider limit.",
                    code="context_length_exceeded",
                    provider_error={"code": "context_length_exceeded"},
                )
            ref = (payload["evidenceRefContract"]["allowedFactIds"] or ["metadata.snapshot"])[0]
            structured_output = {
                "businessRules": [
                    {
                        "category": "ROOT_RULE",
                        "summary": "root 분석은 계속 진행되었습니다.",
                        "status": "INFERRED_DESCRIPTION",
                        "evidenceRefs": [ref],
                    }
                ],
                "modernizationPoints": [],
                "riskFlags": [],
                "reviewMarkers": [],
                "conversionGuidance": [],
                "migrationGuideInsights": [],
                "assumptions": [],
            }
            return _model_invocation(
                prompt=prompt,
                profile=profile,
                provider="spy-child-failure",
                structured_output=structured_output,
            )

    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository, model_gateway=ChildFailureGateway())
    request = SPAnalysisRequest.model_validate(
        {
            "dbProfileId": "master",
            "target": {
                "type": "PROCEDURE",
                "schema": "dbo",
                "name": "usp_ProcessOrderBatch",
            },
            "outputs": ["SP_ANALYSIS_DOCUMENT"],
            "options": {
                "includeEvidenceRefs": True,
                "useLlmAnalysis": True,
                "llmProfileId": "openai_fast_test",
                "allowSpDefinitionToModel": True,
            },
        }
    )

    _request_record, job = service.submit_sp_analysis(request)

    runs = repository.list_agent_runs(job.job_id)
    assert job.status == JobStatus.VALIDATION_COMPLETE
    assert runs is not None
    assert any(
        run.agent_type == "LLM_SEMANTIC_ANALYST_DEPENDENCY"
        and run.status == AgentRunStatus.FAILED.value
        for run in runs
    )
    root_run = next(run for run in runs if run.agent_type == "LLM_SEMANTIC_ANALYST")
    assert any(
        marker["code"] == "DEPENDENCY_SEMANTIC_ANALYSIS_INCOMPLETE"
        for marker in root_run.structured_output["reviewMarkers"]
    )


def test_dependency_selector_keeps_confirmed_same_profile_and_safe_cross_db_procedures() -> None:
    evidence = {
        "rootObject": {
            "database": "master",
            "schema": "dbo",
            "name": "usp_Root",
            "objectType": "PROCEDURE",
        },
        "nodes": [
            {
                "id": "master.dbo.usp_Root:PROCEDURE",
                "database": "master",
                "schema": "dbo",
                "name": "usp_Root",
                "objectType": "PROCEDURE",
                "reviewStatus": "CONFIRMED",
                "evidenceRefs": [{"objectRef": "dbo.usp_Root", "locator": "fixture#/root"}],
            },
            {
                "id": "master.dbo.usp_Child:PROCEDURE",
                "database": "master",
                "schema": "dbo",
                "name": "usp_Child",
                "objectType": "PROCEDURE",
                "reviewStatus": "CONFIRMED",
                "evidenceRefs": [{"objectRef": "dbo.usp_Child", "locator": "fixture#/child"}],
            },
            {
                "id": "OtherDb.dbo.usp_CrossDb:PROCEDURE",
                "database": "OtherDb",
                "schema": "dbo",
                "name": "usp_CrossDb",
                "objectType": "PROCEDURE",
                "sourceScope": "SAME_SERVER_CROSS_DATABASE",
                "reviewStatus": "CONFIRMED",
                "evidenceRefs": [{"objectRef": "dbo.usp_CrossDb", "locator": "fixture#/cross"}],
            },
            {
                "id": "UnsafeDb.dbo.usp_UnsafeCrossDb:PROCEDURE",
                "database": "UnsafeDb",
                "schema": "dbo",
                "name": "usp_UnsafeCrossDb",
                "objectType": "PROCEDURE",
                "reviewStatus": "CONFIRMED",
                "evidenceRefs": [
                    {"objectRef": "dbo.usp_UnsafeCrossDb", "locator": "fixture#/unsafe"}
                ],
            },
        ],
        "edges": [
            {
                "from": "master.dbo.usp_Root:PROCEDURE",
                "to": "master.dbo.usp_Child:PROCEDURE",
                "resolutionStatus": "CONFIRMED",
                "resolutionStrategy": "CATALOG_OBJECT_ID",
                "evidenceRefs": [{"objectRef": "dbo.usp_Root", "locator": "fixture#/edge1"}],
            },
            {
                "from": "master.dbo.usp_Root:PROCEDURE",
                "to": "OtherDb.dbo.usp_CrossDb:PROCEDURE",
                "resolutionStatus": "CONFIRMED",
                "resolutionStrategy": "SAME_SERVER_CROSS_DATABASE_CATALOG",
                "resolutionConfidence": "HIGH",
                "evidenceRefs": [{"objectRef": "dbo.usp_Root", "locator": "fixture#/edge2"}],
            },
            {
                "from": "master.dbo.usp_Root:PROCEDURE",
                "to": "UnsafeDb.dbo.usp_UnsafeCrossDb:PROCEDURE",
                "resolutionStatus": "CONFIRMED",
                "resolutionStrategy": "CATALOG_OBJECT_ID",
                "evidenceRefs": [{"objectRef": "dbo.usp_Root", "locator": "fixture#/edge3"}],
            },
        ],
        "unresolved": [
            {
                "dependencyType": "DYNAMIC_SQL",
                "resolutionStrategy": "DYNAMIC_SQL_PATTERN",
                "evidenceRefs": [{"objectRef": "dynamic", "locator": "fixture#/dynamic"}],
            }
        ],
    }

    candidates, skipped = dependency_procedure_candidates(
        evidence,
        max_depth=2,
        max_tasks=8,
    )

    assert [candidate.target_ref for candidate in candidates] == [
        "OtherDb.dbo.usp_CrossDb",
        "dbo.usp_Child",
    ]
    cross_db = next(
        candidate for candidate in candidates if candidate.target_ref == "OtherDb.dbo.usp_CrossDb"
    )
    assert cross_db.database == "OtherDb"
    assert cross_db.source_scope == "SAME_SERVER_CROSS_DATABASE"
    reasons = {item["reason"] for item in skipped}
    assert "CROSS_DATABASE_DEFINITION_UNSUPPORTED" in reasons
    assert "DYNAMIC_SQL_REVIEW_REQUIRED" in reasons


def test_submit_runs_initial_workflow_and_exposes_persisted_artifact_types() -> None:
    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)

    request_record, job = service.submit_sp_analysis(_request())

    assert request_record.status == JobStatus.VALIDATION_COMPLETE
    assert job.status == JobStatus.VALIDATION_COMPLETE
    assert [status.value for status, _step in job.transitions] == [
        "COLLECTING_METADATA",
        "ANALYZING",
        "GENERATING",
        "VALIDATING",
        "VALIDATION_COMPLETE",
    ]

    artifact_types = {artifact.type for artifact in repository.artifacts.values()}
    assert ArtifactType.SP_ANALYSIS_DOC in artifact_types
    assert ArtifactType.DEPENDENCY_REPORT in artifact_types
    assert ArtifactType.DTO_DRAFT in artifact_types
    assert ArtifactType.SERVICE_DRAFT in artifact_types
    assert ArtifactType.MAPPER_INTERFACE in artifact_types
    assert ArtifactType.MAPPER_XML in artifact_types
    public_types = {artifact.type.value for artifact in repository.artifacts.values()}
    assert "JAVA_MYBATIS_DRAFT" not in public_types
    assert all(artifact.latest_validation_report_id for artifact in repository.artifacts.values())
    assert repository.audit_events
    assert any(event.action == "METADATA_COLLECTED" for event in repository.audit_events)
    artifact_created = [
        event for event in repository.audit_events if event.action == "ARTIFACT_CREATED"
    ]
    assert len(artifact_created) == len(repository.artifacts)
    assert all(event.payload["stage"] == "ARTIFACT" for event in artifact_created)
    assert all(event.payload["targetRef"]["type"] == "ARTIFACT" for event in artifact_created)


def test_generated_artifact_assumptions_are_deduped() -> None:
    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)

    service.submit_sp_analysis(_request())

    assert repository.artifacts
    for artifact in repository.artifacts.values():
        assert len(artifact.assumptions) == len(set(artifact.assumptions))
        assert artifact.assumptions.count(WORKFLOW_METADATA_NOTE) == 1


def test_submit_with_llm_records_sanitized_agent_run_and_llm_evidence() -> None:
    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)

    _request_record, job = service.submit_sp_analysis(_llm_request())

    agent_runs = repository.list_agent_runs(job.job_id)
    assert agent_runs is not None
    assert len(agent_runs) == 1
    run = agent_runs[0]
    assert run.agent_type == "LLM_SEMANTIC_ANALYST"
    assert run.model_invocation["model"] == model_profile_from_env("openai_fast_test").model
    assert run.model_invocation["componentInvocations"]
    assert any(
        component["stage"] == "platform_tool_execution"
        for component in run.model_invocation["componentInvocations"]
    )
    assert "businessRules" in run.structured_output
    assert "CREATE PROCEDURE" not in str(run.model_invocation)
    assert "CREATE PROCEDURE" not in str(run.structured_output)
    assert "CREATE PROCEDURE" not in str(repository.metadata_collections)
    metadata = next(iter(repository.metadata_collections.values()))
    assert metadata.payload["platformToolEvidence"]["toolCallCount"] == 1
    assert metadata.payload["platformToolEvidence"]["toolResults"][0]["factId"].startswith(
        "platform.list_registry_versions."
    )
    assert any(
        ref["type"] == "LLM_INFERENCE"
        for artifact in repository.artifacts.values()
        for ref in artifact.evidence_refs
    )
    assert any(event.action == "AGENT_RUN_RECORDED" for event in repository.audit_events)


def test_submit_with_llm_records_failed_agent_run_when_gateway_fails() -> None:
    class FailingGateway:
        provider = "pgpt"

        def invoke_semantic_analysis(self, *, prompt, profile) -> ModelInvocationRecord:
            raise ModelGatewayError(
                "OpenAI response did not match the required structured output schema.",
                code="OPENAI_STRUCTURED_OUTPUT_INVALID",
                provider_error={
                    "type": "invalid_request_error",
                    "code": "context_length_exceeded",
                    "param": "input",
                    "message": "Input exceeded provider limit.",
                },
            )

    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository, model_gateway=FailingGateway())

    _request_record, job = service.submit_sp_analysis(_llm_request())

    assert job.status == JobStatus.FAILED
    runs = repository.list_agent_runs(job.job_id)
    assert runs is not None
    assert len(runs) == 1
    run = runs[0]
    assert run.status == AgentRunStatus.FAILED.value
    assert run.model_invocation["provider"] == "pgpt"
    assert run.model_invocation["status"] == AgentRunStatus.FAILED.value
    assert run.model_invocation["componentInvocations"][0]["errorCode"] == (
        "OPENAI_STRUCTURED_OUTPUT_INVALID"
    )
    assert run.model_invocation["componentInvocations"][0]["providerError"] == {
        "type": "invalid_request_error",
        "code": "context_length_exceeded",
        "param": "input",
        "message": "Input exceeded provider limit.",
    }
    assert "raw_openai_response_text" not in str(run.model_invocation)
    assert any(event.action == "AGENT_RUN_RECORDED" for event in repository.audit_events)


def test_llm_prompt_receives_dependency_evidence_and_can_bind_claim_refs() -> None:
    class DependencyEvidenceSpyGateway:
        def __init__(self) -> None:
            self.prompt_payloads: list[dict] = []
            self.dependency_fact_refs: list[str] = []

        def invoke_semantic_analysis(self, *, prompt, profile) -> ModelInvocationRecord:
            prompt_payload = json.loads(prompt.user_prompt)
            self.prompt_payloads.append(prompt_payload)
            dependency_evidence = prompt_payload["metadata"]["dependencyEvidence"]
            assert dependency_evidence["toolName"] == "get_dependency_closure"
            assert dependency_evidence["evidenceRefs"]
            assert "definition" not in prompt_payload["metadata"]["procedureDefinition"]
            fact_ref = next(
                ref
                for ref in prompt_payload["evidenceRefContract"]["allowedFactIds"]
                if "dependencies" in ref
            )
            self.dependency_fact_refs.append(fact_ref)
            structured_output = {
                "businessRules": [
                    {
                        "category": "DEPENDENCY_EVIDENCE_BOUND_RULE",
                        "summary": "의존성 closure 근거가 semantic claim에 연결되었습니다.",
                        "status": "INFERRED_DESCRIPTION",
                        "evidenceRefs": [fact_ref],
                    }
                ],
                "modernizationPoints": [],
                "riskFlags": [],
                "reviewMarkers": [],
                "conversionGuidance": [],
                "migrationGuideInsights": [],
                "assumptions": [],
            }
            return ModelInvocationRecord(
                provider="spy",
                model=profile.model,
                model_profile_id=profile.profile_id,
                model_registry_ref=profile.registry_ref,
                reasoning_effort=profile.reasoning_effort,
                prompt_version=prompt.prompt_version,
                output_schema_version=prompt.output_schema_version,
                input_hash=prompt.input_hash,
                prompt_hash=prompt.prompt_hash,
                output_hash=stable_json_hash(structured_output),
                status=AgentRunStatus.SUCCEEDED,
                structured_output=structured_output,
                token_usage={"inputTokens": 0, "outputTokens": 0, "totalTokens": 0},
                latency_ms=0,
            )

    repository = MemoryWorkflowRepository()
    spy_gateway = DependencyEvidenceSpyGateway()
    service = WorkflowService(repository, model_gateway=spy_gateway)
    request = SPAnalysisRequest.model_validate(
        {
            "dbProfileId": "master",
            "target": {
                "type": "PROCEDURE",
                "schema": "dbo",
                "name": "usp_ProcessOrderBatch",
            },
            "outputs": ["SP_ANALYSIS_DOCUMENT"],
            "options": {
                "includeEvidenceRefs": True,
                "useLlmAnalysis": True,
                "llmProfileId": "openai_fast_test",
                "allowSpDefinitionToModel": False,
            },
        }
    )

    _request_record, job = service.submit_sp_analysis(request)

    run = repository.list_agent_runs(job.job_id)[0]
    artifact = next(iter(repository.artifacts.values()))
    assert spy_gateway.prompt_payloads
    assert spy_gateway.dependency_fact_refs
    assert run.structured_output["businessRules"][0]["evidenceRefs"] == [
        spy_gateway.dependency_fact_refs[0]
    ]
    assert "의존성 closure 근거가 semantic claim에 연결되었습니다." in artifact.content
    assert "dependencyEvidence" in spy_gateway.prompt_payloads[0]["metadata"]


def test_ai_tool_orchestration_invokes_internal_read_only_tool_and_binds_fact_ref(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class ToolPlanningSpyGateway:
        def __init__(self) -> None:
            self.planner_prompts: list[dict] = []
            self.semantic_prompts: list[dict] = []
            self.ai_tool_fact_refs: list[str] = []

        def plan_metadata_tools(self, *, prompt, profile) -> ModelInvocationRecord:
            payload = json.loads(prompt.user_prompt)
            self.planner_prompts.append(payload)
            assert any(
                tool["name"] == "get_table_schema"
                for tool in payload["toolCapabilities"]
            )
            structured_output = {
                "toolRequests": [],
                "assumptions": [],
                "reviewMarkers": [],
            }
            if payload["round"] == 1:
                structured_output["toolRequests"].append(
                    {
                        "toolName": "get_table_schema",
                        "arguments": {
                            "dbProfileId": "master",
                            "schema": "dbo",
                            "tableName": "TB_ORDER",
                            "topK": 99,
                        },
                        "reason": "Need table columns for semantic claims.",
                        "expectedEvidenceUse": "Anchor result-shape guidance.",
                    }
                )
            return _model_invocation(
                prompt=prompt,
                profile=profile,
                provider="spy-planner",
                structured_output=structured_output,
            )

        def invoke_semantic_analysis(self, *, prompt, profile) -> ModelInvocationRecord:
            payload = json.loads(prompt.user_prompt)
            self.semantic_prompts.append(payload)
            ai_tool_evidence = payload["metadata"]["aiToolEvidence"]
            assert ai_tool_evidence["toolResults"]
            assert "definition" not in str(ai_tool_evidence).lower()
            assert "CREATE PROCEDURE" not in str(ai_tool_evidence)
            fact_ref = next(
                ref
                for ref in payload["evidenceRefContract"]["allowedFactIds"]
                if ref.startswith("mcp.get_table_schema.")
            )
            self.ai_tool_fact_refs.append(fact_ref)
            structured_output = {
                "businessRules": [
                    {
                        "category": "AI_TOOL_SCHEMA_BOUND_RULE",
                        "summary": "AI-selected table schema evidence anchored this claim.",
                        "status": "INFERRED_DESCRIPTION",
                        "evidenceRefs": [fact_ref],
                    }
                ],
                "modernizationPoints": [],
                "riskFlags": [],
                "reviewMarkers": [],
                "conversionGuidance": [],
                "migrationGuideInsights": [],
                "assumptions": [],
            }
            return _model_invocation(
                prompt=prompt,
                profile=profile,
                provider="spy-semantic",
                structured_output=structured_output,
            )

    class InternalRegistrySpy:
        def __init__(self) -> None:
            self.calls: list[tuple[str, dict]] = []

        def invoke_payload(self, tool_name: str, payload: dict) -> dict:
            arguments = payload["arguments"]
            self.calls.append((tool_name, dict(arguments)))
            return {
                "ok": True,
                "toolName": tool_name,
                "dbProfileId": arguments["dbProfileId"],
                "snapshotId": "fixture:ai-tool",
                "collectedAt": "2026-05-12T00:00:00Z",
                "evidenceRefs": [
                    {
                        "id": "evt_table_schema",
                        "source": "fixture",
                        "path": "fixtures/mcp/metadata_snapshot.json#/tables/TB_ORDER",
                        "objectType": "TABLE",
                        "objectName": "dbo.TB_ORDER",
                    }
                ],
                "data": {
                    "schema": arguments["schema"],
                    "tableName": arguments["tableName"],
                    "columns": [{"name": "OrderId", "dataType": "int"}],
                    "definition": "CREATE PROCEDURE dbo.ShouldNotPersist AS SELECT 1",
                },
            }

    registry = InternalRegistrySpy()
    monkeypatch.setattr(
        "api_app.ai_tool_orchestrator.build_tool_registry",
        lambda **_kwargs: registry,
    )
    repository = MemoryWorkflowRepository()
    gateway = ToolPlanningSpyGateway()
    service = WorkflowService(repository, model_gateway=gateway)
    request = SPAnalysisRequest.model_validate(
        {
            "dbProfileId": "master",
            "target": {
                "type": "PROCEDURE",
                "schema": "dbo",
                "name": "usp_GetOrderSummary",
            },
            "outputs": ["SP_ANALYSIS_DOCUMENT"],
            "options": {
                "includeEvidenceRefs": True,
                "useLlmAnalysis": True,
                "useAiToolOrchestration": True,
                "llmProfileId": "openai_fast_test",
                "allowSpDefinitionToModel": False,
            },
        }
    )

    _request_record, job = service.submit_sp_analysis(request)

    run = repository.list_agent_runs(job.job_id)[0]
    metadata = next(iter(repository.metadata_collections.values()))
    artifact = next(iter(repository.artifacts.values()))
    assert registry.calls == [
        (
            "get_table_schema",
            {
                "dbProfileId": "master",
                "schema": "dbo",
                "tableName": "TB_ORDER",
                "topK": 20,
            },
        )
    ]
    assert metadata.payload["aiToolEvidence"]["toolCallCount"] == 1
    assert metadata.payload["aiToolEvidence"]["plannerMetrics"]["executedToolCallCount"] == 1
    assert metadata.payload["aiToolEvidence"]["plannerMetrics"]["supportedClaimCount"] >= 1
    assert "definition" not in str(metadata.payload["aiToolEvidence"]).lower()
    assert "CREATE PROCEDURE" not in str(metadata.payload)
    assert run.structured_output["businessRules"][0]["evidenceRefs"] == [
        gateway.ai_tool_fact_refs[0]
    ]
    assert any(
        component["stage"] == "ai_tool_execution"
        and component["toolName"] == "get_table_schema"
        and component["status"] == "SUCCEEDED"
        for component in run.model_invocation["componentInvocations"]
    )
    assert "AI-selected table schema evidence anchored this claim." in artifact.content


def test_ai_tool_orchestration_blocks_adversarial_tool_plan_without_storing_raw_args() -> None:
    class AdversarialPlanningGateway:
        def plan_metadata_tools(self, *, prompt, profile) -> ModelInvocationRecord:
            structured_output = {
                "toolRequests": [
                    {
                        "toolName": "get_table_schema",
                        "arguments": {
                            "dbProfileId": "master",
                            "schema": "dbo",
                            "tableName": "TB_ORDER",
                            "sql": "DROP TABLE dbo.TB_ORDER",
                            "password": "supersecret",
                        },
                        "reason": "malicious request",
                        "expectedEvidenceUse": "should be blocked",
                    }
                ],
                "assumptions": [],
                "reviewMarkers": [],
            }
            return _model_invocation(
                prompt=prompt,
                profile=profile,
                provider="spy-planner",
                structured_output=structured_output,
            )

        def invoke_semantic_analysis(self, *, prompt, profile) -> ModelInvocationRecord:
            structured_output = {
                "businessRules": [],
                "modernizationPoints": [],
                "riskFlags": [],
                "reviewMarkers": [],
                "conversionGuidance": [],
                "migrationGuideInsights": [],
                "assumptions": [],
            }
            return _model_invocation(
                prompt=prompt,
                profile=profile,
                provider="spy-semantic",
                structured_output=structured_output,
            )

    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository, model_gateway=AdversarialPlanningGateway())

    _request_record, job = service.submit_sp_analysis(_llm_request(["SP_ANALYSIS_DOCUMENT"]))

    metadata = next(iter(repository.metadata_collections.values()))
    run = repository.list_agent_runs(job.job_id)[0]
    stored_text = str(metadata.payload) + str(run.model_invocation) + str(run.structured_output)
    assert metadata.payload["aiToolEvidence"]["blockedRequests"]
    assert metadata.payload["aiToolEvidence"]["plannerMetrics"]["blockedRequestCount"] == 1
    assert metadata.payload["aiToolEvidence"]["reviewMarkers"][0]["code"] == (
        "AI_TOOL_ORCHESTRATION_REVIEW_REQUIRED"
    )
    assert "DROP TABLE" not in stored_text
    assert "supersecret" not in stored_text
    assert any(
        marker["code"] == "AI_TOOL_ORCHESTRATION_REVIEW_REQUIRED"
        for marker in run.structured_output["reviewMarkers"]
    )


def test_remote_high_quality_requires_openai_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_ENABLE_REMOTE", "1")
    monkeypatch.setenv("LLM_ALLOW_SP_TEXT", "1")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)

    request_record, job = service.submit_sp_analysis(_request(["SP_ANALYSIS_DOCUMENT"]))

    assert request_record.status == JobStatus.FAILED
    assert job.status == JobStatus.FAILED
    assert job.error_code == "OPENAI_API_KEY_MISSING"
    assert "OPENAI_API_KEY" in str(job.error_message)


def test_remote_high_quality_requires_sp_text_gate(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_ENABLE_REMOTE", "1")
    monkeypatch.setenv("OPENAI_API_KEY", "test-only-key")
    monkeypatch.delenv("LLM_ALLOW_SP_TEXT", raising=False)
    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)

    request_record, job = service.submit_sp_analysis(_request(["SP_ANALYSIS_DOCUMENT"]))

    assert request_record.status == JobStatus.FAILED
    assert job.status == JobStatus.FAILED
    assert job.error_code == "LLM_SP_TEXT_NOT_ALLOWED"
    assert "LLM_ALLOW_SP_TEXT=1" in str(job.error_message)


def test_submit_replays_same_idempotency_key_for_same_payload() -> None:
    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)

    first_request, first_job = service.submit_sp_analysis(
        _request(),
        tracking=RequestTrackingContext(
            correlation_id="corr-submit-1",
            idempotency_key="idem-p09-same",
        ),
    )
    replay_request, replay_job = service.submit_sp_analysis(
        _request(),
        tracking=RequestTrackingContext(
            correlation_id="corr-submit-2",
            idempotency_key="idem-p09-same",
        ),
    )

    assert replay_request.request_id == first_request.request_id
    assert replay_job.job_id == first_job.job_id
    assert len(repository.requests) == 1
    assert repository.requests[first_request.request_id].request_hash
    assert repository.requests[first_request.request_id].idempotency_key == "idem-p09-same"
    replay_audit = repository.audit_events[-1]
    assert replay_audit.action == "IDEMPOTENT_REQUEST_REPLAYED"
    assert replay_audit.correlation_id == "corr-submit-2"


def test_submit_rejects_idempotency_key_reused_for_different_payload() -> None:
    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)

    service.submit_sp_analysis(
        _request(["SP_ANALYSIS_DOCUMENT"]),
        tracking=RequestTrackingContext(
            correlation_id="corr-submit",
            idempotency_key="idem-p09-conflict",
        ),
    )

    with pytest.raises(IdempotencyConflictError, match="different request payload"):
        service.submit_sp_analysis(
            _request(["DEPENDENCY_REPORT"]),
            tracking=RequestTrackingContext(
                correlation_id="corr-submit",
                idempotency_key="idem-p09-conflict",
            ),
        )


def test_tracking_context_is_carried_to_request_job_and_audit_payloads() -> None:
    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)

    request_record, job = service.submit_sp_analysis(
        _request(["SP_ANALYSIS_DOCUMENT"]),
        tracking=RequestTrackingContext(
            correlation_id="corr-p09-trace",
            idempotency_key="idem-p09-trace",
        ),
    )

    assert request_record.correlation_id == "corr-p09-trace"
    assert job.correlation_id == "corr-p09-trace"
    assert any(
        event.payload.get("tracking", {}).get("correlationId") == "corr-p09-trace"
        for event in repository.audit_events
    )
    assert all("stage" in event.payload for event in repository.audit_events)
    assert all("actor" in event.payload for event in repository.audit_events)
    assert all("targetRef" in event.payload for event in repository.audit_events)
    assert all(event.audit_id.startswith("audit_") for event in repository.audit_events)


def test_repository_rejects_unsupported_job_transition() -> None:
    repository = MemoryWorkflowRepository()
    request = repository.create_request(
        db_profile_id="master",
        target={"type": "PROCEDURE", "schema": "dbo", "name": "usp_demo"},
        outputs=("SP_ANALYSIS_DOCUMENT",),
        options={},
        request_hash="hash",
        correlation_id="corr-invalid-transition",
        idempotency_key=None,
    )
    job = repository.create_job(
        request.request_id,
        correlation_id=request.correlation_id,
    )

    with pytest.raises(WorkflowStateError, match="Unsupported job transition"):
        repository.transition_job(
            job.job_id,
            status=JobStatus.GENERATING,
            current_step=WorkflowStepType.GENERATE,
        )


def test_validation_complete_is_terminal_job_status() -> None:
    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)
    _request_record, job = service.submit_sp_analysis(_request(["SP_ANALYSIS_DOCUMENT"]))

    with pytest.raises(WorkflowStateError, match="terminal status VALIDATION_COMPLETE"):
        repository.transition_job(
            job.job_id,
            status=JobStatus.CANCELED,
            current_step=WorkflowStepType.VALIDATE,
        )


def test_memory_repository_fail_job_persists_error_state_and_request_status() -> None:
    repository = MemoryWorkflowRepository()
    request = repository.create_request(
        db_profile_id="master",
        target={"type": "PROCEDURE", "schema": "dbo", "name": "usp_demo"},
        outputs=("SP_ANALYSIS_DOCUMENT",),
        options={},
        request_hash="hash-fail-job",
        correlation_id="corr-fail-job",
        idempotency_key=None,
    )
    job = repository.create_job(request.request_id, correlation_id=request.correlation_id)

    failed = repository.fail_job(
        job.job_id,
        code="TEST_FAILURE",
        message="metadata fixture unavailable",
    )

    stored = repository.get_job(job.job_id)
    assert failed.status == JobStatus.FAILED
    assert failed.error_code == "TEST_FAILURE"
    assert stored is not None
    assert stored.status == JobStatus.FAILED
    assert stored.error_code == "TEST_FAILURE"
    assert stored.error_message == "metadata fixture unavailable"
    assert repository.requests[request.request_id].status == JobStatus.FAILED
    audit = repository.audit_events[-1]
    assert audit.action == "JOB_FAILED"
    assert audit.payload["stage"] == "JOB"
    assert audit.payload["code"] == "TEST_FAILURE"


def test_artifact_publish_state_blocks_validation_and_approval_mutation() -> None:
    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)
    service.submit_sp_analysis(_request(["SP_ANALYSIS_DOCUMENT"]))
    artifact = next(iter(repository.artifacts.values()))
    artifact.status = ArtifactStatus.PUBLISHED

    with pytest.raises(WorkflowStateError, match="publish transitions are blocked"):
        service.validate_artifact(artifact.artifact_id)

    with pytest.raises(WorkflowStateError, match="publish transitions are blocked"):
        service.record_approval_decision(
            artifact_id=artifact.artifact_id,
            decision="REQUEST_CHANGES",
            reviewer="reviewer@example.com",
            comment="must stay draft gated",
            validation_report_id=artifact.latest_validation_report_id,
        )


def test_requested_output_placeholders_use_persisted_artifact_enums() -> None:
    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)

    service.submit_sp_analysis(_request(["TABLE_COLUMN_METADATA", "DTO_MODEL_DRAFT", "DDL_DRAFT"]))

    assert {artifact.type for artifact in repository.artifacts.values()} == {
        ArtifactType.METADATA_QUERY_RESULT,
        ArtifactType.DTO_DRAFT,
        ArtifactType.VO_DRAFT,
        ArtifactType.MODEL_DRAFT,
        ArtifactType.DDL_DRAFT,
    }
    assert all("REVIEW_REQUIRED" in artifact.content for artifact in repository.artifacts.values())


def test_fixture_metadata_shapes_generation_context_and_metadata_artifact() -> None:
    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)

    _request_record, job = service.submit_sp_analysis(
        _fixture_request(
            ["SP_ANALYSIS_DOCUMENT", "DEPENDENCY_REPORT", "TABLE_COLUMN_METADATA"]
        )
    )

    assert [status.value for status, _step in job.transitions] == [
        "COLLECTING_METADATA",
        "ANALYZING",
        "GENERATING",
        "VALIDATING",
        "VALIDATION_COMPLETE",
    ]
    assert {artifact.type for artifact in repository.artifacts.values()} == {
        ArtifactType.SP_ANALYSIS_DOC,
        ArtifactType.DEPENDENCY_REPORT,
        ArtifactType.METADATA_QUERY_RESULT,
    }
    artifact_type_values = {artifact.type.value for artifact in repository.artifacts.values()}
    assert "DEPENDENCY_EVIDENCE" not in artifact_type_values

    metadata = next(iter(repository.metadata_collections.values()))
    assert metadata.payload["snapshotId"] == "mcp-fixture-snapshot-0001"
    dependency_evidence = metadata.payload["dependencyEvidence"]
    assert dependency_evidence["toolName"] == "get_dependency_closure"
    assert dependency_evidence["summary"]["reviewRequiredCount"] >= 1
    assert dependency_evidence["unresolved"]
    assert "definition" not in str(dependency_evidence).lower()
    assert "sqltext" not in str(dependency_evidence).replace("_", "").lower()
    assert "rowdata" not in str(dependency_evidence).replace("_", "").lower()
    assert "resolve_dependency_reference" not in str(metadata.payload)

    contents = "\n".join(artifact.content for artifact in repository.artifacts.values())
    assert "dbo.TB_ORDER" in contents
    assert "Order identifier" in contents
    assert "OrderId" in contents
    assert "dependency_closure_evidence" in contents
    assert "## metadata_extraction_appendix" in contents
    assert "definition_hash_length" in contents
    assert "### 확인됨" in contents
    assert "### 검증 필요" in contents
    assert "| 테이블 | SELECT | INSERT | UPDATE | DELETE | MERGE |" in contents
    assert "DYNAMIC_SQL_SIGNAL" in contents
    assert "FIXTURE_AMBIGUOUS" in contents
    assert "resolve_dependency_reference" not in contents
    assert any(
        "dependencies" in ref["locator"]
        for artifact in repository.artifacts.values()
        for ref in artifact.evidence_refs
    )


def test_approve_requires_latest_passed_validation_report() -> None:
    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)
    service.submit_sp_analysis(_request(["SP_ANALYSIS_DOCUMENT"]))
    artifact = next(iter(repository.artifacts.values()))

    with pytest.raises(ValueError, match="PASSED"):
        service.record_approval_decision(
            artifact_id=artifact.artifact_id,
            decision="APPROVE",
            reviewer="reviewer@example.com",
            comment="record only",
            validation_report_id=artifact.latest_validation_report_id,
        )

    gate_report = service.evaluate_publish_gate(artifact.artifact_id)

    assert repository.artifacts[artifact.artifact_id].status.value == "DRAFT"
    assert gate_report.status == "FAILED"
    assert gate_report.storage_result == "FAIL"
    assert gate_report.checks[0]["ruleId"] == "workflow.approval.before_publish"


def test_approve_after_passed_validation_satisfies_gate_without_publishing() -> None:
    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)
    request = repository.create_request(
        db_profile_id="master",
        target={"type": "PROCEDURE", "schema": "dbo", "name": "usp_demo"},
        outputs=("SP_ANALYSIS_DOCUMENT",),
        options={},
        request_hash="hash-approve-pass",
        correlation_id="corr-approve-pass",
        idempotency_key=None,
    )
    job = repository.create_job(request.request_id, correlation_id=request.correlation_id)
    artifact = repository.add_artifact(
        job_id=job.job_id,
        artifact_type=ArtifactType.SP_ANALYSIS_DOC,
        title="Passed Analysis",
        content=_passed_sp_analysis_content(),
        evidence_refs=[
            {
                "type": "MSSQL_METADATA",
                "objectRef": "dbo.usp_demo",
                "locator": "fixture.metadata",
            }
        ],
        generator_version="test",
        registry_refs=("prompt@test",),
        assumptions=(),
        review_required=False,
    )

    validation = service.validate_artifact(
        artifact.artifact_id,
        correlation_id="corr-approve-pass",
    )
    approval = service.record_approval_decision(
        artifact_id=artifact.artifact_id,
        decision="APPROVE",
        reviewer="reviewer@example.com",
        comment="validated and approved",
        validation_report_id=validation.validation_report_id,
        correlation_id="corr-approve-pass",
    )
    gate_report = service.evaluate_publish_gate(artifact.artifact_id)

    stored = repository.artifacts[artifact.artifact_id]
    assert validation.status == "PASSED"
    assert approval.decision == "APPROVE"
    assert approval.storage_decision == "APPROVED"
    assert gate_report.status == "PASSED"
    assert gate_report.storage_result == "PASS"
    assert stored.status == ArtifactStatus.APPROVED
    assert stored.status != ArtifactStatus.PUBLISHED
    assert "PUBLISHED" not in {item.status.value for item in repository.artifacts.values()}
    assert repository.audit_events[-1].action == "PUBLISH_GATE_EVALUATED"


def test_approval_audit_payload_binds_artifact_version_refs_and_correlation() -> None:
    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)
    request = repository.create_request(
        db_profile_id="ppm",
        target={"type": "PROCEDURE", "schema": "dbo", "name": "GetInspItemsCd"},
        outputs=("SP_ANALYSIS_DOCUMENT",),
        options={},
        request_hash="hash-p17c-approval-audit",
        correlation_id="corr-p17c-approval-audit",
        idempotency_key=None,
    )
    job = repository.create_job(request.request_id, correlation_id=request.correlation_id)
    artifact = repository.add_artifact(
        job_id=job.job_id,
        artifact_type=ArtifactType.SP_ANALYSIS_DOC,
        title="Passed P17B Analysis",
        content=_passed_sp_analysis_content(),
        evidence_refs=[
            {
                "type": "MSSQL_METADATA",
                "objectRef": "dbo.usp_demo",
                "locator": "fixtures/eval/live_pilot_artifact_validation_p17_v1.yaml",
                "snapshotId": "live:ppm:2026-05-06T12:52:24Z",
            }
        ],
        generator_version="live-pilot-artifact-manifest-0.1.0",
        registry_refs=("fixture:live_pilot_artifacts_p17_v1",),
        assumptions=(),
        review_required=False,
        extra={
            "artifactVersion": "2026-05-06.p17b.v1",
            "selectedObjectRefs": ["PROCEDURE:dbo.GetInspItemsCd"],
        },
    )
    validation = service.validate_artifact(
        artifact.artifact_id,
        correlation_id="corr-p17c-approval-audit",
    )

    approval = service.record_approval_decision(
        artifact_id=artifact.artifact_id,
        decision="APPROVE",
        reviewer="human.reviewer@example.com",
        comment="human approval evidence supplied outside P17C missing-template mode",
        validation_report_id=validation.validation_report_id,
        correlation_id="corr-p17c-approval-audit",
    )

    audit = [
        event
        for event in repository.audit_events
        if event.action == "APPROVAL_DECISION_RECORDED"
    ][-1]
    assert approval.decision == "APPROVE"
    assert audit.correlation_id == "corr-p17c-approval-audit"
    assert audit.payload["actor"] == "human.reviewer@example.com"
    assert audit.payload["correlationId"] == "corr-p17c-approval-audit"
    assert audit.payload["artifactId"] == artifact.artifact_id
    assert audit.payload["artifactVersion"] == "2026-05-06.p17b.v1"
    assert audit.payload["artifactRef"] == {
        "artifactId": artifact.artifact_id,
        "artifactVersion": "2026-05-06.p17b.v1",
        "artifactType": "SP_ANALYSIS_DOC",
    }
    assert audit.payload["validationRef"]["validationReportId"] == (
        validation.validation_report_id
    )
    assert audit.payload["validationRef"]["validationStatus"] == "PASSED"
    assert audit.payload["approvalRef"]["approvalId"] == approval.approval_id
    assert audit.payload["approvalRef"]["decision"] == "APPROVE"
    assert audit.payload["selectedObjectRefs"] == ["PROCEDURE:dbo.GetInspItemsCd"]
    assert audit.payload["evidenceRefs"] == artifact.evidence_refs
    assert audit.payload["refs"]["artifactVersion"] == "2026-05-06.p17b.v1"
    assert audit.payload["refs"]["validationReportId"] == validation.validation_report_id
    assert audit.payload["refs"]["approvalId"] == approval.approval_id
    assert audit.payload["timestamp"]


def test_approval_decision_requires_latest_validation_context() -> None:
    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)
    request = repository.create_request(
        db_profile_id="master",
        target={"type": "PROCEDURE", "schema": "dbo", "name": "usp_demo"},
        outputs=("SP_ANALYSIS_DOCUMENT",),
        options={},
        request_hash="hash-no-validation",
        correlation_id="corr-no-validation",
        idempotency_key=None,
    )
    job = repository.create_job(request.request_id, correlation_id=request.correlation_id)
    artifact = repository.add_artifact(
        job_id=job.job_id,
        artifact_type=ArtifactType.SP_ANALYSIS_DOC,
        title="Analysis",
        content="# Analysis",
        evidence_refs=[],
        generator_version="test",
        registry_refs=(),
        assumptions=(),
        review_required=True,
    )

    with pytest.raises(ValueError, match="latest artifact validation"):
        service.record_approval_decision(
            artifact_id=artifact.artifact_id,
            decision="REQUEST_CHANGES",
            reviewer="reviewer@example.com",
            comment="needs validation first",
            validation_report_id=None,
        )


def test_approve_rejects_non_latest_validation_report_id() -> None:
    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)
    service.submit_sp_analysis(_request(["SP_ANALYSIS_DOCUMENT", "DEPENDENCY_REPORT"]))
    artifacts = list(repository.artifacts.values())

    with pytest.raises(ValueError, match="latest artifact validation"):
        service.record_approval_decision(
            artifact_id=artifacts[0].artifact_id,
            decision="APPROVE",
            reviewer="reviewer@example.com",
            comment="wrong validation id",
            validation_report_id=artifacts[1].latest_validation_report_id,
        )


def test_request_changes_decision_maps_to_storage_rejected_without_closing_review() -> None:
    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)
    service.submit_sp_analysis(_request(["SP_ANALYSIS_DOCUMENT"]))
    artifact = next(iter(repository.artifacts.values()))

    approval = service.record_approval_decision(
        artifact_id=artifact.artifact_id,
        decision="REQUEST_CHANGES",
        reviewer="reviewer@example.com",
        comment="please revise",
        validation_report_id=None,
    )

    assert approval.decision == "REQUEST_CHANGES"
    assert approval.storage_decision == "REJECTED"
    assert approval.validation_report_id == artifact.latest_validation_report_id
    assert approval.reviewer_checklist
    assert approval.validation_summary["artifactId"] == artifact.artifact_id
    assert repository.artifacts[artifact.artifact_id].status.value == "REVIEW_PENDING"
    audit = repository.audit_events[-1]
    assert audit.action == "APPROVAL_DECISION_RECORDED"
    assert audit.payload["stage"] == "APPROVAL"
    assert audit.payload["actor"] == "reviewer@example.com"
    assert audit.payload["refs"]["validationReportId"] == artifact.latest_validation_report_id
