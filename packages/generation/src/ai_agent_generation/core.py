from __future__ import annotations

from ai_agent_domain import ArtifactType, RequestedOutputType

from ai_agent_generation.documents import DependencyReportRenderer, SPAnalysisDocumentRenderer
from ai_agent_generation.java_mybatis import JavaMyBatisSpWrapperRenderer
from ai_agent_generation.models import GenerationContext, RenderedArtifact, RenderedBundle


def render_artifact(
    artifact_type: ArtifactType | str,
    context: GenerationContext,
) -> RenderedArtifact:
    artifact_value = artifact_type.value if hasattr(artifact_type, "value") else str(artifact_type)
    renderers = {
        ArtifactType.SP_ANALYSIS_DOC.value: SPAnalysisDocumentRenderer(),
        ArtifactType.DEPENDENCY_REPORT.value: DependencyReportRenderer(),
    }
    try:
        return renderers[artifact_value].render(context)
    except KeyError as exc:
        raise ValueError(f"Unsupported artifact type: {artifact_value}") from exc


def render_java_mybatis_sp_wrapper(context: GenerationContext) -> RenderedBundle:
    if context.generation_mode not in {"spWrapper", "spRebuild", "evidenceReconstructed"}:
        raise ValueError(
            "JavaMyBatisSpWrapperRenderer supports generationMode=spWrapper, "
            "spRebuild, or evidenceReconstructed."
        )
    return JavaMyBatisSpWrapperRenderer().render_bundle(context)


def render_requested_output(
    requested_output_type: RequestedOutputType | str,
    context: GenerationContext,
) -> tuple[RenderedArtifact | RenderedBundle, ...]:
    output_value = (
        requested_output_type.value
        if hasattr(requested_output_type, "value")
        else str(requested_output_type)
    )
    if output_value == RequestedOutputType.SP_ANALYSIS_DOCUMENT.value:
        return (render_artifact(ArtifactType.SP_ANALYSIS_DOC, context),)
    if output_value == RequestedOutputType.DEPENDENCY_REPORT.value:
        return (render_artifact(ArtifactType.DEPENDENCY_REPORT, context),)
    if output_value == RequestedOutputType.JAVA_MYBATIS_DRAFT.value:
        return (render_java_mybatis_sp_wrapper(context),)
    raise ValueError(f"Unsupported requested output type: {output_value}")
