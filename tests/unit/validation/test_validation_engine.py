from __future__ import annotations

from pathlib import Path

import yaml
from ai_agent_generation import GenerationContext, JavaMyBatisSpWrapperRenderer
from ai_agent_validation import (
    ValidationCheckResult,
    ValidationStatus,
    expand_artifact_scope,
    load_validation_rules,
    summarize_validation_report,
    validate_artifact,
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


def test_validate_java_mybatis_golden_draft_tracks_quality_caveats_without_failure() -> None:
    report = validate_artifact(_golden_manifest_artifact(), artifact_id="golden-java-draft")

    assert report.status == ValidationStatus.REVIEW_REQUIRED
    assert not report.failed_checks
    assert report.metadata["artifactType"] == "JAVA_MYBATIS_DRAFT"
    assert any(
        check.rule_id == "generator.uncertainty.marker"
        and check.result == ValidationCheckResult.REVIEW_REQUIRED
        for check in report.checks
    )
    assert "초안 artifact에는 근거 보강 또는 품질 caveat가 남아 있습니다." in (
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
                    "REVIEW_REQUIRED: LLM inference needs stronger evidence.",
                    "",
                    "## quality_summary",
                    "- evidence caveat present",
                    "",
                    "## evidence_map",
                    "- LLM_INFERENCE: agent_123",
                    "",
                    "## known_caveats",
                    "- LLM inference needs deterministic evidence.",
                    "",
                    "## next_evidence_to_collect",
                    "- deterministic flow evidence",
                    "",
                    "## draft_readiness",
                    "- draft only",
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


def test_validation_summary_reports_quality_caveats_deterministically() -> None:
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

    assert summary["artifactId"] == "review-required-doc"
    assert summary["checkCounts"]["FAIL"] > 0
    assert summary["checkCounts"]["REVIEW_REQUIRED"] > 0
    assert summary["qualityCaveats"] == list(report.manual_review_points)
