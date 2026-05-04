from __future__ import annotations


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
