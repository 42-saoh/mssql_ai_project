from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from typing import Any

PROFILE_DATABASES = {
    "master": "master",
    "plf": "PLF",
    "ppm": "PPM",
}


PATTERN_CHECKS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("dynamic_sql", re.compile(r"\bsp_executesql\b|EXEC\s*\(@|EXECUTE\s*\(@", re.IGNORECASE)),
    ("temp_table", re.compile(r"(?<!#)#(?!#)[A-Za-z0-9_]+", re.IGNORECASE)),
    ("try_catch", re.compile(r"\bBEGIN\s+TRY\b|\bBEGIN\s+CATCH\b", re.IGNORECASE)),
    ("cursor", re.compile(r"\bCURSOR\b", re.IGNORECASE)),
    (
        "nested_procedure_call",
        re.compile(r"\bEXEC(?:UTE)?\s+(?:\[?\w+\]?\.)?\[?(?:usp_|sp_)", re.IGNORECASE),
    ),
    (
        "transaction",
        re.compile(
            r"\bBEGIN\s+TRAN(?:SACTION)?\b|\bCOMMIT\s+TRAN\b|\bROLLBACK\s+TRAN\b",
            re.IGNORECASE,
        ),
    ),
    (
        "joins_or_branching",
        re.compile(r"\bJOIN\b|\bIF\b|\bELSE\b|\bCASE\b|\bWHILE\b", re.IGNORECASE),
    ),
    (
        "simple_dml_or_select",
        re.compile(r"\bSELECT\b|\bINSERT\b|\bUPDATE\b|\bDELETE\b", re.IGNORECASE),
    ),
)


COMPLEX_PATTERNS = {
    "dynamic_sql",
    "temp_table",
    "try_catch",
    "cursor",
    "nested_procedure_call",
}
MEDIUM_PATTERNS = {"joins_or_branching", "transaction"}


def source_database_for_profile(
    profile_id: str,
    *,
    payload: dict[str, Any] | None = None,
) -> str:
    profile_databases = payload.get("profileDatabases", {}) if payload else {}
    database = profile_databases.get(profile_id) if isinstance(profile_databases, dict) else None
    if isinstance(database, str) and database.strip():
        return database.strip()
    return PROFILE_DATABASES.get(profile_id, profile_id)


def source_context(
    arguments: dict[str, Any],
    *,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile_id = str(arguments["dbProfileId"])
    return {
        "sourceProfile": profile_id,
        "sourceDatabase": source_database_for_profile(profile_id, payload=payload),
    }


def definition_metadata(definition: Any, *, is_encrypted: bool = False) -> dict[str, Any]:
    if is_encrypted or definition is None:
        return {
            "available": False,
            "hash": None,
            "length": None,
            "detectedPatterns": [],
            "isEncrypted": bool(is_encrypted),
        }

    text = str(definition)
    patterns = detect_definition_patterns(text)
    return {
        "available": bool(text),
        "hash": sha256(text) if text else None,
        "length": len(text) if text else 0,
        "detectedPatterns": patterns,
        "isEncrypted": False,
    }


def detect_definition_patterns(definition: str) -> list[str]:
    return [name for name, pattern in PATTERN_CHECKS if pattern.search(definition)]


def classify_procedure_complexity(
    *,
    definition: Any,
    is_encrypted: bool,
    parameter_count: int,
    dependency_count: int,
) -> str:
    patterns = set(definition_metadata(definition, is_encrypted=is_encrypted)["detectedPatterns"])
    if patterns & COMPLEX_PATTERNS or dependency_count >= 5:
        return "complex"
    if patterns & MEDIUM_PATTERNS or parameter_count >= 3 or dependency_count >= 2:
        return "medium"
    return "simple"


def procedure_dependency_summary(
    dependencies: Iterable[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    summary = {
        "tables": [],
        "views": [],
        "functions": [],
        "procedures": [],
        "unresolved": [],
    }
    for dependency in dependencies:
        object_type = str(dependency.get("objectType", "")).upper()
        item = {
            "schema": dependency.get("schema"),
            "name": dependency.get("name"),
            "dependencyType": dependency.get("dependencyType", "UNKNOWN"),
            "reviewStatus": dependency.get("reviewStatus", "CONFIRMED"),
        }
        if dependency.get("resolutionStatus") is not None:
            item["resolutionStatus"] = dependency.get("resolutionStatus")
        if dependency.get("resolutionStrategy") is not None:
            item["resolutionStrategy"] = dependency.get("resolutionStrategy")
        for key in (
            "database",
            "server",
            "referencedDatabase",
            "referencedServer",
            "sourceScope",
        ):
            if dependency.get(key) is not None:
                item[key] = dependency.get(key)
        if not item["name"]:
            summary["unresolved"].append(item)
        elif object_type == "TABLE":
            summary["tables"].append(item)
        elif object_type == "VIEW":
            summary["views"].append(item)
        elif object_type == "FUNCTION":
            summary["functions"].append(item)
        elif object_type == "PROCEDURE":
            summary["procedures"].append(item)
        else:
            summary["unresolved"].append(item)
    return summary


def procedure_inventory_item(
    procedure: dict[str, Any],
    *,
    evidence_refs: list[dict[str, Any]],
) -> dict[str, Any]:
    parameters = procedure.get("parameters", [])
    dependencies = procedure.get("dependencies", [])
    definition = procedure.get("definition")
    is_encrypted = bool(procedure.get("isEncrypted", False))
    definition_info = definition_metadata(definition, is_encrypted=is_encrypted)
    dependency_summary = procedure_dependency_summary(dependencies)
    review_required = (
        not definition_info["available"]
        or any(dep.get("reviewStatus") == "REVIEW_REQUIRED" for dep in dependencies)
        or bool(dependency_summary["unresolved"])
    )
    caveats = []
    if not definition_info["available"]:
        caveats.append("definition_unavailable")
    if any(dep.get("isAmbiguous") for dep in dependencies):
        caveats.append("ambiguous_dependency_metadata")
    if dependency_summary["unresolved"] or any(
        dep.get("reviewStatus") == "REVIEW_REQUIRED" for dep in dependencies
    ):
        caveats.append("DEPENDENCY_METADATA_INCOMPLETE")

    return {
        "schema": procedure["schema"],
        "name": procedure["name"],
        "objectType": "PROCEDURE",
        "complexity": classify_procedure_complexity(
            definition=definition,
            is_encrypted=is_encrypted,
            parameter_count=len(parameters),
            dependency_count=len(dependencies),
        ),
        "definition": definition_info,
        "parameterCount": len(parameters),
        "parameters": parameters,
        "dependencyCount": len(dependencies),
        "dependencySummary": dependency_summary,
        "caveats": caveats,
        "reviewRequired": review_required,
        "evidenceRefs": evidence_refs,
    }


def table_inventory_item(
    table: dict[str, Any],
    *,
    related_procedures: list[dict[str, Any]],
    evidence_refs: list[dict[str, Any]],
) -> dict[str, Any]:
    constraints = table.get("constraints", [])
    indexes = table.get("indexes", [])
    extended_properties = table.get("extendedProperties", [])
    primary_key = next(
        (constraint for constraint in constraints if constraint.get("constraintType") == "PK"),
        None,
    )
    foreign_keys = [
        constraint for constraint in constraints if constraint.get("constraintType") == "FK"
    ]
    review_required = table.get("descriptionStatus") == "REVIEW_REQUIRED" or any(
        column.get("descriptionStatus") == "REVIEW_REQUIRED" for column in table.get("columns", [])
    )
    return {
        "schema": table["schema"],
        "name": table["name"],
        "objectType": "TABLE",
        "logicalName": table.get("logicalName"),
        "descriptionStatus": table.get("descriptionStatus", "CONFIRMED"),
        "columnCount": len(table.get("columns", [])),
        "keyIndexConstraintSummary": {
            "primaryKey": primary_key,
            "foreignKeyCount": len(foreign_keys),
            "indexCount": len(indexes),
            "constraintCount": len(constraints),
        },
        "extendedPropertyCount": len(extended_properties),
        "relatedProcedures": related_procedures,
        "caveats": ["description_review_required"] if review_required else [],
        "reviewRequired": review_required,
        "evidenceRefs": evidence_refs,
    }


def module_inventory_item(
    module: dict[str, Any],
    *,
    object_type: str,
    evidence_refs: list[dict[str, Any]],
) -> dict[str, Any]:
    definition_info = definition_metadata(
        module.get("definition"),
        is_encrypted=bool(module.get("isEncrypted", False)),
    )
    dependencies = module.get("dependencies", [])
    dependency_summary = procedure_dependency_summary(dependencies)
    caveats = [] if definition_info["available"] else ["definition_unavailable"]
    if dependency_summary["unresolved"] or any(
        dep.get("reviewStatus") == "REVIEW_REQUIRED" for dep in dependencies
    ):
        caveats.append("DEPENDENCY_METADATA_INCOMPLETE")
    return {
        "schema": module["schema"],
        "name": module["name"],
        "objectType": object_type,
        "definition": definition_info,
        "dependencyCount": len(dependencies),
        "dependencySummary": dependency_summary,
        "caveats": caveats,
        "reviewRequired": bool(caveats),
        "evidenceRefs": evidence_refs,
    }


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
