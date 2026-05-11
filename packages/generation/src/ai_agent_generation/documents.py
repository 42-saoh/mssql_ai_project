from __future__ import annotations

from ai_agent_domain import ArtifactType

from ai_agent_generation.migration_guide import (
    render_p24_dependency_report_sections,
    render_p24_migration_guide_sections,
)
from ai_agent_generation.models import GenerationContext, RenderedArtifact
from ai_agent_generation.utils import ensure_trailing_newline


class SPAnalysisDocumentRenderer:
    artifact_type = ArtifactType.SP_ANALYSIS_DOC

    def render(self, context: GenerationContext) -> RenderedArtifact:
        llm_analysis = _llm_analysis(context)
        lines = [
            f"# {context.entity_name} SP Analysis Draft",
            "",
            "## input_interpretation",
            f"- systemCode: {context.system_code}",
            f"- entityName: {context.entity_name}",
            f"- spName: {context.sp_name}",
            f"- tableName: {context.table_name}",
            "",
            "## analysis_summary",
            "- status: DRAFT",
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
            f"- Stored Procedure: `{context.sp_name}`",
            f"- Table: `{context.table_name}`",
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
            "## review_checklist",
            "- [x] evidence_included",
            "- [x] draft_only_boundary_marked",
            "- [ ] reviewer_confirms_business_rules",
        ]
        return RenderedArtifact(
            artifact_type=self.artifact_type,
            title=f"{context.entity_name} SP Analysis Draft",
            content=ensure_trailing_newline("\n".join(lines)),
            evidence_refs=context.evidence_refs,
            registry_refs=("template:sp_analysis_doc@0.1.0",),
            assumptions=context.evidence_assumptions,
            review_required=True,
        )


class DependencyReportRenderer:
    artifact_type = ArtifactType.DEPENDENCY_REPORT

    def render(self, context: GenerationContext) -> RenderedArtifact:
        llm_analysis = _llm_analysis(context)
        lines = [
            f"# {context.entity_name} Dependency Report Draft",
            "",
            "## dependency_summary",
            "- status: DRAFT",
            "- REVIEW_REQUIRED: 호출 그래프는 canonical dependency resolver 결과로 확정",
            f"- rootProcedure: `{context.sp_name}`",
            "",
            "## dependency_table",
            "| kind | object | evidence |",
            "|---|---|---|",
        ]
        for source in context.evidence_sources:
            lines.append(f"| {source.display_type} | `{source.name}` | {source.reason} |")
        lines.extend(
            [
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
                "## review_checklist",
                "- [x] evidence_included",
                "- [x] draft_only_boundary_marked",
                "- [ ] reviewer_confirms_dependency_direction",
            ]
        )
        return RenderedArtifact(
            artifact_type=self.artifact_type,
            title=f"{context.entity_name} Dependency Report Draft",
            content=ensure_trailing_newline("\n".join(lines)),
            evidence_refs=context.evidence_refs,
            registry_refs=("template:dependency_report@0.1.0",),
            assumptions=context.evidence_assumptions,
            review_required=True,
        )


def _llm_analysis(context: GenerationContext) -> dict:
    payload = context.value("llmAnalysis", {}) or {}
    return dict(payload) if isinstance(payload, dict) else {}


def _llm_semantic_lines(payload: dict) -> list[str]:
    if not payload:
        return ["- status: NOT_REQUESTED"]
    lines = ["- status: REVIEW_REQUIRED"]
    for rule in payload.get("businessRules", []) or []:
        lines.append(f"- Business rule ({rule.get('category')}): {rule.get('summary')}")
    for point in payload.get("modernizationPoints", []) or []:
        lines.append(f"- Modernization ({point.get('code')}): {point.get('summary')}")
    for guidance in payload.get("conversionGuidance", []) or []:
        lines.append(f"- Conversion guidance ({guidance.get('code')}): {guidance.get('summary')}")
    for insight in payload.get("migrationGuideInsights", []) or []:
        lines.append(f"- Guide insight ({insight.get('section')}): {insight.get('summary')}")
    for marker in payload.get("reviewMarkers", []) or []:
        lines.append(f"- Review marker ({marker.get('code')}): {marker.get('message')}")
    return lines


def _llm_risk_lines(payload: dict) -> list[str]:
    if not payload:
        return ["- status: NOT_REQUESTED"]
    risk_flags = payload.get("riskFlags", []) or []
    if not risk_flags:
        return ["- status: NO_RISK_FLAGS_RETURNED"]
    return [
        f"- {item.get('severity')} `{item.get('code')}`: {item.get('summary')}"
        for item in risk_flags
    ]
