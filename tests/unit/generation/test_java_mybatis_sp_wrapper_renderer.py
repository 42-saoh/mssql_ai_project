from __future__ import annotations

from pathlib import Path

import yaml

from ai_agent_generation import (
    GenerationContext,
    JavaMyBatisSpWrapperRenderer,
    expand_requested_output_type,
    render_artifact,
    render_requested_output,
)
from ai_agent_domain import ArtifactType, RequestedOutputType


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
    assert "REVIEW_REQUIRED" in bundle.manifest.content

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
