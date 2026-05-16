from __future__ import annotations

from typing import Any, Mapping


def canonical_target_key(
    *,
    db_profile_id: str | None,
    object_type: str | None,
    schema: str | None,
    name: str | None,
    database: str | None = None,
) -> str | None:
    profile = _normalize_part(db_profile_id)
    obj_type = _normalize_part(object_type)
    schema_part = _normalize_part(schema)
    name_part = _normalize_part(name)
    if not profile or not obj_type or not schema_part or not name_part:
        return None
    database_part = _normalize_part(database) or "-"
    return f"mssql:{profile}:{database_part}:{obj_type}:{schema_part}.{name_part}"


def target_key_for_target(
    db_profile_id: str | None,
    target: Mapping[str, Any] | None,
    *,
    database: str | None = None,
) -> str | None:
    if not isinstance(target, Mapping):
        return None
    return canonical_target_key(
        db_profile_id=db_profile_id,
        database=database,
        object_type=str(target.get("type") or ""),
        schema=str(target.get("schema") or ""),
        name=str(target.get("name") or ""),
    )


def target_key_for_ref(
    *,
    db_profile_id: str | None,
    target_ref: str | None,
    object_type: str | None = "PROCEDURE",
    database: str | None = None,
) -> str | None:
    parsed_database, schema, name = parse_object_ref(target_ref)
    return canonical_target_key(
        db_profile_id=db_profile_id,
        database=database or parsed_database,
        object_type=object_type,
        schema=schema,
        name=name,
    )


def parse_object_ref(target_ref: str | None) -> tuple[str | None, str | None, str | None]:
    parts = [
        _strip_identifier_quotes(part)
        for part in str(target_ref or "").strip().split(".")
        if part.strip()
    ]
    if len(parts) >= 3:
        return parts[-3], parts[-2], parts[-1]
    if len(parts) == 2:
        return None, parts[0], parts[1]
    return None, None, parts[0] if parts else None


def _normalize_part(value: str | None) -> str:
    cleaned = _strip_identifier_quotes(str(value or "").strip())
    return cleaned.lower()


def _strip_identifier_quotes(value: str) -> str:
    cleaned = value.strip()
    if len(cleaned) >= 2:
        pairs = {("[", "]"), ('"', '"'), ("'", "'"), ("`", "`")}
        if (cleaned[0], cleaned[-1]) in pairs:
            return cleaned[1:-1].strip()
    return cleaned
