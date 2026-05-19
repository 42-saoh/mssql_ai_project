from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any

from ai_agent_domain import ArtifactType

from ai_agent_generation.models import GenerationContext, RenderedArtifact
from ai_agent_generation.utils import ensure_trailing_newline


class SPAnalysisDocumentRenderer:
    artifact_type = ArtifactType.SP_ANALYSIS_DOC

    def render(self, context: GenerationContext) -> RenderedArtifact:
        guide = _guide_payload(context)
        target_ref = _target_ref(context, guide)
        db_context = _mapping(guide.get("db_context"))
        lines = [
            f"# Migration Guide: {target_ref}",
            "",
            f"> **문서 생성일**: DRAFT",
            f"> **대상 SP**: `{target_ref}`",
            f"> **업무명**: {context.description or context.entity_name or 'REVIEW_REQUIRED'}",
            f"> **상태**: DRAFT / production_ready=false",
            "",
            "<!-- section:sp_overview -->",
            "## 1. SP 개요 (Overview)",
            "",
            "### 1.1 기본 정보",
            "",
            "| 항목 | 값 | 상태 | 근거 |",
            "|---|---|---|---|",
            *_overview_rows(context, guide),
            "",
            "<!-- section:feature_branch_taxonomy -->",
            "### 1.2 주요 기능",
            "",
            "| 기능/분기 | 조건 | 요약 | 상태 | 근거 |",
            "|---|---|---|---|---|",
            *_feature_rows(guide),
            "",
            "#### LLM semantic evidence boundary",
            "",
            *_llm_semantic_lines(context),
            "",
            "### 1.3 지원 서브시스템",
            "",
            "| 구분 | 값 | 비고 |",
            "|---|---|---|",
            f"| metadata profile | `{_table_text(db_context.get('metadata_profile_id') or 'REVIEW_REQUIRED')}` | read-only metadata boundary |",
            f"| target DB | `{_table_text(db_context.get('target_db') or 'REVIEW_REQUIRED')}` | catalog metadata only |",
            f"| platform DB | `{_table_text(db_context.get('platform_db') or 'REVIEW_REQUIRED')}` | artifact storage, no business DDL/DML |",
            "",
            "### 1.4 주요 코드/플래그",
            "",
            *_flag_lines(context, guide),
            "",
            "<!-- section:dependency_inventory -->",
            "## 2. 의존성 인벤토리 (Dependency Inventory)",
            "",
            "### 2.1 테이블 의존성",
            "",
            *_dependency_inventory_table(
                guide,
                kind_filter=("table", "view"),
                include_description=True,
            ),
            "",
            "### 2.2 UDF/함수 의존성",
            "",
            *_dependency_inventory_table(guide, kind_filter=("function", "udf")),
            "",
            "### 2.3 저장 프로시저 호출",
            "",
            *_dependency_inventory_table(guide, kind_filter=("procedure", "stored_procedure")),
            "",
            "### 2.4 Dynamic SQL / 미확정 의존성",
            "",
            *_dependency_inventory_table(
                guide,
                status_filter=("Needs verification", "REVIEW_REQUIRED"),
                fallback="- REVIEW_REQUIRED: dynamic SQL 또는 미확정 의존성 근거가 추가로 필요합니다.",
            ),
            "",
            "<!-- section:dml_impact_matrix -->",
            "## 3. DML 영향도 매트릭스 (Data Change Impact Matrix)",
            "",
            *_dml_matrix_lines(guide, target_db=str(db_context.get("target_db") or "")),
            "",
            "<!-- section:call_flow -->",
            "## 4. 호출 흐름 (Call Flow)",
            "",
            "### 4.1 전체 구조",
            "",
            "```text",
            *_call_flow_lines(context, guide),
            "```",
            "",
            "<!-- section:critical_phase_analysis -->",
            "### 4.2 단계별 상세 분석",
            "",
            "| 단계 | 조건/트리거 | 처리 요약 | 위험/Caveat | 근거 |",
            "|---|---|---|---|---|",
            *_phase_rows(guide),
            "",
            "#### P24 phase evidence compatibility",
            "",
            "| Phase | 주요 읽기 | 주요 쓰기 | 위험/검토점 | 상태 | 근거 |",
            "|---|---|---|---|---|---|",
            *_p24_phase_rows(guide),
            "",
            "<!-- section:complexity_risk_metrics -->",
            "## 5. SP 복잡도 분석 (Complexity Analysis)",
            "",
            "### 5.1 복잡도 지표",
            "",
            "| 지표 | 값 | 근거/비고 |",
            "|---|---|---|",
            *_complexity_rows(guide),
            "",
            "### 5.2 Cross-DB / 트랜잭션 위험",
            "",
            *_risk_lines(guide),
            "",
            "<!-- section:migration_strategy -->",
            "<!-- section:appendix_mappings -->",
            "<!-- section:metadata_extraction_appendix -->",
            "<!-- section:evidence_assumptions_review -->",
            "## 6. Appendix",
            "",
            "### 6.1 입력 파라미터",
            "",
            "| 이름 | 타입 | 필수 | 근거 |",
            "|---|---|---|---|",
            *_parameter_rows(context, guide),
            "",
            "### 6.2 결과 필드 후보",
            "",
            "| 필드 | 근거 | 상태 |",
            "|---|---|---|",
            *_result_field_rows(context, guide),
            "",
            "### 6.3 Evidence Map",
            "",
            *_evidence_map_lines(context, guide),
            "",
            *_p24_claim_support_lines(guide),
            "",
            "### 6.4 Caveat / 다음 수집 항목",
            "",
            "- REVIEW_REQUIRED 항목은 업무 규칙, SQL predicate, transaction boundary 근거를 보강해야 합니다.",
            "- generated_source_application: `not_performed`",
            "- full SP definition은 저장하지 않았고 bounded sanitized statement evidence만 사용합니다.",
            "- row data 조회, procedure 실행, business DB DDL/DML, 자동 DDL 적용은 수행하지 않습니다.",
        ]
        return RenderedArtifact(
            artifact_type=self.artifact_type,
            title=f"Migration Guide: {target_ref}",
            content=ensure_trailing_newline("\n".join(lines)),
            evidence_refs=context.evidence_refs,
            registry_refs=("template:sp_analysis_doc@0.2.0", "contract:p36_output_renewal@0.1.0"),
            assumptions=context.evidence_assumptions,
            review_required=True,
        )


class DependencyReportRenderer:
    artifact_type = ArtifactType.DEPENDENCY_REPORT

    def render(self, context: GenerationContext) -> RenderedArtifact:
        guide = _guide_payload(context)
        target_ref = _target_ref(context, guide)
        lines = [
            f"# {target_ref} Evidence Dossier",
            "",
            "## generation_evidence_summary",
            "- 상태: DRAFT / production_ready=false",
            "- 역할: dependency-only 문서가 아니라 SP 분석 및 Java/MyBatis 산출물 생성 근거 보고서입니다.",
            "- SQL 근거: full SP definition이 아닌 bounded sanitized statement evidence만 사용합니다.",
            "",
            "## sp_analysis_evidence",
            "",
            "| 산출물 섹션 | 사용 근거 | Caveat |",
            "|---|---|---|",
            *_sp_analysis_evidence_rows(guide),
            "",
            "## java_mybatis_evidence",
            "",
            "| 산출물 | 생성 근거 | REVIEW_REQUIRED 항목 |",
            "|---|---|---|",
            *_java_mybatis_evidence_rows(context, guide),
            "",
            "## sql_statement_evidence",
            "",
            "| evidence id | operation | target | sanitized skeleton | caveat |",
            "|---|---|---|---|---|",
            *_sql_statement_evidence_rows(guide),
            "",
            "## dependency_closure_evidence",
            "",
            *_dependency_inventory_table(guide, fallback="- REVIEW_REQUIRED: dependency closure 근거가 비어 있습니다."),
            "",
            "## semantic_inference_evidence",
            "",
            *_llm_semantic_lines(context),
            "",
            "## evidence_map",
            "",
            *_evidence_map_lines(context, guide),
            "",
            "## known_caveats",
            "- REVIEW_REQUIRED: SQL JOIN/WHERE/SET/DELETE predicate는 statement evidence만으로 확정하지 않습니다.",
            "- REVIEW_REQUIRED: business branch 의미는 LLM 또는 static scan 단서일 수 있어 운영 반영 전 검토가 필요합니다.",
            "- REVIEW_REQUIRED: Java/MyBatis 초안은 자동 배포 또는 소스 반영 대상이 아닙니다.",
            "",
            "## next_evidence_to_collect",
            "- catalog-confirmed dependency closure와 unresolved reference 해소 결과",
            "- SELECT result shape 확정 근거와 column-level DTO 매핑 근거",
            "- transaction boundary, exception handling, status code mapping 근거",
            "- branch condition별 업무 의미와 DML 영향 범위 근거",
            "",
            "## draft_readiness",
            "- 근거형 초안 작성에는 충분하지만 production_ready=false 상태입니다.",
            "- 자동 DDL 적용, procedure 실행, row data 조회, 자동 배포는 수행하지 않습니다.",
        ]
        return RenderedArtifact(
            artifact_type=self.artifact_type,
            title=f"{target_ref} Evidence Dossier",
            content=ensure_trailing_newline("\n".join(lines)),
            evidence_refs=context.evidence_refs,
            registry_refs=("template:dependency_report@0.2.0", "contract:p36_output_renewal@0.1.0"),
            assumptions=context.evidence_assumptions,
            review_required=True,
        )


def _guide_payload(context: GenerationContext) -> dict[str, Any]:
    payload = context.value("migrationGuide", {}) or {}
    return dict(payload) if isinstance(payload, Mapping) else {}


def _target_ref(context: GenerationContext, guide: Mapping[str, Any]) -> str:
    return str(guide.get("target_ref") or context.sp_name or context.entity_name)


def _mapping(value: object) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _sequence(value: object) -> list[Any]:
    return list(value) if isinstance(value, Sequence) and not isinstance(value, str | bytes) else []


def _table_text(value: object) -> str:
    return str(value).replace("|", "/").replace("\n", " ").strip()


def _refs(refs: object) -> str:
    values = [str(ref) for ref in _sequence(refs) if str(ref)]
    return ", ".join(f"`{_table_text(ref)}`" for ref in values) or "`REVIEW_REQUIRED`"


def _overview_rows(context: GenerationContext, guide: Mapping[str, Any]) -> list[str]:
    rows = []
    for item in _sequence(guide.get("overview_rows")):
        if not isinstance(item, Mapping):
            continue
        rows.append(
            "| "
            f"{_table_text(item.get('label'))} | "
            f"`{_table_text(item.get('value'))}` | "
            f"{_table_text(item.get('status') or 'REVIEW_REQUIRED')} | "
            f"{_refs(item.get('evidence_refs'))} |"
        )
    if rows:
        return rows
    return [
        f"| 대상 SP | `{_table_text(context.sp_name)}` | REVIEW_REQUIRED | `request.target` |",
        f"| 대표 테이블 | `{_table_text(context.table_name)}` | REVIEW_REQUIRED | `request.tableName` |",
    ]


def _feature_rows(guide: Mapping[str, Any]) -> list[str]:
    rows = []
    for item in _sequence(guide.get("feature_branch_rows")):
        if not isinstance(item, Mapping):
            continue
        rows.append(
            "| "
            f"{_table_text(item.get('feature'))} | "
            f"{_table_text(item.get('condition'))} | "
            f"{_table_text(item.get('summary'))} | "
            f"{_table_text(item.get('status') or 'REVIEW_REQUIRED')} | "
            f"{_refs(item.get('evidence_refs'))} |"
        )
    return rows or ["| REVIEW_REQUIRED | 업무 기능 분류 필요 | 추가 근거 수집 필요 | REVIEW_REQUIRED | `static.analysis.migration_guide` |"]


def _llm_semantic_lines(context: GenerationContext) -> list[str]:
    payload = _mapping(context.value("llmAnalysis", {}) or {})
    if not payload:
        return ["- REVIEW_REQUIRED: LLM semantic inference evidence가 없습니다."]

    lines = [
        "- boundary: `LLM_INFERENCE_REVIEW_REQUIRED`",
        "- policy: semantic summaries are draft-only and must stay evidence-bound.",
    ]
    for item in _sequence(payload.get("businessRules")):
        if not isinstance(item, Mapping):
            continue
        lines.append(
            "- businessRule: "
            f"{_table_text(item.get('category') or 'REVIEW_REQUIRED')} "
            f"status={_table_text(item.get('status') or 'REVIEW_REQUIRED')} "
            f"evidenceRefs={_refs(item.get('evidenceRefs') or item.get('evidence_refs'))} "
            f"summary={_table_text(item.get('summary'))}"
        )
    for item in _sequence(payload.get("modernizationPoints")):
        if not isinstance(item, Mapping):
            continue
        lines.append(
            "- modernizationPoint: "
            f"{_table_text(item.get('area') or item.get('category') or 'REVIEW_REQUIRED')} "
            f"status={_table_text(item.get('status') or 'REVIEW_REQUIRED')} "
            f"evidenceRefs={_refs(item.get('evidenceRefs') or item.get('evidence_refs'))} "
            f"summary={_table_text(item.get('summary'))}"
        )
    for item in _sequence(payload.get("riskFlags") or payload.get("risk_flags")):
        if not isinstance(item, Mapping):
            continue
        lines.append(
            "- riskFlag: "
            f"{_table_text(item.get('code') or 'REVIEW_REQUIRED')} "
            f"severity={_table_text(item.get('severity') or 'REVIEW_REQUIRED')} "
            f"status={_table_text(item.get('status') or 'REVIEW_REQUIRED')} "
            f"evidenceRefs={_refs(item.get('evidenceRefs') or item.get('evidence_refs'))} "
            f"summary={_table_text(item.get('summary'))}"
        )
    for item in _sequence(payload.get("conversionGuidance") or payload.get("conversion_guidance")):
        if not isinstance(item, Mapping):
            continue
        lines.append(
            "- conversionGuidance: "
            f"{_table_text(item.get('code') or item.get('target') or 'REVIEW_REQUIRED')} "
            f"status={_table_text(item.get('status') or 'REVIEW_REQUIRED')} "
            f"evidenceRefs={_refs(item.get('evidenceRefs') or item.get('evidence_refs'))} "
            f"summary={_table_text(item.get('summary'))}"
        )
    for item in _sequence(payload.get("migrationGuideInsights") or payload.get("migration_guide_insights")):
        if not isinstance(item, Mapping):
            continue
        lines.append(
            "- migrationGuideInsight: "
            f"{_table_text(item.get('section') or 'REVIEW_REQUIRED')} "
            f"status={_table_text(item.get('status') or 'REVIEW_REQUIRED')} "
            f"evidenceRefs={_refs(item.get('evidenceRefs') or item.get('evidence_refs'))} "
            f"summary={_table_text(item.get('summary'))}"
        )
    for item in _sequence(payload.get("reviewMarkers") or payload.get("review_markers")):
        if not isinstance(item, Mapping):
            continue
        lines.append(
            "- reviewMarker: "
            f"{_table_text(item.get('code') or item.get('category') or 'REVIEW_REQUIRED')} "
            f"evidenceRefs={_refs(item.get('evidenceRefs') or item.get('evidence_refs'))} "
            f"summary={_table_text(item.get('summary') or item.get('reason'))}"
        )

    if len(lines) == 2:
        lines.append("- REVIEW_REQUIRED: semantic claim array가 비어 있습니다.")
    return lines


def _flag_lines(context: GenerationContext, guide: Mapping[str, Any]) -> list[str]:
    flags = []
    for param in context.input_params:
        if "code" in param.name.lower() or "flag" in param.name.lower() or "type" in param.name.lower():
            flags.append(f"- `{param.name}`: {param.db_type} / REVIEW_REQUIRED: 코드 의미 확인 필요")
    risk_flags = _mapping(_mapping(guide.get("phase_risk_metrics")).get("risk_flags"))
    for key, value in risk_flags.items():
        flags.append(f"- `{_table_text(key)}`: {_table_text(value)}")
    for item in _sequence(_mapping(guide.get("phase_risk_metrics")).get("risk_flags")):
        if not isinstance(item, Mapping):
            continue
        flags.append(
            "- "
            f"`{_table_text(item.get('code') or 'REVIEW_REQUIRED')}`: "
            f"{_table_text(item.get('severity') or 'REVIEW_REQUIRED')} / "
            f"{_table_text(item.get('status') or 'REVIEW_REQUIRED')} / "
            f"{_refs(item.get('evidence_refs') or item.get('evidenceRefs'))}"
        )
    return flags or ["- REVIEW_REQUIRED: 코드/플래그 의미를 확정할 근거가 아직 부족합니다."]


def _dependency_items(
    guide: Mapping[str, Any],
    *,
    kind_filter: tuple[str, ...] | None = None,
    status_filter: tuple[str, ...] | None = None,
) -> list[Mapping[str, Any]]:
    items = []
    for item in _sequence(guide.get("dependency_inventory")):
        if not isinstance(item, Mapping):
            continue
        kind = str(item.get("object_kind") or "").lower()
        status = str(item.get("status") or "")
        if kind_filter and not any(token in kind for token in kind_filter):
            continue
        if status_filter and status not in status_filter:
            continue
        items.append(item)
    return items


def _dependency_inventory_table(
    guide: Mapping[str, Any],
    *,
    kind_filter: tuple[str, ...] | None = None,
    status_filter: tuple[str, ...] | None = None,
    include_description: bool = False,
    fallback: str = "- REVIEW_REQUIRED: 해당 범주의 의존성 근거가 없습니다.",
) -> list[str]:
    items = _dependency_items(guide, kind_filter=kind_filter, status_filter=status_filter)
    if not items:
        return [fallback]
    if include_description:
        lines = [
            "| 종류 | 객체 | description | operation | 참조 방식 | 상태 | 근거 | 다음 수집 |",
            "|---|---|---|---|---|---|---|---|",
        ]
        for item in items:
            lines.append(
                "| "
                f"{_table_text(item.get('object_kind'))} | "
                f"`{_table_text(item.get('object_ref'))}` | "
                f"{_table_text(_dependency_description(item))} | "
                f"{_table_text(', '.join(str(op) for op in _sequence(item.get('operations'))))} | "
                f"{_table_text(item.get('how_referenced') or item.get('join_or_where_summary'))} | "
                f"{_table_text(item.get('status') or 'REVIEW_REQUIRED')} | "
                f"{_refs(item.get('evidence_refs'))} | "
                f"{_table_text(_dependency_next_step(item))} |"
            )
        return lines
    lines = [
        "| 종류 | 객체 | operation | 참조 방식 | 상태 | 근거 | 다음 수집 |",
        "|---|---|---|---|---|---|---|",
    ]
    for item in items:
        lines.append(
            "| "
            f"{_table_text(item.get('object_kind'))} | "
            f"`{_table_text(item.get('object_ref'))}` | "
            f"{_table_text(', '.join(str(op) for op in _sequence(item.get('operations'))))} | "
            f"{_table_text(item.get('how_referenced') or item.get('join_or_where_summary'))} | "
            f"{_table_text(item.get('status') or 'REVIEW_REQUIRED')} | "
            f"{_refs(item.get('evidence_refs'))} | "
            f"{_table_text(_dependency_next_step(item))} |"
        )
    return lines


def _dependency_description(item: Mapping[str, Any]) -> str:
    description = str(
        item.get("description")
        or item.get("table_description")
        or item.get("tableDescription")
        or ""
    ).strip()
    if description:
        return description
    kind = str(item.get("object_kind") or "").lower()
    if "table" in kind or "view" in kind:
        return "REVIEW_REQUIRED"
    return ""


def _dependency_next_step(item: Mapping[str, Any]) -> str:
    values = [
        item.get("why_uncertain"),
        item.get("unresolvedReason"),
        item.get("value_or_state_patterns"),
        item.get("what_to_extract_next"),
    ]
    text = " / ".join(_table_text(value) for value in values if _table_text(value))
    return text or "REVIEW_REQUIRED"


def _dml_matrix_lines(guide: Mapping[str, Any], *, target_db: str) -> list[str]:
    items = [item for item in _sequence(guide.get("dml_matrix")) if isinstance(item, Mapping)]
    if not items:
        return ["- REVIEW_REQUIRED: DML 영향도 근거가 없습니다."]
    grouped: dict[str, list[Mapping[str, Any]]] = {}
    for item in items:
        target = str(item.get("target_ref") or "REVIEW_REQUIRED")
        db_name = target.split(".", 1)[0] if "." in target else (target_db or "REVIEW_REQUIRED")
        grouped.setdefault(db_name, []).append(item)
    lines: list[str] = []
    for db_name, db_items in sorted(grouped.items()):
        lines.extend(
            [
                f"### {db_name}",
                "",
                "| operation | target | phase | impact | key/join/where | status | evidence |",
                "|---|---|---|---|---|---|---|",
            ]
        )
        for item in db_items:
            lines.append(
                "| "
                f"{_table_text(item.get('operation'))} | "
                f"`{_table_text(item.get('target_ref'))}` | "
                f"{_table_text(item.get('phase'))} | "
                f"{_table_text(item.get('impact'))} | "
                f"{_table_text(item.get('keys_join_where_summary'))} | "
                f"{_table_text(item.get('status') or 'REVIEW_REQUIRED')} | "
                f"{_refs(item.get('evidence_refs'))} |"
            )
        lines.append("")
    return lines


def _call_flow_lines(context: GenerationContext, guide: Mapping[str, Any]) -> list[str]:
    call_flow = [str(item) for item in _sequence(guide.get("call_flow")) if str(item)]
    if call_flow:
        return call_flow
    call_flow_mapping = _mapping(guide.get("call_flow"))
    branches = [item for item in _sequence(call_flow_mapping.get("branches")) if isinstance(item, Mapping)]
    if branches:
        lines = [f"{context.sp_name or context.entity_name}"]
        for branch in branches:
            branch_label = branch.get("phase") or branch.get("id") or "REVIEW_REQUIRED"
            condition = (
                branch.get("condition")
                or branch.get("trigger")
                or branch.get("condition_summary")
                or "REVIEW_REQUIRED"
            )
            lines.append(f"  -> {branch_label}: {condition}")
            for action in _sequence(branch.get("actions")):
                if not isinstance(action, Mapping):
                    continue
                operation = action.get("operation") or action.get("type") or "ACTION"
                target = (
                    action.get("target_ref")
                    or action.get("targetRef")
                    or action.get("object_ref")
                    or action.get("dependency_ref")
                    or ""
                )
                summary = action.get("summary") or action.get("description") or ""
                refs = ", ".join(str(ref) for ref in _sequence(action.get("evidence_refs") or action.get("evidenceRefs")))
                lines.append(f"     - {operation} {target} {summary} evidence={refs or 'REVIEW_REQUIRED'}")
        return lines
    return [
        f"{context.sp_name or context.entity_name}",
        "  -> REVIEW_REQUIRED: branch condition analysis",
        "  -> REVIEW_REQUIRED: DML/result shape reconstruction",
    ]


def _phase_rows(guide: Mapping[str, Any]) -> list[str]:
    rows = []
    for item in _sequence(guide.get("critical_phase_rows")):
        if not isinstance(item, Mapping):
            continue
        rows.append(
            "| "
            f"{_table_text(item.get('phase') or item.get('name'))} | "
            f"{_table_text(item.get('condition') or item.get('trigger') or 'REVIEW_REQUIRED')} | "
            f"{_table_text(item.get('summary') or item.get('processing_summary'))} | "
            f"{_table_text(item.get('risk') or item.get('caveat') or 'REVIEW_REQUIRED')} | "
            f"{_refs(item.get('evidence_refs'))} |"
        )
    return rows or ["| REVIEW_REQUIRED | REVIEW_REQUIRED | 단계별 흐름 근거 필요 | REVIEW_REQUIRED | `static.analysis.migration_guide` |"]


def _p24_phase_rows(guide: Mapping[str, Any]) -> list[str]:
    rows = []
    for item in _sequence(guide.get("critical_phase_rows")):
        if not isinstance(item, Mapping):
            continue
        rows.append(
            "| "
            f"{_table_text(item.get('phase') or item.get('name') or 'REVIEW_REQUIRED')} | "
            f"{_table_text(', '.join(str(value) for value in _sequence(item.get('reads'))))} | "
            f"{_table_text(', '.join(str(value) for value in _sequence(item.get('writes'))))} | "
            f"{_table_text(item.get('risk') or item.get('caveat') or 'REVIEW_REQUIRED')} | "
            f"{_table_text(item.get('status') or 'REVIEW_REQUIRED')} | "
            f"{_refs(item.get('evidence_refs') or item.get('evidenceRefs'))} |"
        )
    return rows or ["| REVIEW_REQUIRED |  |  | REVIEW_REQUIRED | REVIEW_REQUIRED | `static.analysis.migration_guide` |"]


def _complexity_rows(guide: Mapping[str, Any]) -> list[str]:
    metrics = _mapping(_mapping(guide.get("phase_risk_metrics")).get("complexity_metrics"))
    rows = [
        f"| branch_count | {_table_text(_mapping(guide.get('phase_risk_metrics')).get('branch_count') or 0)} | phase risk metric |",
        f"| dml_operation_count | {_table_text(_mapping(guide.get('phase_risk_metrics')).get('dml_operation_count') or 0)} | DML scan count |",
        f"| complexity_score | {_table_text(_mapping(guide.get('phase_risk_metrics')).get('complexity_score') or 'REVIEW_REQUIRED')} | derived draft metric |",
    ]
    for key, value in sorted(metrics.items()):
        rows.append(f"| {_table_text(key)} | {_table_text(value)} | static analysis metric |")
    for item in _sequence(_mapping(guide.get("phase_risk_metrics")).get("complexity_metrics")):
        if not isinstance(item, Mapping):
            continue
        rows.append(
            "| "
            f"{_table_text(item.get('metric') or 'REVIEW_REQUIRED')} | "
            f"{_table_text(item.get('count') or 0)} | "
            f"{_table_text(item.get('evidence_rule') or item.get('evidenceRule') or item.get('notes') or 'static analysis metric')} |"
        )
    return rows


def _risk_lines(guide: Mapping[str, Any]) -> list[str]:
    items = [item for item in _sequence(guide.get("dml_matrix")) if isinstance(item, Mapping)]
    cross_db_targets = sorted(
        {
            str(item.get("target_ref"))
            for item in items
            if len(str(item.get("target_ref") or "").split(".")) >= 3
        }
    )
    lines = [
        "| 위험 | 상태 | 설명 |",
        "|---|---|---|",
        "| transaction boundary | REVIEW_REQUIRED | DML이 확인되면 Java service transaction 정책 검토가 필요합니다. |",
    ]
    if cross_db_targets:
        lines.append(
            "| cross database reference | REVIEW_REQUIRED | "
            + ", ".join(f"`{_table_text(target)}`" for target in cross_db_targets)
            + " |"
        )
    else:
        lines.append("| cross database reference | REVIEW_REQUIRED | metadata/profile 기준 추가 확인 필요 |")
    return lines


def _parameter_rows(context: GenerationContext, guide: Mapping[str, Any]) -> list[str]:
    refs = _refs([_primary_evidence_id(guide)])
    rows = [
        f"| `{_table_text(param.name)}` | `{_table_text(param.db_type)}` | {str(param.required).lower()} | {refs} |"
        for param in context.input_params
    ]
    return rows or ["| REVIEW_REQUIRED | REVIEW_REQUIRED | false | `request.inputParams` |"]


def _result_field_rows(context: GenerationContext, guide: Mapping[str, Any]) -> list[str]:
    rows = [f"| `{_table_text(field)}` | `static.analysis.migration_guide` | REVIEW_REQUIRED |" for field in context.result_shape]
    if rows:
        return rows
    rows = [f"| `{_table_text(column.name)}` | `{_table_text(column.description or column.name)}` | REVIEW_REQUIRED |" for column in context.columns]
    return rows or ["| REVIEW_REQUIRED | result shape evidence needed | REVIEW_REQUIRED |"]


def _primary_evidence_id(guide: Mapping[str, Any]) -> str:
    refs = _sequence(guide.get("evidence_refs"))
    if refs and isinstance(refs[0], Mapping):
        return str(refs[0].get("id") or "ev_request_target")
    return "ev_request_target"


def _evidence_map_lines(context: GenerationContext, guide: Mapping[str, Any]) -> list[str]:
    lines = ["| id/source | type | object | locator |", "|---|---|---|---|"]
    for ref in _sequence(guide.get("evidence_refs")):
        if not isinstance(ref, Mapping):
            continue
        lines.append(
            "| "
            f"`{_table_text(ref.get('id'))}` | "
            f"{_table_text(ref.get('type'))} | "
            f"`{_table_text(ref.get('object_ref'))}` | "
            f"{_table_text(ref.get('locator'))} |"
        )
    for source in context.evidence_sources:
        lines.append(
            "| "
            f"`{_table_text(source.name)}` | "
            f"{_table_text(source.evidence_type)} | "
            f"`{_table_text(source.name)}` | "
            f"{_table_text(source.locator or source.reason)} |"
        )
    if len(lines) == 2:
        lines.append("| `REVIEW_REQUIRED` | USER_INPUT | `REVIEW_REQUIRED` | request.evidence |")
    return lines


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
    items.extend(
        ("complexity_metric", item)
        for item in _mapping_items(phase_metrics.get("complexity_metrics"))
    )
    appendix = _mapping(guide.get("appendix_mappings"))
    items.extend(("appendix_parameter", item) for item in _mapping_items(appendix.get("parameters")))
    items.extend(("appendix_result_field", item) for item in _mapping_items(appendix.get("result_fields")))
    items.extend(
        ("unsupported_claim", item)
        for item in _mapping_items(guide.get("unsupported_claim_expectations"))
    )
    if not items:
        return ["- REVIEW_REQUIRED: P24/P36 evidence-linked claim support matrix가 비어 있습니다."]

    lines = [
        "#### P24/P36 evidence-linked claim support",
        "",
        "| scope | identity | status | evidence | summary |",
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


def _mapping_items(value: object) -> list[Mapping[str, Any]]:
    return [item for item in _sequence(value) if isinstance(item, Mapping)]


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


def _sp_analysis_evidence_rows(guide: Mapping[str, Any]) -> list[str]:
    section_refs = {
        "1. SP 개요": [_primary_evidence_id(guide)],
        "2. 의존성 인벤토리": ["static.analysis.migration_guide"],
        "3. DML 영향도 매트릭스": ["static.analysis.migration_guide"],
        "4. 호출 흐름": ["static.analysis.migration_guide"],
        "5. 복잡도 분석": ["static.analysis.migration_guide"],
        "6. Appendix": [_primary_evidence_id(guide), "static.analysis.migration_guide"],
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


def _sql_statement_evidence_rows(guide: Mapping[str, Any]) -> list[str]:
    rows = []
    for index, item in enumerate(_sequence(guide.get("dml_matrix")), start=1):
        if not isinstance(item, Mapping):
            continue
        operation = str(item.get("operation") or "REVIEW_REQUIRED").upper()
        target = str(item.get("target_ref") or "REVIEW_REQUIRED")
        refs = _sequence(item.get("evidence_refs")) or ["static.analysis.migration_guide"]
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
    return f"/* REVIEW_REQUIRED {operation} statement evidence for {target} */"
