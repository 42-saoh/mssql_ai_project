from pathlib import Path


def test_core_contract_assets_exist() -> None:
    root = Path(__file__).resolve().parents[2]
    assert (root / "spec" / "openapi" / "ai_agent_platform_openapi_v1.yaml").exists()
    assert (root / "db" / "schema" / "ai_agent_platform_schema_v2_dbo_prefix.sql").exists()
    assert (
        root / "db" / "schema" / "ai_agent_platform_schema_v11_plf_full_create.sql"
    ).exists()
    assert (
        root / "db" / "schema" / "ai_agent_platform_seed_required_v11.sql"
    ).exists()
    assert (root / "spec" / "mcp" / "mssql_metadata_tool_catalog.yaml").exists()
    assert (root / "spec" / "agent-tools" / "platform_ai_tool_catalog.yaml").exists()
    assert (root / "spec" / "validation" / "validation_rules.yaml").exists()
    assert (root / "spec" / "eval" / "p27_dependency_evidence_tooling_contract.yaml").exists()
    assert (root / "docker" / "test" / "docker-compose.yml").exists()
    assert (root / "docker" / "test" / "Dockerfile.python").exists()
    assert (root / "db" / "schema" / "README.md").exists()
