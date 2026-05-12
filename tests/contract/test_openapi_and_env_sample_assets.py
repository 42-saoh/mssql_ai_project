from __future__ import annotations

import re
from pathlib import Path

import yaml

from ai_agent_domain.models import (
    REQUESTED_OUTPUT_ARTIFACT_TYPES,
    ArtifactStatus,
    ArtifactType,
    JobStatus,
    RequestedOutputType,
    WorkflowStepType,
)


ROOT = Path(__file__).resolve().parents[2]


def _enum_values(enum_type: type) -> list[str]:
    return [item.value for item in enum_type]


def _ddl_check_values(ddl_text: str, constraint_name: str) -> list[str]:
    match = re.search(
        rf"CONSTRAINT {constraint_name} CHECK\s*\([^)]*?IN\s*\(([^)]+)\)",
        ddl_text,
        re.S,
    )
    assert match is not None, constraint_name
    return re.findall(r"'([^']+)'", match.group(1))


def test_openapi_skeleton_exists_and_parses() -> None:
    path = ROOT / "spec" / "openapi" / "ai_agent_platform_openapi_v1.yaml"
    assert path.exists()

    data = yaml.safe_load(path.read_text(encoding="utf-8"))

    assert data["openapi"] == "3.1.0"
    assert data["info"]["title"] == "MSSQL Analysis Agent Platform API"
    assert "/health" in data["paths"]
    assert "/api/v1/requests/sp-analysis" in data["paths"]
    assert "/api/v1/jobs" in data["paths"]
    assert "/api/v1/jobs/{jobId}" in data["paths"]
    assert "/api/v1/artifacts/{artifactId}/validation/latest" in data["paths"]
    assert "SPAnalysisRequest" in data["components"]["schemas"]
    assert "Artifact" in data["components"]["schemas"]
    assert "ValidationReport" in data["components"]["schemas"]
    assert "RequestedOutputType" in data["components"]["schemas"]
    assert "WorkflowStepType" in data["components"]["schemas"]
    assert "/api/v1/metadata/search" in data["paths"]
    assert "MetadataSearchResponse" in data["components"]["schemas"]


def test_openapi_metadata_search_contract_matches_p09_surface() -> None:
    openapi = yaml.safe_load(
        (ROOT / "spec" / "openapi" / "ai_agent_platform_openapi_v1.yaml").read_text(
            encoding="utf-8"
        )
    )
    operation = openapi["paths"]["/api/v1/metadata/search"]["get"]
    schemas = openapi["components"]["schemas"]

    assert operation["operationId"] == "searchMetadataObjects"
    assert operation["tags"] == ["metadata"]
    assert {parameter["name"] for parameter in operation["parameters"]} == {
        "dbProfileId",
        "query",
        "objectTypes",
        "limit",
    }
    object_types = next(
        parameter for parameter in operation["parameters"] if parameter["name"] == "objectTypes"
    )
    assert object_types["style"] == "form"
    assert object_types["explode"] is True
    assert object_types["schema"]["items"] == {
        "$ref": "#/components/schemas/MetadataSearchObjectType"
    }
    assert schemas["MetadataSearchObjectType"]["enum"] == [
        "PROCEDURE",
        "TABLE",
        "VIEW",
        "FUNCTION",
    ]

    responses = operation["responses"]
    assert responses["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/MetadataSearchResponse"
    }
    assert responses["403"] == {"$ref": "#/components/responses/Forbidden"}
    assert responses["424"] == {"$ref": "#/components/responses/DependencyBlocked"}
    assert responses["503"] == {"$ref": "#/components/responses/DependencyBlocked"}

    result_schema = schemas["MetadataSearchResult"]
    assert result_schema["properties"]["objectIdentity"] == {
        "$ref": "#/components/schemas/MetadataObjectIdentity"
    }
    assert result_schema["properties"]["evidenceRefs"]["items"] == {
        "$ref": "#/components/schemas/EvidenceRef"
    }
    forbidden_response_fields = {
        "rowData",
        "row_data",
        "definition",
        "sqlText",
        "ddl",
        "dml",
        "execute",
    }
    response_properties = set(schemas["MetadataSearchResponse"]["properties"])
    result_properties = set(result_schema["properties"])
    identity_properties = set(schemas["MetadataObjectIdentity"]["properties"])
    assert forbidden_response_fields.isdisjoint(
        response_properties | result_properties | identity_properties
    )


def test_openapi_domain_and_ddl_enums_share_baseline_names() -> None:
    openapi = yaml.safe_load(
        (ROOT / "spec" / "openapi" / "ai_agent_platform_openapi_v1.yaml").read_text(
            encoding="utf-8"
        )
    )
    schemas = openapi["components"]["schemas"]
    ddl_text = (ROOT / "db" / "schema" / "ai_agent_platform_schema_v2_dbo_prefix.sql").read_text(
        encoding="utf-8"
    )
    validation_complete_ddl = (
        ROOT / "db" / "schema" / "ai_agent_platform_schema_v4_validation_complete_status.sql"
    ).read_text(encoding="utf-8")

    assert schemas["JobStatus"]["enum"] == _enum_values(JobStatus)
    assert schemas["WorkflowStepType"]["enum"] == _enum_values(WorkflowStepType)
    assert schemas["ArtifactType"]["enum"] == _enum_values(ArtifactType)
    assert schemas["ArtifactStatus"]["enum"] == _enum_values(ArtifactStatus)
    assert schemas["RequestedOutputType"]["enum"] == _enum_values(RequestedOutputType)

    assert _enum_values(JobStatus) == _ddl_check_values(
        validation_complete_ddl, "CHK_CORE_JOBS_CURRENT_STATUS_CD"
    )
    assert _enum_values(ArtifactType) == _ddl_check_values(ddl_text, "CHK_ARTIFACTS_TYPE_CD")
    assert _enum_values(ArtifactStatus) == _ddl_check_values(
        ddl_text, "CHK_ARTIFACTS_STATUS_CD"
    )

    outputs_schema = schemas["SPAnalysisRequest"]["properties"]["outputs"]["items"]
    assert outputs_schema == {"$ref": "#/components/schemas/RequestedOutputType"}


def test_requested_output_groups_map_to_persisted_artifact_types() -> None:
    assert set(REQUESTED_OUTPUT_ARTIFACT_TYPES) == set(RequestedOutputType)
    assert REQUESTED_OUTPUT_ARTIFACT_TYPES[RequestedOutputType.JAVA_MYBATIS_DRAFT] == (
        ArtifactType.DTO_DRAFT,
        ArtifactType.SERVICE_DRAFT,
        ArtifactType.MAPPER_INTERFACE,
        ArtifactType.MAPPER_XML,
    )
    for requested_output, artifact_types in REQUESTED_OUTPUT_ARTIFACT_TYPES.items():
        assert isinstance(requested_output, RequestedOutputType)
        assert artifact_types
        assert all(isinstance(artifact_type, ArtifactType) for artifact_type in artifact_types)


def test_validation_rules_reference_known_artifact_types() -> None:
    payload = yaml.safe_load(
        (ROOT / "spec" / "validation" / "validation_rules.yaml").read_text(encoding="utf-8")
    )

    known_artifacts = set(_enum_values(ArtifactType))
    non_artifact_scopes = {"artifact-workflow", "mssql-mcp", "repository-workflow"}
    for rule in payload["rules"]:
        for target in rule["appliesTo"]:
            assert target in known_artifacts | non_artifact_scopes, (rule["id"], target)


def test_env_sample_contains_worktree_port_defaults_without_secrets() -> None:
    path = ROOT / ".env.example"
    assert path.exists()

    text = path.read_text(encoding="utf-8")

    assert "WORKTREE_PORT_SLOT=\nAPP_PORT=\nMCP_PORT=\nWEB_PORT=" in text
    assert "Leave APP/MCP/WEB port empty" in text
    assert "PLATFORM_DB_PASSWORD=\n" in text
    assert "MSSQL_METADATA_PASSWORD=\n" in text
    assert "MSSQL_METADATA_USER=readonly_metadata_user\n" in text
    assert "MSSQL_METADATA_USER=sa" not in text
    assert "MSSQL_METADATA_DEFAULT_PROFILE_ID=master" in text
    assert "MSSQL_METADATA_TDS_VERSION=7.4" in text
    assert "P21_LIVE_PORTAL_GATE=0" in text
    assert "P27_HARD_LIVE_GATE=0" in text
    assert "PORTAL_API_MODE=http" in text
    assert "PORTAL_API_BASE_URL=\n" in text
    assert "TPsaoh" not in text


def test_env_sample_matches_parallel_manifest_basis() -> None:
    manifest = yaml.safe_load(
        (ROOT / "ops" / "codex-parallel" / "REQUEST_MANIFEST.yaml").read_text(
            encoding="utf-8"
        )
    )

    assert manifest["reproducibility"]["env_sample"] == ".env.example"
    assert manifest["reproducibility"]["env_example"] == ".env.example"
    assert ".env.example" in manifest["basis"]
