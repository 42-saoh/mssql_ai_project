from typing import Annotated

from api_app.errors import api_http_exception
from api_app.knowledge_service import (
    export_knowledge,
    present_fact_graph,
    present_knowledge_asset,
    present_knowledge_version,
)
from api_app.repositories import KnowledgePersistenceError, WorkflowRepository
from api_app.dependencies import get_repository
from api_app.schemas import (
    KnowledgeAssetSummary,
    KnowledgeAssetVersion,
    KnowledgeExportRequest,
    KnowledgeExportResponse,
    KnowledgeFactGraph,
)
from fastapi import APIRouter, Depends

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])


@router.get("/assets/{assetId}", response_model=KnowledgeAssetSummary)
def get_knowledge_asset(
    assetId: str,
    repository: Annotated[WorkflowRepository, Depends(get_repository)],
) -> KnowledgeAssetSummary:
    try:
        asset = repository.get_knowledge_asset(assetId)
    except KnowledgePersistenceError as exc:
        raise _knowledge_error(exc) from exc
    if asset is None:
        raise api_http_exception(
            status_code=404,
            detail=f"Unknown knowledge asset: {assetId}",
            code="KNOWLEDGE_ASSET_NOT_FOUND",
        )
    return present_knowledge_asset(asset)


@router.get("/assets/{assetId}/versions")
def list_knowledge_asset_versions(
    assetId: str,
    repository: Annotated[WorkflowRepository, Depends(get_repository)],
) -> dict[str, str | list[KnowledgeAssetVersion]]:
    try:
        versions = repository.list_knowledge_asset_versions(assetId)
    except KnowledgePersistenceError as exc:
        raise _knowledge_error(exc) from exc
    if versions is None:
        raise api_http_exception(
            status_code=404,
            detail=f"Unknown knowledge asset: {assetId}",
            code="KNOWLEDGE_ASSET_NOT_FOUND",
        )
    return {
        "assetId": assetId,
        "versions": [present_knowledge_version(version) for version in versions],
    }


@router.get(
    "/assets/{assetId}/versions/{versionId}/facts",
    response_model=KnowledgeFactGraph,
)
def list_knowledge_version_facts(
    assetId: str,
    versionId: str,
    repository: Annotated[WorkflowRepository, Depends(get_repository)],
) -> KnowledgeFactGraph:
    try:
        graph = repository.list_knowledge_facts(assetId, versionId)
    except KnowledgePersistenceError as exc:
        raise _knowledge_error(exc) from exc
    if graph is None:
        raise api_http_exception(
            status_code=404,
            detail=f"Unknown knowledge asset version: {versionId}",
            code="KNOWLEDGE_ASSET_NOT_FOUND",
        )
    facts, edges = graph
    return present_fact_graph(
        asset_id=assetId,
        version_id=versionId,
        facts=facts,
        edges=edges,
    )


@router.post("/exports", response_model=KnowledgeExportResponse)
def create_knowledge_export(
    request: KnowledgeExportRequest,
    repository: Annotated[WorkflowRepository, Depends(get_repository)],
) -> KnowledgeExportResponse:
    try:
        return export_knowledge(repository=repository, request=request)
    except KnowledgePersistenceError as exc:
        raise _knowledge_error(exc) from exc


def _knowledge_error(exc: KnowledgePersistenceError):
    return api_http_exception(
        status_code=exc.status_code,
        detail=str(exc),
        code=exc.code,
    )
