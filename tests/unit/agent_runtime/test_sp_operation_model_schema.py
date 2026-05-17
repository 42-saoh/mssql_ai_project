from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import yaml

from ai_agent_runtime import (
    SP_OPERATION_PLANNER_OUTPUT_SCHEMA_VERSION,
    SP_OPERATION_PLANNER_PROMPT_VERSION,
    FakeModelGateway,
    ModelProfile,
    OperationModelValidationError,
    RenderedPrompt,
    all_sp_operation_model_evidence_refs,
    sp_operation_model_output_schema,
    validate_sp_operation_model_output,
)

FIXTURE_PATH = Path("fixtures/eval/sp_operation_model_p41_manage_bond_v1.yaml")


def _fixture_operation_model() -> dict[str, Any]:
    payload = yaml.safe_load(FIXTURE_PATH.read_text(encoding="utf-8"))
    return deepcopy(payload["operation_model"])


def _allowed_refs(payload: dict[str, Any]) -> list[str]:
    model = validate_sp_operation_model_output(payload)
    return sorted(set(all_sp_operation_model_evidence_refs(model)))


def _prompt(payload: dict[str, Any]) -> RenderedPrompt:
    return RenderedPrompt(
        prompt_version=SP_OPERATION_PLANNER_PROMPT_VERSION,
        output_schema_version=SP_OPERATION_PLANNER_OUTPUT_SCHEMA_VERSION,
        system_prompt="Return a strict SpOperationModel JSON object.",
        user_prompt="Use sanitized statement evidence only.",
        input_hash="p41b-input-hash",
        prompt_hash="p41b-prompt-hash",
        metadata={
            "targetRef": payload["targetRef"],
            "allowedEvidenceRefs": _allowed_refs(payload),
        },
    )


def test_sp_operation_model_output_schema_is_strict_and_constrained() -> None:
    schema = sp_operation_model_output_schema(["ev.allowed"])

    assert schema["additionalProperties"] is False
    assert schema["properties"]["schemaVersion"]["const"] == "SpOperationModel.v0.1"
    assert schema["properties"]["productionReady"]["const"] is False
    assert schema["properties"]["evidenceRefs"]["items"]["enum"] == ["ev.allowed"]
    dto_schema = schema["properties"]["dtoBlueprints"]["items"]
    assert dto_schema["additionalProperties"] is False
    assert "COMMAND" in dto_schema["properties"]["role"]["enum"]


def test_manage_bond_operation_model_validates_for_planner_output() -> None:
    payload = _fixture_operation_model()
    model = validate_sp_operation_model_output(payload, allowed_evidence_refs=_allowed_refs(payload))

    assert model.target_ref == "PPM.dbo.PCO_GU_ManageBond_PRC"
    assert model.production_ready is False
    assert len(model.operations) == 7
    assert len(model.dto_blueprints) >= 9


def test_fake_gateway_uses_sp_operation_model_schema_contract() -> None:
    payload = _fixture_operation_model()
    gateway = FakeModelGateway(sp_operation_model_by_target_ref={payload["targetRef"]: payload})
    profile = ModelProfile(
        profile_id="fake_gateway_fixture",
        model="fake",
        registry_ref="model:fake_gateway_fixture@0.1.0",
        reasoning_effort="none",
    )

    invocation = gateway.plan_sp_operation_model(prompt=_prompt(payload), profile=profile)

    assert invocation.output_schema_version == SP_OPERATION_PLANNER_OUTPUT_SCHEMA_VERSION
    assert invocation.structured_output["targetRef"] == payload["targetRef"]
    assert invocation.structured_output["productionReady"] is False


def test_invalid_dto_role_fails_deterministically() -> None:
    payload = _fixture_operation_model()
    payload["dtoBlueprints"][0]["role"] = "MEGA_DTO"

    with pytest.raises(OperationModelValidationError, match="schema validation failed"):
        FakeModelGateway(sp_operation_model_by_target_ref={payload["targetRef"]: payload})


def test_empty_nested_evidence_refs_fail_deterministically() -> None:
    payload = _fixture_operation_model()
    payload["dtoBlueprints"][0]["evidenceRefs"] = []

    with pytest.raises(OperationModelValidationError, match="evidenceRefs must not be empty"):
        validate_sp_operation_model_output(payload)


def test_unresolved_statement_and_dto_refs_fail_deterministically() -> None:
    payload = _fixture_operation_model()
    payload["operations"][0]["statementRefs"].append("stmt.missing")
    payload["operations"][0]["dtoBlueprintRefs"].append("MissingDto")

    with pytest.raises(OperationModelValidationError) as exc_info:
        validate_sp_operation_model_output(payload)

    message = str(exc_info.value)
    assert "unknown ids" in message
    assert "unknown DTOs" in message


def test_unknown_evidence_refs_fail_against_allowlist() -> None:
    payload = _fixture_operation_model()
    allowed_refs = _allowed_refs(payload)
    payload["dtoBlueprints"][0]["fields"][0]["evidenceRefs"] = ["ev.not_allowed"]

    with pytest.raises(OperationModelValidationError, match="unknown ref"):
        validate_sp_operation_model_output(payload, allowed_evidence_refs=allowed_refs)
