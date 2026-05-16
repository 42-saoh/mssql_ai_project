from __future__ import annotations

from copy import deepcopy
from pathlib import Path

import yaml
from ai_agent_domain import ArtifactType, RequestedOutputType
from ai_agent_generation import (
    GenerationContext,
    GenerationPolicyAssets,
    GenerationPolicyError,
    JavaMyBatisDtoModelRenderer,
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
DTO_MODEL_GOLDEN_DIR = (
    ROOT
    / "fixtures"
    / "generation"
    / "golden"
    / "java_mybatis_dto_model_order_metadata_v1"
)


def _golden_context() -> GenerationContext:
    payload = yaml.safe_load((GOLDEN_DIR / "input.yaml").read_text(encoding="utf-8"))
    return GenerationContext.from_mapping(payload)


def _dto_model_golden_context() -> GenerationContext:
    payload = yaml.safe_load(
        (DTO_MODEL_GOLDEN_DIR / "input.yaml").read_text(encoding="utf-8")
    )
    return GenerationContext.from_mapping(payload)


def test_java_mybatis_sp_wrapper_matches_golden_manifest_and_files() -> None:
    context = _golden_context()
    bundle = JavaMyBatisSpWrapperRenderer().render_bundle(context)
    manifest = yaml.safe_load((GOLDEN_DIR / "expected_manifest.yaml").read_text(encoding="utf-8"))

    assert bundle.manifest.content == (GOLDEN_DIR / "expected_output.md").read_text(
        encoding="utf-8"
    )
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
    assert "REVIEW_REQUIRED" in content
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
    assert "template:java_mybatis_sp_wrapper@0.2.0" in bundle.manifest.registry_refs
    assert bundle.manifest.extra["inputSnapshotHash"] == context.input_snapshot_hash

    for relative_path, content in bundle.file_map.items():
        assert content == (GOLDEN_DIR / relative_path).read_text(encoding="utf-8")


def test_requested_output_aliases_keep_contract_names_visible() -> None:
    assert expand_requested_output_type("SP_ANALYSIS_DOCUMENT") == (
        ArtifactType.SP_ANALYSIS_DOC,
    )
    assert ArtifactType.DTO_DRAFT in expand_requested_output_type("JAVA_MYBATIS_DRAFT")


def test_analysis_and_dependency_renderers_emit_draft_required_sections() -> None:
    context = _golden_context()

    analysis = render_artifact(ArtifactType.SP_ANALYSIS_DOC, context)
    dependency = render_artifact(ArtifactType.DEPENDENCY_REPORT, context)

    assert analysis.artifact_type == ArtifactType.SP_ANALYSIS_DOC
    assert "## analysis_summary" in analysis.content
    assert "REVIEW_REQUIRED" in analysis.content
    assert analysis.evidence_refs

    assert dependency.artifact_type == ArtifactType.DEPENDENCY_REPORT
    assert "## dependency_table" in dependency.content
    assert "REVIEW_REQUIRED" in dependency.content
    assert dependency.evidence_refs


def test_render_requested_output_uses_openapi_group_aliases() -> None:
    context = _golden_context()
    rendered = render_requested_output(RequestedOutputType.JAVA_MYBATIS_DRAFT, context)

    assert len(rendered) == 1
    bundle = rendered[0]
    assert bundle.requested_output_type == RequestedOutputType.JAVA_MYBATIS_DRAFT.value


def test_dto_model_requested_output_renders_dto_vo_model_bundle() -> None:
    context = _dto_model_golden_context()
    rendered = render_requested_output(RequestedOutputType.DTO_MODEL_DRAFT, context)

    assert len(rendered) == 1
    bundle = rendered[0]
    assert bundle.requested_output_type == RequestedOutputType.DTO_MODEL_DRAFT.value
    assert bundle.artifact_types == (
        ArtifactType.DTO_DRAFT.value,
        ArtifactType.VO_DRAFT.value,
        ArtifactType.MODEL_DRAFT.value,
    )
    assert "template:java_mybatis_dto_model_bundle@0.1.0" in bundle.manifest.registry_refs
    assert "NO_SQL_RENDERED" in bundle.manifest.content
    assert any(path.endswith("OrderMetadataVO.java") for path in bundle.file_map)
    assert any(path.endswith("OrderMetadataModel.java") for path in bundle.file_map)


def test_java_mybatis_dto_model_matches_golden_manifest_and_files() -> None:
    context = _dto_model_golden_context()
    bundle = JavaMyBatisDtoModelRenderer().render_bundle(context)
    manifest = yaml.safe_load(
        (DTO_MODEL_GOLDEN_DIR / "expected_manifest.yaml").read_text(encoding="utf-8")
    )

    assert bundle.manifest.content == (DTO_MODEL_GOLDEN_DIR / "expected_output.md").read_text(
        encoding="utf-8"
    )
    assert tuple(file.path for file in bundle.files) == tuple(manifest["expectedFiles"])
    assert manifest["inputSnapshotHash"] == context.input_snapshot_hash

    for relative_path, content in bundle.file_map.items():
        assert content == (DTO_MODEL_GOLDEN_DIR / relative_path).read_text(encoding="utf-8")


def test_dto_model_renderer_uses_same_policy_loaded_field_mapping() -> None:
    context = _dto_model_golden_context()
    bundle = JavaMyBatisDtoModelRenderer().render_bundle(context)

    dto = bundle.file_map[
        "src/main/java/com/pec/pem/order/metadata/model/OrderMetadataDTO.java"
    ]
    vo = bundle.file_map[
        "src/main/java/com/pec/pem/order/metadata/model/OrderMetadataVO.java"
    ]

    assert "private LocalDate orderDate;" in dto
    assert "public class OrderMetadataVO" in vo


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
        RequestedOutputType.DTO_MODEL_DRAFT.value
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
