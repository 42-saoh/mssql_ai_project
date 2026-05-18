from __future__ import annotations

from collections.abc import Iterable, Mapping
from copy import deepcopy
from pathlib import Path
from typing import Any

import yaml
from ai_agent_validation import validate_ai_java_mybatis_draft_pack_quality
from ai_agent_validation.models import ValidationStatus

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "fixtures" / "eval" / "ai_draft_pack_p42_manage_bond_v1.yaml"

REQUIRED_DTOS = {
    "ManageBondSearchCriteria",
    "ManageBondSearchRow",
    "ApproveAdvanceBondCommand",
    "ApproveDefectBondCommand",
    "FinanceTransferCommand",
    "CreateBondCommand",
    "CreateRetentionBondBatchItem",
    "UpdateBondCommand",
    "DeleteBondCommand",
    "VendorBondUpdateCommand",
    "OnlineBondUpdateCommand",
}

ALLOWED_ARTIFACT_TYPES = {
    "DTO_DRAFT",
    "SERVICE_DRAFT",
    "MAPPER_INTERFACE",
    "MAPPER_XML",
}


def _yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _materialized_pack(fixture: dict[str, Any]) -> dict[str, Any]:
    target = fixture["ai_draft_pack_quality_target"]
    quality_gates = fixture["quality_gates"]
    return {
        "schemaVersion": target["schemaVersion"],
        "contractTarget": target["contractTarget"],
        "targetRef": target["targetRef"],
        "sourcePolicy": target["sourcePolicy"],
        "productionReady": target["productionReady"],
        "files": [_materialized_file(file) for file in target["expectedFiles"]],
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
        "assumptions": ["P42C eval materialization is sanitized and productionReady=false."],
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
    for optional_key in ("dtoRole", "requiredFields", "references"):
        if optional_key in file:
            payload[optional_key] = deepcopy(file[optional_key])
    return payload


def _materialized_content(file: dict[str, Any]) -> str:
    artifact_type = file["artifactType"]
    class_name = file["className"]
    if artifact_type == "DTO_DRAFT":
        fields = "\n".join(f"    private String {field};" for field in file["requiredFields"])
        return f"public class {class_name} {{\n    // REVIEW_REQUIRED draft DTO.\n{fields}\n}}"
    if artifact_type == "MAPPER_XML":
        references = " ".join(file["references"])
        statements = "\n".join(
            f'  <update id="{operation_id}">/* SQL_SKELETON_REVIEW_REQUIRED */</update>'
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
        return f"public interface {class_name} {{\n    // {references}\n{methods}\n}}"
    return f"public class {class_name} {{\n    // {references}\n{methods}\n}}"


def _iter_mapping_keys(value: Any) -> Iterable[str]:
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield str(key)
            yield from _iter_mapping_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_mapping_keys(item)


def test_p42_manage_bond_fixture_declares_required_multi_dto_pack() -> None:
    fixture = _yaml(FIXTURE)
    pack = fixture["ai_draft_pack_quality_target"]
    files = pack["expectedFiles"]
    dto_files = [file for file in files if file["artifactType"] == "DTO_DRAFT"]
    service_files = [file for file in files if file["artifactType"] == "SERVICE_DRAFT"]
    mapper_files = [file for file in files if file["artifactType"] == "MAPPER_INTERFACE"]
    mapper_xml_files = [file for file in files if file["artifactType"] == "MAPPER_XML"]

    assert pack["schemaVersion"] == "AiJavaMyBatisDraftPack.v0.1"
    assert pack["sourcePolicy"] == "sanitized_facts_only"
    assert pack["productionReady"] is False
    assert {file["artifactType"] for file in files} <= ALLOWED_ARTIFACT_TYPES
    assert {file["className"] for file in dto_files} == REQUIRED_DTOS
    assert len(dto_files) == fixture["expected_quality_report"]["scores"]["expectedDtoArtifactRows"]
    assert len(service_files) == 1
    assert len(mapper_files) == 1
    assert len(mapper_xml_files) == 1
    assert not any(file["className"] == "ManageBondDTO" for file in dto_files)


def test_p42_manage_bond_fixture_wires_service_mapper_xml_to_dtos() -> None:
    fixture = _yaml(FIXTURE)
    pack = fixture["ai_draft_pack_quality_target"]
    required_methods = set(fixture["quality_gates"]["required_service_methods"])
    required_refs = set(fixture["quality_gates"]["required_dto_classes"])

    non_dto_files = [
        file for file in pack["expectedFiles"] if file["artifactType"] != "DTO_DRAFT"
    ]
    assert {file["artifactType"] for file in non_dto_files} == {
        "SERVICE_DRAFT",
        "MAPPER_INTERFACE",
        "MAPPER_XML",
    }
    for file in non_dto_files:
        assert required_methods <= set(file["operationIds"])
        assert required_refs <= set(file["references"])


def test_p42_manage_bond_fixture_blocks_p41_fallback_and_single_dto_collapse() -> None:
    fixture = _yaml(FIXTURE)
    gates = fixture["quality_gates"]
    report = fixture["expected_quality_report"]["scores"]

    assert "OperationModelReviewRequired" in gates["blocker_patterns"]
    assert "ManageBondDTO" in gates["blocker_patterns"]
    assert "P41_OPERATION_MODEL_REVIEW_REQUIRED" in gates["blocker_patterns"]
    assert gates["blank_content_is_blocker"] is True
    assert gates["dto_collapse_is_blocker"] is True
    assert gates["fallback_skeleton_persistence_allowed_on_failure"] is False
    assert report["operationModelFallbackAllowed"] is False
    assert report["singleDtoCollapseAllowed"] is False
    assert report["blankFileAllowed"] is False


def test_p42_manage_bond_fixture_keeps_uncertain_items_review_required() -> None:
    fixture = _yaml(FIXTURE)
    review_required = set(fixture["guide_quality_facts"]["review_required_facts"])
    report_markers = set(fixture["expected_quality_report"]["reviewRequiredFindings"])

    assert "CROSS_DB_WRITE_REVIEW_REQUIRED" in review_required
    assert "CALLED_PROCEDURE_IO_REVIEW_REQUIRED" in review_required
    assert "TVF_OR_PROCEDURE_KIND_REVIEW_REQUIRED" in review_required
    assert "TRANSACTION_BOUNDARY_REVIEW_REQUIRED" in review_required
    assert report_markers <= review_required
    assert len(report_markers) >= 3


def test_p42_manage_bond_fixture_does_not_store_forbidden_payload_keys() -> None:
    fixture = _yaml(FIXTURE)
    forbidden = set(fixture["storage_policy"]["forbidden_payload_fields"])
    pack_keys = set(_iter_mapping_keys(fixture["ai_draft_pack_quality_target"]))

    assert pack_keys.isdisjoint(forbidden)
    assert fixture["source_reference"]["copy_reference_content_to_repo"] is False
    assert fixture["source_reference"]["copy_raw_sp_text_to_repo"] is False
    assert fixture["artifact_scope"]["new_public_artifact_type_allowed"] is False
    assert fixture["artifact_scope"]["ui_change_allowed"] is False
    assert fixture["artifact_scope"]["db_schema_change_allowed"] is False


def test_p42_manage_bond_fixture_tracks_branch_and_dependency_coverage() -> None:
    fixture = _yaml(FIXTURE)
    facts = fixture["guide_quality_facts"]

    assert set(facts["crud_flags"]) == {"R", "A", "C", "U", "D", "VENDOR_U", "ONLINE_U"}
    assert {"@CRUDFlag", "@BondKindCode", "@GUBUNFlag", "@SValue"} <= set(
        facts["branch_variables"]
    )
    assert "ERP.dbo.XXEAI_TRX_HEADER_II" in facts["major_dependencies"]["cross_database"]
    assert "PPM.dbo.PCO_GUAR" in facts["major_dependencies"]["same_database"]
    assert (
        "PPM.dbo.PCS_PA_ReserveAmtSplitString_PRC"
        in facts["major_dependencies"]["called_procedures"]
    )


def test_p42_manage_bond_materialized_pack_passes_deterministic_validator() -> None:
    fixture = _yaml(FIXTURE)
    expected_scores = fixture["expected_quality_report"]["scores"]

    report = validate_ai_java_mybatis_draft_pack_quality(_materialized_pack(fixture))
    scores = report.metadata["scores"]

    assert report.status == ValidationStatus.PASSED
    assert scores["requiredDtoFileCoverage"] == expected_scores["requiredDtoFileCoverage"]
    assert scores["requiredServiceMethodCoverage"] == expected_scores[
        "requiredServiceMethodCoverage"
    ]
    assert scores["expectedDtoArtifactRows"] == expected_scores["expectedDtoArtifactRows"]
    assert scores["expectedServiceArtifactRows"] == expected_scores[
        "expectedServiceArtifactRows"
    ]
    assert scores["expectedMapperInterfaceArtifactRows"] == expected_scores[
        "expectedMapperInterfaceArtifactRows"
    ]
    assert scores["expectedMapperXmlArtifactRows"] == expected_scores[
        "expectedMapperXmlArtifactRows"
    ]
    assert set(fixture["expected_quality_report"]["reviewRequiredFindings"]) <= set(
        report.manual_review_points
    )


def test_p42_manage_bond_fallback_skeleton_pattern_is_not_acceptance_output() -> None:
    fixture = _yaml(FIXTURE)
    payload = _materialized_pack(fixture)
    payload["files"][0]["path"] = "dto/OperationModelReviewRequired.java"
    payload["files"][0]["className"] = "OperationModelReviewRequired"
    payload["files"][0]["content"] = "public class OperationModelReviewRequired {}"

    report = validate_ai_java_mybatis_draft_pack_quality(payload)

    assert report.status == ValidationStatus.FAILED
