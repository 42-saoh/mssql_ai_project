from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path
from typing import Any

import yaml
from ai_agent_domain import ArtifactType, SpOperationModel
from ai_agent_generation import GenerationContext, JavaMyBatisSpWrapperRenderer

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "fixtures" / "eval" / "sp_operation_model_p41_manage_bond_v1.yaml"

REQUIRED_CRUD_FLAGS = {"R", "A", "C", "U", "D", "VENDOR_U", "ONLINE_U"}
REQUIRED_DTO_BLUEPRINTS = {
    "ManageBondSearchCriteria",
    "ManageBondSearchRow",
    "ApproveAdvanceBondCommand",
    "CreateBondCommand",
    "CreateRetentionBondBatchItem",
    "UpdateBondCommand",
    "DeleteBondCommand",
    "VendorBondUpdateCommand",
    "OnlineBondUpdateCommand",
}


def _yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def _iter_mapping_keys(value: Any) -> Iterable[str]:
    if isinstance(value, Mapping):
        for key, item in value.items():
            yield str(key)
            yield from _iter_mapping_keys(item)
    elif isinstance(value, list):
        for item in value:
            yield from _iter_mapping_keys(item)


def test_p41_manage_bond_fixture_validates_sp_operation_model_contract() -> None:
    fixture = _yaml(FIXTURE)
    model = SpOperationModel.model_validate(fixture["operation_model"])

    assert model.schema_version == "SpOperationModel.v0.1"
    assert model.contract_target == "SpOperationModel"
    assert model.target_ref == "PPM.dbo.PCO_GU_ManageBond_PRC"
    assert model.production_ready is False
    assert {operation.crud_flag for operation in model.operations} == REQUIRED_CRUD_FLAGS
    assert len(model.statement_evidence) >= fixture["quality_thresholds"]["statement_evidence_min"]
    assert len(model.dto_blueprints) >= fixture["quality_thresholds"]["dto_blueprint_min"]

    statement_ids = {statement.statement_id for statement in model.statement_evidence}
    dto_names = {dto.name for dto in model.dto_blueprints}
    assert REQUIRED_DTO_BLUEPRINTS <= dto_names
    for operation in model.operations:
        assert operation.statement_refs
        assert operation.dto_blueprint_refs
        assert set(operation.statement_refs) <= statement_ids
        assert set(operation.dto_blueprint_refs) <= dto_names


def test_p41_manage_bond_fixture_keeps_uncertain_items_review_required() -> None:
    fixture = _yaml(FIXTURE)
    model = SpOperationModel.model_validate(fixture["operation_model"])

    review_markers = set(model.review_markers)
    review_markers.update(
        marker
        for statement in model.statement_evidence
        for marker in statement.review_markers
    )
    review_markers.update(
        marker for dto in model.dto_blueprints for marker in dto.review_markers
    )

    assert "CROSS_DB_WRITE_REVIEW_REQUIRED" in review_markers
    assert "TVF_OR_PROCEDURE_KIND_REVIEW_REQUIRED" in review_markers
    assert "CALLED_PROCEDURE_IO_REVIEW_REQUIRED" in review_markers
    assert (
        len(review_markers)
        >= fixture["quality_thresholds"]["review_required_uncertain_items_min"]
    )
    assert any(statement.cross_database for statement in model.statement_evidence)


def test_p41_manage_bond_fixture_does_not_store_forbidden_payload_keys() -> None:
    fixture = _yaml(FIXTURE)
    forbidden = set(fixture["storage_policy"]["forbidden_payload_fields"])
    operation_model_keys = set(_iter_mapping_keys(fixture["operation_model"]))

    assert operation_model_keys.isdisjoint(forbidden)
    assert fixture["source_reference"]["copy_reference_content_to_repo"] is False
    assert fixture["source_reference"]["copy_raw_sp_text_to_repo"] is False
    assert fixture["artifact_scope"]["new_public_artifact_type_allowed"] is False
    assert fixture["artifact_scope"]["ui_change_allowed"] is False


def test_p41_current_java_mybatis_renderer_gap_is_visible() -> None:
    fixture = _yaml(FIXTURE)
    probe = fixture["generation_readiness"]["current_renderer_probe"]
    model = SpOperationModel.model_validate(fixture["operation_model"])
    context = GenerationContext.from_mapping(probe)

    bundle = JavaMyBatisSpWrapperRenderer().render_bundle(context)
    dto_files = [file for file in bundle.files if file.artifact_type == ArtifactType.DTO_DRAFT]

    assert len(dto_files) == 1
    assert dto_files[0].path.endswith("/ManageBondDTO.java")
    assert "INPUT_PARAM" in dto_files[0].content
    assert "RESULT_FIELD" in dto_files[0].content
    assert len(model.dto_blueprints) >= 9
    gap = fixture["generation_readiness"]["current_generator_gap"]
    assert gap["single_dto_collapse"] is True
    assert gap["marker"] == "SINGLE_DTO_COLLAPSE_REVIEW_REQUIRED"
    assert gap["next_slice_required"] == "P41B"


def test_p41_operation_model_renderer_keeps_multi_dto_bundle() -> None:
    fixture = _yaml(FIXTURE)
    probe = dict(fixture["generation_readiness"]["current_renderer_probe"])
    probe["request"] = dict(probe["request"])
    probe["request"]["operationModel"] = fixture["operation_model"]
    context = GenerationContext.from_mapping(probe)

    bundle = JavaMyBatisSpWrapperRenderer().render_bundle(context)
    dto_files = [file for file in bundle.files if file.artifact_type == ArtifactType.DTO_DRAFT]
    service_files = [
        file for file in bundle.files if file.artifact_type == ArtifactType.SERVICE_DRAFT
    ]
    mapper_files = [
        file for file in bundle.files if file.artifact_type == ArtifactType.MAPPER_INTERFACE
    ]
    mapper_xml_files = [
        file for file in bundle.files if file.artifact_type == ArtifactType.MAPPER_XML
    ]

    expected = fixture["generation_readiness"]["operation_model_renderer_behavior"]
    assert expected["observed_behavior"] == "multi_file_dto_draft_bundle"
    assert len(dto_files) == expected["expected_dto_blueprint_count"]
    assert len(service_files) == expected["service_draft_files"]
    assert len(mapper_files) == expected["mapper_interface_files"]
    assert len(mapper_xml_files) == expected["mapper_xml_files"]
    assert not any(file.path.endswith("/ManageBondDTO.java") for file in dto_files)
    assert expected["public_artifact_types_unchanged"] is True
    assert expected["productionReady"] is False
