from __future__ import annotations

from pathlib import Path

import yaml
from ai_agent_generation import GenerationContext, JavaMyBatisSpWrapperRenderer
from ai_agent_validation import (
    ValidationCheckResult,
    ValidationStatus,
    build_reviewer_checklist,
    expand_artifact_scope,
    load_validation_rules,
    summarize_validation_report,
    validate_artifact,
    validate_publish_gate,
)

ROOT = Path(__file__).resolve().parents[3]
GOLDEN_DIR = (
    ROOT
    / "fixtures"
    / "generation"
    / "golden"
    / "java_mybatis_sp_wrapper_order_request_v1"
)


def _golden_manifest_artifact():
    payload = yaml.safe_load((GOLDEN_DIR / "input.yaml").read_text(encoding="utf-8"))
    context = GenerationContext.from_mapping(payload)
    return JavaMyBatisSpWrapperRenderer().render_bundle(context).manifest


def test_rules_loader_reads_spec_and_expands_aliases() -> None:
    rules = load_validation_rules()

    assert any(rule.id == "artifact.evidence.required" for rule in rules)
    assert expand_artifact_scope("SP_ANALYSIS_DOCUMENT") == ("SP_ANALYSIS_DOC",)
    assert expand_artifact_scope("JAVA_MYBATIS_DRAFT") == (
        "DTO_DRAFT",
        "SERVICE_DRAFT",
        "MAPPER_INTERFACE",
        "MAPPER_XML",
    )


def test_validate_java_mybatis_golden_draft_requires_review_without_failure() -> None:
    report = validate_artifact(_golden_manifest_artifact(), artifact_id="golden-java-draft")

    assert report.status == ValidationStatus.REVIEW_REQUIRED
    assert not report.failed_checks
    assert report.metadata["artifactType"] == "JAVA_MYBATIS_DRAFT"
    assert any(
        check.rule_id == "generator.uncertainty.marker"
        and check.result == ValidationCheckResult.REVIEW_REQUIRED
        for check in report.checks
    )
    assert "초안 artifact에는 downstream 사용 전 확인할 validation caveat가 있습니다." in (
        report.manual_review_points
    )
    assert any(
        check.rule_id == "artifact.localized_human_text.ko_kr"
        and check.result == ValidationCheckResult.PASS
        for check in report.checks
    )


def test_validate_missing_sections_and_evidence_fails() -> None:
    report = validate_artifact(
        {
            "artifactType": "SP_ANALYSIS_DOC",
            "content": "# Missing baseline sections\n",
            "evidenceRefs": [],
            "reviewRequired": False,
        },
        artifact_id="bad-analysis-doc",
    )

    assert report.status == ValidationStatus.FAILED
    assert "artifact.evidence_refs" in report.missing_evidence
    assert any(
        check.rule_id == "artifact.required_section.evidence_summary"
        and check.result == ValidationCheckResult.FAIL
        for check in report.checks
    )


def test_publish_gate_requires_passed_validation_and_approval() -> None:
    blocked = validate_publish_gate(
        artifact_id="draft-1",
        validation_status=ValidationStatus.REVIEW_REQUIRED,
        approval_decision=None,
    )
    allowed = validate_publish_gate(
        artifact_id="draft-1",
        validation_status=ValidationStatus.PASSED,
        approval_decision="APPROVE",
    )

    assert blocked.status == ValidationStatus.FAILED
    assert allowed.status == ValidationStatus.PASSED


def test_llm_inference_evidence_forces_review_required() -> None:
    report = validate_artifact(
        {
            "artifactType": "SP_ANALYSIS_DOC",
            "content": "\n".join(
                [
                    "# Analysis",
                    "",
                    "## input_interpretation",
                    "dbo.usp_demo",
                    "",
                    "## analysis_summary",
                    "LLM Inference enrichment remains REVIEW_REQUIRED.",
                    "",
                    "## procedure_signature",
                    "dbo.usp_demo()",
                    "",
                    "## evidence_summary",
                    "dbo.usp_demo",
                    "agent_123",
                    "",
                    "## assumptions_and_todo",
                    "REVIEW_REQUIRED: LLM inference must be reviewed.",
                    "",
                    "## review_checklist",
                    "- [ ] reviewer_confirms_llm_inference",
                ]
            ),
            "evidenceRefs": [
                {
                    "type": "MSSQL_METADATA",
                    "objectRef": "dbo.usp_demo",
                    "locator": "metadata.snapshot",
                },
                {
                    "type": "LLM_INFERENCE",
                    "objectRef": "agent_123",
                    "locator": "agent-runtime.modelInvocation.outputHash",
                },
            ],
            "reviewRequired": True,
        },
        artifact_id="llm-analysis-doc",
    )

    assert report.status == ValidationStatus.REVIEW_REQUIRED
    assert any(
        check.rule_id == "llm.inference.review_required"
        and check.result == ValidationCheckResult.REVIEW_REQUIRED
        for check in report.checks
    )


def test_export_gate_uses_same_approval_rule_without_taxonomy_change() -> None:
    report = validate_publish_gate(
        artifact_id="draft-1",
        validation_status=ValidationStatus.PASSED,
        approval_decision=None,
        operation="export",
    )

    assert report.status == ValidationStatus.FAILED
    assert report.checks[0].rule_id == "workflow.approval.before_publish"
    assert report.metadata["gate"] == "export"
    assert "Export에는 PASSED validation" in report.checks[0].message


def test_validation_summary_and_reviewer_checklist_are_deterministic() -> None:
    report = validate_artifact(
        {
            "artifactType": "SP_ANALYSIS_DOC",
            "content": "# Missing baseline sections\nREVIEW_REQUIRED\n",
            "evidenceRefs": [],
            "reviewRequired": True,
            "assumptions": ["REVIEW_REQUIRED: table dependency evidence가 불완전합니다."],
        },
        artifact_id="review-required-doc",
    )

    summary = summarize_validation_report(report)
    checklist = build_reviewer_checklist(
        report,
        decision="REQUEST_CHANGES",
        reviewer="reviewer@example.com",
        comment="acknowledged",
    )

    assert summary["artifactId"] == "review-required-doc"
    assert summary["checkCounts"] == {
        "PASS": 0,
        "FAIL": 6,
        "REVIEW_REQUIRED": 3,
    }
    assert summary["severityCounts"] == {
        "INFO": 0,
        "WARNING": 2,
        "ERROR": 7,
        "BLOCKER": 0,
    }
    assert [item.item_id for item in checklist] == [
        "validation.latest_report_bound",
        "validation.status_passed_for_approval",
        "validation.no_failed_checks",
        "evidence.no_missing_refs",
        "review.manual_points_acknowledged",
        "approval.human_actor_recorded",
    ]
    assert checklist[-1].as_dict()["satisfied"] is True
