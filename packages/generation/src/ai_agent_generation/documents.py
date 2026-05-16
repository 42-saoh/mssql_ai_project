from __future__ import annotations

from ai_agent_domain import ArtifactType

from ai_agent_generation.migration_guide import (
    render_p24_dependency_report_sections,
    render_p24_migration_guide_sections,
)
from ai_agent_generation.models import GenerationContext, RenderedArtifact
from ai_agent_generation.utils import draft_quality_text, ensure_trailing_newline


class SPAnalysisDocumentRenderer:
    artifact_type = ArtifactType.SP_ANALYSIS_DOC

    def render(self, context: GenerationContext) -> RenderedArtifact:
        llm_analysis = _llm_analysis(context)
        lines = [
            f"# {context.entity_name} SP 분석 초안",
            "",
            "## input_interpretation",
            f"- systemCode: {context.system_code}",
            f"- entityName: {context.entity_name}",
            f"- spName: {context.sp_name}",
            f"- tableName: {context.table_name}",
            "",
            "## analysis_summary",
            "- 상태: 초안(`DRAFT`)",
            (
                "- REVIEW_REQUIRED: SP 내부 제어 흐름과 비즈니스 규칙은 "
                "canonical analysis 확정 후 보강"
            ),
            f"- generationMode: {context.generation_mode}",
            "",
            "## procedure_signature",
            *[
                f"- `{param.name}` {param.db_type} required={str(param.required).lower()}"
                for param in context.input_params
            ],
            "",
            "## result_shape",
            *[f"- `{column}`" for column in context.result_shape],
            "",
            "## dependency_summary",
            f"- 저장 프로시저: `{context.sp_name}`",
            f"- 테이블: `{context.table_name}`",
            "",
            *render_p24_migration_guide_sections(context),
            "## llm_semantic_analysis",
            *_llm_semantic_lines(llm_analysis),
            "",
            "## evidence_summary",
            *[
                f"- {source.display_type}: `{source.name}` - {source.reason}"
                for source in context.evidence_sources
            ],
            "",
            "## assumptions_and_todo",
            *[f"- TODO: {assumption}" for assumption in context.evidence_assumptions],
            "- TODO: transaction boundary 확인",
            "- TODO: dynamic SQL/temp table 여부는 analysis engine 결과로 확정",
            "",
            "## quality_summary",
            "- evidence_included: true",
            "- draft_only_boundary_marked: true",
            "- business rules are draft caveats when not evidence-linked",
            "",
            "## evidence_map",
            *[
                f"- {source.display_type}: `{source.name}` - {source.reason}"
                for source in context.evidence_sources
            ],
            "",
            "## known_caveats",
            "- REVIEW_REQUIRED items mean evidence needs to be strengthened.",
            "",
            "## next_evidence_to_collect",
            "- Confirm transaction boundary, branch conditions, DML targets, and call-flow depth.",
            "",
            "## draft_readiness",
            "- Ready as a draft analysis input; no execution or apply path is included.",
        ]
        return RenderedArtifact(
            artifact_type=self.artifact_type,
            title=f"{context.entity_name} SP 분석 초안",
            content=ensure_trailing_newline(draft_quality_text("\n".join(lines))),
            evidence_refs=context.evidence_refs,
            registry_refs=("template:sp_analysis_doc@0.1.0",),
            assumptions=context.evidence_assumptions,
            review_required=True,
        )


class DependencyReportRenderer:
    artifact_type = ArtifactType.DEPENDENCY_REPORT

    def render(self, context: GenerationContext) -> RenderedArtifact:
        llm_analysis = _llm_analysis(context)
        dependency_evidence = _dependency_evidence(context)
        lines = [
            f"# {context.entity_name} 의존성 보고서 초안",
            "",
            "## dependency_summary",
            "- 상태: 초안(`DRAFT`)",
            "- REVIEW_REQUIRED: 호출 그래프는 canonical dependency resolver 결과로 확정",
            f"- rootProcedure: `{context.sp_name}`",
            *_dependency_summary_lines(dependency_evidence),
            "",
            "## dependency_table",
            "| 유형 | 객체 | 근거 |",
            "|---|---|---|",
        ]
        for source in context.evidence_sources:
            lines.append(f"| {source.display_type} | `{source.name}` | {source.reason} |")
        lines.extend(
            [
                "",
                "## dependency_closure_evidence",
                *_dependency_closure_lines(dependency_evidence),
                "",
                *render_p24_dependency_report_sections(context),
                "## evidence_summary",
                *[
                    f"- {source.display_type}: `{source.name}`"
                    for source in context.evidence_sources
                ],
                "",
                "## llm_risk_flags",
                *_llm_risk_lines(llm_analysis),
                "",
                "## assumptions_and_todo",
                "- TODO: nested procedure/function/view dependencies 확인",
                "- TODO: read/write dependency direction 확정",
                "",
                "## quality_summary",
                "- evidence_included: true",
                "- draft_only_boundary_marked: true",
                "- dependency direction remains a caveat when resolver evidence is incomplete",
                "",
                "## evidence_map",
                *[
                    f"- {source.display_type}: `{source.name}`"
                    for source in context.evidence_sources
                ],
                "",
                "## known_caveats",
                "- REVIEW_REQUIRED items mean evidence needs to be strengthened.",
                "",
                "## next_evidence_to_collect",
                "- Confirm nested procedure/function/view dependencies and read/write direction.",
                "",
                "## draft_readiness",
                "- Ready as a draft dependency input; no execution or apply path is included.",
            ]
        )
        return RenderedArtifact(
            artifact_type=self.artifact_type,
            title=f"{context.entity_name} 의존성 보고서 초안",
            content=ensure_trailing_newline(draft_quality_text("\n".join(lines))),
            evidence_refs=context.evidence_refs,
            registry_refs=("template:dependency_report@0.1.0",),
            assumptions=context.evidence_assumptions,
            review_required=True,
        )


def _llm_analysis(context: GenerationContext) -> dict:
    payload = context.value("llmAnalysis", {}) or {}
    return dict(payload) if isinstance(payload, dict) else {}


def _dependency_evidence(context: GenerationContext) -> dict:
    payload = context.value("dependencyEvidence", {}) or {}
    return dict(payload) if isinstance(payload, dict) else {}


def _dependency_summary_lines(payload: dict) -> list[str]:
    summary = payload.get("summary")
    if not isinstance(summary, dict):
        return ["- dependencyClosure: 근거 없음(`NOT_AVAILABLE`)"]
    return [
        f"- dependencyClosureTool: `{payload.get('toolName', 'get_dependency_closure')}`",
        f"- dependencySnapshot: `{payload.get('snapshotId') or 'REVIEW_REQUIRED'}`",
        f"- closureNodes: {summary.get('nodeCount', 0)}",
        f"- closureEdges: {summary.get('edgeCount', 0)}",
        f"- unresolvedReviewRequired: {summary.get('reviewRequiredCount', 0)}",
    ]


def _dependency_closure_lines(payload: dict) -> list[str]:
    if not payload:
        return ["- REVIEW_REQUIRED: 의존성 closure 근거를 사용할 수 없습니다."]
    lines = [
        "| 상태 | 객체 | 유형 | 확인 전략 |",
        "|---|---|---|---|",
    ]
    for edge in _dict_items(payload.get("edges")):
        lines.append(
            "| "
            f"{edge.get('resolutionStatus', 'REVIEW_REQUIRED')} | "
            f"`{_table_text(edge.get('to', 'unknown'))}` | "
            f"{_table_text(edge.get('dependencyType', 'REFERENCE'))} | "
            f"{_table_text(edge.get('resolutionStrategy', 'UNRESOLVED'))} |"
        )
    for item in _dict_items(payload.get("unresolved")):
        object_ref = ".".join(
            str(part)
            for part in (item.get("schema"), item.get("name"))
            if part
        )
        lines.append(
            "| "
            f"{item.get('resolutionStatus', 'REVIEW_REQUIRED')} | "
            f"`{_table_text(object_ref or 'unresolved')}` | "
            f"{_table_text(item.get('dependencyType', 'REFERENCE'))} | "
            f"{_table_text(item.get('resolutionStrategy', 'UNRESOLVED'))} |"
        )
    if len(lines) == 2:
        lines.append("| CONFIRMED | `no dependencies returned` | 없음 | 없음 |")
    return lines


def _dict_items(value: object) -> list[dict]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _table_text(value: object) -> str:
    return str(value).replace("|", "/")


def _llm_semantic_lines(payload: dict) -> list[str]:
    if not payload:
        return ["- 상태: 요청하지 않음(`NOT_REQUESTED`)"]
    lines = ["- 상태: 근거 보강 필요(`REVIEW_REQUIRED`)"]
    for rule in payload.get("businessRules", []) or []:
        lines.append(f"- 비즈니스 규칙({rule.get('category')}): {rule.get('summary')}")
    for point in payload.get("modernizationPoints", []) or []:
        lines.append(f"- 현대화 포인트({point.get('code')}): {point.get('summary')}")
    for guidance in payload.get("conversionGuidance", []) or []:
        lines.append(f"- 전환 가이드({guidance.get('code')}): {guidance.get('summary')}")
    for insight in payload.get("migrationGuideInsights", []) or []:
        suffix = (
            f" 다음 추출 항목={insight.get('whatToExtractNext')}"
            if insight.get("whatToExtractNext")
            else ""
        )
        lines.append(
            f"- 가이드 인사이트({insight.get('section')}): {insight.get('summary')}{suffix}"
        )
    for marker in payload.get("reviewMarkers", []) or []:
        lines.append(f"- 근거 caveat({marker.get('code')}): {marker.get('message')}")
    return lines


def _llm_risk_lines(payload: dict) -> list[str]:
    if not payload:
        return ["- 상태: 요청하지 않음(`NOT_REQUESTED`)"]
    risk_flags = payload.get("riskFlags", []) or []
    if not risk_flags:
        return ["- 상태: 반환된 위험 플래그 없음(`NO_RISK_FLAGS_RETURNED`)"]
    return [
        f"- {item.get('severity')} `{item.get('code')}`: {item.get('summary')}"
        for item in risk_flags
    ]
