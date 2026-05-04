from __future__ import annotations

from api_app.schemas import RegistryVersion
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/registry", tags=["registry"])


ACTIVE_REGISTRY_BINDINGS = (
    RegistryVersion(registryType="PROMPT", version="prompt:sp_analysis@0.1.0", active=True),
    RegistryVersion(
        registryType="TEMPLATE",
        version="template:sp_analysis_doc@0.1.0",
        active=True,
    ),
    RegistryVersion(
        registryType="TEMPLATE",
        version="template:dependency_report@0.1.0",
        active=True,
    ),
    RegistryVersion(
        registryType="TEMPLATE",
        version="template:java_mybatis_sp_wrapper@0.1.0",
        active=True,
    ),
    RegistryVersion(
        registryType="POLICY",
        version="policy:project_ai_java_mybatis_generation_policy@1.0.0",
        active=True,
    ),
    RegistryVersion(
        registryType="DB_PROFILE",
        version="config:mssql/local_docker_profiles.yaml@local",
        active=True,
    ),
    RegistryVersion(
        registryType="GENERATOR",
        version="generation-core-0.1.0",
        active=True,
    ),
)


@router.get("/versions")
def list_registry_versions() -> dict:
    return {
        "versions": [binding.to_response() for binding in ACTIVE_REGISTRY_BINDINGS],
    }
