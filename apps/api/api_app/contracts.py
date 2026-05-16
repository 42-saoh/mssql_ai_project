from __future__ import annotations

from typing import Literal

ValidationStatus = Literal["PASSED", "FAILED", "REVIEW_REQUIRED"]
ValidationStorageResult = Literal["PASS", "FAIL"]
RegistryType = Literal["PROMPT", "TEMPLATE", "POLICY", "DB_PROFILE", "GENERATOR"]
RegistryStorageType = Literal["PROMPT", "TEMPLATE", "MODEL_POLICY", "DB_PROFILE_POLICY"]


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
