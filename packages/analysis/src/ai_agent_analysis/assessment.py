from __future__ import annotations

from typing import Any

from ai_agent_analysis.models import (
    BusinessRuleSummary,
    CallGraphEdge,
    CanonicalConversionBlocker,
    ConfidenceScore,
    DependencyOperation,
    DependencySummary,
    EvidenceAssessment,
    EvidenceRef,
    EvidenceStatus,
    ModernizationPoint,
    PatternSummary,
    ProcedureSignature,
    ResultSetHint,
    ReviewMarker,
    TodoItem,
)


def build_call_graph(
    procedure: ProcedureSignature,
    dependencies: DependencySummary,
) -> list[CallGraphEdge]:
    caller = procedure.identifier.full_name
    return [
        CallGraphEdge(
            caller=caller,
            callee=call.full_name,
            status=call.status,
            evidence=call.evidence,
            review_notes=call.review_notes,
        )
        for call in dependencies.called_procedures
    ]


def summarize_business_rules(
    dependencies: DependencySummary,
    patterns: PatternSummary,
    result_sets: list[ResultSetHint],
) -> list[BusinessRuleSummary]:
    summaries: list[BusinessRuleSummary] = []
    for reference in [
        *dependencies.table_references,
        *dependencies.view_references,
        *dependencies.function_references,
    ]:
        verb = _operation_verb(reference.operation)
        summaries.append(
            BusinessRuleSummary(
                category="DEPENDENCY",
                summary=f"{reference.full_name}({reference.object_type.value}) 객체를 {verb}.",
                status=reference.status,
                evidence=reference.evidence,
                inferred_from=["static dependency token"],
            )
        )
    for call in dependencies.called_procedures:
        summaries.append(
            BusinessRuleSummary(
                category="CALL_GRAPH",
                summary=f"중첩 procedure {call.full_name} 호출을 확인했습니다.",
                status=call.status,
                evidence=call.evidence,
                inferred_from=["EXEC statement"],
            )
        )
    for finding, summary in (
        (patterns.transaction, "명시적 트랜잭션 제어를 사용합니다."),
        (patterns.try_catch, "TRY/CATCH 예외 처리를 사용합니다."),
        (patterns.temp_table, "임시 테이블 staging을 사용합니다."),
        (patterns.cursor, "cursor 기반 반복 처리를 사용합니다."),
        (patterns.dynamic_sql, "Dynamic SQL을 생성하거나 실행합니다."),
        (patterns.multi_result_set, "여러 result set을 반환할 수 있습니다."),
    ):
        if finding.detected:
            summaries.append(
                BusinessRuleSummary(
                    category="PATTERN",
                    summary=summary,
                    status=finding.status,
                    evidence=finding.evidence,
                    inferred_from=[finding.name],
                )
            )
    for result_set in result_sets:
        column_names = [column.name for column in result_set.columns if column.name]
        column_summary = ", ".join(column_names) if column_names else "근거 보강 필요한 컬럼"
        summaries.append(
            BusinessRuleSummary(
                category="RESULT_SET",
                summary=f"result set {result_set.ordinal} 반환 후보: {column_summary}.",
                status=result_set.status
                if result_set.status == EvidenceStatus.REVIEW_REQUIRED
                else EvidenceStatus.INFERRED_DESCRIPTION,
                evidence=result_set.evidence,
                inferred_from=["static SELECT list"],
            )
        )
    return summaries


def summarize_modernization_points(
    dependencies: DependencySummary,
    patterns: PatternSummary,
) -> list[ModernizationPoint]:
    points: list[ModernizationPoint] = []
    if patterns.dynamic_sql.detected:
        points.append(
            ModernizationPoint(
                code="DYNAMIC_SQL_MODERNIZATION_REVIEW",
                summary="Dynamic SQL 전환 전략은 근거 보강이 필요합니다.",
                status=EvidenceStatus.REVIEW_REQUIRED,
                evidence=patterns.dynamic_sql.evidence,
                inferred_from=["dynamic_sql"],
            )
        )
    if patterns.cursor.detected:
        points.append(
            ModernizationPoint(
                code="CURSOR_MODERNIZATION_REVIEW",
                summary="Java/MyBatis 초안 적용 전에 cursor 기반 반복 처리를 검토해야 합니다.",
                status=EvidenceStatus.REVIEW_REQUIRED,
                evidence=patterns.cursor.evidence,
                inferred_from=["cursor"],
            )
        )
    if dependencies.temp_tables:
        evidence = [
            evidence
            for temp_table in dependencies.temp_tables
            for evidence in temp_table.evidence
        ]
        points.append(
            ModernizationPoint(
                code="TEMP_TABLE_STAGING_REVIEW",
                summary="동등한 application flow 설계를 위해 임시 테이블 staging을 검토해야 합니다.",
                status=EvidenceStatus.REVIEW_REQUIRED,
                evidence=evidence,
                inferred_from=["temp_table"],
            )
        )
    return points


def build_todos(
    dependencies: DependencySummary,
    patterns: PatternSummary,
    result_sets: list[ResultSetHint],
    blockers: list[CanonicalConversionBlocker],
) -> list[TodoItem]:
    todos: list[TodoItem] = []
    if patterns.dynamic_sql.detected:
        todos.append(
            TodoItem(
                code="DYNAMIC_SQL_DEPENDENCY_REVIEW",
                message="Dynamic SQL 내부에서 생성되는 의존성과 result set을 검토합니다.",
                evidence=patterns.dynamic_sql.evidence,
            )
        )
    if patterns.multi_result_set.detected:
        todos.append(
            TodoItem(
                code="MULTI_RESULT_SET_REVIEW",
                message="여러 result set에 대한 client 기대 동작을 확인합니다.",
                evidence=patterns.multi_result_set.evidence,
            )
        )
    for reference in dependencies.view_references:
        todos.append(
            TodoItem(
                code="VIEW_DEPENDENCY_TYPE_REVIEW",
                message=f"{reference.full_name} 객체 유형을 메타데이터 근거로 확인합니다.",
                evidence=reference.evidence,
            )
        )
    for result_set in result_sets:
        if result_set.status == EvidenceStatus.REVIEW_REQUIRED:
            todos.append(
                TodoItem(
                    code="RESULT_SET_COLUMN_REVIEW",
                    message=f"result set {result_set.ordinal} 컬럼을 검토합니다.",
                    evidence=result_set.evidence,
                )
            )
    for blocker in blockers:
        todos.append(
            TodoItem(
                code=blocker.code,
                message=blocker.message,
                status=blocker.status,
            )
        )
    return _dedupe_todos(todos)


def calculate_overall_confidence(
    dependencies: DependencySummary,
    patterns: PatternSummary,
    result_sets: list[ResultSetHint],
    review_markers: list[ReviewMarker],
    todos: list[TodoItem],
    blockers: list[CanonicalConversionBlocker],
) -> ConfidenceScore:
    score = 0.95
    factors = ["procedure signature와 static SQL token을 결정론적으로 파싱했습니다."]
    if patterns.dynamic_sql.detected:
        score -= 0.25
        factors.append("dynamic SQL 의존성은 근거 보강이 필요합니다.")
    if patterns.multi_result_set.detected:
        score -= 0.05
        factors.append("여러 result set은 consumer 검토가 필요합니다.")
    if dependencies.view_references:
        score -= 0.05
        factors.append("view/table 분류는 메타데이터 근거가 제한적입니다.")
    review_required_dependencies = [
        *[
            call.full_name
            for call in dependencies.called_procedures
            if call.status == EvidenceStatus.REVIEW_REQUIRED
        ],
        *[
            reference.full_name
            for reference in [*dependencies.table_references, *dependencies.view_references]
            if reference.status == EvidenceStatus.REVIEW_REQUIRED
        ],
    ]
    if review_required_dependencies:
        score -= 0.10
        factors.append("하나 이상의 의존성 참조가 REVIEW_REQUIRED 상태입니다.")
    if any(result_set.status == EvidenceStatus.REVIEW_REQUIRED for result_set in result_sets):
        score -= 0.10
        factors.append("하나 이상의 result-set hint가 REVIEW_REQUIRED 상태입니다.")
    if review_markers:
        score -= min(0.20, 0.05 * len(review_markers))
        factors.append("분석 결과에 근거 caveat가 포함되어 있습니다.")
    if blockers:
        score -= 0.05
        factors.append("canonical conversion binding이 아직 차단되어 있습니다.")
    if todos:
        score -= min(0.15, 0.03 * len(todos))
        factors.append("수동 확인 TODO가 남아 있습니다.")
    score = max(0.05, round(score, 2))
    status = (
        EvidenceStatus.REVIEW_REQUIRED
        if todos or review_markers or blockers
        else EvidenceStatus.OBSERVED
    )
    return ConfidenceScore(
        score=score,
        status=status,
        rationale="confidence는 결정론적으로 산출되며 REVIEW_REQUIRED 근거가 있으면 낮아집니다.",
        factors=factors,
    )


def assess_evidence(
    payloads: list[Any],
    todos: list[TodoItem],
) -> EvidenceAssessment:
    evidence_refs = list(_iter_evidence_refs(payloads))
    review_required_count = sum(
        1 for evidence in evidence_refs if evidence.status == EvidenceStatus.REVIEW_REQUIRED
    )
    review_required = bool(review_required_count or todos)
    notes: list[str] = []
    if review_required_count:
        notes.append("일부 evidence ref가 REVIEW_REQUIRED로 표시되어 있습니다.")
    if todos:
        notes.append("수동 TODO가 validation caveat로 남아 있습니다.")
    return EvidenceAssessment(
        status=EvidenceStatus.REVIEW_REQUIRED if review_required else EvidenceStatus.OBSERVED,
        review_required=review_required,
        evidence_ref_count=len(evidence_refs),
        observed_ref_count=sum(
            1 for evidence in evidence_refs if evidence.status == EvidenceStatus.OBSERVED
        ),
        review_required_ref_count=review_required_count,
        todo_count=len(todos),
        notes=notes,
    )


def _operation_verb(operation: DependencyOperation) -> str:
    return {
        DependencyOperation.READ: "읽습니다",
        DependencyOperation.WRITE: "수정합니다",
        DependencyOperation.EXECUTE: "실행합니다",
        DependencyOperation.DECLARE: "선언합니다",
        DependencyOperation.UNKNOWN: "참조합니다",
    }[operation]


def _dedupe_todos(todos: list[TodoItem]) -> list[TodoItem]:
    deduped: list[TodoItem] = []
    seen: set[tuple[str, str]] = set()
    for todo in todos:
        key = (todo.code, todo.message)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(todo)
    return deduped


def _iter_evidence_refs(payload: Any) -> list[EvidenceRef]:
    refs: list[EvidenceRef] = []
    if isinstance(payload, EvidenceRef):
        refs.append(payload)
    elif isinstance(payload, list | tuple):
        for item in payload:
            refs.extend(_iter_evidence_refs(item))
    elif hasattr(payload, "model_dump"):
        refs.extend(_iter_evidence_refs(payload.model_dump()))
    elif isinstance(payload, dict):
        if {"source", "snippet", "status"}.issubset(payload):
            refs.append(
                EvidenceRef(
                    source=str(payload["source"]),
                    line=payload.get("line"),
                    snippet=str(payload["snippet"]),
                    status=EvidenceStatus(payload["status"]),
                )
            )
            return refs
        for value in payload.values():
            refs.extend(_iter_evidence_refs(value))
    return refs
