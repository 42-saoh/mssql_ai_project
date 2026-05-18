from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml
from ai_agent_validation import validate_ai_java_mybatis_draft_pack_quality
from ai_agent_validation.ai_draft_pack import (
    RULE_DTO_FIELD,
    RULE_FORBIDDEN_PAYLOAD,
    RULE_MAPPER_METHOD,
    RULE_MAPPER_XML,
    RULE_NON_DTO_REFERENCE,
    RULE_REVIEW_MARKER,
    RULE_SCHEMA,
)
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
        "assumptions": ["P42C fixture pack is draft-only and productionReady=false."],
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
            f"    // REVIEW_REQUIRED draft DTO backed by sanitized evidence.\n"
            f"{fields}\n"
            "}"
        )
    if artifact_type == "MAPPER_XML":
        references = " ".join(file["references"])
        statements = "\n".join(
            f'  <select id="{operation_id}" parameterType="map" resultType="map">'
            f"/* SQL_SKELETON_REVIEW_REQUIRED */</select>"
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


def _file(payload: dict[str, Any], class_name: str) -> dict[str, Any]:
    return next(file for file in payload["files"] if file["className"] == class_name)


def _file_by_type(payload: dict[str, Any], artifact_type: str) -> dict[str, Any]:
    return next(file for file in payload["files"] if file["artifactType"] == artifact_type)


def _failed_rule_ids(payload: dict[str, Any]) -> set[str]:
    report = validate_ai_java_mybatis_draft_pack_quality(payload)
    return {check.rule_id for check in report.failed_checks}


def test_valid_manage_bond_pack_passes_quality_gate() -> None:
    report = validate_ai_java_mybatis_draft_pack_quality(_valid_pack())

    assert report.status == ValidationStatus.PASSED
    assert report.failed_checks == ()
    assert report.metadata["productionReady"] is False
    assert report.metadata["scores"]["requiredDtoFileCoverage"] == 1.0
    assert report.metadata["scores"]["requiredServiceMethodCoverage"] == 1.0
    assert report.metadata["scores"]["requiredMapperMethodCoverage"] == 1.0
    assert report.metadata["scores"]["requiredReviewMarkerCoverage"] == 1.0


def test_blank_content_and_schema_failure_are_blockers() -> None:
    payload = _valid_pack()
    payload["files"][0]["content"] = "   "

    assert RULE_SCHEMA in _failed_rule_ids(payload)


def test_fallback_skeleton_and_single_dto_collapse_are_blockers() -> None:
    payload = _valid_pack()
    payload["files"][0]["className"] = "OperationModelReviewRequired"

    assert RULE_SCHEMA in _failed_rule_ids(payload)

    payload = _valid_pack()
    original = payload["files"][0]["className"]
    payload["files"][0]["className"] = "ManageBondDTO"
    payload["files"][0]["path"] = "dto/ManageBondDTO.java"
    payload["files"][0]["content"] = payload["files"][0]["content"].replace(
        original,
        "ManageBondDTO",
    )
    payload["qualityGates"]["requiredDtoClasses"] = [
        "ManageBondDTO" if item == original else item
        for item in payload["qualityGates"]["requiredDtoClasses"]
    ]
    for file in payload["files"]:
        if "references" in file:
            file["references"] = [
                "ManageBondDTO" if item == original else item
                for item in file["references"]
            ]
            file["content"] = file["content"].replace(original, "ManageBondDTO")

    assert RULE_FORBIDDEN_PAYLOAD in _failed_rule_ids(payload)


def test_missing_required_dto_is_a_blocker() -> None:
    payload = _valid_pack()
    payload["files"] = [
        file for file in payload["files"] if file["className"] != "OnlineBondUpdateCommand"
    ]

    assert RULE_SCHEMA in _failed_rule_ids(payload)


def test_missing_dto_required_field_fails_content_quality() -> None:
    payload = _valid_pack()
    dto = _file(payload, "CreateBondCommand")
    dto["content"] = dto["content"].replace("    private String currencyInsureAmt;\n", "")

    assert RULE_DTO_FIELD in _failed_rule_ids(payload)


def test_missing_service_dto_reference_fails_content_quality() -> None:
    payload = _valid_pack()
    service = _file_by_type(payload, "SERVICE_DRAFT")
    service["content"] = service["content"].replace(" OnlineBondUpdateCommand", "")

    assert RULE_NON_DTO_REFERENCE in _failed_rule_ids(payload)


def test_missing_mapper_method_fails_content_quality() -> None:
    payload = _valid_pack()
    mapper = _file_by_type(payload, "MAPPER_INTERFACE")
    mapper["content"] = mapper["content"].replace("    public void updateOnlineBond() {}\n", "")

    assert RULE_MAPPER_METHOD in _failed_rule_ids(payload)


def test_invalid_mapper_xml_fails_static_xml_quality() -> None:
    payload = _valid_pack()
    mapper_xml = _file_by_type(payload, "MAPPER_XML")
    mapper_xml["content"] = "<mapper><select id='readBond'></mapper>"

    assert RULE_MAPPER_XML in _failed_rule_ids(payload)


def test_forbidden_payload_markers_fail_quality_gate() -> None:
    payload = _valid_pack()
    dto = _file(payload, "ManageBondSearchCriteria")
    dto["content"] = f"{dto['content']}\n// CREATE PROCEDURE dbo.PCO_GU_ManageBond_PRC"

    assert RULE_SCHEMA in _failed_rule_ids(payload)

    payload = _valid_pack()
    dto = _file(payload, "ManageBondSearchCriteria")
    dto["content"] = f"{dto['content']}\n// mark this artifact as production ready"

    assert RULE_FORBIDDEN_PAYLOAD in _failed_rule_ids(payload)

    forbidden_cases = [
        "sample rows are included here",
        "execute stored procedure before using this mapper",
        "deployed to production after generated source apply",
    ]
    for forbidden in forbidden_cases:
        payload = _valid_pack()
        dto = _file(payload, "ManageBondSearchCriteria")
        dto["content"] = f"{dto['content']}\n// {forbidden}"

        assert _failed_rule_ids(payload) & {RULE_SCHEMA, RULE_FORBIDDEN_PAYLOAD}


def test_required_review_marker_removal_fails_quality_gate() -> None:
    payload = _valid_pack()
    payload["reviewMarkers"] = []
    for file in payload["files"]:
        file["reviewMarkers"] = []

    assert RULE_SCHEMA in _failed_rule_ids(payload)

    payload = _valid_pack()
    payload["qualityGates"]["requiredReviewMarkers"] = []
    payload["reviewMarkers"] = [
        marker
        for marker in payload["reviewMarkers"]
        if marker != "TRANSACTION_BOUNDARY_REVIEW_REQUIRED"
    ]

    assert RULE_REVIEW_MARKER in _failed_rule_ids(payload)
