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

LOCALIZED_HUMAN_TEXT_ARTIFACT_TYPES = {
    "SP_ANALYSIS_DOC",
    "SP_ANALYSIS_DOCUMENT",
    "DEPENDENCY_REPORT",
    "JAVA_MYBATIS_DRAFT",
    "DTO_MODEL_DRAFT",
}

_KOREAN_TEXT_RE = re.compile(r"[가-힣]")
_CODE_FENCE_RE = re.compile(r"```.*?```", flags=re.DOTALL)


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
    llm_check = _llm_inference_review_check(evidence_refs)
    if llm_check is not None:
        checks.append(llm_check)
    localized_check = _localized_human_text_check(
        artifact_type=artifact_type,
        content=content,
    )
    if localized_check is not None:
        checks.append(localized_check)

    for rule in rules_for_artifact(artifact_type, rules):
        if rule.id in {
            "artifact.evidence.required",
            "generator.uncertainty.marker",
            "llm.inference.review_required",
            "artifact.localized_human_text.ko_kr",
        }:
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
        manual_review_points.append("초안 artifact에는 downstream 사용 전 확인할 validation caveat가 있습니다.")
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
        f"{operation_label} gate는 PASSED validation과 approval record로 충족되었습니다."
        if result == ValidationCheckResult.PASS
        else f"{operation_label}에는 PASSED validation과 APPROVE decision이 필요합니다."
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
        else (f"{operation_value}에 필요한 governance evidence가 부족합니다.",),
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
            label="최신 validation report 연결",
            satisfied=True,
            detail=f"{report.artifact_id}:{report.status.value}",
        ),
        ReviewerChecklistItem(
            item_id="validation.status_passed_for_approval",
            label="승인을 지원하는 validation status",
            satisfied=report.status == ValidationStatus.PASSED,
            detail=(
                "APPROVE에는 PASSED validation이 필요하며, 비승인 decision은 미해결 검토를 "
                "기록할 수 있습니다."
            ),
        ),
        ReviewerChecklistItem(
            item_id="validation.no_failed_checks",
            label="실패 validation check 없음",
            satisfied=not report.failed_checks,
            detail=f"failed check {len(report.failed_checks)}개",
        ),
        ReviewerChecklistItem(
            item_id="evidence.no_missing_refs",
            label="누락 evidence 해소",
            satisfied=missing_evidence == 0,
            detail=f"missing evidence ref {missing_evidence}개",
        ),
        ReviewerChecklistItem(
            item_id="review.manual_points_acknowledged",
            label="수동 검토 항목 확인",
            satisfied=manual_review_points == 0 or comment_present,
            detail=f"manual review point {manual_review_points}개",
        ),
        ReviewerChecklistItem(
            item_id="approval.human_actor_recorded",
            label="검토자와 의견 기록",
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
                    f"필수 section이 있습니다: {section}"
                    if exists
                    else f"필수 section이 없습니다: {section}"
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
                    f"{artifact_type}에는 evidence ref가 없지만 REVIEW_REQUIRED로 명시 표시되었습니다."
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
                message=f"{artifact_type}에는 evidence ref 또는 REVIEW_REQUIRED marker가 필요합니다.",
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
                "Evidence ref가 있으며 본문에서 참조됩니다."
                if result == ValidationCheckResult.PASS
                else "Evidence ref는 있지만 본문에 모두 언급되지는 않았습니다."
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
            message="초안의 불확실성이 validation caveat로 명시 표시되었습니다.",
        )
    if review_required:
        return ValidationCheck(
            rule_id="generator.uncertainty.marker",
            severity=ValidationSeverity.WARNING,
            result=ValidationCheckResult.FAIL,
            message=(
                "review_required metadata는 true이지만 본문에 REVIEW_REQUIRED/TODO marker가 없습니다."
            ),
        )
    return ValidationCheck(
        rule_id="generator.uncertainty.marker",
        severity=ValidationSeverity.WARNING,
        result=ValidationCheckResult.PASS,
        message="이 artifact metadata에는 review-required marker가 필요하지 않습니다.",
    )


def _llm_inference_review_check(evidence_refs: Sequence[Any]) -> ValidationCheck | None:
    if not any(_evidence_type(ref) == "LLM_INFERENCE" for ref in evidence_refs):
        return None
    return ValidationCheck(
        rule_id="llm.inference.review_required",
        severity=ValidationSeverity.WARNING,
        result=ValidationCheckResult.REVIEW_REQUIRED,
        message=(
            "LLM inference는 초안 의미를 보강할 수 있지만 결정론적 근거 없이 새로운 dependency, "
            "table, function, procedure fact를 확정할 수 없습니다."
        ),
    )


def _localized_human_text_check(
    *,
    artifact_type: str,
    content: str,
) -> ValidationCheck | None:
    if artifact_type not in LOCALIZED_HUMAN_TEXT_ARTIFACT_TYPES:
        return None
    text = _human_text_for_language_check(content)
    has_korean = bool(_KOREAN_TEXT_RE.search(text))
    return ValidationCheck(
        rule_id="artifact.localized_human_text.ko_kr",
        severity=ValidationSeverity.WARNING,
        result=(
            ValidationCheckResult.PASS
            if has_korean
            else ValidationCheckResult.REVIEW_REQUIRED
        ),
        message=(
            "작업자-facing 자유 텍스트가 한국어로 포함되어 있습니다."
            if has_korean
            else (
                "작업자-facing 자유 텍스트에 한국어 설명이 없어 검토가 필요합니다. "
                "코드블록과 식별자는 검사에서 제외했습니다."
            )
        ),
    )


def _human_text_for_language_check(content: str) -> str:
    without_fences = _CODE_FENCE_RE.sub("", content)
    lines = []
    for line in without_fences.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith(("```", "|---")):
            continue
        lines.append(stripped)
    return "\n".join(lines)


def _evidence_type(ref: Any) -> str:
    if isinstance(ref, Mapping):
        return str(ref.get("type", ""))
    return str(getattr(ref, "type", ""))


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
