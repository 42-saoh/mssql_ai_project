from __future__ import annotations

from ai_agent_analysis.models import (
    CanonicalConversionBlocker,
    EvidenceStatus,
    StoredProcedureAnalysisResult,
)


def canonical_conversion_blockers() -> list[CanonicalConversionBlocker]:
    return [
        CanonicalConversionBlocker(
            code="DOMAIN_CONTRACT_MISSING",
            message=(
                "tasks/0003 requests CanonicalAnalysisModel expansion, but this worker boundary "
                "marks packages/domain as read-only."
            ),
            target_path="packages/domain/src/ai_agent_domain/models.py",
        )
    ]


def to_canonical_candidate(result: StoredProcedureAnalysisResult) -> dict:
    return {
        "target_contract": "CanonicalAnalysisModel",
        "status": EvidenceStatus.REVIEW_REQUIRED.value,
        "blockers": [
            blocker.model_dump(mode="json") for blocker in canonical_conversion_blockers()
        ],
        "analysis_local": result.model_dump(mode="json"),
    }
