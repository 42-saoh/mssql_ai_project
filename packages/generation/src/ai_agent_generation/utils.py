from __future__ import annotations

import re


def snake_to_lower_camel(value: str) -> str:
    parts = [part.lower() for part in value.split("_") if part]
    if not parts:
        return ""
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


def upper_first(value: str) -> str:
    if not value:
        return value
    return value[0].upper() + value[1:]


def java_type_for_db_type(db_type: str) -> str:
    normalized = db_type.strip().lower().split("(", 1)[0]
    mapping = {
        "char": "String",
        "varchar": "String",
        "nchar": "String",
        "nvarchar": "String",
        "text": "String",
        "ntext": "String",
        "tinyint": "Integer",
        "smallint": "Integer",
        "int": "Integer",
        "bigint": "Long",
        "decimal": "BigDecimal",
        "numeric": "BigDecimal",
        "money": "BigDecimal",
        "smallmoney": "BigDecimal",
        "bit": "Boolean",
        "date": "LocalDate",
        "datetime": "LocalDateTime",
        "datetime2": "LocalDateTime",
        "smalldatetime": "LocalDateTime",
        "time": "LocalTime",
        "uniqueidentifier": "String",
        "binary": "byte[]",
        "varbinary": "byte[]",
        "image": "byte[]",
    }
    return mapping.get(normalized, "String")


def java_imports_for_types(java_types: set[str]) -> tuple[str, ...]:
    imports = []
    if "BigDecimal" in java_types:
        imports.append("java.math.BigDecimal")
    if "LocalDate" in java_types:
        imports.append("java.time.LocalDate")
    if "LocalDateTime" in java_types:
        imports.append("java.time.LocalDateTime")
    if "LocalTime" in java_types:
        imports.append("java.time.LocalTime")
    return tuple(imports)


def korean_entity_label(description: str, fallback: str) -> str:
    if " 목록" in description:
        prefix = description.split(" 목록", 1)[0].strip()
        if prefix:
            return prefix
    if " 초안" in description:
        prefix = description.split(" 초안", 1)[0].strip()
        if prefix:
            return prefix
    return fallback


def ensure_trailing_newline(text: str) -> str:
    return text if text.endswith("\n") else f"{text}\n"


def draft_quality_text(text: str) -> str:
    """Render machine uncertainty markers as draft-quality caveat language."""
    replacements = (
        ("REVIEW_REQUIRED:", "근거 보강 필요:"),
        ("REVIEW_REQUIRED는", "근거 보강 필요는"),
        ("REVIEW_REQUIRED??", "근거 보강 필요는 "),
        ("REVIEW_REQUIRED items", "Evidence caveat items"),
        ("REVIEW_REQUIRED caveats", "evidence caveats"),
        ("REVIEW_REQUIRED dependencies", "evidence-caveated dependencies"),
        ("status=REVIEW_REQUIRED", "status=evidence_caveat"),
        ("상태=REVIEW_REQUIRED", "상태=근거 보강 필요"),
        ("상태 REVIEW_REQUIRED:", "품질 caveat:"),
        ("- 가정: REVIEW_REQUIRED ", "- 가정: 근거 보강 필요 "),
        ("LLM_INFERENCE_REVIEW_REQUIRED", "LLM_INFERENCE_EVIDENCE_CAVEAT"),
        ("_REVIEW_REQUIRED", "_EVIDENCE_CAVEAT"),
        ("review marker claim", "evidence caveat claim"),
        ("review marker", "evidence caveat"),
        ("Review marker", "Evidence caveat"),
        ("reviewMarkers", "evidenceCaveats"),
        ("검토 마커", "근거 caveat"),
        ("검토 전까지", "근거 보강 전까지"),
        ("검토합니다", "근거를 보강합니다"),
    )
    rendered = text
    for old, new in replacements:
        rendered = rendered.replace(old, new)
    return re.sub(r"(?<![A-Za-z0-9_])REVIEW_REQUIRED(?![A-Za-z0-9_])", "근거 보강 필요", rendered)
