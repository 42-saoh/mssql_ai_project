from __future__ import annotations

from typing import Annotated, Literal

from api_app.dependencies import (
    get_metadata_analysis_service,
    get_repository,
)
from api_app.errors import api_http_exception
from api_app.metadata_analysis_runs import (
    create_metadata_analysis_run,
    execute_metadata_analysis_run,
    get_metadata_analysis_run as read_metadata_analysis_run,
)
from api_app.repositories import (
    KnowledgePersistenceError,
    MetadataAnalysisRunPersistenceError,
    WorkflowRepository,
)
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
    MetadataAnalysisRunStatus,
    MetadataSearchResponse,
    MetadataToolInvokeRequest,
    MetadataToolInvokeResponse,
)
from fastapi import APIRouter, BackgroundTasks, Depends, Path, Query, status
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


@router.post(
    "/analysis-runs",
    response_model=MetadataAnalysisRunStatus,
    status_code=status.HTTP_202_ACCEPTED,
)
def submit_metadata_analysis_run(
    request: MetadataAnalysisRequest,
    background_tasks: BackgroundTasks,
    service: Annotated[MetadataAnalysisService, Depends(get_metadata_analysis_service)],
    repository: Annotated[WorkflowRepository, Depends(get_repository)],
) -> MetadataAnalysisRunStatus:
    try:
        run = create_metadata_analysis_run(repository=repository, request=request)
    except MetadataAnalysisRunPersistenceError as exc:
        raise api_http_exception(
            status_code=exc.status_code,
            detail=str(exc),
            code=exc.code,
        ) from exc
    background_tasks.add_task(
        execute_metadata_analysis_run,
        run_id=run.run_id,
        request=request.model_copy(deep=True),
        service=service,
        repository=repository,
    )
    return run


@router.get("/analysis-runs/{runId}", response_model=MetadataAnalysisRunStatus)
def get_metadata_analysis_run(
    run_id: Annotated[str, Path(alias="runId", min_length=1)],
    repository: Annotated[WorkflowRepository, Depends(get_repository)],
) -> MetadataAnalysisRunStatus:
    try:
        run = read_metadata_analysis_run(repository=repository, run_id=run_id)
    except MetadataAnalysisRunPersistenceError as exc:
        raise api_http_exception(
            status_code=exc.status_code,
            detail=str(exc),
            code=exc.code,
        ) from exc
    if run is None:
        raise api_http_exception(
            status_code=404,
            detail="Metadata analysis run was not found.",
            code="METADATA_ANALYSIS_RUN_NOT_FOUND",
        )
    return run
