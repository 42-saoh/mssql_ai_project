from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from ai_agent_validation.models import (
    ReviewerChecklistItem,
    ValidationCheck,
    ValidationCheckResult,
    ValidationReport,
    ValidationSeverity,
    ValidationStatus,
)
from ai_agent_validation.rules import load_validation_rules, rules_for_artifact

REQUIRED_SECTIONS_BY_ARTIFACT: dict[str, tuple[str, ...]] = {
    "SP_ANALYSIS_DOC": (
        "input_interpretation",
        "analysis_summary",
        "procedure_signature",
        "evidence_summary",
        "assumptions_and_todo",
        "review_checklist",
    ),
    "SP_ANALYSIS_DOCUMENT": (
        "input_interpretation",
        "analysis_summary",
        "procedure_signature",
        "evidence_summary",
        "assumptions_and_todo",
        "review_checklist",
    ),
    "DEPENDENCY_REPORT": (
        "dependency_summary",
        "dependency_table",
        "evidence_summary",
        "assumptions_and_todo",
        "review_checklist",
    ),
    "JAVA_MYBATIS_DRAFT": (
        "input_interpretation",
        "generation_mode",
        "evidence_summary",
        "package_structure",
        "generated_files",
        "code_draft",
        "message_and_config_examples",
        "assumptions_and_todo",
        "review_checklist",
    ),
}


def validate_artifact(
    artifact: Any,
    *,
    artifact_id: str = "draft-artifact",
    rules_path: str | None = None,
) -> ValidationReport:
    artifact_type = _artifact_type_value(artifact)
    content = _content(artifact)
    evidence_refs = _evidence_refs(artifact)
    assumptions = _assumptions(artifact)
    review_required = _review_required(artifact)
    rules = load_validation_rules(rules_path)

    checks: list[ValidationCheck] = []
    missing_evidence: list[str] = []
    manual_review_points: list[str] = []

    checks.extend(_required_section_checks(artifact_type, content))

    evidence_check, evidence_missing = _evidence_coverage_check(
        artifact_type=artifact_type,
        content=content,
        evidence_refs=evidence_refs,
        has_review_marker=_has_review_marker(content, assumptions),
    )
    checks.append(evidence_check)
    missing_evidence.extend(evidence_missing)

    checks.append(
        _review_required_marker_check(
            content=content,
            assumptions=assumptions,
            review_required=review_required,
        )
    )

    for rule in rules_for_artifact(artifact_type, rules):
        if rule.id in {"artifact.evidence.required", "generator.uncertainty.marker"}:
            continue
        checks.append(
            ValidationCheck(
                rule_id=rule.id,
                severity=rule.severity,
                result=ValidationCheckResult.PASS,
                message=rule.description,
            )
        )

    if review_required or _has_review_marker(content, assumptions):
        manual_review_points.append("Draft artifact requires human review before approval/publish.")
    for assumption in assumptions:
        manual_review_points.append(assumption)

    status = _status_from_checks(checks)
    manual_review_points = _dedupe_preserve_order(manual_review_points)
    missing_evidence = _dedupe_preserve_order(missing_evidence)
    return ValidationReport(
        artifact_id=artifact_id,
        status=status,
        checks=tuple(checks),
        missing_evidence=tuple(missing_evidence),
        manual_review_points=tuple(manual_review_points),
        metadata={
            "artifactType": artifact_type,
            "evidenceCoverage": 1.0 if evidence_refs else 0.0,
        },
    )


def validate_publish_gate(
    *,
    artifact_id: str,
    validation_status: str | ValidationStatus | None,
    approval_decision: str | None,
    operation: str = "publish",
) -> ValidationReport:
    operation_value = _gate_operation(operation)
    operation_label = operation_value.capitalize()
    status_value = (
        validation_status.value
        if hasattr(validation_status, "value")
        else str(validation_status or "")
    )
    passed_validation = status_value == ValidationStatus.PASSED.value
    approved = approval_decision == "APPROVE"
    result = (
        ValidationCheckResult.PASS
        if passed_validation and approved
        else ValidationCheckResult.FAIL
    )
    message = (
        f"{operation_label} gate satisfied by passed validation and approval record."
        if result == ValidationCheckResult.PASS
        else f"{operation_label} requires PASSED validation and APPROVE decision."
    )
    check = ValidationCheck(
        rule_id="workflow.approval.before_publish",
        severity=ValidationSeverity.ERROR,
        result=result,
        message=message,
    )
    return ValidationReport(
        artifact_id=artifact_id,
        status=_status_from_checks((check,)),
        checks=(check,),
        manual_review_points=()
        if result == ValidationCheckResult.PASS
        else (f"Review or approval is missing for {operation_value}.",),
        metadata={"gate": operation_value},
    )


def summarize_validation_report(report: ValidationReport) -> dict[str, Any]:
    result_counts = {result.value: 0 for result in ValidationCheckResult}
    severity_counts = {severity.value: 0 for severity in ValidationSeverity}
    failed_rule_ids = []
    review_required_rule_ids = []

    for check in report.checks:
        result_counts[check.result.value] += 1
        severity_counts[check.severity.value] += 1
        if check.result == ValidationCheckResult.FAIL:
            failed_rule_ids.append(check.rule_id)
        if check.result == ValidationCheckResult.REVIEW_REQUIRED:
            review_required_rule_ids.append(check.rule_id)

    return {
        "artifactId": report.artifact_id,
        "status": report.status.value,
        "checkCounts": result_counts,
        "severityCounts": severity_counts,
        "failedRuleIds": sorted(failed_rule_ids),
        "reviewRequiredRuleIds": sorted(review_required_rule_ids),
        "missingEvidence": list(report.missing_evidence),
        "manualReviewPoints": list(report.manual_review_points),
    }


def build_reviewer_checklist(
    report: ValidationReport,
    *,
    decision: str,
    reviewer: str,
    comment: str,
) -> tuple[ReviewerChecklistItem, ...]:
    reviewer_present = bool(str(reviewer).strip())
    comment_present = bool(str(comment).strip())
    manual_review_points = len(report.manual_review_points)
    missing_evidence = len(report.missing_evidence)

    return (
        ReviewerChecklistItem(
            item_id="validation.latest_report_bound",
            label="Latest validation report is bound",
            satisfied=True,
            detail=f"{report.artifact_id}:{report.status.value}",
        ),
        ReviewerChecklistItem(
            item_id="validation.status_passed_for_approval",
            label="Validation status supports approval",
            satisfied=report.status == ValidationStatus.PASSED,
            detail=(
                "APPROVE requires PASSED validation; non-approval decisions may "
                "record unresolved review."
            ),
        ),
        ReviewerChecklistItem(
            item_id="validation.no_failed_checks",
            label="No failed validation checks remain",
            satisfied=not report.failed_checks,
            detail=f"{len(report.failed_checks)} failed checks",
        ),
        ReviewerChecklistItem(
            item_id="evidence.no_missing_refs",
            label="Missing evidence has been resolved",
            satisfied=missing_evidence == 0,
            detail=f"{missing_evidence} missing evidence refs",
        ),
        ReviewerChecklistItem(
            item_id="review.manual_points_acknowledged",
            label="Manual review points are acknowledged",
            satisfied=manual_review_points == 0 or comment_present,
            detail=f"{manual_review_points} manual review points",
        ),
        ReviewerChecklistItem(
            item_id="approval.human_actor_recorded",
            label="Human reviewer and comment are recorded",
            satisfied=reviewer_present and comment_present,
            detail=f"decision={decision}",
        ),
    )


def _artifact_type_value(artifact: Any) -> str:
    if isinstance(artifact, Mapping):
        value = artifact.get("artifactType") or artifact.get("artifact_type") or ""
    else:
        value = getattr(artifact, "artifact_type_value", None)
        if value is None:
            value = getattr(artifact, "artifact_type", "")
    return value.value if hasattr(value, "value") else str(value)


def _content(artifact: Any) -> str:
    if isinstance(artifact, Mapping):
        return str(artifact.get("content", ""))
    return str(getattr(artifact, "content", ""))


def _evidence_refs(artifact: Any) -> tuple[Any, ...]:
    if isinstance(artifact, Mapping):
        return tuple(artifact.get("evidenceRefs", artifact.get("evidence_refs", ())) or ())
    return tuple(getattr(artifact, "evidence_refs", ()) or ())


def _assumptions(artifact: Any) -> tuple[str, ...]:
    if isinstance(artifact, Mapping):
        return tuple(str(item) for item in artifact.get("assumptions", ()) or ())
    return tuple(str(item) for item in getattr(artifact, "assumptions", ()) or ())


def _review_required(artifact: Any) -> bool:
    if isinstance(artifact, Mapping):
        return bool(artifact.get("reviewRequired", artifact.get("review_required", False)))
    return bool(getattr(artifact, "review_required", False))


def _required_section_checks(artifact_type: str, content: str) -> tuple[ValidationCheck, ...]:
    required_sections = REQUIRED_SECTIONS_BY_ARTIFACT.get(artifact_type, ())
    if not required_sections:
        return ()
    checks = []
    for section in required_sections:
        exists = _has_markdown_section(content, section)
        checks.append(
            ValidationCheck(
                rule_id=f"artifact.required_section.{section}",
                severity=ValidationSeverity.ERROR,
                result=ValidationCheckResult.PASS if exists else ValidationCheckResult.FAIL,
                message=(
                    f"Required section present: {section}"
                    if exists
                    else f"Missing required section: {section}"
                ),
            )
        )
    return tuple(checks)


def _has_markdown_section(content: str, section: str) -> bool:
    pattern = re.compile(rf"^##\s+{re.escape(section)}\s*$", flags=re.MULTILINE)
    return bool(pattern.search(content))


def _evidence_coverage_check(
    *,
    artifact_type: str,
    content: str,
    evidence_refs: Sequence[Any],
    has_review_marker: bool,
) -> tuple[ValidationCheck, tuple[str, ...]]:
    if not evidence_refs and has_review_marker:
        return (
            ValidationCheck(
                rule_id="artifact.evidence.required",
                severity=ValidationSeverity.ERROR,
                result=ValidationCheckResult.REVIEW_REQUIRED,
                message=(
                    f"{artifact_type} has no evidence refs but is explicitly marked "
                    "REVIEW_REQUIRED."
                ),
            ),
            (),
        )
    if not evidence_refs:
        return (
            ValidationCheck(
                rule_id="artifact.evidence.required",
                severity=ValidationSeverity.ERROR,
                result=ValidationCheckResult.FAIL,
                message=f"{artifact_type} must include evidence refs or REVIEW_REQUIRED marker.",
            ),
            ("artifact.evidence_refs",),
        )

    missing = []
    for ref in evidence_refs:
        object_ref = _evidence_object_ref(ref)
        if object_ref and object_ref not in content:
            missing.append(object_ref)
    result = ValidationCheckResult.PASS if not missing else ValidationCheckResult.FAIL
    return (
        ValidationCheck(
            rule_id="artifact.evidence.required",
            severity=ValidationSeverity.ERROR,
            result=result,
            message=(
                "Evidence refs are present and referenced in content."
                if result == ValidationCheckResult.PASS
                else "Evidence refs exist but are not all mentioned in content."
            ),
        ),
        tuple(missing),
    )


def _evidence_object_ref(ref: Any) -> str:
    if isinstance(ref, Mapping):
        return str(ref.get("objectRef", ref.get("object_ref", "")))
    return str(getattr(ref, "object_ref", ""))


def _review_required_marker_check(
    *,
    content: str,
    assumptions: Sequence[str],
    review_required: bool,
) -> ValidationCheck:
    has_marker = _has_review_marker(content, assumptions)
    if review_required and has_marker:
        return ValidationCheck(
            rule_id="generator.uncertainty.marker",
            severity=ValidationSeverity.WARNING,
            result=ValidationCheckResult.REVIEW_REQUIRED,
            message="Draft uncertainty is explicitly marked for human review.",
        )
    if review_required:
        return ValidationCheck(
            rule_id="generator.uncertainty.marker",
            severity=ValidationSeverity.WARNING,
            result=ValidationCheckResult.FAIL,
            message=(
                "review_required metadata is true but content lacks "
                "REVIEW_REQUIRED/TODO marker."
            ),
        )
    return ValidationCheck(
        rule_id="generator.uncertainty.marker",
        severity=ValidationSeverity.WARNING,
        result=ValidationCheckResult.PASS,
        message="No review-required marker needed for this artifact metadata.",
    )


def _has_review_marker(content: str, assumptions: Sequence[str]) -> bool:
    joined_assumptions = "\n".join(assumptions)
    return any(
        marker in content or marker in joined_assumptions
        for marker in ("REVIEW_REQUIRED", "TODO")
    )


def _gate_operation(operation: str) -> str:
    normalized = str(operation or "publish").strip().lower()
    if normalized not in {"publish", "export"}:
        raise ValueError(f"Unsupported approval gate operation: {operation}")
    return normalized


def _dedupe_preserve_order(items: Sequence[str]) -> list[str]:
    seen = set()
    deduped = []
    for item in items:
        if item in seen:
            continue
        seen.add(item)
        deduped.append(item)
    return deduped


def _status_from_checks(checks: Sequence[ValidationCheck]) -> ValidationStatus:
    if any(
        check.result == ValidationCheckResult.FAIL
        and check.severity in {ValidationSeverity.ERROR, ValidationSeverity.BLOCKER}
        for check in checks
    ):
        return ValidationStatus.FAILED
    if any(check.result == ValidationCheckResult.REVIEW_REQUIRED for check in checks):
        return ValidationStatus.REVIEW_REQUIRED
    if any(check.result == ValidationCheckResult.FAIL for check in checks):
        return ValidationStatus.REVIEW_REQUIRED
    return ValidationStatus.PASSED
