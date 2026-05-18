from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import yaml
from ai_agent_runtime import (
    AI_GENERATION_FRAMEWORK_ADAPTER_VERSION,
    AiDraftPackValidationError,
    AiGenerationFrameworkAdapterRequest,
    BaselineResponsesFrameworkAdapter,
    FakeAiGenerationFrameworkAdapter,
    FakeModelGateway,
    ModelGatewayError,
    ModelProfile,
    P43_FRAMEWORK_RAW_TRACE_BLOCKED,
    P43_FRAMEWORK_TOOL_CONTEXT_BLOCKED,
    build_framework_tool_context,
    build_ai_java_mybatis_draft_pack_run,
    summarize_framework_trace,
    validate_framework_tool_context,
    validate_framework_trace_summary,
)
from ai_agent_runtime.prompts import render_ai_java_mybatis_draft_pack_prompt
from ai_agent_validation import validate_ai_java_mybatis_draft_pack_quality
from ai_agent_validation.models import ValidationStatus

FIXTURE_PATH = Path("fixtures/eval/ai_draft_pack_p42_manage_bond_v1.yaml")


def _fixture() -> dict[str, Any]:
    return yaml.safe_load(FIXTURE_PATH.read_text(encoding="utf-8"))


def _valid_pack() -> dict[str, Any]:
    fixture = _fixture()
    target = fixture["ai_draft_pack_quality_target"]
    quality_gates = fixture["quality_gates"]
    return {
        "schemaVersion": target["schemaVersion"],
        "contractTarget": target["contractTarget"],
        "targetRef": target["targetRef"],
        "sourcePolicy": target["sourcePolicy"],
        "productionReady": target["productionReady"],
        "files": [_file_with_content(file) for file in target["expectedFiles"]],
        "evidenceRefs": list(target["evidenceRefs"]),
        "reviewMarkers": list(target["reviewMarkers"]),
        "qualityGates": {
            "requiredDtoClasses": list(quality_gates["required_dto_classes"]),
            "requiredServiceMethods": list(quality_gates["required_service_methods"]),
            "requiredMapperMethods": list(quality_gates["required_mapper_methods"]),
            "requiredReviewMarkers": list(target["reviewMarkers"]),
            "blockerPatterns": list(quality_gates["blocker_patterns"]),
            "blankContentIsBlocker": bool(quality_gates["blank_content_is_blocker"]),
            "dtoCollapseIsBlocker": bool(quality_gates["dto_collapse_is_blocker"]),
            "fallbackSkeletonPersistenceAllowedOnFailure": bool(
                quality_gates["fallback_skeleton_persistence_allowed_on_failure"]
            ),
        },
        "assumptions": ["P43B adapter fixture pack is draft-only and productionReady=false."],
    }


def _file_with_content(file: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "artifactType": file["artifactType"],
        "path": file["path"],
        "role": file["role"],
        "className": file["className"],
        "content": _content_for(file),
        "operationIds": list(file["operationIds"]),
        "evidenceRefs": list(file["evidenceRefs"]),
        "reviewMarkers": list(file.get("reviewMarkers") or []),
    }
    for optional_key in ("dtoRole", "requiredFields", "references"):
        if optional_key in file:
            payload[optional_key] = deepcopy(file[optional_key])
    return payload


def _content_for(file: dict[str, Any]) -> str:
    artifact_type = file["artifactType"]
    class_name = file["className"]
    if artifact_type == "DTO_DRAFT":
        fields = "\n".join(f"    private String {field};" for field in file["requiredFields"])
        return (
            f"public class {class_name} {{\n"
            "    // REVIEW_REQUIRED draft DTO backed by sanitized evidence.\n"
            f"{fields}\n"
            "}"
        )
    if artifact_type == "MAPPER_XML":
        references = " ".join(file["references"])
        statements = "\n".join(
            f'  <select id="{operation_id}" parameterType="map" resultType="map">'
            "/* SQL_SKELETON_REVIEW_REQUIRED */</select>"
            for operation_id in file["operationIds"]
        )
        return (
            '<mapper namespace="ManageBondMapper">\n'
            f"  <!-- REVIEW_REQUIRED DTO references: {references} -->\n"
            f"{statements}\n"
            "</mapper>"
        )
    references = " ".join(file.get("references") or ())
    methods = "\n".join(
        f"    public void {operation_id}() {{}}" for operation_id in file["operationIds"]
    )
    if artifact_type == "MAPPER_INTERFACE":
        return (
            f"public interface {class_name} {{\n"
            f"    // REVIEW_REQUIRED DTO references: {references}\n"
            f"{methods}\n"
            "}"
        )
    return (
        f"public class {class_name} {{\n"
        f"    // REVIEW_REQUIRED DTO references: {references}\n"
        f"{methods}\n"
        "}"
    )


def _allowed_refs(payload: dict[str, Any]) -> list[str]:
    refs = list(payload["evidenceRefs"])
    for file in payload["files"]:
        refs.extend(file["evidenceRefs"])
    return sorted(set(refs))


def _expected_inventory() -> list[dict[str, Any]]:
    return list(_fixture()["ai_draft_pack_quality_target"]["expectedFiles"])


def _prompt(payload: dict[str, Any], *, stage: str = "file_content"):
    fixture = _fixture()
    return render_ai_java_mybatis_draft_pack_prompt(
        target_ref=payload["targetRef"],
        sanitized_draft_context={
            "targetRef": payload["targetRef"],
            "branchVariables": fixture["guide_quality_facts"]["branch_variables"],
            "reviewRequiredFacts": fixture["guide_quality_facts"]["review_required_facts"],
        },
        expected_inventory=_expected_inventory(),
        quality_gates=payload["qualityGates"],
        allowed_evidence_refs=_allowed_refs(payload),
        stage=stage,
    )


def _profile() -> ModelProfile:
    return ModelProfile(
        profile_id="fake_framework_adapter",
        model="fake",
        registry_ref="model:fake_framework_adapter@0.1.0",
        reasoning_effort="none",
    )


def _request(
    payload: dict[str, Any],
    *,
    stage: str = "file_content",
    sanitized_context: dict[str, Any] | None = None,
    repair_context: dict[str, Any] | None = None,
):
    return AiGenerationFrameworkAdapterRequest(
        target_ref=payload["targetRef"],
        sanitized_draft_context=sanitized_context or {"targetRef": payload["targetRef"]},
        expected_inventory=_expected_inventory(),
        quality_gates=payload["qualityGates"],
        allowed_evidence_refs=_allowed_refs(payload),
        prompt=_prompt(payload, stage=stage),
        profile=_profile(),
        stage=stage,
        repair_context=repair_context,
    )


def _build_run_with_adapter(payload: dict[str, Any], adapter: FakeAiGenerationFrameworkAdapter):
    return build_ai_java_mybatis_draft_pack_run(
        target_ref=payload["targetRef"],
        sanitized_draft_context={"targetRef": payload["targetRef"]},
        expected_inventory=_expected_inventory(),
        quality_gates=_valid_pack()["qualityGates"],
        model_gateway=FakeModelGateway(),
        profile_id="openai_fast_test",
        allowed_evidence_refs=_allowed_refs(_valid_pack()),
        framework_adapter=adapter,
    )


def _build_run_with_file_inventory_stage(
    payload: dict[str, Any],
    adapter: Any,
):
    return build_ai_java_mybatis_draft_pack_run(
        target_ref=payload["targetRef"],
        sanitized_draft_context={"targetRef": payload["targetRef"]},
        expected_inventory=_expected_inventory(),
        quality_gates=_valid_pack()["qualityGates"],
        model_gateway=FakeModelGateway(
            ai_draft_pack_by_target_ref={payload["targetRef"]: payload}
        ),
        profile_id="openai_fast_test",
        allowed_evidence_refs=_allowed_refs(_valid_pack()),
        framework_adapter=adapter,
        run_file_inventory_stage=True,
    )


def test_baseline_adapter_wraps_existing_responses_gateway() -> None:
    payload = _valid_pack()
    adapter = BaselineResponsesFrameworkAdapter(
        model_gateway=FakeModelGateway(
            ai_draft_pack_by_target_ref={payload["targetRef"]: payload}
        )
    )

    invocation = adapter.draft_file_content(request=_request(payload))

    assert invocation.structured_output["targetRef"] == payload["targetRef"]
    assert invocation.structured_output["productionReady"] is False
    component = invocation.component_invocations[-1]
    assert component["adapterContract"] == AI_GENERATION_FRAMEWORK_ADAPTER_VERSION
    assert component["candidateFramework"] == "baseline_internal_responses_gateway"
    assert component["stage"] == "file_content"
    assert component["traceHash"]


def test_sanitized_framework_tool_context_excludes_raw_prompt_text() -> None:
    payload = _valid_pack()
    sanitized_context = {
        "targetRef": payload["targetRef"],
        "inputParams": [{"name": "ContractNum"}],
        "resultShape": ["ContractNum"],
        "allowedEvidenceRefs": _allowed_refs(payload),
        "operationModelSummary": {
            "schemaVersion": "SpOperationModel.v0.1",
            "reviewMarkers": ["TRANSACTION_BOUNDARY_REVIEW_REQUIRED"],
        },
        "operations": [
            {
                "operationId": "readBond",
                "statementRefs": ["stmt.read"],
                "dtoBlueprintRefs": ["ManageBondSearchCriteria"],
            }
        ],
        "dtoBlueprints": [{"name": "ManageBondSearchCriteria"}],
        "statementEvidence": [{"statementId": "stmt.read", "operation": "SELECT"}],
        "dependencyEvidenceSummary": {"evidenceRefs": ["dep.ref"]},
    }
    request = _request(payload, sanitized_context=sanitized_context)

    context = validate_framework_tool_context(request)
    context_text = json.dumps(context, ensure_ascii=False)

    assert context == build_framework_tool_context(request)
    assert context["targetRefHash"]
    assert context["stage"] == "file_content"
    assert context["operationSummary"]["operationIds"] == ["readBond"]
    assert context["operationSummary"]["statementIds"] == ["stmt.read"]
    assert context["metadataSummary"]["inputParamCount"] == 1
    assert context["deterministicInventoryContract"]
    assert "user_prompt" not in context_text
    assert "system_prompt" not in context_text
    assert request.prompt.user_prompt not in context_text


@pytest.mark.parametrize(
    ("sanitized_context", "repair_context"),
    [
        ({"targetRef": "dbo.safe", "raw_prompt": "never store"}, None),
        ({"targetRef": "dbo.safe", "rowData": [{"id": 1}]}, None),
        ({"targetRef": "dbo.safe", "note": "procedure execution was attempted"}, None),
        ({"targetRef": "dbo.safe", "note": "generated source apply succeeded"}, None),
        ({"targetRef": "dbo.safe", "note": "deploy generated source"}, None),
        ({"targetRef": "dbo.safe"}, {"failedPayload": "public class Leak {}"}),
        ({"targetRef": "dbo.safe"}, {"failedXml": "<mapper namespace=\"Leak\" />"}),
    ],
)
def test_framework_tool_context_blocks_unsafe_request_material(
    sanitized_context: dict[str, Any],
    repair_context: dict[str, Any] | None,
) -> None:
    payload = _valid_pack()
    request = _request(
        payload,
        stage="repair" if repair_context else "file_content",
        sanitized_context=sanitized_context,
        repair_context=repair_context,
    )
    adapter = FakeAiGenerationFrameworkAdapter(output=payload)

    with pytest.raises(ModelGatewayError) as exc:
        if repair_context:
            adapter.repair_draft_pack(request=request)
        else:
            adapter.draft_file_content(request=request)

    diagnostics = json.dumps(exc.value.provider_error, ensure_ascii=False)
    assert exc.value.code == P43_FRAMEWORK_TOOL_CONTEXT_BLOCKED
    assert "never store" not in diagnostics
    assert "public class" not in diagnostics
    assert "<mapper" not in diagnostics


def test_adapter_routed_planner_runs_file_inventory_before_file_content() -> None:
    payload = _valid_pack()
    adapter = BaselineResponsesFrameworkAdapter(
        model_gateway=FakeModelGateway(
            ai_draft_pack_by_target_ref={payload["targetRef"]: payload}
        )
    )

    run = _build_run_with_file_inventory_stage(payload, adapter)

    stages = [
        component["stage"]
        for component in run.model_invocation.component_invocations
        if component.get("component") == "ai_generation_framework_adapter"
    ]
    assert stages == ["file_inventory", "file_content"]
    assert run.structured_output["productionReady"] is False


def test_fake_candidate_adapters_represent_policy_safe_staged_runs() -> None:
    payload = _valid_pack()
    for candidate in ("openai_agents_sdk_fake", "langgraph_fake"):
        adapter = FakeAiGenerationFrameworkAdapter(
            output=payload,
            candidate_framework=candidate,
            trace_events=({"eventType": "agent_loop", "blockerIds": []},),
        )

        run = _build_run_with_file_inventory_stage(payload, adapter)
        stages = [
            component["stage"]
            for component in run.model_invocation.component_invocations
            if component.get("component") == "ai_generation_framework_adapter"
        ]

        assert stages == ["file_inventory", "file_content"]
        assert run.structured_output["schemaVersion"] == "AiJavaMyBatisDraftPack.v0.1"
        assert run.model_invocation.component_invocations[0]["candidateFramework"] == candidate
        assert validate_ai_java_mybatis_draft_pack_quality(
            run.structured_output
        ).status == ValidationStatus.PASSED


def test_adapter_routed_repair_stage_uses_repair_draft_pack() -> None:
    payload = _valid_pack()
    adapter = FakeAiGenerationFrameworkAdapter(
        stage_outputs={"repair": payload},
        candidate_framework="langgraph_fake",
    )

    run = build_ai_java_mybatis_draft_pack_run(
        target_ref=payload["targetRef"],
        sanitized_draft_context={"targetRef": payload["targetRef"]},
        expected_inventory=_expected_inventory(),
        quality_gates=payload["qualityGates"],
        model_gateway=FakeModelGateway(),
        profile_id="openai_fast_test",
        allowed_evidence_refs=_allowed_refs(payload),
        repair_context={
            "failureStage": "deterministic_quality_validation",
            "errorCode": "AI_DRAFT_PACK_QUALITY_GATE_FAILED",
        },
        framework_adapter=adapter,
    )

    stages = [
        component["stage"]
        for component in run.model_invocation.component_invocations
        if component.get("component") == "ai_generation_framework_adapter"
    ]
    assert stages == ["repair"]
    assert run.model_invocation.component_invocations[-1]["component"] == (
        "ai_draft_pack_repair_stage"
    )
    assert validate_ai_java_mybatis_draft_pack_quality(
        run.structured_output
    ).status == ValidationStatus.PASSED


def test_schema_invalid_adapter_output_cannot_bypass_repair_retry() -> None:
    payload = _valid_pack()
    repair_invalid = deepcopy(payload)
    repair_invalid["productionReady"] = True
    adapter = FakeAiGenerationFrameworkAdapter(
        stage_outputs={
            "file_content": {"not": "an-ai-draft-pack"},
            "repair": repair_invalid,
        }
    )

    with pytest.raises(AiDraftPackValidationError) as exc:
        _build_run_with_adapter(payload, adapter)

    assert "productionReady must be false" in str(exc.value)


def test_two_dto_collapse_still_fails_p42_quality_gate() -> None:
    payload = _valid_pack()
    collapsed = deepcopy(payload)
    dto_files = [file for file in collapsed["files"] if file["artifactType"] == "DTO_DRAFT"][:2]
    non_dto_files = [file for file in collapsed["files"] if file["artifactType"] != "DTO_DRAFT"]
    kept_dtos = [file["className"] for file in dto_files]
    for file in non_dto_files:
        file["references"] = list(kept_dtos)
    collapsed["files"] = [*dto_files, *non_dto_files]
    collapsed["qualityGates"]["requiredDtoClasses"] = list(kept_dtos)
    adapter = FakeAiGenerationFrameworkAdapter(output=collapsed)

    run = _build_run_with_adapter(payload, adapter)
    report = validate_ai_java_mybatis_draft_pack_quality(run.structured_output)

    assert report.status == ValidationStatus.FAILED
    assert "requiredDtoClasses missing DTO files" in " ".join(
        check.message for check in report.failed_checks
    )


def test_missing_review_required_markers_still_fail_p42_quality_gate() -> None:
    payload = _valid_pack()
    missing_markers = deepcopy(payload)
    missing_markers["reviewMarkers"] = []
    missing_markers["qualityGates"]["requiredReviewMarkers"] = []
    for file in missing_markers["files"]:
        file["reviewMarkers"] = []
    adapter = FakeAiGenerationFrameworkAdapter(output=missing_markers)

    run = _build_run_with_adapter(payload, adapter)
    report = validate_ai_java_mybatis_draft_pack_quality(run.structured_output)

    assert report.status == ValidationStatus.FAILED
    assert "required REVIEW_REQUIRED markers missing" in " ".join(
        check.message for check in report.failed_checks
    )


def test_raw_framework_trace_leakage_is_blocked_before_storage() -> None:
    payload = _valid_pack()
    adapter = FakeAiGenerationFrameworkAdapter(
        output=payload,
        trace_events=(
            {
                "eventType": "unsafe_trace",
                "raw_provider_response": "CREATE PROCEDURE dbo.Leak password=supersecret",
            },
        ),
    )

    with pytest.raises(ModelGatewayError) as exc:
        adapter.draft_file_content(request=_request(payload))

    assert exc.value.code == P43_FRAMEWORK_RAW_TRACE_BLOCKED
    diagnostics = json.dumps(exc.value.provider_error, ensure_ascii=False)
    assert "CREATE PROCEDURE" not in diagnostics
    assert "supersecret" not in diagnostics
    assert "raw_provider_response" not in diagnostics


def test_trace_summary_accepts_hashes_counts_codes_and_metrics_only() -> None:
    summary = summarize_framework_trace(
        adapter_id="openai_agents_sdk_fake",
        candidate_framework="openai_agents_sdk_fake",
        target_ref="dbo.SafeProc",
        stage="file_content",
        status="SUCCEEDED",
        events=(
            {
                "componentId": "draft_stage",
                "fileCount": 14,
                "latencyMs": 42,
                "blockerIds": ["P43_FRAMEWORK_QUALITY_REGRESSION"],
                "failureCode": "P43_FRAMEWORK_QUALITY_REGRESSION",
            },
        ),
    )

    assert validate_framework_trace_summary(summary) == summary
    assert summary["componentIds"] == ["draft_stage"]
    assert summary["blockerIds"] == ["P43_FRAMEWORK_QUALITY_REGRESSION"]
    assert summary["failureCodes"] == ["P43_FRAMEWORK_QUALITY_REGRESSION"]
    assert summary["metrics"] == {"fileCount": 14, "latencyMs": 42}
    assert summary["traceHash"]
    assert "events" not in summary


def test_trace_summary_rejects_extra_fields_and_unsafe_values() -> None:
    safe = summarize_framework_trace(
        adapter_id="langgraph_fake",
        candidate_framework="langgraph_fake",
        target_ref="dbo.SafeProc",
        stage="repair",
        status="FAILED",
        events=({"componentId": "repair_stage", "errorCode": "P43_FRAMEWORK_BLOCKED"},),
    )
    unsafe = dict(safe)
    unsafe["rawEvent"] = {"raw_provider_response": "CREATE PROCEDURE dbo.Leak"}

    with pytest.raises(ModelGatewayError) as exc:
        validate_framework_trace_summary(unsafe)

    diagnostics = json.dumps(exc.value.provider_error, ensure_ascii=False)
    assert exc.value.code == P43_FRAMEWORK_RAW_TRACE_BLOCKED
    assert "raw_provider_response" not in diagnostics
    assert "CREATE PROCEDURE" not in diagnostics
    assert "rawEvent" not in diagnostics


def test_adapter_storage_summary_contains_hashes_not_raw_trace_payloads() -> None:
    payload = _valid_pack()
    adapter = FakeAiGenerationFrameworkAdapter(
        output=payload,
        trace_events=(
            {
                "eventType": "policy_safe_trace",
                "componentId": "draft_stage",
                "blockerIds": ["P43_FRAMEWORK_QUALITY_REGRESSION"],
            },
        ),
    )

    run = _build_run_with_adapter(payload, adapter)
    stored = run.model_invocation.to_storage_dict()
    stored_text = json.dumps(stored, ensure_ascii=False)
    component = stored["componentInvocations"][0]

    assert component["traceHash"]
    assert component["blockerIds"] == ["P43_FRAMEWORK_QUALITY_REGRESSION"]
    assert "eventType" not in component
    assert "raw_prompt" not in stored_text
    assert "raw_provider_response" not in stored_text
    assert "raw_sp_definition" not in stored_text
    assert "CREATE PROCEDURE" not in stored_text
    assert "row data" not in stored_text
    assert "procedure execution" not in stored_text
