from fastapi import FastAPI
from fastapi.responses import JSONResponse

from api_app.platform_db import PlatformPersistenceError
from api_app.routes.approvals import router as approvals_router
from api_app.routes.artifacts import router as artifacts_router
from api_app.routes.health import router as health_router
from api_app.routes.jobs import router as jobs_router
from api_app.routes.metadata import router as metadata_router
from api_app.routes.registry import router as registry_router
from api_app.routes.requests import router as requests_router

app = FastAPI(
    title="AI Agent Platform API",
    version="0.1.0",
    description="Starter API for MSSQL analysis and conversion-code agent platform.",
)

app.include_router(health_router)
app.include_router(jobs_router)
app.include_router(requests_router)
app.include_router(artifacts_router)
app.include_router(approvals_router)
app.include_router(metadata_router)
app.include_router(registry_router)


@app.exception_handler(PlatformPersistenceError)
async def platform_persistence_error_handler(_request, exc: PlatformPersistenceError):
    return JSONResponse(status_code=503, content={"detail": str(exc)})
