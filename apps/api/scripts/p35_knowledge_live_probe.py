#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

import yaml

API_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]
MCP_ROOT = REPO_ROOT / "services" / "mssql-mcp"
for import_root in (API_ROOT, MCP_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from api_app.auth import (  # noqa: E402
    ARTIFACT_REVIEW_ROLES,
    AuthConfigurationError,
    AuthenticationRequiredError,
    OidcJwtVerifier,
    load_auth_settings,
)
from api_app.dependencies import reset_application_state  # noqa: E402
from api_app.main import app  # noqa: E402
from api_app.platform_db import (  # noqa: E402
    MssqlPlatformRepository,
    PlatformPersistenceError,
    load_platform_db_settings,
)
from fastapi.testclient import TestClient  # noqa: E402
from mssql_mcp_app.profiles import load_db_profiles  # noqa: E402
from mssql_mcp_app.settings import load_live_metadata_settings  # noqa: E402

LIVE_GATE_ENV = "P35_KNOWLEDGE_LIVE_GATE"
LIVE_BLOCKER = "P35_KNOWLEDGE_LIVE_REQUIRED"
SCHEMA_BLOCKER = "P35_KNOWLEDGE_SCHEMA_REQUIRED"
PILOT_MANIFEST = REPO_ROOT / "fixtures" / "pilot" / "ppm_object_selection_v1" / "selected_objects.yaml"
EXPECTED_ASSET_KINDS = {
    "SP_ANALYSIS",
    "DEPENDENCY_EVIDENCE",
    "METADATA_PROFILE",
    "DTO_READINESS",
    "CANONICAL_ANALYSIS",
}
REQUIRED_ENV = (
    "P35_KNOWLEDGE_LIVE_GATE",
    "PLATFORM_DB_HOST",
    "PLATFORM_DB_PORT",
    "PLATFORM_DB_USER",
    "PLATFORM_DB_PASSWORD",
    "PLATFORM_DB_NAME",
    "MSSQL_ENABLE_LIVE_METADATA",
    "MSSQL_METADATA_HOST",
    "MSSQL_METADATA_PORT",
    "MSSQL_METADATA_USER",
    "MSSQL_METADATA_PASSWORD",
    "MSSQL_METADATA_PROFILE_FILE",
    "LLM_LIVE_GATE",
    "LLM_ENABLE_REMOTE",
    "LLM_ALLOW_SP_TEXT",
    "OPENAI_API_KEY",
)
AUTH_REVIEW_ENV = (
    "OIDC_ISSUER",
    "OIDC_AUDIENCE",
    "OIDC_JWKS_URL",
    "OIDC_REVIEWER_BEARER_TOKEN",
)
REDACTION = {
    "tokens": "not_returned",
    "rawJwtClaims": "not_returned",
    "plfRows": "not_returned",
    "ppmRows": "not_returned",
    "connectionStrings": "not_returned",
    "rawPrompts": "not_returned",
    "rawProviderResponses": "not_returned",
}
FORBIDDEN_FRAGMENTS = (
    "CREATE PROCEDURE",
    "CREATE OR ALTER PROCEDURE",
    "CREATE FUNCTION",
    "CREATE VIEW",
    "rowData",
    "row_data",
    "sampleRows",
    "sampleData",
    "procedureExecution",
    "definitionText",
    "sqlText",
    "raw_prompt",
    "rawPrompt",
    "raw_sp_definition",
    "rawProviderResponse",
    "raw_openai_response_text",
    "connectionString",
)


def run_probe(*, load_dotenv: bool = True) -> dict[str, Any]:
    if load_dotenv:
        load_root_dotenv()

    if not _flag_enabled(LIVE_GATE_ENV):
        return _result(
            status="skipped",
            blocker_code=None,
            summary=(
                "P35_KNOWLEDGE_LIVE_GATE is not enabled; default eval did not access "
                "PLF, live PPM metadata, or OpenAI."
            ),
            checks=[],
        )

    missing = _missing_required_env()
    if missing:
        return _result(
            status="failed",
            blocker_code=LIVE_BLOCKER,
            summary="P35 knowledge live gate is enabled but required env names are missing.",
            checks=[
                _check(
                    "required_env",
                    "fail",
                    blocker_code=LIVE_BLOCKER,
                    summary="Missing env name(s): " + ", ".join(missing),
                )
            ],
        )

    try:
        manifest = _pilot_manifest()
        _require_live_manifest_and_profile(manifest)
        reviewer = _reviewer_context()
        reset_application_state()
        client = TestClient(app)
        schema_result = _preflight_knowledge_schema(client)
        target = _selected_live_procedure(manifest)
        workflow = _submit_live_workflow(client, target)
        agent_run = _verify_agent_run(client, workflow["jobId"])
        knowledge = _verify_job_knowledge(client, workflow["jobId"], target)
        graph = _verify_fact_graph(client, knowledge["dependencyAsset"])
        search = _verify_search(client, target, knowledge["spAsset"])
        export = _verify_export(client, knowledge["dependencyAsset"])
        review = _review_real_ppm_asset(client, knowledge["spAsset"], reviewer)
        for payload, check_name in (
            (workflow, "workflow_submit"),
            (agent_run, "openai_agent_run"),
            (knowledge, "knowledge_assets"),
            (graph, "fact_graph"),
            (search, "knowledge_search"),
            (export, "knowledge_export"),
            (review, "knowledge_review"),
        ):
            _assert_safe_payload(payload, check_name)
    except ProbeFailure as exc:
        return _result(
            status="failed",
            blocker_code=exc.blocker_code,
            summary=exc.summary,
            checks=exc.checks,
        )

    return _result(
        status="passed",
        blocker_code=None,
        summary=(
            "P35 live knowledge confidence gate passed with live PPM metadata, "
            "OpenAI semantic analysis, PLF v5 knowledge persistence, search/export, "
            "and one non-terminal REVIEWED curation event."
        ),
        checks=[
            _check("v5_schema_readiness", "pass", summary=schema_result["summary"]),
            _check("workflow_submit", "pass", summary=workflow["summary"]),
            _check("openai_agent_run", "pass", summary=agent_run["summary"]),
            _check("knowledge_assets", "pass", summary=knowledge["summary"]),
            _check("fact_graph", "pass", summary=graph["summary"]),
            _check("knowledge_search", "pass", summary=search["summary"]),
            _check("knowledge_export", "pass", summary=export["summary"]),
            _check("knowledge_review", "pass", summary=review["summary"]),
        ],
    )


def _preflight_knowledge_schema(client: TestClient) -> dict[str, str]:
    response = client.get("/api/v1/knowledge/assets", params={"limit": "1"})
    if response.status_code != 200:
        raise ProbeFailure.from_response(
            response,
            fallback_blocker=SCHEMA_BLOCKER,
            check_name="v5_schema_readiness",
        )
    return {"summary": "PLF v5 knowledge schema readiness check returned a safe response."}


def _submit_live_workflow(client: TestClient, target: dict[str, str]) -> dict[str, Any]:
    response = client.post(
        "/api/v1/requests/sp-analysis",
        headers={"X-Correlation-ID": "corr-p35-live-knowledge"},
        json={
            "dbProfileId": "ppm",
            "target": target,
            "outputs": ["SP_ANALYSIS_DOCUMENT", "DEPENDENCY_REPORT"],
            "options": {
                "includeEvidenceRefs": True,
                "useLlmAnalysis": True,
                "llmProfileId": "openai_sp_semantic_analysis",
                "allowSpDefinitionToModel": True,
                "useAiToolOrchestration": True,
                "persistKnowledge": True,
            },
        },
    )
    if response.status_code != 202:
        raise ProbeFailure.from_response(
            response,
            fallback_blocker=LIVE_BLOCKER,
            check_name="workflow_submit",
        )
    payload = response.json()
    job_id = str(payload.get("jobId") or "")
    if payload.get("status") == "FAILED":
        job_response = client.get(f"/api/v1/jobs/{job_id}")
        job_payload = job_response.json() if job_response.status_code == 200 else {}
        blockers = job_payload.get("blockers") or []
        code = str(blockers[0].get("code") if blockers else LIVE_BLOCKER)
        raise ProbeFailure(
            blocker_code=code,
            summary=str(job_payload.get("failureReason") or "P35 live workflow failed."),
            checks=[
                _check(
                    "workflow_submit",
                    "fail",
                    blocker_code=code,
                    summary="Workflow job entered FAILED state.",
                )
            ],
        )
    if payload.get("status") != "VALIDATION_COMPLETE":
        raise ProbeFailure(
            blocker_code="P35_LIVE_WORKFLOW_STATUS_MISMATCH",
            summary=f"Unexpected live workflow status: {payload.get('status')}",
            checks=[
                _check(
                    "workflow_submit",
                    "fail",
                    blocker_code="P35_LIVE_WORKFLOW_STATUS_MISMATCH",
                    summary="Workflow did not stop at VALIDATION_COMPLETE.",
                )
            ],
        )
    return {
        "requestId": payload.get("requestId"),
        "jobId": job_id,
        "target": target,
        "summary": "Live PPM SP workflow reached VALIDATION_COMPLETE and persisted PLF records.",
    }


def _verify_agent_run(client: TestClient, job_id: str) -> dict[str, Any]:
    response = client.get(f"/api/v1/jobs/{job_id}/agent-runs")
    if response.status_code != 200:
        raise ProbeFailure.from_response(
            response,
            fallback_blocker=LIVE_BLOCKER,
            check_name="openai_agent_run",
        )
    runs = response.json().get("agentRuns") or []
    _assert_safe_payload({"agentRuns": runs}, "openai_agent_run")
    if not runs:
        raise ProbeFailure(
            blocker_code="P35_LIVE_OPENAI_RUN_MISSING",
            summary="Live workflow did not persist an agent run.",
            checks=[
                _check(
                    "openai_agent_run",
                    "fail",
                    blocker_code="P35_LIVE_OPENAI_RUN_MISSING",
                    summary="No raw provider response was inspected.",
                )
            ],
        )
    run = runs[0]
    invocation = dict(run.get("modelInvocation") or {})
    if invocation.get("status") != "SUCCEEDED":
        raise ProbeFailure(
            blocker_code="P35_LIVE_OPENAI_RUN_FAILED",
            summary="Live OpenAI semantic analysis did not succeed.",
            checks=[
                _check(
                    "openai_agent_run",
                    "fail",
                    blocker_code="P35_LIVE_OPENAI_RUN_FAILED",
                    summary="Model invocation status was not SUCCEEDED.",
                )
            ],
        )
    expected_provider = _expected_remote_provider()
    if invocation.get("provider") != expected_provider:
        raise ProbeFailure(
            blocker_code="P35_LIVE_OPENAI_PROVIDER_MISMATCH",
            summary="Model invocation did not use the configured remote provider.",
            checks=[
                _check(
                    "openai_agent_run",
                    "fail",
                    blocker_code="P35_LIVE_OPENAI_PROVIDER_MISMATCH",
                    summary=f"Expected provider {expected_provider}.",
                )
            ],
        )
    return {
        "agentRunId": run.get("agentRunId"),
        "provider": invocation.get("provider"),
        "model": invocation.get("model"),
        "summary": "Remote model invocation succeeded and stored only sanitized trace metadata.",
    }


def _verify_job_knowledge(
    client: TestClient,
    job_id: str,
    target: dict[str, str],
) -> dict[str, Any]:
    response = client.get(f"/api/v1/jobs/{job_id}/knowledge-assets")
    if response.status_code != 200:
        raise ProbeFailure.from_response(
            response,
            fallback_blocker=SCHEMA_BLOCKER,
            check_name="knowledge_assets",
        )
    assets = response.json().get("knowledgeAssets") or []
    _assert_safe_payload({"knowledgeAssets": assets}, "knowledge_assets")
    by_kind = {asset.get("assetKind"): asset for asset in assets}
    missing = sorted(EXPECTED_ASSET_KINDS.difference(by_kind))
    if missing:
        raise ProbeFailure(
            blocker_code="P35_LIVE_KNOWLEDGE_ASSETS_MISSING",
            summary="Live workflow did not expose every expected job-linked knowledge asset.",
            checks=[
                _check(
                    "knowledge_assets",
                    "fail",
                    blocker_code="P35_LIVE_KNOWLEDGE_ASSETS_MISSING",
                    summary="Missing asset kind(s): " + ", ".join(missing),
                )
            ],
        )
    for asset in assets:
        if asset.get("dbProfileId") != "ppm" or asset.get("targetName") != target["name"]:
            raise ProbeFailure(
                blocker_code="P35_LIVE_KNOWLEDGE_TARGET_MISMATCH",
                summary="Live knowledge asset target binding did not match selected PPM target.",
                checks=[
                    _check(
                        "knowledge_assets",
                        "fail",
                        blocker_code="P35_LIVE_KNOWLEDGE_TARGET_MISMATCH",
                        summary="Job-linked asset returned an unexpected target binding.",
                    )
                ],
            )
    return {
        "assets": assets,
        "spAsset": by_kind["SP_ANALYSIS"],
        "dependencyAsset": by_kind["DEPENDENCY_EVIDENCE"],
        "summary": "Job-linked knowledge asset lookup returned every P34/P35 asset kind.",
    }


def _verify_fact_graph(client: TestClient, asset: dict[str, Any]) -> dict[str, Any]:
    asset_id = str(asset.get("assetId") or "")
    version_id = str(asset.get("currentVersionId") or "")
    response = client.get(f"/api/v1/knowledge/assets/{asset_id}/versions/{version_id}/facts")
    if response.status_code != 200:
        raise ProbeFailure.from_response(
            response,
            fallback_blocker=SCHEMA_BLOCKER,
            check_name="fact_graph",
        )
    payload = response.json()
    _assert_safe_payload(payload, "fact_graph")
    facts = payload.get("facts") or []
    edges = payload.get("edges") or []
    if not facts:
        raise ProbeFailure(
            blocker_code="P35_LIVE_FACT_GRAPH_EMPTY",
            summary="Live dependency knowledge graph returned no facts.",
            checks=[
                _check(
                    "fact_graph",
                    "fail",
                    blocker_code="P35_LIVE_FACT_GRAPH_EMPTY",
                    summary="Fact graph must include persisted fact ids.",
                )
            ],
        )
    fact_ids = {str(fact.get("factId") or "") for fact in facts}
    dangling = [
        edge
        for edge in edges
        if str(edge.get("fromFactId") or "") not in fact_ids
        or str(edge.get("toFactId") or "") not in fact_ids
    ]
    if dangling:
        raise ProbeFailure(
            blocker_code="P35_LIVE_FACT_EDGE_INTEGRITY_FAILED",
            summary="Live dependency knowledge graph contained dangling fact edges.",
            checks=[
                _check(
                    "fact_graph",
                    "fail",
                    blocker_code="P35_LIVE_FACT_EDGE_INTEGRITY_FAILED",
                    summary="Every edge must point to a fact in the same persisted version.",
                )
            ],
        )
    return {
        "factCount": len(facts),
        "edgeCount": len(edges),
        "summary": "Fact graph edges reference persisted fact ids in the same version.",
    }


def _verify_search(
    client: TestClient,
    target: dict[str, str],
    sp_asset: dict[str, Any],
) -> dict[str, Any]:
    asset_response = client.get(
        "/api/v1/knowledge/assets",
        params={
            "assetKind": "SP_ANALYSIS",
            "dbProfileId": "ppm",
            "targetName": target["name"],
            "limit": "10",
        },
    )
    if asset_response.status_code != 200:
        raise ProbeFailure.from_response(
            asset_response,
            fallback_blocker=SCHEMA_BLOCKER,
            check_name="knowledge_asset_search",
        )
    asset_ids = {asset.get("assetId") for asset in asset_response.json().get("assets") or []}
    _assert_safe_payload(asset_response.json(), "knowledge_asset_search")
    if sp_asset.get("assetId") not in asset_ids:
        raise ProbeFailure(
            blocker_code="P35_LIVE_ASSET_SEARCH_MISS",
            summary="Live asset search did not return the job-linked SP knowledge asset.",
            checks=[
                _check(
                    "knowledge_asset_search",
                    "fail",
                    blocker_code="P35_LIVE_ASSET_SEARCH_MISS",
                    summary="Search filters did not find the expected asset id.",
                )
            ],
        )
    fact_response = client.get(
        "/api/v1/knowledge/facts/search",
        params={"targetName": target["name"], "limit": "20"},
    )
    if fact_response.status_code != 200:
        raise ProbeFailure.from_response(
            fact_response,
            fallback_blocker=SCHEMA_BLOCKER,
            check_name="knowledge_fact_search",
        )
    facts = fact_response.json().get("facts") or []
    _assert_safe_payload({"facts": facts}, "knowledge_fact_search")
    if not facts:
        raise ProbeFailure(
            blocker_code="P35_LIVE_FACT_SEARCH_EMPTY",
            summary="Live fact search returned no cross-asset facts for the selected target.",
            checks=[
                _check(
                    "knowledge_fact_search",
                    "fail",
                    blocker_code="P35_LIVE_FACT_SEARCH_EMPTY",
                    summary="Fact search must find at least one persisted fact.",
                )
            ],
        )
    if any(item.get("lifecycleStatus") == "ARCHIVED" for item in facts):
        raise ProbeFailure(
            blocker_code="P35_LIVE_FACT_SEARCH_ARCHIVED_DEFAULT",
            summary="Default live fact search included archived knowledge.",
            checks=[
                _check(
                    "knowledge_fact_search",
                    "fail",
                    blocker_code="P35_LIVE_FACT_SEARCH_ARCHIVED_DEFAULT",
                    summary="Archived versions require an explicit lifecycleStatus filter.",
                )
            ],
        )
    return {
        "assetSearchCount": len(asset_ids),
        "factSearchCount": len(facts),
        "summary": "Asset and fact search returned live PPM knowledge while excluding archived versions by default.",
    }


def _verify_export(client: TestClient, asset: dict[str, Any]) -> dict[str, Any]:
    response = client.post(
        "/api/v1/knowledge/exports",
        json={"assetIds": [asset["assetId"]], "format": "GRAPH_JSON"},
    )
    if response.status_code != 200:
        raise ProbeFailure.from_response(
            response,
            fallback_blocker=SCHEMA_BLOCKER,
            check_name="knowledge_export",
        )
    payload = response.json()
    _assert_safe_payload(payload, "knowledge_export")
    content = str(payload.get("content") or "")
    try:
        graph = json.loads(content)
    except json.JSONDecodeError as exc:
        raise ProbeFailure(
            blocker_code="P35_LIVE_EXPORT_INVALID_JSON",
            summary="Knowledge GRAPH_JSON export was not valid JSON.",
            checks=[
                _check(
                    "knowledge_export",
                    "fail",
                    blocker_code="P35_LIVE_EXPORT_INVALID_JSON",
                    summary=str(exc),
                )
            ],
        ) from exc
    nodes = graph.get("nodes") if isinstance(graph, dict) else None
    if not isinstance(nodes, list) or not nodes:
        raise ProbeFailure(
            blocker_code="P35_LIVE_EXPORT_EMPTY",
            summary="Knowledge GRAPH_JSON export did not contain fact nodes.",
            checks=[
                _check(
                    "knowledge_export",
                    "fail",
                    blocker_code="P35_LIVE_EXPORT_EMPTY",
                    summary="Export must include sanitized graph nodes.",
                )
            ],
        )
    return {
        "exportId": payload.get("exportId"),
        "contentHash": payload.get("contentHash"),
        "summary": "GRAPH_JSON export returned sanitized graph content and persisted an export record.",
    }


def _review_real_ppm_asset(
    client: TestClient,
    asset: dict[str, Any],
    reviewer: dict[str, Any],
) -> dict[str, Any]:
    asset_id = str(asset.get("assetId") or "")
    version_id = str(asset.get("currentVersionId") or "")
    response = client.post(
        f"/api/v1/knowledge/assets/{asset_id}/versions/{version_id}/review",
        headers=reviewer["headers"],
        json={
            "status": "REVIEWED",
            "reasonCode": "P35_LIVE_CONFIDENCE_REVIEW",
            "reviewer": reviewer["reviewer"],
            "comment": "P35 live confidence review of sanitized knowledge.",
        },
    )
    if response.status_code != 200:
        raise ProbeFailure.from_response(
            response,
            fallback_blocker=SCHEMA_BLOCKER,
            check_name="knowledge_review",
        )
    payload = response.json()
    _assert_safe_payload(payload, "knowledge_review")
    if payload.get("toStatus") != "REVIEWED":
        raise ProbeFailure(
            blocker_code="P35_LIVE_REVIEW_STATUS_MISMATCH",
            summary="Knowledge review transition did not record REVIEWED.",
            checks=[
                _check(
                    "knowledge_review",
                    "fail",
                    blocker_code="P35_LIVE_REVIEW_STATUS_MISMATCH",
                    summary="Expected a non-terminal REVIEWED curation event.",
                )
            ],
        )
    history = client.get(
        f"/api/v1/knowledge/assets/{asset_id}/reviews",
        params={"versionId": version_id},
    )
    if history.status_code != 200:
        raise ProbeFailure.from_response(
            history,
            fallback_blocker=SCHEMA_BLOCKER,
            check_name="knowledge_review_history",
        )
    reviews = history.json().get("reviews") or []
    _assert_safe_payload({"reviews": reviews}, "knowledge_review_history")
    if not any(item.get("reasonCode") == "P35_LIVE_CONFIDENCE_REVIEW" for item in reviews):
        raise ProbeFailure(
            blocker_code="P35_LIVE_REVIEW_HISTORY_MISSING",
            summary="Knowledge review history did not include the live review event.",
            checks=[
                _check(
                    "knowledge_review_history",
                    "fail",
                    blocker_code="P35_LIVE_REVIEW_HISTORY_MISSING",
                    summary="Append-only review history must expose the live curation event.",
                )
            ],
        )
    return {
        "reviewId": payload.get("reviewId"),
        "reviewer": payload.get("reviewer"),
        "summary": "A real PPM knowledge version recorded one non-terminal REVIEWED event.",
    }


def _reviewer_context() -> dict[str, Any]:
    if os.getenv("AUTH_RBAC_ENFORCEMENT", "").strip() != "1":
        return {"headers": {}, "reviewer": "p35-live-reviewer@example.com"}
    token = os.getenv("OIDC_REVIEWER_BEARER_TOKEN", "").strip()
    try:
        identity = OidcJwtVerifier(load_auth_settings()).verify(token)
        actor = MssqlPlatformRepository(load_platform_db_settings()).resolve_actor_roles(identity)
    except AuthConfigurationError as exc:
        raise ProbeFailure(
            blocker_code="P35_LIVE_AUTH_CONFIGURATION_INVALID",
            summary="Live auth/RBAC reviewer configuration is invalid.",
            checks=[
                _check(
                    "reviewer_auth",
                    "fail",
                    blocker_code="P35_LIVE_AUTH_CONFIGURATION_INVALID",
                    summary=str(exc),
                )
            ],
        ) from exc
    except AuthenticationRequiredError as exc:
        raise ProbeFailure(
            blocker_code="P35_LIVE_REVIEWER_TOKEN_INVALID",
            summary="Live reviewer token could not be verified.",
            checks=[
                _check(
                    "reviewer_auth",
                    "fail",
                    blocker_code="P35_LIVE_REVIEWER_TOKEN_INVALID",
                    summary="OIDC/JWKS verification rejected the reviewer token.",
                )
            ],
        ) from exc
    except PlatformPersistenceError as exc:
        raise ProbeFailure(
            blocker_code=exc.code,
            summary="PLF reviewer role lookup failed.",
            checks=[
                _check(
                    "reviewer_auth",
                    "fail",
                    blocker_code=exc.code,
                    summary="PLF AUTH role lookup did not return safe reviewer evidence.",
                )
            ],
        ) from exc
    if actor is None or not actor.roles.intersection(ARTIFACT_REVIEW_ROLES):
        raise ProbeFailure(
            blocker_code="P35_LIVE_REVIEWER_ROLE_REQUIRED",
            summary="Verified reviewer token did not map to a PLF REVIEWER or ADMIN actor.",
            checks=[
                _check(
                    "reviewer_auth",
                    "fail",
                    blocker_code="P35_LIVE_REVIEWER_ROLE_REQUIRED",
                    summary="A REVIEWER or ADMIN actor is required for live review writes.",
                )
            ],
        )
    return {
        "headers": {"Authorization": f"Bearer {token}"},
        "reviewer": actor.reviewer_id,
    }


def _require_live_manifest_and_profile(manifest: dict[str, Any]) -> None:
    if manifest.get("selection_mode") != "live_metadata":
        raise ProbeFailure(
            blocker_code=LIVE_BLOCKER,
            summary="Selected PPM manifest must be live_metadata.",
            checks=[
                _check(
                    "pilot_manifest",
                    "fail",
                    blocker_code=LIVE_BLOCKER,
                    summary="fixtures/pilot selected_objects.yaml is not live_metadata.",
                )
            ],
        )
    if manifest.get("source_db") != "PPM":
        raise ProbeFailure(
            blocker_code=LIVE_BLOCKER,
            summary="Selected manifest source_db must be PPM.",
            checks=[_check("pilot_manifest", "fail", blocker_code=LIVE_BLOCKER)],
        )
    settings = load_live_metadata_settings()
    if not settings.live_metadata_enabled:
        raise ProbeFailure(
            blocker_code=LIVE_BLOCKER,
            summary="MSSQL_ENABLE_LIVE_METADATA=1 is required.",
            checks=[_check("metadata_profile", "fail", blocker_code=LIVE_BLOCKER)],
        )
    profiles = load_db_profiles(settings, repo_root=REPO_ROOT)
    ppm_profile = next((profile for profile in profiles if profile.id == "ppm"), None)
    if ppm_profile is None or ppm_profile.database != "PPM":
        raise ProbeFailure(
            blocker_code=LIVE_BLOCKER,
            summary="Metadata profile registry must include ppm -> PPM.",
            checks=[
                _check(
                    "metadata_profile",
                    "fail",
                    blocker_code=LIVE_BLOCKER,
                    summary="No PLF fallback is allowed for the PPM target profile.",
                )
            ],
        )


def _selected_live_procedure(manifest: dict[str, Any]) -> dict[str, str]:
    for procedure in manifest.get("stored_procedures", []):
        if (
            procedure.get("complexity") == "simple"
            and procedure.get("object_type") == "PROCEDURE"
            and not procedure.get("review_required")
        ):
            return {
                "type": "PROCEDURE",
                "schema": str(procedure["schema"]),
                "name": str(procedure["name"]),
            }
    raise ProbeFailure(
        blocker_code=LIVE_BLOCKER,
        summary="Selected manifest must include a simple live PPM procedure.",
        checks=[
            _check(
                "pilot_manifest",
                "fail",
                blocker_code=LIVE_BLOCKER,
                summary="No simple procedure candidate was available for the bounded live gate.",
            )
        ],
    )


def _assert_safe_payload(payload: Any, check_name: str) -> None:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    lowered = serialized.lower()
    for fragment in FORBIDDEN_FRAGMENTS:
        if fragment.lower() in lowered:
            raise ProbeFailure(
                blocker_code="P35_LIVE_RAW_LEAKAGE_DETECTED",
                summary="Live knowledge confidence gate detected forbidden raw payload text.",
                checks=[
                    _check(
                        check_name,
                        "fail",
                        blocker_code="P35_LIVE_RAW_LEAKAGE_DETECTED",
                        summary=f"Forbidden fragment category detected: {fragment}",
                    )
                ],
            )


class ProbeFailure(RuntimeError):
    def __init__(
        self,
        *,
        blocker_code: str,
        summary: str,
        checks: list[dict[str, Any]],
    ) -> None:
        super().__init__(summary)
        self.blocker_code = blocker_code
        self.summary = summary
        self.checks = checks

    @classmethod
    def from_response(
        cls,
        response: Any,
        *,
        fallback_blocker: str,
        check_name: str,
    ) -> ProbeFailure:
        try:
            payload = response.json()
        except Exception:
            payload = {}
        code = str(payload.get("code") or fallback_blocker)
        if code == "KNOWLEDGE_SCHEMA_REQUIRED":
            blocker_code = code
        else:
            blocker_code = code or fallback_blocker
        detail = str(payload.get("detail") or f"HTTP {response.status_code}")
        return cls(
            blocker_code=blocker_code,
            summary=detail,
            checks=[
                _check(
                    check_name,
                    "fail",
                    blocker_code=blocker_code,
                    summary=f"HTTP {response.status_code}: {detail}",
                )
            ],
        )


def _result(
    *,
    status: str,
    blocker_code: str | None,
    summary: str,
    checks: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "gate": LIVE_GATE_ENV,
        "status": status,
        "productionReady": False,
        "blockerCode": blocker_code,
        "summary": summary,
        "checks": checks,
        "redaction": REDACTION,
    }


def _check(
    name: str,
    status: str,
    *,
    blocker_code: str | None = None,
    summary: str = "",
) -> dict[str, Any]:
    return {
        "name": name,
        "status": status,
        "blockerCode": blocker_code,
        "summary": summary,
    }


def _missing_required_env() -> list[str]:
    required = list(REQUIRED_ENV)
    if os.getenv("AUTH_RBAC_ENFORCEMENT", "").strip() == "1":
        required.extend(AUTH_REVIEW_ENV)
    missing = [name for name in required if not os.getenv(name, "").strip()]
    for enabled_name in (
        "P35_KNOWLEDGE_LIVE_GATE",
        "MSSQL_ENABLE_LIVE_METADATA",
        "LLM_LIVE_GATE",
        "LLM_ENABLE_REMOTE",
        "LLM_ALLOW_SP_TEXT",
    ):
        if os.getenv(enabled_name, "").strip() != "1":
            missing.append(f"{enabled_name}=1")
    return sorted(dict.fromkeys(missing))


def _flag_enabled(name: str) -> bool:
    return os.getenv(name, "").strip().lower() in {"1", "true", "yes", "on"}


def _expected_remote_provider() -> str:
    provider = os.getenv("LLM_REMOTE_PROVIDER", "openai").strip().lower()
    if provider in {"pgpt", "p-gpt", "private-gpt"}:
        return "pgpt"
    return "openai"


def _pilot_manifest() -> dict[str, Any]:
    return yaml.safe_load(PILOT_MANIFEST.read_text(encoding="utf-8"))


def load_root_dotenv(path: Path | None = None) -> None:
    env_path = path or REPO_ROOT / ".env"
    if not env_path.exists():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def main() -> int:
    result = run_probe(load_dotenv=True)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result["status"] in {"passed", "skipped"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
