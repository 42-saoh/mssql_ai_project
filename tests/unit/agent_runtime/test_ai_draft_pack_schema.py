from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
import yaml
from ai_agent_runtime.ai_draft_pack import (
    AiDraftPackValidationError,
    ai_java_mybatis_draft_pack_output_schema,
    all_ai_java_mybatis_draft_pack_evidence_refs,
    validate_ai_java_mybatis_draft_pack_output,
)

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
        "evidenceRefs": target["evidenceRefs"],
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
        "assumptions": ["P42B fixture pack is draft-only and productionReady=false."],
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
    class_name = file["className"]
    operation_ids = list(file["operationIds"])
    if file["artifactType"] == "MAPPER_XML":
        statements = "\n".join(
            f'  <select id="{operation_id}" parameterType="map" resultType="map" />'
            for operation_id in operation_ids
        )
        return f'<mapper namespace="ManageBondMapper">\n{statements}\n</mapper>'
    methods = "\n".join(f"    void {operation_id}();" for operation_id in operation_ids)
    references = " ".join(file.get("references") or file.get("requiredFields") or [])
    if file["artifactType"] == "MAPPER_INTERFACE":
        return f"public interface {class_name} {{\n{methods}\n}}"
    return (
        f"public class {class_name} {{\n"
        f"    // REVIEW_REQUIRED draft backed by sanitized evidence. {references}\n"
        f"{methods}\n"
        "}"
    )


def test_ai_draft_pack_schema_is_strict_and_constrained() -> None:
    schema = ai_java_mybatis_draft_pack_output_schema(["ev.allowed"])

    assert schema["additionalProperties"] is False
    assert schema["properties"]["schemaVersion"]["const"] == "AiJavaMyBatisDraftPack.v0.1"
    assert schema["properties"]["productionReady"]["const"] is False
    assert schema["properties"]["evidenceRefs"]["items"]["enum"] == ["ev.allowed"]
    file_schema = schema["properties"]["files"]["items"]
    assert file_schema["additionalProperties"] is False
    assert file_schema["properties"]["artifactType"]["enum"] == [
        "DTO_DRAFT",
        "SERVICE_DRAFT",
        "MAPPER_INTERFACE",
        "MAPPER_XML",
    ]
    assert "CALL_REQUEST_DTO" in file_schema["properties"]["role"]["enum"]
    assert "content" in file_schema["required"]


def test_manage_bond_fixture_materializes_valid_ai_draft_pack() -> None:
    payload = _valid_pack()
    model = validate_ai_java_mybatis_draft_pack_output(payload)

    assert model.target_ref == "PPM.dbo.PCO_GU_ManageBond_PRC"
    assert model.production_ready is False
    assert len([file for file in model.files if file.artifact_type == "DTO_DRAFT"]) == 11
    assert "ManageBondDTO" not in {file.class_name for file in model.files}
    assert "CROSS_DB_WRITE_REVIEW_REQUIRED" in model.review_markers


def test_allowed_evidence_refs_are_enforced() -> None:
    payload = _valid_pack()
    model = validate_ai_java_mybatis_draft_pack_output(payload)
    allowed_refs = sorted(set(all_ai_java_mybatis_draft_pack_evidence_refs(model)))

    payload["files"][0]["evidenceRefs"] = ["ev.not_allowed"]

    with pytest.raises(AiDraftPackValidationError, match="unknown ref"):
        validate_ai_java_mybatis_draft_pack_output(
            payload,
            allowed_evidence_refs=allowed_refs,
        )


def test_invalid_artifact_type_fails_deterministically() -> None:
    payload = _valid_pack()
    payload["files"][0]["artifactType"] = "MODEL_DRAFT"

    with pytest.raises(AiDraftPackValidationError, match="schema validation failed"):
        validate_ai_java_mybatis_draft_pack_output(payload)


def test_invalid_role_fails_deterministically() -> None:
    payload = _valid_pack()
    payload["files"][0]["role"] = "MEGA_DTO"

    with pytest.raises(AiDraftPackValidationError, match="schema validation failed"):
        validate_ai_java_mybatis_draft_pack_output(payload)


def test_blank_or_missing_content_fails_deterministically() -> None:
    payload = _valid_pack()
    payload["files"][0]["content"] = "   "

    with pytest.raises(AiDraftPackValidationError, match="content must not be blank"):
        validate_ai_java_mybatis_draft_pack_output(payload)

    payload = _valid_pack()
    del payload["files"][0]["content"]

    with pytest.raises(AiDraftPackValidationError, match="schema validation failed"):
        validate_ai_java_mybatis_draft_pack_output(payload)


def test_empty_evidence_refs_fail_deterministically() -> None:
    payload = _valid_pack()
    payload["files"][0]["evidenceRefs"] = []

    with pytest.raises(AiDraftPackValidationError, match="schema validation failed"):
        validate_ai_java_mybatis_draft_pack_output(payload)


def test_fallback_class_names_fail_deterministically() -> None:
    payload = _valid_pack()
    payload["files"][0]["className"] = "OperationModelReviewRequired"

    with pytest.raises(AiDraftPackValidationError, match="OperationModelReviewRequired"):
        validate_ai_java_mybatis_draft_pack_output(payload)


def test_required_review_markers_must_be_preserved() -> None:
    payload = _valid_pack()
    payload["reviewMarkers"] = []
    for file in payload["files"]:
        file["reviewMarkers"] = []

    with pytest.raises(AiDraftPackValidationError, match="required REVIEW_REQUIRED markers"):
        validate_ai_java_mybatis_draft_pack_output(payload)
