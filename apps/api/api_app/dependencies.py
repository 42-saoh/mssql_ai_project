from __future__ import annotations

from functools import lru_cache
from typing import Annotated, cast

from fastapi import Depends, Request

from api_app.auth import (
    Actor,
    AuthConfigurationError,
    AuthenticationRequiredError,
    AuthRoleRepository,
    AuthSettings,
    OidcJwtVerifier,
    extract_bearer_token,
    forbidden_exception,
    load_auth_settings,
    unauthorized_exception,
)
from api_app.errors import api_http_exception
from api_app.metadata_analysis_service import MetadataAnalysisService
from api_app.platform_db import build_platform_repository
from api_app.repositories import WorkflowRepository
from api_app.workflow import WorkflowService
from mssql_mcp_app.tool_cache import clear_metadata_tool_result_cache


@lru_cache(maxsize=1)
def get_repository() -> WorkflowRepository:
    return build_platform_repository()


@lru_cache(maxsize=1)
def get_workflow_service() -> WorkflowService:
    return WorkflowService(get_repository())


@lru_cache(maxsize=1)
def get_metadata_analysis_service() -> MetadataAnalysisService:
    return MetadataAnalysisService()


@lru_cache(maxsize=1)
def get_auth_settings() -> AuthSettings:
    return load_auth_settings()


@lru_cache(maxsize=1)
def get_jwt_verifier() -> OidcJwtVerifier:
    return OidcJwtVerifier(get_auth_settings())


def get_auth_role_repository(
    repository: Annotated[WorkflowRepository, Depends(get_repository)],
) -> AuthRoleRepository:
    return cast(AuthRoleRepository, repository)


def get_current_actor(
    request: Request,
    settings: Annotated[AuthSettings, Depends(get_auth_settings)],
    verifier: Annotated[OidcJwtVerifier, Depends(get_jwt_verifier)],
    role_repository: Annotated[AuthRoleRepository, Depends(get_auth_role_repository)],
) -> Actor | None:
    if not settings.enforcement_enabled:
        return None
    try:
        token = extract_bearer_token(request.headers.get("authorization"))
        identity = verifier.verify(token)
        actor = role_repository.resolve_actor_roles(identity)
    except AuthConfigurationError as exc:
        raise api_http_exception(
            status_code=503,
            detail=str(exc),
            code="DEPENDENCY_BLOCKED",
        ) from exc
    except AuthenticationRequiredError as exc:
        raise unauthorized_exception(str(exc)) from exc
    if actor is None:
        raise unauthorized_exception(
            "Verified OIDC/JWT identity is not mapped to an active PLF actor."
        )
    return actor


def require_roles(*allowed_roles: str):
    allowed = frozenset(role.strip().upper() for role in allowed_roles)

    def dependency(
        actor: Annotated[Actor | None, Depends(get_current_actor)],
    ) -> Actor | None:
        if actor is None:
            return None
        if not actor.roles.intersection(allowed):
            raise forbidden_exception("Actor role does not allow this action.")
        return actor

    return dependency


def reset_application_state() -> None:
    get_workflow_service.cache_clear()
    get_metadata_analysis_service.cache_clear()
    get_repository.cache_clear()
    get_jwt_verifier.cache_clear()
    get_auth_settings.cache_clear()
    clear_metadata_tool_result_cache()
