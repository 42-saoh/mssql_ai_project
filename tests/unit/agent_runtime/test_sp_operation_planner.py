from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import httpx
import yaml
from ai_agent_runtime import (
    BRANCH_PLANNER_AGENT_TYPE,
    FakeModelGateway,
    ModelGatewayError,
    REPAIR_AGENT_TYPE,
    build_sp_operation_model_run,
    build_sp_operation_model_run_result,
)
from ai_agent_runtime.gateway import OpenAIModelGateway, model_profile_from_env
from ai_agent_runtime.models import AgentRunStatus, ModelInvocationRecord, stable_json_hash
from ai_agent_runtime.operation_model import (
    all_sp_operation_model_evidence_refs,
    validate_sp_operation_model_output,
)
from ai_agent_runtime.operation_planner import (
    EVIDENCE_REPAIRED_MARKER,
    VALIDATOR_REPAIRED_MARKER,
    OperationModelPlanningError,
)
from ai_agent_runtime.prompts import render_sp_operation_model_prompt

FIXTURE_PATH = Path("fixtures/eval/sp_operation_model_p41_manage_bond_v1.yaml")


def _fixture_operation_model() -> dict[str, Any]:
    payload = yaml.safe_load(FIXTURE_PATH.read_text(encoding="utf-8"))
    return deepcopy(payload["operation_model"])


def _statement_evidence(payload: dict[str, Any]) -> list[dict[str, Any]]:
    return deepcopy(payload["statementEvidence"])


def _allowed_refs(payload: dict[str, Any]) -> list[str]:
    model = validate_sp_operation_model_output(payload)
    return sorted(set(all_sp_operation_model_evidence_refs(model)))


def _operation_model_with_unknown_dto_ref(payload: dict[str, Any]) -> dict[str, Any]:
    dirty = deepcopy(payload)
    dirty["operations"][0]["dtoBlueprintRefs"] = ["MissingBranchCommand"]
    return dirty


def test_operation_model_prompt_uses_sanitized_statement_evidence_contract() -> None:
    payload = _fixture_operation_model()
    prompt = render_sp_operation_model_prompt(
        target_ref=payload["targetRef"],
        statement_evidence=_statement_evidence(payload),
        allowed_evidence_refs=_allowed_refs(payload),
    )

    prompt_payload = json.loads(prompt.user_prompt)

    assert prompt.output_schema_version == "schema:sp_operation_model@0.1.0"
    assert prompt_payload["dtoBlueprintPolicy"]["mustNotCollapseToSingleDto"] is True
    assert (
        prompt_payload["operationSeparationPolicy"]["mustCoverEveryStatementEvidenceId"]
        is True
    )
    assert prompt_payload["operationSeparationPolicy"]["branchCoverage"]["statementIds"]
    assert prompt_payload["evidenceRefContract"]["allowedFactIds"]
    assert "CREATE PROCEDURE" not in prompt.user_prompt
    assert "raw SQL" in prompt.system_prompt
    assert prompt.metadata["statementEvidenceCount"] == len(payload["statementEvidence"])


def test_operation_model_prompt_supports_split_and_repair_task_modes() -> None:
    payload = _fixture_operation_model()
    statements = _statement_evidence(payload)
    allowed_refs = _allowed_refs(payload)

    branch_prompt = render_sp_operation_model_prompt(
        target_ref=payload["targetRef"],
        statement_evidence=statements,
        allowed_evidence_refs=allowed_refs,
        task_mode="branch_plan",
        stage="operation_model_branch_plan",
    )
    final_prompt = render_sp_operation_model_prompt(
        target_ref=payload["targetRef"],
        statement_evidence=statements,
        allowed_evidence_refs=allowed_refs,
        task_mode="final_model",
        branch_plan_context={"operationCount": 10, "source": BRANCH_PLANNER_AGENT_TYPE},
    )
    repair_prompt = render_sp_operation_model_prompt(
        target_ref=payload["targetRef"],
        statement_evidence=statements,
        allowed_evidence_refs=allowed_refs,
        task_mode="repair",
        stage="operation_model_repair",
        branch_plan_context={"operationCount": 10, "source": BRANCH_PLANNER_AGENT_TYPE},
        repair_context={
            "validationFindings": ["operations must not be empty."],
            "rawFailedOutputIncluded": False,
        },
    )

    branch_payload = json.loads(branch_prompt.user_prompt)
    final_payload = json.loads(final_prompt.user_prompt)
    repair_payload = json.loads(repair_prompt.user_prompt)

    assert branch_payload["taskMode"] == "branch_plan"
    assert final_payload["taskMode"] == "final_model"
    assert repair_payload["taskMode"] == "repair"
    assert any(
        "operations[].dtoBlueprintRefs value must exactly match a dtoBlueprints[].name"
        in requirement
        for requirement in branch_payload["taskModeInstructions"]["requirements"]
    )
    assert any(
        "dtoBlueprints[].operationIds value must exactly match an operations[].operationId"
        in requirement
        for requirement in branch_payload["taskModeInstructions"]["requirements"]
    )
    assert final_payload["branchPlanContext"]["source"] == BRANCH_PLANNER_AGENT_TYPE
    assert repair_payload["repairContext"]["rawFailedOutputIncluded"] is False
    assert "failed provider payload text" in repair_prompt.user_prompt
    assert "CREATE PROCEDURE" not in branch_prompt.user_prompt
    assert "CREATE PROCEDURE" not in final_prompt.user_prompt
    assert "CREATE PROCEDURE" not in repair_prompt.user_prompt


def test_build_sp_operation_model_run_keeps_multi_dto_blueprints_with_fake_gateway() -> None:
    payload = _fixture_operation_model()
    run = build_sp_operation_model_run(
        target_ref=payload["targetRef"],
        statement_evidence=_statement_evidence(payload),
        allowed_evidence_refs=_allowed_refs(payload),
        model_gateway=FakeModelGateway(
            sp_operation_model_by_target_ref={payload["targetRef"]: payload}
        ),
        profile_id="openai_fast_test",
    )

    roles = {dto["role"] for dto in run.structured_output["dtoBlueprints"]}
    dto_names = {dto["name"] for dto in run.structured_output["dtoBlueprints"]}

    assert run.agent_type == "LLM_SP_OPERATION_PLANNER"
    assert run.structured_output["productionReady"] is False
    assert {"QUERY", "RESULT", "COMMAND", "BATCH_ITEM", "CALL_REQUEST"} <= roles
    assert "ManageBondSearchCriteria" in dto_names
    assert "ManageBondSearchRow" in dto_names
    assert "ManageBondDTO" not in dto_names


def test_operation_model_run_records_branch_sidecar_for_complex_sp() -> None:
    payload = _fixture_operation_model()
    result = build_sp_operation_model_run_result(
        target_ref=payload["targetRef"],
        statement_evidence=_statement_evidence(payload),
        allowed_evidence_refs=_allowed_refs(payload),
        model_gateway=FakeModelGateway(
            sp_operation_model_by_target_ref={payload["targetRef"]: payload}
        ),
        profile_id="openai_fast_test",
    )

    assert [run.agent_type for run in result.sidecar_runs] == [BRANCH_PLANNER_AGENT_TYPE]
    assert result.final_run.agent_type == "LLM_SP_OPERATION_PLANNER"
    assert result.sidecar_runs[0].structured_output["targetRef"] == payload["targetRef"]


def test_operation_model_run_repairs_branch_plan_validation_failure() -> None:
    payload = _fixture_operation_model()
    dirty_branch_plan = _operation_model_with_unknown_dto_ref(payload)
    gateway = _SequencedOperationGateway([dirty_branch_plan, payload])

    result = build_sp_operation_model_run_result(
        target_ref=payload["targetRef"],
        statement_evidence=_statement_evidence(payload),
        allowed_evidence_refs=_allowed_refs(payload),
        model_gateway=gateway,
        profile_id="openai_fast_test",
    )

    assert [run.agent_type for run in result.sidecar_runs] == [
        BRANCH_PLANNER_AGENT_TYPE,
        REPAIR_AGENT_TYPE,
    ]
    assert result.sidecar_runs[0].status == AgentRunStatus.FAILED
    assert result.sidecar_runs[1].status == AgentRunStatus.SUCCEEDED
    assert result.final_run.agent_type == "LLM_SP_OPERATION_PLANNER"
    assert VALIDATOR_REPAIRED_MARKER in result.final_run.structured_output["reviewMarkers"]
    assert [payload["taskMode"] for payload in gateway.prompt_payloads] == [
        "branch_plan",
        "repair",
    ]
    serialized = json.dumps(
        {
            "repairPrompt": gateway.prompt_payloads[1],
            "result": result.final_run.to_storage_dict(),
            "sidecars": [run.to_storage_dict() for run in result.sidecar_runs],
        },
        ensure_ascii=False,
    )
    assert "MissingBranchCommand" in serialized
    assert "dtoBlueprintRefs contains unknown DTOs" in serialized
    assert "CREATE PROCEDURE" not in serialized
    assert "raw provider response" not in serialized
    assert gateway.prompt_payloads[1]["repairContext"]["rawFailedOutputIncluded"] is False


def test_operation_model_run_preserves_review_required_when_branch_plan_repair_fails() -> None:
    payload = _fixture_operation_model()
    dirty_branch_plan = _operation_model_with_unknown_dto_ref(payload)
    gateway = _SequencedOperationGateway(
        [
            dirty_branch_plan,
            ModelGatewayError(
                "repair invalid",
                code="OPENAI_SP_OPERATION_MODEL_INVALID",
                provider_error={
                    "findings": ["dtoBlueprints must not be empty."],
                    "stage": "operation_model_repair",
                    "schemaName": "sp_operation_model",
                },
            ),
        ]
    )

    try:
        build_sp_operation_model_run_result(
            target_ref=payload["targetRef"],
            statement_evidence=_statement_evidence(payload),
            allowed_evidence_refs=_allowed_refs(payload),
            model_gateway=gateway,
            profile_id="openai_fast_test",
        )
    except OperationModelPlanningError as exc:
        assert exc.code == "OPENAI_SP_OPERATION_MODEL_INVALID"
        assert [run.agent_type for run in exc.sidecar_runs] == [
            BRANCH_PLANNER_AGENT_TYPE,
            REPAIR_AGENT_TYPE,
        ]
        assert exc.sidecar_runs[0].status == AgentRunStatus.FAILED
        assert exc.sidecar_runs[1].status == AgentRunStatus.FAILED
        serialized = json.dumps(
            {
                "promptPayloads": gateway.prompt_payloads,
                "sidecars": [run.to_storage_dict() for run in exc.sidecar_runs],
            },
            ensure_ascii=False,
        )
        assert "MissingBranchCommand" in serialized
        assert "dtoBlueprints must not be empty" in serialized
        assert "CREATE PROCEDURE" not in serialized
    else:
        raise AssertionError("Expected operation-model planning to fail after repair.")


def test_operation_model_run_repairs_invalid_evidence_refs_at_boundary() -> None:
    payload = _fixture_operation_model()
    dirty = deepcopy(payload)
    dirty["evidenceRefs"] = ["ev.not_allowed"]
    dirty["operations"][0]["evidenceRefs"] = ["ev.not_allowed"]
    dirty["operations"][0]["branchCondition"]["evidenceRefs"] = ["ev.not_allowed"]
    dirty["dtoBlueprints"][0]["fields"][0]["evidenceRefs"] = ["ev.not_allowed"]

    run = build_sp_operation_model_run(
        target_ref=payload["targetRef"],
        statement_evidence=_statement_evidence(payload),
        allowed_evidence_refs=_allowed_refs(payload),
        model_gateway=FakeModelGateway(
            sp_operation_model_by_target_ref={payload["targetRef"]: dirty}
        ),
        profile_id="openai_fast_test",
    )

    assert EVIDENCE_REPAIRED_MARKER in run.structured_output["reviewMarkers"]
    assert run.model_invocation.component_invocations[-1]["component"] == (
        "sp_operation_model_evidence_guard"
    )
    assert "ev.not_allowed" not in str(run.to_storage_dict())


def test_operation_model_run_repairs_structural_validation_failure_without_raw_payload() -> None:
    payload = _fixture_operation_model()
    gateway = _SequencedOperationGateway(
        [
            payload,
            ModelGatewayError(
                "invalid operation model",
                code="OPENAI_SP_OPERATION_MODEL_INVALID",
                provider_error={
                    "type": "openai_agents_structured_adapter",
                    "stage": "sp_operation_model",
                    "schemaName": "sp_operation_model",
                    "findingCount": 3,
                    "findings": [
                        "operations must not be empty.",
                        "CREATE PROCEDURE dbo.secret-token raw provider response",
                    ],
                },
            ),
            payload,
        ]
    )

    result = build_sp_operation_model_run_result(
        target_ref=payload["targetRef"],
        statement_evidence=_statement_evidence(payload),
        allowed_evidence_refs=_allowed_refs(payload),
        model_gateway=gateway,
        profile_id="openai_fast_test",
    )

    assert [run.agent_type for run in result.sidecar_runs] == [
        BRANCH_PLANNER_AGENT_TYPE,
        REPAIR_AGENT_TYPE,
    ]
    assert result.final_run.agent_type == "LLM_SP_OPERATION_PLANNER"
    assert VALIDATOR_REPAIRED_MARKER in result.final_run.structured_output["reviewMarkers"]
    repair_prompt_payload = gateway.prompt_payloads[2]
    serialized = json.dumps(
        {
            "repairPrompt": repair_prompt_payload,
            "result": result.final_run.to_storage_dict(),
            "sidecars": [run.to_storage_dict() for run in result.sidecar_runs],
        },
        ensure_ascii=False,
    )
    assert "operations must not be empty" in serialized
    assert "CREATE PROCEDURE" not in serialized
    assert "secret-token" not in serialized
    assert "raw provider response" not in serialized
    assert repair_prompt_payload["repairContext"]["rawFailedOutputIncluded"] is False


def test_operation_model_run_preserves_review_required_when_validator_repair_fails() -> None:
    payload = _fixture_operation_model()
    gateway = _SequencedOperationGateway(
        [
            payload,
            ModelGatewayError(
                "invalid operation model",
                code="OPENAI_SP_OPERATION_MODEL_INVALID",
                provider_error={
                    "findings": ["operations must not be empty."],
                    "stage": "sp_operation_model",
                    "schemaName": "sp_operation_model",
                },
            ),
            ModelGatewayError(
                "repair invalid",
                code="OPENAI_SP_OPERATION_MODEL_INVALID",
                provider_error={
                    "findings": ["dtoBlueprints must not be empty."],
                    "stage": "operation_model_repair",
                    "schemaName": "sp_operation_model",
                },
            ),
        ]
    )

    try:
        build_sp_operation_model_run_result(
            target_ref=payload["targetRef"],
            statement_evidence=_statement_evidence(payload),
            allowed_evidence_refs=_allowed_refs(payload),
            model_gateway=gateway,
            profile_id="openai_fast_test",
        )
    except OperationModelPlanningError as exc:
        assert exc.code == "OPENAI_SP_OPERATION_MODEL_INVALID"
        assert [run.agent_type for run in exc.sidecar_runs] == [
            BRANCH_PLANNER_AGENT_TYPE,
            REPAIR_AGENT_TYPE,
        ]
        assert exc.sidecar_runs[-1].status == AgentRunStatus.FAILED
        serialized = json.dumps(
            [run.to_storage_dict() for run in exc.sidecar_runs],
            ensure_ascii=False,
        )
        assert "dtoBlueprints must not be empty" in serialized
        assert "CREATE PROCEDURE" not in serialized
    else:
        raise AssertionError("Expected operation-model planning to fail after repair.")


def test_openai_gateway_uses_responses_json_schema_for_operation_model(monkeypatch: Any) -> None:
    payload = _fixture_operation_model()
    captured = _capture_post(monkeypatch, _json_response(payload))
    monkeypatch.delenv("LLM_REMOTE_PROVIDER", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.test/v1")

    prompt = render_sp_operation_model_prompt(
        target_ref=payload["targetRef"],
        statement_evidence=_statement_evidence(payload),
        allowed_evidence_refs=_allowed_refs(payload),
    )
    result = OpenAIModelGateway(timeout_seconds=1).plan_sp_operation_model(
        prompt=prompt,
        profile=model_profile_from_env("openai_fast_test"),
    )

    assert captured["json"]["text"]["format"]["name"] == "sp_operation_model"
    assert (
        captured["json"]["text"]["format"]["schema"]["properties"]["productionReady"]["const"]
        is False
    )
    assert result.structured_output["targetRef"] == payload["targetRef"]


def test_openai_gateway_normalizes_operation_model_schema_drift(monkeypatch: Any) -> None:
    payload = _fixture_operation_model()
    dirty = deepcopy(payload)
    dirty["reviewMarkers"] = [
        {"code": "TARGET_REF_REVIEW_REQUIRED", "status": "REVIEW_REQUIRED"}
    ]
    removed_statement = dirty["statementEvidence"].pop(0)
    dirty["operations"][0]["statementRefs"] = [removed_statement["statementId"]]
    dirty["operations"][0]["dtoBlueprintRefs"] = [
        f"dto.{dirty['operations'][0]['dtoBlueprintRefs'][0]}"
    ]
    dirty["operations"][0]["koreanName"] = "search"
    dirty["operations"][0]["reviewMarkers"] = ["LLM_BUSINESS_NAMING_REVIEW_REQUIRED"]
    dirty["operations"][0]["branchCondition"]["evidence_refs"] = dirty["operations"][0][
        "branchCondition"
    ].pop("evidenceRefs")
    dirty["statementEvidence"][0]["outputs"] = ["FROM"]
    dirty["statementEvidence"][0]["target_ref"] = dirty["statementEvidence"][0].pop(
        "targetRef"
    )
    dirty["dtoBlueprints"][0]["operation_ids"] = dirty["dtoBlueprints"][0].pop(
        "operationIds"
    )
    dirty["dtoBlueprints"][0]["fields"][0]["db_type"] = dirty["dtoBlueprints"][0]["fields"][
        0
    ].pop("dbType")
    captured = _capture_post(monkeypatch, _json_response(dirty))
    monkeypatch.delenv("LLM_REMOTE_PROVIDER", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.openai.test/v1")

    prompt = render_sp_operation_model_prompt(
        target_ref=payload["targetRef"],
        statement_evidence=_statement_evidence(payload),
        allowed_evidence_refs=_allowed_refs(payload),
    )
    result = OpenAIModelGateway(timeout_seconds=1).plan_sp_operation_model(
        prompt=prompt,
        profile=model_profile_from_env("openai_fast_test"),
    )

    assert captured["json"]["text"]["format"]["name"] == "sp_operation_model"
    assert result.structured_output["targetRef"] == payload["targetRef"]
    assert "koreanName" not in str(result.structured_output)
    assert "TARGET_REF_REVIEW_REQUIRED" in result.structured_output["reviewMarkers"]
    assert "LLM_BUSINESS_NAMING_REVIEW_REQUIRED" in result.structured_output["operations"][0][
        "riskMarkers"
    ]
    assert removed_statement["statementId"] in result.structured_output["operations"][0][
        "statementRefs"
    ]
    assert removed_statement["statementId"] in {
        item["statementId"] for item in result.structured_output["statementEvidence"]
    }
    assert not result.structured_output["operations"][0]["dtoBlueprintRefs"][0].startswith(
        "dto."
    )
    assert "FROM" not in result.structured_output["statementEvidence"][0]["outputs"]
    assert result.structured_output["statementEvidence"][0]["targetRef"]
    assert result.structured_output["dtoBlueprints"][0]["operationIds"]
    assert result.structured_output["dtoBlueprints"][0]["fields"][0]["dbType"]
    assert result.component_invocations[-1]["action"] == "normalized_sp_operation_model"


def _json_response(output: dict[str, Any]) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "id": "resp_test",
            "output_text": json.dumps(output),
            "usage": {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3},
        },
        request=httpx.Request("POST", "https://api.openai.test/v1/responses"),
    )


def _capture_post(monkeypatch: Any, response: httpx.Response) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    def fake_post(
        url: str,
        *,
        headers: dict[str, str],
        json: dict[str, Any],
        timeout: float,
    ) -> httpx.Response:
        captured["url"] = url
        captured["headers"] = dict(headers)
        captured["json"] = dict(json)
        captured["timeout"] = timeout
        return response

    monkeypatch.setattr("ai_agent_runtime.gateway.httpx.post", fake_post)
    return captured


class _SequencedOperationGateway:
    provider = "sequenced-operation-model"

    def __init__(self, outputs: list[Any]) -> None:
        self.outputs = list(outputs)
        self.prompt_payloads: list[dict[str, Any]] = []

    def plan_sp_operation_model(
        self,
        *,
        prompt: Any,
        profile: Any,
    ) -> ModelInvocationRecord:
        self.prompt_payloads.append(json.loads(prompt.user_prompt))
        output = self.outputs.pop(0)
        if isinstance(output, Exception):
            raise output
        structured_output = deepcopy(output)
        return ModelInvocationRecord(
            provider=self.provider,
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
            provider_request_id="seq-operation-model",
        )
