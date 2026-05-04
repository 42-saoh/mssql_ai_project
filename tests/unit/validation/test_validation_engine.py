from __future__ import annotations

from pathlib import Path

import yaml

from ai_agent_generation import GenerationContext, JavaMyBatisSpWrapperRenderer
from ai_agent_validation import (
    ValidationCheckResult,
    ValidationStatus,
    expand_artifact_scope,
    load_validation_rules,
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
    assert "Draft artifact requires human review before approval/publish." in (
        report.manual_review_points
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
