from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from typing import Any

from ai_agent_domain import ArtifactType

from ai_agent_generation.models import GenerationContext, RenderedArtifact
from ai_agent_generation.utils import ensure_trailing_newline


DATABASE_SECTION_ORDER = ("PPM", "ERP", "HRM", "TCM")
CRUD_DISPLAY_ORDER = ("R", "A", "C", "U", "D", "VENDOR_U", "ONLINE_U")
CRUD_LABELS = {
    "R": ("Read", "대상 정보 조회"),
    "A": ("Approval", "승인 처리"),
    "C": ("Create", "대상 정보 등록"),
    "U": ("Update", "대상 정보 수정"),
    "D": ("Delete", "대상 정보 삭제"),
}
COMPLEXITY_METRICS = (
    ("LOC", "LOC"),
    ("PARAMETER_COUNT", "입력 파라미터"),
    ("DECLARE_VARIABLE", "DECLARE 변수"),
    ("BEGIN_END_BLOCK", "BEGIN/END 블록"),
    ("IF", "IF/ELSE 분기"),
    ("ELSE", "ELSE"),
    ("WHILE", "WHILE/LOOP"),
    ("CASE", "CASE 표현식"),
    ("GOTO", "GOTO"),
    ("RETURN", "RETURN"),
    ("CURSOR_SIGNAL", "CURSOR"),
    ("TRY_CATCH_BLOCK", "TRY/CATCH"),
    ("TRANSACTION_SIGNAL", "BEGIN TRAN"),
    ("DYNAMIC_SQL_SIGNAL", "동적 SQL"),
    ("CROSS_DB_REFERENCE", "Cross-DB 참조"),
)
HUMAN_REDIRECT_MARKERS = (
    "LLM_INFERENCE_EVIDENCE_CAVEAT",
    "evidenceRefs=",
    "reviewMarker:",
    "unsupported_claim",
    "section_expectation",
    "section_claim",
    "static.dml.",
    "ev_metadata_",
    "mcp.get_",
    "agent-runtime.modelInvocation.outputHash",
    "sanitized skeleton",
    "Evidence Map",
)


class SPAnalysisDocumentRenderer:
    artifact_type = ArtifactType.SP_ANALYSIS_DOC

    def render(self, context: GenerationContext) -> RenderedArtifact:
        model = build_migration_guide_model(context)
        target_ref = str(model["target_ref"])
        return RenderedArtifact(
            artifact_type=self.artifact_type,
            title=f"Migration Guide: {target_ref}",
            content=ensure_trailing_newline(render_migration_guide(model)),
            evidence_refs=context.evidence_refs,
            registry_refs=(
                "template:sp_analysis_doc@0.3.0",
                "contract:p36_output_renewal@0.1.0",
                "contract:p51_migration_guide_dossier_split@0.1.0",
            ),
            assumptions=context.evidence_assumptions,
            review_required=True,
        )


class DependencyReportRenderer:
    artifact_type = ArtifactType.DEPENDENCY_REPORT

    def render(self, context: GenerationContext) -> RenderedArtifact:
        model = build_evidence_dossier_model(context)
        target_ref = str(model["target_ref"])
        return RenderedArtifact(
            artifact_type=self.artifact_type,
            title=f"{target_ref} Evidence Dossier",
            content=ensure_trailing_newline(render_evidence_dossier(model)),
            evidence_refs=context.evidence_refs,
            registry_refs=(
                "template:dependency_report@0.3.0",
                "contract:p36_output_renewal@0.1.0",
                "contract:p51_migration_guide_dossier_split@0.1.0",
            ),
            assumptions=context.evidence_assumptions,
            review_required=True,
        )


def build_migration_guide_model(context: GenerationContext) -> dict[str, Any]:
    guide = _guide_payload(context)
    db_context = _mapping(guide.get("db_context"))
    target_ref = _qualified_target_ref(context, guide, db_context)
    return {
        "context": context,
        "guide": guide,
        "target_ref": target_ref,
        "db_context": db_context,
        "humanSummary": _overview_model(context, guide, target_ref),
        "businessFlows": _business_flows(context, guide),
        "dependencySummary": _dependency_summary(guide, db_context),
        "dmlPivotMatrix": _pivot_matrix(guide, db_context),
        "riskSummary": _risk_summary(guide),
    }


def build_evidence_dossier_model(context: GenerationContext) -> dict[str, Any]:
    guide = _guide_payload(context)
    db_context = _mapping(guide.get("db_context"))
    target_ref = _qualified_target_ref(context, guide, db_context)
    return {
        "context": context,
        "guide": guide,
        "target_ref": target_ref,
        "db_context": db_context,
        "rawEvidence": _raw_evidence_ids(context, guide),
        "statementEvidence": _statement_evidence_items(context, guide),
        "semanticEvidence": _mapping(context.value("llmAnalysis", {}) or {}),
        "evidenceMap": _evidence_map_entries(context, guide),
        "reviewMarkers": _review_markers(context, guide),
    }


def render_migration_guide(model: Mapping[str, Any]) -> str:
    context = model["context"]
    guide = _mapping(model.get("guide"))
    target_ref = str(model["target_ref"])
    db_context = _mapping(model.get("db_context"))
    flows = _mapping_items(model.get("businessFlows"))
    pivot_items = _mapping_items(model.get("dmlPivotMatrix"))
    risk_summary = _mapping(model.get("riskSummary"))
    database, schema, procedure = _target_parts(target_ref)

    lines = [
        f"# Migration Guide: {target_ref}",
        "",
        f"> **문서 상태**: Draft",
        f"> **대상 SP**: `{target_ref}`",
        f"> **업무명**: {_human_text(context.description or context.entity_name or '확인 필요')}",
        "",
        "<!-- section:sp_overview -->",
        "## 1. SP 개요 (Overview)",
        "",
        "### 1.1 기본 정보",
        "",
        "| 항목 | 값 |",
        "|---|---|",
        f"| 프로시저명 | `{_human_text(procedure)}` |",
        f"| 스키마 | `{_human_text(schema)}` |",
        f"| 데이터베이스 | `{_human_text(database)}` |",
        f"| 업무영역 | {_human_text(context.description or context.entity_name or '확인 필요')} |",
        "| 개발자 | 확인 필요 |",
        f"| 입력 파라미터 수 | {len(context.input_params)}개 |",
        "",
        "<!-- section:feature_branch_taxonomy -->",
        "### 1.2 주요 기능",
        "",
        *_business_feature_lines(flows),
        "",
        "### 1.3 지원 서브시스템",
        "",
        *_subsystem_lines(guide, db_context),
        "",
        "### 1.4 주요 업무 코드 / 보증유형코드",
        "",
        *_code_mapping_lines(context, guide, flows),
        "",
        "<!-- section:dependency_inventory -->",
        "## 2. 의존성 인벤토리 (Dependency Inventory)",
        "",
        "### 2.1 테이블 의존성",
        "",
    ]
    for index, db_name in enumerate(DATABASE_SECTION_ORDER, start=1):
        lines.extend(
            [
                f"#### 2.1.{index} Confirmed - {db_name} Database"
                if db_name == "PPM"
                else f"#### 2.1.{index} Confirmed - Cross-DB References ({db_name})",
                "",
                "| Type | Schema | Table Name | DML Operations | Key Columns | Notes |",
                "|---|---|---|---|---|---|",
                *_dependency_table_rows_for_db(guide, db_name=db_name),
                "",
            ]
        )
    lines.extend(
        [
            "### 2.2 UDF 의존성",
            "",
            "| Type | Schema | Function Name | Return Type | Notes |",
            "|---|---|---|---|---|",
            *_dependency_function_rows(guide),
            "",
            "### 2.3 Stored Procedure 의존성",
            "",
            "| Type | Schema | Procedure Name | Call Method | Status | Notes |",
            "|---|---|---|---|---|---|",
            *_dependency_procedure_rows(guide),
            "",
            "### 2.4 동적 SQL 분석",
            "",
            *_dynamic_sql_lines(guide, risk_summary),
            "",
            "<!-- section:dml_impact_matrix -->",
            "## 3. DML 영향도 매트릭스 (Data Change Impact Matrix)",
            "",
        ]
    )
    for index, db_name in enumerate(DATABASE_SECTION_ORDER, start=1):
        lines.extend(
            [
                f"### 3.{index} {db_name} Database",
                "",
                "| Table | SELECT | INSERT | UPDATE | DELETE | Keys/Join/Where 요약 | 중요 컬럼/값 패턴 |",
                "|---|:---:|:---:|:---:|:---:|---|---|",
                *_dml_pivot_rows_for_db(pivot_items, db_name=db_name),
                "",
            ]
        )
    lines.extend(
        [
            "<!-- section:call_flow -->",
            "## 4. 호출 흐름 (Call Flow)",
            "",
            "### 4.1 전체 구조",
            "",
            "```text",
            *_business_call_flow_lines(context, flows, pivot_items),
            "```",
            "",
            "<!-- section:critical_phase_analysis -->",
            "### 4.2 세부 Phase 분석",
            "",
            "| Phase | 주요 읽기 | 주요 쓰기 | 전환 리스크 / 확인 필요 |",
            "|---|---|---|---|",
            *_phase_analysis_rows(guide, pivot_items),
            "",
            "<!-- section:complexity_risk_metrics -->",
            "## 5. SP 복잡도 분석 (Complexity Analysis)",
            "",
            "### 5.1 정량 메트릭",
            "",
            "| Metric | Count | Evidence/Rule | Notes |",
            "|---|---:|---|---|",
            *_human_complexity_rows(context, guide),
            "",
            "### 5.2 Cross-DB 트랜잭션 리스크",
            "",
            *_human_risk_lines(pivot_items, risk_summary),
            "",
            "<!-- section:migration_strategy -->",
            "<!-- section:appendix_mappings -->",
            "<!-- section:metadata_extraction_appendix -->",
            "<!-- section:evidence_assumptions_review -->",
            "## 6. Appendix",
            "",
            "### 6.1 입력 파라미터 전체 목록",
            "",
            "| Parameter | Type | Default | Description |",
            "|---|---|---|---|",
            *_parameter_rows(context),
            "",
            "### 6.2 상태코드 매핑",
            "",
            "| Code/Flag | Values | Meaning | Notes |",
            "|---|---|---|---|",
            *_status_code_rows(context, guide, flows),
            "",
            "### 6.3 확인 필요 항목",
            "",
            "| 항목 | 내용 | 다음 확인 |",
            "|---|---|---|",
            *_human_caveat_rows(context, guide, risk_summary),
            "",
            "상세 근거는 Evidence Dossier 참조.",
        ]
    )
    return "\n".join(lines)


def render_evidence_dossier(model: Mapping[str, Any]) -> str:
    context = model["context"]
    guide = _mapping(model.get("guide"))
    target_ref = str(model["target_ref"])
    raw_refs = [str(item) for item in _sequence(model.get("rawEvidence")) if str(item)]
    lines = [
        f"# {target_ref} Evidence Dossier",
        "",
        "## generation_evidence_summary",
        "- status: DRAFT / production_ready=false",
        "- role: audit, validation, and regeneration evidence for the paired Migration Guide.",
        "- SP_ANALYSIS_DOC projection: human-facing guide without raw evidence ids or generation logs.",
        "- DEPENDENCY_REPORT projection: conservation surface for evidence ids, review markers, sanitized SQL skeletons, and LLM caveats.",
        "- generated_source_application: `not_performed`",
        "",
        "## sp_analysis_evidence",
        "",
        "| output section | evidenceRefs | caveat |",
        "|---|---|---|",
        *_sp_analysis_evidence_rows(guide),
        "",
        "## java_mybatis_evidence",
        "",
        "| artifact | generation evidence | review markers |",
        "|---|---|---|",
        *_java_mybatis_evidence_rows(context, guide),
        *_ai_draft_pack_evidence_rows(context),
        "",
        "### p50_stage_trace",
        "",
        *_ai_draft_pack_stage_trace_lines(context),
        "",
        "## sql_statement_evidence",
        "",
        "| evidence id | operation | target | sanitized skeleton | caveat |",
        "|---|---|---|---|---|",
        *_sql_statement_evidence_rows(guide),
        *_operation_model_statement_rows(context),
        "",
        "### static.dml.* raw evidence refs",
        "",
        *[f"- {ref}" for ref in raw_refs if ref.startswith("static.dml.")],
        *([] if any(ref.startswith("static.dml.") for ref in raw_refs) else ["- REVIEW_REQUIRED: no static.dml.* refs available"]),
        "",
        "## dependency_closure_evidence",
        "",
        *_dependency_inventory_table(guide, fallback="- REVIEW_REQUIRED: dependency closure evidence is empty."),
        "",
        "## semantic_inference_evidence",
        "- LLM_INFERENCE_EVIDENCE_CAVEAT: semantic summaries are draft-only unless supported by deterministic evidence.",
        "",
        *_llm_semantic_lines(context),
        "",
        "## evidence_map",
        "",
        *_evidence_map_lines(context, guide),
        "",
        *_p24_claim_support_lines(guide),
        "",
        *(_review_marker_lines(context, guide) or ["- reviewMarker: REVIEW_REQUIRED evidence marker inventory is empty."]),
        "",
        "## known_caveats",
        "- REVIEW_REQUIRED: SQL JOIN/WHERE/SET/DELETE predicates are not promoted to confirmed facts from statement skeletons alone.",
        "- REVIEW_REQUIRED: business branch names and status-code meanings need human verification when only inferred.",
        "- REVIEW_REQUIRED: Java/MyBatis drafts are not deployable source and require review before any implementation use.",
        "",
        "## next_evidence_to_collect",
        "- catalog-confirmed dependency closure and unresolved reference resolution",
        "- branch-specific statement evidence for SELECT/JOIN/WHERE/SET/DELETE details",
        "- status-code and business-code meaning from authoritative code tables or design docs",
        "- transaction boundary, exception handling, and cross-DB write policy evidence",
        "",
        "## draft_readiness",
        "- draft_readiness: evidence-conserved draft, production_ready=false",
        "- no procedure execution, row-data query, automatic schema/data apply, source apply, or deploy path is included.",
    ]
    return "\n".join(lines)


def _guide_payload(context: GenerationContext) -> dict[str, Any]:
    payload = context.value("migrationGuide", {}) or {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def _qualified_target_ref(
    context: GenerationContext,
    guide: Mapping[str, Any],
    db_context: Mapping[str, Any],
) -> str:
    raw = str(guide.get("target_ref") or context.sp_name or context.entity_name).strip()
    parts = [part for part in raw.split(".") if part]
    if len(parts) >= 3:
        return ".".join(parts[-3:])
    database = str(db_context.get("target_db") or "").strip()
    if database and database not in {"REVIEW_REQUIRED", "확인 필요"}:
        return f"{database}.{raw}"
    return raw


def _target_parts(target_ref: str) -> tuple[str, str, str]:
    parts = [part for part in target_ref.split(".") if part]
    if len(parts) >= 3:
        return parts[-3], parts[-2], parts[-1]
    if len(parts) == 2:
        return "확인 필요", parts[0], parts[1]
    return "확인 필요", "확인 필요", parts[0] if parts else "확인 필요"


def _overview_model(
    context: GenerationContext,
    guide: Mapping[str, Any],
    target_ref: str,
) -> dict[str, Any]:
    database, schema, procedure = _target_parts(target_ref)
    return {
        "database": database,
        "schema": schema,
        "procedure": procedure,
        "parameterCount": len(context.input_params),
        "description": context.description or context.entity_name or "확인 필요",
        "metadataProfileId": _mapping(guide.get("db_context")).get("metadata_profile_id", "확인 필요"),
    }


def _dependency_summary(guide: Mapping[str, Any], db_context: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "targetDb": str(db_context.get("target_db") or "PPM"),
        "items": _mapping_items(guide.get("dependency_inventory")),
    }


def _risk_summary(guide: Mapping[str, Any]) -> dict[str, Any]:
    phase_metrics = _mapping(guide.get("phase_risk_metrics"))
    return {
        "branchCount": phase_metrics.get("branch_count"),
        "dmlOperationCount": phase_metrics.get("dml_operation_count"),
        "complexityScore": phase_metrics.get("complexity_score"),
        "riskFlags": _mapping_items(phase_metrics.get("risk_flags")),
        "complexityMetrics": _mapping_items(phase_metrics.get("complexity_metrics")),
    }


def _business_flows(context: GenerationContext, guide: Mapping[str, Any]) -> list[dict[str, Any]]:
    flows: list[dict[str, Any]] = []
    for operation in _mapping_items(context.operation_model.get("operations")):
        code = str(operation.get("crudFlag") or "").strip()
        condition = _mapping(operation.get("branchCondition")).get("expression")
        if not code:
            code = _crud_code_from_text(condition)
        if not code:
            continue
        flows.append(
            _flow_entry(
                flag="@CRUDFlag",
                code=code,
                label=str(operation.get("title") or ""),
                summary=str(operation.get("summary") or ""),
            )
        )
    predicate_flows: list[dict[str, Any]] = []
    fallback_predicate_flows: list[dict[str, Any]] = []
    for item in _mapping_items(guide.get("branch_predicates")):
        parameter = _parameter_name(item.get("parameter"))
        if not parameter:
            continue
        values = [str(value) for value in _sequence(item.get("values")) if str(value)]
        for value in values:
            if parameter.lower() == "@crudflag":
                predicate_flows.append(_flow_entry(flag=parameter, code=value))
            elif _primary_branch_parameter(parameter):
                fallback_predicate_flows.append(_flow_entry(flag=parameter, code=value))
    flows.extend(predicate_flows or ([] if flows else fallback_predicate_flows))
    for branch in _mapping_items(_mapping(guide.get("call_flow")).get("branches")):
        code = _crud_code_from_text(branch.get("condition_summary") or branch.get("phase"))
        if code:
            flows.append(
                _flow_entry(
                    flag="@CRUDFlag",
                    code=code,
                    summary=str(branch.get("condition_summary") or ""),
                )
            )
    if not flows:
        flows.extend(_feature_row_flows(guide))
    return _sort_flows(_dedupe_flows(flows))


def _feature_row_flows(guide: Mapping[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in _mapping_items(guide.get("feature_branch_rows")):
        condition = str(item.get("condition") or "")
        feature = str(item.get("feature") or "")
        if "static DML scan" in condition or feature.upper().startswith(("SELECT", "INSERT", "UPDATE", "DELETE", "MERGE")):
            continue
        rows.append(
            {
                "flag": "업무 플래그",
                "code": feature or "확인 필요",
                "label": feature or "확인 필요",
                "summary": _human_text(item.get("summary") or "확인 필요"),
            }
        )
    return rows


def _flow_entry(
    *,
    flag: str,
    code: str,
    label: str = "",
    summary: str = "",
) -> dict[str, Any]:
    normalized = code.strip().strip("'\"").upper()
    default_label, default_summary = _crud_label_summary(normalized)
    return {
        "flag": _parameter_name(flag) or "@CRUDFlag",
        "code": normalized,
        "label": _human_text(label or default_label),
        "summary": _human_text(summary or default_summary),
    }


def _crud_label_summary(code: str) -> tuple[str, str]:
    if code in CRUD_LABELS:
        return CRUD_LABELS[code]
    if code.endswith("_U"):
        stem = code.removesuffix("_U").replace("_", " ").title()
        return f"{stem} Update", f"{stem} 업데이트"
    return code, "업무 처리"


def _dedupe_flows(flows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    seen: set[tuple[str, str]] = set()
    result: list[dict[str, Any]] = []
    for flow in flows:
        key = (str(flow.get("flag") or ""), str(flow.get("code") or ""))
        if not key[1] or key in seen:
            continue
        seen.add(key)
        result.append(dict(flow))
    return result


def _sort_flows(flows: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    order = {code: index for index, code in enumerate(CRUD_DISPLAY_ORDER)}
    return sorted(
        (dict(flow) for flow in flows),
        key=lambda flow: (
            0 if str(flow.get("code")) in order else 1,
            order.get(str(flow.get("code")), 999),
            str(flow.get("code")),
        ),
    )


def _pivot_matrix(guide: Mapping[str, Any], db_context: Mapping[str, Any]) -> list[dict[str, Any]]:
    items = _mapping_items(guide.get("table_dml_matrix"))
    if not items:
        items = _aggregate_dml_matrix(guide)
    target_db = str(db_context.get("target_db") or "PPM").upper()
    rows: list[dict[str, Any]] = []
    for item in items:
        target = str(item.get("target_ref") or item.get("targetRef") or "확인 필요")
        db_name = _object_db(target, default_db=target_db)
        rows.append(
            {
                "db": db_name,
                "table": target,
                "select": _mark(item.get("select")),
                "insert": _mark(item.get("insert")),
                "update": _mark(item.get("update") or item.get("merge")),
                "delete": _mark(item.get("delete")),
                "keys": _human_text(item.get("keys_join_where_summary") or "확인 필요"),
                "patterns": _human_text(item.get("important_columns_or_patterns") or "확인 필요"),
            }
        )
    return sorted(rows, key=lambda row: (str(row["db"]), str(row["table"])))


def _aggregate_dml_matrix(guide: Mapping[str, Any]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = {}
    for item in _mapping_items(guide.get("dml_matrix")):
        target = str(item.get("target_ref") or item.get("targetRef") or "확인 필요")
        operation = str(item.get("operation") or "").lower()
        entry = grouped.setdefault(
            target,
            {
                "target_ref": target,
                "select": "",
                "insert": "",
                "update": "",
                "delete": "",
                "keys_join_where_summary": item.get("keys_join_where_summary") or "확인 필요",
                "important_columns_or_patterns": item.get("important_columns_or_patterns") or "확인 필요",
            },
        )
        if operation in {"select", "insert", "update", "delete"}:
            entry[operation] = "Y"
        elif operation == "merge":
            entry["update"] = "Y"
            entry["important_columns_or_patterns"] = _join_unique_text(
                entry.get("important_columns_or_patterns"),
                "MERGE/UPSERT 확인 필요",
            )
    return list(grouped.values())


def _business_feature_lines(flows: Sequence[Mapping[str, Any]]) -> list[str]:
    if not flows:
        return ["- 확인 필요: 업무 기능 목록은 상세 근거 보강 후 확정합니다."]
    return [
        f"- **{_human_text(flow.get('code'))} ({_human_text(flow.get('label'))})**: {_human_text(flow.get('summary'))}"
        for flow in flows
    ]


def _subsystem_lines(guide: Mapping[str, Any], db_context: Mapping[str, Any]) -> list[str]:
    dependencies = _mapping_items(guide.get("dependency_inventory"))
    dbs = sorted(
        {
            _object_db(str(item.get("object_ref") or ""), default_db=str(db_context.get("target_db") or "PPM"))
            for item in dependencies
            if item.get("object_ref")
        }
    )
    if not dbs:
        dbs = [str(db_context.get("target_db") or "확인 필요")]
    return [f"- **{_human_text(db)}**: {_db_subsystem_note(db)}" for db in dbs]


def _db_subsystem_note(db_name: str) -> str:
    notes = {
        "PPM": "주 업무 데이터베이스",
        "ERP": "Cross-DB 연계 데이터베이스",
        "HRM": "인사/조직 참조 데이터베이스",
        "TCM": "공통 코드 참조 데이터베이스",
    }
    return notes.get(db_name.upper(), "확인 필요")


def _code_mapping_lines(
    context: GenerationContext,
    guide: Mapping[str, Any],
    flows: Sequence[Mapping[str, Any]],
) -> list[str]:
    rows = _status_code_rows(context, guide, flows)
    return ["| Code/Flag | Values | Meaning | Notes |", "|---|---|---|---|", *rows]


def _dependency_table_rows_for_db(guide: Mapping[str, Any], *, db_name: str) -> list[str]:
    rows: list[str] = []
    for item in _dependency_items(guide, kind_filter=("table", "view")):
        object_ref = str(item.get("object_ref") or "")
        if _object_db(object_ref, default_db="PPM") != db_name:
            continue
        if not _is_confirmed(item):
            continue
        schema, table = _schema_and_name(object_ref)
        operations = ", ".join(str(op) for op in _sequence(item.get("operations")) if str(op))
        keys = ", ".join(str(key) for key in _sequence(item.get("key_columns")) if str(key))
        rows.append(
            "| "
            f"{_human_text(item.get('object_kind') or 'table')} | "
            f"{_human_text(schema)} | "
            f"`{_human_text(table)}` | "
            f"{_human_text(operations or '확인 필요')} | "
            f"{_human_text(keys or item.get('join_or_where_summary') or '확인 필요')} | "
            f"{_human_text(_dependency_description(item) or item.get('value_or_state_patterns') or '확인 필요')} |"
        )
    return rows or ["| - | - | - | - | - | 확인 필요 |"]


def _dependency_function_rows(guide: Mapping[str, Any]) -> list[str]:
    rows = []
    for item in _dependency_items(guide, kind_filter=("function", "udf")):
        schema, name = _schema_and_name(str(item.get("object_ref") or ""))
        rows.append(
            "| "
            f"{_human_text(item.get('object_kind') or 'Function')} | "
            f"{_human_text(schema)} | "
            f"`{_human_text(name)}` | "
            "확인 필요 | "
            f"{_human_text(item.get('join_or_where_summary') or item.get('value_or_state_patterns') or item.get('status') or '확인 필요')} |"
        )
    return rows or ["| - | - | - | 확인 필요 | 확인 필요 |"]


def _dependency_procedure_rows(guide: Mapping[str, Any]) -> list[str]:
    rows = []
    for item in _dependency_items(guide, kind_filter=("procedure", "stored_procedure")):
        schema, name = _schema_and_name(str(item.get("object_ref") or ""))
        rows.append(
            "| "
            f"{_human_text(item.get('object_kind') or 'StoredProcedure')} | "
            f"{_human_text(schema)} | "
            f"`{_human_text(name)}` | "
            f"{_human_text(item.get('how_referenced') or 'EXEC')} | "
            f"{_status_label(item.get('status'))} | "
            f"{_human_text(item.get('why_uncertain') or item.get('join_or_where_summary') or '확인 필요')} |"
        )
    return rows or ["| - | - | - | 확인 필요 | 확인 필요 | 확인 필요 |"]


def _dynamic_sql_lines(guide: Mapping[str, Any], risk_summary: Mapping[str, Any]) -> list[str]:
    dynamic_deps = [
        item for item in _dependency_items(guide) if "dynamic" in str(item.get("object_kind") or "").lower()
    ]
    dynamic_metric = _metric_count(risk_summary.get("complexityMetrics"), "DYNAMIC_SQL_SIGNAL")
    if dynamic_deps or dynamic_metric:
        return [
            f"- **동적 SQL 사용 여부**: 감지됨",
            "- **전환 리스크**: SQL 문자열 내부 의존성은 상세 근거 확인 필요",
            "- 상세 근거는 Evidence Dossier 참조.",
        ]
    return ["- **동적 SQL 사용 여부**: 감지되지 않음 또는 확인 필요", "- 상세 근거는 Evidence Dossier 참조."]


def _dml_pivot_rows_for_db(items: Sequence[Mapping[str, Any]], *, db_name: str) -> list[str]:
    rows = []
    for item in items:
        if str(item.get("db") or "").upper() != db_name.upper():
            continue
        _, table = _schema_and_name(str(item.get("table") or ""))
        rows.append(
            "| "
            f"`{_human_text(table)}` | "
            f"{_human_text(item.get('select') or '-')} | "
            f"{_human_text(item.get('insert') or '-')} | "
            f"{_human_text(item.get('update') or '-')} | "
            f"{_human_text(item.get('delete') or '-')} | "
            f"{_human_text(item.get('keys') or '확인 필요')} | "
            f"{_human_text(item.get('patterns') or '확인 필요')} |"
        )
    return rows or ["| - | - | - | - | - | 확인 필요 | 확인 필요 |"]


def _business_call_flow_lines(
    context: GenerationContext,
    flows: Sequence[Mapping[str, Any]],
    pivot_items: Sequence[Mapping[str, Any]],
) -> list[str]:
    if not flows:
        return [
            f"[입력] {len(context.input_params)}개 파라미터",
            "  └─► 업무 분기 확인 필요 ─► 상세 근거는 Evidence Dossier 참조",
        ]
    flag_name = str(flows[0].get("flag") or "@CRUDFlag")
    lines = [f"[입력] {len(context.input_params)}개 파라미터"]
    for index, flow in enumerate(flows):
        connector = "└─►" if index == len(flows) - 1 else "├─►"
        lines.append(
            f"  {connector} {flag_name} = '{_human_text(flow.get('code'))}' ─► {_human_text(flow.get('summary'))}"
        )
        for action in _flow_action_summaries(str(flow.get("code") or ""), pivot_items)[:3]:
            lines.append(f"  │     └─ {action}")
    return lines


def _flow_action_summaries(code: str, pivot_items: Sequence[Mapping[str, Any]]) -> list[str]:
    # Deterministic statement-to-branch binding is not always available in the guide model.
    # Use the pivot matrix as a compact, human-facing effect summary.
    summaries = []
    for item in pivot_items:
        operations = [
            operation
            for operation in ("SELECT", "INSERT", "UPDATE", "DELETE")
            if _mark(item.get(operation.lower()))
        ]
        if operations:
            _, table = _schema_and_name(str(item.get("table") or ""))
            summaries.append(f"{'/'.join(operations)} {table}")
    return summaries


def _phase_analysis_rows(guide: Mapping[str, Any], pivot_items: Sequence[Mapping[str, Any]]) -> list[str]:
    rows = []
    for item in _mapping_items(guide.get("critical_phase_rows")):
        reads = ", ".join(str(value) for value in _sequence(item.get("reads")) if str(value))
        writes = ", ".join(str(value) for value in _sequence(item.get("writes")) if str(value))
        phase_label = _human_text(item.get("phase") or item.get("name") or "확인 필요")
        if phase_label == "static_dml_scan":
            phase_label = "DML 영향 범위"
        rows.append(
            "| "
            f"{phase_label} | "
            f"{_human_text(reads or '-')} | "
            f"{_human_text(writes or '-')} | "
            f"{_human_text(item.get('risk') or item.get('caveat') or '확인 필요')} |"
        )
    if rows:
        return rows
    for item in pivot_items[:8]:
        operations = ", ".join(
            op for op in ("SELECT", "INSERT", "UPDATE", "DELETE") if _mark(item.get(op.lower()))
        )
        rows.append(
            "| "
            f"{_human_text(operations or '확인 필요')} | "
            f"{_human_text(item.get('table'))} | "
            f"{_human_text(item.get('table')) if any(_mark(item.get(op)) for op in ('insert', 'update', 'delete')) else '-'} | "
            "상세 조건 확인 필요 |"
        )
    return rows or ["| 확인 필요 | - | - | 상세 근거는 Evidence Dossier 참조 |"]


def _human_complexity_rows(context: GenerationContext, guide: Mapping[str, Any]) -> list[str]:
    metrics = {
        str(item.get("metric") or ""): item
        for item in _mapping_items(_mapping(guide.get("phase_risk_metrics")).get("complexity_metrics"))
    }
    rows = []
    for metric_key, label in COMPLEXITY_METRICS:
        if metric_key == "PARAMETER_COUNT":
            count = len(context.input_params)
            rule = "metadata parameter inventory"
            notes = ""
        else:
            item = metrics.get(metric_key)
            count = item.get("count") if item else "확인 필요"
            rule = _human_text(item.get("evidence_rule") or item.get("evidenceRule") or "static analysis") if item else "확인 필요"
            notes = _human_text(item.get("notes") or "") if item else ""
        rows.append(f"| {label} | {_human_text(count)} | {_human_text(rule)} | {_human_text(notes or '-')} |")
    return rows


def _human_risk_lines(
    pivot_items: Sequence[Mapping[str, Any]],
    risk_summary: Mapping[str, Any],
) -> list[str]:
    cross_db_writes = [
        str(item.get("table"))
        for item in pivot_items
        if str(item.get("db") or "").upper() not in {"", "PPM"}
        and (_mark(item.get("insert")) or _mark(item.get("update")) or _mark(item.get("delete")))
    ]
    lines = [
        "| 리스크 | 상태 | 설명 |",
        "|---|---|---|",
        "| 트랜잭션 경계 | 확인 필요 | Java 전환 시 서비스 트랜잭션 경계와 보상 전략을 별도 검토해야 합니다. |",
    ]
    if cross_db_writes:
        lines.append(
            "| Cross-DB write | 확인 필요 | "
            + ", ".join(f"`{_human_text(ref)}`" for ref in cross_db_writes)
            + " 쓰기 영향이 감지되었습니다. |"
        )
    else:
        lines.append("| Cross-DB write | 확인 필요 | 상세 근거는 Evidence Dossier 참조. |")
    for risk in _mapping_items(risk_summary.get("riskFlags"))[:6]:
        lines.append(
            "| "
            f"{_human_text(risk.get('code') or '확인 필요')} | "
            f"{_status_label(risk.get('status'))} | "
            f"{_human_text(risk.get('severity') or '확인 필요')} |"
        )
    return lines


def _parameter_rows(context: GenerationContext) -> list[str]:
    rows = []
    for param in context.input_params:
        rows.append(
            "| "
            f"`{_human_text(param.name)}` | "
            f"`{_human_text(param.db_type)}` | "
            f"{str(param.required).lower()} | "
            f"{_parameter_description(param.name)} |"
        )
    return rows or ["| 확인 필요 | 확인 필요 | false | 파라미터 메타데이터 확인 필요 |"]


def _status_code_rows(
    context: GenerationContext,
    guide: Mapping[str, Any],
    flows: Sequence[Mapping[str, Any]],
) -> list[str]:
    rows = []
    if flows:
        values = ", ".join(f"`{_human_text(flow.get('code'))}`" for flow in flows)
        rows.append(f"| @CRUDFlag | {values} | 업무 처리 분기 | 상세 의미 확인 필요 |")
    branch_values: dict[str, list[str]] = {}
    for item in _mapping_items(guide.get("branch_predicates")):
        parameter = _parameter_name(item.get("parameter"))
        if not parameter or parameter == "@CRUDFlag":
            continue
        branch_values.setdefault(parameter, [])
        branch_values[parameter].extend(str(value) for value in _sequence(item.get("values")) if str(value))
    for param in context.input_params:
        name = _parameter_name(param.name)
        lowered = name.lower()
        if not any(token in lowered for token in ("flag", "code", "type", "status", "_st_")):
            continue
        values = branch_values.get(name, [])
        rows.append(
            "| "
            f"{_human_text(name)} | "
            f"{_human_text(', '.join(values) if values else '확인 필요')} | "
            f"{_parameter_description(name)} | "
            "상세 근거는 Evidence Dossier 참조 |"
        )
    return _dedupe_rows(rows) or ["| 확인 필요 | 확인 필요 | 상태코드/업무코드 매핑 근거 부족 | 상세 근거 보강 필요 |"]


def _human_caveat_rows(
    context: GenerationContext,
    guide: Mapping[str, Any],
    risk_summary: Mapping[str, Any],
) -> list[str]:
    rows = []
    for item in _mapping_items(guide.get("unsupported_claim_expectations"))[:8]:
        rows.append(
            "| "
            f"{_human_claim_type(item)} | "
            f"{_human_text(item.get('claim_type') or '확인 필요')} | "
            "상세 근거는 Evidence Dossier 참조 |"
        )
    for item in _dependency_items(guide):
        if _is_confirmed(item):
            continue
        rows.append(
            "| "
            f"{_human_text(item.get('object_kind') or '의존성')} | "
            f"`{_human_text(item.get('object_ref') or '확인 필요')}` | "
            f"{_human_text(item.get('what_to_extract_next') or '카탈로그/설계 근거 확인 필요')} |"
        )
    for risk in _mapping_items(risk_summary.get("riskFlags")):
        rows.append(
            "| "
            f"{_human_text(risk.get('code') or '리스크')} | "
            f"{_human_text(risk.get('severity') or '확인 필요')} | "
            "상세 근거는 Evidence Dossier 참조 |"
        )
    for assumption in context.evidence_assumptions[:4]:
        rows.append(f"| 가정 | {_human_text(assumption)} | 상세 근거는 Evidence Dossier 참조 |")
    return _dedupe_rows(rows) or ["| 확인 필요 | 추가 검증 항목 없음 또는 근거 부족 | 상세 근거는 Evidence Dossier 참조 |"]


def _sp_analysis_evidence_rows(guide: Mapping[str, Any]) -> list[str]:
    section_refs = {
        "sp_overview": [_primary_evidence_id(guide)],
        "dependency_inventory": ["static.analysis.migration_guide"],
        "dml_impact_matrix": _raw_evidence_ids_from_guide(guide) or ["static.analysis.migration_guide"],
        "call_flow": _raw_evidence_ids_from_guide(guide) or ["static.analysis.migration_guide"],
        "complexity_analysis": ["static.analysis.migration_guide"],
        "appendix": [_primary_evidence_id(guide), "static.analysis.migration_guide"],
    }
    return [
        f"| {section} | {_refs(refs)} | REVIEW_REQUIRED where inference exceeds evidence |"
        for section, refs in section_refs.items()
    ]


def _java_mybatis_evidence_rows(context: GenerationContext, guide: Mapping[str, Any]) -> list[str]:
    return [
        f"| DTO_DRAFT | input params={len(context.input_params)}, result candidates={max(len(context.result_shape), len(context.columns))}, {_refs([_primary_evidence_id(guide), 'static.analysis.migration_guide'])} | field type/name finalization |",
        "| SERVICE_DRAFT | feature branches, DML matrix, phase risks | transaction/exception policy and branch semantics |",
        "| MAPPER_INTERFACE | DML operations and result shape candidates | method names and parameter granularity |",
        "| MAPPER_XML | bounded sanitized statement evidence | SELECT/JOIN/WHERE/SET/DELETE details |",
    ]


def _ai_draft_pack_evidence_rows(context: GenerationContext) -> list[str]:
    pack = _mapping(context.value("aiDraftPack", {}) or {})
    rows = []
    for file in _mapping_items(pack.get("files")):
        rows.append(
            "| "
            f"{_table_text(file.get('artifactType') or 'JAVA_MYBATIS_DRAFT')} `{_table_text(file.get('path') or '')}` | "
            f"operationIds={_refs(file.get('operationIds'))}; evidenceRefs={_refs(file.get('evidenceRefs'))} | "
            f"reviewMarker: {_refs(file.get('reviewMarkers'))} |"
        )
    return rows


def _ai_draft_pack_stage_trace_lines(context: GenerationContext) -> list[str]:
    trace = _mapping(context.value("aiDraftPackTrace", {}) or {})
    pack = _mapping(context.value("aiDraftPack", {}) or {})
    components = _mapping_items(trace.get("componentInvocations")) or _mapping_items(
        pack.get("componentInvocations")
    )
    stage_lines: list[str] = []
    for component in components:
        stage = str(component.get("stage") or "")
        if not stage:
            continue
        failed_rule_ids = _sequence(component.get("failedRuleIds"))
        stage_lines.append(
            "- "
            f"stage={_table_text(stage)} "
            f"status={_table_text(component.get('status') or 'REVIEW_REQUIRED')} "
            f"fileCount={_table_text(component.get('fileCount') or component.get('stageCount') or '')} "
            f"failedRuleIds={_refs(failed_rule_ids)}"
        )
    validation = _mapping(trace.get("validation") or pack.get("validation") or {})
    failed_rules = _sequence(validation.get("failedRuleIds"))
    if failed_rules:
        stage_lines.append(
            "- validation_failure_code: "
            f"{_refs(failed_rules)}; repair_caveat: REVIEW_REQUIRED"
        )
    repair = _mapping(trace.get("repair") or pack.get("repair") or {})
    target_stages = _sequence(repair.get("targetStages"))
    if target_stages:
        stage_lines.append(
            "- repair_routing: "
            f"targetStages={_refs(target_stages)}; caveat=REVIEW_REQUIRED"
        )
    if not stage_lines:
        return ["- REVIEW_REQUIRED: P50 stage trace not attached to this dossier context."]
    return stage_lines


def _sql_statement_evidence_rows(guide: Mapping[str, Any]) -> list[str]:
    rows = []
    for index, item in enumerate(_mapping_items(guide.get("dml_matrix")), start=1):
        operation = str(item.get("operation") or "REVIEW_REQUIRED").upper()
        target = str(item.get("target_ref") or item.get("targetRef") or "REVIEW_REQUIRED")
        refs = _sequence(item.get("evidence_refs") or item.get("evidenceRefs")) or ["static.analysis.migration_guide"]
        evidence_id = str(refs[0])
        rows.append(
            "| "
            f"`stmt_ev_{index}` | "
            f"{_table_text(operation)} | "
            f"`{_table_text(target)}` | "
            f"`{_table_text(_sql_skeleton(operation, target))}` | "
            f"REVIEW_REQUIRED; source={_table_text(evidence_id)} |"
        )
    return rows or ["| `stmt_ev_0` | REVIEW_REQUIRED | `REVIEW_REQUIRED` | `/* REVIEW_REQUIRED: no DML evidence */` | collect static DML evidence |"]


def _operation_model_statement_rows(context: GenerationContext) -> list[str]:
    rows = []
    for item in _mapping_items(context.operation_model.get("statementEvidence")):
        operation = str(item.get("operation") or "REVIEW_REQUIRED").upper()
        target = str(item.get("targetRef") or item.get("target_ref") or "REVIEW_REQUIRED")
        evidence_id = str(item.get("statementId") or "operation_model_statement")
        rows.append(
            "| "
            f"`{_table_text(evidence_id)}` | "
            f"{_table_text(operation)} | "
            f"`{_table_text(target)}` | "
            f"`{_table_text(_sql_skeleton(operation, target))}` | "
            f"reviewMarker: {_refs(item.get('reviewMarkers'))}; evidenceRefs={_refs(item.get('evidenceRefs'))} |"
        )
    return rows


def _sql_skeleton(operation: str, target: str) -> str:
    if operation == "SELECT":
        return f"SELECT /* REVIEW_REQUIRED columns */ FROM {target} WHERE /* REVIEW_REQUIRED predicates */"
    if operation == "INSERT":
        return f"INSERT INTO {target} (/* REVIEW_REQUIRED columns */) VALUES (/* REVIEW_REQUIRED values */)"
    if operation == "UPDATE":
        return f"UPDATE {target} SET /* REVIEW_REQUIRED assignments */ WHERE /* REVIEW_REQUIRED predicates */"
    if operation == "DELETE":
        return f"DELETE FROM {target} WHERE /* REVIEW_REQUIRED predicates */"
    if operation == "MERGE":
        return f"MERGE {target} USING /* REVIEW_REQUIRED source */ ON /* REVIEW_REQUIRED match */"
    if operation in {"EXEC", "EXECUTE", "CALL"}:
        return f"EXEC {target} /* REVIEW_REQUIRED parameters */"
    return f"/* REVIEW_REQUIRED {operation} statement evidence for {target} */"


def _dependency_inventory_table(
    guide: Mapping[str, Any],
    *,
    kind_filter: tuple[str, ...] | None = None,
    status_filter: tuple[str, ...] | None = None,
    fallback: str = "- REVIEW_REQUIRED: dependency evidence is empty.",
) -> list[str]:
    items = _dependency_items(guide, kind_filter=kind_filter, status_filter=status_filter)
    if not items:
        return [fallback]
    lines = [
        "| kind | object | operations | status | evidenceRefs | next evidence |",
        "|---|---|---|---|---|---|",
    ]
    for item in items:
        lines.append(
            "| "
            f"{_table_text(item.get('object_kind'))} | "
            f"`{_table_text(item.get('object_ref'))}` | "
            f"{_table_text(', '.join(str(op) for op in _sequence(item.get('operations'))))} | "
            f"{_table_text(item.get('status') or 'REVIEW_REQUIRED')} | "
            f"{_refs(item.get('evidence_refs') or item.get('evidenceRefs'))} | "
            f"{_table_text(_dependency_next_step(item))} |"
        )
    return lines


def _llm_semantic_lines(context: GenerationContext) -> list[str]:
    payload = _mapping(context.value("llmAnalysis", {}) or {})
    if not payload:
        return ["- REVIEW_REQUIRED: LLM semantic inference evidence is empty."]
    lines = [
        "- boundary: `LLM_INFERENCE_REVIEW_REQUIRED`",
        "- policy: semantic summaries are draft-only and must stay evidence-bound.",
    ]
    for key, label, id_key in (
        ("businessRules", "businessRule", "category"),
        ("modernizationPoints", "modernizationPoint", "area"),
        ("riskFlags", "riskFlag", "code"),
        ("conversionGuidance", "conversionGuidance", "code"),
        ("migrationGuideInsights", "migrationGuideInsight", "section"),
    ):
        for item in _mapping_items(payload.get(key) or payload.get(_snake_case(key))):
            lines.append(
                "- "
                f"{label}: "
                f"{_table_text(item.get(id_key) or item.get('target') or 'REVIEW_REQUIRED')} "
                f"status={_table_text(item.get('status') or 'REVIEW_REQUIRED')} "
                f"evidenceRefs={_refs(item.get('evidenceRefs') or item.get('evidence_refs'))} "
                f"summary={_table_text(item.get('summary') or item.get('description') or '')}"
            )
    for item in _mapping_items(payload.get("reviewMarkers") or payload.get("review_markers")):
        lines.append(
            "- reviewMarker: "
            f"{_table_text(item.get('code') or item.get('category') or 'REVIEW_REQUIRED')} "
            f"evidenceRefs={_refs(item.get('evidenceRefs') or item.get('evidence_refs'))} "
            f"summary={_table_text(item.get('summary') or item.get('reason') or '')}"
        )
    return lines


def _evidence_map_lines(context: GenerationContext, guide: Mapping[str, Any]) -> list[str]:
    lines = ["| id/source | type | object | locator |", "|---|---|---|---|"]
    for entry in _evidence_map_entries(context, guide):
        lines.append(
            "| "
            f"`{_table_text(entry.get('id'))}` | "
            f"{_table_text(entry.get('type'))} | "
            f"`{_table_text(entry.get('object'))}` | "
            f"{_table_text(entry.get('locator'))} |"
        )
    if len(lines) == 2:
        lines.append("| `REVIEW_REQUIRED` | USER_INPUT | `REVIEW_REQUIRED` | request.evidence |")
    return lines


def _evidence_map_entries(context: GenerationContext, guide: Mapping[str, Any]) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for ref in _mapping_items(guide.get("evidence_refs")):
        entries.append(
            {
                "id": str(ref.get("id") or "unnamed_evidence"),
                "type": str(ref.get("type") or "REVIEW_REQUIRED"),
                "object": str(ref.get("object_ref") or "REVIEW_REQUIRED"),
                "locator": str(ref.get("locator") or "REVIEW_REQUIRED"),
            }
        )
    for source in context.evidence_sources:
        entries.append(
            {
                "id": source.reason or source.name or "context.evidence",
                "type": source.evidence_type,
                "object": source.name,
                "locator": source.locator or source.reason,
            }
        )
    trace = _mapping(context.value("llmTrace", {}) or {})
    if trace.get("outputHash"):
        entries.append(
            {
                "id": str(trace.get("outputHash")),
                "type": "LLM_INFERENCE",
                "object": str(trace.get("agentRunId") or "agent-runtime"),
                "locator": "agent-runtime.modelInvocation.outputHash",
            }
        )
    return entries


def _p24_claim_support_lines(guide: Mapping[str, Any]) -> list[str]:
    items: list[tuple[str, Mapping[str, Any]]] = []
    for key in ("sanitized_facts", "dependency_inventory", "dml_matrix", "table_dml_matrix"):
        items.extend((key, item) for item in _mapping_items(guide.get(key)))
    for section in _mapping_items(guide.get("section_expectations")):
        items.append(("section_expectation", section))
        items.extend(("section_claim", claim) for claim in _mapping_items(section.get("claims")))
    call_flow = _mapping(guide.get("call_flow"))
    for branch in _mapping_items(call_flow.get("branches")):
        items.append(("call_flow_branch", branch))
        items.extend(("call_flow_action", action) for action in _mapping_items(branch.get("actions")))
    phase_metrics = _mapping(guide.get("phase_risk_metrics"))
    items.extend(("risk_flag", item) for item in _mapping_items(phase_metrics.get("risk_flags")))
    items.extend(("complexity_metric", item) for item in _mapping_items(phase_metrics.get("complexity_metrics")))
    appendix = _mapping(guide.get("appendix_mappings"))
    items.extend(("appendix_parameter", item) for item in _mapping_items(appendix.get("parameters")))
    items.extend(("appendix_result_field", item) for item in _mapping_items(appendix.get("result_fields")))
    items.extend(("unsupported_claim", item) for item in _mapping_items(guide.get("unsupported_claim_expectations")))
    if not items:
        return ["- REVIEW_REQUIRED: P24/P36 evidence-linked claim support matrix is empty."]
    lines = [
        "### P24/P36 evidence-linked claim support",
        "",
        "| scope | identity | status | evidenceRefs | summary |",
        "|---|---|---|---|---|",
    ]
    for scope, item in items:
        lines.append(
            "| "
            f"{_table_text(scope)} | "
            f"{_table_text(_claim_identity(item))} | "
            f"{_table_text(item.get('status') or item.get('expected_status') or 'REVIEW_REQUIRED')} | "
            f"{_refs(item.get('evidence_refs') or item.get('evidenceRefs'))} | "
            f"{_table_text(_claim_summary(item))} |"
        )
    return lines


def _review_marker_lines(context: GenerationContext, guide: Mapping[str, Any]) -> list[str]:
    markers = _review_markers(context, guide)
    return [f"- reviewMarker: {marker}" for marker in markers]


def _review_markers(context: GenerationContext, guide: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for source in (
        context.value("llmAnalysis", {}) or {},
        context.operation_model,
        context.value("aiDraftPack", {}) or {},
    ):
        if isinstance(source, Mapping):
            values.extend(str(item) for item in _sequence(source.get("reviewMarkers")) if str(item))
            for marker in _mapping_items(source.get("review_markers")):
                values.append(str(marker.get("code") or marker.get("category") or marker))
            for file in _mapping_items(source.get("files")):
                values.extend(str(item) for item in _sequence(file.get("reviewMarkers")) if str(item))
    for item in _mapping_items(guide.get("unsupported_claim_expectations")):
        values.append(str(item.get("claim_code") or "unsupported_claim"))
    return _ordered_unique(values)


def _raw_evidence_ids(context: GenerationContext, guide: Mapping[str, Any]) -> list[str]:
    values = _raw_evidence_ids_from_guide(guide)
    for source in context.evidence_sources:
        values.append(source.reason or source.locator or source.name)
    return _ordered_unique(values)


def _raw_evidence_ids_from_guide(guide: Mapping[str, Any]) -> list[str]:
    values: list[str] = []
    for key in (
        "sanitized_facts",
        "dependency_inventory",
        "dml_matrix",
        "table_dml_matrix",
        "unsupported_claim_expectations",
    ):
        for item in _mapping_items(guide.get(key)):
            values.extend(str(ref) for ref in _sequence(item.get("evidence_refs") or item.get("evidenceRefs")) if str(ref))
    for ref in _mapping_items(guide.get("evidence_refs")):
        if ref.get("id"):
            values.append(str(ref["id"]))
    return _ordered_unique(values)


def _statement_evidence_items(context: GenerationContext, guide: Mapping[str, Any]) -> list[Mapping[str, Any]]:
    return [
        *_mapping_items(guide.get("dml_matrix")),
        *_mapping_items(context.operation_model.get("statementEvidence")),
    ]


def _dependency_items(
    guide: Mapping[str, Any],
    *,
    kind_filter: tuple[str, ...] | None = None,
    status_filter: tuple[str, ...] | None = None,
) -> list[Mapping[str, Any]]:
    items = []
    for item in _mapping_items(guide.get("dependency_inventory")):
        kind = str(item.get("object_kind") or "").lower()
        status = str(item.get("status") or "")
        if kind_filter and not any(token in kind for token in kind_filter):
            continue
        if status_filter and status not in status_filter:
            continue
        items.append(item)
    return items


def _is_confirmed(item: Mapping[str, Any]) -> bool:
    status = str(item.get("status") or "").casefold()
    return status not in {"needs verification", "review_required", "확인 필요"} and "review" not in status


def _object_db(object_ref: str, *, default_db: str) -> str:
    parts = _identifier_parts(object_ref)
    if len(parts) >= 3:
        return parts[-3].upper()
    return default_db.upper() if default_db else "확인 필요"


def _schema_and_name(object_ref: str) -> tuple[str, str]:
    parts = _identifier_parts(object_ref)
    if len(parts) >= 2:
        return parts[-2], parts[-1]
    if parts:
        return "확인 필요", parts[-1]
    return "확인 필요", "확인 필요"


def _identifier_parts(value: str) -> list[str]:
    return [
        _strip_identifier_quotes(part)
        for part in str(value).strip().split(".")
        if _strip_identifier_quotes(part)
    ]


def _strip_identifier_quotes(value: str) -> str:
    stripped = value.strip()
    if stripped.startswith("[") and stripped.endswith("]"):
        return stripped[1:-1].strip()
    return stripped


def _parameter_name(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    return text if text.startswith("@") else f"@{text}"


def _primary_branch_parameter(parameter: str) -> bool:
    lowered = parameter.lower()
    return lowered == "@crudflag" or lowered.endswith("flag")


def _crud_code_from_text(value: object) -> str:
    text = str(value or "")
    match = re.search(r"@?CRUDFlag\s*=\s*N?'([^']+)'", text, flags=re.IGNORECASE)
    if match:
        return match.group(1).upper()
    match = re.search(r"\bcrud_([a-z0-9_]+?)_(?:select|insert|update|delete|execute|call|compute|validate)\b", text, flags=re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return ""


def _parameter_description(name: str) -> str:
    normalized = _parameter_name(name).lower()
    if normalized == "@crudflag":
        return "업무 처리 구분"
    if "bondkindcode" in normalized:
        return "업무/유형 코드"
    if "gubunflag" in normalized:
        return "세부 업무 구분"
    if "flag" in normalized:
        return "분기 플래그"
    if "code" in normalized or "type" in normalized:
        return "업무 코드"
    return "확인 필요"


def _human_claim_type(item: Mapping[str, Any]) -> str:
    text = str(item.get("obligation") or item.get("claim_code") or "확인 필요")
    if "dependency" in text:
        return "의존성 확인 필요"
    if "cross" in text:
        return "Cross-DB 확인 필요"
    if "business" in text:
        return "업무 규칙 확인 필요"
    if "function" in text:
        return "함수 확인 필요"
    if "table" in text:
        return "테이블 확인 필요"
    return "확인 필요"


def _metric_count(metrics: object, metric_name: str) -> int:
    for item in _mapping_items(metrics):
        if str(item.get("metric") or "") == metric_name:
            return int(item.get("count") or 0)
    return 0


def _mark(value: object) -> str:
    text = str(value or "").strip().upper()
    return "Y" if text in {"Y", "YES", "TRUE", "1", "✓"} else ""


def _status_label(value: object) -> str:
    text = str(value or "").strip()
    if not text or "review" in text.casefold() or "needs verification" in text.casefold():
        return "확인 필요"
    if text.casefold() in {"accepted", "confirmed", "observed"}:
        return "확인됨"
    return _human_text(text)


def _human_text(value: object) -> str:
    text = _table_text(value)
    if not text:
        return "확인 필요"
    if any(marker in text for marker in HUMAN_REDIRECT_MARKERS):
        return "상세 근거는 Evidence Dossier 참조"
    replacements = {
        "REVIEW_REQUIRED": "확인 필요",
        "Needs verification": "확인 필요",
        "review_required": "확인 필요",
        "STATIC_ANALYSIS": "정적 분석",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    return text or "확인 필요"


def _table_text(value: object) -> str:
    return str(value or "").replace("|", "/").replace("\n", " ").strip()


def _refs(refs: object) -> str:
    values = [str(ref) for ref in _sequence(refs) if str(ref)]
    return ", ".join(f"`{_table_text(ref)}`" for ref in values) or "`REVIEW_REQUIRED`"


def _primary_evidence_id(guide: Mapping[str, Any]) -> str:
    refs = _mapping_items(guide.get("evidence_refs"))
    if refs:
        return str(refs[0].get("id") or "ev_request_target")
    return "ev_request_target"


def _dependency_description(item: Mapping[str, Any]) -> str:
    return str(
        item.get("description")
        or item.get("table_description")
        or item.get("tableDescription")
        or ""
    ).strip()


def _dependency_next_step(item: Mapping[str, Any]) -> str:
    values = [
        item.get("why_uncertain"),
        item.get("unresolvedReason"),
        item.get("value_or_state_patterns"),
        item.get("what_to_extract_next"),
    ]
    return " / ".join(_table_text(value) for value in values if _table_text(value)) or "REVIEW_REQUIRED"


def _claim_identity(item: Mapping[str, Any]) -> str:
    parts = []
    for key in (
        "id",
        "claim_code",
        "obligation",
        "fact_type",
        "object_ref",
        "target_ref",
        "dependency_ref",
        "operation",
        "phase",
        "code",
        "name",
        "metric",
    ):
        value = item.get(key)
        if value:
            parts.append(str(value))
    return " / ".join(parts) or "REVIEW_REQUIRED"


def _claim_summary(item: Mapping[str, Any]) -> str:
    values = [
        item.get("summary"),
        item.get("condition_summary"),
        item.get("impact"),
        item.get("keys_join_where_summary"),
        item.get("important_columns_or_patterns"),
        item.get("evidence_rule"),
        item.get("evidenceRule"),
        item.get("notes"),
        item.get("claim_type"),
    ]
    return " / ".join(_table_text(value) for value in values if _table_text(value)) or "REVIEW_REQUIRED"


def _snake_case(value: str) -> str:
    return re.sub(r"(?<!^)(?=[A-Z])", "_", value).lower()


def _join_unique_text(left: object, right: object) -> str:
    return " / ".join(_ordered_unique([left, right]))


def _ordered_unique(values: Sequence[Any]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        text = str(value)
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _dedupe_rows(rows: Sequence[str]) -> list[str]:
    return _ordered_unique(rows)


def _mapping_items(value: object) -> list[Mapping[str, Any]]:
    return [item for item in _sequence(value) if isinstance(item, Mapping)]


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _sequence(value: object) -> list[Any]:
    if isinstance(value, Sequence) and not isinstance(value, str | bytes):
        return list(value)
    return []
