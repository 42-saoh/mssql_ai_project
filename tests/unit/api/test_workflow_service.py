from __future__ import annotations

import json

import pytest
from ai_agent_domain import ArtifactStatus, ArtifactType, JobStatus, WorkflowStepType
from ai_agent_generation import GenerationContext
from ai_agent_runtime import (
    FakeModelGateway,
    LangGraphAiDraftPackOrchestrator,
    OpenAIAgentsFrameworkAdapter,
)
from ai_agent_runtime.gateway import ModelGatewayError, model_profile_from_env
from ai_agent_runtime.models import AgentRunStatus, ModelInvocationRecord, stable_json_hash
from api_app.lifecycle import WorkflowStateError
from api_app.metadata_gateway import MetadataCollectionResult
from api_app.schemas import SPAnalysisRequest
from api_app.tracking import IdempotencyConflictError, RequestTrackingContext
from api_app.workflow import (
    AI_DRAFT_PACK_PLANNER_AGENT_TYPE,
    DEPENDENCY_AGENT_TYPE,
    OPERATION_MODEL_AGENT_TYPE,
    P41_OPERATION_MODEL_REVIEW_REQUIRED,
    P42_AI_DRAFT_PACK_FAILED,
    P42_AI_DRAFT_PACK_REVIEW_REQUIRED,
    P42_INVENTORY_CONTRACT_INCOMPLETE,
    WORKFLOW_METADATA_NOTE,
    WorkflowService,
    ai_draft_pack_expected_inventory,
    ai_draft_pack_quality_gates,
    dependency_procedure_candidates,
    generation_context_from_request,
)
from tests.helpers.framework_adapters import (
    BaselineResponsesFrameworkAdapter,
    FakeAiGenerationFrameworkAdapter,
)

from tests.helpers.p42_manage_bond import (
    ManageBondMetadataGateway,
    manage_bond_request,
    p41_operation_model_fixture,
    p42_ai_draft_pack_fixture,
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


def test_workflow_service_defaults_openai_remote_to_agents_and_langgraph(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_ENABLE_REMOTE", "1")
    monkeypatch.setenv("LLM_REMOTE_PROVIDER", "openai")
    monkeypatch.delenv("AI_GENERATION_RUNTIME", raising=False)
    monkeypatch.delenv("AI_DRAFT_PACK_ORCHESTRATOR", raising=False)

    service = WorkflowService(
        MemoryWorkflowRepository(),
        metadata_gateway=ManageBondMetadataGateway(),
        model_gateway=FakeModelGateway(),
    )

    assert isinstance(service.ai_generation_framework_adapter, OpenAIAgentsFrameworkAdapter)
    assert isinstance(service.ai_draft_pack_orchestrator, LangGraphAiDraftPackOrchestrator)


def test_workflow_service_keeps_pgpt_on_responses_httpx_rollback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_ENABLE_REMOTE", "1")
    monkeypatch.setenv("LLM_REMOTE_PROVIDER", "pgpt")
    monkeypatch.delenv("AI_GENERATION_RUNTIME", raising=False)
    monkeypatch.delenv("AI_DRAFT_PACK_ORCHESTRATOR", raising=False)

    service = WorkflowService(
        MemoryWorkflowRepository(),
        metadata_gateway=ManageBondMetadataGateway(),
        model_gateway=FakeModelGateway(),
    )

    assert service.ai_generation_framework_adapter is None
    assert service.ai_draft_pack_orchestrator is None


def test_workflow_service_allows_explicit_pgpt_agents_sdk_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_ENABLE_REMOTE", "1")
    monkeypatch.setenv("LLM_REMOTE_PROVIDER", "pgpt")
    monkeypatch.setenv("AI_GENERATION_RUNTIME", "openai_agents")
    monkeypatch.setenv("AI_DRAFT_PACK_ORCHESTRATOR", "langgraph")

    service = WorkflowService(
        MemoryWorkflowRepository(),
        metadata_gateway=ManageBondMetadataGateway(),
        model_gateway=FakeModelGateway(),
    )

    assert isinstance(service.ai_generation_framework_adapter, OpenAIAgentsFrameworkAdapter)
    assert isinstance(service.ai_draft_pack_orchestrator, LangGraphAiDraftPackOrchestrator)


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
            "## quality_summary",
            "- evidence ref confirmed.",
            "",
            "## evidence_map",
            "- dbo.usp_demo",
            "",
            "## known_caveats",
            "- none",
            "",
            "## next_evidence_to_collect",
            "- none",
            "",
            "## draft_readiness",
            "- draft only",
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


def test_p42_inventory_derives_java_method_ids_from_operation_refs() -> None:
    operation_model = {
        "targetRef": "dbo.usp_ComplexProc",
        "operations": [
            {
                "operationId": "op.complexCrudRQuery",
                "statementRefs": ["stmt.select.s001"],
                "dtoBlueprintRefs": ["ComplexSearchCriteria", "ComplexSearchRow"],
            },
            {
                "operationId": "op.complexCrudUUpdate",
                "statementRefs": ["stmt.update.s002"],
                "dtoBlueprintRefs": ["ComplexUpdateCommand"],
            },
        ],
        "statementEvidence": [
            {"statementId": "stmt.select.s001", "operation": "SELECT"},
            {"statementId": "stmt.update.s002", "operation": "UPDATE"},
        ],
        "dtoBlueprints": [
            {
                "name": "ComplexSearchCriteria",
                "role": "QUERY",
                "operationIds": ["op.complexCrudRQuery"],
                "fields": [{"name": "SearchType"}],
                "evidenceRefs": ["source.span.s001"],
                "reviewMarkers": [],
            },
            {
                "name": "ComplexSearchRow",
                "role": "RESULT",
                "operationIds": ["op.complexCrudRQuery"],
                "fields": [{"name": "ResultId"}],
                "evidenceRefs": ["source.span.s001"],
                "reviewMarkers": [],
            },
            {
                "name": "ComplexUpdateCommand",
                "role": "COMMAND",
                "operationIds": ["op.complexCrudUUpdate"],
                "fields": [{"name": "UpdateValue"}],
                "evidenceRefs": ["source.span.s002"],
                "reviewMarkers": [],
            },
        ],
        "reviewMarkers": ["TRANSACTION_BOUNDARY_REVIEW_REQUIRED"],
    }
    context = GenerationContext.from_mapping(
        {
            "sampleId": "sample",
            "request": {
                "entityName": "ComplexProc",
                "spName": "dbo.usp_ComplexProc",
                "operationModel": operation_model,
            },
        }
    )

    inventory = ai_draft_pack_expected_inventory(context)
    service_item = next(item for item in inventory if item["artifactType"] == "SERVICE_DRAFT")
    mapper_item = next(item for item in inventory if item["artifactType"] == "MAPPER_INTERFACE")
    mapper_xml_item = next(item for item in inventory if item["artifactType"] == "MAPPER_XML")
    quality_gates = ai_draft_pack_quality_gates(context, inventory)

    assert service_item["operationIds"] == ["complexCrudRQuery", "complexCrudUUpdate"]
    assert mapper_item["operationIds"] == service_item["operationIds"]
    assert mapper_xml_item["operationIds"] == service_item["operationIds"]
    assert "TVF_OR_PROCEDURE_KIND_REVIEW_REQUIRED" in quality_gates["requiredReviewMarkers"]
    assert "TRANSACTION_BOUNDARY_REVIEW_REQUIRED" in quality_gates["requiredReviewMarkers"]
    assert not any(
        str(operation_id).startswith("op.")
        for item in inventory
        for operation_id in item.get("operationIds", [])
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


def test_sp_analysis_can_be_submitted_then_executed_later() -> None:
    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)

    request_record, submitted = service.submit_sp_analysis(
        _request(["SP_ANALYSIS_DOCUMENT"]),
        run_async=True,
    )

    assert submitted.status == JobStatus.SUBMITTED
    assert repository.requests[request_record.request_id].status == JobStatus.SUBMITTED
    assert repository.list_job_artifacts(submitted.job_id) == []

    completed = service.execute_submitted_sp_analysis(submitted.job_id)
    second_execution = service.execute_submitted_sp_analysis(submitted.job_id)

    assert completed.status == JobStatus.VALIDATION_COMPLETE
    assert second_execution.status == JobStatus.VALIDATION_COMPLETE
    assert repository.claim_submitted_job(submitted.job_id) is None
    assert repository.list_job_artifacts(submitted.job_id)


def test_p42_manage_bond_workflow_wires_ai_draft_pack_into_multi_dto_artifacts() -> None:
    operation_model = p41_operation_model_fixture()
    ai_draft_pack = p42_ai_draft_pack_fixture()
    repository = MemoryWorkflowRepository()
    service = WorkflowService(
        repository,
        metadata_gateway=ManageBondMetadataGateway(),
        model_gateway=FakeModelGateway(
            sp_operation_model_by_target_ref={operation_model["targetRef"]: operation_model},
            ai_draft_pack_by_target_ref={ai_draft_pack["targetRef"]: ai_draft_pack},
        ),
    )

    _request_record, job = service.submit_sp_analysis(manage_bond_request())

    artifacts = repository.list_job_artifacts(job.job_id) or []
    dto_artifacts = [artifact for artifact in artifacts if artifact.type == ArtifactType.DTO_DRAFT]
    service_artifacts = [
        artifact for artifact in artifacts if artifact.type == ArtifactType.SERVICE_DRAFT
    ]
    mapper_artifacts = [
        artifact for artifact in artifacts if artifact.type == ArtifactType.MAPPER_INTERFACE
    ]
    mapper_xml_artifacts = [
        artifact for artifact in artifacts if artifact.type == ArtifactType.MAPPER_XML
    ]
    dto_titles = {artifact.title for artifact in dto_artifacts}
    required_dtos = set(ai_draft_pack["qualityGates"]["requiredDtoClasses"])

    validation_debug = [
        (
            artifact.title,
            repository.latest_validation_for(artifact.artifact_id).status,
            repository.latest_validation_for(artifact.artifact_id).checks,
        )
        for artifact in artifacts
    ]
    assert job.status == JobStatus.VALIDATION_COMPLETE, validation_debug
    assert len(dto_artifacts) == len(required_dtos)
    assert len(service_artifacts) == 1
    assert len(mapper_artifacts) == 1
    assert len(mapper_xml_artifacts) == 1
    assert not any(title.endswith("/ManageBondDTO.java") for title in dto_titles)
    assert not any(title.endswith("/OperationModelReviewRequired.java") for title in dto_titles)
    assert {f"{dto}.java" for dto in required_dtos} == {
        title.rsplit("/", 1)[-1] for title in dto_titles
    }
    for artifact in dto_artifacts:
        assert artifact.extra["bundleFilePath"] == artifact.title
        assert artifact.extra["bundleRole"] == ArtifactType.DTO_DRAFT.value
        assert artifact.extra["aiDraftPackSchema"] == "AiJavaMyBatisDraftPack.v0.1"
        assert artifact.extra["aiDraftPackTargetRef"] == ai_draft_pack["targetRef"]
        assert artifact.extra["aiDraftPackAgentRunId"]
        assert artifact.extra["aiFileRole"]
        assert artifact.extra["operationIds"]
        assert artifact.extra["dtoRole"]
        assert artifact.extra["qualityScore"] >= 1.0
        assert artifact.extra["aiEvidenceRefs"]
        assert isinstance(artifact.extra["reviewMarkers"], list)
        assert "OperationModelReviewRequired" not in artifact.content
        assert "ManageBondDTO" not in artifact.content
    for artifact in [*service_artifacts, *mapper_artifacts, *mapper_xml_artifacts]:
        assert artifact.extra["aiDraftPackSchema"] == "AiJavaMyBatisDraftPack.v0.1"
        assert artifact.extra["bundleFilePath"] == artifact.title
        assert artifact.extra["aiFileRole"]
        assert artifact.extra["operationIds"]
        assert "OperationModelReviewRequired" not in artifact.content
        assert "ManageBondDTO" not in artifact.content

    service_content = service_artifacts[0].content
    mapper_content = mapper_artifacts[0].content
    mapper_xml_content = mapper_xml_artifacts[0].content
    assert "public class ManageBondService" in service_content
    assert (
        "List<ManageBondSearchRow> readBond(ManageBondSearchCriteria criteria)"
        in service_content
    )
    assert "int updateVendorBond(VendorBondUpdateCommand command)" in mapper_content
    assert "int updateOnlineBond(OnlineBondUpdateCommand command)" in mapper_content
    assert 'parameterType="ManageBondSearchCriteria"' in mapper_xml_content
    assert 'resultType="ManageBondSearchRow"' in mapper_xml_content
    assert 'parameterType="VendorBondUpdateCommand"' in mapper_xml_content
    assert 'parameterType="OnlineBondUpdateCommand"' in mapper_xml_content
    operation_runs = [
        run
        for run in repository.list_agent_runs(job.job_id) or []
        if run.agent_type == OPERATION_MODEL_AGENT_TYPE
    ]
    assert len(operation_runs) == 1
    assert operation_runs[0].structured_output["targetRef"] == operation_model["targetRef"]
    assert "CREATE PROCEDURE" not in str(operation_runs[0].structured_output)
    assert "SET GUAR_APRV_YN" not in str(operation_runs[0].model_invocation)
    ai_draft_runs = [
        run
        for run in repository.list_agent_runs(job.job_id) or []
        if run.agent_type == AI_DRAFT_PACK_PLANNER_AGENT_TYPE
    ]
    assert len(ai_draft_runs) == 1
    assert ai_draft_runs[0].status == AgentRunStatus.SUCCEEDED.value
    context = generation_context_from_request(
        repository.requests[job.request_id],
        operation_model_run=operation_runs[0],
        ai_draft_pack_run=ai_draft_runs[0],
    )
    assert context.request["aiDraftPack"]["schemaVersion"] == "AiJavaMyBatisDraftPack.v0.1"
    assert context.request["aiDraftPackTrace"]["agentRunId"] == ai_draft_runs[0].agent_run_id


@pytest.mark.parametrize(
    ("adapter_kind", "candidate_framework"),
    [
        ("baseline", "baseline_internal_responses_gateway"),
        ("candidate", "openai_agents_sdk_fake"),
    ],
)
def test_p43c_workflow_ab_routes_ai_draft_pack_through_framework_adapter(
    adapter_kind: str,
    candidate_framework: str,
) -> None:
    operation_model = p41_operation_model_fixture()
    ai_draft_pack = p42_ai_draft_pack_fixture()
    gateway = FakeModelGateway(
        sp_operation_model_by_target_ref={operation_model["targetRef"]: operation_model},
        ai_draft_pack_by_target_ref={ai_draft_pack["targetRef"]: ai_draft_pack},
    )
    adapter = (
        BaselineResponsesFrameworkAdapter(model_gateway=gateway)
        if adapter_kind == "baseline"
        else FakeAiGenerationFrameworkAdapter(
            output=ai_draft_pack,
            candidate_framework=candidate_framework,
        )
    )
    repository = MemoryWorkflowRepository()
    service = WorkflowService(
        repository,
        metadata_gateway=ManageBondMetadataGateway(),
        model_gateway=gateway,
        ai_generation_framework_adapter=adapter,
    )

    _request_record, job = service.submit_sp_analysis(manage_bond_request())

    artifacts = repository.list_job_artifacts(job.job_id) or []
    ai_draft_run = next(
        run
        for run in repository.list_agent_runs(job.job_id) or []
        if run.agent_type == AI_DRAFT_PACK_PLANNER_AGENT_TYPE
    )
    adapter_components = [
        component
        for component in ai_draft_run.model_invocation["componentInvocations"]
        if component.get("component") == "ai_generation_framework_adapter"
    ]

    assert job.status == JobStatus.VALIDATION_COMPLETE
    assert [component["stage"] for component in adapter_components] == [
        "file_inventory",
        "file_content",
    ]
    assert {component["candidateFramework"] for component in adapter_components} == {
        candidate_framework
    }
    assert len([artifact for artifact in artifacts if artifact.type == ArtifactType.DTO_DRAFT]) == (
        len(ai_draft_pack["qualityGates"]["requiredDtoClasses"])
    )
    assert "OperationModelReviewRequired" not in str(artifacts)
    assert "ManageBondDTO" not in str(artifacts)


def test_p42_complex_sp_inventory_contract_rejects_collapsed_operation_model() -> None:
    operation_model = p41_operation_model_fixture()
    operation_model["operations"] = operation_model["operations"][:1]
    operation_model["dtoBlueprints"] = operation_model["dtoBlueprints"][:2]
    ai_draft_pack = p42_ai_draft_pack_fixture()

    class InventorySpyGateway(FakeModelGateway):
        def __init__(self) -> None:
            super().__init__(
                sp_operation_model_by_target_ref={operation_model["targetRef"]: operation_model},
                ai_draft_pack_by_target_ref={ai_draft_pack["targetRef"]: ai_draft_pack},
            )
            self.draft_calls = 0

        def draft_ai_java_mybatis_pack(self, *, prompt, profile) -> ModelInvocationRecord:
            self.draft_calls += 1
            return super().draft_ai_java_mybatis_pack(prompt=prompt, profile=profile)

    class ShouldNotCallFrameworkAdapter:
        adapter_id = "should_not_call"
        candidate_framework = "should_not_call"

        def __init__(self) -> None:
            self.calls: list[str] = []

        def plan_file_inventory(self, *, request) -> ModelInvocationRecord:
            self.calls.append("file_inventory")
            raise AssertionError("adapter should not run before inventory contract passes")

        def draft_file_content(self, *, request) -> ModelInvocationRecord:
            self.calls.append("file_content")
            raise AssertionError("adapter should not run before inventory contract passes")

        def repair_draft_pack(self, *, request) -> ModelInvocationRecord:
            self.calls.append("repair")
            raise AssertionError("adapter should not run before inventory contract passes")

        def summarize_trace(self, **_kwargs) -> dict:
            return {}

    gateway = InventorySpyGateway()
    adapter = ShouldNotCallFrameworkAdapter()
    repository = MemoryWorkflowRepository()
    service = WorkflowService(
        repository,
        metadata_gateway=ManageBondMetadataGateway(),
        model_gateway=gateway,
        ai_generation_framework_adapter=adapter,
    )

    _request_record, job = service.submit_sp_analysis(manage_bond_request())

    artifacts = repository.list_job_artifacts(job.job_id) or []
    ai_draft_run = next(
        run
        for run in repository.list_agent_runs(job.job_id) or []
        if run.agent_type == AI_DRAFT_PACK_PLANNER_AGENT_TYPE
    )

    assert job.status == JobStatus.FAILED
    assert job.error_code == P42_INVENTORY_CONTRACT_INCOMPLETE
    assert gateway.draft_calls == 0
    assert adapter.calls == []
    assert ai_draft_run.status == AgentRunStatus.FAILED.value
    assert ai_draft_run.structured_output["reviewMarkers"][0]["code"] == (
        P42_INVENTORY_CONTRACT_INCOMPLETE
    )
    assert ai_draft_run.structured_output["failureDiagnostics"]["failureStage"] == (
        "inventory_contract"
    )
    assert not any(
        artifact.type
        in {
            ArtifactType.DTO_DRAFT,
            ArtifactType.SERVICE_DRAFT,
            ArtifactType.MAPPER_INTERFACE,
            ArtifactType.MAPPER_XML,
        }
        for artifact in artifacts
    )


def test_p42_workflow_fails_without_java_artifacts_when_planner_is_disabled() -> None:
    repository = MemoryWorkflowRepository()
    service = WorkflowService(
        repository,
        metadata_gateway=ManageBondMetadataGateway(),
        model_gateway=FakeModelGateway(),
    )

    _request_record, job = service.submit_sp_analysis(
        manage_bond_request(use_llm_analysis=False)
    )

    artifacts = repository.list_job_artifacts(job.job_id) or []
    dto_artifacts = [artifact for artifact in artifacts if artifact.type == ArtifactType.DTO_DRAFT]
    runs = repository.list_agent_runs(job.job_id) or []
    operation_run = next(run for run in runs if run.agent_type == OPERATION_MODEL_AGENT_TYPE)
    ai_draft_run = next(run for run in runs if run.agent_type == AI_DRAFT_PACK_PLANNER_AGENT_TYPE)

    assert job.status == JobStatus.FAILED
    assert job.error_code == P42_AI_DRAFT_PACK_REVIEW_REQUIRED
    assert not dto_artifacts
    assert not any(artifact.type == ArtifactType.SERVICE_DRAFT for artifact in artifacts)
    assert not any(artifact.type == ArtifactType.MAPPER_INTERFACE for artifact in artifacts)
    assert not any(artifact.type == ArtifactType.MAPPER_XML for artifact in artifacts)
    assert P41_OPERATION_MODEL_REVIEW_REQUIRED in operation_run.structured_output["reviewMarkers"]
    assert "LLM_OPERATION_MODEL_DISABLED" in operation_run.structured_output["reviewMarkers"]
    assert ai_draft_run.status == AgentRunStatus.FAILED.value
    assert ai_draft_run.structured_output["reviewMarkers"][0]["code"] == (
        P42_AI_DRAFT_PACK_REVIEW_REQUIRED
    )
    assert not any(artifact.title.endswith("/PcoGuManagebondPrcDTO.java") for artifact in artifacts)


def test_p42_workflow_fails_without_java_artifacts_when_definition_is_missing() -> None:
    repository = MemoryWorkflowRepository()
    service = WorkflowService(
        repository,
        metadata_gateway=ManageBondMetadataGateway(definition=None),
        model_gateway=FakeModelGateway(),
    )

    _request_record, job = service.submit_sp_analysis(manage_bond_request())

    artifacts = repository.list_job_artifacts(job.job_id) or []
    dto_artifacts = [artifact for artifact in artifacts if artifact.type == ArtifactType.DTO_DRAFT]
    runs = repository.list_agent_runs(job.job_id) or []
    operation_run = next(
        run
        for run in runs
        if run.agent_type == OPERATION_MODEL_AGENT_TYPE
    )
    ai_draft_run = next(run for run in runs if run.agent_type == AI_DRAFT_PACK_PLANNER_AGENT_TYPE)

    assert job.status == JobStatus.FAILED
    assert job.error_code == P42_AI_DRAFT_PACK_REVIEW_REQUIRED
    assert not dto_artifacts
    assert not any(artifact.type == ArtifactType.SERVICE_DRAFT for artifact in artifacts)
    assert not any(artifact.type == ArtifactType.MAPPER_INTERFACE for artifact in artifacts)
    assert not any(artifact.type == ArtifactType.MAPPER_XML for artifact in artifacts)
    assert P41_OPERATION_MODEL_REVIEW_REQUIRED in operation_run.structured_output["reviewMarkers"]
    assert "PROCEDURE_DEFINITION_UNAVAILABLE" in operation_run.structured_output["reviewMarkers"]
    assert ai_draft_run.status == AgentRunStatus.FAILED.value
    assert ai_draft_run.structured_output["reviewMarkers"][0]["code"] == (
        P42_AI_DRAFT_PACK_REVIEW_REQUIRED
    )


def test_p42_workflow_rejects_invalid_pack_quality_without_fallback_artifacts() -> None:
    operation_model = p41_operation_model_fixture()
    ai_draft_pack = p42_ai_draft_pack_fixture()
    for file in ai_draft_pack["files"]:
        if file["artifactType"] == "SERVICE_DRAFT":
            file["content"] = "public class ManageBondService { /* REVIEW_REQUIRED */ }"
            break
    repository = MemoryWorkflowRepository()
    service = WorkflowService(
        repository,
        metadata_gateway=ManageBondMetadataGateway(),
        model_gateway=FakeModelGateway(
            sp_operation_model_by_target_ref={operation_model["targetRef"]: operation_model},
            ai_draft_pack_by_target_ref={ai_draft_pack["targetRef"]: ai_draft_pack},
        ),
    )

    _request_record, job = service.submit_sp_analysis(manage_bond_request())

    artifacts = repository.list_job_artifacts(job.job_id) or []
    ai_draft_run = next(
        run
        for run in repository.list_agent_runs(job.job_id) or []
        if run.agent_type == AI_DRAFT_PACK_PLANNER_AGENT_TYPE
        and run.status == AgentRunStatus.FAILED.value
    )

    assert job.status == JobStatus.FAILED
    assert job.error_code == P42_AI_DRAFT_PACK_FAILED
    assert not any(
        artifact.type
        in {
            ArtifactType.DTO_DRAFT,
            ArtifactType.SERVICE_DRAFT,
            ArtifactType.MAPPER_INTERFACE,
            ArtifactType.MAPPER_XML,
        }
        for artifact in artifacts
    )
    assert ai_draft_run.structured_output["reviewMarkers"][0]["code"] == (
        P42_AI_DRAFT_PACK_FAILED
    )
    failed_rule_ids = {
        finding["ruleId"]
        for finding in ai_draft_run.structured_output["qualityGateFindings"]
    }
    assert failed_rule_ids & {
        "p42.ai_draft_pack.non_dto.dto_reference",
        "p42.ai_draft_pack.service.method",
    }
    assert "OperationModelReviewRequired" not in str(artifacts)


def test_p43c_candidate_two_dto_collapse_fails_without_java_artifacts() -> None:
    operation_model = p41_operation_model_fixture()
    collapsed_pack = p42_ai_draft_pack_fixture()
    dto_files = [
        file for file in collapsed_pack["files"] if file["artifactType"] == "DTO_DRAFT"
    ][:2]
    non_dto_files = [
        file for file in collapsed_pack["files"] if file["artifactType"] != "DTO_DRAFT"
    ]
    kept_dtos = [file["className"] for file in dto_files]
    for file in non_dto_files:
        file["references"] = list(kept_dtos)
    collapsed_pack["files"] = [*dto_files, *non_dto_files]
    collapsed_pack["qualityGates"]["requiredDtoClasses"] = list(kept_dtos)
    repository = MemoryWorkflowRepository()
    service = WorkflowService(
        repository,
        metadata_gateway=ManageBondMetadataGateway(),
        model_gateway=FakeModelGateway(
            sp_operation_model_by_target_ref={operation_model["targetRef"]: operation_model}
        ),
        ai_generation_framework_adapter=FakeAiGenerationFrameworkAdapter(
            output=collapsed_pack,
            candidate_framework="langgraph_fake",
        ),
    )

    _request_record, job = service.submit_sp_analysis(manage_bond_request())

    artifacts = repository.list_job_artifacts(job.job_id) or []
    ai_draft_run = next(
        run
        for run in repository.list_agent_runs(job.job_id) or []
        if run.agent_type == AI_DRAFT_PACK_PLANNER_AGENT_TYPE
    )
    stored_text = str(ai_draft_run.structured_output) + str(ai_draft_run.model_invocation)

    assert job.status == JobStatus.FAILED
    assert job.error_code == P42_AI_DRAFT_PACK_FAILED
    assert ai_draft_run.structured_output["failureDiagnostics"]["failureStage"] == (
        "quality_validation"
    )
    assert "p42.ai_draft_pack.schema" in str(
        ai_draft_run.structured_output["failureDiagnostics"]
    )
    assert "qualityGates.requiredDtoClasses missing DTO files" in str(
        ai_draft_run.structured_output["failureDiagnostics"]
    )
    assert "public class" not in stored_text
    assert "ManageBondDTO" not in stored_text
    assert not any(
        artifact.type
        in {
            ArtifactType.DTO_DRAFT,
            ArtifactType.SERVICE_DRAFT,
            ArtifactType.MAPPER_INTERFACE,
            ArtifactType.MAPPER_XML,
        }
        for artifact in artifacts
    )


def test_p43c_candidate_missing_review_markers_fails_quality_gate() -> None:
    operation_model = p41_operation_model_fixture()
    missing_markers_pack = p42_ai_draft_pack_fixture()
    missing_markers_pack["reviewMarkers"] = []
    missing_markers_pack["qualityGates"]["requiredReviewMarkers"] = []
    for file in missing_markers_pack["files"]:
        file["reviewMarkers"] = []
    repository = MemoryWorkflowRepository()
    service = WorkflowService(
        repository,
        metadata_gateway=ManageBondMetadataGateway(),
        model_gateway=FakeModelGateway(
            sp_operation_model_by_target_ref={operation_model["targetRef"]: operation_model}
        ),
        ai_generation_framework_adapter=FakeAiGenerationFrameworkAdapter(
            output=missing_markers_pack,
            candidate_framework="openai_agents_sdk_fake",
        ),
    )

    _request_record, job = service.submit_sp_analysis(manage_bond_request())

    artifacts = repository.list_job_artifacts(job.job_id) or []
    ai_draft_run = next(
        run
        for run in repository.list_agent_runs(job.job_id) or []
        if run.agent_type == AI_DRAFT_PACK_PLANNER_AGENT_TYPE
    )
    diagnostics = ai_draft_run.structured_output["failureDiagnostics"]

    assert job.status == JobStatus.FAILED
    assert job.error_code == P42_AI_DRAFT_PACK_FAILED
    assert diagnostics["failureStage"] == "quality_validation"
    assert "p42.ai_draft_pack.schema" in str(diagnostics)
    assert "required REVIEW_REQUIRED markers missing" in str(diagnostics)
    assert not any(
        artifact.type
        in {
            ArtifactType.DTO_DRAFT,
            ArtifactType.SERVICE_DRAFT,
            ArtifactType.MAPPER_INTERFACE,
            ArtifactType.MAPPER_XML,
        }
        for artifact in artifacts
    )


def test_p43c_raw_adapter_trace_failure_is_sanitized_and_stage_specific() -> None:
    operation_model = p41_operation_model_fixture()
    ai_draft_pack = p42_ai_draft_pack_fixture()
    repository = MemoryWorkflowRepository()
    service = WorkflowService(
        repository,
        metadata_gateway=ManageBondMetadataGateway(),
        model_gateway=FakeModelGateway(
            sp_operation_model_by_target_ref={operation_model["targetRef"]: operation_model}
        ),
        ai_generation_framework_adapter=FakeAiGenerationFrameworkAdapter(
            output=ai_draft_pack,
            candidate_framework="openai_agents_sdk_fake",
            trace_events=(
                {
                    "eventType": "unsafe_trace",
                    "raw_provider_response": (
                        "CREATE PROCEDURE dbo.Leak AS SELECT password FROM row data"
                    ),
                },
            ),
        ),
    )

    _request_record, job = service.submit_sp_analysis(manage_bond_request())

    artifacts = repository.list_job_artifacts(job.job_id) or []
    ai_draft_run = next(
        run
        for run in repository.list_agent_runs(job.job_id) or []
        if run.agent_type == AI_DRAFT_PACK_PLANNER_AGENT_TYPE
    )
    diagnostics = ai_draft_run.structured_output["failureDiagnostics"]
    stored_text = str(ai_draft_run.structured_output) + str(ai_draft_run.model_invocation)

    assert job.status == JobStatus.FAILED
    assert job.error_code == P42_AI_DRAFT_PACK_FAILED
    assert diagnostics["failureStage"] == "file_inventory_framework_trace"
    assert diagnostics["providerError"]["stage"] == "file_inventory"
    assert "CREATE PROCEDURE" not in stored_text
    assert "password" not in stored_text
    assert "raw_provider_response" not in stored_text
    assert "row data" not in stored_text
    assert not any(
        artifact.type
        in {
            ArtifactType.DTO_DRAFT,
            ArtifactType.SERVICE_DRAFT,
            ArtifactType.MAPPER_INTERFACE,
            ArtifactType.MAPPER_XML,
        }
        for artifact in artifacts
    )


def test_p42_workflow_repairs_invalid_quality_once_and_persists_artifacts() -> None:
    operation_model = p41_operation_model_fixture()
    repaired_pack = p42_ai_draft_pack_fixture()
    invalid_pack = p42_ai_draft_pack_fixture()
    for file in invalid_pack["files"]:
        if file["artifactType"] == "SERVICE_DRAFT":
            file["content"] = "public class ManageBondService { /* REVIEW_REQUIRED */ }"
            break

    class QualityRepairGateway(FakeModelGateway):
        def __init__(self) -> None:
            super().__init__(
                sp_operation_model_by_target_ref={operation_model["targetRef"]: operation_model}
            )
            self.draft_calls = 0
            self.stages: list[str] = []

        def draft_ai_java_mybatis_pack(self, *, prompt, profile) -> ModelInvocationRecord:
            self.draft_calls += 1
            self.stages.append(str(prompt.metadata["stage"]))
            payload = invalid_pack if self.draft_calls == 1 else repaired_pack
            return _model_invocation(
                prompt=prompt,
                profile=profile,
                provider="quality-repair-gateway",
                structured_output=payload,
            )

    gateway = QualityRepairGateway()
    repository = MemoryWorkflowRepository()
    service = WorkflowService(
        repository,
        metadata_gateway=ManageBondMetadataGateway(),
        model_gateway=gateway,
    )

    _request_record, job = service.submit_sp_analysis(manage_bond_request())

    artifacts = repository.list_job_artifacts(job.job_id) or []
    ai_draft_run = next(
        run
        for run in repository.list_agent_runs(job.job_id) or []
        if run.agent_type == AI_DRAFT_PACK_PLANNER_AGENT_TYPE
    )

    assert job.status == JobStatus.VALIDATION_COMPLETE
    assert gateway.draft_calls == 2
    assert gateway.stages == ["file_content", "repair"]
    assert ai_draft_run.status == AgentRunStatus.SUCCEEDED.value
    assert any(
        component["component"] == "ai_draft_pack_repair_stage"
        and component["failureStage"] == "deterministic_quality_validation"
        for component in ai_draft_run.model_invocation["componentInvocations"]
    )
    assert len([artifact for artifact in artifacts if artifact.type == ArtifactType.DTO_DRAFT]) == (
        len(repaired_pack["qualityGates"]["requiredDtoClasses"])
    )


def test_p42_workflow_reference_guard_preserves_missing_mapper_xml_dto_token() -> None:
    operation_model = p41_operation_model_fixture()
    ai_draft_pack = p42_ai_draft_pack_fixture()
    for file in ai_draft_pack["files"]:
        if file["artifactType"] == "MAPPER_XML":
            file["content"] = file["content"].replace(
                "CreateRetentionBondBatchItem",
                "RetentionBatchItem",
            )
            break
    repository = MemoryWorkflowRepository()
    service = WorkflowService(
        repository,
        metadata_gateway=ManageBondMetadataGateway(),
        model_gateway=FakeModelGateway(
            sp_operation_model_by_target_ref={operation_model["targetRef"]: operation_model},
            ai_draft_pack_by_target_ref={ai_draft_pack["targetRef"]: ai_draft_pack},
        ),
    )

    _request_record, job = service.submit_sp_analysis(manage_bond_request())

    mapper_xml = next(
        artifact
        for artifact in repository.list_job_artifacts(job.job_id) or []
        if artifact.type == ArtifactType.MAPPER_XML
    )
    ai_draft_run = next(
        run
        for run in repository.list_agent_runs(job.job_id) or []
        if run.agent_type == AI_DRAFT_PACK_PLANNER_AGENT_TYPE
    )

    assert job.status == JobStatus.VALIDATION_COMPLETE
    assert "CreateRetentionBondBatchItem" in mapper_xml.content
    assert any(
        component["component"] == "ai_draft_pack_reference_guard"
        for component in ai_draft_run.model_invocation["componentInvocations"]
    )


def test_p42_workflow_records_sanitized_gateway_failure_without_repairing_timeout() -> None:
    operation_model = p41_operation_model_fixture()

    class TimeoutDraftGateway(FakeModelGateway):
        def __init__(self) -> None:
            super().__init__(
                sp_operation_model_by_target_ref={operation_model["targetRef"]: operation_model}
            )
            self.draft_calls = 0

        def draft_ai_java_mybatis_pack(self, *, prompt, profile) -> ModelInvocationRecord:
            self.draft_calls += 1
            raise ModelGatewayError(
                "OpenAI Responses API request timed out.",
                code="OPENAI_TIMEOUT",
            )

    gateway = TimeoutDraftGateway()
    repository = MemoryWorkflowRepository()
    service = WorkflowService(
        repository,
        metadata_gateway=ManageBondMetadataGateway(),
        model_gateway=gateway,
    )

    _request_record, job = service.submit_sp_analysis(manage_bond_request())

    artifacts = repository.list_job_artifacts(job.job_id) or []
    ai_draft_run = next(
        run
        for run in repository.list_agent_runs(job.job_id) or []
        if run.agent_type == AI_DRAFT_PACK_PLANNER_AGENT_TYPE
    )
    diagnostics = ai_draft_run.structured_output["failureDiagnostics"]

    assert job.status == JobStatus.FAILED
    assert job.error_code == P42_AI_DRAFT_PACK_FAILED
    assert gateway.draft_calls == 1
    assert diagnostics["failureStage"] == "model_gateway"
    assert diagnostics["errorCode"] == "OPENAI_TIMEOUT"
    assert diagnostics["errorClass"] == "ModelGatewayError"
    assert ai_draft_run.model_invocation["componentInvocations"][0]["failureStage"] == (
        "model_gateway"
    )
    assert not any(
        artifact.type
        in {
            ArtifactType.DTO_DRAFT,
            ArtifactType.SERVICE_DRAFT,
            ArtifactType.MAPPER_INTERFACE,
            ArtifactType.MAPPER_XML,
        }
        for artifact in artifacts
    )
    assert "CREATE PROCEDURE" not in str(ai_draft_run.structured_output)
    assert "rawProviderResponse" not in str(ai_draft_run.structured_output)


def test_p42_workflow_records_sanitized_invalid_output_failure_after_repair_fails() -> None:
    operation_model = p41_operation_model_fixture()

    class InvalidOutputGateway(FakeModelGateway):
        def __init__(self) -> None:
            super().__init__(
                sp_operation_model_by_target_ref={operation_model["targetRef"]: operation_model}
            )
            self.draft_calls = 0

        def draft_ai_java_mybatis_pack(self, *, prompt, profile) -> ModelInvocationRecord:
            self.draft_calls += 1
            raise ModelGatewayError(
                "OpenAI response did not match the required structured output schema.",
                code="OPENAI_AI_DRAFT_PACK_INVALID",
            )

    gateway = InvalidOutputGateway()
    repository = MemoryWorkflowRepository()
    service = WorkflowService(
        repository,
        metadata_gateway=ManageBondMetadataGateway(),
        model_gateway=gateway,
    )

    _request_record, job = service.submit_sp_analysis(manage_bond_request())

    ai_draft_run = next(
        run
        for run in repository.list_agent_runs(job.job_id) or []
        if run.agent_type == AI_DRAFT_PACK_PLANNER_AGENT_TYPE
    )
    diagnostics = ai_draft_run.structured_output["failureDiagnostics"]

    assert job.status == JobStatus.FAILED
    assert job.error_code == P42_AI_DRAFT_PACK_FAILED
    assert gateway.draft_calls == 2
    assert diagnostics["failureStage"] == "model_gateway"
    assert diagnostics["errorCode"] == "OPENAI_AI_DRAFT_PACK_INVALID"
    assert diagnostics["errorClass"] == "ModelGatewayError"
    assert "rawProviderResponse" not in str(ai_draft_run.model_invocation)
    assert "CREATE PROCEDURE" not in str(ai_draft_run.model_invocation)


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
    class MultiSpSpyGateway(FakeModelGateway):
        def __init__(self) -> None:
            super().__init__()
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


def test_dependency_semantic_analysis_reuses_successful_child_run_by_target() -> None:
    class ChildReuseSpyGateway:
        def __init__(self) -> None:
            self.prompt_payloads: list[dict] = []

        def invoke_semantic_analysis(self, *, prompt, profile) -> ModelInvocationRecord:
            payload = json.loads(prompt.user_prompt)
            self.prompt_payloads.append(payload)
            assert payload["targetRef"] != "dbo.usp_GetOrderSummary"
            ref = (payload["evidenceRefContract"]["allowedFactIds"] or ["metadata.snapshot"])[0]
            structured_output = {
                "businessRules": [
                    {
                        "category": "NEW_CHILD_RULE",
                        "summary": f"{payload['targetRef']} child analysis was retried.",
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
                provider="spy-child-reuse",
                structured_output=structured_output,
            )

    repository = MemoryWorkflowRepository()
    spy_gateway = ChildReuseSpyGateway()
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
                "allowSpDefinitionToModel": True,
            },
        }
    )
    request_record = repository.create_request(
        db_profile_id=request.db_profile_id,
        target=request.target.to_response(),
        outputs=tuple(output.value for output in request.outputs),
        options=request.options.to_response(),
        request_hash="hash-child-reuse",
        correlation_id="corr-child-reuse",
        idempotency_key=None,
    )
    job = repository.create_job(
        request_record.request_id,
        correlation_id=request_record.correlation_id,
    )
    metadata = service._collect_metadata(job.job_id, request_record)
    profile = model_profile_from_env("openai_fast_test")
    reused_output = {
        "businessRules": [
            {
                "category": "REUSED_CHILD_RULE",
                "summary": "Existing child semantic run is safe to reuse.",
                "status": "INFERRED_DESCRIPTION",
                "evidenceRefs": ["metadata.snapshot"],
            }
        ],
        "modernizationPoints": [],
        "riskFlags": [],
        "reviewMarkers": [],
        "conversionGuidance": [],
        "migrationGuideInsights": [],
        "assumptions": [],
    }
    reused_invocation = ModelInvocationRecord(
        provider="spy-existing",
        model=profile.model,
        model_profile_id=profile.profile_id,
        model_registry_ref=profile.registry_ref,
        reasoning_effort=profile.reasoning_effort,
        prompt_version="test",
        output_schema_version="test",
        input_hash="input-reused",
        prompt_hash="prompt-reused",
        output_hash=stable_json_hash(reused_output),
        status=AgentRunStatus.SUCCEEDED,
        structured_output=reused_output,
        token_usage={"inputTokens": 0, "outputTokens": 0, "totalTokens": 0},
        latency_ms=0,
        component_invocations=(
            {
                "stage": "dependency_semantic_analysis",
                "status": "SUCCEEDED",
                "sourceContextSummary": {
                    "mode": "RETRIEVED_SPANS",
                    "budgetStatus": "WITHIN_BUDGET",
                    "selectedSpanCount": 1,
                    "skippedSpanCount": 0,
                    "reviewMarkers": [],
                },
            },
        ),
    )
    existing = repository.save_agent_run(
        job_id=job.job_id,
        agent_type=DEPENDENCY_AGENT_TYPE,
        status=AgentRunStatus.SUCCEEDED.value,
        target_ref="DBO.USP_GETORDERSUMMARY",
        target_key="mssql:master:-:procedure:dbo.usp_getordersummary",
        summary="existing dependency child semantic analysis",
        structured_output=reused_output,
        model_invocation=reused_invocation.to_storage_dict(),
    )
    failed_output = {
        "businessRules": [],
        "modernizationPoints": [],
        "riskFlags": [],
        "reviewMarkers": [],
        "conversionGuidance": [],
        "migrationGuideInsights": [],
        "assumptions": [],
    }
    repository.save_agent_run(
        job_id=job.job_id,
        agent_type=DEPENDENCY_AGENT_TYPE,
        status=AgentRunStatus.FAILED.value,
        target_ref="OtherDB.dbo.usp_CrossDbOrderAudit",
        summary="previous failed dependency child semantic analysis",
        structured_output=failed_output,
        model_invocation={
            **reused_invocation.to_storage_dict(),
            "status": AgentRunStatus.FAILED.value,
            "outputHash": stable_json_hash(failed_output),
        },
    )

    summary = service._run_dependency_semantic_analyses(
        job_id=job.job_id,
        request_record=request_record,
        metadata=metadata,
    )

    runs = repository.list_agent_runs(job.job_id)
    assert runs is not None
    reused_runs = [
        run
        for run in runs
        if run.target_key == "mssql:master:-:procedure:dbo.usp_getordersummary"
    ]
    retried_runs = [
        run
        for run in runs
        if run.target_ref == "OtherDB.dbo.usp_CrossDbOrderAudit"
    ]
    assert [run.agent_run_id for run in reused_runs] == [existing.agent_run_id]
    assert len(retried_runs) == 2
    assert any(run.status == AgentRunStatus.SUCCEEDED.value for run in retried_runs)
    assert spy_gateway.prompt_payloads
    assert {payload["targetRef"] for payload in spy_gateway.prompt_payloads} == {
        "OtherDB.dbo.usp_CrossDbOrderAudit"
    }
    assert summary["analyzedCount"] == 2
    assert summary["childRunCount"] == 2
    assert summary["reusedChildRunCount"] == 1
    reused_target = next(
        item
        for item in summary["analyzedTargets"]
        if item["targetRef"] == "dbo.usp_GetOrderSummary"
    )
    assert reused_target["agentRunId"] == existing.agent_run_id
    assert reused_target["targetKey"] == "mssql:master:-:procedure:dbo.usp_getordersummary"
    assert reused_target["reused"] is True


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

    assert request_record.status == JobStatus.VALIDATION_COMPLETE, (
        job.error_code,
        job.error_message,
    )
    assert job.status == JobStatus.VALIDATION_COMPLETE, (job.error_code, job.error_message)
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
    assert run.target_key == "mssql:master:-:procedure:dbo.usp_getordersummary"
    assert run.model_invocation["provider"] == "pgpt"
    assert run.model_invocation["status"] == AgentRunStatus.FAILED.value
    assert run.model_invocation["componentInvocations"][0]["errorCode"] == (
        "OPENAI_STRUCTURED_OUTPUT_INVALID"
    )
    provider_error = run.model_invocation["componentInvocations"][0]["providerError"]
    assert {
        "type": provider_error["type"],
        "code": provider_error["code"],
        "param": provider_error["param"],
        "message": provider_error["message"],
    } == {
        "type": "invalid_request_error",
        "code": "context_length_exceeded",
        "param": "input",
        "message": "Input exceeded provider limit.",
    }
    assert provider_error["semanticCompactionApplied"] == "true"
    assert provider_error["semanticCompactionLevel"] == "minimum"
    assert "raw_openai_response_text" not in str(run.model_invocation)
    assert any(event.action == "AGENT_RUN_RECORDED" for event in repository.audit_events)


def test_workflow_recovers_large_semantic_prompt_with_compacted_retry(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_SEMANTIC_INPUT_TOKEN_BUDGET", "1400")

    class LargeMetadataGateway:
        def collect_procedure_metadata(
            self,
            *,
            db_profile_id: str,
            schema: str,
            procedure_name: str,
        ) -> MetadataCollectionResult:
            return MetadataCollectionResult(
                db_profile_id=db_profile_id,
                object_ref=f"{schema}.{procedure_name}",
                snapshot_id="snapshot-large-workflow",
                collected_at="2026-05-17T00:00:00Z",
                evidence_refs=tuple(
                    {
                        "type": "MSSQL_METADATA",
                        "objectRef": f"dbo.InvoiceNode{i}",
                        "locator": f"mssql-mcp#/dependencies/{i}",
                    }
                    for i in range(180)
                ),
                procedure_definition={
                    "definitionHash": "hash-large-workflow",
                    "definition": (
                        "CREATE PROCEDURE dbo.usp_GetOrderSummary AS\n"
                        "SELECT OrderId FROM dbo.InvoiceSchedule;"
                    ),
                    "hasDefinitionAccess": True,
                },
                deterministic_facts=tuple(
                    {
                        "id": f"fact.invoice.{i}",
                        "fact_type": "TABLE_READ" if i % 2 else "TABLE_WRITE",
                        "summary": f"Invoice schedule deterministic fact {i}",
                    }
                    for i in range(240)
                ),
                dependency_evidence={
                    "toolName": "get_dependency_closure",
                    "rootObject": {
                        "database": "master",
                        "schema": schema,
                        "name": procedure_name,
                        "objectType": "PROCEDURE",
                    },
                    "summary": {"maxDepth": 2, "nodeCount": 400, "edgeCount": 600},
                    "nodes": [
                        {
                            "id": f"master.dbo.InvoiceNode{i}:TABLE",
                            "schema": "dbo",
                            "name": f"InvoiceNode{i}",
                            "objectType": "TABLE",
                            "evidenceRefs": [
                                {
                                    "objectRef": f"dbo.InvoiceNode{i}",
                                    "locator": f"mssql-mcp#/nodes/{i}",
                                }
                            ],
                        }
                        for i in range(400)
                    ],
                    "edges": [
                        {
                            "from": "master.dbo.usp_GetOrderSummary:PROCEDURE",
                            "to": f"master.dbo.InvoiceNode{i}:TABLE",
                            "dependencyType": "REFERENCE",
                            "resolutionStatus": "CONFIRMED",
                            "evidenceRefs": [
                                {
                                    "objectRef": f"dbo.InvoiceNode{i}",
                                    "locator": f"mssql-mcp#/edges/{i}",
                                }
                            ],
                        }
                        for i in range(600)
                    ],
                    "unresolved": [],
                    "evidenceRefs": [],
                },
                table_schemas=tuple(
                    {
                        "schema": "dbo",
                        "tableName": f"InvoiceTable{table}",
                        "columns": [
                            {
                                "name": f"Column{column}",
                                "dataType": "nvarchar(200)",
                                "description": "Invoice schedule description " * 8,
                            }
                            for column in range(60)
                        ],
                    }
                    for table in range(16)
                ),
            )

        def collect_procedure_definition(
            self,
            *,
            db_profile_id: str,
            schema: str,
            procedure_name: str,
            referenced_database: str | None = None,
        ) -> dict[str, object]:
            return {
                "data": {
                    "definition": "CREATE PROCEDURE dbo.usp_Child AS SELECT 1;",
                    "definitionHash": "hash-child",
                    "hasDefinitionAccess": True,
                },
                "evidenceRefs": [],
            }

    class CompactRetryGateway:
        provider = "pgpt"

        def __init__(self) -> None:
            self.payloads: list[dict[str, object]] = []

        def invoke_semantic_analysis(self, *, prompt, profile) -> ModelInvocationRecord:
            payload = json.loads(prompt.user_prompt)
            self.payloads.append(payload)
            if not payload["metadata"].get("promptCompaction"):
                raise ModelGatewayError(
                    "OpenAI Responses API returned an error.",
                    code="OPENAI_HTTP_400",
                    provider_error={"code": "context_length_exceeded"},
                )
            assert "CREATE PROCEDURE" not in prompt.user_prompt
            ref = payload["evidenceRefContract"]["allowedFactIds"][0]
            structured_output = {
                "businessRules": [
                    {
                        "category": "WORKFLOW_COMPACT_RETRY_RULE",
                        "summary": "압축된 근거로 초안 분석을 진행했습니다.",
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
                provider=self.provider,
                structured_output=structured_output,
            )

    repository = MemoryWorkflowRepository()
    gateway = CompactRetryGateway()
    service = WorkflowService(
        repository,
        metadata_gateway=LargeMetadataGateway(),
        model_gateway=gateway,
    )

    _request_record, job = service.submit_sp_analysis(_llm_request(["SP_ANALYSIS_DOCUMENT"]))

    assert job.status == JobStatus.VALIDATION_COMPLETE
    assert any(payload["metadata"].get("promptCompaction") for payload in gateway.payloads)
    run = next(
        run
        for run in repository.list_agent_runs(job.job_id)
        if run.agent_type == "LLM_SEMANTIC_ANALYST"
    )
    assert run.model_invocation["sourceContextSummary"]["promptCompaction"]["applied"] is True
    assert repository.list_job_artifacts(job.job_id)


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


def test_artifact_publish_state_blocks_validation_mutation() -> None:
    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)
    service.submit_sp_analysis(_request(["SP_ANALYSIS_DOCUMENT"]))
    artifact = next(iter(repository.artifacts.values()))
    artifact.status = ArtifactStatus.PUBLISHED

    with pytest.raises(WorkflowStateError, match="publish transitions are blocked"):
        service.validate_artifact(artifact.artifact_id)


def test_table_metadata_placeholder_uses_persisted_artifact_enum() -> None:
    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)

    service.submit_sp_analysis(_request(["TABLE_COLUMN_METADATA"]))

    assert {artifact.type for artifact in repository.artifacts.values()} == {
        ArtifactType.METADATA_QUERY_RESULT,
    }
    assert all("quality_summary" in artifact.content for artifact in repository.artifacts.values())
    assert all("evidence caveat" in artifact.content for artifact in repository.artifacts.values())


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
    assert "quality_summary" in contents
    assert "evidence_map" in contents
    assert "known_caveats" in contents
    assert "draft_readiness" in contents
    assert "DYNAMIC_SQL_SIGNAL" in contents
    assert "FIXTURE_AMBIGUOUS" in contents
    assert "resolve_dependency_reference" not in contents
    assert any(
        "dependencies" in ref["locator"]
        for artifact in repository.artifacts.values()
        for ref in artifact.evidence_refs
    )



def test_validation_only_workflow_has_no_approval_audit_events() -> None:
    repository = MemoryWorkflowRepository()
    service = WorkflowService(repository)
    service.submit_sp_analysis(_request(["SP_ANALYSIS_DOCUMENT"]))

    assert not any(
        event.action == "APPROVAL_DECISION_RECORDED"
        for event in repository.audit_events
    )
    assert all(
        artifact.status != ArtifactStatus.PUBLISHED
        for artifact in repository.artifacts.values()
    )
