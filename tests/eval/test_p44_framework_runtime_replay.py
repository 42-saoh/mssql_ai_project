from __future__ import annotations

import json
from types import SimpleNamespace
from typing import Any

from ai_agent_domain import ArtifactType, JobStatus
from ai_agent_runtime import (
    FakeModelGateway,
    LangGraphAiDraftPackOrchestrator,
    OpenAIAgentsFrameworkAdapter,
)
from ai_agent_validation import validate_ai_java_mybatis_draft_pack_quality
from ai_agent_validation.models import ValidationStatus
from api_app.workflow import (
    AI_DRAFT_PACK_PLANNER_AGENT_TYPE,
    WorkflowService,
    ai_draft_pack_allowed_evidence_refs,
    ai_draft_pack_context,
    ai_draft_pack_expected_inventory,
    ai_draft_pack_quality_gates,
)

from tests.helpers.framework_replay import (
    assert_no_collapsed_or_fallback_pack as _assert_no_collapsed_or_fallback_pack,
    assert_no_raw_trace_leakage as _assert_no_raw_trace_leakage,
    collapse_to_two_dtos as _collapse_to_two_dtos,
    dto_files as _dto_files,
    materialized_file as _materialized_file,
    pack_from_inventory as _pack_from_inventory,
    synthetic_generation_context as _synthetic_generation_context,
)
from tests.helpers.p42_manage_bond import (
    ManageBondMetadataGateway,
    manage_bond_request,
    p41_operation_model_fixture,
    p42_ai_draft_pack_fixture,
    p42_pack_from_persisted_artifacts,
)
from tests.unit.api.fake_repository import MemoryWorkflowRepository


def test_p44_manage_bond_runs_through_openai_agents_and_langgraph_runtime() -> None:
    operation_model = p41_operation_model_fixture()
    ai_draft_pack = p42_ai_draft_pack_fixture()
    gateway = FakeModelGateway(
        sp_operation_model_by_target_ref={operation_model["targetRef"]: operation_model},
    )
    adapter = _mock_agents_adapter({"default": ai_draft_pack})
    repository = MemoryWorkflowRepository()
    service = WorkflowService(
        repository,
        metadata_gateway=ManageBondMetadataGateway(),
        model_gateway=gateway,
        ai_generation_framework_adapter=adapter,
        ai_draft_pack_orchestrator=LangGraphAiDraftPackOrchestrator(
            framework_adapter=adapter
        ),
    )

    _request_record, job = service.submit_sp_analysis(manage_bond_request())

    artifacts = repository.list_job_artifacts(job.job_id) or []
    reconstructed = p42_pack_from_persisted_artifacts(
        artifacts,
        expected_pack=ai_draft_pack,
    )
    report = validate_ai_java_mybatis_draft_pack_quality(reconstructed)
    ai_draft_run = next(
        run
        for run in repository.list_agent_runs(job.job_id) or []
        if run.agent_type == AI_DRAFT_PACK_PLANNER_AGENT_TYPE
    )
    components = ai_draft_run.model_invocation["componentInvocations"]
    adapter_components = [
        component
        for component in components
        if component.get("component") == "ai_generation_framework_adapter"
    ]
    graph_component = components[-1]

    assert job.status == JobStatus.VALIDATION_COMPLETE
    assert report.status == ValidationStatus.PASSED
    assert {artifact.type for artifact in artifacts if artifact.type in _draft_types()} == {
        ArtifactType.DTO_DRAFT,
        ArtifactType.SERVICE_DRAFT,
        ArtifactType.MAPPER_INTERFACE,
        ArtifactType.MAPPER_XML,
    }
    assert [component["stage"] for component in adapter_components] == [
        "file_inventory",
        "file_content",
    ]
    assert {component["candidateFramework"] for component in adapter_components} == {
        "openai_agents_sdk"
    }
    assert graph_component["component"] == "langgraph_ai_draft_pack_orchestrator"
    assert graph_component["checkpointer"] == "disabled"
    assert graph_component["stageTrace"] == [
        "file_inventory",
        "file_content",
        "quality_gate",
        "final",
    ]
    _assert_no_collapsed_or_fallback_pack(reconstructed)
    _assert_no_raw_trace_leakage(json.dumps(ai_draft_run.model_invocation, ensure_ascii=False))


def test_p44_synthetic_complex_sp_uses_langgraph_without_manage_bond_hardcoding() -> None:
    context = _synthetic_generation_context()
    expected_inventory = ai_draft_pack_expected_inventory(context)
    quality_gates = ai_draft_pack_quality_gates(context, expected_inventory)
    pack = _pack_from_inventory(
        target_ref=context.operation_model["targetRef"],
        expected_inventory=expected_inventory,
        quality_gates=quality_gates,
    )
    adapter = _mock_agents_adapter({"default": pack})
    orchestrator = LangGraphAiDraftPackOrchestrator(framework_adapter=adapter)
    sanitized_context = ai_draft_pack_context(context)
    allowed_refs = ai_draft_pack_allowed_evidence_refs(
        context=sanitized_context,
        expected_inventory=expected_inventory,
    )

    run = orchestrator.build_run(
        target_ref=pack["targetRef"],
        sanitized_draft_context=sanitized_context,
        expected_inventory=expected_inventory,
        quality_gates=quality_gates,
        model_gateway=FakeModelGateway(),
        profile_id="openai_fast_test",
        allowed_evidence_refs=allowed_refs,
    )
    report = validate_ai_java_mybatis_draft_pack_quality(run.structured_output)

    assert report.status == ValidationStatus.PASSED
    assert "ManageBond" not in json.dumps(run.structured_output, ensure_ascii=False)
    assert len(_dto_files(run.structured_output)) > 2
    assert run.model_invocation.component_invocations[-1]["orchestrator"] == "langgraph"
    _assert_no_collapsed_or_fallback_pack(run.structured_output)
    _assert_no_raw_trace_leakage(
        json.dumps(run.model_invocation.to_storage_dict(), ensure_ascii=False)
    )


def test_p44_synthetic_two_dto_collapse_fails_generic_quality_gate() -> None:
    context = _synthetic_generation_context()
    expected_inventory = ai_draft_pack_expected_inventory(context)
    quality_gates = ai_draft_pack_quality_gates(context, expected_inventory)
    pack = _pack_from_inventory(
        target_ref=context.operation_model["targetRef"],
        expected_inventory=expected_inventory,
        quality_gates=quality_gates,
    )
    collapsed = _collapse_to_two_dtos(pack)
    adapter = _mock_agents_adapter(
        {
            "file_inventory": pack,
            "file_content": collapsed,
            "repair": collapsed,
        }
    )
    orchestrator = LangGraphAiDraftPackOrchestrator(framework_adapter=adapter)
    sanitized_context = ai_draft_pack_context(context)
    allowed_refs = ai_draft_pack_allowed_evidence_refs(
        context=sanitized_context,
        expected_inventory=expected_inventory,
    )

    run = orchestrator.build_run(
        target_ref=pack["targetRef"],
        sanitized_draft_context=sanitized_context,
        expected_inventory=expected_inventory,
        quality_gates=quality_gates,
        model_gateway=FakeModelGateway(),
        profile_id="openai_fast_test",
        allowed_evidence_refs=allowed_refs,
    )
    report = validate_ai_java_mybatis_draft_pack_quality(run.structured_output)
    messages = " ".join(check.message for check in report.failed_checks)

    assert report.status == ValidationStatus.FAILED
    assert "missing DTO files" in messages
    assert "ManageBond" not in json.dumps(collapsed, ensure_ascii=False)
    _assert_no_raw_trace_leakage(
        json.dumps(run.model_invocation.to_storage_dict(), ensure_ascii=False)
    )


def _mock_agents_adapter(stage_outputs: dict[str, dict[str, Any]]) -> OpenAIAgentsFrameworkAdapter:
    def agent_factory(request: Any) -> SimpleNamespace:
        return SimpleNamespace(stage=request.stage, request=request, name=f"mock-{request.stage}")

    def runner(agent: Any, _prompt: str, _run_config: Any) -> SimpleNamespace:
        output = (
            stage_outputs.get(agent.stage)
            or stage_outputs.get("default")
            or _pack_from_adapter_request(agent.request)
        )
        output = _with_allowed_evidence_refs(output, agent.request.allowed_evidence_refs)
        return SimpleNamespace(
            final_output=output,
            usage={"input_tokens": 3, "output_tokens": 5, "total_tokens": 8},
            response_id=f"resp_{agent.stage}",
        )

    return OpenAIAgentsFrameworkAdapter(runner=runner, agent_factory=agent_factory)


def _with_allowed_evidence_refs(
    pack: dict[str, Any],
    allowed_evidence_refs: list[str],
) -> dict[str, Any]:
    allowed = list(allowed_evidence_refs)
    fallback = allowed[:1]
    normalized = json.loads(json.dumps(pack))
    normalized["evidenceRefs"] = allowed or list(normalized.get("evidenceRefs") or [])
    for file in normalized.get("files", []):
        refs = [
            str(ref)
            for ref in file.get("evidenceRefs", [])
            if str(ref) in set(allowed)
        ]
        file["evidenceRefs"] = refs or fallback
    return normalized


def _pack_from_adapter_request(request: Any) -> dict[str, Any]:
    return {
        "schemaVersion": "AiJavaMyBatisDraftPack.v0.1",
        "contractTarget": "AiJavaMyBatisDraftPack",
        "targetRef": request.target_ref,
        "sourcePolicy": "sanitized_facts_only",
        "productionReady": False,
        "files": [_materialized_file(dict(file)) for file in request.expected_inventory],
        "evidenceRefs": list(request.allowed_evidence_refs),
        "reviewMarkers": list(request.quality_gates["requiredReviewMarkers"]),
        "qualityGates": dict(request.quality_gates),
        "assumptions": ["P44 mocked OpenAI Agents SDK output is draft-only."],
    }


def _draft_types() -> set[ArtifactType]:
    return {
        ArtifactType.DTO_DRAFT,
        ArtifactType.SERVICE_DRAFT,
        ArtifactType.MAPPER_INTERFACE,
        ArtifactType.MAPPER_XML,
    }
