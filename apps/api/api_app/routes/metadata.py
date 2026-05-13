from __future__ import annotations

from typing import Annotated, Literal

from api_app.dependencies import get_metadata_analysis_service, get_repository
from api_app.errors import api_http_exception
from api_app.repositories import KnowledgePersistenceError, WorkflowRepository
from api_app.metadata_analysis_service import MetadataAnalysisService
from api_app.metadata_service import (
    DEFAULT_METADATA_SEARCH_OBJECT_TYPES,
    MetadataSearchDependencyError,
    invoke_metadata_tool,
    list_safe_metadata_profiles,
    list_safe_metadata_tools,
    search_metadata_objects,
)
from api_app.schemas import (
    MetadataAnalysisRequest,
    MetadataAnalysisResponse,
    MetadataSearchResponse,
    MetadataToolInvokeRequest,
    MetadataToolInvokeResponse,
)
from fastapi import APIRouter, Depends, Path, Query
from mssql_mcp_app.errors import MetadataToolError

router = APIRouter(prefix="/api/v1/metadata", tags=["metadata"])

SearchObjectType = Literal["PROCEDURE", "TABLE", "VIEW", "FUNCTION"]


@router.get("/db-profiles")
def list_metadata_profiles() -> dict:
    default_profile_id, profiles = list_safe_metadata_profiles()
    return {
        "defaultProfileId": default_profile_id,
        "profiles": [profile.to_response() for profile in profiles],
    }


@router.get("/tools")
def list_metadata_tools() -> dict:
    return {
        "tools": [tool.to_response() for tool in list_safe_metadata_tools()],
    }


@router.post("/tools/{toolName}/invoke", response_model=MetadataToolInvokeResponse)
def invoke_metadata_tool_route(
    tool_name: Annotated[str, Path(alias="toolName", min_length=1)],
    request: MetadataToolInvokeRequest,
) -> MetadataToolInvokeResponse:
    try:
        return invoke_metadata_tool(tool_name=tool_name, arguments=request.arguments)
    except MetadataSearchDependencyError as exc:
        raise api_http_exception(
            status_code=exc.status_code,
            detail=exc.detail,
            code=exc.code,
        ) from exc
    except MetadataToolError as exc:
        raise api_http_exception(
            status_code=exc.http_status,
            detail=exc.message,
            code=exc.code,
        ) from exc
    except KnowledgePersistenceError as exc:
        raise api_http_exception(
            status_code=exc.status_code,
            detail=str(exc),
            code=exc.code,
        ) from exc
    except ValueError as exc:
        raise api_http_exception(
            status_code=422,
            detail=str(exc),
            code="VALIDATION_ERROR",
        ) from exc


@router.get("/search", response_model=MetadataSearchResponse)
def search_metadata(
    dbProfileId: Annotated[str, Query(min_length=1)],
    query: Annotated[str, Query(min_length=1)],
    objectTypes: Annotated[list[SearchObjectType] | None, Query()] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> MetadataSearchResponse:
    try:
        return search_metadata_objects(
            db_profile_id=dbProfileId,
            query=query,
            object_types=tuple(objectTypes or DEFAULT_METADATA_SEARCH_OBJECT_TYPES),
            limit=limit,
        )
    except MetadataSearchDependencyError as exc:
        raise api_http_exception(
            status_code=exc.status_code,
            detail=exc.detail,
            code=exc.code,
        ) from exc
    except MetadataToolError as exc:
        raise api_http_exception(
            status_code=exc.http_status,
            detail=exc.message,
            code=exc.code,
        ) from exc
    except KnowledgePersistenceError as exc:
        raise api_http_exception(
            status_code=exc.status_code,
            detail=str(exc),
            code=exc.code,
        ) from exc
    except ValueError as exc:
        raise api_http_exception(
            status_code=422,
            detail=str(exc),
            code="VALIDATION_ERROR",
        ) from exc


@router.post("/analyze", response_model=MetadataAnalysisResponse)
def analyze_metadata(
    request: MetadataAnalysisRequest,
    service: Annotated[MetadataAnalysisService, Depends(get_metadata_analysis_service)],
    repository: Annotated[WorkflowRepository, Depends(get_repository)],
) -> MetadataAnalysisResponse:
    try:
        service.repository = repository
        return service.analyze(request)
    except MetadataSearchDependencyError as exc:
        raise api_http_exception(
            status_code=exc.status_code,
            detail=exc.detail,
            code=exc.code,
        ) from exc
    except MetadataToolError as exc:
        raise api_http_exception(
            status_code=exc.http_status,
            detail=exc.message,
            code=exc.code,
        ) from exc
    except ValueError as exc:
        raise api_http_exception(
            status_code=422,
            detail=str(exc),
            code="VALIDATION_ERROR",
        ) from exc
