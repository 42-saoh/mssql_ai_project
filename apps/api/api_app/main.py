from fastapi import FastAPI

from api_app.routes.health import router as health_router
from api_app.routes.jobs import router as jobs_router
from api_app.routes.requests import router as requests_router

app = FastAPI(
    title="AI Agent Platform API",
    version="0.1.0",
    description="Starter API for MSSQL analysis and conversion-code agent platform.",
)

app.include_router(health_router)
app.include_router(jobs_router)
app.include_router(requests_router)
