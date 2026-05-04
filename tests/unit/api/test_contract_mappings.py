from __future__ import annotations

import pytest
from api_app.contracts import (
    approval_decision_mapping,
    registry_storage_type,
    validation_storage_result,
)


def test_approval_decision_mapping_preserves_openapi_and_storage_values() -> None:
    assert approval_decision_mapping("APPROVE").storage_decision == "APPROVED"
    assert approval_decision_mapping("REJECT").storage_decision == "REJECTED"

    request_changes = approval_decision_mapping("REQUEST_CHANGES")

    assert request_changes.api_decision == "REQUEST_CHANGES"
    assert request_changes.storage_decision == "REJECTED"
    assert request_changes.artifact_status == "REVIEW_PENDING"


def test_validation_status_mapping_to_storage_result() -> None:
    assert validation_storage_result("PASSED") == "PASS"
    assert validation_storage_result("FAILED") == "FAIL"
    assert validation_storage_result("REVIEW_REQUIRED") == "FAIL"


def test_registry_type_mapping_to_storage_contract() -> None:
    assert registry_storage_type("PROMPT") == "PROMPT"
    assert registry_storage_type("TEMPLATE") == "TEMPLATE"
    assert registry_storage_type("POLICY") == "MODEL_POLICY"
    assert registry_storage_type("DB_PROFILE") == "DB_PROFILE_POLICY"
    assert registry_storage_type("GENERATOR") == "MODEL_POLICY"


def test_unknown_mapping_value_is_explicit_error() -> None:
    with pytest.raises(ValueError):
        approval_decision_mapping("APPROVED")
    with pytest.raises(ValueError):
        validation_storage_result("PASS")
    with pytest.raises(ValueError):
        registry_storage_type("MODEL_POLICY")
