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
    RequestedOutputType.JAVA_MYBATIS_DRAFT.value: JAVA_MYBATIS_POLICY_ARTIFACT_TYPES,
    RequestedOutputType.DTO_MODEL_DRAFT.value: (
        ArtifactType.DTO_DRAFT,
        ArtifactType.VO_DRAFT,
        ArtifactType.MODEL_DRAFT,
    ),
    RequestedOutputType.DDL_DRAFT.value: (ArtifactType.DDL_DRAFT,),
}

JAVA_MYBATIS_DTO_MAPPING_BLOCKER = (
    "Policy spWrapper defaultOutputs includes dto, while the shared domain "
    "REQUESTED_OUTPUT_ARTIFACT_TYPES[JAVA_MYBATIS_DRAFT] omits DTO_DRAFT. "
    "The renderer emits DTO as draft-only policy output without changing the "
    "read-only domain/OpenAPI contract."
)


def expand_requested_output_type(requested_output_type: str) -> tuple[ArtifactType, ...]:
    try:
        return REQUESTED_OUTPUT_ALIASES[requested_output_type]
    except KeyError as exc:
        raise ValueError(f"Unsupported requested output type: {requested_output_type}") from exc
