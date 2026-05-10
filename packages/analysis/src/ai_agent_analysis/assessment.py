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
                summary=f"{verb} {reference.full_name} ({reference.object_type.value}).",
                status=reference.status,
                evidence=reference.evidence,
                inferred_from=["static dependency token"],
            )
        )
    for call in dependencies.called_procedures:
        summaries.append(
            BusinessRuleSummary(
                category="CALL_GRAPH",
                summary=f"Executes nested procedure {call.full_name}.",
                status=call.status,
                evidence=call.evidence,
                inferred_from=["EXEC statement"],
            )
        )
    for finding, summary in (
        (patterns.transaction, "Uses explicit transaction control."),
        (patterns.try_catch, "Uses TRY/CATCH exception handling."),
        (patterns.temp_table, "Uses temporary table staging."),
        (patterns.cursor, "Uses cursor-based iteration."),
        (patterns.dynamic_sql, "Builds or executes dynamic SQL."),
        (patterns.multi_result_set, "May return multiple result sets."),
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
        column_summary = ", ".join(column_names) if column_names else "review-required columns"
        summaries.append(
            BusinessRuleSummary(
                category="RESULT_SET",
                summary=f"Returns result set {result_set.ordinal}: {column_summary}.",
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
                summary="Dynamic SQL migration strategy requires manual review.",
                status=EvidenceStatus.REVIEW_REQUIRED,
                evidence=patterns.dynamic_sql.evidence,
                inferred_from=["dynamic_sql"],
            )
        )
    if patterns.cursor.detected:
        points.append(
            ModernizationPoint(
                code="CURSOR_MODERNIZATION_REVIEW",
                summary="Cursor-based iteration should be reviewed before Java/MyBatis draft adoption.",
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
                summary="Temporary table staging should be reviewed for equivalent application flow.",
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
                message="Review dependencies and result sets produced inside dynamic SQL.",
                evidence=patterns.dynamic_sql.evidence,
            )
        )
    if patterns.multi_result_set.detected:
        todos.append(
            TodoItem(
                code="MULTI_RESULT_SET_REVIEW",
                message="Confirm client expectations for multiple result sets.",
                evidence=patterns.multi_result_set.evidence,
            )
        )
    for reference in dependencies.view_references:
        todos.append(
            TodoItem(
                code="VIEW_DEPENDENCY_TYPE_REVIEW",
                message=f"Confirm {reference.full_name} object type with metadata evidence.",
                evidence=reference.evidence,
            )
        )
    for result_set in result_sets:
        if result_set.status == EvidenceStatus.REVIEW_REQUIRED:
            todos.append(
                TodoItem(
                    code="RESULT_SET_COLUMN_REVIEW",
                    message=f"Review result set {result_set.ordinal} columns.",
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
    factors = ["procedure signature and static SQL tokens parsed deterministically"]
    if patterns.dynamic_sql.detected:
        score -= 0.25
        factors.append("dynamic SQL requires manual dependency review")
    if patterns.multi_result_set.detected:
        score -= 0.05
        factors.append("multiple result sets require consumer review")
    if dependencies.view_references:
        score -= 0.05
        factors.append("view/table classification is metadata-limited")
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
        factors.append("one or more dependency references are review-required")
    if any(result_set.status == EvidenceStatus.REVIEW_REQUIRED for result_set in result_sets):
        score -= 0.10
        factors.append("one or more result-set hints are review-required")
    if review_markers:
        score -= min(0.20, 0.05 * len(review_markers))
        factors.append("analysis emitted review markers")
    if blockers:
        score -= 0.05
        factors.append("canonical conversion bindings remain blocked")
    if todos:
        score -= min(0.15, 0.03 * len(todos))
        factors.append("manual TODOs remain")
    score = max(0.05, round(score, 2))
    status = (
        EvidenceStatus.REVIEW_REQUIRED
        if todos or review_markers or blockers
        else EvidenceStatus.OBSERVED
    )
    return ConfidenceScore(
        score=score,
        status=status,
        rationale="Confidence is deterministic and decreases for review-required evidence.",
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
        notes.append("Some evidence refs are marked REVIEW_REQUIRED.")
    if todos:
        notes.append("Manual TODOs remain before approval.")
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
        DependencyOperation.READ: "Reads from",
        DependencyOperation.WRITE: "Writes to",
        DependencyOperation.EXECUTE: "Executes",
        DependencyOperation.DECLARE: "Declares",
        DependencyOperation.UNKNOWN: "References",
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
