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

from tests.unit.api.fake_repository import MemoryWorkflowRepository

ROOT = Path(__file__).resolve().parents[2]
CONTRACT = ROOT / "spec" / "eval" / "p40_metadata_design_natural_language_chat_contract.yaml"
FIXTURE = ROOT / "fixtures" / "eval" / "metadata_design_natural_language_chat_p40_v1.yaml"
FORBIDDEN_DTO_PACKAGE_FRAGMENTS = ("com.example", "org.example", "example.")


def _assert_metadata_dto_package(content: str) -> None:
    assert f"package {METADATA_DESIGN_DTO_DRAFT_PACKAGE};" in content
    for forbidden in FORBIDDEN_DTO_PACKAGE_FRAGMENTS:
        assert forbidden not in content


class P40EvalRegistry:
    def __init__(self, *, empty: bool = False) -> None:
        self.empty = empty

    def invoke_payload(self, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        arguments = payload["arguments"]
        if self.empty:
            data = {"candidates": [], "columns": []}
        elif tool_name == "search_tables":
            table_name = str(arguments.get("physicalName") or "").upper()
            if table_name in {"PCS_CTRT", "PEM_CTRT"}:
                data = {
                    "candidates": [
                        {
                            "schema": "dbo",
                            "tableName": table_name,
                            "description": "Contract reference table",
                            "score": 94,
                        }
                    ]
                }
            else:
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
                        "description": "Order request header",
                        "score": 95,
                    }
                ]
            }
        elif tool_name == "get_table_schema":
            table_name = str(arguments.get("tableName") or "PPM_ORDER_REQ").upper()
            if table_name in {"PCS_CTRT", "PEM_CTRT"}:
                data = {
                    "schema": "dbo",
                    "tableName": table_name,
                    "columns": [
                        {"name": "CTRT_NO", "dataType": "VARCHAR(50)", "description": "계약번호"},
                        {"name": "ORDR_NO", "dataType": "VARCHAR(50)", "description": "주문번호"},
                        {"name": "CTRT_CHG_SEQ_NO", "dataType": "INT", "description": "계약변경차수"},
                        {"name": "PREV_AUDT_YN", "dataType": "VARCHAR(1)", "description": "사전감사 여부"},
                    ],
                }
            else:
                data = {
                    "schema": "dbo",
                    "tableName": "PPM_ORDER_REQ",
                    "columns": [
                        {"name": "CUSTOMER_NM", "dataType": "VARCHAR(100)"},
                        {"name": "ADDR", "dataType": "VARCHAR(500)"},
                        {"name": "ORDER_DT", "dataType": "VARCHAR(8)"},
                    ],
                }
        else:
            lookup = {
                "CUSTOMER_NM": ("CUSTOMER_NM", "Customer name", "VARCHAR(100)", 96),
                "ADDR": ("ADDR", "Address", "VARCHAR(500)", 94),
                "ORDER_DT": ("ORDER_DT", "Order date", "VARCHAR(8)", 93),
                "DLV_MEMO": ("DLV_MEMO", "Delivery memo", "VARCHAR(500)", 90),
                "CTRT_NO": ("CTRT_NO", "계약번호", "VARCHAR(50)", 97),
                "ORDR_NO": ("ORDR_NO", "주문번호", "VARCHAR(50)", 96),
                "CTRT_CHG_SEQ_NO": ("CTRT_CHG_SEQ_NO", "계약변경차수", "INT", 95),
                "PREV_AUDT_YN": ("PREV_AUDT_YN", "사전감사 여부", "VARCHAR(1)", 94),
            }
            requested = str(arguments.get("physicalName") or "").upper()
            column_name, description, data_type, score = lookup.get(
                requested,
                ("FIELD_VAL", "Unconfirmed value", "VARCHAR(500)", 40),
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
            "snapshotId": "p40-eval-snapshot-1",
            "collectedAt": "2026-05-17T00:00:00Z",
            "evidenceRefs": [
                {
                    "id": f"mcp.{tool_name}.p40_eval",
                    "source": "fixture",
                    "path": f"fixtures/eval/metadata_design_natural_language_chat_p40_v1.yaml#/{tool_name}",
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


def test_p40_contract_and_fixture_are_aligned() -> None:
    contract = _yaml(CONTRACT)
    fixture = _yaml(FIXTURE)

    assert contract["contract_id"] == "p40_metadata_design_natural_language_chat"
    assert contract["production_ready"] is False
    assert fixture["scenario_id"] == "metadata_design_natural_language_chat_p40_v1"
    assert fixture["expected"]["tableScriptField"] == contract["result_contract"][
        "table_script_field"
    ]
    assert fixture["expected"]["dtoArtifactType"] == contract["result_contract"][
        "dto_preview_artifact_type"
    ]
    assert (
        contract["result_contract"]["dto_preview_package"]
        == METADATA_DESIGN_DTO_DRAFT_PACKAGE
    )
    assert contract["storage"]["no_new_ddl"] is True
    assert "REFINE_CURRENT" in contract["input_contract"]["conversation_modes"]


def test_p40_new_design_and_refine_eval_generate_chat_outputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fixture = _yaml(FIXTURE)
    monkeypatch.setattr(
        "api_app.metadata_design_service._build_internal_registry",
        lambda _db_profile_id: P40EvalRegistry(),
    )
    repository = MemoryWorkflowRepository()
    service = MetadataDesignChatService(
        model_gateway=FakeModelGateway(),
        repository=repository,
    )

    new_response = service.design(
        MetadataDesignRunRequest.model_validate(fixture["newDesignRequest"])
    ).to_response()
    _persist_successful_baseline(repository, new_response)

    refine_response = service.design(
        MetadataDesignRunRequest.model_validate(fixture["refineRequest"])
    ).to_response()
    reference_response = service.design(
        MetadataDesignRunRequest.model_validate(fixture["referenceDesignRequest"])
    ).to_response()

    expected = fixture["expected"]
    assert new_response["interpretedIntent"]["intent"] == "CREATE_TABLE"
    assert [field["name"] for field in new_response["interpretedIntent"]["fields"]] == (
        expected["newDesignFields"]
    )
    assert new_response["tableProposal"]["tableName"] == expected["tableName"]
    assert expected["tableScriptField"] in new_response["tableProposal"]
    assert new_response["dtoDraft"]["artifactType"] == expected["dtoArtifactType"]
    _assert_metadata_dto_package(new_response["dtoDraft"]["content"])
    assert refine_response["interpretedIntent"]["intent"] == "REFINE_TABLE"
    assert set(expected["requiredAppliedActions"]) <= {
        change["action"] for change in refine_response["appliedChanges"]
    }
    refine_columns = {
        column["name"]: column["dataType"]
        for column in refine_response["tableProposal"]["columns"]
    }
    assert "DLV_MEMO" in refine_columns
    assert refine_columns["ORDER_DT"] == "VARCHAR(8)"
    assert refine_response["dtoDraft"]["artifactType"] == "DTO_DRAFT"
    _assert_metadata_dto_package(refine_response["dtoDraft"]["content"])
    assert reference_response["interpretedIntent"]["intent"] == "CREATE_TABLE"
    assert reference_response["interpretedIntent"]["tableNameCandidate"] == expected[
        "referenceTableName"
    ]
    assert [
        field["name"] for field in reference_response["interpretedIntent"]["fields"]
    ] == expected["referenceDesignFields"]
    assert reference_response["tableProposal"]["tableName"] == expected[
        "referenceTableName"
    ]
    assert "DBO_PCS_CTRT_DBO_PEM_CTRT" not in reference_response["tableProposal"][
        "createTableScriptPreview"
    ]
    _assert_metadata_dto_package(reference_response["dtoDraft"]["content"])
    reference_columns = {
        column["name"]: column["dataType"]
        for column in reference_response["tableProposal"]["columns"]
    }
    assert "FIELD_1_VAL" not in reference_columns
    assert reference_columns["CTRT_NO"] == "VARCHAR(50)"
    assert reference_columns["PREV_AUDT_YN"] == "VARCHAR(1)"
    serialized = json.dumps(
        {"new": new_response, "refine": refine_response, "reference": reference_response},
        ensure_ascii=False,
        sort_keys=True,
    )
    for forbidden in expected["forbiddenFragments"]:
        assert forbidden not in serialized


def test_p40_no_metadata_fallback_keeps_review_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        "api_app.metadata_design_service._build_internal_registry",
        lambda _db_profile_id: P40EvalRegistry(empty=True),
    )
    service = MetadataDesignChatService(model_gateway=FakeModelGateway())

    response = service.design(
        MetadataDesignRunRequest.model_validate(
            {
                "dbProfileId": "master",
                "message": "희귀한 외부 정산 식별값 테이블을 만들어줘.",
                "options": {
                    "useLlmAnalysis": False,
                    "generateDtoDraft": True,
                    "conversationMode": "NEW_DESIGN",
                },
            }
        )
    ).to_response()

    assert response["reviewRequired"] is True
    assert "METADATA_DESIGN_NO_SIMILAR_METADATA" in response["caveats"]
    assert response["tableProposal"]["reviewRequired"] is True
    assert response["dtoDraft"]["reviewRequired"] is True
    _assert_metadata_dto_package(response["dtoDraft"]["content"])


def _persist_successful_baseline(
    repository: MemoryWorkflowRepository,
    result: dict[str, Any],
) -> None:
    repository.create_metadata_design_run(
        run_id="metadata_design_run_p40_eval_baseline",
        conversation_id="metadata_design_conv_p40_eval",
        request={
            "dbProfileId": "master",
            "message": "고객명, 주소, 주문일이 있는 주문 요청 테이블을 만들어줘.",
            "conversationId": "metadata_design_conv_p40_eval",
        },
    )
    repository.mark_metadata_design_run_succeeded(
        "metadata_design_run_p40_eval_baseline",
        result=result,
    )


def _yaml(path: Path) -> dict[str, Any]:
    return yaml.safe_load(path.read_text(encoding="utf-8"))
