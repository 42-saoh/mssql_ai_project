from __future__ import annotations

from ai_agent_runtime.gateway import model_profile_from_env
from ai_agent_runtime.models import (
    FAST_TEST_MODEL_PROFILE_ID,
    METADATA_ANALYSIS_OUTPUT_SCHEMA_VERSION,
    METADATA_ANALYSIS_PROMPT_VERSION,
    OUTPUT_SCHEMA_VERSION,
    PLATFORM_TOOL_PLANNER_OUTPUT_SCHEMA_VERSION,
    PLATFORM_TOOL_PLANNER_PROMPT_VERSION,
    PROMPT_VERSION,
    TOOL_PLANNER_OUTPUT_SCHEMA_VERSION,
    TOOL_PLANNER_PROMPT_VERSION,
)
from api_app.schemas import RegistryVersion
from fastapi import APIRouter

router = APIRouter(prefix="/api/v1/registry", tags=["registry"])


def active_registry_bindings() -> tuple[RegistryVersion, ...]:
    fast_test_profile = model_profile_from_env(FAST_TEST_MODEL_PROFILE_ID)
    return (
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
        RegistryVersion(
            registryType="MODEL",
            version="model:openai_sp_semantic_analysis@0.1.0",
            active=True,
        ),
        RegistryVersion(
            registryType="MODEL",
            version=fast_test_profile.registry_ref,
            active=True,
        ),
        RegistryVersion(
            registryType="PROMPT",
            version=PROMPT_VERSION,
            active=True,
        ),
        RegistryVersion(
            registryType="SCHEMA",
            version=OUTPUT_SCHEMA_VERSION,
            active=True,
        ),
        RegistryVersion(
            registryType="PROMPT",
            version=TOOL_PLANNER_PROMPT_VERSION,
            active=True,
        ),
        RegistryVersion(
            registryType="SCHEMA",
            version=TOOL_PLANNER_OUTPUT_SCHEMA_VERSION,
            active=True,
        ),
        RegistryVersion(
            registryType="PROMPT",
            version=PLATFORM_TOOL_PLANNER_PROMPT_VERSION,
            active=True,
        ),
        RegistryVersion(
            registryType="SCHEMA",
            version=PLATFORM_TOOL_PLANNER_OUTPUT_SCHEMA_VERSION,
            active=True,
        ),
        RegistryVersion(
            registryType="PROMPT",
            version=METADATA_ANALYSIS_PROMPT_VERSION,
            active=True,
        ),
        RegistryVersion(
            registryType="SCHEMA",
            version=METADATA_ANALYSIS_OUTPUT_SCHEMA_VERSION,
            active=True,
        ),
    )


@router.get("/versions")
def list_registry_versions() -> dict:
    return {
        "versions": [binding.to_response() for binding in active_registry_bindings()],
    }
