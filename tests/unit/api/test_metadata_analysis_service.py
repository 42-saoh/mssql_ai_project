from __future__ import annotations

from typing import Any

import pytest
from ai_agent_runtime import FakeModelGateway
from api_app.metadata_analysis_service import MetadataAnalysisService
from api_app.schemas import MetadataAnalysisRequest
from pydantic import ValidationError


class SpyRegistry:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def invoke_payload(self, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((tool_name, payload))
        return {
            "ok": True,
            "toolName": tool_name,
            "dbProfileId": "master",
            "snapshotId": "spy-snapshot-1",
            "collectedAt": "2026-05-12T00:00:00Z",
            "evidenceRefs": [
                {
                    "id": "spy_table_schema",
                    "source": "fixture",
                    "path": "fixtures/mcp/metadata_snapshot.json#/tables/0",
                    "objectType": "TABLE",
                    "objectName": "dbo.TB_ORDER",
                }
            ],
            "data": {
                "schema": "dbo",
                "tableName": "TB_ORDER",
                "columns": [{"name": "ORDER_ID", "dataType": "int"}],
                "definition": "CREATE PROCEDURE dbo.usp_leak AS SELECT 1",
                "rowData": [{"ORDER_ID": 1}],
                "secret": "do-not-return",
            },
        }


@pytest.fixture(autouse=True)
def fixture_metadata_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("P21_LIVE_PORTAL_GATE", "0")
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")
    monkeypatch.setenv("LLM_ENABLE_REMOTE", "0")


def test_metadata_analysis_request_requires_query_xor_target_and_defaults() -> None:
    request = MetadataAnalysisRequest.model_validate(
        {"dbProfileId": "master", "query": "order"}
    )

    assert request.options.use_llm_analysis is True
    assert request.options.use_ai_tool_orchestration is True
    assert request.options.max_targets == 3

    with pytest.raises(ValidationError):
        MetadataAnalysisRequest.model_validate({"dbProfileId": "master"})

    with pytest.raises(ValidationError):
        MetadataAnalysisRequest.model_validate(
            {
                "dbProfileId": "master",
                "query": "order",
                "target": {"schema": "dbo", "name": "TB_ORDER", "type": "TABLE"},
            }
        )


def test_metadata_analysis_uses_internal_mcp_tool_and_sanitized_fact_ids(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = SpyRegistry()
    monkeypatch.setattr(
        "api_app.metadata_analysis_service._build_internal_registry",
        lambda _db_profile_id: registry,
    )
    service = MetadataAnalysisService(
        model_gateway=FakeModelGateway(
            tool_plan_by_target_ref={
                "metadata.search:order": {
                    "toolRequests": [
                        {
                            "toolName": "get_table_schema",
                            "arguments": {
                                "dbProfileId": "master",
                                "schema": "dbo",
                                "tableName": "TB_ORDER",
                            },
                            "reason": "Need table schema evidence.",
                            "expectedEvidenceUse": "Anchor metadata object insight.",
                        }
                    ],
                    "assumptions": [],
                    "reviewMarkers": [],
                }
            }
        )
    )

    response = service.analyze(
        MetadataAnalysisRequest.model_validate(
            {
                "dbProfileId": "master",
                "query": "order",
                "objectTypes": ["TABLE"],
                "options": {"llmProfileId": "openai_fast_test", "maxTargets": 2},
            }
        )
    ).to_response()

    assert registry.calls == [
        (
            "get_table_schema",
            {
                "arguments": {
                    "dbProfileId": "master",
                    "schema": "dbo",
                    "tableName": "TB_ORDER",
                }
            },
        )
    ]
    assert response["aiToolEvidence"]["toolCallCount"] == 1
    assert response["deterministicFacts"]
    assert any(
        str(fact["id"]).startswith("mcp.get_table_schema.")
        for fact in response["deterministicFacts"]
    )
    assert response["objectInsights"][0]["evidenceRefs"][0].startswith("mcp.get_table_schema.")
    serialized = str(response).lower()
    for forbidden in ("create procedure", "rowdata", "row_data", "do-not-return"):
        assert forbidden not in serialized


def test_metadata_analysis_blocks_adversarial_planner_without_leaking_arguments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = SpyRegistry()
    monkeypatch.setattr(
        "api_app.metadata_analysis_service._build_internal_registry",
        lambda _db_profile_id: registry,
    )
    service = MetadataAnalysisService(
        model_gateway=FakeModelGateway(
            tool_plan_by_target_ref={
                "dbo.TB_ORDER": {
                    "toolRequests": [
                        {
                            "toolName": "get_table_schema",
                            "arguments": {
                                "dbProfileId": "master",
                                "schema": "dbo",
                                "tableName": "TB_ORDER",
                                "sql": "DROP TABLE dbo.TB_ORDER",
                                "secret": "do-not-return",
                            },
                            "reason": "Unsafe request.",
                            "expectedEvidenceUse": "Should be blocked.",
                        }
                    ],
                    "assumptions": [],
                    "reviewMarkers": [],
                }
            }
        )
    )

    response = service.analyze(
        MetadataAnalysisRequest.model_validate(
            {
                "dbProfileId": "master",
                "target": {"schema": "dbo", "name": "TB_ORDER", "type": "TABLE"},
                "options": {"llmProfileId": "openai_fast_test"},
            }
        )
    ).to_response()

    assert registry.calls == []
    assert response["aiToolEvidence"]["blockedRequests"][0]["code"] in {
        "AI_TOOL_FORBIDDEN_ARGUMENT",
        "AI_TOOL_FREEFORM_SQL_BLOCKED",
    }
    assert any(
        marker["code"] == "AI_METADATA_ANALYSIS_REVIEW_REQUIRED"
        for marker in response["reviewMarkers"]
    )
    serialized = str(response).lower()
    assert "drop table" not in serialized
    assert "do-not-return" not in serialized
