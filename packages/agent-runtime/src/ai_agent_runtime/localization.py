from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

KOREAN_OUTPUT_INSTRUCTION = (
    "Human-readable free-text values must be written in Korean (ko-KR). Preserve "
    "machine contract identifiers exactly: JSON keys, enum/status/code values, section ids, "
    "artifact types, evidence refs, registry refs, SQL identifiers, and Java identifiers."
)
LANGUAGE_REVIEW_MARKER_CODE = "LLM_OUTPUT_LANGUAGE_REVIEW_REQUIRED"
LANGUAGE_REVIEW_MESSAGE = (
    "일부 사람이 읽는 자유 텍스트가 한국어가 아니어서 결과 검토가 필요합니다. "
    "JSON 키, enum/status/code, evidence ref 같은 기계 계약 식별자는 그대로 유지했습니다."
)

_HANGUL_RE = re.compile(r"[가-힣]")
_LATIN_WORD_RE = re.compile(r"[A-Za-z]{3,}")
_CONTRACT_TOKEN_RE = re.compile(r"[A-Z0-9_./:@-]+")
_HUMAN_TEXT_KEYS = {"summary", "message", "whatToExtractNext"}
_HUMAN_LIST_KEYS = {"assumptions", "reviewReasons"}


def contains_korean(value: Any) -> bool:
    return bool(_HANGUL_RE.search(str(value or "")))


def human_text_needs_korean(value: Any) -> bool:
    text = str(value or "").strip()
    if not text or contains_korean(text):
        return False
    if _CONTRACT_TOKEN_RE.fullmatch(text):
        return False
    return bool(_LATIN_WORD_RE.search(text))


def korean_language_review_paths(payload: Any, *, path: str = "$") -> list[str]:
    findings: list[str] = []
    if isinstance(payload, Mapping):
        for key, value in payload.items():
            key_text = str(key)
            child_path = f"{path}.{key_text}"
            if key_text in _HUMAN_TEXT_KEYS and human_text_needs_korean(value):
                findings.append(child_path)
            elif key_text in _HUMAN_LIST_KEYS and isinstance(value, list | tuple):
                for index, item in enumerate(value):
                    if human_text_needs_korean(item):
                        findings.append(f"{child_path}[{index}]")
            else:
                findings.extend(korean_language_review_paths(value, path=child_path))
    elif isinstance(payload, list | tuple):
        for index, item in enumerate(payload):
            findings.extend(korean_language_review_paths(item, path=f"{path}[{index}]"))
    return findings


def append_korean_language_review_marker(
    output: dict[str, Any],
    *,
    evidence_refs: list[str] | tuple[str, ...],
) -> dict[str, Any]:
    markers = output.setdefault("reviewMarkers", [])
    if not isinstance(markers, list):
        return output
    if any(
        isinstance(marker, dict)
        and marker.get("code") == LANGUAGE_REVIEW_MARKER_CODE
        for marker in markers
    ):
        return output
    refs = [str(ref) for ref in evidence_refs if str(ref).strip()]
    markers.append(
        {
            "code": LANGUAGE_REVIEW_MARKER_CODE,
            "message": LANGUAGE_REVIEW_MESSAGE,
            "status": "REVIEW_REQUIRED",
            "evidenceRefs": refs[:1],
        }
    )
    return output
