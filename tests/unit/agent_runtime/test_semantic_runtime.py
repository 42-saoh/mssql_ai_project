from __future__ import annotations

from typing import Any

import pytest
from ai_agent_runtime import (
    FakeModelGateway,
    SemanticAnalysisTask,
    build_semantic_analysis_run,
    build_semantic_analysis_runs,
)
from ai_agent_runtime.gateway import model_profile_from_env
from ai_agent_runtime.models import (
    metadata_analysis_output_schema,
    metadata_tool_planning_output_schema,
    semantic_output_schema,
)
from ai_agent_runtime.prompts import (
    render_metadata_analysis_prompt,
    render_metadata_tool_planning_prompt,
    render_semantic_analysis_prompt,
)
from ai_agent_runtime.quality_eval import evaluate_p23_semantic_quality


@pytest.fixture(autouse=True)
def _default_openai_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_REMOTE_PROVIDER", raising=False)
    monkeypatch.delenv("PGPT_MODEL_ANALYSIS", raising=False)
    monkeypatch.delenv("PGPT_MODEL_FAST_TEST", raising=False)


def test_prompt_renderer_hashes_inputs_and_sanitizes_metadata_copy() -> None:
    prompt = render_semantic_analysis_prompt(
        target_ref="dbo.usp_Demo",
        metadata={
            "procedureDefinition": {
                "definition": "CREATE PROCEDURE dbo.usp_Demo AS SELECT 1",
                "definitionHash": "abc",
            }
        },
        static_analysis={"procedure": {"identifier": {"full_name": "dbo.usp_Demo"}}},
        procedure_definition="CREATE PROCEDURE dbo.usp_Demo AS SELECT 1",
    )

    assert len(prompt.input_hash) == 64
    assert len(prompt.prompt_hash) == 64
    assert "CREATE PROCEDURE dbo.usp_Demo" in prompt.user_prompt
    assert '"definitionHash": "abc"' in prompt.user_prompt


def test_fake_gateway_returns_schema_valid_sanitized_invocation(monkeypatch: Any) -> None:
    monkeypatch.delenv("OPENAI_MODEL_FAST_TEST", raising=False)
    prompt = render_semantic_analysis_prompt(
        target_ref="dbo.usp_Demo",
        metadata={"procedureDefinition": {"definitionHash": "abc"}},
        static_analysis=None,
        procedure_definition=None,
    )
    profile = model_profile_from_env("openai_fast_test")
    result = FakeModelGateway().invoke_semantic_analysis(prompt=prompt, profile=profile)

    assert result.model == "gpt-5-nano"
    assert result.model_profile_id == "openai_fast_test"
    assert result.status == "SUCCEEDED"
    assert "businessRules" in result.structured_output
    assert "CREATE PROCEDURE" not in str(result.to_storage_dict())


def test_fast_test_profile_defaults_to_gpt_5_nano(monkeypatch: Any) -> None:
    monkeypatch.delenv("OPENAI_MODEL_FAST_TEST", raising=False)

    profile = model_profile_from_env("openai_fast_test")

    assert profile.model == "gpt-5-nano"
    assert profile.profile_id == "openai_fast_test"
    assert profile.registry_ref == "model:openai_fast_test@gpt-5-nano@0.1.0"


def test_fast_test_profile_honors_model_env_override(monkeypatch: Any) -> None:
    monkeypatch.setenv("OPENAI_MODEL_FAST_TEST", "gpt-5.4-mini")

    profile = model_profile_from_env("openai_fast_test")

    assert profile.model == "gpt-5.4-mini"
    assert profile.profile_id == "openai_fast_test"
    assert profile.registry_ref == "model:openai_fast_test@gpt-5.4-mini@0.1.0"


def test_fake_gateway_can_return_fixture_output_by_target_ref(monkeypatch: Any) -> None:
    monkeypatch.setenv("OPENAI_MODEL_FAST_TEST", "gpt-5.4-mini")
    prompt = render_semantic_analysis_prompt(
        target_ref="dbo.usp_Demo",
        metadata={},
        static_analysis=None,
        procedure_definition=None,
    )
    profile = model_profile_from_env("openai_fast_test")
    result = FakeModelGateway(
        output_by_target_ref={
            "dbo.usp_Demo": {
                "businessRules": [
                    {
                        "category": "CUSTOM_FIXTURE_RULE",
                        "summary": "Fixture-provided output for deterministic eval.",
                        "status": "INFERRED_DESCRIPTION",
                        "evidenceRefs": ["fact_demo"],
                    }
                ],
                "modernizationPoints": [],
                "riskFlags": [],
                "reviewMarkers": [],
                "assumptions": [],
            }
        }
    ).invoke_semantic_analysis(prompt=prompt, profile=profile)

    assert result.structured_output["businessRules"][0]["category"] == "CUSTOM_FIXTURE_RULE"
    assert result.model == "gpt-5.4-mini"


def test_semantic_output_schema_is_strict_for_responses_api() -> None:
    schema = semantic_output_schema()

    assert schema["additionalProperties"] is False
    assert schema["required"] == [
        "businessRules",
        "modernizationPoints",
        "riskFlags",
        "reviewMarkers",
        "conversionGuidance",
        "migrationGuideInsights",
        "assumptions",
    ]
    business_rule_schema = schema["properties"]["businessRules"]["items"]
    assert business_rule_schema["additionalProperties"] is False
    assert business_rule_schema["required"] == [
        "category",
        "summary",
        "status",
        "evidenceRefs",
    ]
    assert business_rule_schema["properties"]["evidenceRefs"]["minItems"] == 1


def test_semantic_output_schema_can_constrain_fact_id_evidence_refs() -> None:
    schema = semantic_output_schema(
        allowed_evidence_refs=["fact_customer", "fact_status"],
    )
    evidence_items = schema["properties"]["businessRules"]["items"]["properties"][
        "evidenceRefs"
    ]["items"]

    assert evidence_items["enum"] == ["fact_customer", "fact_status"]


def test_metadata_tool_planner_prompt_and_schema_are_strict() -> None:
    prompt = render_metadata_tool_planning_prompt(
        target_ref="dbo.usp_Demo",
        metadata={
            "procedureDefinition": {
                "definition": "CREATE PROCEDURE dbo.usp_Demo AS SELECT 1",
                "definitionHash": "abc",
            }
        },
        static_analysis=None,
        tool_capabilities=[
            {
                "name": "get_table_schema",
                "description": "Return columns and data types for a table.",
                "inputSchema": {"type": "object"},
            }
        ],
    )
    schema = metadata_tool_planning_output_schema(tool_names=["get_table_schema"])

    assert '"definition":' not in prompt.user_prompt
    assert "CREATE PROCEDURE dbo.usp_Demo" not in prompt.user_prompt
    assert schema["additionalProperties"] is False
    assert schema["properties"]["toolRequests"]["items"]["additionalProperties"] is False
    assert (
        schema["properties"]["toolRequests"]["items"]["properties"]["toolName"]["enum"]
        == ["get_table_schema"]
    )


def test_fake_gateway_can_return_metadata_tool_plan(monkeypatch: Any) -> None:
    monkeypatch.delenv("OPENAI_MODEL_FAST_TEST", raising=False)
    prompt = render_metadata_tool_planning_prompt(
        target_ref="dbo.usp_Demo",
        metadata={},
        static_analysis=None,
        tool_capabilities=[
            {
                "name": "get_table_schema",
                "description": "Return columns and data types for a table.",
                "inputSchema": {"type": "object"},
            }
        ],
    )
    result = FakeModelGateway(
        tool_plan_by_target_ref={
            "dbo.usp_Demo": {
                "toolRequests": [
                    {
                        "toolName": "get_table_schema",
                        "arguments": {
                            "dbProfileId": "master",
                            "schema": "dbo",
                            "tableName": "TB_ORDER",
                        },
                        "reason": "Need column metadata.",
                        "expectedEvidenceUse": "Anchor DTO shape claims.",
                    }
                ],
                "assumptions": [],
                "reviewMarkers": [],
            }
        }
    ).plan_metadata_tools(prompt=prompt, profile=model_profile_from_env("openai_fast_test"))

    assert result.structured_output["toolRequests"][0]["toolName"] == "get_table_schema"
    assert result.output_schema_version == "schema:mssql_metadata_tool_plan@0.1.0"


def test_metadata_analysis_prompt_and_schema_are_strict() -> None:
    prompt = render_metadata_analysis_prompt(
        target_ref="dbo.TB_ORDER",
        metadata={
            "deterministicFacts": [
                {
                    "id": "mcp.get_table_schema.abc123",
                    "summary": "Table schema metadata.",
                }
            ],
            "aiToolEvidence": {
                "toolResults": [
                    {
                        "data": {
                            "definition": "CREATE VIEW dbo.vw_leak AS SELECT 1",
                            "rowData": [{"id": 1}],
                            "columns": [{"name": "ORDER_ID"}],
                        }
                    }
                ]
            },
        },
        allowed_evidence_refs=["mcp.get_table_schema.abc123"],
    )
    schema = metadata_analysis_output_schema(
        allowed_evidence_refs=["mcp.get_table_schema.abc123"],
    )

    assert "CREATE VIEW" not in prompt.user_prompt
    assert "rowData" not in prompt.user_prompt
    assert schema["additionalProperties"] is False
    assert schema["required"] == [
        "summary",
        "objectInsights",
        "insightGroups",
        "dtoReadiness",
        "reviewMarkers",
        "assumptions",
    ]
    evidence_items = schema["properties"]["objectInsights"]["items"]["properties"][
        "evidenceRefs"
    ]["items"]
    assert evidence_items["enum"] == ["mcp.get_table_schema.abc123"]


def test_fake_gateway_can_return_metadata_analysis(monkeypatch: Any) -> None:
    monkeypatch.delenv("OPENAI_MODEL_FAST_TEST", raising=False)
    prompt = render_metadata_analysis_prompt(
        target_ref="dbo.TB_ORDER",
        metadata={
            "deterministicFacts": [
                {
                    "id": "mcp.get_table_schema.abc123",
                    "summary": "Table schema metadata.",
                }
            ]
        },
        allowed_evidence_refs=["mcp.get_table_schema.abc123"],
    )
    result = FakeModelGateway().analyze_metadata(
        prompt=prompt,
        profile=model_profile_from_env("openai_fast_test"),
    )

    assert result.output_schema_version == "schema:mssql_metadata_analysis@0.1.0"
    assert result.structured_output["objectInsights"][0]["evidenceRefs"] == [
        "mcp.get_table_schema.abc123"
    ]
    assert result.structured_output["insightGroups"][0]["category"] == "DTO_READINESS"
    assert result.structured_output["dtoReadiness"][0]["evidenceRefs"] == [
        "mcp.get_table_schema.abc123"
    ]


def test_semantic_run_payload_excludes_raw_prompt_and_sql_from_storage(monkeypatch: Any) -> None:
    monkeypatch.delenv("OPENAI_MODEL_FAST_TEST", raising=False)
    payload = build_semantic_analysis_run(
        target_ref="dbo.usp_Demo",
        metadata={"procedureDefinition": {"definitionHash": "abc"}},
        static_analysis=None,
        procedure_definition="CREATE PROCEDURE dbo.usp_Demo AS SELECT 1",
        model_gateway=FakeModelGateway(),
        profile_id="openai_fast_test",
    )

    stored = payload.to_storage_dict()
    assert stored["modelInvocation"]["model"] == "gpt-5-nano"
    assert "prompt" not in stored["modelInvocation"]
    assert "CREATE PROCEDURE" not in str(stored)


def test_staged_semantic_run_repairs_invalid_evidence_refs(monkeypatch: Any) -> None:
    monkeypatch.delenv("OPENAI_MODEL_FAST_TEST", raising=False)
    payload = build_semantic_analysis_run(
        target_ref="dbo.usp_Demo",
        metadata={
            "deterministicFacts": [
                {"id": "fact_demo_parameters", "summary": "Demo input parameters."},
                {"id": "fact_demo_lookup", "summary": "Demo lookup behavior."},
            ]
        },
        static_analysis={"fact_ids": ["fact_demo_parameters", "fact_demo_lookup"]},
        procedure_definition=None,
        model_gateway=FakeModelGateway(
            output_by_target_ref={
                "dbo.usp_Demo": {
                    "businessRules": [
                        {
                            "category": "DEMO_LOOKUP",
                            "summary": "Demo lookup behavior.",
                            "status": "INFERRED_DESCRIPTION",
                            "evidenceRefs": ["prompt.inputHash", "not_a_fact"],
                        }
                    ],
                    "modernizationPoints": [],
                    "riskFlags": [],
                    "reviewMarkers": [],
                    "assumptions": [],
                }
            }
        ),
        profile_id="openai_fast_test",
    )

    item = payload.structured_output["businessRules"][0]
    assert set(item["evidenceRefs"]) <= {"fact_demo_parameters", "fact_demo_lookup"}
    assert item["evidenceRefs"]
    component_stages = [
        item["stage"]
        for item in payload.model_invocation.to_storage_dict()["componentInvocations"]
    ]
    assert component_stages[:5] == [
        "deterministic_evidence_digest",
        "business_rule_extraction",
        "conversion_readiness",
        "migration_guide_insights",
        "evidence_critic",
    ]


def test_complex_staged_run_injects_required_review_markers(monkeypatch: Any) -> None:
    monkeypatch.delenv("OPENAI_MODEL_FAST_TEST", raising=False)
    payload = build_semantic_analysis_run(
        target_ref="dbo.usp_Dynamic",
        metadata={
            "deterministicFacts": [
                {"id": "fact_dynamic_sql", "summary": "Dynamic SQL is present."},
                {"id": "fact_cross_db", "summary": "Cross database target is dynamic."},
                {"id": "fact_sp_executesql", "summary": "sys.sp_executesql is used."},
            ]
        },
        static_analysis={
            "fact_ids": ["fact_dynamic_sql", "fact_cross_db", "fact_sp_executesql"],
            "patterns": {
                "dynamic_sql": True,
                "cross_database_reference": True,
                "unsupported_dependency_claims_possible": True,
            },
        },
        procedure_definition=None,
        model_gateway=FakeModelGateway(
            output_by_target_ref={
                "dbo.usp_Dynamic": {
                    "businessRules": [],
                    "modernizationPoints": [],
                    "riskFlags": [],
                    "reviewMarkers": [],
                    "assumptions": [],
                }
            }
        ),
        profile_id="openai_fast_test",
    )

    markers = {
        marker["code"]: marker
        for marker in payload.structured_output["reviewMarkers"]
    }
    assert set(markers) >= {
        "UNSUPPORTED_TABLE_CLAIM_REVIEW",
        "UNSUPPORTED_FUNCTION_CLAIM_REVIEW",
        "UNSUPPORTED_PROCEDURE_CLAIM_REVIEW",
    }
    assert all(marker["status"] == "REVIEW_REQUIRED" for marker in markers.values())
    assert all(marker["evidenceRefs"] for marker in markers.values())


def test_semantic_tasks_can_run_as_independent_sp_units(monkeypatch: Any) -> None:
    monkeypatch.setenv("LLM_SP_CONCURRENCY", "2")

    runs = build_semantic_analysis_runs(
        tasks=[
            SemanticAnalysisTask(
                target_ref="dbo.usp_First",
                metadata={"deterministicFacts": [{"id": "fact_first"}]},
                static_analysis={"fact_ids": ["fact_first"]},
            ),
            SemanticAnalysisTask(
                target_ref="dbo.usp_Second",
                metadata={"deterministicFacts": [{"id": "fact_second"}]},
                static_analysis={"fact_ids": ["fact_second"]},
            ),
        ],
        model_gateway=FakeModelGateway(
            output_by_target_ref={
                "dbo.usp_First": {
                    "businessRules": [
                        {
                            "category": "FIRST",
                            "summary": "First SP.",
                            "status": "INFERRED_DESCRIPTION",
                            "evidenceRefs": ["fact_first"],
                        }
                    ],
                    "modernizationPoints": [],
                    "riskFlags": [],
                    "reviewMarkers": [],
                    "assumptions": [],
                },
                "dbo.usp_Second": {
                    "businessRules": [
                        {
                            "category": "SECOND",
                            "summary": "Second SP.",
                            "status": "INFERRED_DESCRIPTION",
                            "evidenceRefs": ["fact_second"],
                        }
                    ],
                    "modernizationPoints": [],
                    "riskFlags": [],
                    "reviewMarkers": [],
                    "assumptions": [],
                },
            }
        ),
        profile_id="openai_fast_test",
    )

    assert [run.target_ref for run in runs] == ["dbo.usp_First", "dbo.usp_Second"]


def test_staged_semantic_run_sanitizes_raw_sql_echo_before_storage(monkeypatch: Any) -> None:
    monkeypatch.delenv("OPENAI_MODEL_FAST_TEST", raising=False)
    procedure_definition = "CREATE PROCEDURE dbo.usp_Demo AS SELECT * FROM dbo.SecretOrders"

    payload = build_semantic_analysis_run(
        target_ref="dbo.usp_Demo",
        metadata={"deterministicFacts": [{"id": "fact_demo"}]},
        static_analysis={"fact_ids": ["fact_demo"]},
        procedure_definition=procedure_definition,
        model_gateway=FakeModelGateway(
            output_by_target_ref={
                "dbo.usp_Demo": {
                    "businessRules": [
                        {
                            "category": "DEMO_RULE",
                            "summary": procedure_definition,
                            "status": "INFERRED_DESCRIPTION",
                            "evidenceRefs": ["fact_demo"],
                        }
                    ],
                    "modernizationPoints": [],
                    "riskFlags": [
                        {
                            "code": "RAW_PROVIDER_ECHO",
                            "severity": "WARNING",
                            "summary": "raw_openai_response_text: provider echoed SQL",
                            "status": "REVIEW_REQUIRED",
                            "evidenceRefs": ["fact_demo"],
                        }
                    ],
                    "reviewMarkers": [],
                    "conversionGuidance": [],
                    "migrationGuideInsights": [],
                    "assumptions": ["password=supersecret"],
                }
            }
        ),
        profile_id="openai_fast_test",
    )

    stored = payload.to_storage_dict()
    serialized = str(stored)
    markers = {
        marker["code"]: marker
        for marker in stored["structuredOutput"]["reviewMarkers"]
    }
    assert "CREATE PROCEDURE" not in serialized
    assert "SecretOrders" not in serialized
    assert "raw_openai_response_text" not in serialized
    assert "supersecret" not in serialized
    assert "LLM_OUTPUT_STORAGE_SANITIZED" in markers
    assert markers["LLM_OUTPUT_STORAGE_SANITIZED"]["status"] == "REVIEW_REQUIRED"
    assert markers["LLM_OUTPUT_STORAGE_SANITIZED"]["evidenceRefs"] == ["fact_demo"]


def test_p23_quality_report_flags_unsafe_payload_without_leaking_raw_field_name() -> None:
    run = build_semantic_analysis_run(
        target_ref="dbo.usp_Demo",
        metadata={},
        static_analysis=None,
        procedure_definition=None,
        model_gateway=FakeModelGateway(
            output_by_target_ref={
                "dbo.usp_Demo": {
                    "businessRules": [
                        {
                            "category": "DEMO_RULE",
                            "summary": "Demo rule.",
                            "status": "INFERRED_DESCRIPTION",
                            "evidenceRefs": ["fact_demo"],
                        }
                    ],
                    "modernizationPoints": [],
                    "riskFlags": [],
                    "reviewMarkers": [],
                    "assumptions": [],
                }
            }
        ),
        profile_id="openai_fast_test",
    )

    report = evaluate_p23_semantic_quality(
        scenario={
            "fixture_id": "demo",
            "target_ref": "dbo.usp_Demo",
            "deterministic_facts": [{"id": "fact_demo"}],
            "transient_model_input": {"procedure_definition": "CREATE PROCEDURE demo"},
            "golden_expected_semantic_output": {
                "business_rules": [
                    {
                        "category": "DEMO_RULE",
                        "summary": "Demo rule.",
                        "status": "INFERRED_DESCRIPTION",
                        "evidence_refs": ["fact_demo"],
                    }
                ],
                "modernization_points": [],
                "risk_flags": [],
                "review_markers": [],
                "assumptions": [],
            },
            "unsupported_claim_expectations": [],
        },
        run=run,
        thresholds={
            "semantic_recall_min": 0.75,
            "evidence_discipline_min": 0.9,
            "unreviewed_overclaims_max": 0,
            "storage_safety_findings_max": 0,
        },
        additional_storage_payloads=({"raw_prompt": "redacted by report"},),
    )

    serialized = str(report)
    assert report["status"] == "FAILED"
    assert report["storageSafety"]["findingCount"] == 1
    assert "raw_prompt" not in serialized
    assert "redacted by report" not in serialized
