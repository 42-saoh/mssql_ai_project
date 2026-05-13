from __future__ import annotations

from ai_agent_runtime.planner_effectiveness import build_planner_metrics


def test_planner_metrics_counts_cited_tool_evidence_and_claim_support() -> None:
    metrics = build_planner_metrics(
        ai_tool_evidence={
            "status": "SUCCEEDED",
            "toolCallCount": 2,
            "toolResults": [
                {"factId": "mcp.get_table_schema.aaa111"},
                {"factId": "mcp.get_table_indexes.bbb222"},
            ],
            "blockedRequests": [],
            "caveats": [],
        },
        deterministic_facts=[
            {"id": "metadata.profile.ccc333"},
            {"id": "metadata.search.ddd444"},
        ],
        component_invocations=[
            {
                "stage": "ai_metadata_tool_planning",
                "toolRequestCount": 3,
                "status": "SUCCEEDED",
            },
            {"stage": "ai_tool_execution", "status": "SUCCEEDED"},
            {"stage": "ai_tool_execution", "status": "SUCCEEDED"},
        ],
        structured_output={
            "objectInsights": [
                {
                    "code": "TABLE_SHAPE",
                    "evidenceRefs": ["mcp.get_table_schema.aaa111"],
                }
            ],
            "insightGroups": [
                {
                    "category": "INDEX",
                    "insights": [
                        {
                            "code": "INDEX_CLAIM",
                            "evidenceRefs": ["mcp.get_table_indexes.bbb222"],
                        }
                    ],
                }
            ],
            "dtoReadiness": [
                {
                    "objectRef": "dbo.TB_ORDER",
                    "evidenceRefs": ["metadata.profile.ccc333"],
                }
            ],
        },
        deduped_request_count=1,
    )

    assert metrics["plannedRequestCount"] == 3
    assert metrics["executedToolCallCount"] == 2
    assert metrics["dedupedRequestCount"] == 1
    assert metrics["evidenceFactCount"] == 3
    assert metrics["citedEvidenceFactCount"] == 3
    assert metrics["claimSupportRate"] == 1.0
    assert metrics["status"] == "SUCCEEDED"


def test_planner_metrics_marks_under_utilized_or_blocked_plans_review_required() -> None:
    metrics = build_planner_metrics(
        ai_tool_evidence={
            "status": "REVIEW_REQUIRED",
            "toolCallCount": 1,
            "toolResults": [{"factId": "mcp.get_table_schema.aaa111"}],
            "blockedRequests": [{"code": "AI_TOOL_FORBIDDEN_ARGUMENT"}],
            "caveats": [],
        },
        deterministic_facts=[{"id": "metadata.profile.bbb222"}],
        component_invocations=[
            {"stage": "ai_metadata_tool_planning", "toolRequestCount": 2},
            {"stage": "ai_tool_execution", "status": "SUCCEEDED"},
            {"stage": "ai_tool_execution", "status": "REVIEW_REQUIRED"},
        ],
        structured_output={
            "objectInsights": [
                {"code": "UNSUPPORTED", "evidenceRefs": ["metadata.search.ccc333"]}
            ]
        },
    )

    assert metrics["blockedRequestCount"] == 1
    assert metrics["claimSupportRate"] == 0.0
    assert metrics["status"] == "REVIEW_REQUIRED"


def test_planner_metrics_preserves_skipped_status_without_claim_analysis() -> None:
    metrics = build_planner_metrics(
        ai_tool_evidence={
            "status": "SKIPPED",
            "toolCallCount": 0,
            "toolResults": [],
            "blockedRequests": [],
            "caveats": ["AI_METADATA_ANALYSIS_SKIPPED"],
        },
    )

    assert metrics["status"] == "SKIPPED"
    assert metrics["claimAnalysisAvailable"] is False
    assert metrics["evidenceUtilization"] == 1.0
