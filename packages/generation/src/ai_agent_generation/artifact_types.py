from __future__ import annotations

from ai_agent_domain import ArtifactType, RequestedOutputType

JAVA_MYBATIS_POLICY_ARTIFACT_TYPES = (
    ArtifactType.DTO_DRAFT,
    ArtifactType.SERVICE_DRAFT,
    ArtifactType.MAPPER_INTERFACE,
    ArtifactType.MAPPER_XML,
)

REQUESTED_OUTPUT_ALIASES: dict[str, tuple[ArtifactType, ...]] = {
    RequestedOutputType.SP_ANALYSIS_DOCUMENT.value: (ArtifactType.SP_ANALYSIS_DOC,),
    RequestedOutputType.DEPENDENCY_REPORT.value: (ArtifactType.DEPENDENCY_REPORT,),
    RequestedOutputType.TABLE_COLUMN_METADATA.value: (ArtifactType.METADATA_QUERY_RESULT,),
    RequestedOutputType.JAVA_MYBATIS_DRAFT.value: JAVA_MYBATIS_POLICY_ARTIFACT_TYPES,
}

def expand_requested_output_type(requested_output_type: str) -> tuple[ArtifactType, ...]:
    try:
        return REQUESTED_OUTPUT_ALIASES[requested_output_type]
    except KeyError as exc:
        raise ValueError(f"Unsupported requested output type: {requested_output_type}") from exc
