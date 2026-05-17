from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import yaml
from ai_agent_domain import ArtifactType, RequestedOutputType
from ai_agent_generation import (
    GenerationContext,
    GenerationPolicyAssets,
    GenerationPolicyError,
    JavaMyBatisSpWrapperRenderer,
    expand_requested_output_type,
    load_generation_assets,
    render_artifact,
    render_requested_output,
)

ROOT = Path(__file__).resolve().parents[3]
GOLDEN_DIR = (
    ROOT
    / "fixtures"
    / "generation"
    / "golden"
    / "java_mybatis_sp_wrapper_order_request_v1"
)


def _golden_context() -> GenerationContext:
    payload = yaml.safe_load((GOLDEN_DIR / "input.yaml").read_text(encoding="utf-8"))
    return GenerationContext.from_mapping(payload)


def _p41_operation_model_context() -> tuple[GenerationContext, dict]:
    fixture = yaml.safe_load(
        (ROOT / "fixtures" / "eval" / "sp_operation_model_p41_manage_bond_v1.yaml")
        .read_text(encoding="utf-8")
    )
    probe = deepcopy(fixture["generation_readiness"]["current_renderer_probe"])
    probe["request"]["operationModel"] = fixture["operation_model"]
    return GenerationContext.from_mapping(probe), fixture["operation_model"]


def test_java_mybatis_sp_wrapper_matches_golden_manifest_and_files() -> None:
    context = _golden_context()
    bundle = JavaMyBatisSpWrapperRenderer().render_bundle(context)
    manifest = yaml.safe_load((GOLDEN_DIR / "expected_manifest.yaml").read_text(encoding="utf-8"))

    assert tuple(file.path for file in bundle.files) == tuple(manifest["expectedFiles"])
    assert bundle.artifact_types == (
        ArtifactType.DTO_DRAFT.value,
        ArtifactType.SERVICE_DRAFT.value,
        ArtifactType.MAPPER_INTERFACE.value,
        ArtifactType.MAPPER_XML.value,
    )
    assert bundle.blockers == ()
    assert bundle.manifest.review_required is True
    content = bundle.manifest.content
    assert "## registry_versions" in content
    assert "## generator_metadata" in content
    assert "- generatorVersion: `generation-core-0.1.0`" in content
    assert "- artifactStatus: `DRAFT`" in content
    assert "- evidenceCaveat: `true`" in content
    assert "- draftQualityGate: `validation_only`" in content
    assert "## input_snapshot" in content
    assert "## sql_risk_markers" in content
    assert "## draft_change_summary" in content
    assert "## evidence_map" in content
    assert "## known_caveats" in content
    assert "template:java_mybatis_sp_wrapper@0.3.0" in bundle.manifest.registry_refs
    assert bundle.manifest.extra["inputSnapshotHash"] == context.input_snapshot_hash

    dto = bundle.file_map["src/main/java/com/pec/pem/order/request/model/OrderRequestDTO.java"]
    service = bundle.file_map[
        "src/main/java/com/pec/pem/order/request/service/OrderRequestService.java"
    ]
    mapper = bundle.file_map[
        "src/main/java/com/pec/pem/order/request/mapper/OrderRequestMapper.java"
    ]
    mapper_xml = bundle.file_map[
        "src/main/resources/mybatis/pem/mappers/order/request/OrderRequestMapperSQL.xml"
    ]
    assert "INPUT_PARAM" in dto
    assert "RESULT_FIELD" in dto
    assert "public class OrderRequestService" in service
    assert "private final OrderRequestMapper mapper" in service
    assert "List<OrderRequestDTO> selectOrderRequestList" in mapper
    assert f"EXEC {context.sp_name}" in mapper_xml


def test_requested_output_aliases_keep_contract_names_visible() -> None:
    assert expand_requested_output_type("SP_ANALYSIS_DOCUMENT") == (
        ArtifactType.SP_ANALYSIS_DOC,
    )
    assert ArtifactType.DTO_DRAFT in expand_requested_output_type("JAVA_MYBATIS_DRAFT")


def test_analysis_and_dependency_renderers_emit_p36_sections() -> None:
    context = _golden_context()

    analysis = render_artifact(ArtifactType.SP_ANALYSIS_DOC, context)
    dependency = render_artifact(ArtifactType.DEPENDENCY_REPORT, context)

    assert analysis.artifact_type == ArtifactType.SP_ANALYSIS_DOC
    assert "## 1. SP 개요 (Overview)" in analysis.content
    assert "## 6. Appendix" in analysis.content
    assert "REVIEW_REQUIRED" in analysis.content
    assert analysis.evidence_refs

    assert dependency.artifact_type == ArtifactType.DEPENDENCY_REPORT
    assert "## generation_evidence_summary" in dependency.content
    assert "## sql_statement_evidence" in dependency.content
    assert "Evidence Dossier" in dependency.content
    assert dependency.evidence_refs


def test_render_requested_output_uses_openapi_group_aliases() -> None:
    context = _golden_context()
    rendered = render_requested_output(RequestedOutputType.JAVA_MYBATIS_DRAFT, context)

    assert len(rendered) == 1
    bundle = rendered[0]
    assert bundle.requested_output_type == RequestedOutputType.JAVA_MYBATIS_DRAFT.value


def test_missing_policy_naming_asset_blocks_generation() -> None:
    assets = load_generation_assets(template_ids=("java_mybatis_sp_wrapper",))
    policy = dict(assets.policy)
    policy["classNames"] = dict(policy["classNames"])
    policy["classNames"].pop("mapper")
    broken_assets = GenerationPolicyAssets(
        policy=policy,
        registry=assets.registry,
        policy_path=assets.policy_path,
        registry_path=assets.registry_path,
    )

    try:
        JavaMyBatisSpWrapperRenderer(assets=broken_assets)
    except GenerationPolicyError as exc:
        assert "policy.classNames.mapper" in str(exc)
    else:
        raise AssertionError("broken generation policy should block rendering")


def test_template_requested_output_drift_blocks_generation() -> None:
    assets = load_generation_assets(template_ids=("java_mybatis_sp_wrapper",))
    registry = deepcopy(assets.registry)
    registry["templates"]["java_mybatis_sp_wrapper"]["requestedOutputType"] = (
        "REMOVED_P36_OUTPUT"
    )
    drifted_assets = GenerationPolicyAssets(
        policy=assets.policy,
        registry=registry,
        policy_path=assets.policy_path,
        registry_path=assets.registry_path,
    )

    try:
        JavaMyBatisSpWrapperRenderer(assets=drifted_assets)
    except GenerationPolicyError as exc:
        assert "requestedOutputType drift" in str(exc)
        assert RequestedOutputType.JAVA_MYBATIS_DRAFT.value in str(exc)
    else:
        raise AssertionError("registry requestedOutputType drift should block rendering")


def test_p41_operation_model_renders_multi_dto_java_mybatis_bundle() -> None:
    context, operation_model = _p41_operation_model_context()
    bundle = JavaMyBatisSpWrapperRenderer().render_bundle(context)

    dto_files = [
        file for file in bundle.files if file.artifact_type == ArtifactType.DTO_DRAFT
    ]
    dto_paths = {file.path for file in dto_files}

    assert len(dto_files) == len(operation_model["dtoBlueprints"]) >= 10
    assert not any(path.endswith("/ManageBondDTO.java") for path in dto_paths)
    assert {
        "src/main/java/com/pec/ppm/guarantee/bond/model/ManageBondSearchCriteria.java",
        "src/main/java/com/pec/ppm/guarantee/bond/model/ManageBondSearchRow.java",
        "src/main/java/com/pec/ppm/guarantee/bond/model/ApproveAdvanceBondCommand.java",
        "src/main/java/com/pec/ppm/guarantee/bond/model/CreateRetentionBondBatchItem.java",
        "src/main/java/com/pec/ppm/guarantee/bond/model/VendorBondUpdateCommand.java",
        "src/main/java/com/pec/ppm/guarantee/bond/model/OnlineBondUpdateCommand.java",
    }.issubset(dto_paths)

    assert bundle.artifact_types.count(ArtifactType.DTO_DRAFT.value) == len(
        operation_model["dtoBlueprints"]
    )
    assert bundle.artifact_types.count(ArtifactType.SERVICE_DRAFT.value) == 1
    assert bundle.artifact_types.count(ArtifactType.MAPPER_INTERFACE.value) == 1
    assert bundle.artifact_types.count(ArtifactType.MAPPER_XML.value) == 1
    assert bundle.manifest.extra["operationModelSchema"] == "SpOperationModel.v0.1"
    bundle_files = bundle.manifest.extra["bundleFiles"]
    assert bundle_files[
        "src/main/java/com/pec/ppm/guarantee/bond/model/ManageBondSearchCriteria.java"
    ]["dtoRole"] == "QUERY"
    assert bundle_files[
        "src/main/java/com/pec/ppm/guarantee/bond/model/ManageBondSearchCriteria.java"
    ]["operationIds"] == ["readBond"]

    service = bundle.file_map[
        "src/main/java/com/pec/ppm/guarantee/bond/service/ManageBondService.java"
    ]
    mapper = bundle.file_map[
        "src/main/java/com/pec/ppm/guarantee/bond/mapper/ManageBondMapper.java"
    ]
    mapper_xml = bundle.file_map[
        "src/main/resources/mybatis/ppm/mappers/guarantee/bond/ManageBondMapperSQL.xml"
    ]

    assert (
        "List<ManageBondSearchRow> readBond(ManageBondSearchCriteria condition)"
        in service
    )
    assert "int approveAdvanceBond(ApproveAdvanceBondCommand command)" in service
    assert "int financeTransfer(FinanceTransferCommand request)" in service
    assert "int createRetentionBond(CreateRetentionBondBatchItem item)" in service
    assert "int vendorBondUpdate(VendorBondUpdateCommand command)" in mapper
    assert "int onlineBondUpdate(OnlineBondUpdateCommand command)" in mapper

    assert '<select id="readBond"' in mapper_xml
    assert (
        'parameterType="com.pec.ppm.guarantee.bond.model.ManageBondSearchCriteria"'
        in mapper_xml
    )
    assert (
        'resultType="com.pec.ppm.guarantee.bond.model.ManageBondSearchRow"'
        in mapper_xml
    )
    assert (
        'parameterType="com.pec.ppm.guarantee.bond.model.VendorBondUpdateCommand"'
        in mapper_xml
    )
    assert (
        'parameterType="com.pec.ppm.guarantee.bond.model.OnlineBondUpdateCommand"'
        in mapper_xml
    )
