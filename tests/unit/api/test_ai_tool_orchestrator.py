from __future__ import annotations

from api_app.ai_tool_orchestrator import AgentToolPolicy
from mssql_mcp_app.catalog import load_tool_catalog


def test_agent_tool_policy_allows_active_read_only_tool_and_caps_arguments() -> None:
    policy = AgentToolPolicy(
        tools=load_tool_catalog(),
        request_db_profile_id="master",
    )

    decision = policy.decide(
        tool_name="get_dependency_closure",
        arguments={
            "dbProfileId": "master",
            "schema": "dbo",
            "objectName": "usp_ProcessOrderBatch",
            "objectType": "PROCEDURE",
            "maxDepth": 99,
        },
    )

    assert decision.allowed is True
    assert decision.arguments["maxDepth"] == 3


def test_agent_tool_policy_blocks_profile_switch_and_write_like_arguments() -> None:
    policy = AgentToolPolicy(
        tools=load_tool_catalog(),
        request_db_profile_id="master",
    )

    profile_switch = policy.decide(
        tool_name="get_table_schema",
        arguments={
            "dbProfileId": "ppm",
            "schema": "dbo",
            "tableName": "TB_ORDER",
        },
    )
    write_like = policy.decide(
        tool_name="get_table_schema",
        arguments={
            "dbProfileId": "master",
            "schema": "dbo",
            "tableName": "TB_ORDER",
            "sql": "DROP TABLE dbo.TB_ORDER",
        },
    )
    freeform_sql = policy.decide(
        tool_name="search_metadata_objects",
        arguments={
            "dbProfileId": "master",
            "query": "SELECT * FROM dbo.TB_ORDER",
        },
    )

    assert profile_switch.allowed is False
    assert profile_switch.code == "AI_TOOL_PROFILE_SWITCH_BLOCKED"
    assert write_like.allowed is False
    assert write_like.code == "AI_TOOL_FORBIDDEN_ARGUMENT"
    assert freeform_sql.allowed is False
    assert freeform_sql.code == "AI_TOOL_FREEFORM_SQL_BLOCKED"
