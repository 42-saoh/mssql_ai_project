from __future__ import annotations

from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]


def test_platform_ai_tool_catalog_declares_internal_read_only_tools() -> None:
    catalog_path = ROOT / "spec" / "agent-tools" / "platform_ai_tool_catalog.yaml"
    catalog = yaml.safe_load(catalog_path.read_text(encoding="utf-8"))

    assert catalog["service"] == "platformAgentTools"
    assert catalog["readOnly"] is True
    assert catalog["internalOnly"] is True
    tools = catalog["tools"]
    by_name = {tool["name"]: tool for tool in tools}
    assert {
        "platform.search_knowledge_facts",
        "platform.list_knowledge_assets",
        "platform.get_knowledge_version_graph",
        "platform.list_job_artifacts",
        "platform.get_latest_validation_report",
        "platform.list_job_agent_runs",
        "platform.list_registry_versions",
    } <= set(by_name)
    assert all(tool["active"] is True for tool in tools)
    assert all(tool["readOnly"] is True for tool in tools)
    assert all(tool["internalOnly"] is True for tool in tools)
    assert "PLATFORM_TOOL_SCOPE_SWITCH_BLOCKED" in catalog["errorCodes"]


def test_platform_ai_tools_do_not_expand_public_invoke_surface() -> None:
    openapi = yaml.safe_load(
        (ROOT / "spec" / "openapi" / "ai_agent_platform_openapi_v1.yaml").read_text(
            encoding="utf-8"
        )
    )
    paths = set(openapi["paths"])

    assert "/api/v1/metadata/tools/{toolName}/invoke" in paths
    assert not any("platform/tools" in path and "invoke" in path for path in paths)
    assert (
        openapi["components"]["schemas"]["SPAnalysisOptions"]["properties"][
            "usePlatformToolOrchestration"
        ]["default"]
        is True
    )
