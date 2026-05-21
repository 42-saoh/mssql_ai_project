from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ValidationSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    BLOCKER = "BLOCKER"


class ValidationCheckResult(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


class ValidationStatus(StrEnum):
    PASSED = "PASSED"
    FAILED = "FAILED"
    REVIEW_REQUIRED = "REVIEW_REQUIRED"


@dataclass(frozen=True)
class ValidationRule:
    id: str
    severity: ValidationSeverity
    applies_to: tuple[str, ...]
    description: str


@dataclass(frozen=True)
class ValidationCheck:
    rule_id: str
    severity: ValidationSeverity
    result: ValidationCheckResult
    message: str

    def as_dict(self) -> dict[str, str]:
        return {
            "ruleId": self.rule_id,
            "severity": self.severity.value,
            "result": self.result.value,
            "message": self.message,
        }


@dataclass(frozen=True)
class ValidationReport:
    artifact_id: str
    status: ValidationStatus
    checks: tuple[ValidationCheck, ...]
    missing_evidence: tuple[str, ...] = ()
    manual_review_points: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def failed_checks(self) -> tuple[ValidationCheck, ...]:
        return tuple(check for check in self.checks if check.result == ValidationCheckResult.FAIL)

    @property
    def requires_review(self) -> bool:
        return self.status == ValidationStatus.REVIEW_REQUIRED

    def as_dict(self) -> dict[str, Any]:
        return {
            "artifactId": self.artifact_id,
            "status": self.status.value,
            "checks": [check.as_dict() for check in self.checks],
            "missingEvidence": list(self.missing_evidence),
            "qualityCaveats": list(self.manual_review_points),
            "metadata": dict(self.metadata),
        }
