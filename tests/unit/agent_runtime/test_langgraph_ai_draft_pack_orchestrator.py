from __future__ import annotations

import json
from copy import deepcopy

import pytest
from ai_agent_runtime import (
    P44_LANGGRAPH_ORCHESTRATOR_FAILED,
    FakeModelGateway,
    LangGraphAiDraftPackOrchestrator,
    ModelGatewayError,
)
from ai_agent_validation import validate_ai_java_mybatis_draft_pack_quality
from ai_agent_validation.models import ValidationStatus
from tests.helpers.framework_adapters import FakeAiGenerationFrameworkAdapter

from tests.unit.agent_runtime.test_framework_adapter import (
    _allowed_refs,
    _expected_inventory,
    _valid_pack,
)


def test_langgraph_orchestrator_runs_inventory_content_quality_final() -> None:
    payload = _valid_pack()
    orchestrator = LangGraphAiDraftPackOrchestrator(
        framework_adapter=FakeAiGenerationFrameworkAdapter(
            output=payload,
            candidate_framework="openai_agents_sdk",
        )
    )

    run = orchestrator.build_run(
        target_ref=payload["targetRef"],
        sanitized_draft_context={"targetRef": payload["targetRef"]},
        expected_inventory=_expected_inventory(),
        quality_gates=payload["qualityGates"],
        model_gateway=FakeModelGateway(),
        profile_id="openai_fast_test",
        allowed_evidence_refs=_allowed_refs(payload),
    )

    adapter_stages = _adapter_stages(run)
    langgraph_component = run.model_invocation.component_invocations[-1]
    assert adapter_stages == ["file_inventory", "file_content"]
    assert langgraph_component["component"] == "langgraph_ai_draft_pack_orchestrator"
    assert langgraph_component["orchestrator"] == "langgraph"
    assert langgraph_component["checkpointer"] == "disabled"
    assert langgraph_component["stageTrace"] == [
        "file_inventory",
        "file_content",
        "quality_gate",
        "final",
    ]
    assert langgraph_component["composerStages"] == [
        "dto_inventory",
        "dto_content",
        "service_content",
        "mapper_interface_content",
        "mapper_xml_content",
        "integration_quality_gate",
    ]
    assert langgraph_component["repairAttempted"] is False
    assert validate_ai_java_mybatis_draft_pack_quality(
        run.structured_output
    ).status == ValidationStatus.PASSED


def test_langgraph_orchestrator_routes_quality_failure_to_repair() -> None:
    payload = _valid_pack()
    weak_payload = deepcopy(payload)
    weak_payload["reviewMarkers"] = []
    weak_payload["qualityGates"]["requiredReviewMarkers"] = []
    for file in weak_payload["files"]:
        file["reviewMarkers"] = []
    orchestrator = LangGraphAiDraftPackOrchestrator(
        framework_adapter=FakeAiGenerationFrameworkAdapter(
            stage_outputs={
                "file_inventory": payload,
                "file_content": weak_payload,
                "repair": payload,
            },
            candidate_framework="openai_agents_sdk",
        )
    )

    run = orchestrator.build_run(
        target_ref=payload["targetRef"],
        sanitized_draft_context={"targetRef": payload["targetRef"]},
        expected_inventory=_expected_inventory(),
        quality_gates=payload["qualityGates"],
        model_gateway=FakeModelGateway(),
        profile_id="openai_fast_test",
        allowed_evidence_refs=_allowed_refs(payload),
    )

    langgraph_component = run.model_invocation.component_invocations[-1]
    assert _adapter_stages(run) == ["file_inventory", "file_content", "repair"]
    assert "repair" in langgraph_component["stageTrace"]
    assert langgraph_component["repairAttempted"] is True
    assert validate_ai_java_mybatis_draft_pack_quality(
        run.structured_output
    ).status == ValidationStatus.PASSED


def test_langgraph_orchestrator_routes_schema_failure_to_repair() -> None:
    payload = _valid_pack()
    orchestrator = LangGraphAiDraftPackOrchestrator(
        framework_adapter=FakeAiGenerationFrameworkAdapter(
            stage_outputs={
                "file_inventory": payload,
                "file_content": {"not": "an AiJavaMyBatisDraftPack"},
                "repair": payload,
            },
            candidate_framework="openai_agents_sdk",
        )
    )

    run = orchestrator.build_run(
        target_ref=payload["targetRef"],
        sanitized_draft_context={"targetRef": payload["targetRef"]},
        expected_inventory=_expected_inventory(),
        quality_gates=payload["qualityGates"],
        model_gateway=FakeModelGateway(),
        profile_id="openai_fast_test",
        allowed_evidence_refs=_allowed_refs(payload),
    )

    assert _adapter_stages(run) == ["file_inventory", "file_content", "repair"]
    assert run.model_invocation.component_invocations[-1]["repairAttempted"] is True
    assert validate_ai_java_mybatis_draft_pack_quality(
        run.structured_output
    ).status == ValidationStatus.PASSED


def test_langgraph_orchestrator_returns_failed_quality_to_workflow_gate() -> None:
    payload = _valid_pack()
    weak_payload = deepcopy(payload)
    weak_payload["reviewMarkers"] = []
    weak_payload["qualityGates"]["requiredReviewMarkers"] = []
    for file in weak_payload["files"]:
        file["reviewMarkers"] = []
    orchestrator = LangGraphAiDraftPackOrchestrator(
        framework_adapter=FakeAiGenerationFrameworkAdapter(
            stage_outputs={
                "file_inventory": payload,
                "file_content": weak_payload,
                "repair": weak_payload,
            },
            candidate_framework="openai_agents_sdk",
        )
    )

    run = orchestrator.build_run(
        target_ref=payload["targetRef"],
        sanitized_draft_context={"targetRef": payload["targetRef"]},
        expected_inventory=_expected_inventory(),
        quality_gates=payload["qualityGates"],
        model_gateway=FakeModelGateway(),
        profile_id="openai_fast_test",
        allowed_evidence_refs=_allowed_refs(payload),
    )

    report = validate_ai_java_mybatis_draft_pack_quality(run.structured_output)
    component = run.model_invocation.component_invocations[-1]
    assert report.status == ValidationStatus.FAILED
    assert component["qualityStatus"] == ValidationStatus.FAILED.value
    assert component["qualityFailedCheckCount"] > 0
    assert component["repairAttempted"] is True


def test_langgraph_orchestrator_failure_diagnostics_are_sanitized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    payload = _valid_pack()
    orchestrator = LangGraphAiDraftPackOrchestrator(
        framework_adapter=FakeAiGenerationFrameworkAdapter(output=payload)
    )
    monkeypatch.setattr(
        "ai_agent_runtime.ai_draft_pack_orchestrator._compile_langgraph",
        lambda **_kwargs: _NoOutputGraph(),
    )

    with pytest.raises(ModelGatewayError) as exc:
        orchestrator.build_run(
            target_ref=payload["targetRef"],
            sanitized_draft_context={"targetRef": payload["targetRef"]},
            expected_inventory=_expected_inventory(),
            quality_gates=payload["qualityGates"],
            model_gateway=FakeModelGateway(),
            profile_id="openai_fast_test",
            allowed_evidence_refs=_allowed_refs(payload),
        )

    diagnostics = json.dumps(exc.value.provider_error, ensure_ascii=False)
    assert exc.value.code == P44_LANGGRAPH_ORCHESTRATOR_FAILED
    assert "raw_prompt" not in diagnostics
    assert "CREATE PROCEDURE" not in diagnostics


def _adapter_stages(run) -> list[str]:
    return [
        component["stage"]
        for component in run.model_invocation.component_invocations
        if component.get("component") == "ai_generation_framework_adapter"
    ]


class _NoOutputGraph:
    def invoke(self, _state):
        return {"stageTrace": ["file_inventory", "final"]}
