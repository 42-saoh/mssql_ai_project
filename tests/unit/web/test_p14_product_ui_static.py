from __future__ import annotations

import json
import re
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


def _form_control_block(source: str, name: str) -> str:
    match = re.search(
        rf"<(?:input|textarea)\s+[^>]*name=\"{re.escape(name)}\"[\s\S]*?(?:/>|</textarea>)",
        source,
    )
    assert match is not None
    return match.group(0)


def test_p14_sample_names_come_from_live_manifest_not_web_source() -> None:
    manifest = yaml.safe_load(MANIFEST.read_text(encoding="utf-8"))
    reader_source = (WEB_ROOT / "lib" / "pilot-manifest.ts").read_text(encoding="utf-8")
    request_sources = "\n".join(
        path.read_text(encoding="utf-8")
        for root in [WEB_ROOT / "app" / "requests"]
        for path in root.rglob("*")
        if path.suffix in {".ts", ".tsx"}
    )
    request_sources += "\n" + (WEB_ROOT / "components" / "request-form.tsx").read_text(
        encoding="utf-8"
    )

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
            assert name not in request_sources


def test_p14_web_source_keeps_forbidden_actions_out_of_ui() -> None:
    source = _web_source().lower()

    assert "/api/v1/metadata/search" not in source
    assert "/api/v1/metadata/analyze" in source
    assert "/api/v1/metadata/tools" in source
    assert "/api/v1/knowledge/" in source
    assert "/metadata/design" in source
    assert "/api/metadata/design-runs" in source
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
    search_page = (WEB_ROOT / "app" / "metadata" / "search" / "page.tsx").read_text(
        encoding="utf-8"
    )
    analyze_action = (WEB_ROOT / "components" / "metadata-analyze-action.tsx").read_text(
        encoding="utf-8"
    )
    analyze_route = (
        WEB_ROOT / "app" / "api" / "metadata" / "analyze" / "route.ts"
    ).read_text(encoding="utf-8")
    portal_api = (WEB_ROOT / "lib" / "api" / "portal-api.ts").read_text(encoding="utf-8")
    http_client = (WEB_ROOT / "lib" / "api" / "http-client.ts").read_text(encoding="utf-8")
    smoke = (WEB_ROOT / "scripts" / "http-adapter-smoke.mjs").read_text(encoding="utf-8")

    assert 'href="/metadata/dependencies"' in layout
    assert 'href="/jobs"' in layout
    assert "Dependency diagnostics" in page
    assert "get_dependency_closure" in page
    assert "resolve_dependency_reference" in page
    assert "api.listMetadataTools()" in page
    assert "api.invokeMetadataTool" in page
    assert 'cleanParam(params, "dbProfileId", "ppm")' in page
    assert 'cleanParam(params, "objectName", "GetInspItemsCd")' in page
    assert 'cleanParam(params, "referencedName", "PEX_INSP_ITEMS")' in page
    assert 'redirect("/metadata/design?intent=search")' in search_page
    assert "MetadataAnalyzeAction" not in search_page
    assert 'fetch("/api/metadata/analysis-runs"' in analyze_action
    assert "/api/metadata/analysis-runs/${encodeURIComponent(run.runId)}" in analyze_action
    assert "AI_METADATA_ANALYSIS_TIMEOUT" in analyze_action
    assert "Analysis target limit" in analyze_action
    assert 'name="generateDtoDrafts"' in analyze_action
    assert "Generate DTO draft" in analyze_action
    assert "api.submitMetadataAnalysisRun(payload)" in (
        WEB_ROOT / "app" / "api" / "metadata" / "analysis-runs" / "route.ts"
    ).read_text(encoding="utf-8")
    assert "api.getMetadataAnalysisRun(runId)" in (
        WEB_ROOT
        / "app"
        / "api"
        / "metadata"
        / "analysis-runs"
        / "[runId]"
        / "route.ts"
    ).read_text(encoding="utf-8")
    assert "api.analyzeMetadata(payload)" in analyze_route
    assert "evidenceStatusLabel(item.status)" in _web_source()
    assert "DTO {item.status}" not in _web_source()
    assert "generatedDrafts" in _web_source()
    assert "downloadGeneratedDraft" in _web_source()
    assert "Download DTO draft" in _web_source()
    assert "inputSchema" not in page
    assert "input schema" not in page.lower()
    assert "listMetadataTools" in portal_api
    assert "invokeMetadataTool" in portal_api
    assert "/api/v1/metadata/tools/${encodeURIComponent(toolName)}/invoke" in http_client
    assert "metadataTools.tools.every((tool) => !(\"input\" in tool))" in smoke
    assert "dependencyClosure.data.unresolved" in smoke


def test_p38_metadata_design_chat_page_and_proxy_are_wired() -> None:
    layout = (WEB_ROOT / "app" / "layout.tsx").read_text(encoding="utf-8")
    page = (WEB_ROOT / "app" / "metadata" / "design" / "page.tsx").read_text(
        encoding="utf-8"
    )
    component = (WEB_ROOT / "components" / "metadata-design-chat.tsx").read_text(
        encoding="utf-8"
    )
    styles = (WEB_ROOT / "app" / "globals.css").read_text(encoding="utf-8")
    submit_route = (
        WEB_ROOT / "app" / "api" / "metadata" / "design-runs" / "route.ts"
    ).read_text(encoding="utf-8")
    poll_route = (
        WEB_ROOT
        / "app"
        / "api"
        / "metadata"
        / "design-runs"
        / "[runId]"
        / "route.ts"
    ).read_text(encoding="utf-8")
    conversation_route = (
        WEB_ROOT
        / "app"
        / "api"
        / "metadata"
        / "design-conversations"
        / "[conversationId]"
        / "route.ts"
    ).read_text(encoding="utf-8")
    portal_api = (WEB_ROOT / "lib" / "api" / "portal-api.ts").read_text(
        encoding="utf-8"
    )
    http_client = (WEB_ROOT / "lib" / "api" / "http-client.ts").read_text(
        encoding="utf-8"
    )

    assert 'href="/metadata/design"' in layout
    assert "MetadataDesignChat" in page
    assert "api.listMetadataProfiles()" in page
    assert "searchParams" in page
    assert "initialWorkModeForIntent(firstParam(params.intent))" in page
    assert 'value === "search" ? "SEARCH_METADATA" : "NEW_TABLE_DESIGN"' in page
    assert "initialWorkMode={initialWorkMode}" in page
    assert 'fetch("/api/metadata/design-runs"' in component
    assert "/api/metadata/design-runs/${encodeURIComponent(nextRun.runId)}" in component
    assert "metadata-chat-shell" in component
    assert "metadata-chat-transcript" in component
    assert "metadata-chat-composer" in component
    assert "metadata-design-output-stack" in component
    assert component.index("metadata-chat-transcript") < component.index(
        "metadata-chat-composer"
    )
    assert component.index("metadata-chat-composer") < component.index(
        "metadata-design-output-stack"
    )
    assert "Work mode" in component
    assert "Search metadata" in component
    assert "New table design" in component
    assert "Refine current design" in component
    assert "conversationModeForWorkMode" in component
    assert "intentModeForWorkMode" in component
    assert "conversationMode" in component
    assert "Search limit" in component
    assert "Search object types" in component
    assert "searchInputs" in component
    assert "intentMode," in component
    assert '"SEARCH_ONLY"' in component
    assert '"DESIGN_TABLE"' in component
    assert 'nextRun.result.resultKind === "SEARCH_RESULT"' in component
    assert '"REFINE_CURRENT_DESIGN"' in component
    assert 'setWorkMode("NEW_TABLE_DESIGN")' in component
    assert "SEARCH_RESULT" in component
    assert "searchResult" in component
    assert "Use as table hint" in component
    assert "MetadataEvidenceCandidates" in component
    assert 'const [message, setMessage] = useState("")' in component
    assert "messagePlaceholder" in component
    assert "placeholder={messagePlaceholder}" in component
    assert "const canSubmit = !isLoading && message.trim().length > 0" in component
    assert "disabled={!canSubmit}" in component
    assert "interpretedIntent" in component
    assert "appliedChanges" in component
    assert "createTableScriptPreview" in component
    assert "Download SQL preview" in component
    assert "Download DTO draft" in component
    assert "new Blob([content]" in component
    assert 'className="metadata-chat-compose"' not in component
    assert "metadata-chat-layout" not in component
    assert "metadata-design-field-row" not in component
    assert "Add field" not in component
    assert "Field 1 name" not in component
    assert ".metadata-chat-transcript" in styles
    assert "overflow-y: auto" in styles
    assert "height: clamp(360px, 52vh, 620px)" in styles
    assert ".metadata-chat-composer" in styles
    assert ".metadata-chat-controls" in styles
    assert ".metadata-design-output-stack" in styles
    assert "grid-template-columns: minmax(320px, 0.9fr) minmax(0, 1.1fr)" not in styles
    assert ".metadata-chat-layout" not in styles
    assert "api.submitMetadataDesignRun(payload)" in submit_route
    assert "conversationMode: request.options?.conversationMode ?? \"NEW_DESIGN\"" in submit_route
    assert "intentMode: request.options?.intentMode ?? \"AUTO\"" in submit_route
    assert "includeTableSchema: true" in submit_route
    assert "api.getMetadataDesignRun(runId)" in poll_route
    assert "api.getMetadataDesignConversation(conversationId)" in conversation_route
    assert "submitMetadataDesignRun" in portal_api
    assert "getMetadataDesignRun" in portal_api
    assert "getMetadataDesignConversation" in portal_api
    assert "/api/v1/metadata/design-runs" in http_client
    assert (
        "/api/v1/metadata/design-conversations/${encodeURIComponent(conversationId)}"
        in http_client
    )
    combined = "\n".join([component, submit_route, poll_route, conversation_route]).lower()
    for forbidden in (
        "/execute",
        "/apply",
        "/deploy",
        "/publish",
        "workflow artifact",
        "artifact-download",
    ):
        assert forbidden not in combined


def test_p21_web_pages_use_strict_http_api_without_demo_fallbacks() -> None:
    client = (WEB_ROOT / "lib" / "api" / "client.ts").read_text(encoding="utf-8")
    request_page = (WEB_ROOT / "app" / "requests" / "new" / "page.tsx").read_text(
        encoding="utf-8"
    )
    request_form = (WEB_ROOT / "components" / "request-form.tsx").read_text(
        encoding="utf-8"
    )
    artifact_page = (
        WEB_ROOT / "app" / "artifacts" / "[artifactId]" / "page.tsx"
    ).read_text(encoding="utf-8")
    job_status_view = (WEB_ROOT / "components" / "job-status-view.tsx").read_text(
        encoding="utf-8"
    )
    job_auto_refresh = (WEB_ROOT / "components" / "job-auto-refresh.tsx").read_text(
        encoding="utf-8"
    )
    procedure_search_route = (
        WEB_ROOT / "app" / "api" / "metadata" / "procedure-search" / "route.ts"
    ).read_text(encoding="utf-8")
    portal_api = (WEB_ROOT / "lib" / "api" / "portal-api.ts").read_text(
        encoding="utf-8"
    )
    http_client = (WEB_ROOT / "lib" / "api" / "http-client.ts").read_text(encoding="utf-8")
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
    assert "getPilotManifestSummary" not in request_page
    assert "selectedSample" not in request_page
    assert "Sample request target" not in request_form
    assert "PPM pilot samples" not in request_form
    assert "sample-option" not in request_form
    assert "/requests/new?sample=" not in request_form
    assert "AnalysisHistoryList" in source
    assert "api.listJobs(5)" in source
    assert "api.listJobs(limit, targetKey || undefined)" in source
    assert "targetKey" in source
    assert "Same target history" in source
    assert "Exact targetKey" in source
    assert 'firstParam(value) ?? "50"' in source
    assert "api.listJobArtifacts(job.jobId)" in source
    assert "View all analysis history" in source
    assert "batchTargets" in source
    assert 'name="targetType" readOnly type="hidden" value="PROCEDURE"' in source
    assert 'name="schema" readOnly type="hidden"' in source
    assert 'name="name" readOnly type="hidden"' in source
    assert "SingleProcedureTargetInput" in request_form
    assert "BatchProcedureTargetsInput" in request_form
    assert "ProcedureSearchCombobox" in source
    assert 'fetch(`/api/metadata/procedure-search?' in source
    assert "/api/metadata/search" not in source
    assert "searchMetadataObjects" not in source
    assert "api.searchProcedures({ dbProfileId, query, limit })" in procedure_search_route
    assert "submitMetadataDesignRun" not in procedure_search_route
    assert "getMetadataDesignRun" not in procedure_search_route
    assert "searchProcedures" in portal_api
    assert "/api/v1/metadata/procedure-search" in http_client
    assert "Type at least 2 characters." not in source
    assert "field-code--empty" in source
    assert "Add to batch" in source
    assert "Search and add PROCEDURE targets one at a time." in source
    assert "required" in _form_control_block(source, "batchTargets")
    assert not (WEB_ROOT / "app" / "api" / "metadata" / "search" / "route.ts").exists()
    global_css = (WEB_ROOT / "app" / "globals.css").read_text(encoding="utf-8")
    assert "align-items: start;" in global_css
    assert "position: absolute;" in global_css
    assert "z-index: 30;" in global_css
    assert "max-height: min(420px, 45vh);" in global_css
    assert ".field-code--empty" in global_css
    assert "useLlmAnalysis" in request_page
    assert "useAiToolOrchestration" in request_page
    assert "usePlatformToolOrchestration" in request_page
    assert "allowSpDefinitionToModel" in request_page
    assert "sourceContextMode" in request_page
    assert "sourceDependencyMode" in request_page
    assert 'name="useLlmAnalysis" defaultChecked' in source
    assert 'name="useAiToolOrchestration" defaultChecked' in source
    assert 'name="usePlatformToolOrchestration" defaultChecked' in source
    assert 'name="allowSpDefinitionToModel" defaultChecked' in source
    assert 'name="sourceContextMode" defaultValue="RETRIEVED_SPANS"' in source
    assert 'name="sourceDependencyMode" defaultValue="CONFIRMED_PROCEDURES"' in source
    assert 'defaultValue="openai_sp_semantic_analysis"' in source
    assert "semantic analysis - gpt-5.5" in source
    assert "openai_fast_test" in source
    assert "api.listJobAgentRuns" in source
    assert "api.listJobKnowledgeAssets" in source
    assert "createKnowledgeExport" in source
    assert "runAsync" in request_page
    assert 'params.set("runAsync", "true")' in http_client
    assert "redirect(`/jobs/${response.jobId}`)" in request_page
    assert "Estimated progress" in job_status_view
    assert 'role="progressbar"' in job_status_view
    assert "aria-valuenow={progressPercent}" in job_status_view
    assert "router.refresh()" in job_auto_refresh
    assert "작업 진행 중 - 자동 새로고침 중" in job_auto_refresh
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


def test_job_page_renders_dependency_child_agent_runs_without_raw_trace_dump() -> None:
    job_status_view = (WEB_ROOT / "components" / "job-status-view.tsx").read_text(
        encoding="utf-8"
    )

    assert "dependencyAnalysis" in job_status_view
    assert "LLM_SEMANTIC_ANALYST_DEPENDENCY" in job_status_view
    assert "Dependency child" in job_status_view
    assert "Root run" in job_status_view
    assert "근거 보강 필요" in job_status_view
    assert "skippedDependencyDisplayLimit = 8" in job_status_view
    assert "sourceContextDigest" in job_status_view
    assert "target {run.targetRef}" in job_status_view
    assert "run.structuredOutput" not in job_status_view
    assert "componentInvocations" not in job_status_view


def test_knowledge_fact_graph_links_and_draft_download_controls_are_wired() -> None:
    job_status_view = (WEB_ROOT / "components" / "job-status-view.tsx").read_text(
        encoding="utf-8"
    )
    artifact_preview = (WEB_ROOT / "components" / "artifact-preview.tsx").read_text(
        encoding="utf-8"
    )
    metadata_panel = (WEB_ROOT / "components" / "metadata-analysis-panel.tsx").read_text(
        encoding="utf-8"
    )
    artifact_actions = (WEB_ROOT / "components" / "artifact-actions.tsx").read_text(
        encoding="utf-8"
    )
    global_css = (WEB_ROOT / "app" / "globals.css").read_text(encoding="utf-8")
    asset_page = (
        WEB_ROOT / "app" / "knowledge" / "assets" / "[assetId]" / "page.tsx"
    ).read_text(encoding="utf-8")
    facts_page = (
        WEB_ROOT
        / "app"
        / "knowledge"
        / "assets"
        / "[assetId]"
        / "versions"
        / "[versionId]"
        / "facts"
        / "page.tsx"
    ).read_text(encoding="utf-8")
    single_download_route = (
        WEB_ROOT / "app" / "artifacts" / "[artifactId]" / "download" / "route.ts"
    ).read_text(encoding="utf-8")
    bundle_download_route = (
        WEB_ROOT / "app" / "jobs" / "[jobId]" / "artifacts" / "download" / "route.ts"
    ).read_text(encoding="utf-8")
    artifact_download = (WEB_ROOT / "lib" / "artifact-download.ts").read_text(
        encoding="utf-8"
    )
    zip_writer = (WEB_ROOT / "lib" / "zip-writer.ts").read_text(encoding="utf-8")
    package_json = json.loads((WEB_ROOT / "package.json").read_text(encoding="utf-8"))
    helper_smoke = (WEB_ROOT / "scripts" / "draft-download-helper-smoke.mjs").read_text(
        encoding="utf-8"
    )

    assert 'href={`/api/v1/knowledge/assets/${asset.assetId}`}' not in job_status_view
    assert "knowledgeAssetHref(asset.assetId)" in job_status_view
    assert "knowledgeFactsHref(asset.assetId, asset.currentVersionId)" in job_status_view
    assert 'href={`/api/v1/knowledge/assets/${asset.assetId}`}' not in metadata_panel
    assert "`/api/v1/knowledge/assets/${asset.assetId}/versions/" not in metadata_panel
    assert "knowledgeAssetHref(asset.assetId)" in metadata_panel
    assert "knowledgeFactsHref(asset.assetId, asset.currentVersionId)" in metadata_panel
    assert "encodeURIComponent(assetId)" in metadata_panel
    assert "displayCaveatText(marker.message)" in metadata_panel
    assert "displayCaveatText(caveat)" in metadata_panel
    assert "api.getKnowledgeAsset(assetId)" in asset_page
    assert "api.listKnowledgeAssetVersions(assetId)" in asset_page
    assert "api.listKnowledgeFacts(assetId, versionId)" in facts_page
    assert "fact.payload" not in facts_page
    assert "edge.payload" not in facts_page
    assert "Open current facts" in asset_page
    assert "Sanitized fact rows" in facts_page
    assert "Fact graph links" in facts_page

    assert "ArtifactActions" in artifact_preview
    assert "const displayedContent = displayArtifactContent(artifact.content)" in artifact_preview
    assert "content={displayedContent}" in artifact_preview
    assert 'import Markdown from "react-markdown";' in artifact_preview
    assert 'import remarkGfm from "remark-gfm";' in artifact_preview
    assert "isMarkdownArtifactType(artifact.type)" in artifact_preview
    markdown_type_block = re.search(
        r"markdownArtifactTypes = new Set<Artifact\[\"type\"\]>\(\[([\s\S]*?)\]\);",
        artifact_preview,
    )
    assert markdown_type_block is not None
    assert '"SP_ANALYSIS_DOC"' in markdown_type_block.group(1)
    assert '"DEPENDENCY_REPORT"' in markdown_type_block.group(1)
    for code_preview_type in (
        "METADATA_QUERY_RESULT",
        "SCHEMA_ENRICHMENT_RESULT",
        "MAPPER_XML",
        "MAPPER_INTERFACE",
        "SERVICE_DRAFT",
        "DTO_DRAFT",
        "VALIDATION_REPORT",
    ):
        assert code_preview_type not in markdown_type_block.group(1)
    assert "remarkPlugins={[remarkGfm]}" in artifact_preview
    assert "skipHtml" in artifact_preview
    assert 'className="markdown-preview"' in artifact_preview
    assert "<pre>{displayedContent}</pre>" in artifact_preview
    assert "rehypeRaw" not in artifact_preview
    assert "dangerouslySetInnerHTML" not in artifact_preview
    assert ".markdown-preview {" in global_css
    assert ".markdown-preview table" in global_css
    assert ".markdown-preview pre code" in global_css
    assert "Copy content" in artifact_actions
    assert "Download draft file" in artifact_actions
    assert "navigator.clipboard.writeText(content)" in artifact_actions
    assert "/artifacts/${encodeURIComponent(artifactId)}/download" in artifact_actions
    assert "Download all draft artifacts" in job_status_view
    assert "/artifacts/download" in job_status_view
    assert "api.getArtifact(artifactId)" in single_download_route
    assert "displayArtifactContent(artifact.content)" in single_download_route
    assert "api.listJobArtifacts(jobId)" in bundle_download_route
    assert "api.getArtifact(artifact.artifactId)" in bundle_download_route
    assert "displayArtifactContent(artifact.content)" in bundle_download_route
    assert "displayCaveatText" in bundle_download_route
    assert "createStoreOnlyZip(entries)" in bundle_download_route
    assert "README.md" in bundle_download_route
    assert "manifest.json" in bundle_download_route
    assert "application/zip" in bundle_download_route

    assert 'SP_ANALYSIS_DOC: "md"' in artifact_download
    assert 'DEPENDENCY_REPORT: "md"' in artifact_download
    assert 'MAPPER_XML: "xml"' in artifact_download
    assert 'MAPPER_INTERFACE: "java"' in artifact_download
    assert 'SERVICE_DRAFT: "java"' in artifact_download
    assert "DDL_DRAFT" not in artifact_download
    assert "VO_DRAFT" not in artifact_download
    assert "MODEL_DRAFT" not in artifact_download
    assert "sanitizeFilePart" in artifact_download
    assert "0x04034b50" in zip_writer
    assert "0x02014b50" in zip_writer
    assert "0x06054b50" in zip_writer
    assert "react-markdown" in package_json["dependencies"]
    assert "remark-gfm" in package_json["dependencies"]
    assert package_json["scripts"]["smoke:draft-download"] == (
        "node --experimental-strip-types scripts/draft-download-helper-smoke.mjs"
    )
    assert package_json["scripts"]["test:smoke"] == "pnpm run build"
    assert "artifactFileExtension(\"SP_ANALYSIS_DOC\")" in helper_smoke
    assert "artifactFilename(" in helper_smoke
    assert "createStoreOnlyZip(" in helper_smoke
    assert "README.md" in helper_smoke
    assert "manifest.json" in helper_smoke
    assert "0x06054b50" in helper_smoke


def test_validation_and_metadata_caveat_ui_avoids_false_error_states() -> None:
    artifact_preview = (WEB_ROOT / "components" / "artifact-preview.tsx").read_text(
        encoding="utf-8"
    )
    metadata_search = (WEB_ROOT / "app" / "metadata" / "search" / "page.tsx").read_text(
        encoding="utf-8"
    )
    metadata_design = (WEB_ROOT / "components" / "metadata-design-chat.tsx").read_text(
        encoding="utf-8"
    )
    display_helpers = (WEB_ROOT / "lib" / "display-caveats.ts").read_text(
        encoding="utf-8"
    )

    assert "StatusPill value={check.result}" in artifact_preview
    assert "check.result === \"PASS\"" in artifact_preview
    assert "passedCheckLabel(check.severity)" in artifact_preview
    assert "ruleLevelLabel(check.severity)" in artifact_preview
    assert "StatusPill value={check.severity} label={check.severity}" not in artifact_preview
    assert artifact_preview.index("StatusPill value={check.result}") < artifact_preview.index(
        "check.result === \"PASS\""
    )
    assert "displayCaveatText(check.message" in artifact_preview
    assert "displayCaveatText(item)" in artifact_preview

    assert 'redirect("/metadata/design?intent=search")' in metadata_search
    assert "result.searchResult.blockers.map" in metadata_design
    assert "Evidence bound" in metadata_design
    assert "metadataCaveatMessages(response.caveats, caveatBlockers)" not in metadata_search
    assert "REVIEW_REQUIRED" in metadata_design

    assert "DEPENDENCY_METADATA_INCOMPLETE" in display_helpers
    assert "의존성 링크 일부는 근거 보강 필요 상태입니다" in display_helpers
    assert "Evidence caveat: " in display_helpers
    assert "review_required" in display_helpers
    assert "evidence_caveat" in display_helpers
    assert "displayArtifactContent" in display_helpers
    assert "LLM_INFERENCE_EVIDENCE_CAVEAT" in display_helpers
    assert "_EVIDENCE_CAVEAT" in display_helpers
    assert "_EVIDENCE_CAVEATS" in display_helpers
    assert "status=EVIDENCE_CAVEAT" in display_helpers


def test_web_visible_copy_uses_evidence_caveat_language_not_review_actions() -> None:
    source = _web_source().lower()
    raw_source = _web_source()

    assert "review required" not in source
    assert "review marker" not in source
    assert "manual review" not in source
    assert "approval decision" not in source
    assert "evidence caveat" in source
    assert "근거 보강 필요" in raw_source
    assert "분석 중" in raw_source
    assert "洹쇨굅" not in raw_source
    assert "遺꾩꽍" not in raw_source
    assert "쨌" not in raw_source
    assert "�" not in raw_source
