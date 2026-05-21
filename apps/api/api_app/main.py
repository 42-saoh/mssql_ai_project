from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from typing import Any

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from api_app.dependencies import (
    get_metadata_analysis_service,
    get_metadata_design_service,
    get_repository,
)
from api_app.errors import ERROR_CODE_HEADER, error_payload, normalized_http_error_content
from api_app.platform_db import PlatformPersistenceError
from api_app.recovery_worker import recovery_worker_loop
from api_app.routes.artifacts import router as artifacts_router
from api_app.routes.health import router as health_router
from api_app.routes.jobs import router as jobs_router
from api_app.routes.knowledge import router as knowledge_router
from api_app.routes.metadata import router as metadata_router
from api_app.routes.registry import router as registry_router
from api_app.routes.requests import router as requests_router
from api_app.tracking import (
    CORRELATION_ID_HEADER,
    set_tracking_context_on_request,
    tracking_context_from_headers,
)

app = FastAPI(
    title="AI Agent Platform API",
    version="0.1.0",
    description="Starter API for MSSQL analysis and conversion-code agent platform.",
    lifespan=lambda application: _lifespan(application),
)

_recovery_worker_task: asyncio.Task[None] | None = None


@app.middleware("http")
async def correlation_id_middleware(request: Request, call_next):
    tracking = tracking_context_from_headers(request.headers)
    set_tracking_context_on_request(request, tracking)
    response = await call_next(request)
    response.headers[CORRELATION_ID_HEADER] = tracking.correlation_id
    return response


app.include_router(health_router)
app.include_router(jobs_router)
app.include_router(requests_router)
app.include_router(artifacts_router)
app.include_router(metadata_router)
app.include_router(knowledge_router)
app.include_router(registry_router)


@contextlib.asynccontextmanager
async def _lifespan(application: FastAPI):
    await _start_recovery_worker(application)
    try:
        yield
    finally:
        await _stop_recovery_worker()


async def _start_recovery_worker(application: FastAPI) -> None:
    global _recovery_worker_task
    if _recovery_worker_task is not None and not _recovery_worker_task.done():
        return
    _recovery_worker_task = asyncio.create_task(
        recovery_worker_loop(
            repository_factory=lambda: _resolve_dependency(application, get_repository),
            metadata_service_factory=lambda: _resolve_dependency(
                application,
                get_metadata_analysis_service
            ),
            metadata_design_service_factory=lambda: _resolve_dependency(
                application,
                get_metadata_design_service,
            ),
        )
    )


async def _stop_recovery_worker() -> None:
    global _recovery_worker_task
    if _recovery_worker_task is None:
        return
    _recovery_worker_task.cancel()
    with contextlib.suppress(asyncio.CancelledError):
        await _recovery_worker_task
    _recovery_worker_task = None


def _resolve_dependency(application: FastAPI, provider: Callable[[], Any]) -> Any:
    override = application.dependency_overrides.get(provider)
    if override is not None:
        return override()
    return provider()


@app.exception_handler(HTTPException)
async def http_error_handler(_request: Request, exc: HTTPException):
    headers = dict(exc.headers or {})
    headers.pop(ERROR_CODE_HEADER, None)
    return JSONResponse(
        status_code=exc.status_code,
        content=normalized_http_error_content(exc),
        headers=headers,
    )


@app.exception_handler(RequestValidationError)
async def request_validation_error_handler(_request: Request, _exc: RequestValidationError):
    return JSONResponse(
        status_code=422,
        content=error_payload("Request validation failed.", "VALIDATION_ERROR"),
    )


@app.exception_handler(PlatformPersistenceError)
async def platform_persistence_error_handler(_request: Request, exc: PlatformPersistenceError):
    return JSONResponse(
        status_code=503,
        content=error_payload(str(exc), exc.code),
    )
