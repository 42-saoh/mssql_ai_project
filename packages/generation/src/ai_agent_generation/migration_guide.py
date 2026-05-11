from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from typing import Any

from ai_agent_generation.models import GenerationContext, RenderedArtifact

P24_REQUIRED_SECTION_IDS = (
    "sp_overview",
    "feature_branch_taxonomy",
    "dependency_inventory",
    "dml_impact_matrix",
    "call_flow",
    "critical_phase_analysis",
    "complexity_risk_metrics",
    "migration_strategy",
    "appendix_mappings",
    "evidence_assumptions_review",
)

P24_SECTION_TITLES = {
    "sp_overview": "SP overview and basic information",
    "feature_branch_taxonomy": "Main features and branch/flag taxonomy",
    "dependency_inventory": "Dependency inventory",
    "dml_impact_matrix": "DML impact matrix",
    "call_flow": "Branch-level call flow",
    "critical_phase_analysis": "Critical phase analysis",
    "complexity_risk_metrics": "Complexity and risk metrics",
    "migration_strategy": "Migration strategy and Java/MyBatis draft readiness",
    "appendix_mappings": "Parameter and code mapping appendix",
    "evidence_assumptions_review": "Evidence refs, assumptions, and REVIEW_REQUIRED markers",
}

_THRESHOLD_FIELD_MAP = {
    "required_section_coverage_min": "requiredSectionCoverageMin",
    "evidence_linked_claim_coverage_min": "evidenceLinkedClaimCoverageMin",
    "dml_matrix_coverage_min": "dmlMatrixCoverageMin",
    "branch_call_flow_coverage_min": "branchCallFlowCoverageMin",
    "unsupported_claim_review_required_ratio_min": (
        "unsupportedClaimReviewRequiredRatioMin"
    ),
    "forbidden_storage_findings_max": "forbiddenStorageFindingsMax",
}

_FORBIDDEN_STORAGE_KEYS = frozenset(
    {
        "raw_prompt",
        "raw_sp_definition",
        "raw_openai_response_text",
        "row_data",
        "secrets",
    }
)
_FORBIDDEN_TEXT_MARKERS = (
    "CREATE OR ALTER PROCEDURE",
    "CREATE PROCEDURE",
    "CREATE PROC",
    "ALTER PROCEDURE",
)


def migration_guide_payload(context: GenerationContext) -> Mapping[str, Any]:
    payload = context.value("migrationGuide", {}) or {}
    return payload if isinstance(payload, Mapping) else {}


def render_p24_migration_guide_sections(context: GenerationContext) -> list[str]:
    guide = migration_guide_payload(context)
    if not guide:
        return _render_placeholder_sections(context)

    section_by_id = {
        str(section.get("id")): section
        for section in _sequence(guide.get("section_expectations"))
        if isinstance(section, Mapping)
    }
    lines: list[str] = []
    for section_id in P24_REQUIRED_SECTION_IDS:
        section = _mapping(section_by_id.get(section_id))
        _append_required_section(lines, section_id, section)
        if section_id == "sp_overview":
            _append_overview(lines, context, guide)
        elif section_id == "feature_branch_taxonomy":
            _append_sanitized_facts(lines, guide)
        elif section_id == "dependency_inventory":
            _append_dependency_inventory(lines, guide)
        elif section_id == "dml_impact_matrix":
            _append_dml_matrix(lines, guide)
        elif section_id == "call_flow":
            _append_call_flow(lines, guide)
        elif section_id == "critical_phase_analysis":
            _append_critical_phase(lines, guide)
        elif section_id == "complexity_risk_metrics":
            _append_complexity_risk(lines, guide)
        elif section_id == "migration_strategy":
            _append_migration_strategy(lines, context)
        elif section_id == "appendix_mappings":
            _append_appendix_mappings(lines, guide)
        elif section_id == "evidence_assumptions_review":
            _append_evidence_and_review(lines, context, guide)
        lines.append("")
    return lines


def render_p24_dependency_report_sections(context: GenerationContext) -> list[str]:
    guide = migration_guide_payload(context)
    if not guide:
        return [
            "## p24_dependency_report_contract",
            "- REVIEW_REQUIRED: migrationGuide sanitized facts not supplied.",
            "- generated_source_application: `not_performed`",
            "",
        ]

    lines = [
        "## p24_dependency_inventory",
        "- source: migrationGuide.dependency_inventory",
    ]
    _append_dependency_inventory(lines, guide)
    lines.extend(["", "## p24_dml_impact_matrix", "- source: migrationGuide.dml_matrix"])
    _append_dml_matrix(lines, guide)
    lines.extend(["", "## p24_branch_call_flow", "- source: migrationGuide.call_flow"])
    _append_call_flow(lines, guide)
    lines.extend(["", "## p24_review_required_claims"])
    _append_evidence_and_review(lines, context, guide)
    lines.append("")
    return lines


def evaluate_p24_migration_guide_quality(
    *,
    scenario: Mapping[str, Any],
    artifacts: Sequence[RenderedArtifact | Mapping[str, Any]],
    thresholds: Mapping[str, Any],
    additional_storage_payloads: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    artifact_payloads = [_artifact_payload(artifact) for artifact in artifacts]
    combined_text = "\n".join(_artifact_text(artifact) for artifact in artifacts)
    normalized_thresholds = _normalize_thresholds(thresholds)

    section_coverage = _section_coverage(scenario, combined_text)
    evidence_linked_claim_coverage = _evidence_linked_claim_coverage(
        scenario,
        combined_text,
    )
    dml_matrix_coverage = _dml_matrix_coverage(scenario, combined_text)
    branch_call_flow_coverage = _branch_call_flow_coverage(scenario, combined_text)
    unsupported_ratio = _unsupported_claim_review_required_ratio(scenario, combined_text)
    review_required_findings = _review_required_findings(scenario, combined_text)
    storage_findings = _storage_safety_findings(
        payloads=(*artifact_payloads, *additional_storage_payloads),
    )

    scores = {
        "requiredSectionCoverage": _ratio(
            sum(1 for covered in section_coverage.values() if covered),
            len(section_coverage),
        ),
        "evidenceLinkedClaimCoverage": evidence_linked_claim_coverage,
        "dmlMatrixCoverage": dml_matrix_coverage,
        "branchCallFlowCoverage": branch_call_flow_coverage,
        "unsupportedClaimReviewRequiredRatio": unsupported_ratio,
        "storageSafetyFindings": len(storage_findings),
    }
    report = {
        "status": _status(scores=scores, thresholds=normalized_thresholds),
        "productionReady": False,
        "scores": scores,
        "thresholds": normalized_thresholds,
        "evidenceRefs": _quality_report_evidence_refs(scenario),
        "sectionCoverage": section_coverage,
        "reviewRequiredFindings": review_required_findings,
        "storageSafetyFindings": storage_findings,
    }

    report_storage_findings = _storage_safety_findings(payloads=(report,))
    if report_storage_findings:
        report["storageSafetyFindings"] = [*storage_findings, *report_storage_findings]
        report["scores"]["storageSafetyFindings"] = len(report["storageSafetyFindings"])
        report["status"] = _status(scores=report["scores"], thresholds=normalized_thresholds)

    return report


def _append_required_section(
    lines: list[str],
    section_id: str,
    section: Mapping[str, Any],
) -> None:
    lines.extend(
        [
            f"## {section_id}",
            f"- title: {section.get('title') or P24_SECTION_TITLES[section_id]}",
            f"- evidenceRefs: {_refs_text(_evidence_refs(section))}",
        ]
    )
    claims = _sequence(section.get("claims"))
    if not claims:
        lines.append("- REVIEW_REQUIRED: section claim coverage must be reviewed.")
        return
    for claim in claims:
        if not isinstance(claim, Mapping):
            continue
        lines.append(
            "- claim: "
            f"{claim.get('id', 'unnamed_claim')} "
            f"status={claim.get('status', 'REVIEW_REQUIRED')} "
            f"evidenceRefs={_refs_text(_evidence_refs(claim))} "
            f"summary={claim.get('summary', '')}"
        )


def _append_overview(
    lines: list[str],
    context: GenerationContext,
    guide: Mapping[str, Any],
) -> None:
    db_context = _mapping(guide.get("db_context"))
    lines.extend(
        [
            f"- targetRef: `{guide.get('target_ref', context.sp_name)}`",
            f"- fixtureId: `{guide.get('fixture_id', context.sample_id)}`",
            "- status: DRAFT",
            "- productionReady: `false`",
            f"- artifactsUnderTest: {_refs_text(_sequence(guide.get('artifacts_under_test')))}",
            f"- metadataProfileId: `{db_context.get('metadata_profile_id', 'REVIEW_REQUIRED')}`",
            f"- targetDb: `{db_context.get('target_db', 'REVIEW_REQUIRED')}`",
            f"- platformDb: `{db_context.get('platform_db', 'REVIEW_REQUIRED')}`",
            f"- plfFallback: `{db_context.get('plf_fallback', 'forbidden')}`",
        ]
    )


def _append_sanitized_facts(lines: list[str], guide: Mapping[str, Any]) -> None:
    facts = _sequence(guide.get("sanitized_facts"))
    if not facts:
        lines.append("- REVIEW_REQUIRED: no sanitized deterministic facts supplied.")
        return
    for fact in facts:
        if not isinstance(fact, Mapping):
            continue
        lines.append(
            "- fact: "
            f"{fact.get('id', 'unnamed_fact')} "
            f"type={fact.get('fact_type', 'REVIEW_REQUIRED')} "
            f"evidenceRefs={_refs_text(_evidence_refs(fact))} "
            f"summary={fact.get('summary', '')}"
        )


def _append_dependency_inventory(lines: list[str], guide: Mapping[str, Any]) -> None:
    inventory = _sequence(guide.get("dependency_inventory"))
    if not inventory:
        lines.append("- REVIEW_REQUIRED: dependency inventory unavailable.")
        return
    lines.extend(
        [
            "| kind | object | operations | keyColumns | status | evidenceRefs | summary |",
            "|---|---|---|---|---|---|---|",
        ]
    )
    for item in inventory:
        if not isinstance(item, Mapping):
            continue
        lines.append(
            "| "
            f"{item.get('object_kind', 'REVIEW_REQUIRED')} | "
            f"`{item.get('object_ref', 'REVIEW_REQUIRED')}` | "
            f"{_refs_text(_sequence(item.get('operations')))} | "
            f"{_refs_text(_sequence(item.get('key_columns')))} | "
            f"{item.get('status', 'REVIEW_REQUIRED')} | "
            f"{_refs_text(_evidence_refs(item))} | "
            f"{item.get('join_or_where_summary', '')} "
            f"{item.get('value_or_state_patterns', '')} |"
        )


def _append_dml_matrix(lines: list[str], guide: Mapping[str, Any]) -> None:
    matrix = _sequence(guide.get("dml_matrix"))
    if not matrix:
        lines.append("- REVIEW_REQUIRED: DML matrix unavailable.")
        return
    lines.extend(
        [
            "| operation | target | phase | status | evidenceRefs | impact |",
            "|---|---|---|---|---|---|",
        ]
    )
    for item in matrix:
        if not isinstance(item, Mapping):
            continue
        lines.append(
            "| "
            f"{item.get('operation', 'REVIEW_REQUIRED')} | "
            f"`{item.get('target_ref', 'REVIEW_REQUIRED')}` | "
            f"{item.get('phase', 'REVIEW_REQUIRED')} | "
            f"{item.get('status', 'REVIEW_REQUIRED')} | "
            f"{_refs_text(_evidence_refs(item))} | "
            f"{item.get('impact', '')} |"
        )


def _append_call_flow(lines: list[str], guide: Mapping[str, Any]) -> None:
    branches = _sequence(_mapping(guide.get("call_flow")).get("branches"))
    if not branches:
        lines.append("- REVIEW_REQUIRED: branch-level call flow unavailable.")
        return
    for branch in branches:
        if not isinstance(branch, Mapping):
            continue
        lines.append(
            "- branch: "
            f"{branch.get('id', 'unnamed_branch')} "
            f"phase={branch.get('phase', 'REVIEW_REQUIRED')} "
            f"evidenceRefs={_refs_text(_evidence_refs(branch))} "
            f"condition={branch.get('condition_summary', '')}"
        )
        for action in _sequence(branch.get("actions")):
            if not isinstance(action, Mapping):
                continue
            lines.append(
                "  - action: "
                f"{action.get('operation', 'REVIEW_REQUIRED')} "
                f"dependency={action.get('dependency_ref', 'REVIEW_REQUIRED')} "
                f"evidenceRefs={_refs_text(_evidence_refs(action))}"
            )


def _append_critical_phase(lines: list[str], guide: Mapping[str, Any]) -> None:
    metrics = _mapping(guide.get("phase_risk_metrics"))
    lines.extend(
        [
            f"- branchCount: `{metrics.get('branch_count', 'REVIEW_REQUIRED')}`",
            f"- dmlOperationCount: `{metrics.get('dml_operation_count', 'REVIEW_REQUIRED')}`",
            (
                "- REVIEW_REQUIRED: phase ordering and transaction semantics "
                "require reviewer confirmation."
            ),
        ]
    )


def _append_complexity_risk(lines: list[str], guide: Mapping[str, Any]) -> None:
    metrics = _mapping(guide.get("phase_risk_metrics"))
    lines.extend(
        [
            f"- complexityScore: `{metrics.get('complexity_score', 'REVIEW_REQUIRED')}`",
            f"- branchCount: `{metrics.get('branch_count', 'REVIEW_REQUIRED')}`",
            f"- dmlOperationCount: `{metrics.get('dml_operation_count', 'REVIEW_REQUIRED')}`",
        ]
    )
    for risk in _sequence(metrics.get("risk_flags")):
        if not isinstance(risk, Mapping):
            continue
        lines.append(
            "- risk: "
            f"{risk.get('code', 'REVIEW_REQUIRED')} "
            f"status={risk.get('status', 'REVIEW_REQUIRED')} "
            f"severity={risk.get('severity', 'REVIEW_REQUIRED')} "
            f"evidenceRefs={_refs_text(_evidence_refs(risk))}"
        )


def _append_migration_strategy(lines: list[str], context: GenerationContext) -> None:
    lines.extend(
        [
            "- javaMyBatisReadiness: `draft_notes_only`",
            "- generated_source_application: `not_performed`",
            "- automatic_conversion_completion: `not_claimed`",
            "- target_application_write: `forbidden_without_human_review`",
            (
                "- REVIEW_REQUIRED: Java/MyBatis adoption requires manual review "
                "of evidence and risks."
            ),
        ]
    )
    _append_llm_migration_strategy_insights(lines, context)


def _append_llm_migration_strategy_insights(
    lines: list[str],
    context: GenerationContext,
) -> None:
    payload = context.value("llmAnalysis", {}) or {}
    if not isinstance(payload, Mapping):
        return
    guidance = _sequence(payload.get("conversionGuidance"))
    insights = _sequence(payload.get("migrationGuideInsights"))
    if not guidance and not insights:
        return
    lines.append("- llmInsightBoundary: `LLM_INFERENCE_REVIEW_REQUIRED`")
    for item in guidance:
        if not isinstance(item, Mapping):
            continue
        lines.append(
            "- llmConversionGuidance: "
            f"{item.get('code', 'REVIEW_REQUIRED')} "
            f"status={item.get('status', 'REVIEW_REQUIRED')} "
            f"evidenceRefs={_refs_text(_evidence_refs(item))} "
            f"summary={item.get('summary', '')}"
        )
    for item in insights:
        if not isinstance(item, Mapping):
            continue
        lines.append(
            "- llmMigrationGuideInsight: "
            f"{item.get('section', 'REVIEW_REQUIRED')} "
            f"status={item.get('status', 'REVIEW_REQUIRED')} "
            f"evidenceRefs={_refs_text(_evidence_refs(item))} "
            f"summary={item.get('summary', '')}"
        )


def _append_appendix_mappings(lines: list[str], guide: Mapping[str, Any]) -> None:
    appendix = _mapping(guide.get("appendix_mappings"))
    parameters = _sequence(appendix.get("parameters"))
    result_fields = _sequence(appendix.get("result_fields"))
    lines.append("- parameters:")
    if parameters:
        for parameter in parameters:
            if not isinstance(parameter, Mapping):
                continue
            lines.append(
                "  - "
                f"name={parameter.get('name', 'REVIEW_REQUIRED')} "
                f"sanitizedType={parameter.get('sanitized_type', 'REVIEW_REQUIRED')} "
                f"evidenceRefs={_refs_text(_evidence_refs(parameter))}"
            )
    else:
        lines.append("  - REVIEW_REQUIRED: parameter mapping unavailable.")
    lines.append("- resultFields:")
    if result_fields:
        for field in result_fields:
            if not isinstance(field, Mapping):
                continue
            lines.append(
                "  - "
                f"name={field.get('name', 'REVIEW_REQUIRED')} "
                f"evidenceRefs={_refs_text(_evidence_refs(field))}"
            )
    else:
        lines.append("  - REVIEW_REQUIRED: no result fields supplied.")


def _append_evidence_and_review(
    lines: list[str],
    context: GenerationContext,
    guide: Mapping[str, Any],
) -> None:
    lines.append("- evidenceRefs:")
    evidence_refs = _sequence(guide.get("evidence_refs"))
    if evidence_refs:
        for ref in evidence_refs:
            if not isinstance(ref, Mapping):
                continue
            lines.append(
                "  - "
                f"id={ref.get('id', 'unnamed_evidence')} "
                f"type={ref.get('type', 'REVIEW_REQUIRED')} "
                f"objectRef={ref.get('object_ref', 'REVIEW_REQUIRED')} "
                f"locator={ref.get('locator', 'REVIEW_REQUIRED')}"
            )
    else:
        for ref in context.evidence_refs:
            lines.append(
                "  - "
                f"type={ref.type} objectRef={ref.object_ref} locator={ref.locator}"
            )
    lines.append("- reviewRequiredFindings:")
    unsupported_claims = _sequence(guide.get("unsupported_claim_expectations"))
    if unsupported_claims:
        for claim in unsupported_claims:
            if not isinstance(claim, Mapping):
                continue
            lines.append(
                "  - "
                f"claimCode={claim.get('claim_code', 'REVIEW_REQUIRED')} "
                f"claimType={claim.get('claim_type', 'REVIEW_REQUIRED')} "
                f"status={claim.get('expected_status', 'REVIEW_REQUIRED')} "
                f"obligation={claim.get('obligation', 'REVIEW_REQUIRED')} "
                f"evidenceRefs={_refs_text(_evidence_refs(claim))}"
            )
    else:
        lines.append("  - REVIEW_REQUIRED: unsupported claim review set unavailable.")
    for assumption in context.evidence_assumptions:
        lines.append(f"- assumption: REVIEW_REQUIRED {assumption}")


def _render_placeholder_sections(context: GenerationContext) -> list[str]:
    lines: list[str] = []
    for section_id in P24_REQUIRED_SECTION_IDS:
        lines.extend(
            [
                f"## {section_id}",
                f"- title: {P24_SECTION_TITLES[section_id]}",
                "- REVIEW_REQUIRED: migrationGuide sanitized facts not supplied.",
                "- generated_source_application: `not_performed`",
            ]
        )
        for ref in context.evidence_refs:
            lines.append(f"- evidenceRef: {ref.type} `{ref.object_ref}` locator=`{ref.locator}`")
        lines.append("")
    return lines


def _normalize_thresholds(thresholds: Mapping[str, Any]) -> dict[str, float | int]:
    return {
        report_key: (
            int(thresholds[contract_key])
            if contract_key == "forbidden_storage_findings_max"
            else float(thresholds[contract_key])
        )
        for contract_key, report_key in _THRESHOLD_FIELD_MAP.items()
    }


def _section_coverage(
    scenario: Mapping[str, Any],
    combined_text: str,
) -> dict[str, bool]:
    required_sections = [
        str(section.get("id"))
        for section in _sequence(scenario.get("section_expectations"))
        if isinstance(section, Mapping)
    ] or list(P24_REQUIRED_SECTION_IDS)
    return {
        section_id: f"## {section_id}" in combined_text
        for section_id in required_sections
    }


def _evidence_linked_claim_coverage(
    scenario: Mapping[str, Any],
    combined_text: str,
) -> float:
    items = list(_iter_evidence_claims(scenario))
    return _ratio(
        sum(1 for item in items if _evidence_item_is_rendered(item, combined_text)),
        len(items),
    )


def _dml_matrix_coverage(scenario: Mapping[str, Any], combined_text: str) -> float:
    expected_operations = {str(item) for item in _sequence(scenario.get("expected_dml_operations"))}
    matrix = [
        item
        for item in _sequence(scenario.get("dml_matrix"))
        if isinstance(item, Mapping) and _evidence_item_is_rendered(item, combined_text)
    ]
    covered_operations = {str(item.get("operation")) for item in matrix}
    return _ratio(len(expected_operations & covered_operations), len(expected_operations))


def _branch_call_flow_coverage(scenario: Mapping[str, Any], combined_text: str) -> float:
    branches = [
        branch
        for branch in _sequence(_mapping(scenario.get("call_flow")).get("branches"))
        if isinstance(branch, Mapping)
    ]
    covered = 0
    for branch in branches:
        actions = [
            action
            for action in _sequence(branch.get("actions"))
            if isinstance(action, Mapping)
        ]
        if _evidence_item_is_rendered(branch, combined_text) and all(
            _evidence_item_is_rendered(action, combined_text) for action in actions
        ):
            covered += 1
    return _ratio(covered, len(branches))


def _unsupported_claim_review_required_ratio(
    scenario: Mapping[str, Any],
    combined_text: str,
) -> float:
    claims = [
        claim
        for claim in _sequence(scenario.get("unsupported_claim_expectations"))
        if isinstance(claim, Mapping)
    ]
    covered = sum(1 for claim in claims if _review_required_claim_is_rendered(claim, combined_text))
    return _ratio(covered, len(claims))


def _review_required_findings(
    scenario: Mapping[str, Any],
    combined_text: str,
) -> list[str]:
    findings = []
    for claim in _sequence(scenario.get("unsupported_claim_expectations")):
        if isinstance(claim, Mapping) and _review_required_claim_is_rendered(claim, combined_text):
            findings.append(str(claim.get("claim_code")))
    return findings


def _iter_evidence_claims(scenario: Mapping[str, Any]) -> Sequence[Mapping[str, Any]]:
    items: list[Mapping[str, Any]] = []
    items.extend(_mapping_items(scenario.get("sanitized_facts")))
    for section in _mapping_items(scenario.get("section_expectations")):
        items.append(section)
        items.extend(_mapping_items(section.get("claims")))
    items.extend(_mapping_items(scenario.get("dependency_inventory")))
    items.extend(_mapping_items(scenario.get("dml_matrix")))
    for branch in _mapping_items(_mapping(scenario.get("call_flow")).get("branches")):
        items.append(branch)
        items.extend(_mapping_items(branch.get("actions")))
    items.extend(_mapping_items(_mapping(scenario.get("phase_risk_metrics")).get("risk_flags")))
    appendix = _mapping(scenario.get("appendix_mappings"))
    items.extend(_mapping_items(appendix.get("parameters")))
    items.extend(_mapping_items(appendix.get("result_fields")))
    items.extend(_mapping_items(scenario.get("unsupported_claim_expectations")))
    return items


def _evidence_item_is_rendered(item: Mapping[str, Any], combined_text: str) -> bool:
    evidence_refs = _evidence_refs(item)
    if not evidence_refs or any(ref not in combined_text for ref in evidence_refs):
        return False
    tokens = _identity_tokens(item)
    return not tokens or any(token in combined_text for token in tokens)


def _review_required_claim_is_rendered(
    claim: Mapping[str, Any],
    combined_text: str,
) -> bool:
    return (
        str(claim.get("expected_status")) == "REVIEW_REQUIRED"
        and str(claim.get("claim_code")) in combined_text
        and "REVIEW_REQUIRED" in combined_text
        and _evidence_item_is_rendered(claim, combined_text)
    )


def _identity_tokens(item: Mapping[str, Any]) -> list[str]:
    tokens = []
    for key in (
        "id",
        "object_ref",
        "target_ref",
        "dependency_ref",
        "operation",
        "phase",
        "code",
        "name",
        "fact_type",
        "claim_code",
        "obligation",
    ):
        value = item.get(key)
        if value:
            tokens.append(str(value))
    return tokens


def _quality_report_evidence_refs(scenario: Mapping[str, Any]) -> list[str]:
    expected = _mapping(scenario.get("expected_quality_report")).get("evidenceRefs")
    if isinstance(expected, Sequence) and not isinstance(expected, str | bytes):
        return [str(item) for item in expected]
    return [
        str(ref.get("id"))
        for ref in _mapping_items(scenario.get("evidence_refs"))
        if ref.get("id")
    ]


def _status(*, scores: Mapping[str, float | int], thresholds: Mapping[str, float | int]) -> str:
    if scores["requiredSectionCoverage"] < thresholds["requiredSectionCoverageMin"]:
        return "FAILED"
    if scores["evidenceLinkedClaimCoverage"] < thresholds["evidenceLinkedClaimCoverageMin"]:
        return "FAILED"
    if scores["dmlMatrixCoverage"] < thresholds["dmlMatrixCoverageMin"]:
        return "FAILED"
    if scores["branchCallFlowCoverage"] < thresholds["branchCallFlowCoverageMin"]:
        return "FAILED"
    if (
        scores["unsupportedClaimReviewRequiredRatio"]
        < thresholds["unsupportedClaimReviewRequiredRatioMin"]
    ):
        return "FAILED"
    if scores["storageSafetyFindings"] > thresholds["forbiddenStorageFindingsMax"]:
        return "FAILED"
    return "PASSED"


def _storage_safety_findings(*, payloads: Sequence[Mapping[str, Any]]) -> list[str]:
    findings: list[str] = []
    for payload in payloads:
        findings.extend(
            "FORBIDDEN_STORAGE_FIELD_PRESENT"
            for key in _iter_mapping_keys(payload)
            if key in _FORBIDDEN_STORAGE_KEYS
        )
        serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
        if any(marker in serialized for marker in _FORBIDDEN_TEXT_MARKERS):
            findings.append("PROCEDURE_TEXT_MARKER_PRESENT")
    return findings


def _artifact_payload(artifact: RenderedArtifact | Mapping[str, Any]) -> Mapping[str, Any]:
    if isinstance(artifact, Mapping):
        return artifact
    return artifact.as_validation_payload()


def _artifact_text(artifact: RenderedArtifact | Mapping[str, Any]) -> str:
    if isinstance(artifact, Mapping):
        return json.dumps(artifact, ensure_ascii=False, sort_keys=True, default=str)
    return artifact.content


def _iter_mapping_keys(value: Any) -> Sequence[str]:
    keys: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            keys.append(str(key))
            keys.extend(_iter_mapping_keys(item))
    elif isinstance(value, Sequence) and not isinstance(value, str | bytes):
        for item in value:
            keys.extend(_iter_mapping_keys(item))
    return keys


def _mapping_items(value: Any) -> list[Mapping[str, Any]]:
    return [item for item in _sequence(value) if isinstance(item, Mapping)]


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return value
    return ()


def _evidence_refs(item: Mapping[str, Any]) -> list[str]:
    value = item.get("evidenceRefs") or item.get("evidence_refs") or []
    return [str(ref) for ref in _sequence(value)]


def _refs_text(values: Sequence[Any]) -> str:
    refs = [str(value) for value in values]
    return ", ".join(refs) if refs else "REVIEW_REQUIRED"


def _ratio(numerator: int, denominator: int) -> float:
    if denominator == 0:
        return 1.0
    return numerator / denominator
