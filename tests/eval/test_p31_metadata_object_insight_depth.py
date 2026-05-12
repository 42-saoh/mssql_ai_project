from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml
from ai_agent_runtime import FakeModelGateway
from api_app.metadata_analysis_service import MetadataAnalysisService
from api_app.schemas import MetadataAnalysisRequest

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "fixtures" / "eval" / "metadata_object_insight_depth_p31_v1.yaml"


class ObjectDepthRegistry:
    def invoke_payload(self, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        data_by_tool = {
            "get_table_schema": {
                "schema": "dbo",
                "tableName": "TB_ORDER",
                "description": "Order header.",
                "descriptionStatus": "CONFIRMED",
                "columns": [
                    {
                        "name": "ORDER_ID",
                        "dataType": "INT",
                        "isNullable": False,
                        "isIdentity": True,
                        "isPrimaryKey": True,
                        "description": "Primary key.",
                        "descriptionStatus": "CONFIRMED",
                    },
                    {
                        "name": "CUSTOMER_ID",
                        "dataType": "INT",
                        "isNullable": False,
                        "isIdentity": False,
                        "isPrimaryKey": False,
                        "description": "Customer reference.",
                        "descriptionStatus": "CONFIRMED",
                    },
                    {
                        "name": "STATUS_CD",
                        "dataType": "VARCHAR(30)",
                        "isNullable": False,
                        "isIdentity": False,
                        "isPrimaryKey": False,
                        "descriptionStatus": "REVIEW_REQUIRED",
                    },
                ],
                "definition": "CREATE PROCEDURE dbo.usp_leak AS SELECT 1",
                "rowData": [{"ORDER_ID": 1}],
                "secret": "do-not-return",
            },
            "get_table_constraints": {
                "schema": "dbo",
                "tableName": "TB_ORDER",
                "constraints": [
                    {
                        "name": "PK_TB_ORDER",
                        "constraintType": "PK",
                        "columns": ["ORDER_ID"],
                        "referencedObject": None,
                    },
                    {
                        "name": "FK_TB_ORDER_CUSTOMER",
                        "constraintType": "FK",
                        "columns": ["CUSTOMER_ID"],
                        "referencedObject": {
                            "schema": "dbo",
                            "tableName": "TB_CUSTOMER",
                            "columns": ["CUSTOMER_ID"],
                        },
                    },
                ],
            },
            "get_table_indexes": {
                "schema": "dbo",
                "tableName": "TB_ORDER",
                "indexes": [
                    {
                        "name": "IX_TB_ORDER_CUSTOMER",
                        "isUnique": False,
                        "indexType": "NONCLUSTERED",
                        "keyColumns": ["CUSTOMER_ID"],
                        "includedColumns": ["STATUS_CD"],
                    }
                ],
            },
            "get_extended_properties": {
                "schema": "dbo",
                "objectName": "TB_ORDER",
                "objectType": "TABLE",
                "extendedProperties": [
                    {
                        "name": "MS_Description",
                        "value": "Order header.",
                        "level": "OBJECT",
                    }
                ],
            },
            "get_related_db_objects": {
                "schema": "dbo",
                "objectName": "TB_ORDER",
                "objectType": "TABLE",
                "relatedObjects": [
                    {
                        "schema": "dbo",
                        "name": "TB_CUSTOMER",
                        "objectType": "TABLE",
                        "dependencyType": "FK",
                        "reviewStatus": "CONFIRMED",
                    }
                ],
            },
        }
        return {
            "ok": True,
            "toolName": tool_name,
            "dbProfileId": payload["arguments"]["dbProfileId"],
            "snapshotId": "p31-eval-snapshot-1",
            "collectedAt": "2026-05-12T00:00:00Z",
            "evidenceRefs": [
                {
                    "id": f"p31_{tool_name}",
                    "source": "fixture",
                    "path": f"fixtures/eval/metadata_object_insight_depth_p31_v1.yaml#{tool_name}",
                    "objectType": "TABLE",
                    "objectName": "dbo.TB_ORDER",
                }
            ],
            "data": data_by_tool[tool_name],
        }


@pytest.fixture(autouse=True)
def fixture_metadata_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("P21_LIVE_PORTAL_GATE", "0")
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")
    monkeypatch.setenv("LLM_ENABLE_REMOTE", "0")


def test_p31_metadata_object_depth_fixture_contract() -> None:
    fixture = _fixture()

    assert fixture["production_ready"] is False
    assert fixture["status"] == "authored_p31"
    assert {scenario["fixture_id"] for scenario in fixture["scenarios"]} == {
        "p31_table_object_depth",
        "p31_adversarial_depth_planner_blocked",
    }


def test_p31_metadata_object_depth_builds_profiles_graph_and_dto(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "api_app.metadata_analysis_service._build_internal_registry",
        lambda _db_profile_id: ObjectDepthRegistry(),
    )
    scenario = _scenario("p31_table_object_depth")
    response = MetadataAnalysisService(
        model_gateway=FakeModelGateway(
            tool_plan_by_target_ref={"dbo.TB_ORDER": scenario["planner_output"]}
        )
    ).analyze(MetadataAnalysisRequest.model_validate(scenario["request"]))
    payload = response.to_response()

    profile = payload["objectProfiles"][0]
    assert profile["objectRef"] == scenario["expected"]["objectRef"]
    assert profile["columnCount"] == 3
    assert profile["primaryKeyCount"] == 1
    assert profile["foreignKeyCount"] == 1
    assert profile["indexCount"] == 1
    assert payload["dependencyGraph"]["edges"]
    assert payload["dtoReadiness"][0]["fieldCount"] == 3
    categories = {group["category"] for group in payload["insightGroups"]}
    assert set(scenario["expected"]["requiredCategories"]) <= categories
    assert any(
        str(fact["id"]).startswith(scenario["expected"]["requiredFactIdPrefix"])
        for fact in payload["deterministicFacts"]
    )
    assert any(
        str(fact["id"]).startswith(scenario["expected"]["requiredToolFactPrefix"])
        for fact in payload["deterministicFacts"]
    )
    serialized = json.dumps(payload, sort_keys=True)
    for fragment in scenario["expected"]["forbiddenFragments"]:
        assert fragment.lower() not in serialized.lower()


def test_p31_metadata_object_depth_blocks_adversarial_planner(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "api_app.metadata_analysis_service._build_internal_registry",
        lambda _db_profile_id: ObjectDepthRegistry(),
    )
    scenario = _scenario("p31_adversarial_depth_planner_blocked")
    response = MetadataAnalysisService(
        model_gateway=FakeModelGateway(
            tool_plan_by_target_ref={"dbo.TB_ORDER": scenario["planner_output"]}
        )
    ).analyze(MetadataAnalysisRequest.model_validate(scenario["request"]))
    payload = response.to_response()

    blocked_codes = {
        item["code"] for item in payload["aiToolEvidence"].get("blockedRequests", [])
    }
    assert scenario["expected"]["requiredBlockedCode"] in blocked_codes
    serialized = json.dumps(payload, sort_keys=True)
    for fragment in scenario["expected"]["forbiddenFragments"]:
        assert fragment.lower() not in serialized.lower()


def _fixture() -> dict[str, Any]:
    return yaml.safe_load(FIXTURE.read_text(encoding="utf-8"))


def _scenario(fixture_id: str) -> dict[str, Any]:
    for scenario in _fixture()["scenarios"]:
        if scenario["fixture_id"] == fixture_id:
            return scenario
    raise AssertionError(f"missing scenario: {fixture_id}")
