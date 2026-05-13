from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[3]
MANIFEST = ROOT / "fixtures" / "pilot" / "ppm_object_selection_v1" / "selected_objects.yaml"
WEB_ROOT = ROOT / "apps" / "web"


def _web_source() -> str:
    roots = [WEB_ROOT / "app", WEB_ROOT / "components", WEB_ROOT / "lib"]
    return "\n".join(
        path.read_text(encoding="utf-8")
        for root in roots
        for path in root.rglob("*")
        if path.suffix in {".ts", ".tsx"}
    )


def test_p14_sample_names_come_from_live_manifest_not_web_source() -> None:
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    reader_source = (WEB_ROOT / "lib" / "pilot-manifest.ts").read_text(encoding="utf-8")
    web_source = _web_source()

    assert 'selectionMode !== "live_metadata"' in reader_source
    assert "procedureSamples: []" in reader_source

    if manifest["selection_mode"] == "live_metadata":
        manifest_names = {item["name"] for item in manifest["stored_procedures"]}
        assert {
            "GetInspItemsCd",
            "PAD_GET_BAT_LIST_PRC",
            "PCS_PY_ManageInvoiceFldSchd_PRC",
        } <= manifest_names
        for name in manifest_names:
            assert name not in web_source


def test_p14_web_source_keeps_forbidden_actions_out_of_ui() -> None:
    source = _web_source().lower()

    assert "/api/v1/metadata/search" in source
    assert "/api/v1/metadata/analyze" in source
    assert "/api/v1/metadata/tools" in source
    assert "/api/v1/knowledge/" in source
    assert "/metadata/dependencies" in source
    assert "/api/v1/artifacts/" in source
    assert "/publish" not in source
    assert "/deploy" not in source
    assert "/execute" not in source
    assert "/review/decision" not in source
    assert "createapprovaldecision" not in source
    assert "recorddecision" not in source
    assert "approval_preview_" not in source
    assert "row data" in source
    assert "ddl/dml" in source
    assert "blocker-row" in source


def test_p29_dependency_diagnostics_use_safe_invocation_without_schema_exposure() -> None:
    layout = (WEB_ROOT / "app" / "layout.tsx").read_text(encoding="utf-8")
    page = (WEB_ROOT / "app" / "metadata" / "dependencies" / "page.tsx").read_text(
        encoding="utf-8"
    )
    portal_api = (WEB_ROOT / "lib" / "api" / "portal-api.ts").read_text(encoding="utf-8")
    http_client = (WEB_ROOT / "lib" / "api" / "http-client.ts").read_text(encoding="utf-8")
    smoke = (WEB_ROOT / "scripts" / "http-adapter-smoke.mjs").read_text(encoding="utf-8")

    assert 'href="/metadata/dependencies"' in layout
    assert "Dependency diagnostics" in page
    assert "get_dependency_closure" in page
    assert "resolve_dependency_reference" in page
    assert "api.listMetadataTools()" in page
    assert "api.invokeMetadataTool" in page
    assert "api.analyzeMetadata" in _web_source()
    assert "inputSchema" not in page
    assert "input schema" not in page.lower()
    assert "listMetadataTools" in portal_api
    assert "invokeMetadataTool" in portal_api
    assert "/api/v1/metadata/tools/${encodeURIComponent(toolName)}/invoke" in http_client
    assert "metadataTools.tools.every((tool) => !(\"input\" in tool))" in smoke
    assert "dependencyClosure.data.unresolved" in smoke


def test_p21_web_pages_use_strict_http_api_without_demo_fallbacks() -> None:
    client = (WEB_ROOT / "lib" / "api" / "client.ts").read_text(encoding="utf-8")
    request_page = (WEB_ROOT / "app" / "requests" / "new" / "page.tsx").read_text(
        encoding="utf-8"
    )
    artifact_page = (
        WEB_ROOT / "app" / "artifacts" / "[artifactId]" / "page.tsx"
    ).read_text(encoding="utf-8")
    source = _web_source()

    assert not (WEB_ROOT / "app" / "review" / "decision" / "page.tsx").exists()
    assert not (WEB_ROOT / "lib" / "api" / "mock-adapter.ts").exists()
    assert 'process.env.PORTAL_API_MODE ?? "http"' not in client
    assert "PORTAL_API_MODE=http is required for the P21 no-mock portal" in client
    assert "PORTAL_API_BASE_URL is required for the P21 no-mock portal" in client

    for demo_id in ("job_demo_", "art_demo_", "approval_preview_"):
        assert demo_id not in source

    assert "api.createSPAnalysisRequest" in request_page
    assert "api.createSPAnalysisBatchRequest" in request_page
    assert "batchTargets" in source
    assert "useLlmAnalysis" in request_page
    assert "useAiToolOrchestration" in request_page
    assert "allowSpDefinitionToModel" in request_page
    assert 'name="useLlmAnalysis" defaultChecked' in source
    assert 'name="useAiToolOrchestration" defaultChecked' in source
    assert 'name="allowSpDefinitionToModel" defaultChecked' in source
    assert 'defaultValue="openai_sp_semantic_analysis"' in source
    assert "semantic analysis - gpt-5.5" in source
    assert "openai_fast_test" in source
    assert "api.listJobAgentRuns" in source
    assert "api.listJobKnowledgeAssets" in source
    assert "createKnowledgeExport" in source
    assert "redirect(`/jobs/${response.jobId}`)" in request_page
    assert "objectProfiles" in source
    assert "insightGroups" in source
    assert "dependencyGraph" in source
    assert "dtoReadiness" in source
    assert "knowledgeAssets" in source
    assert "Knowledge assets" in source
    assert "Versioned fact graph" in source
    assert "plannerMetrics" in source
    assert "Planner effectiveness" in source
    assert "api.getLatestValidation(artifactId)" in artifact_page
    assert artifact_page.count("api.validateArtifact(artifactId)") == 1
    assert artifact_page.index("async function runValidation") < artifact_page.index(
        "api.validateArtifact(artifactId)"
    )
    assert "api.createApprovalDecision" not in source
    assert "formatPortalApiError" in source
    assert "portalApiErrorCode" in source
