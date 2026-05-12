from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ai_agent_runtime.models import (
    AgentRunPayload,
    LlmSemanticAnalysisOutput,
    stable_json_hash,
)
from ai_agent_runtime.storage_safety import storage_safety_findings

P23_SUITE_ID = "p23_llm_sp_analysis_quality"
LLM_INFERENCE_EVIDENCE_TYPE = "LLM_INFERENCE"

_OUTPUT_FIELDS = (
    "businessRules",
    "modernizationPoints",
    "riskFlags",
    "reviewMarkers",
    "conversionGuidance",
    "migrationGuideInsights",
)
_GUIDE_CONVERSION_FIELDS = ("conversionGuidance", "migrationGuideInsights")
_KEY_FIELDS = {
    "businessRules": "category",
    "modernizationPoints": "code",
    "riskFlags": "code",
    "reviewMarkers": "code",
    "conversionGuidance": "code",
    "migrationGuideInsights": "section",
}
def evaluate_p23_semantic_quality(
    *,
    scenario: Mapping[str, Any],
    run: AgentRunPayload,
    thresholds: Mapping[str, Any],
    additional_storage_payloads: Sequence[Mapping[str, Any]] = (),
) -> dict[str, Any]:
    expected_output = _normalize_output(scenario["golden_expected_semantic_output"])
    actual_output = _normalize_output(run.structured_output)
    fact_ids = frozenset(str(fact["id"]) for fact in scenario["deterministic_facts"])

    semantic_recall = _semantic_recall(expected_output, actual_output)
    guide_conversion_recall = _semantic_recall(
        expected_output,
        actual_output,
        field_names=_GUIDE_CONVERSION_FIELDS,
    )
    evidence_discipline = _evidence_discipline(actual_output, fact_ids)
    validator_results = _validator_results(
        scenario.get("unsupported_claim_expectations", ()),
        actual_output,
    )
    unreviewed_overclaims = sum(
        1 for result in validator_results if result["status"] != "REVIEW_REQUIRED"
    )

    storage_findings = storage_safety_findings(
        payloads=(run.to_storage_dict(), *additional_storage_payloads),
        procedure_definition=str(
            scenario.get("transient_model_input", {}).get("procedure_definition", "")
        ),
    )
    normalized_thresholds = _normalize_thresholds(thresholds)
    base_report = {
        "suite": P23_SUITE_ID,
        "fixtureId": scenario["fixture_id"],
        "targetRef": scenario["target_ref"],
        "productionReady": False,
        "status": _status(
            scores={
                "semanticRecall": semantic_recall,
                "guideConversionRecall": guide_conversion_recall,
                "evidenceDiscipline": evidence_discipline,
                "unreviewedOverclaims": unreviewed_overclaims,
                "storageSafetyFindings": len(storage_findings),
            },
            thresholds=normalized_thresholds,
        ),
        "scores": {
            "semanticRecall": semantic_recall,
            "guideConversionRecall": guide_conversion_recall,
            "evidenceDiscipline": evidence_discipline,
            "unreviewedOverclaims": unreviewed_overclaims,
            "storageSafetyFindings": len(storage_findings),
        },
        "thresholds": normalized_thresholds,
        "evidenceRefs": [
            {
                "type": LLM_INFERENCE_EVIDENCE_TYPE,
                "objectRef": run.model_invocation.output_hash,
                "locator": "agent-runtime.modelInvocation.outputHash",
            }
        ],
        "validatorResults": validator_results,
        "storageSafety": {
            "findingCount": len(storage_findings),
            "findingCodes": sorted({finding["code"] for finding in storage_findings}),
        },
    }

    report_findings = storage_safety_findings(
        payloads=(base_report,),
        procedure_definition=str(
            scenario.get("transient_model_input", {}).get("procedure_definition", "")
        ),
    )
    if report_findings:
        base_report["storageSafety"] = {
            "findingCount": len(storage_findings) + len(report_findings),
            "findingCodes": sorted(
                {finding["code"] for finding in (*storage_findings, *report_findings)}
            ),
        }
        base_report["scores"]["storageSafetyFindings"] = base_report["storageSafety"][
            "findingCount"
        ]
        base_report["status"] = _status(
            scores=base_report["scores"],
            thresholds=normalized_thresholds,
        )

    base_report["reportHash"] = stable_json_hash(base_report)
    return base_report


def _normalize_output(output: Mapping[str, Any]) -> dict[str, Any]:
    return LlmSemanticAnalysisOutput.model_validate(output).to_storage_dict()


def _normalize_thresholds(thresholds: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "semanticRecallMin": float(thresholds["semantic_recall_min"]),
        "guideConversionRecallMin": float(
            thresholds.get("guide_conversion_recall_min", thresholds["semantic_recall_min"])
        ),
        "evidenceDisciplineMin": float(thresholds["evidence_discipline_min"]),
        "unreviewedOverclaimsMax": int(thresholds["unreviewed_overclaims_max"]),
        "storageSafetyFindingsMax": int(thresholds["storage_safety_findings_max"]),
    }


def _semantic_recall(
    expected_output: Mapping[str, Any],
    actual_output: Mapping[str, Any],
    *,
    field_names: Sequence[str] = _OUTPUT_FIELDS,
) -> float:
    expected_items = [
        (field_name, expected_item)
        for field_name in field_names
        for expected_item in expected_output[field_name]
    ]
    if not expected_items:
        return 1.0

    recalled = sum(
        1
        for field_name, expected_item in expected_items
        if _has_recalled_item(
            expected_item=expected_item,
            actual_items=actual_output[field_name],
            key_field=_KEY_FIELDS[field_name],
        )
    )
    return recalled / len(expected_items)


def _has_recalled_item(
    *,
    expected_item: Mapping[str, Any],
    actual_items: Sequence[Mapping[str, Any]],
    key_field: str,
) -> bool:
    expected_key = str(expected_item.get(key_field) or "")
    expected_evidence = set(_evidence_refs(expected_item))
    for actual_item in actual_items:
        actual_key = str(actual_item.get(key_field) or "")
        if expected_key and actual_key == expected_key:
            return True
        if expected_evidence and expected_evidence.intersection(_evidence_refs(actual_item)):
            return True
    return False


def _evidence_discipline(output: Mapping[str, Any], fact_ids: frozenset[str]) -> float:
    claim_items = [
        item
        for field_name in _OUTPUT_FIELDS
        for item in output[field_name]
    ]
    if not claim_items:
        return 1.0

    disciplined = sum(
        1
        for item in claim_items
        if (evidence_refs := set(_evidence_refs(item))) and evidence_refs <= fact_ids
    )
    return disciplined / len(claim_items)


def _validator_results(
    unsupported_claims: Sequence[Mapping[str, Any]],
    output: Mapping[str, Any],
) -> list[dict[str, Any]]:
    marker_status_by_code = {
        str(marker.get("code")): str(marker.get("status"))
        for marker in output["reviewMarkers"]
    }
    return [
        {
            "claimType": str(claim["claim_type"]),
            "claimCode": str(claim["claim_code"]),
            "status": marker_status_by_code.get(str(claim["claim_code"]), "MISSING"),
            "expectedStatus": str(claim["expected_status"]),
            "result": (
                "PASS"
                if marker_status_by_code.get(str(claim["claim_code"]))
                == str(claim["expected_status"])
                else "FAIL"
            ),
        }
        for claim in unsupported_claims
    ]


def _evidence_refs(item: Mapping[str, Any]) -> list[str]:
    value = item.get("evidenceRefs") or item.get("evidence_refs") or []
    return [str(ref) for ref in value]


def _status(*, scores: Mapping[str, float | int], thresholds: Mapping[str, Any]) -> str:
    if scores["semanticRecall"] < thresholds["semanticRecallMin"]:
        return "FAILED"
    if scores["guideConversionRecall"] < thresholds["guideConversionRecallMin"]:
        return "FAILED"
    if scores["evidenceDiscipline"] < thresholds["evidenceDisciplineMin"]:
        return "FAILED"
    if scores["unreviewedOverclaims"] > thresholds["unreviewedOverclaimsMax"]:
        return "FAILED"
    if scores["storageSafetyFindings"] > thresholds["storageSafetyFindingsMax"]:
        return "FAILED"
    return "PASSED"
