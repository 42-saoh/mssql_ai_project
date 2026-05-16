from __future__ import annotations

import pytest
from ai_agent_domain import ArtifactStatus
from api_app.contracts import (
    registry_storage_type,
    validation_storage_result,
)
from api_app.lifecycle import artifact_status_after_validation


def test_validation_status_mapping_to_storage_result() -> None:
    assert validation_storage_result("PASSED") == "PASS"
    assert validation_storage_result("FAILED") == "FAIL"
    assert validation_storage_result("REVIEW_REQUIRED") == "FAIL"
    assert (
        artifact_status_after_validation("REVIEW_REQUIRED", ArtifactStatus.DRAFT)
        == ArtifactStatus.DRAFT
    )


def test_registry_type_mapping_to_storage_contract() -> None:
    assert registry_storage_type("PROMPT") == "PROMPT"
    assert registry_storage_type("TEMPLATE") == "TEMPLATE"
    assert registry_storage_type("POLICY") == "MODEL_POLICY"
    assert registry_storage_type("DB_PROFILE") == "DB_PROFILE_POLICY"
    assert registry_storage_type("GENERATOR") == "MODEL_POLICY"


def test_unknown_mapping_value_is_explicit_error() -> None:
    with pytest.raises(ValueError):
        validation_storage_result("PASS")
    with pytest.raises(ValueError):
        registry_storage_type("MODEL_POLICY")
