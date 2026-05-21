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
    assert "/api/v1/requests/sp-analysis/batch" in data["paths"]
    assert "/api/v1/jobs" in data["paths"]
    assert "/api/v1/jobs/{jobId}" in data["paths"]
    assert "/api/v1/jobs/{jobId}/knowledge-assets" in data["paths"]
    assert "/api/v1/knowledge/assets/{assetId}" in data["paths"]
    assert "/api/v1/knowledge/assets/{assetId}/versions" in data["paths"]
    assert "/api/v1/knowledge/assets/{assetId}/versions/{versionId}/facts" in data["paths"]
    assert "/api/v1/knowledge/exports" in data["paths"]
    assert "/api/v1/artifacts/{artifactId}/validation/latest" in data["paths"]
    assert "SPAnalysisRequest" in data["components"]["schemas"]
    assert "SPAnalysisBatchRequest" in data["components"]["schemas"]
    assert (
        data["components"]["schemas"]["SPAnalysisOptions"]["properties"][
            "useAiToolOrchestration"
        ]["default"]
        is True
    )
    assert (
        data["components"]["schemas"]["SPAnalysisOptions"]["properties"][
            "usePlatformToolOrchestration"
        ]["default"]
        is True
    )
    assert (
        data["components"]["schemas"]["SPAnalysisOptions"]["properties"][
            "sourceContextMode"
        ]["default"]
        == "RETRIEVED_SPANS"
    )
    assert (
        data["components"]["schemas"]["SPAnalysisOptions"]["properties"][
            "sourceDependencyMode"
        ]["default"]
        == "CONFIRMED_PROCEDURES"
    )
    assert "Artifact" in data["components"]["schemas"]
    assert "ValidationReport" in data["components"]["schemas"]
    assert "RequestedOutputType" in data["components"]["schemas"]
    assert "WorkflowStepType" in data["components"]["schemas"]
    assert "/api/v1/metadata/search" in data["paths"]
    assert "/api/v1/metadata/procedure-search" not in data["paths"]
    assert "/api/v1/metadata/analyze" in data["paths"]
    assert "/api/v1/metadata/analysis-runs" in data["paths"]
    assert "/api/v1/metadata/analysis-runs/{runId}" in data["paths"]
    assert "/api/v1/metadata/design-runs" in data["paths"]
    assert "/api/v1/metadata/design-runs/{runId}" in data["paths"]
    assert "/api/v1/metadata/design-conversations/{conversationId}" in data["paths"]
    assert "/api/v1/metadata/tools/{toolName}/invoke" in data["paths"]
    assert "MetadataSearchResponse" in data["components"]["schemas"]
    assert "MetadataSearchTableSummary" in data["components"]["schemas"]
    assert "MetadataSearchColumnSummary" in data["components"]["schemas"]
    assert "MetadataProcedureSearchResponse" not in data["components"]["schemas"]
    assert "MetadataAnalysisResponse" in data["components"]["schemas"]
    assert "MetadataAnalysisRunStatus" in data["components"]["schemas"]
    assert "MetadataDesignRunRequest" in data["components"]["schemas"]
    assert "MetadataDesignRunStatus" in data["components"]["schemas"]
    assert "MetadataDesignResult" in data["components"]["schemas"]
    assert "MetadataToolInvokeResponse" in data["components"]["schemas"]
    assert "KnowledgeAssetSummary" in data["components"]["schemas"]
    assert "KnowledgeExportResponse" in data["components"]["schemas"]


def test_openapi_exposes_canonical_target_keys_on_public_history_surface() -> None:
    openapi = yaml.safe_load(
        (ROOT / "spec" / "openapi" / "ai_agent_platform_openapi_v1.yaml").read_text(
            encoding="utf-8"
        )
    )
    paths = openapi["paths"]
    schemas = openapi["components"]["schemas"]

    job_parameters = paths["/api/v1/jobs"]["get"]["parameters"]
    assert {parameter["name"] for parameter in job_parameters} == {"limit", "targetKey"}
    assert schemas["Job"]["properties"]["targetKey"]["type"] == "string"
    assert schemas["ArtifactSummary"]["properties"]["targetKey"]["type"] == "string"
    assert schemas["AgentRunSummary"]["properties"]["targetKey"]["type"] == "string"
    assert schemas["KnowledgeAssetSummary"]["properties"]["targetKey"]["type"] == "string"
    assert schemas["MetadataSearchResult"]["properties"]["targetKey"]["type"] == "string"
    assert schemas["MetadataObjectProfile"]["properties"]["targetKey"]["type"] == "string"
    assert schemas["MetadataDependencyGraphNode"]["properties"]["targetKey"]["type"] == "string"


def test_openapi_metadata_search_and_design_contracts_are_separate() -> None:
    openapi = yaml.safe_load(
        (ROOT / "spec" / "openapi" / "ai_agent_platform_openapi_v1.yaml").read_text(
            encoding="utf-8"
        )
    )
    schemas = openapi["components"]["schemas"]

    assert "/api/v1/metadata/search" in openapi["paths"]
    assert "/api/v1/metadata/procedure-search" not in openapi["paths"]
    search_route = openapi["paths"]["/api/v1/metadata/search"]["get"]
    assert search_route["operationId"] == "searchMetadataObjects"
    assert search_route["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/MetadataSearchResponse"
    }
    assert schemas["MetadataSearchObjectType"]["enum"] == [
        "PROCEDURE",
        "TABLE",
        "COLUMN",
        "VIEW",
        "FUNCTION",
    ]
    assert schemas["MetadataSearchResponse"]["properties"]["objectTypes"]["items"] == {
        "$ref": "#/components/schemas/MetadataSearchObjectType"
    }
    assert schemas["MetadataObjectIdentity"]["properties"]["type"]["enum"] == [
        "PROCEDURE",
        "TABLE",
        "VIEW",
        "FUNCTION",
    ]
    request_schema = schemas["MetadataDesignRunRequest"]
    design_options = schemas["MetadataDesignOptions"]
    design_result = schemas["MetadataDesignResult"]
    interpreted_intent = schemas["MetadataDesignInterpretedIntent"]

    assert "MetadataDesignSearchInputs" not in schemas
    assert "searchInputs" not in request_schema["properties"]
    assert "intentMode" not in design_options["properties"]
    assert "SEARCH_METADATA" not in interpreted_intent["properties"]["intent"]["enum"]
    assert "resultKind" not in design_result["properties"]
    assert "searchResult" not in design_result["properties"]
    assert design_result["properties"]["tableProposal"] == {
        "$ref": "#/components/schemas/MetadataTableProposal"
    }

    result_schema = schemas["MetadataSearchResult"]
    assert result_schema["properties"]["objectIdentity"] == {
        "$ref": "#/components/schemas/MetadataSearchObjectIdentity"
    }
    assert result_schema["properties"]["description"]["type"] == ["string", "null"]
    assert result_schema["properties"]["logicalName"]["type"] == ["string", "null"]
    assert result_schema["properties"]["dataType"]["type"] == ["string", "null"]
    assert result_schema["properties"]["table"] == {
        "anyOf": [
            {"$ref": "#/components/schemas/MetadataSearchTableSummary"},
            {"type": "null"},
        ]
    }
    assert result_schema["properties"]["column"] == {
        "anyOf": [
            {"$ref": "#/components/schemas/MetadataSearchColumnSummary"},
            {"type": "null"},
        ]
    }
    assert result_schema["properties"]["columns"]["items"] == {
        "$ref": "#/components/schemas/MetadataSearchColumnSummary"
    }
    assert schemas["MetadataSearchTableSummary"]["required"] == ["schema", "name"]
    assert schemas["MetadataSearchColumnSummary"]["required"] == ["name"]
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
    identity_properties = set(schemas["MetadataObjectIdentity"]["properties"]) | set(
        schemas["MetadataSearchObjectIdentity"]["properties"]
    )
    assert forbidden_response_fields.isdisjoint(
        response_properties
        | result_properties
        | identity_properties
    )


def test_openapi_metadata_tool_invocation_contract_matches_p28_surface() -> None:
    openapi = yaml.safe_load(
        (ROOT / "spec" / "openapi" / "ai_agent_platform_openapi_v1.yaml").read_text(
            encoding="utf-8"
        )
    )
    operation = openapi["paths"]["/api/v1/metadata/tools/{toolName}/invoke"]["post"]
    schemas = openapi["components"]["schemas"]

    assert operation["operationId"] == "invokeMetadataTool"
    assert operation["tags"] == ["metadata"]
    tool_name = operation["parameters"][0]
    assert tool_name["name"] == "toolName"
    assert tool_name["schema"]["enum"] == [
        "get_dependency_closure",
        "resolve_dependency_reference",
    ]
    assert operation["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/MetadataToolInvokeRequest"
    }
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/MetadataToolInvokeResponse"
    }
    assert operation["responses"]["429"] == {"$ref": "#/components/responses/Backpressure"}
    assert schemas["MetadataToolSummary"]["properties"]["invokable"] == {
        "type": "boolean",
        "description": "True only for public API invocation allowlisted metadata tools.",
    }
    assert schemas["MetadataToolInvokeRequest"]["additionalProperties"] is False
    assert schemas["MetadataToolInvokeRequest"]["required"] == ["arguments"]
    assert schemas["MetadataToolInvokeResponse"]["additionalProperties"] is False
    assert schemas["MetadataToolInvokeResponse"]["required"] == [
        "ok",
        "toolName",
        "dbProfileId",
        "snapshotId",
        "collectedAt",
        "evidenceRefs",
        "data",
    ]
    forbidden_response_fields = {
        "rowData",
        "row_data",
        "definition",
        "sqlText",
        "ddl",
        "dml",
        "execute",
        "rawStorage",
    }
    assert forbidden_response_fields.isdisjoint(
        set(schemas["MetadataToolInvokeResponse"]["properties"])
    )


def test_openapi_metadata_analysis_contract_matches_bounded_ai_mcp_surface() -> None:
    openapi = yaml.safe_load(
        (ROOT / "spec" / "openapi" / "ai_agent_platform_openapi_v1.yaml").read_text(
            encoding="utf-8"
        )
    )
    operation = openapi["paths"]["/api/v1/metadata/analyze"]["post"]
    schemas = openapi["components"]["schemas"]

    assert operation["operationId"] == "analyzeMetadata"
    assert operation["tags"] == ["metadata"]
    assert operation["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/MetadataAnalysisRequest"
    }
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/MetadataAnalysisResponse"
    }
    options = schemas["MetadataAnalysisOptions"]["properties"]
    assert options["useLlmAnalysis"]["default"] is True
    assert options["useAiToolOrchestration"]["default"] is True
    assert options["persistKnowledge"]["default"] is True
    assert options["generateDtoDrafts"]["default"] is False
    assert options["maxTargets"]["maximum"] == 5
    response_properties = set(schemas["MetadataAnalysisResponse"]["properties"])
    assert {
        "aiToolEvidence",
        "deterministicFacts",
        "objectInsights",
        "objectProfiles",
        "insightGroups",
        "dependencyGraph",
        "dtoReadiness",
        "generatedDrafts",
        "reviewMarkers",
        "componentInvocations",
        "knowledgeAssets",
    } <= response_properties
    assert schemas["MetadataGeneratedDraft"]["properties"]["artifactType"]["enum"] == [
        "DTO_DRAFT"
    ]
    assert schemas["MetadataAnalysisResponse"]["properties"]["generatedDrafts"] == {
        "type": "array",
        "items": {"$ref": "#/components/schemas/MetadataGeneratedDraft"},
    }
    assert schemas["AiToolEvidenceSummary"]["properties"]["plannerMetrics"] == {
        "$ref": "#/components/schemas/PlannerMetrics"
    }
    assert "claimSupportRate" in schemas["PlannerMetrics"]["properties"]
    assert "cacheHitCount" in schemas["PlannerMetrics"]["properties"]
    assert "cacheMissCount" in schemas["PlannerMetrics"]["properties"]
    forbidden_response_fields = {
        "rowData",
        "row_data",
        "definition",
        "sqlText",
        "ddl",
        "dml",
        "execute",
        "rawStorage",
    }
    assert forbidden_response_fields.isdisjoint(response_properties)


def test_openapi_metadata_analysis_run_contract_matches_async_polling_surface() -> None:
    openapi = yaml.safe_load(
        (ROOT / "spec" / "openapi" / "ai_agent_platform_openapi_v1.yaml").read_text(
            encoding="utf-8"
        )
    )
    paths = openapi["paths"]
    schemas = openapi["components"]["schemas"]

    submit = paths["/api/v1/metadata/analysis-runs"]["post"]
    poll = paths["/api/v1/metadata/analysis-runs/{runId}"]["get"]

    assert submit["operationId"] == "submitMetadataAnalysisRun"
    assert submit["tags"] == ["metadata"]
    assert "background recovery worker" in submit["description"]
    assert "reclaims stale `RUNNING`" in submit["description"]
    assert submit["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/MetadataAnalysisRequest"
    }
    assert submit["responses"]["202"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/MetadataAnalysisRunStatus"
    }
    assert poll["operationId"] == "getMetadataAnalysisRun"
    assert poll["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/MetadataAnalysisRunStatus"
    }
    assert {
        parameter["name"] for parameter in poll["parameters"]
    } == {"runId"}
    run_schema = schemas["MetadataAnalysisRunStatus"]
    assert run_schema["properties"]["status"]["enum"] == [
        "QUEUED",
        "RUNNING",
        "SUCCEEDED",
        "FAILED",
    ]
    assert run_schema["properties"]["request"] == {
        "$ref": "#/components/schemas/MetadataAnalysisRequest"
    }
    assert run_schema["properties"]["startedAt"]["oneOf"] == [
        {"type": "string", "format": "date-time"},
        {"type": "null"},
    ]
    assert run_schema["properties"]["completedAt"]["oneOf"] == [
        {"type": "string", "format": "date-time"},
        {"type": "null"},
    ]
    assert run_schema["properties"]["analysis"]["oneOf"] == [
        {"$ref": "#/components/schemas/MetadataAnalysisResponse"},
        {"type": "null"},
    ]
    assert run_schema["properties"]["error"]["oneOf"] == [
        {"$ref": "#/components/schemas/MetadataAnalysisRunError"},
        {"type": "null"},
    ]


def test_openapi_metadata_design_chat_contract_matches_p38_surface() -> None:
    openapi = yaml.safe_load(
        (ROOT / "spec" / "openapi" / "ai_agent_platform_openapi_v1.yaml").read_text(
            encoding="utf-8"
        )
    )
    paths = openapi["paths"]
    schemas = openapi["components"]["schemas"]

    submit = paths["/api/v1/metadata/design-runs"]["post"]
    poll = paths["/api/v1/metadata/design-runs/{runId}"]["get"]
    conversation = paths["/api/v1/metadata/design-conversations/{conversationId}"]["get"]

    assert submit["operationId"] == "submitMetadataDesignRun"
    assert submit["tags"] == ["metadata"]
    submit_description = re.sub(r"\s+", " ", submit["description"])
    assert "durable metadata design chat run" in submit_description
    assert "read-only" in submit_description
    assert "workflow artifact persistence" in submit_description
    assert submit["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/MetadataDesignRunRequest"
    }
    assert submit["responses"]["202"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/MetadataDesignRunStatus"
    }
    assert poll["operationId"] == "getMetadataDesignRun"
    assert poll["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/MetadataDesignRunStatus"
    }
    assert conversation["operationId"] == "getMetadataDesignConversation"
    assert conversation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/MetadataDesignConversation"
    }

    request_schema = schemas["MetadataDesignRunRequest"]
    assert request_schema["required"] == ["dbProfileId", "message"]
    assert request_schema["properties"]["designInputs"] == {
        "$ref": "#/components/schemas/MetadataDesignInputs"
    }
    assert request_schema["properties"]["options"] == {
        "$ref": "#/components/schemas/MetadataDesignOptions"
    }
    assert schemas["MetadataDesignOptions"]["properties"]["generateDtoDraft"][
        "default"
    ] is True
    assert schemas["MetadataDesignOptions"]["properties"]["maxCandidates"]["maximum"] == 10
    assert schemas["MetadataDesignOptions"]["properties"]["conversationMode"] == {
        "type": "string",
        "enum": ["NEW_DESIGN", "REFINE_CURRENT"],
        "default": "NEW_DESIGN",
    }

    result_schema = schemas["MetadataDesignResult"]
    result_properties = set(result_schema["properties"])
    assert {
        "assistantMessage",
        "interpretedIntent",
        "appliedChanges",
        "relatedMetadata",
        "standardizationMappings",
        "tableProposal",
        "dtoDraft",
        "aiToolEvidence",
        "modelInvocation",
        "reviewMarkers",
        "caveats",
    } <= result_properties
    assert result_schema["properties"]["interpretedIntent"] == {
        "$ref": "#/components/schemas/MetadataDesignInterpretedIntent"
    }
    assert result_schema["properties"]["appliedChanges"]["items"] == {
        "$ref": "#/components/schemas/MetadataDesignAppliedChange"
    }
    assert schemas["MetadataDesignInterpretedIntent"]["properties"]["modifications"][
        "items"
    ] == {"$ref": "#/components/schemas/MetadataDesignIntentChange"}
    assert "proposedDescription" in schemas["MetadataStandardizationMapping"][
        "properties"
    ]
    table_schema = schemas["MetadataTableProposal"]
    assert "createTableScriptPreview" in table_schema["properties"]
    assert "DDL_DRAFT" not in str(result_schema)
    assert schemas["MetadataGeneratedDraft"]["properties"]["artifactType"]["enum"] == [
        "DTO_DRAFT"
    ]
    run_schema = schemas["MetadataDesignRunStatus"]
    assert run_schema["properties"]["result"]["oneOf"] == [
        {"$ref": "#/components/schemas/MetadataDesignResult"},
        {"type": "null"},
    ]
    forbidden_response_fields = {
        "rowData",
        "row_data",
        "rawPrompt",
        "rawProviderResponse",
        "providerTrace",
        "apply",
        "execute",
        "deploy",
        "publish",
        "artifactId",
    }
    assert forbidden_response_fields.isdisjoint(result_properties)


def test_openapi_sp_analysis_async_progress_contract() -> None:
    openapi = yaml.safe_load(
        (ROOT / "spec" / "openapi" / "ai_agent_platform_openapi_v1.yaml").read_text(
            encoding="utf-8"
        )
    )
    operation = openapi["paths"]["/api/v1/requests/sp-analysis"]["post"]
    job_schema = openapi["components"]["schemas"]["Job"]

    run_async = next(
        parameter for parameter in operation["parameters"] if parameter["name"] == "runAsync"
    )

    assert run_async["in"] == "query"
    assert run_async["schema"] == {"type": "boolean", "default": False}
    assert "returns after job creation" in run_async["description"]
    progress_description = job_schema["properties"]["progress"]["description"].lower()
    assert "estimated status-based progress" in progress_description
    assert "not exact work completion" in progress_description


def test_openapi_sp_batch_contract_matches_p33_scale_surface() -> None:
    openapi = yaml.safe_load(
        (ROOT / "spec" / "openapi" / "ai_agent_platform_openapi_v1.yaml").read_text(
            encoding="utf-8"
        )
    )
    operation = openapi["paths"]["/api/v1/requests/sp-analysis/batch"]["post"]
    schemas = openapi["components"]["schemas"]

    assert operation["operationId"] == "createStoredProcedureAnalysisBatch"
    assert operation["requestBody"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/SPAnalysisBatchRequest"
    }
    assert operation["responses"]["202"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/SPAnalysisBatchResponse"
    }
    assert operation["responses"]["429"] == {"$ref": "#/components/responses/Backpressure"}
    assert schemas["SPAnalysisBatchRequest"]["required"] == [
        "dbProfileId",
        "targets",
        "outputs",
    ]
    response_properties = schemas["SPAnalysisBatchResponse"]["properties"]
    assert set(response_properties) == {"batchId", "status", "accepted", "rejected", "limits"}
    rejected_codes = schemas["SPAnalysisBatchRejectedItem"]["properties"]["code"]["enum"]
    assert "DUPLICATE_TARGET_SKIPPED" in rejected_codes
    assert "BATCH_TARGET_LIMIT_EXCEEDED" in rejected_codes


def test_openapi_knowledge_assetization_contract_matches_p35_surface() -> None:
    openapi = yaml.safe_load(
        (ROOT / "spec" / "openapi" / "ai_agent_platform_openapi_v1.yaml").read_text(
            encoding="utf-8"
        )
    )
    paths = openapi["paths"]
    schemas = openapi["components"]["schemas"]

    assert paths["/api/v1/jobs/{jobId}/knowledge-assets"]["get"]["operationId"] == (
        "listJobKnowledgeAssets"
    )
    assert paths["/api/v1/knowledge/assets/{assetId}"]["get"]["operationId"] == (
        "getKnowledgeAsset"
    )
    assert paths["/api/v1/knowledge/exports"]["post"]["operationId"] == (
        "createKnowledgeExport"
    )
    assert paths["/api/v1/knowledge/assets"]["get"]["operationId"] == (
        "listKnowledgeAssets"
    )
    assert paths["/api/v1/knowledge/facts/search"]["get"]["operationId"] == (
        "searchKnowledgeFacts"
    )
    assert "/api/v1/knowledge/assets/{assetId}/versions/{versionId}/review" not in paths
    assert "/api/v1/knowledge/assets/{assetId}/reviews" not in paths
    assert schemas["SPAnalysisOptions"]["properties"]["persistKnowledge"]["default"] is True
    assert (
        schemas["SPAnalysisOptions"]["properties"]["usePlatformToolOrchestration"][
            "default"
        ]
        is True
    )
    assert schemas["MetadataAnalysisResponse"]["properties"]["knowledgeAssets"] == {
        "type": "array",
        "items": {"$ref": "#/components/schemas/KnowledgeAssetSummary"},
    }
    assert schemas["KnowledgeAssetKind"]["enum"] == [
        "SP_ANALYSIS",
        "DEPENDENCY_EVIDENCE",
        "METADATA_PROFILE",
        "DTO_READINESS",
        "CANONICAL_ANALYSIS",
    ]
    assert schemas["KnowledgeExportRequest"]["properties"]["format"]["enum"] == [
        "JSONL",
        "GRAPH_JSON",
    ]
    assert schemas["KnowledgeLifecycleStatus"]["enum"] == [
        "DRAFT",
        "REVIEW_REQUIRED",
        "ARCHIVED",
    ]
    assert "lifecycleStatus" in schemas["KnowledgeAssetSummary"]["properties"]
    assert "KnowledgeReviewRequest" not in schemas
    assert "KnowledgeReview" not in schemas
    assert "KnowledgeFactSearchResult" in schemas
    assert "one-to-one" in schemas["KnowledgeExportRequest"]["properties"]["versionIds"][
        "description"
    ]
    assert set(schemas["KnowledgeEdge"]["properties"]["edgeType"]["enum"]) == {
        "DEPENDS_ON",
        "DERIVED_FROM",
        "SUPPORTS",
        "READS",
        "WRITES",
        "CALLS",
        "FK_TO",
        "DTO_FIELD_OF",
    }


def test_v6_knowledge_asset_schema_has_job_links_and_fact_edge_integrity_without_reviews() -> None:
    ddl_text = (
        ROOT / "db" / "schema" / "ai_agent_platform_schema_v6_draft_quality_no_review.sql"
    ).read_text(encoding="utf-8")

    assert "CREATE TABLE dbo.KNOWLEDGE_ASSET_JOB_LINKS" in ddl_text
    assert "JOB_REF_ID NVARCHAR(80) NOT NULL" in ddl_text
    assert "PK_KNOWLEDGE_ASSET_JOB_LINKS" in ddl_text
    assert "FK_KNOWLEDGE_ASSET_JOB_LINKS_ASSET" in ddl_text
    assert "FK_KNOWLEDGE_ASSET_JOB_LINKS_VERSION" in ddl_text
    assert "FK_KNOWLEDGE_FACT_EDGES_FROM_FACT" in ddl_text
    assert "FK_KNOWLEDGE_FACT_EDGES_TO_FACT" in ddl_text
    assert "REFERENCES dbo.KNOWLEDGE_FACTS(ASST_VER_ID, FACT_ID)" in ddl_text
    assert "IX_KNOWLEDGE_ASSET_JOB_LINKS_JOB" in ddl_text
    assert "LIFECYCLE_STAT_CD NVARCHAR(30) NOT NULL DEFAULT 'DRAFT'" in ddl_text
    assert "LIFECYCLE_NOTE_JSON NVARCHAR(MAX) NOT NULL DEFAULT '{}'" in ddl_text
    assert "ARCHV_DTM DATETIME2(3) NULL" in ddl_text
    assert "CREATE TABLE dbo.KNOWLEDGE_ASSET_REVIEWS" not in ddl_text
    assert "REVIEWER_REF_TXT" not in ddl_text
    assert "REVIEWED" not in ddl_text
    assert "CHK_KNOWLEDGE_ASSET_VERSIONS_LIFECYCLE" in ddl_text
    assert "CHK_KNOWLEDGE_ASSET_REVIEWS_TO_STATUS" not in ddl_text
    assert "IX_KNOWLEDGE_ASSET_VERSIONS_LIFECYCLE" in ddl_text
    assert "IX_KNOWLEDGE_ASSET_REVIEWS_VERSION" not in ddl_text
    assert "IX_KNOWLEDGE_FACTS_SEARCH" in ddl_text


def test_platform_repository_checks_all_v6_knowledge_tables() -> None:
    source = (ROOT / "apps" / "api" / "api_app" / "platform_db.py").read_text(
        encoding="utf-8"
    )

    for table_name in (
        "KNOWLEDGE_ASSETS",
        "KNOWLEDGE_ASSET_VERSIONS",
        "KNOWLEDGE_FACTS",
        "KNOWLEDGE_FACT_EDGES",
        "KNOWLEDGE_ASSET_JOB_LINKS",
        "KNOWLEDGE_EXPORTS",
    ):
        assert table_name in source
    for schema_object in (
        "LIFECYCLE_STAT_CD",
        "LIFECYCLE_NOTE_JSON",
        "ARCHV_DTM",
        "IX_KNOWLEDGE_ASSET_VERSIONS_LIFECYCLE",
        "IX_KNOWLEDGE_FACTS_SEARCH",
    ):
        assert schema_object in source
    for removed_schema_object in (
        "KNOWLEDGE_ASSET_REVIEWS",
        "FROM_STAT_CD",
        "TO_STAT_CD",
        "IX_KNOWLEDGE_ASSET_REVIEWS_VERSION",
    ):
        assert removed_schema_object not in source
    assert "KNOWLEDGE_SCHEMA_REQUIRED" in source


def test_v7_metadata_analysis_run_schema_is_durable_and_draft_only() -> None:
    ddl_text = (
        ROOT / "db" / "schema" / "ai_agent_platform_schema_v7_metadata_analysis_runs.sql"
    ).read_text(encoding="utf-8")

    assert "Manual apply only" in ddl_text
    assert "CREATE TABLE dbo.METADATA_ANALYSIS_RUNS" in ddl_text
    assert "RUN_ID NVARCHAR(80) NOT NULL" in ddl_text
    assert "REQUEST_JSON NVARCHAR(MAX) NOT NULL" in ddl_text
    assert "ANALYSIS_JSON NVARCHAR(MAX) NULL" in ddl_text
    assert "ERR_JSON NVARCHAR(MAX) NULL" in ddl_text
    assert "STAT_CD IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED')" in ddl_text
    assert "IX_METADATA_ANALYSIS_RUNS_STATUS" in ddl_text
    assert "IX_METADATA_ANALYSIS_RUNS_SUBMITTED" in ddl_text
    for forbidden in (
        "APPROVAL_DECISIONS",
        "REVIEWER_REF_TXT",
        "ROW_DATA",
        "RAW_PROMPT",
        "RAW_PROVIDER",
    ):
        assert forbidden not in ddl_text.upper()


def test_v10_metadata_design_run_schema_is_manual_and_preview_only() -> None:
    ddl_text = (
        ROOT / "db" / "schema" / "ai_agent_platform_schema_v10_metadata_design_runs.sql"
    ).read_text(encoding="utf-8")
    upper = ddl_text.upper()

    assert "Manual apply only" in ddl_text
    assert "CREATE TABLE dbo.METADATA_DESIGN_RUNS" in ddl_text
    assert "CONVERSATION_ID NVARCHAR(80) NOT NULL" in ddl_text
    assert "REQUEST_JSON NVARCHAR(MAX) NOT NULL" in ddl_text
    assert "RESULT_JSON NVARCHAR(MAX) NULL" in ddl_text
    assert "ERR_JSON NVARCHAR(MAX) NULL" in ddl_text
    assert "STAT_CD IN ('QUEUED', 'RUNNING', 'SUCCEEDED', 'FAILED')" in ddl_text
    assert "ISJSON(REQUEST_JSON) = 1" in ddl_text
    assert "IX_METADATA_DESIGN_RUNS_STATUS" in ddl_text
    assert "IX_METADATA_DESIGN_RUNS_CONVERSATION" in ddl_text
    assert "IX_METADATA_DESIGN_RUNS_SUBMITTED" in ddl_text
    assert "non-executable" in ddl_text
    assert "workflow artifact" in ddl_text
    assert "DDL_DRAFT artifact" in ddl_text
    for forbidden in (
        "RAW_PROMPT",
        "RAW_PROVIDER",
        "ROW_DATA",
        "APPROVAL_DECISIONS",
        "EXECUTE_SQL",
        "APPLY_SQL",
        "PUBLISH_JOB",
        "DEPLOY_JOB",
    ):
        assert forbidden not in upper


def test_v8_canonical_target_key_schema_is_manual_and_no_review_surface() -> None:
    ddl_text = (
        ROOT
        / "db"
        / "schema"
        / "ai_agent_platform_schema_v8_canonical_target_keys_consolidated.sql"
    ).read_text(encoding="utf-8")
    upper = ddl_text.upper()

    assert "Manual apply only" in ddl_text
    assert "CANON_TRGT_KEY_TXT NVARCHAR(300) NULL" in ddl_text
    for table_name in (
        "CORE_WORK_REQUESTS",
        "CORE_JOBS",
        "AGENT_RUNS",
        "ARTIFACTS",
        "KNOWLEDGE_ASSETS",
    ):
        assert f"dbo.{table_name}" in ddl_text
    for index_name in (
        "IX_CORE_WORK_REQUESTS_CANON_TARGET_SUBMITTED",
        "IX_CORE_JOBS_CANON_TARGET_CREATED",
        "IX_AGENT_RUNS_JOB_CANON_TARGET",
        "IX_ARTIFACTS_JOB_CANON_TARGET",
        "IX_KNOWLEDGE_ASSETS_CANON_TARGET",
    ):
        assert index_name in ddl_text
    for forbidden in (
        "CREATE TABLE DBO.APPROVAL",
        "CREATE TABLE DBO.KNOWLEDGE_ASSET_REVIEWS",
        "PUBLISH_JOB",
        "DEPLOY_JOB",
        "EXECUTE_SQL",
        "ROW_DATA",
        "RAW_PROMPT",
    ):
        assert forbidden not in upper


def test_v11_plf_full_create_schema_consolidates_current_manual_drafts() -> None:
    ddl_text = (
        ROOT / "db" / "schema" / "ai_agent_platform_schema_v11_plf_full_create.sql"
    ).read_text(encoding="utf-8")
    upper = ddl_text.upper()

    assert "Manual apply only" in ddl_text
    assert "new, empty PLF database" in ddl_text
    assert "v2, v3, v4, v6, v7, v8, v9, and v10" in ddl_text
    for table_name in (
        "AUTH_USERS",
        "CORE_DB_PROFILES",
        "CORE_WORK_REQUESTS",
        "CORE_JOBS",
        "ARTIFACTS",
        "AGENT_RUNS",
        "MODEL_INVOCATIONS",
        "KNOWLEDGE_ASSETS",
        "KNOWLEDGE_ASSET_VERSIONS",
        "KNOWLEDGE_FACTS",
        "KNOWLEDGE_FACT_EDGES",
        "KNOWLEDGE_ASSET_JOB_LINKS",
        "KNOWLEDGE_EXPORTS",
        "METADATA_ANALYSIS_RUNS",
        "METADATA_DESIGN_RUNS",
    ):
        assert f"CREATE TABLE dbo.{table_name}" in ddl_text

    assert "CANON_TRGT_KEY_TXT NVARCHAR(300) NULL" in ddl_text
    assert "VALIDATION_COMPLETE" in ddl_text
    assert "TRG_ARTIFACTS_BLOCK_P36_RETIRED_TYPES" in ddl_text
    assert "LIFECYCLE_STAT_CD NVARCHAR(30) NOT NULL DEFAULT 'DRAFT'" in ddl_text
    assert "IX_KNOWLEDGE_FACTS_SEARCH" in ddl_text
    assert "IX_METADATA_ANALYSIS_RUNS_STATUS" in ddl_text
    assert "IX_METADATA_DESIGN_RUNS_CONVERSATION" in ddl_text
    artifact_storage_values = _ddl_check_values(ddl_text, "CHK_ARTIFACTS_TYPE_CD")
    assert set(_enum_values(ArtifactType)) <= set(artifact_storage_values)
    assert {"VO_DRAFT", "MODEL_DRAFT", "DDL_DRAFT"} <= set(artifact_storage_values)
    for forbidden in (
        "CREATE DATABASE",
        "DROP TABLE",
        "DTO_MODEL_DRAFT",
        "KNOWLEDGE_ASSET_REVIEWS",
        "PUBLISH_JOB",
        "DEPLOY_JOB",
        "EXECUTE_SQL",
        "ROW_DATA",
        "RAW_PROMPT",
        "RAW_PROVIDER",
    ):
        assert forbidden not in upper


def test_v11_required_seed_has_only_required_bootstrap_data_without_secret_values() -> None:
    seed_text = (
        ROOT / "db" / "schema" / "ai_agent_platform_seed_required_v11.sql"
    ).read_text(encoding="utf-8")
    upper = seed_text.upper()

    assert "Manual apply only" in seed_text
    assert "MERGE dbo.AUTH_ROLES" in seed_text
    assert "MERGE dbo.AUTH_USERS" in seed_text
    assert "MERGE dbo.CORE_DB_PROFILES" in seed_text
    assert "MERGE dbo.CORE_DB_PROFILE_ALLOWED_SCHEMAS" in seed_text
    for required_value in (
        "codex-api-local",
        "USER",
        "ADMIN",
        "AUDITOR",
        "plf",
        "master",
        "ppm",
        "REVIEW_REQUIRED_PLF_HOST",
        "REVIEW_REQUIRED_METADATA_HOST",
    ):
        assert required_value in seed_text
    assert "REVIEWER" not in upper
    for forbidden in (
        "PASSWORD",
        "TOKEN",
        "API_KEY",
        "OPENAI_API_KEY",
        "PLATFORM_DB_PASSWORD",
        "MSSQL_METADATA_PASSWORD",
        "CONNECTION STRING",
    ):
        assert forbidden not in upper


def test_schema_docs_reference_v11_plf_bootstrap_without_stale_paths() -> None:
    docs_text = "\n".join(
        [
            (ROOT / "db" / "schema" / "README.md").read_text(encoding="utf-8"),
            (ROOT / "apps" / "api" / "README.md").read_text(encoding="utf-8"),
            *[
                path.read_text(encoding="utf-8")
                for path in (ROOT / "docs").glob("*.md")
            ],
        ]
    )

    assert "ai_agent_platform_schema_v11_plf_full_create.sql" in docs_text
    assert "ai_agent_platform_seed_required_v11.sql" in docs_text
    for stale_path in (
        "ai_agent_platform_schema_v2.sql",
        "ai_agent_platform_schema_v3_agent_runs.sql",
        "ai_agent_platform_schema_v4_knowledge_assets.sql",
    ):
        assert stale_path not in docs_text


def test_platform_repository_checks_v7_metadata_analysis_run_schema() -> None:
    source = (ROOT / "apps" / "api" / "api_app" / "platform_db.py").read_text(
        encoding="utf-8"
    )

    for schema_object in (
        "METADATA_ANALYSIS_RUNS",
        "RUN_ID",
        "STAT_CD",
        "REQUEST_JSON",
        "ANALYSIS_JSON",
        "ERR_JSON",
        "IX_METADATA_ANALYSIS_RUNS_STATUS",
        "IX_METADATA_ANALYSIS_RUNS_SUBMITTED",
        "METADATA_ANALYSIS_RUN_SCHEMA_REQUIRED",
    ):
        assert schema_object in source


def test_platform_repository_checks_v10_metadata_design_run_schema() -> None:
    source = (ROOT / "apps" / "api" / "api_app" / "platform_db.py").read_text(
        encoding="utf-8"
    )

    for schema_object in (
        "METADATA_DESIGN_RUNS",
        "CONVERSATION_ID",
        "REQUEST_JSON",
        "RESULT_JSON",
        "ERR_JSON",
        "IX_METADATA_DESIGN_RUNS_STATUS",
        "IX_METADATA_DESIGN_RUNS_CONVERSATION",
        "IX_METADATA_DESIGN_RUNS_SUBMITTED",
        "METADATA_DESIGN_RUN_SCHEMA_REQUIRED",
    ):
        assert schema_object in source


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
    output_renewal_ddl = (
        ROOT / "db" / "schema" / "ai_agent_platform_schema_v9_output_renewal_artifact_types.sql"
    ).read_text(encoding="utf-8")
    validation_complete_ddl = (
        ROOT / "db" / "schema" / "ai_agent_platform_schema_v4_validation_complete_status.sql"
    ).read_text(encoding="utf-8")

    active_job_statuses = [
        "SUBMITTED",
        "COLLECTING_METADATA",
        "ANALYZING",
        "GENERATING",
        "VALIDATING",
        "VALIDATION_COMPLETE",
        "FAILED",
        "CANCELED",
    ]
    active_workflow_steps = ["COLLECT_METADATA", "ANALYZE", "GENERATE", "VALIDATE"]
    active_artifact_types = [
        value for value in _enum_values(ArtifactType) if value != "APPROVAL_LOG"
    ]
    active_artifact_statuses = ["DRAFT", "VALIDATED", "ARCHIVED"]

    assert schemas["JobStatus"]["enum"] == active_job_statuses
    assert set(active_job_statuses) <= set(_enum_values(JobStatus))
    assert schemas["WorkflowStepType"]["enum"] == active_workflow_steps
    assert set(active_workflow_steps) <= set(_enum_values(WorkflowStepType))
    assert schemas["ArtifactType"]["enum"] == active_artifact_types
    assert set(active_artifact_types) <= set(_enum_values(ArtifactType))
    assert schemas["ArtifactStatus"]["enum"] == active_artifact_statuses
    assert set(active_artifact_statuses) <= set(_enum_values(ArtifactStatus))
    assert schemas["RequestedOutputType"]["enum"] == _enum_values(RequestedOutputType)
    p29b_deferred_dependency_storage_names = {
        "DEPENDENCY_EVIDENCE",
        "DEPENDENCY_CLOSURE",
        "DEPENDENCY_EVIDENCE_DIGEST",
    }
    assert p29b_deferred_dependency_storage_names.isdisjoint(
        set(schemas["ArtifactType"]["enum"])
    )
    assert p29b_deferred_dependency_storage_names.isdisjoint(
        set(schemas["RequestedOutputType"]["enum"])
    )

    assert _enum_values(JobStatus) == _ddl_check_values(
        validation_complete_ddl, "CHK_CORE_JOBS_CURRENT_STATUS_CD"
    )
    artifact_storage_values = _ddl_check_values(
        output_renewal_ddl, "CHK_ARTIFACTS_TYPE_CD"
    )
    assert set(_enum_values(ArtifactType)) <= set(artifact_storage_values)
    assert {"VO_DRAFT", "MODEL_DRAFT", "DDL_DRAFT"} <= set(artifact_storage_values)
    assert "TRG_ARTIFACTS_BLOCK_P36_RETIRED_TYPES" in output_renewal_ddl
    assert "historical-only" in output_renewal_ddl
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

    known_artifacts = set(_enum_values(ArtifactType)) | set(_enum_values(RequestedOutputType))
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
    assert "P42_LIVE_REPLAY_GATE=0" in text
    assert "MCP_TOOL_RESULT_CACHE_ENABLED=1" in text
    assert "MCP_TOOL_RESULT_CACHE_TTL_SECONDS=300" in text
    assert "MCP_TOOL_RESULT_CACHE_MAX_ENTRIES=1024" in text
    assert "WORKFLOW_MAX_ACTIVE_JOBS=4" in text
    assert "MSSQL_METADATA_MAX_CONCURRENCY=4" in text
    assert "BACKPRESSURE_WAIT_MS=250" in text
    assert "SP_BATCH_MAX_TARGETS=20" in text
    assert "SP_BATCH_MAX_CONCURRENT_JOBS=2" in text
    assert "LLM_SEMANTIC_INPUT_TOKEN_BUDGET=64000" in text
    assert "LLM_SEMANTIC_SOURCE_TOKEN_BUDGET=32000" in text
    assert "LLM_SP_MAX_RETRIEVED_SPANS=24" in text
    assert "LLM_SP_DEPENDENCY_DEPTH=2" in text
    assert "LLM_SP_MAX_DEPENDENCY_TASKS=8" in text
    assert "AI_TOOL_MAX_CALLS=5" in text
    assert "AI_TOOL_MAX_ROUNDS=2" in text
    assert "AI_TOOL_LIVE_MAX_ROUNDS=1" in text
    assert "PLATFORM_TOOL_MAX_CALLS=3" in text
    assert "KNOWLEDGE_ASSETIZATION_ENABLED=1" in text
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
