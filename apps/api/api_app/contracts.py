from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

ApprovalDecision = Literal["APPROVE", "REJECT", "REQUEST_CHANGES"]
ApprovalStorageDecision = Literal["APPROVED", "REJECTED"]
ValidationStatus = Literal["PASSED", "FAILED", "REVIEW_REQUIRED"]
ValidationStorageResult = Literal["PASS", "FAIL"]
RegistryType = Literal["PROMPT", "TEMPLATE", "POLICY", "DB_PROFILE", "GENERATOR"]
RegistryStorageType = Literal["PROMPT", "TEMPLATE", "MODEL_POLICY", "DB_PROFILE_POLICY"]


@dataclass(frozen=True)
class ApprovalDecisionMapping:
    api_decision: ApprovalDecision
    storage_decision: ApprovalStorageDecision
    artifact_status: str
    persistence_note: str


def approval_decision_mapping(decision: str) -> ApprovalDecisionMapping:
    if decision == "APPROVE":
        return ApprovalDecisionMapping(
            api_decision="APPROVE",
            storage_decision="APPROVED",
            artifact_status="APPROVED",
            persistence_note="OpenAPI APPROVE maps directly to DDL APPROVED.",
        )
    if decision == "REJECT":
        return ApprovalDecisionMapping(
            api_decision="REJECT",
            storage_decision="REJECTED",
            artifact_status="REJECTED",
            persistence_note="OpenAPI REJECT maps directly to DDL REJECTED.",
        )
    if decision == "REQUEST_CHANGES":
        return ApprovalDecisionMapping(
            api_decision="REQUEST_CHANGES",
            storage_decision="REJECTED",
            artifact_status="REVIEW_PENDING",
            persistence_note=(
                "DDL has no REQUEST_CHANGES value; persist as REJECTED and keep "
                "apiDecision=REQUEST_CHANGES in checklist/result JSON."
            ),
        )
    raise ValueError(f"Unsupported approval decision: {decision}")


def validation_storage_result(status: str) -> ValidationStorageResult:
    if status == "PASSED":
        return "PASS"
    if status in {"FAILED", "REVIEW_REQUIRED"}:
        return "FAIL"
    raise ValueError(f"Unsupported validation status: {status}")


def registry_storage_type(registry_type: str) -> RegistryStorageType:
    mapping: dict[str, RegistryStorageType] = {
        "PROMPT": "PROMPT",
        "TEMPLATE": "TEMPLATE",
        "POLICY": "MODEL_POLICY",
        "DB_PROFILE": "DB_PROFILE_POLICY",
        "GENERATOR": "MODEL_POLICY",
    }
    try:
        return mapping[registry_type]
    except KeyError as exc:
        raise ValueError(f"Unsupported registry type: {registry_type}") from exc
