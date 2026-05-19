from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from ai_agent_runtime import FakeModelGateway
from ai_agent_runtime.models import AgentRunStatus, ModelInvocationRecord, stable_json_hash
from api_app.metadata_analysis_service import MetadataAnalysisService
from api_app.metadata_design_runs import execute_metadata_design_run
from api_app.metadata_design_service import MetadataDesignChatService
from api_app.recovery_worker import run_recovery_once
from api_app.schemas import MetadataDesignRunRequest

from tests.unit.api.fake_repository import MemoryWorkflowRepository


class DesignSpyRegistry:
    def __init__(self, *, empty: bool = False) -> None:
        self.empty = empty
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def invoke_payload(self, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        self.calls.append((tool_name, payload))
        evidence_id = f"mcp.{tool_name}.fixture"
        data = self._data_for(tool_name, payload["arguments"])
        return {
            "ok": True,
            "toolName": tool_name,
            "dbProfileId": payload["arguments"]["dbProfileId"],
            "snapshotId": "design-snapshot-1",
            "collectedAt": "2026-05-17T00:00:00Z",
            "evidenceRefs": [
                {
                    "id": evidence_id,
                    "source": "fixture",
                    "path": f"fixtures/mcp/design_snapshot.json#/{tool_name}",
                    "objectType": "METADATA",
                    "objectName": "dbo.PPM_CUSTOMER_ORDER",
                }
            ],
            "data": data,
        }

    def _data_for(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if self.empty:
            return {"candidates": [], "columns": []}
        if tool_name == "search_tables":
            return {
                "candidates": [
                    {
                        "schema": "dbo",
                        "tableName": "PPM_CUSTOMER_ORDER",
                        "logicalName": "customer order",
                        "description": "Customer order request table.",
                        "score": 92,
                    }
                ]
            }
        if tool_name == "find_similar_tables":
            return {
                "candidates": [
                    {
                        "schema": "dbo",
                        "tableName": "PPM_ORDER_REQ",
                        "logicalName": "order request",
                        "description": "Similar order request metadata.",
                        "score": 87,
                    }
                ]
            }
        if tool_name == "get_table_schema":
            return {
                "schema": "dbo",
                "tableName": str(arguments.get("tableName") or "PPM_CUSTOMER_ORDER"),
                "columns": [
                    {
                        "name": "CUSTOMER_NM",
                        "dataType": "VARCHAR(100)",
                        "nullable": False,
                        "description": "Customer name.",
                    },
                    {
                        "name": "ORDER_DT",
                        "dataType": "VARCHAR(8)",
                        "nullable": True,
                        "description": "Order date.",
                    },
                    {
                        "name": "RAW_DEFINITION_SHOULD_NOT_LEAK",
                        "definition": "CREATE PROCEDURE dbo.leak AS SELECT * FROM x",
                        "rowData": [{"secret": "do-not-return"}],
                    },
                ],
            }
        if tool_name == "search_columns":
            text = " ".join(
                str(arguments.get(key) or "").lower()
                for key in ("physicalName", "logicalName", "description")
            )
            if "customer" in text:
                column = {
                    "schema": "dbo",
                    "tableName": "PPM_CUSTOMER_ORDER",
                    "columnName": "CUSTOMER_NM",
                    "logicalName": "customer name",
                    "description": "Customer name.",
                    "dataType": "VARCHAR(100)",
                    "score": 96,
                }
            else:
                column = {
                    "schema": "dbo",
                    "tableName": "PPM_CUSTOMER_ORDER",
                    "columnName": "ORDER_DT",
                    "logicalName": "order date",
                    "description": "Order date.",
                    "dataType": "VARCHAR(8)",
                    "score": 93,
                }
            return {"candidates": [column]}
        return {"candidates": []}


class ContractReferenceDesignRegistry:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def invoke_payload(self, tool_name: str, payload: dict[str, Any]) -> dict[str, Any]:
        arguments = payload["arguments"]
        self.calls.append((tool_name, arguments))
        data = self._data_for(tool_name, arguments)
        return {
            "ok": True,
            "toolName": tool_name,
            "dbProfileId": arguments["dbProfileId"],
            "snapshotId": "contract-reference-design-snapshot-1",
            "collectedAt": "2026-05-19T00:00:00Z",
            "evidenceRefs": [
                {
                    "id": f"mcp.{tool_name}.contract_reference",
                    "source": "fixture",
                    "path": f"fixtures/mcp/contract_reference_design.json#/{tool_name}",
                    "objectType": "METADATA",
                    "objectName": "dbo.PEM_CTRT",
                }
            ],
            "data": data,
        }

    def _data_for(self, tool_name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if tool_name == "search_tables":
            table_name = str(arguments.get("physicalName") or "").upper()
            if table_name in {"PCS_CTRT", "PEM_CTRT"}:
                return {
                    "candidates": [
                        {
                            "schema": "dbo",
                            "tableName": table_name,
                            "logicalName": "contract reference",
                            "description": "Contract reference metadata.",
                            "score": 95,
                        }
                    ]
                }
            return {"candidates": []}
        if tool_name == "get_table_schema":
            table_name = str(arguments.get("tableName") or "").upper()
            columns = [
                {
                    "name": "CTRT_NO",
                    "dataType": "VARCHAR(50)",
                    "nullable": False,
                    "description": "계약번호",
                },
                {
                    "name": "ORDR_NO",
                    "dataType": "VARCHAR(50)",
                    "nullable": False,
                    "description": "주문번호",
                },
                {
                    "name": "CTRT_NM",
                    "dataType": "VARCHAR(400)",
                    "nullable": True,
                    "description": "계약명",
                },
                {
                    "name": "CTRT_CHG_SEQ_NO",
                    "dataType": "INT",
                    "nullable": False,
                    "description": "계약변경차수",
                },
                {
                    "name": "CTRT_TP_CD",
                    "dataType": "VARCHAR(20)",
                    "nullable": True,
                    "description": "계약종류코드",
                },
                {
                    "name": "CRE_USR_ID",
                    "dataType": "UNIQUEIDENTIFIER",
                    "nullable": False,
                    "description": "등록 사용자 ID",
                },
                {
                    "name": "CRE_DTM",
                    "dataType": "DATETIME2(3)",
                    "nullable": False,
                    "description": "등록 일시",
                },
                {
                    "name": "UPD_USR_ID",
                    "dataType": "UNIQUEIDENTIFIER",
                    "nullable": False,
                    "description": "수정 사용자 ID",
                },
                {
                    "name": "UPD_DTM",
                    "dataType": "DATETIME2(3)",
                    "nullable": False,
                    "description": "수정 일시",
                },
            ]
            if table_name == "PEM_CTRT":
                columns.append(
                    {
                        "name": "PREV_AUDT_YN",
                        "dataType": "VARCHAR(1)",
                        "nullable": True,
                        "description": "사전감사 여부",
                    }
                )
            return {"schema": "dbo", "tableName": table_name, "columns": columns}
        if tool_name == "search_columns":
            lookup = {
                "CTRT_NO": ("CTRT_NO", "계약번호", "VARCHAR(50)", 97),
                "CTRT_NM": ("CTRT_NM", "계약명", "VARCHAR(400)", 96),
                "ORDR_NO": ("ORDR_NO", "주문번호", "VARCHAR(50)", 96),
                "CTRT_CHG_SEQ_NO": ("CTRT_CHG_SEQ_NO", "계약변경차수", "INT", 95),
                "CTRT_TP_CD": ("CTRT_TP_CD", "계약종류코드", "VARCHAR(20)", 95),
                "PREV_AUDT_YN": ("PREV_AUDT_YN", "사전감사 여부", "VARCHAR(1)", 94),
            }
            requested = str(arguments.get("physicalName") or "").upper()
            if requested in lookup:
                column_name, description, data_type, score = lookup[requested]
                return {
                    "candidates": [
                        {
                            "schema": "dbo",
                            "tableName": "PEM_CTRT",
                            "columnName": column_name,
                            "logicalName": description,
                            "description": description,
                            "dataType": data_type,
                            "score": score,
                        }
                    ]
                }
            return {
                "candidates": [
                    {
                        "schema": "dbo",
                        "tableName": "PEM_CTRT",
                        "columnName": "FIELD_VAL",
                        "logicalName": "Unconfirmed value",
                        "description": "Unconfirmed value",
                        "dataType": "VARCHAR(500)",
                        "score": 40,
                    }
                ]
            }
        if tool_name == "find_similar_tables":
            return {
                "candidates": [
                    {
                        "schema": "dbo",
                        "tableName": "PEM_CTRT",
                        "logicalName": "contract",
                        "description": "Similar contract metadata.",
                        "score": 88,
                    }
                ]
            }
        return {"candidates": []}


@pytest.fixture(autouse=True)
def metadata_design_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("P21_LIVE_PORTAL_GATE", "0")
    monkeypatch.setenv("MSSQL_ENABLE_LIVE_METADATA", "0")
    monkeypatch.setenv("LLM_ENABLE_REMOTE", "0")


def test_metadata_design_builds_table_script_and_dto_from_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = DesignSpyRegistry()
    monkeypatch.setattr(
        "api_app.metadata_design_service._build_internal_registry",
        lambda _db_profile_id: registry,
    )
    service = MetadataDesignChatService(model_gateway=FakeModelGateway())

    response = service.design(
        MetadataDesignRunRequest.model_validate(
            {
                "dbProfileId": "master",
                "message": "Create a customer order table.",
                "designInputs": {
                    "tableNameHint": "PPM_CUSTOMER_ORDER",
                    "tableDescription": "Customer order request table.",
                    "fields": [
                        {
                            "name": "customer name",
                            "description": "Customer name",
                        },
                        {
                            "name": "order date",
                            "description": "Order date",
                        },
                    ],
                },
                "options": {
                    "llmProfileId": "openai_fast_test",
                    "maxCandidates": 3,
                    "generateDtoDraft": True,
                },
            }
        )
    ).to_response()

    assert [call[0] for call in registry.calls] == [
        "search_tables",
        "search_columns",
        "search_columns",
        "find_similar_tables",
        "get_table_schema",
    ]
    assert response["tableProposal"]["tableName"] == "PPM_CUSTOMER_ORDER"
    assert "CREATE TABLE [dbo].[PPM_CUSTOMER_ORDER]" in response["tableProposal"][
        "createTableScriptPreview"
    ]
    assert "[CUSTOMER_NM] VARCHAR(100)" in response["tableProposal"][
        "createTableScriptPreview"
    ]
    assert response["dtoDraft"]["artifactType"] == "DTO_DRAFT"
    assert response["dtoDraft"]["fileName"] == "PpmCustomerOrderDto.java"
    assert "public class PpmCustomerOrderDto" in response["dtoDraft"]["content"]
    assert "private String customerNm;" in response["dtoDraft"]["content"]
    assert response["interpretedIntent"]["intent"] == "CREATE_TABLE"
    assert response["appliedChanges"][0]["action"] == "ADD_FIELD"
    assert response["relatedMetadata"]
    assert response["standardizationMappings"][0]["source"] == "METADATA"
    assert response["reviewRequired"] is True
    assert any(
        ref.startswith("mcp.search_columns") or ref.startswith("mcp.get_table_schema")
        for ref in response["tableProposal"]["evidenceRefs"]
    )
    serialized = str(response).lower()
    for forbidden in ("rowdata", "row_data", "create procedure", "do-not-return"):
        assert forbidden not in serialized


def test_metadata_design_no_candidates_uses_policy_with_review_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = DesignSpyRegistry(empty=True)
    monkeypatch.setattr(
        "api_app.metadata_design_service._build_internal_registry",
        lambda _db_profile_id: registry,
    )
    service = MetadataDesignChatService(model_gateway=FakeModelGateway())

    response = service.design(
        MetadataDesignRunRequest.model_validate(
            {
                "dbProfileId": "master",
                "message": "Unknown business field",
                "designInputs": {
                    "fields": [
                        {
                            "description": "Unconfirmed external value",
                        }
                    ],
                },
                "options": {
                    "useLlmAnalysis": False,
                    "generateDtoDraft": True,
                },
            }
        )
    ).to_response()

    assert response["standardizationMappings"][0]["source"] == "REVIEW_REQUIRED"
    assert response["standardizationMappings"][0]["reviewRequired"] is True
    assert response["tableProposal"]["reviewRequired"] is True
    assert "REVIEW_REQUIRED" in response["tableProposal"]["createTableScriptPreview"]
    assert response["dtoDraft"]["reviewRequired"] is True
    assert "METADATA_DESIGN_NO_SIMILAR_METADATA" in response["caveats"]


def test_metadata_design_planner_prompt_metadata_includes_allowed_tool_names(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class CapturingPlannerGateway:
        def __init__(self) -> None:
            self.captured_prompt = None

        def plan_metadata_tools(self, *, prompt, profile) -> ModelInvocationRecord:
            self.captured_prompt = prompt
            structured_output = {
                "toolRequests": [],
                "assumptions": [],
                "reviewMarkers": [],
            }
            return ModelInvocationRecord(
                provider="capture",
                model=profile.model,
                model_profile_id=profile.profile_id,
                model_registry_ref=profile.registry_ref,
                reasoning_effort=profile.reasoning_effort,
                prompt_version=prompt.prompt_version,
                output_schema_version=prompt.output_schema_version,
                input_hash=prompt.input_hash,
                prompt_hash=prompt.prompt_hash,
                output_hash=stable_json_hash(structured_output),
                status=AgentRunStatus.SUCCEEDED,
                structured_output=structured_output,
            )

    registry = DesignSpyRegistry(empty=True)
    monkeypatch.setattr(
        "api_app.metadata_design_service._build_internal_registry",
        lambda _db_profile_id: registry,
    )
    gateway = CapturingPlannerGateway()
    service = MetadataDesignChatService(model_gateway=gateway)

    service.design(
        MetadataDesignRunRequest.model_validate(
            {
                "dbProfileId": "master",
                "message": "Create a customer order table.",
                "designInputs": {"tableNameHint": "PPM_CUSTOMER_ORDER"},
                "options": {
                    "useLlmAnalysis": True,
                    "useAiToolOrchestration": True,
                    "llmProfileId": "openai_fast_test",
                },
            }
        )
    )

    expected_tools = [
        "search_columns",
        "search_tables",
        "find_similar_tables",
        "get_table_schema",
    ]
    assert gateway.captured_prompt is not None
    assert gateway.captured_prompt.metadata["toolNames"] == expected_tools
    payload = json.loads(gateway.captured_prompt.user_prompt)
    assert payload["allowedTools"] == expected_tools


def test_metadata_design_extracts_korean_natural_language_fields(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = DesignSpyRegistry(empty=True)
    monkeypatch.setattr(
        "api_app.metadata_design_service._build_internal_registry",
        lambda _db_profile_id: registry,
    )
    service = MetadataDesignChatService(model_gateway=FakeModelGateway())

    response = service.design(
        MetadataDesignRunRequest.model_validate(
            {
                "dbProfileId": "master",
                "message": "고객명, 주소, 주문일이 있는 주문 요청 테이블을 만들어줘.",
                "options": {"useLlmAnalysis": False, "generateDtoDraft": True},
            }
        )
    ).to_response()

    intent = response["interpretedIntent"]
    assert intent["intent"] == "CREATE_TABLE"
    assert intent["tableNameCandidate"] == "PPM_ORDER_REQ"
    assert [field["name"] for field in intent["fields"]] == [
        "CUSTOMER_NM",
        "ADDR",
        "ORDER_DT",
    ]
    assert response["tableProposal"]["tableName"] == "PPM_ORDER_REQ"
    assert "[CUSTOMER_NM]" in response["tableProposal"]["createTableScriptPreview"]
    assert "[ORDER_DT]" in response["tableProposal"]["createTableScriptPreview"]
    assert response["dtoDraft"]["artifactType"] == "DTO_DRAFT"


def test_metadata_design_korean_reference_scope_uses_metadata_and_policy(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = ContractReferenceDesignRegistry()
    monkeypatch.setattr(
        "api_app.metadata_design_service._build_internal_registry",
        lambda _db_profile_id: registry,
    )
    service = MetadataDesignChatService(model_gateway=FakeModelGateway())

    response = service.design(
        MetadataDesignRunRequest.model_validate(
            {
                "dbProfileId": "master",
                "message": (
                    "테이블 명은 PCO_사전감사야. 안에 들어가는 필드는 "
                    "계약번호, 주문번호, 계약변경차수, 사전감사YN 야."
                ),
                "designInputs": {
                    "tableNameHint": "dbo.PCS_CTRT, dbo.PEM_CTRT",
                },
                "options": {
                    "useLlmAnalysis": False,
                    "generateDtoDraft": True,
                },
            }
        )
    ).to_response()

    intent = response["interpretedIntent"]
    assert intent["tableNameCandidate"] == "PCO_PREV_AUDT"
    assert [field["name"] for field in intent["fields"]] == [
        "CTRT_NO",
        "ORDR_NO",
        "CTRT_CHG_SEQ_NO",
        "PREV_AUDT_YN",
    ]
    assert {change["target"] for change in response["appliedChanges"]} >= {
        "CTRT_NO",
        "ORDR_NO",
        "CTRT_CHG_SEQ_NO",
        "PREV_AUDT_YN",
    }
    assert response["tableProposal"]["tableName"] == "PCO_PREV_AUDT"
    assert response["tableProposal"]["tableName"] != "DBO_PCS_CTRT_DBO_PEM_CTRT"

    columns = {
        column["name"]: column["dataType"]
        for column in response["tableProposal"]["columns"]
    }
    assert columns["CTRT_NO"] == "VARCHAR(50)"
    assert columns["ORDR_NO"] == "VARCHAR(50)"
    assert columns["CTRT_CHG_SEQ_NO"] == "INT"
    assert columns["PREV_AUDT_YN"] == "VARCHAR(1)"
    assert not any(name.startswith("FIELD_") and name.endswith("_VAL") for name in columns)

    search_column_calls = [
        arguments for tool_name, arguments in registry.calls if tool_name == "search_columns"
    ]
    assert search_column_calls
    assert all("," not in str(arguments.get("tableName") or "") for arguments in search_column_calls)
    schema_calls = [
        arguments for tool_name, arguments in registry.calls if tool_name == "get_table_schema"
    ]
    assert {(call["schema"], call["tableName"]) for call in schema_calls} >= {
        ("DBO", "PCS_CTRT"),
        ("DBO", "PEM_CTRT"),
    }
    assert response["reviewRequired"] is True


def test_metadata_design_quoted_korean_field_list_keeps_notification_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = ContractReferenceDesignRegistry()
    monkeypatch.setattr(
        "api_app.metadata_design_service._build_internal_registry",
        lambda _db_profile_id: registry,
    )
    service = MetadataDesignChatService(model_gateway=FakeModelGateway())

    response = service.design(
        MetadataDesignRunRequest.model_validate(
            {
                "dbProfileId": "master",
                "message": (
                    '테이블 명은 "PCO_사전감사_알림" 이야. 필드로 '
                    '"계약번호, 계약명, 주문번호, 계약금액, 계약유형, 알림여부, 알림내용" '
                    "이 들어가."
                ),
                "designInputs": {
                    "tableNameHint": "PCS_CTRT, PEM_CTRT",
                },
                "options": {
                    "useLlmAnalysis": False,
                    "generateDtoDraft": True,
                },
            }
        )
    ).to_response()

    intent_field_names = [field["name"] for field in response["interpretedIntent"]["fields"]]
    assert intent_field_names == [
        "CTRT_NO",
        "CTRT_NM",
        "ORDR_NO",
        "CTRT_AMT",
        "CTRT_TP_CD",
        "NTC_YN",
        "NTC_CNTNT",
    ]
    assert all('" 이 들어' not in field["name"] for field in response["interpretedIntent"]["fields"])

    columns = {
        column["name"]: column
        for column in response["tableProposal"]["columns"]
    }
    assert {"CTRT_TP_CD", "NTC_YN", "NTC_CNTNT"} <= set(columns)
    assert columns["CTRT_TP_CD"]["source"] == "METADATA"
    assert columns["CTRT_TP_CD"]["dataType"] == "VARCHAR(20)"
    assert columns["NTC_YN"]["dataType"] == "VARCHAR(1)"
    assert columns["NTC_CNTNT"]["dataType"] == "VARCHAR(2000)"
    assert columns["NTC_CNTNT"]["reviewRequired"] is True

    script = response["tableProposal"]["createTableScriptPreview"]
    assert '" 이 들어' not in script
    assert "UNCONFIRMED_5_VAL" not in script
    assert "UNCONFIRMED_7_VAL" not in script
    assert "[CTRT_TP_CD] VARCHAR(20)" in script
    assert "[NTC_CNTNT] VARCHAR(2000)" in script


def test_metadata_design_preserves_amount_fields_common_metadata_and_description_sql(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = ContractReferenceDesignRegistry()
    monkeypatch.setattr(
        "api_app.metadata_design_service._build_internal_registry",
        lambda _db_profile_id: registry,
    )
    service = MetadataDesignChatService(model_gateway=FakeModelGateway())

    response = service.design(
        MetadataDesignRunRequest.model_validate(
            {
                "dbProfileId": "master",
                "message": "PCS_CTRT 계약번호, 계약금액, 테스트금액",
                "designInputs": {
                    "tableNameHint": "dbo.PCS_CTRT",
                    "tableDescription": "PCS_CTRT O'Brien request",
                },
                "options": {
                    "useLlmAnalysis": False,
                    "generateDtoDraft": True,
                },
            }
        )
    ).to_response()

    columns = {
        column["name"]: column
        for column in response["tableProposal"]["columns"]
    }
    assert {"CTRT_NO", "CTRT_AMT", "TEST_AMT"} <= set(columns)
    assert columns["CTRT_AMT"]["dataType"] == "NUMERIC(18,3)"
    assert columns["TEST_AMT"]["dataType"] == "NUMERIC(18,3)"
    assert columns["CTRT_AMT"]["reviewRequired"] is True
    assert columns["TEST_AMT"]["reviewRequired"] is True
    assert any(
        "TEST" in reason
        for reason in columns["TEST_AMT"]["reviewReasons"]
    )
    assert columns["UPD_DTM"]["dataType"] == "DATETIME2(3)"
    assert columns["UPD_DTM"]["source"] == "METADATA"

    script = response["tableProposal"]["createTableScriptPreview"]
    assert "FIELD_1_VAL" not in script
    assert "REVIEW_REQUIRED_FIELD" not in script
    assert "[CTRT_AMT] NUMERIC(18,3)" in script
    assert "[TEST_AMT] NUMERIC(18,3)" in script
    assert "EXEC sys.sp_addextendedproperty" in script
    assert "@name = N'MS_Description'" in script
    assert "@value = N'PCS_CTRT O''Brien request'" in script
    assert "@level2type = N'COLUMN'" in script
    assert "@level2name = N'TEST_AMT'" in script
    assert "-- REVIEW_REQUIRED: [TEST_AMT]" in script


def test_metadata_design_refine_current_applies_latest_successful_baseline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = DesignSpyRegistry(empty=True)
    monkeypatch.setattr(
        "api_app.metadata_design_service._build_internal_registry",
        lambda _db_profile_id: registry,
    )
    repository = MemoryWorkflowRepository()
    repository.create_metadata_design_run(
        run_id="metadata_design_run_baseline",
        conversation_id="metadata_design_conv_refine",
        request={
            "dbProfileId": "master",
            "message": "고객명, 주소, 주문일이 있는 주문 요청 테이블",
            "conversationId": "metadata_design_conv_refine",
        },
    )
    repository.mark_metadata_design_run_succeeded(
        "metadata_design_run_baseline",
        result={
            "assistantMessage": "baseline",
            "tableProposal": {
                "schema": "dbo",
                "tableName": "PPM_ORDER_REQ",
                "tableDescription": "Order request table",
                "columns": [
                    {
                        "name": "CUSTOMER_NM",
                        "dataType": "VARCHAR(100)",
                        "nullable": True,
                        "description": "Customer name",
                        "source": "STANDARD_POLICY",
                        "evidenceRefs": ["policy:fixture"],
                        "reviewRequired": True,
                        "reviewReasons": ["REVIEW_REQUIRED: fixture"],
                    },
                    {
                        "name": "ADDR",
                        "dataType": "VARCHAR(500)",
                        "nullable": True,
                        "description": "Address",
                        "source": "STANDARD_POLICY",
                        "evidenceRefs": ["policy:fixture"],
                        "reviewRequired": True,
                        "reviewReasons": ["REVIEW_REQUIRED: fixture"],
                    },
                    {
                        "name": "ORDER_DT",
                        "dataType": "VARCHAR(500)",
                        "nullable": True,
                        "description": "Order date",
                        "source": "STANDARD_POLICY",
                        "evidenceRefs": ["policy:fixture"],
                        "reviewRequired": True,
                        "reviewReasons": ["REVIEW_REQUIRED: fixture"],
                    },
                ],
                "createTableScriptPreview": "-- baseline",
                "evidenceRefs": ["policy:fixture"],
                "reviewRequired": True,
                "reviewReasons": ["REVIEW_REQUIRED: fixture"],
            },
        },
    )
    service = MetadataDesignChatService(
        model_gateway=FakeModelGateway(),
        repository=repository,
    )

    response = service.design(
        MetadataDesignRunRequest.model_validate(
            {
                "dbProfileId": "master",
                "message": "배송메모 추가하고, 주문일은 날짜 타입으로 바꿔줘.",
                "conversationId": "metadata_design_conv_refine",
                "options": {
                    "conversationMode": "REFINE_CURRENT",
                    "useLlmAnalysis": False,
                    "generateDtoDraft": True,
                },
            }
        )
    ).to_response()

    columns = {
        column["name"]: column["dataType"]
        for column in response["tableProposal"]["columns"]
    }
    assert response["interpretedIntent"]["intent"] == "REFINE_TABLE"
    assert {"ADD_FIELD", "CHANGE_TYPE"} <= {
        change["action"] for change in response["appliedChanges"]
    }
    assert columns["DLV_MEMO"] == "VARCHAR(500)"
    assert columns["ORDER_DT"] == "VARCHAR(8)"
    assert "METADATA_DESIGN_REFINE_BASELINE_REQUIRED" not in response["caveats"]


def test_metadata_design_refine_current_without_baseline_marks_review_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = DesignSpyRegistry(empty=True)
    monkeypatch.setattr(
        "api_app.metadata_design_service._build_internal_registry",
        lambda _db_profile_id: registry,
    )
    service = MetadataDesignChatService(
        model_gateway=FakeModelGateway(),
        repository=MemoryWorkflowRepository(),
    )

    response = service.design(
        MetadataDesignRunRequest.model_validate(
            {
                "dbProfileId": "master",
                "message": "배송메모 추가",
                "conversationId": "metadata_design_conv_missing",
                "options": {
                    "conversationMode": "REFINE_CURRENT",
                    "useLlmAnalysis": False,
                },
            }
        )
    ).to_response()

    assert "METADATA_DESIGN_REFINE_BASELINE_REQUIRED" in response["caveats"]
    assert response["appliedChanges"][0]["reviewRequired"] is True
    assert response["reviewRequired"] is True


def test_metadata_design_redacts_secret_like_input_from_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = DesignSpyRegistry(empty=True)
    monkeypatch.setattr(
        "api_app.metadata_design_service._build_internal_registry",
        lambda _db_profile_id: registry,
    )
    service = MetadataDesignChatService(model_gateway=FakeModelGateway())

    response = service.design(
        MetadataDesignRunRequest.model_validate(
            {
                "dbProfileId": "master",
                "message": "password=do-not-return raw prompt select * from dbo.secret",
                "designInputs": {
                    "fields": [
                        {
                            "name": "api token",
                            "description": "secret value",
                        }
                    ],
                },
                "options": {"llmProfileId": "openai_fast_test"},
            }
        )
    ).to_response()

    serialized = str(response).lower()
    for forbidden in (
        "do-not-return",
        "raw prompt",
        "api token",
        "secret value",
        "select *",
    ):
        assert forbidden not in serialized
    assert "redacted_review_required" in serialized


def test_metadata_design_repository_claims_conversation_runs_and_recovers_stale() -> None:
    repository = MemoryWorkflowRepository()
    stale_before = datetime.now(UTC) - timedelta(seconds=60)
    created = repository.create_metadata_design_run(
        run_id="metadata_design_run_contract",
        conversation_id="metadata_design_conv_contract",
        request={
            "dbProfileId": "master",
            "message": "customer name",
            "conversationId": "metadata_design_conv_contract",
        },
    )

    listed = repository.list_metadata_design_runs_for_conversation(
        created.conversation_id,
        limit=5,
    )
    claimed = repository.claim_metadata_design_run(
        created.run_id,
        stale_before=stale_before,
    )
    second_claim = repository.claim_metadata_design_run(
        created.run_id,
        stale_before=stale_before,
    )
    repository.mark_metadata_design_run_succeeded(
        created.run_id,
        result={
            "assistantMessage": "done",
            "tableProposal": {
                "schema": "dbo",
                "tableName": "PPM_CUSTOMER_ORDER",
                "columns": [],
                "createTableScriptPreview": "-- preview",
            },
        },
    )

    assert listed[0].run_id == created.run_id
    assert claimed is not None
    assert claimed.status == "RUNNING"
    assert second_claim is None
    assert repository.get_metadata_design_run(created.run_id).status == "SUCCEEDED"
    assert repository.list_recoverable_metadata_design_runs(
        stale_before=datetime.now(UTC),
        limit=5,
    ) == []


def test_metadata_design_execute_skips_non_stale_running_claim() -> None:
    repository = MemoryWorkflowRepository()
    service = MetadataDesignChatService(model_gateway=FakeModelGateway())
    created = repository.create_metadata_design_run(
        run_id="metadata_design_run_claimed_elsewhere",
        conversation_id="metadata_design_conv_claimed_elsewhere",
        request={
            "dbProfileId": "master",
            "message": "customer name",
            "conversationId": "metadata_design_conv_claimed_elsewhere",
        },
    )
    repository.mark_metadata_design_run_running(created.run_id)

    claimed = execute_metadata_design_run(
        run_id=created.run_id,
        request=None,
        service=service,
        repository=repository,
    )

    assert claimed is False
    assert repository.get_metadata_design_run(created.run_id).status == "RUNNING"


def test_recovery_worker_processes_queued_metadata_design_run(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registry = DesignSpyRegistry()
    monkeypatch.setattr(
        "api_app.metadata_design_service._build_internal_registry",
        lambda _db_profile_id: registry,
    )
    repository = MemoryWorkflowRepository()
    created = repository.create_metadata_design_run(
        run_id="metadata_design_run_worker_queued",
        conversation_id="metadata_design_conv_worker",
        request={
            "dbProfileId": "master",
            "message": "customer name",
            "conversationId": "metadata_design_conv_worker",
            "designInputs": {
                "tableNameHint": "PPM_CUSTOMER_ORDER",
                "fields": [{"name": "customer name"}],
            },
            "options": {"llmProfileId": "openai_fast_test"},
        },
    )

    report = run_recovery_once(
        repository=repository,
        metadata_service=MetadataAnalysisService(),
        metadata_design_service=MetadataDesignChatService(
            model_gateway=FakeModelGateway()
        ),
        batch_size=5,
    )
    record = repository.get_metadata_design_run(created.run_id)

    assert report.metadata_design_runs_claimed == 1
    assert report.errors == ()
    assert record is not None
    assert record.status == "SUCCEEDED"
    assert record.result["dtoDraft"]["artifactType"] == "DTO_DRAFT"
