from __future__ import annotations

from typing import Annotated, Literal

from api_app.errors import api_http_exception
from api_app.metadata_service import (
    DEFAULT_METADATA_SEARCH_OBJECT_TYPES,
    MetadataSearchDependencyError,
    list_safe_metadata_profiles,
    list_safe_metadata_tools,
    search_metadata_objects,
)
from api_app.schemas import MetadataSearchResponse
from fastapi import APIRouter, Query
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
    except ValueError as exc:
        raise api_http_exception(
            status_code=422,
            detail=str(exc),
            code="VALIDATION_ERROR",
        ) from exc
