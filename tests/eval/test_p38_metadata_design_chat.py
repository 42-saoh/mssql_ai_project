from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from ai_agent_runtime import FakeModelGateway
from api_app.metadata_design_service import (
    METADATA_DESIGN_DTO_DRAFT_PACKAGE,
    MetadataDesignChatService,
)
from api_app.schemas import MetadataDesignRunRequest

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "spec" / "eval" / "p38_metadata_design_chat_contract.yaml"
FIXTURE = ROOT / "fixtures" / "eval" / "metadata_design_chat_p38_v1.yaml"
FORBIDDEN_DTO_PACKAGE_FRAGMENTS = ("com.example", "org.example", "example.")


def _assert_metadata_dto_package(content: str) -> None:
    assert f"package {METADATA_DESIGN_DTO_DRAFT_PACKAGE};" in content
    for forbidden in FORBIDDEN_DTO_PACKAGE_FRAGMENTS:
        assert forbidden not in content


class P38EvalRegistry:
    def invoke_payload(self, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        arguments = payload["arguments"]
        if tool_name == "search_tables":
            data = {
                "candidates": [
                    {
                        "schema": "dbo",
                        "tableName": "PPM_ORDER_REQ",
                        "description": "Order request header",
                        "score": 95,
                    }
                ]
            }
        elif tool_name == "find_similar_tables":
            data = {
                "candidates": [
                    {
                        "schema": "dbo",
                        "tableName": "PPM_ORDER_REQ",
                        "description": "Similar order request table",
                        "score": 91,
                    }
                ]
            }
        elif tool_name == "get_table_schema":
            data = {
                "schema": "dbo",
                "tableName": "PPM_ORDER_REQ",
                "columns": [
                    {"name": "CUSTOMER_NM", "dataType": "VARCHAR(100)"},
                    {"name": "CUSTOMER_ADDR", "dataType": "VARCHAR(500)"},
                    {"name": "ORDER_DT", "dataType": "VARCHAR(8)"},
                ],
            }
        else:
            lookup = {
                "CUSTOMER_NM": ("CUSTOMER_NM", "Customer name", "VARCHAR(100)", 96),
                "CUSTOMER_ADDR": ("CUSTOMER_ADDR", "Customer address", "VARCHAR(500)", 94),
                "ORDER_DT": ("ORDER_DT", "Order date", "VARCHAR(8)", 93),
            }
            requested = str(arguments.get("physicalName") or "").upper()
            column_name, description, data_type, score = lookup.get(
                requested,
                ("ORDER_DT", "Order date", "VARCHAR(8)", 88),
            )
            data = {
                "candidates": [
                    {
                        "schema": "dbo",
                        "tableName": "PPM_ORDER_REQ",
                        "columnName": column_name,
                        "logicalName": description,
                        "description": description,
                        "dataType": data_type,
                        "score": score,
                    }
                ]
            }
        return {
            "ok": True,
            "toolName": tool_name,
            "dbProfileId": payload["arguments"]["dbProfileId"],
            "snapshotId": "p38-eval-snapshot-1",
            "collectedAt": "2026-05-17T00:00:00Z",
            "evidenceRefs": [
                {
                    "id": f"mcp.{tool_name}.p38_eval",
                    "source": "fixture",
                    "path": f"fixtures/eval/metadata_design_chat_p38_v1.yaml#/{tool_name}",
                    "objectType": "METADATA",
                    "objectName": "dbo.PPM_ORDER_REQ",
                }
            ],
            "data": data,
        }


@pytest.fixture(autouse=True)
def fixture_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("P21_LIVE_PORTAL_GATE", "0")
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")
    monkeypatch.setenv("LLM_ENABLE_REMOTE", "0")


def test_p38_contract_and_fixture_are_aligned() -> None:
    contract = _yaml(CONTRACT)
    fixture = _yaml(FIXTURE)

    assert contract["contract_id"] == "p38_metadata_design_chat"
    assert contract["production_ready"] is False
    assert fixture["scenario_id"] == "metadata_design_chat_p38_v1"
    assert fixture["expected"]["tableScriptField"] == contract["outputs"][
        "table_script_field"
    ]
    assert fixture["expected"]["dtoArtifactType"] == contract["outputs"][
        "dto_preview_artifact_type"
    ]
    assert contract["outputs"]["dto_preview_package"] == METADATA_DESIGN_DTO_DRAFT_PACKAGE
    assert set(contract["required_paths"]) == {
        "/api/v1/metadata/design-runs",
        "/api/v1/metadata/design-runs/{runId}",
        "/api/v1/metadata/design-conversations/{conversationId}",
    }
    assert contract["storage"]["manual_sql"].endswith(
        "ai_agent_platform_schema_v10_metadata_design_runs.sql"
    )
    assert contract["outputs"]["not_workflow_artifacts"] is True


def test_p38_fixture_design_eval_generates_evidence_backed_outputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _yaml(FIXTURE)
    monkeypatch.setattr(
        "api_app.metadata_design_service._build_internal_registry",
        lambda _db_profile_id: P38EvalRegistry(),
    )
    service = MetadataDesignChatService(model_gateway=FakeModelGateway())

    response = service.design(
        MetadataDesignRunRequest.model_validate(fixture["request"])
    ).to_response()

    expected = fixture["expected"]
    assert response["reviewRequired"] is True
    assert expected["tableScriptField"] in response["tableProposal"]
    assert response["dtoDraft"]["artifactType"] == expected["dtoArtifactType"]
    assert response["relatedMetadata"]
    assert response["standardizationMappings"]
    assert response["tableProposal"]["evidenceRefs"]
    assert "CREATE TABLE [dbo].[PPM_ORDER_REQ]" in response["tableProposal"][
        "createTableScriptPreview"
    ]
    assert "[CUSTOMER_NM] VARCHAR(100)" in response["tableProposal"][
        "createTableScriptPreview"
    ]
    _assert_metadata_dto_package(response["dtoDraft"]["content"])
    assert "public class PpmOrderReqDto" in response["dtoDraft"]["content"]
    assert any(
        "PK/FK and index structure must be confirmed" in reason
        for reason in response["tableProposal"]["reviewReasons"]
    )
    serialized = json.dumps(response, ensure_ascii=False, sort_keys=True)
    for forbidden in expected["forbiddenFragments"]:
        assert forbidden not in serialized


def _yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))
