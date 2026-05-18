from __future__ import annotations

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import httpx
import yaml
from ai_agent_runtime import (
    FakeModelGateway,
    build_sp_operation_model_run,
)
from ai_agent_runtime.gateway import OpenAIModelGateway, model_profile_from_env
from ai_agent_runtime.operation_model import (
    all_sp_operation_model_evidence_refs,
    validate_sp_operation_model_output,
)
from ai_agent_runtime.operation_planner import EVIDENCE_REPAIRED_MARKER
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
