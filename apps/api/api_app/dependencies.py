from __future__ import annotations

from functools import lru_cache

from api_app.platform_db import build_platform_repository
from api_app.repositories import WorkflowRepository
from api_app.workflow import WorkflowService


@lru_cache(maxsize=1)
def get_repository() -> WorkflowRepository:
    return build_platform_repository()


@lru_cache(maxsize=1)
def get_workflow_service() -> WorkflowService:
    return WorkflowService(get_repository())


def reset_application_state() -> None:
    get_workflow_service.cache_clear()
    get_repository.cache_clear()
