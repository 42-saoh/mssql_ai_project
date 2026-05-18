from __future__ import annotations

import json
from copy import deepcopy
from typing import Any

from ai_agent_domain import ArtifactType, JobStatus
from ai_agent_generation import GenerationContext
from ai_agent_runtime import (
    BaselineResponsesFrameworkAdapter,
    FakeAiGenerationFrameworkAdapter,
    FakeModelGateway,
    build_ai_java_mybatis_draft_pack_run,
)
from ai_agent_validation import validate_ai_java_mybatis_draft_pack_quality
from ai_agent_validation.models import ValidationReport, ValidationStatus
from api_app.workflow import (
    AI_DRAFT_PACK_PLANNER_AGENT_TYPE,
    WorkflowService,
    ai_draft_pack_allowed_evidence_refs,
    ai_draft_pack_context,
    ai_draft_pack_expected_inventory,
    ai_draft_pack_quality_gates,
)

from tests.helpers.p42_manage_bond import (
    ManageBondMetadataGateway,
    manage_bond_request,
    p41_operation_model_fixture,
    p42_ai_draft_pack_fixture,
    p42_pack_from_persisted_artifacts,
)
from tests.unit.api.fake_repository import MemoryWorkflowRepository


QUALITY_SCORE_KEYS = (
    "requiredDtoFileCoverage",
    "requiredServiceMethodCoverage",
    "requiredMapperMethodCoverage",
    "requiredReviewMarkerCoverage",
)


def test_p43e_manage_bond_replay_preserves_p42_quality_for_baseline_and_candidate() -> None:
    baseline = _run_manage_bond_replay(
        adapter_kind="baseline",
        candidate_framework="baseline_internal_responses_gateway",
    )
    candidate = _run_manage_bond_replay(
        adapter_kind="candidate",
        candidate_framework="openai_agents_sdk_fake",
    )

    _assert_quality_preserved_or_improved(
        baseline=baseline["report"],
        candidate=candidate["report"],
    )
    assert candidate["reconstructed_pack"]["qualityGates"] == baseline[
        "reconstructed_pack"
    ]["qualityGates"]
    assert len(_dto_files(candidate["reconstructed_pack"])) == len(
        candidate["reconstructed_pack"]["qualityGates"]["requiredDtoClasses"]
    )
    assert [component["stage"] for component in candidate["adapter_components"]] == [
        "file_inventory",
        "file_content",
    ]
    assert {component["candidateFramework"] for component in candidate["adapter_components"]} == {
        "openai_agents_sdk_fake"
    }
    _assert_no_collapsed_or_fallback_pack(candidate["reconstructed_pack"])
    _assert_no_raw_trace_leakage(candidate["stored_invocation"])


def test_p43e_synthetic_replay_proves_candidate_is_not_manage_bond_answer_key() -> None:
    context = _synthetic_generation_context()
    expected_inventory = ai_draft_pack_expected_inventory(context)
    quality_gates = ai_draft_pack_quality_gates(context, expected_inventory)
    pack = _pack_from_inventory(
        target_ref=context.operation_model["targetRef"],
        expected_inventory=expected_inventory,
        quality_gates=quality_gates,
    )
    baseline = _run_synthetic_adapter_replay(
        context=context,
        expected_inventory=expected_inventory,
        quality_gates=quality_gates,
        adapter=BaselineResponsesFrameworkAdapter(
            model_gateway=FakeModelGateway(
                ai_draft_pack_by_target_ref={pack["targetRef"]: pack}
            )
        ),
        pack=pack,
    )
    candidate = _run_synthetic_adapter_replay(
        context=context,
        expected_inventory=expected_inventory,
        quality_gates=quality_gates,
        adapter=FakeAiGenerationFrameworkAdapter(
            output=pack,
            candidate_framework="langgraph_fake",
        ),
        pack=pack,
    )

    assert "ManageBond" not in json.dumps(pack, ensure_ascii=False)
    assert len(_dto_files(candidate["run"].structured_output)) > 2
    assert candidate["run"].structured_output["qualityGates"] == quality_gates
    _assert_quality_preserved_or_improved(
        baseline=baseline["report"],
        candidate=candidate["report"],
    )
    _assert_no_collapsed_or_fallback_pack(candidate["run"].structured_output)
    _assert_no_raw_trace_leakage(
        json.dumps(candidate["run"].model_invocation.to_storage_dict(), ensure_ascii=False)
    )


def test_p43e_synthetic_two_dto_collapse_fails_generic_p42_quality_gate() -> None:
    context = _synthetic_generation_context()
    expected_inventory = ai_draft_pack_expected_inventory(context)
    quality_gates = ai_draft_pack_quality_gates(context, expected_inventory)
    pack = _pack_from_inventory(
        target_ref=context.operation_model["targetRef"],
        expected_inventory=expected_inventory,
        quality_gates=quality_gates,
    )
    collapsed = _collapse_to_two_dtos(pack)

    result = _run_synthetic_adapter_replay(
        context=context,
        expected_inventory=expected_inventory,
        quality_gates=quality_gates,
        adapter=FakeAiGenerationFrameworkAdapter(
            output=collapsed,
            candidate_framework="openai_agents_sdk_fake",
        ),
        pack=collapsed,
    )

    report = result["report"]
    messages = " ".join(check.message for check in report.failed_checks)
    assert report.status == ValidationStatus.FAILED
    assert result["run"].structured_output["qualityGates"] == quality_gates
    assert "missing DTO files" in messages
    assert "ManageBond" not in json.dumps(collapsed, ensure_ascii=False)
    _assert_no_raw_trace_leakage(
        json.dumps(result["run"].model_invocation.to_storage_dict(), ensure_ascii=False)
    )


def _run_manage_bond_replay(
    *,
    adapter_kind: str,
    candidate_framework: str,
) -> dict[str, Any]:
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
    adapter_components = [
        component
        for component in ai_draft_run.model_invocation["componentInvocations"]
        if component.get("component") == "ai_generation_framework_adapter"
    ]

    assert job.status == JobStatus.VALIDATION_COMPLETE
    assert report.status == ValidationStatus.PASSED
    assert {artifact.type for artifact in artifacts if artifact.type in _draft_types()} == {
        ArtifactType.DTO_DRAFT,
        ArtifactType.SERVICE_DRAFT,
        ArtifactType.MAPPER_INTERFACE,
        ArtifactType.MAPPER_XML,
    }
    return {
        "report": report,
        "reconstructed_pack": reconstructed,
        "adapter_components": adapter_components,
        "stored_invocation": json.dumps(ai_draft_run.model_invocation, ensure_ascii=False),
    }


def _run_synthetic_adapter_replay(
    *,
    context: GenerationContext,
    expected_inventory: list[dict[str, Any]],
    quality_gates: dict[str, Any],
    adapter: Any,
    pack: dict[str, Any],
) -> dict[str, Any]:
    sanitized_context = ai_draft_pack_context(context)
    allowed_refs = ai_draft_pack_allowed_evidence_refs(
        context=sanitized_context,
        expected_inventory=expected_inventory,
    )
    run = build_ai_java_mybatis_draft_pack_run(
        target_ref=pack["targetRef"],
        sanitized_draft_context=sanitized_context,
        expected_inventory=expected_inventory,
        quality_gates=quality_gates,
        model_gateway=FakeModelGateway(ai_draft_pack_by_target_ref={pack["targetRef"]: pack}),
        profile_id="openai_fast_test",
        allowed_evidence_refs=allowed_refs,
        framework_adapter=adapter,
        run_file_inventory_stage=True,
    )
    return {
        "run": run,
        "report": validate_ai_java_mybatis_draft_pack_quality(run.structured_output),
    }


def _synthetic_generation_context() -> GenerationContext:
    target_ref = "dbo.usp_SyntheticComplexOrder_PRC"
    operation_model = {
        "schemaVersion": "SpOperationModel.v0.1",
        "targetRef": target_ref,
        "operations": [
            {
                "operationId": "op.syntheticOrderSearch",
                "statementRefs": ["stmt.synthetic.s001"],
                "dtoBlueprintRefs": [
                    "SyntheticOrderSearchCriteria",
                    "SyntheticOrderSearchRow",
                ],
            },
            {
                "operationId": "op.approveSyntheticOrder",
                "statementRefs": ["stmt.synthetic.s002"],
                "dtoBlueprintRefs": ["ApproveSyntheticOrderCommand"],
            },
            {
                "operationId": "op.syncSyntheticOrderAudit",
                "statementRefs": ["stmt.synthetic.s003"],
                "dtoBlueprintRefs": ["SyntheticOrderAuditCallRequest"],
            },
        ],
        "statementEvidence": [
            {
                "statementId": "stmt.synthetic.s001",
                "operation": "SELECT",
                "phase": "synthetic order search",
                "evidenceRefs": ["fixture.synthetic.s001"],
            },
            {
                "statementId": "stmt.synthetic.s002",
                "operation": "UPDATE",
                "phase": "approve synthetic order",
                "evidenceRefs": ["fixture.synthetic.s002"],
            },
            {
                "statementId": "stmt.synthetic.s003",
                "operation": "EXECUTE",
                "phase": "sync synthetic order audit",
                "evidenceRefs": ["fixture.synthetic.s003"],
            },
        ],
        "dtoBlueprints": [
            _dto_blueprint(
                "SyntheticOrderSearchCriteria",
                "QUERY",
                ["op.syntheticOrderSearch"],
                ["ContractNum", "StatusCode"],
                ["fixture.synthetic.s001"],
            ),
            _dto_blueprint(
                "SyntheticOrderSearchRow",
                "RESULT",
                ["op.syntheticOrderSearch"],
                ["ContractNum", "OrderStatus"],
                ["fixture.synthetic.s001"],
            ),
            _dto_blueprint(
                "ApproveSyntheticOrderCommand",
                "COMMAND",
                ["op.approveSyntheticOrder"],
                ["ContractNum", "ApprovalYN"],
                ["fixture.synthetic.s002"],
                ["TRANSACTION_BOUNDARY_REVIEW_REQUIRED"],
            ),
            _dto_blueprint(
                "SyntheticOrderAuditCallRequest",
                "CALL_REQUEST",
                ["op.syncSyntheticOrderAudit"],
                ["ContractNum", "AuditUserId"],
                ["fixture.synthetic.s003"],
                ["CALLED_PROCEDURE_IO_REVIEW_REQUIRED"],
            ),
        ],
        "reviewMarkers": [
            "CROSS_DB_WRITE_REVIEW_REQUIRED",
            "CALLED_PROCEDURE_IO_REVIEW_REQUIRED",
            "TVF_OR_PROCEDURE_KIND_REVIEW_REQUIRED",
            "TRANSACTION_BOUNDARY_REVIEW_REQUIRED",
        ],
    }
    return GenerationContext.from_mapping(
        {
            "sampleId": "p43e-synthetic-complex-sp",
            "request": {
                "entityName": "SyntheticOrder",
                "spName": target_ref,
                "operationModel": operation_model,
            },
        }
    )


def _dto_blueprint(
    name: str,
    role: str,
    operation_ids: list[str],
    fields: list[str],
    evidence_refs: list[str],
    review_markers: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "role": role,
        "operationIds": operation_ids,
        "fields": [{"name": field} for field in fields],
        "evidenceRefs": evidence_refs,
        "reviewMarkers": list(review_markers or []),
    }


def _pack_from_inventory(
    *,
    target_ref: str,
    expected_inventory: list[dict[str, Any]],
    quality_gates: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schemaVersion": "AiJavaMyBatisDraftPack.v0.1",
        "contractTarget": "AiJavaMyBatisDraftPack",
        "targetRef": target_ref,
        "sourcePolicy": "sanitized_facts_only",
        "productionReady": False,
        "files": [_materialized_file(file) for file in expected_inventory],
        "evidenceRefs": _inventory_evidence_refs(expected_inventory),
        "reviewMarkers": list(quality_gates["requiredReviewMarkers"]),
        "qualityGates": deepcopy(quality_gates),
        "assumptions": ["P43E replay fixture uses sanitized fake adapter output only."],
    }


def _materialized_file(file: dict[str, Any]) -> dict[str, Any]:
    payload = {
        "artifactType": file["artifactType"],
        "path": file["path"],
        "role": file["role"],
        "className": file["className"],
        "content": _materialized_content(file),
        "operationIds": list(file["operationIds"]),
        "evidenceRefs": list(file["evidenceRefs"]),
        "reviewMarkers": list(file.get("reviewMarkers") or []),
    }
    for key in ("dtoRole", "requiredFields", "references"):
        if key in file:
            payload[key] = deepcopy(file[key])
    return payload


def _materialized_content(file: dict[str, Any]) -> str:
    artifact_type = file["artifactType"]
    class_name = file["className"]
    if artifact_type == ArtifactType.DTO_DRAFT.value:
        fields = "\n".join(
            f"    private String {field};" for field in file.get("requiredFields", [])
        )
        return (
            f"public class {class_name} {{\n"
            "    // REVIEW_REQUIRED draft DTO backed by sanitized evidence.\n"
            f"{fields}\n"
            "}"
        )
    references = " ".join(file.get("references") or ())
    methods = "\n".join(
        f"    public void {operation_id}() {{}}"
        for operation_id in file.get("operationIds", [])
    )
    if artifact_type == ArtifactType.SERVICE_DRAFT.value:
        return (
            f"public class {class_name} {{\n"
            f"    // REVIEW_REQUIRED DTO references: {references}\n"
            f"{methods}\n"
            "}"
        )
    if artifact_type == ArtifactType.MAPPER_INTERFACE.value:
        return (
            f"public interface {class_name} {{\n"
            f"    // REVIEW_REQUIRED DTO references: {references}\n"
            f"{methods}\n"
            "}"
        )
    statements = "\n".join(
        f'  <select id="{operation_id}">/* SQL_SKELETON_REVIEW_REQUIRED */</select>'
        for operation_id in file.get("operationIds", [])
    )
    return (
        '<mapper namespace="SyntheticOrderMapper">\n'
        f"  <!-- REVIEW_REQUIRED DTO references: {references} -->\n"
        f"{statements}\n"
        "</mapper>"
    )


def _inventory_evidence_refs(inventory: list[dict[str, Any]]) -> list[str]:
    refs: list[str] = []
    for item in inventory:
        refs.extend(str(ref) for ref in item.get("evidenceRefs", []) if str(ref).strip())
    return list(dict.fromkeys(refs))


def _collapse_to_two_dtos(pack: dict[str, Any]) -> dict[str, Any]:
    collapsed = deepcopy(pack)
    dto_files = _dto_files(collapsed)[:2]
    non_dto_files = [
        file for file in collapsed["files"] if file["artifactType"] != ArtifactType.DTO_DRAFT.value
    ]
    kept_dtos = [file["className"] for file in dto_files]
    for file in non_dto_files:
        file["references"] = list(kept_dtos)
        file["content"] = _materialized_content(file)
    collapsed["files"] = [*dto_files, *non_dto_files]
    collapsed["qualityGates"]["requiredDtoClasses"] = list(kept_dtos)
    return collapsed


def _assert_quality_preserved_or_improved(
    *,
    baseline: ValidationReport,
    candidate: ValidationReport,
) -> None:
    assert baseline.status == ValidationStatus.PASSED
    assert candidate.status == ValidationStatus.PASSED
    baseline_scores = baseline.metadata["scores"]
    candidate_scores = candidate.metadata["scores"]
    for key in QUALITY_SCORE_KEYS:
        assert candidate_scores[key] >= baseline_scores[key]
    assert candidate_scores["expectedDtoArtifactRows"] >= baseline_scores[
        "expectedDtoArtifactRows"
    ]
    assert candidate_scores["singleDtoCollapseAllowed"] is False
    assert candidate_scores["operationModelFallbackAllowed"] is False


def _assert_no_collapsed_or_fallback_pack(pack: dict[str, Any]) -> None:
    generated_payload = json.dumps(
        {
            "files": pack["files"],
            "reviewMarkers": pack.get("reviewMarkers", []),
            "assumptions": pack.get("assumptions", []),
        },
        ensure_ascii=False,
    )
    dto_classes = [file["className"] for file in _dto_files(pack)]
    assert "OperationModelReviewRequired" not in generated_payload
    assert "ManageBondDTO" not in generated_payload
    assert not any(
        class_name.endswith("DTO") and len(dto_classes) == 1
        for class_name in dto_classes
    )
    assert all(str(file.get("content") or "").strip() for file in pack["files"])
    assert len(dto_classes) > 2
    assert len(dto_classes) == len(set(dto_classes))


def _assert_no_raw_trace_leakage(serialized: str) -> None:
    lowered = serialized.lower()
    forbidden = (
        "raw_prompt",
        "raw provider response",
        "raw_provider_response",
        "raw_sp_definition",
        "raw guide body",
        "create procedure",
        "row data",
        "procedure execution",
        "generated source apply",
        "deploy generated source",
        "secret",
        "password",
    )
    for marker in forbidden:
        assert marker not in lowered


def _dto_files(pack: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        file
        for file in pack["files"]
        if file["artifactType"] == ArtifactType.DTO_DRAFT.value
    ]


def _draft_types() -> set[ArtifactType]:
    return {
        ArtifactType.DTO_DRAFT,
        ArtifactType.SERVICE_DRAFT,
        ArtifactType.MAPPER_INTERFACE,
        ArtifactType.MAPPER_XML,
    }
