from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

FORBIDDEN_STORAGE_KEYS = frozenset(
    {
        "rawprompt",
        "rawspdefinition",
        "rawopenairesponsetext",
        "rawproviderresponsetext",
        "providerresponsetext",
        "rowdata",
        "secrets",
        "secret",
        "password",
        "apikey",
        "token",
    }
)
RAW_TRACE_TEXT_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\braw_prompt\b",
        r"\braw_sp_definition\b",
        r"\braw_openai_response_text\b",
        r"\braw_provider_response_text\b",
        r"\bprovider_response_text\b",
        r"\brow_data\b",
        r"\browData\b",
        r"\b(?:password|secret|token|api[_-]?key)\s*[:=]",
    )
)
SQL_DEFINITION_TEXT_PATTERNS = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bCREATE\s+(?:OR\s+ALTER\s+)?PROC(?:EDURE)?\b",
        r"\bALTER\s+PROC(?:EDURE)?\b",
    )
)
SANITIZED_TEXT = "REDACTED_FOR_STORAGE_REVIEW_REQUIRED"


def storage_safety_findings(
    *,
    payloads: Sequence[Mapping[str, Any]],
    procedure_definition: str = "",
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    for payload in payloads:
        findings.extend(
            {"code": "FORBIDDEN_STORAGE_FIELD_PRESENT"}
            for key in _iter_mapping_keys(payload)
            if _is_forbidden_storage_key(key)
        )
        for text_value in _iter_string_values(payload):
            findings.extend(
                storage_safety_findings_for_text(text_value, procedure_definition)
            )
    return _dedupe_findings(findings)


def storage_safety_findings_for_text(
    value: str,
    procedure_definition: str = "",
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    if procedure_definition and procedure_definition in value:
        findings.append({"code": "PROCEDURE_TEXT_PRESENT"})
    if any(pattern.search(value) for pattern in SQL_DEFINITION_TEXT_PATTERNS):
        findings.append({"code": "PROCEDURE_TEXT_MARKER_PRESENT"})
    if any(pattern.search(value) for pattern in RAW_TRACE_TEXT_PATTERNS):
        findings.append({"code": "RAW_TRACE_OR_SECRET_MARKER_PRESENT"})
    return _dedupe_findings(findings)


def sanitize_value_for_storage(
    value: Any,
    *,
    procedure_definition: str = "",
) -> Any:
    if isinstance(value, str):
        if storage_safety_findings_for_text(value, procedure_definition):
            return SANITIZED_TEXT
        return value
    if isinstance(value, Mapping):
        return {
            key: sanitize_value_for_storage(
                item,
                procedure_definition=procedure_definition,
            )
            for key, item in value.items()
        }
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return [
            sanitize_value_for_storage(
                item,
                procedure_definition=procedure_definition,
            )
            for item in value
        ]
    return value


def _iter_mapping_keys(value: Any) -> list[str]:
    keys: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            keys.append(str(key))
            keys.extend(_iter_mapping_keys(item))
    elif isinstance(value, Sequence) and not isinstance(value, str | bytes):
        for item in value:
            keys.extend(_iter_mapping_keys(item))
    return keys


def _iter_string_values(value: Any) -> list[str]:
    values: list[str] = []
    if isinstance(value, str):
        values.append(value)
    elif isinstance(value, Mapping):
        for item in value.values():
            values.extend(_iter_string_values(item))
    elif isinstance(value, Sequence) and not isinstance(value, str | bytes):
        for item in value:
            values.extend(_iter_string_values(item))
    return values


def _normalize_key(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", value.lower())


def _is_forbidden_storage_key(value: str) -> bool:
    normalized = _normalize_key(value)
    if normalized in FORBIDDEN_STORAGE_KEYS:
        return True
    if normalized.endswith(("password", "secret", "token", "apikey")):
        return True
    return normalized.startswith(("password", "secret", "apikey"))


def _dedupe_findings(findings: Sequence[Mapping[str, str]]) -> list[dict[str, str]]:
    seen: set[str] = set()
    deduped: list[dict[str, str]] = []
    for finding in findings:
        code = str(finding.get("code") or "")
        if not code or code in seen:
            continue
        deduped.append({"code": code})
        seen.add(code)
    return deduped
