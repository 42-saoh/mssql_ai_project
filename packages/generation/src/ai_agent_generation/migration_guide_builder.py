from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ai_agent_generation.migration_guide import P24_REQUIRED_SECTION_IDS

_DML_ORDER = ("SELECT", "INSERT", "UPDATE", "DELETE", "MERGE")


def build_migration_guide_payload(
    *,
    target_ref: str,
    db_profile_id: str,
    metadata: Mapping[str, Any] | None,
    static_analysis: Mapping[str, Any] | None,
    llm_analysis: Mapping[str, Any] | None,
    input_params: Sequence[Mapping[str, Any]],
    result_shape: Sequence[str],
    sample_id: str,
) -> dict[str, Any]:
    metadata_payload = metadata or {}
    static_payload = static_analysis or {}
    evidence_refs = _evidence_refs(metadata_payload, target_ref=target_ref)
    primary_ref = evidence_refs[0]["id"] if evidence_refs else "ev_request_target"
    static_ref = "static.analysis.migration_guide"
    if not any(ref["id"] == static_ref for ref in evidence_refs):
        evidence_refs.append(
            {
                "id": static_ref,
                "type": "STATIC_ANALYSIS",
                "object_ref": target_ref,
                "locator": "analysis.migrationGuideStaticMetrics",
            }
        )

    dependency_inventory = _dependency_inventory(
        metadata_payload=metadata_payload,
        static_analysis=static_payload,
        static_ref=static_ref,
    )
    dml_matrix, table_dml_matrix = _dml_matrices(static_payload, static_ref=static_ref)
    complexity_metrics = _complexity_metrics(static_payload, static_ref=static_ref)
    risk_flags = _risk_flags(static_payload, llm_analysis or {}, static_ref=static_ref)

    return {
        "target_ref": target_ref,
        "fixture_id": sample_id,
        "db_context": {
            "metadata_profile_id": db_profile_id,
            "target_db": _target_db(db_profile_id),
            "platform_db": "PLF",
            "plf_fallback": "forbidden",
        },
        "artifacts_under_test": ["SP_ANALYSIS_DOC", "DEPENDENCY_REPORT"],
        "evidence_refs": evidence_refs,
        "sanitized_facts": _sanitized_facts(
            target_ref=target_ref,
            input_params=input_params,
            result_shape=result_shape,
            primary_ref=primary_ref,
            static_ref=static_ref,
        ),
        "section_expectations": _section_expectations(primary_ref, static_ref),
        "dependency_inventory": dependency_inventory,
        "confirmed_dependency_inventory": [
            item for item in dependency_inventory if item.get("status") == "Confirmed"
        ],
        "needs_verification_dependency_inventory": [
            item
            for item in dependency_inventory
            if item.get("status") == "Needs verification"
        ],
        "expected_dml_operations": sorted(
            {str(item.get("operation")) for item in dml_matrix if item.get("operation")},
            key=lambda value: _DML_ORDER.index(value) if value in _DML_ORDER else 99,
        ),
        "dml_matrix": dml_matrix,
        "table_dml_matrix": table_dml_matrix,
        "call_flow": _call_flow(dml_matrix, static_ref=static_ref),
        "phase_risk_metrics": {
            "branch_count": max(1, len(dml_matrix)),
            "dml_operation_count": len(dml_matrix),
            "complexity_score": _complexity_score(complexity_metrics),
            "complexity_metrics": complexity_metrics,
            "risk_flags": risk_flags,
        },
        "appendix_mappings": {
            "parameters": [
                {
                    "name": str(param.get("name") or "REVIEW_REQUIRED"),
                    "sanitized_type": str(param.get("dbType") or param.get("db_type") or ""),
                    "evidence_refs": [primary_ref],
                }
                for param in input_params
            ],
            "result_fields": [
                {"name": str(field), "evidence_refs": [static_ref]} for field in result_shape
            ],
        },
        "metadata_extraction_appendix": _manual_metadata_extraction_appendix(target_ref),
        "unsupported_claim_expectations": _unsupported_claims(
            dependency_inventory=dependency_inventory,
            risk_flags=risk_flags,
            static_ref=static_ref,
        ),
    }


def _evidence_refs(metadata: Mapping[str, Any], *, target_ref: str) -> list[dict[str, str]]:
    refs: list[dict[str, str]] = []
    for index, ref in enumerate(_sequence(metadata.get("evidenceRefs")), start=1):
        if not isinstance(ref, Mapping):
            continue
        refs.append(
            {
                "id": f"ev_metadata_{index}",
                "type": str(ref.get("type") or "MSSQL_METADATA"),
                "object_ref": str(ref.get("objectRef") or target_ref),
                "locator": str(ref.get("locator") or "metadata.evidenceRefs"),
            }
        )
    if refs:
        return refs
    return [
        {
            "id": "ev_request_target",
            "type": "USER_INPUT",
            "object_ref": target_ref,
            "locator": "request.target",
        }
    ]


def _sanitized_facts(
    *,
    target_ref: str,
    input_params: Sequence[Mapping[str, Any]],
    result_shape: Sequence[str],
    primary_ref: str,
    static_ref: str,
) -> list[dict[str, Any]]:
    facts = [
        {
            "id": "fact_target_identity",
            "fact_type": "PROCEDURE_IDENTITY",
            "summary": f"Migration guide target is {target_ref}.",
            "evidence_refs": [primary_ref],
        },
        {
            "id": "fact_parameter_inventory",
            "fact_type": "PROCEDURE_PARAMETERS",
            "summary": f"{len(input_params)} parameter(s) available from metadata.",
            "evidence_refs": [primary_ref],
        },
        {
            "id": "fact_result_shape",
            "fact_type": "RESULT_SHAPE",
            "summary": f"{len(result_shape)} result field candidate(s) available.",
            "evidence_refs": [static_ref],
        },
    ]
    return facts


def _section_expectations(primary_ref: str, static_ref: str) -> list[dict[str, Any]]:
    sections = []
    for section_id in P24_REQUIRED_SECTION_IDS:
        refs = (
            [static_ref]
            if section_id not in {"sp_overview", "appendix_mappings"}
            else [primary_ref]
        )
        summary = f"{section_id} is rendered from sanitized metadata/static facts."
        sections.append(
            {
                "id": section_id,
                "evidence_refs": refs,
                "claims": [
                    {
                        "id": f"claim_{section_id}",
                        "status": "REVIEW_REQUIRED",
                        "summary": summary,
                        "evidence_refs": refs,
                    }
                ],
            }
        )
    return sections


def _dependency_inventory(
    *,
    metadata_payload: Mapping[str, Any],
    static_analysis: Mapping[str, Any],
    static_ref: str,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for edge in _sequence(_mapping(metadata_payload.get("dependencyEvidence")).get("edges")):
        if not isinstance(edge, Mapping):
            continue
        status = (
            "Confirmed"
            if str(edge.get("resolutionStatus")) == "CONFIRMED"
            else "Needs verification"
        )
        items.append(
            {
                "object_kind": str(edge.get("dependencyType") or "dependency").lower(),
                "object_ref": str(edge.get("to") or "REVIEW_REQUIRED"),
                "operations": ["REFERENCE"],
                "key_columns": [],
                "join_or_where_summary": str(edge.get("resolutionStrategy") or ""),
                "value_or_state_patterns": str(edge.get("resolutionEvidenceKind") or ""),
                "evidence_refs": _edge_refs(edge) or [static_ref],
                "status": status,
                "how_referenced": str(edge.get("resolutionStrategy") or "dependency closure"),
                "why_uncertain": ""
                if status == "Confirmed"
                else str(edge.get("unresolvedReason") or "Dependency was not catalog-confirmed."),
                "what_to_extract_next": ""
                if status == "Confirmed"
                else (
                    "Run dependency closure/reference resolution metadata tools "
                    "or manual catalog queries."
                ),
            }
        )
    for unresolved in _sequence(
        _mapping(metadata_payload.get("dependencyEvidence")).get("unresolved")
    ):
        if not isinstance(unresolved, Mapping):
            continue
        name = ".".join(
            str(unresolved.get(part))
            for part in ("schema", "name")
            if unresolved.get(part)
        )
        items.append(
            {
                "object_kind": str(unresolved.get("dependencyType") or "dependency").lower(),
                "object_ref": name or "REVIEW_REQUIRED",
                "operations": ["REFERENCE"],
                "key_columns": [],
                "join_or_where_summary": str(unresolved.get("resolutionStrategy") or "UNRESOLVED"),
                "value_or_state_patterns": str(unresolved.get("resolutionEvidenceKind") or ""),
                "evidence_refs": _edge_refs(unresolved) or [static_ref],
                "status": "Needs verification",
                "how_referenced": "unresolved dependency evidence",
                "why_uncertain": str(unresolved.get("unresolvedReason") or "Unresolved reference."),
                "what_to_extract_next": (
                    "Resolve candidates with catalog metadata; do not infer from LLM text."
                ),
            }
        )
    for reference in _static_dependency_refs(static_analysis):
        if not any(item.get("object_ref") == reference["object_ref"] for item in items):
            items.append(reference)
    if _dynamic_sql_detected(static_analysis):
        items.append(
            {
                "object_kind": "dynamic_sql",
                "object_ref": "sp_executesql/EXEC dynamic candidate",
                "operations": ["REVIEW_REQUIRED"],
                "key_columns": [],
                "join_or_where_summary": "Dynamic SQL may hide object dependencies.",
                "value_or_state_patterns": (
                    "Generated SQL text is not promoted as deterministic dependency evidence."
                ),
                "evidence_refs": [static_ref],
                "status": "Needs verification",
                "how_referenced": "dynamic SQL signal",
                "why_uncertain": "Static parser cannot confirm dependencies inside generated SQL.",
                "what_to_extract_next": (
                    "Capture catalog-confirmed dependency closure or reviewer-supplied "
                    "sanitized metadata."
                ),
            }
        )
    return items


def _static_dependency_refs(static_analysis: Mapping[str, Any]) -> list[dict[str, Any]]:
    dependencies = _mapping(static_analysis.get("dependencies"))
    refs: list[dict[str, Any]] = []
    for key, kind in (
        ("table_references", "table"),
        ("view_references", "view"),
        ("function_references", "function"),
    ):
        for item in _sequence(dependencies.get(key)):
            if not isinstance(item, Mapping):
                continue
            status = (
                "Confirmed"
                if str(item.get("status")) == "OBSERVED"
                else "Needs verification"
            )
            operation = (
                "SELECT"
                if str(item.get("operation")) == "READ"
                else str(item.get("operation") or "")
            )
            refs.append(
                {
                    "object_kind": kind,
                    "object_ref": str(
                        item.get("full_name") or item.get("fullName") or item.get("object_name")
                    ),
                    "operations": [operation],
                    "key_columns": [],
                    "join_or_where_summary": "Static parser reference.",
                    "value_or_state_patterns": "",
                    "evidence_refs": ["static.analysis.migration_guide"],
                    "status": status,
                    "how_referenced": "static parser",
                    "why_uncertain": ""
                    if status == "Confirmed"
                    else "Static reference requires catalog confirmation.",
                    "what_to_extract_next": ""
                    if status == "Confirmed"
                    else "Confirm object type and database with MCP metadata.",
                }
            )
    for call in _sequence(dependencies.get("called_procedures")):
        if not isinstance(call, Mapping):
            continue
        status = "Confirmed" if str(call.get("status")) == "OBSERVED" else "Needs verification"
        refs.append(
            {
                "object_kind": "procedure",
                "object_ref": str(
                    call.get("full_name") or call.get("fullName") or call.get("procedure_name")
                ),
                "operations": ["EXECUTE"],
                "key_columns": [],
                "join_or_where_summary": "EXEC call parsed from static SQL.",
                "value_or_state_patterns": "",
                "evidence_refs": ["static.analysis.migration_guide"],
                "status": status,
                "how_referenced": "static EXEC parser",
                "why_uncertain": ""
                if status == "Confirmed"
                else "Dynamic or system procedure call.",
                "what_to_extract_next": ""
                if status == "Confirmed"
                else "Confirm executed target through metadata or review.",
            }
        )
    return refs


def _dml_matrices(
    static_analysis: Mapping[str, Any],
    *,
    static_ref: str,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    dml_operations = [
        item
        for item in _sequence(
            _mapping(static_analysis.get("migrationGuideStaticMetrics")).get("dmlOperations")
        )
        if isinstance(item, Mapping)
    ]
    matrix: list[dict[str, Any]] = []
    table_ops: dict[str, set[str]] = {}
    for item in dml_operations:
        operation = str(item.get("operation") or "REVIEW_REQUIRED")
        target = str(item.get("targetRef") or "REVIEW_REQUIRED")
        table_ops.setdefault(target, set()).add(operation)
        matrix.append(
            {
                "operation": operation,
                "target_ref": target,
                "phase": "static_dml_scan",
                "impact": f"{operation} reference detected for {target}.",
                "keys_join_where_summary": "REVIEW_REQUIRED: inspect predicates and join keys.",
                "important_columns_or_patterns": (
                    "REVIEW_REQUIRED: column-level write/read pattern extraction pending."
                ),
                "evidence_refs": [str(item.get("evidenceRef") or static_ref)],
                "status": "Confirmed",
            }
        )
    grouped = [
        {
            "target_ref": target,
            "select": "Y" if "SELECT" in operations else "",
            "insert": "Y" if "INSERT" in operations else "",
            "update": "Y" if "UPDATE" in operations else "",
            "delete": "Y" if "DELETE" in operations else "",
            "merge": "Y" if "MERGE" in operations else "",
            "keys_join_where_summary": (
                "REVIEW_REQUIRED: predicate/key extraction requires reviewer confirmation."
            ),
            "important_columns_or_patterns": (
                "REVIEW_REQUIRED: important column patterns are not inferred from LLM output."
            ),
            "evidence_refs": [
                str(item.get("evidenceRef") or static_ref)
                for item in dml_operations
                if str(item.get("targetRef")) == target
            ]
            or [static_ref],
            "status": "Confirmed",
        }
        for target, operations in sorted(table_ops.items())
    ]
    return matrix, grouped


def _complexity_metrics(
    static_analysis: Mapping[str, Any],
    *,
    static_ref: str,
) -> list[dict[str, Any]]:
    metrics = _sequence(
        _mapping(static_analysis.get("migrationGuideStaticMetrics")).get("complexityMetrics")
    )
    return [
        {
            "metric": str(item.get("metric") or "REVIEW_REQUIRED"),
            "count": int(item.get("count") or 0),
            "evidence_rule": str(item.get("evidenceRule") or "static analysis"),
            "notes": str(item.get("notes") or ""),
            "evidence_refs": [static_ref],
        }
        for item in metrics
        if isinstance(item, Mapping)
    ]


def _risk_flags(
    static_analysis: Mapping[str, Any],
    llm_analysis: Mapping[str, Any],
    *,
    static_ref: str,
) -> list[dict[str, Any]]:
    flags: list[dict[str, Any]] = []
    if _dynamic_sql_detected(static_analysis):
        flags.append(
            {
                "code": "DYNAMIC_SQL_DEPENDENCY_REVIEW",
                "severity": "WARNING",
                "status": "REVIEW_REQUIRED",
                "evidence_refs": [static_ref],
            }
        )
    for risk in _sequence(llm_analysis.get("riskFlags")):
        if not isinstance(risk, Mapping):
            continue
        flags.append(
            {
                "code": str(risk.get("code") or "LLM_RISK_REVIEW"),
                "severity": str(risk.get("severity") or "WARNING"),
                "status": "REVIEW_REQUIRED",
                "evidence_refs": [
                    str(ref) for ref in _sequence(risk.get("evidenceRefs"))
                ]
                or [static_ref],
            }
        )
    return flags


def _call_flow(dml_matrix: Sequence[Mapping[str, Any]], *, static_ref: str) -> dict[str, Any]:
    branches = []
    if not dml_matrix:
        return {
            "inputs": ["Procedure parameters from metadata."],
            "branches": [
                {
                    "id": "branch_review_required_flow",
                    "phase": "review_required",
                    "condition_summary": "No deterministic DML operation sequence was extracted.",
                    "evidence_refs": [static_ref],
                    "actions": [
                        {
                            "operation": "REVIEW_REQUIRED",
                            "dependency_ref": "REVIEW_REQUIRED",
                            "evidence_refs": [static_ref],
                        }
                    ],
                }
            ],
            "results": ["REVIEW_REQUIRED: result shape must be validated."],
            "error_handling": "REVIEW_REQUIRED: error handling requires reviewer confirmation.",
        }
    for index, item in enumerate(dml_matrix, start=1):
        refs = [str(ref) for ref in _sequence(item.get("evidence_refs"))] or [static_ref]
        branches.append(
            {
                "id": f"branch_dml_{index}",
                "phase": str(item.get("phase") or "static_dml_scan"),
                "condition_summary": str(item.get("impact") or ""),
                "evidence_refs": refs,
                "actions": [
                    {
                        "operation": str(item.get("operation") or "REVIEW_REQUIRED"),
                        "dependency_ref": str(item.get("target_ref") or "REVIEW_REQUIRED"),
                        "evidence_refs": refs,
                    }
                ],
            }
        )
    return {
        "inputs": ["Procedure parameters from metadata."],
        "branches": branches,
        "results": ["Result shape candidates are rendered in appendix mappings."],
        "error_handling": "REVIEW_REQUIRED: confirm normal/exception/resource cleanup branches.",
    }


def _manual_metadata_extraction_appendix(target_ref: str) -> dict[str, Any]:
    schema, name = _schema_name(target_ref)
    prelude = (
        f"DECLARE @SchemaName sysname = N'{schema}';\n"
        f"DECLARE @ObjectName sysname = N'{name}';\n"
        "DECLARE @FullName nvarchar(517) = QUOTENAME(@SchemaName) + N'.' + QUOTENAME(@ObjectName);"
    )
    return {
        "policy": (
            "Manual reviewer aid only. Run in SSMS against the source metadata DB; "
            "do not execute procedures, select row data, apply DDL/DML, or paste raw definitions."
        ),
        "queries": [
            {
                "id": "definition_hash_length",
                "title": "SP definition hash/length",
                "sql": (
                    prelude
                    + "\nSELECT DB_NAME() AS database_name, s.name AS schema_name,"
                    " o.name AS object_name,"
                    + "\n       CONVERT(varchar(64), HASHBYTES('SHA2_256',"
                    " CONVERT(varbinary(max), sm.definition)), 2) AS definition_sha256,"
                    + "\n       DATALENGTH(sm.definition) AS definition_bytes"
                    + "\nFROM sys.objects o"
                    + "\nJOIN sys.schemas s ON s.schema_id = o.schema_id"
                    + "\nJOIN sys.sql_modules sm ON sm.object_id = o.object_id"
                    + "\nWHERE s.name = @SchemaName AND o.name = @ObjectName;"
                ),
                "result_template": (
                    "| database_name | schema_name | object_name | definition_sha256 | "
                    "definition_bytes | status |"
                ),
            },
            {
                "id": "parameters",
                "title": "Procedure parameters",
                "sql": (
                    prelude
                    + "\nSELECT p.parameter_id, p.name, TYPE_NAME(p.user_type_id) AS data_type,"
                    + "\n       p.max_length, p.precision, p.scale, p.is_output"
                    + "\nFROM sys.parameters p"
                    + "\nWHERE p.object_id = OBJECT_ID(@FullName)"
                    + "\nORDER BY p.parameter_id;"
                ),
                "result_template": (
                    "| parameter_id | name | data_type | max_length | precision | scale | "
                    "is_output | status |"
                ),
            },
            {
                "id": "static_dependencies",
                "title": "Static catalog dependencies",
                "sql": (
                    prelude
                    + "\nSELECT referenced_server_name, referenced_database_name,"
                    " referenced_schema_name,"
                    + "\n       referenced_entity_name, referenced_class_desc,"
                    " is_caller_dependent, is_ambiguous"
                    + "\nFROM sys.sql_expression_dependencies"
                    + "\nWHERE referencing_id = OBJECT_ID(@FullName);"
                ),
                "result_template": (
                    "| server | database | schema | entity | class | caller_dependent | "
                    "ambiguous | status |"
                ),
            },
            {
                "id": "referenced_entities",
                "title": "Referenced entities DMV",
                "sql": (
                    prelude
                    + "\nSELECT referenced_schema_name, referenced_entity_name,"
                    " referenced_minor_name,"
                    + "\n       referenced_class_desc, is_selected, is_updated, is_select_all"
                    + "\nFROM sys.dm_sql_referenced_entities(@FullName, N'OBJECT');"
                ),
                "result_template": (
                    "| schema | entity | minor_name | class | selected | updated | "
                    "select_all | status |"
                ),
            },
            {
                "id": "dynamic_sql_indicators",
                "title": "Dynamic SQL and external reference indicators",
                "sql": (
                    prelude
                    + "\nSELECT CASE WHEN sm.definition LIKE '%sp_executesql%'"
                    " THEN 1 ELSE 0 END AS has_sp_executesql,"
                    + "\n       CASE WHEN sm.definition LIKE '%EXEC(%'"
                    " OR sm.definition LIKE '%EXEC (@%' THEN 1 ELSE 0 END"
                    " AS has_exec_string,"
                    + "\n       CASE WHEN sm.definition LIKE '%OPENQUERY%' THEN 1 ELSE 0 END"
                    " AS has_openquery"
                    + "\nFROM sys.sql_modules sm"
                    + "\nWHERE sm.object_id = OBJECT_ID(@FullName);"
                ),
                "result_template": (
                    "| has_sp_executesql | has_exec_string | has_openquery | status | "
                    "what_to_extract_next |"
                ),
            },
            {
                "id": "temp_table_review",
                "title": "Temp table/table variable review indicators",
                "sql": (
                    prelude
                    + "\nSELECT CASE WHEN sm.definition LIKE '%CREATE TABLE #%'"
                    " THEN 1 ELSE 0 END AS has_temp_table,"
                    + "\n       CASE WHEN sm.definition LIKE '%DECLARE @% TABLE%'"
                    " THEN 1 ELSE 0 END AS has_table_variable"
                    + "\nFROM sys.sql_modules sm"
                    + "\nWHERE sm.object_id = OBJECT_ID(@FullName);"
                ),
                "result_template": (
                    "| has_temp_table | has_table_variable | status | what_to_extract_next |"
                ),
            },
        ],
        "paste_templates": [
            "| Type | Name | How referenced | Evidence | Notes |",
            "| Type | Name/Candidate | Why uncertain | What to extract next | Notes |",
        ],
    }


def _unsupported_claims(
    *,
    dependency_inventory: Sequence[Mapping[str, Any]],
    risk_flags: Sequence[Mapping[str, Any]],
    static_ref: str,
) -> list[dict[str, Any]]:
    claims = [
        {
            "claim_code": f"NEEDS_VERIFICATION_{index}",
            "claim_type": str(item.get("object_kind") or "dependency"),
            "expected_status": "REVIEW_REQUIRED",
            "obligation": "unsupported_dependency_claims",
            "evidence_refs": [
                str(ref) for ref in _sequence(item.get("evidence_refs"))
            ]
            or [static_ref],
        }
        for index, item in enumerate(dependency_inventory, start=1)
        if item.get("status") == "Needs verification"
    ]
    for risk in risk_flags:
        claims.append(
            {
                "claim_code": str(risk.get("code") or "RISK_REVIEW_REQUIRED"),
                "claim_type": "risk",
                "expected_status": "REVIEW_REQUIRED",
                "obligation": "low_evidence_business_rule_claims",
                "evidence_refs": [
                    str(ref) for ref in _sequence(risk.get("evidence_refs"))
                ]
                or [static_ref],
            }
        )
    return claims


def _edge_refs(item: Mapping[str, Any]) -> list[str]:
    refs = []
    for ref in _sequence(item.get("evidenceRefs")):
        if isinstance(ref, Mapping):
            refs.append(str(ref.get("objectRef") or ref.get("locator") or "metadata.evidence"))
        else:
            refs.append(str(ref))
    return refs


def _complexity_score(metrics: Sequence[Mapping[str, Any]]) -> int:
    weighted = 0
    for item in metrics:
        metric = str(item.get("metric") or "")
        count = int(item.get("count") or 0)
        if metric in {
            "DYNAMIC_SQL_SIGNAL",
            "CURSOR_SIGNAL",
            "TRANSACTION_SIGNAL",
            "CROSS_DB_REFERENCE",
        }:
            weighted += count * 2
        elif metric not in {"LOC"}:
            weighted += count
    return weighted


def _dynamic_sql_detected(static_analysis: Mapping[str, Any]) -> bool:
    return bool(
        _mapping(_mapping(static_analysis.get("patterns")).get("dynamic_sql")).get("detected")
        or _mapping(_mapping(static_analysis.get("patterns")).get("dynamicSql")).get("detected")
    )


def _target_db(db_profile_id: str) -> str:
    normalized = "".join(char for char in db_profile_id.upper() if char.isalnum())
    return normalized or "REVIEW_REQUIRED"


def _schema_name(target_ref: str) -> tuple[str, str]:
    parts = [part for part in target_ref.split(".") if part]
    if len(parts) >= 2:
        return parts[-2], parts[-1]
    return "dbo", parts[-1] if parts else "REVIEW_REQUIRED"


def _sequence(value: Any) -> Sequence[Any]:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return value
    return ()


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}
