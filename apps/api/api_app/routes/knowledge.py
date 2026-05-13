from typing import Annotated

from api_app.auth import Actor, forbidden_exception
from api_app.dependencies import get_repository, require_artifact_review_actor
from api_app.errors import api_http_exception
from api_app.knowledge_service import (
    ensure_knowledge_search_filter,
    export_knowledge,
    present_fact_graph,
    present_fact_search_result,
    present_knowledge_asset,
    present_knowledge_review,
    present_knowledge_version,
    sanitize_knowledge_review_note,
)
from api_app.repositories import KnowledgePersistenceError, WorkflowRepository
from api_app.schemas import (
    KnowledgeAssetSummary,
    KnowledgeAssetVersion,
    KnowledgeExportRequest,
    KnowledgeExportResponse,
    KnowledgeFactSearchResult,
    KnowledgeFactGraph,
    KnowledgeReview,
    KnowledgeReviewRequest,
)
from fastapi import APIRouter, Depends, Query

router = APIRouter(prefix="/api/v1/knowledge", tags=["knowledge"])


@router.get("/assets", response_model=dict[str, list[KnowledgeAssetSummary]])
def list_knowledge_assets(
    repository: Annotated[WorkflowRepository, Depends(get_repository)],
    assetKind: Annotated[str | None, Query(alias="assetKind")] = None,
    dbProfileId: Annotated[str | None, Query(alias="dbProfileId")] = None,
    targetType: Annotated[str | None, Query(alias="targetType")] = None,
    targetSchema: Annotated[str | None, Query(alias="targetSchema")] = None,
    targetName: Annotated[str | None, Query(alias="targetName")] = None,
    lifecycleStatus: Annotated[str | None, Query(alias="lifecycleStatus")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict[str, list[KnowledgeAssetSummary]]:
    try:
        assets = repository.list_knowledge_assets(
            asset_kind=assetKind,
            db_profile_id=dbProfileId,
            target_type=targetType,
            target_schema=targetSchema,
            target_name=targetName,
            lifecycle_status=lifecycleStatus,
            limit=limit,
        )
    except KnowledgePersistenceError as exc:
        raise _knowledge_error(exc) from exc
    return {"assets": [present_knowledge_asset(asset) for asset in assets]}


@router.get("/facts/search")
def search_knowledge_facts(
    repository: Annotated[WorkflowRepository, Depends(get_repository)],
    objectRef: Annotated[str | None, Query(alias="objectRef")] = None,
    factType: Annotated[str | None, Query(alias="factType")] = None,
    status: str | None = None,
    assetKind: Annotated[str | None, Query(alias="assetKind")] = None,
    targetName: Annotated[str | None, Query(alias="targetName")] = None,
    lifecycleStatus: Annotated[str | None, Query(alias="lifecycleStatus")] = None,
    limit: Annotated[int, Query(ge=1, le=200)] = 50,
) -> dict[str, list[KnowledgeFactSearchResult]]:
    try:
        ensure_knowledge_search_filter(
            objectRef=objectRef,
            factType=factType,
            status=status,
            assetKind=assetKind,
            targetName=targetName,
            lifecycleStatus=lifecycleStatus,
        )
        facts = repository.search_knowledge_facts(
            object_ref=objectRef,
            fact_type=factType,
            status=status,
            asset_kind=assetKind,
            target_name=targetName,
            lifecycle_status=lifecycleStatus,
            limit=limit,
        )
    except KnowledgePersistenceError as exc:
        raise _knowledge_error(exc) from exc
    return {"facts": [present_fact_search_result(fact) for fact in facts]}


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


@router.get("/assets/{assetId}/reviews")
def list_knowledge_asset_reviews(
    assetId: str,
    repository: Annotated[WorkflowRepository, Depends(get_repository)],
    versionId: Annotated[str | None, Query(alias="versionId")] = None,
) -> dict[str, str | list[KnowledgeReview]]:
    try:
        reviews = repository.list_knowledge_reviews(assetId, version_id=versionId)
    except KnowledgePersistenceError as exc:
        raise _knowledge_error(exc) from exc
    if reviews is None:
        raise api_http_exception(
            status_code=404,
            detail=f"Unknown knowledge asset: {assetId}",
            code="KNOWLEDGE_ASSET_NOT_FOUND",
        )
    return {
        "assetId": assetId,
        "reviews": [present_knowledge_review(review) for review in reviews],
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


@router.post(
    "/assets/{assetId}/versions/{versionId}/review",
    response_model=KnowledgeReview,
)
def review_knowledge_asset_version(
    assetId: str,
    versionId: str,
    request: KnowledgeReviewRequest,
    repository: Annotated[WorkflowRepository, Depends(get_repository)],
    actor: Annotated[Actor | None, Depends(require_artifact_review_actor)],
) -> KnowledgeReview:
    if actor is not None and not actor.matches_reviewer(request.reviewer):
        raise forbidden_exception(
            "Knowledge review reviewer must match the verified actor identity."
        )
    reviewer = actor.reviewer_id if actor is not None else request.reviewer
    note = sanitize_knowledge_review_note(request.comment)
    try:
        review = repository.review_knowledge_asset_version(
            asset_id=assetId,
            version_id=versionId,
            status=request.status,
            reason_code=request.reason_code,
            note=note,
            reviewer=reviewer,
            actor=reviewer,
        )
    except KnowledgePersistenceError as exc:
        raise _knowledge_error(exc) from exc
    if review is None:
        raise api_http_exception(
            status_code=404,
            detail=f"Unknown knowledge asset version: {versionId}",
            code="KNOWLEDGE_ASSET_NOT_FOUND",
        )
    return present_knowledge_review(review)


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
