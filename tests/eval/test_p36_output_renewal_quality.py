from __future__ import annotations

from ai_agent_domain import ArtifactType, RequestedOutputType
from ai_agent_generation import (
    GenerationContext,
    JavaMyBatisSpWrapperRenderer,
    render_artifact,
)


def _p36_context() -> GenerationContext:
    return GenerationContext.from_mapping(
        {
            "sampleId": "p36-output-renewal-eval",
            "request": {
                "systemCode": "PEM",
                "businessCodeLv1": "bond",
                "businessCodeLv2": "request",
                "entityName": "BondRequest",
                "resourceName": "bond-request",
                "description": "보증 요청 조회",
                "generationMode": "spRebuild",
                "tableName": "PPM.dbo.BOND_REQ",
                "spName": "PPM.dbo.USP_BOND_REQUEST_LIST",
                "columns": [
                    {"name": "BOND_REQ_ID", "dbType": "bigint", "description": "request id"},
                    {"name": "STATUS_CD", "dbType": "varchar(20)", "description": "status"},
                ],
                "inputParams": [
                    {"name": "BOND_KIND_CD", "dbType": "varchar(10)", "required": False},
                    {"name": "FROM_DT", "dbType": "datetime2", "required": False},
                ],
                "resultShape": ["BOND_REQ_ID", "STATUS_CD"],
                "authorId": "AI",
                "migrationGuide": {
                    "target_ref": "PPM.dbo.USP_BOND_REQUEST_LIST",
                    "db_context": {
                        "metadata_profile_id": "ppm_ro",
                        "target_db": "PPM",
                        "platform_db": "PLF",
                    },
                    "evidence_refs": [
                        {
                            "id": "ev_metadata_1",
                            "type": "MSSQL_METADATA",
                            "object_ref": "PPM.dbo.USP_BOND_REQUEST_LIST",
                            "locator": "metadata.procedure",
                        },
                        {
                            "id": "static.analysis.migration_guide",
                            "type": "STATIC_ANALYSIS",
                            "object_ref": "PPM.dbo.USP_BOND_REQUEST_LIST",
                            "locator": "analysis.dml",
                        },
                    ],
                    "overview_rows": [
                        {
                            "label": "대상 SP",
                            "value": "PPM.dbo.USP_BOND_REQUEST_LIST",
                            "status": "Confirmed",
                            "evidence_refs": ["ev_metadata_1"],
                        }
                    ],
                    "feature_branch_rows": [
                        {
                            "feature": "보증유형 분기",
                            "condition": "@BOND_KIND_CD",
                            "summary": "보증유형별 조회 조건 후보",
                            "status": "REVIEW_REQUIRED",
                            "evidence_refs": ["static.analysis.migration_guide"],
                        }
                    ],
                    "dependency_inventory": [
                        {
                            "object_kind": "table",
                            "object_ref": "PPM.dbo.BOND_REQ",
                            "operations": ["SELECT", "UPDATE"],
                            "how_referenced": "static parser",
                            "status": "Confirmed",
                            "evidence_refs": ["static.analysis.migration_guide"],
                            "what_to_extract_next": "",
                        }
                    ],
                    "dml_matrix": [
                        {
                            "operation": "SELECT",
                            "target_ref": "PPM.dbo.BOND_REQ",
                            "phase": "search",
                            "impact": "조회 결과 후보",
                            "keys_join_where_summary": "REVIEW_REQUIRED",
                            "status": "Confirmed",
                            "evidence_refs": ["stmt.select.1"],
                        },
                        {
                            "operation": "UPDATE",
                            "target_ref": "PPM.dbo.BOND_REQ",
                            "phase": "status_update",
                            "impact": "상태 갱신 후보",
                            "keys_join_where_summary": "REVIEW_REQUIRED",
                            "status": "Confirmed",
                            "evidence_refs": ["stmt.update.1"],
                        },
                    ],
                    "call_flow": ["START", "  -> SELECT PPM.dbo.BOND_REQ", "  -> UPDATE status branch"],
                    "critical_phase_rows": [
                        {
                            "phase": "search",
                            "condition": "@BOND_KIND_CD",
                            "summary": "분기 조회",
                            "risk": "REVIEW_REQUIRED",
                            "evidence_refs": ["stmt.select.1"],
                        }
                    ],
                    "phase_risk_metrics": {
                        "branch_count": 2,
                        "dml_operation_count": 2,
                        "complexity_score": 42,
                        "complexity_metrics": {"select_count": 1, "update_count": 1},
                    },
                },
            },
            "evidence": {
                "sources": [
                    {
                        "type": "storedProcedure",
                        "name": "PPM.dbo.USP_BOND_REQUEST_LIST",
                        "reason": "metadata fixture",
                        "locator": "metadata.procedure",
                    }
                ],
                "assumptions": ["REVIEW_REQUIRED: fixture uses bounded statement evidence"],
            },
        }
    )


def test_sp_analysis_doc_follows_p36_migration_guide_flow() -> None:
    artifact = render_artifact(ArtifactType.SP_ANALYSIS_DOC, _p36_context())

    assert artifact.artifact_type == ArtifactType.SP_ANALYSIS_DOC
    for heading in [
        "## 1. SP 개요 (Overview)",
        "## 2. 의존성 인벤토리 (Dependency Inventory)",
        "## 3. DML 영향도 매트릭스 (Data Change Impact Matrix)",
        "## 4. 호출 흐름 (Call Flow)",
        "## 5. SP 복잡도 분석 (Complexity Analysis)",
        "## 6. Appendix",
    ]:
        assert heading in artifact.content
    assert "PPM.dbo.USP_BOND_REQUEST_LIST" in artifact.content
    assert "Evidence Map" not in artifact.content
    assert "evidenceRefs=" not in artifact.content
    assert "static.dml." not in artifact.content


def test_dependency_report_is_evidence_dossier() -> None:
    artifact = render_artifact(ArtifactType.DEPENDENCY_REPORT, _p36_context())

    assert artifact.artifact_type == ArtifactType.DEPENDENCY_REPORT
    for section in [
        "## generation_evidence_summary",
        "## sp_analysis_evidence",
        "## java_mybatis_evidence",
        "## sql_statement_evidence",
        "## next_evidence_to_collect",
    ]:
        assert section in artifact.content
    assert "SELECT /* REVIEW_REQUIRED columns */ FROM PPM.dbo.BOND_REQ" in artifact.content
    assert "UPDATE PPM.dbo.BOND_REQ SET /* REVIEW_REQUIRED assignments */" in artifact.content


def test_java_mybatis_draft_uses_business_logic_reconstruction_mode() -> None:
    context = _p36_context()
    bundle = JavaMyBatisSpWrapperRenderer().render_bundle(context)

    assert bundle.requested_output_type == RequestedOutputType.JAVA_MYBATIS_DRAFT.value
    assert bundle.artifact_types == (
        ArtifactType.DTO_DRAFT.value,
        ArtifactType.SERVICE_DRAFT.value,
        ArtifactType.MAPPER_INTERFACE.value,
        ArtifactType.MAPPER_XML.value,
    )
    dto = next(file.content for file in bundle.files if file.artifact_type == ArtifactType.DTO_DRAFT)
    service = next(
        file.content for file in bundle.files if file.artifact_type == ArtifactType.SERVICE_DRAFT
    )
    mapper_xml = next(
        file.content for file in bundle.files if file.artifact_type == ArtifactType.MAPPER_XML
    )

    assert "INPUT_PARAM" in dto
    assert "RESULT_FIELD" in dto
    assert "public class BondRequestService" in service
    assert "UPDATE draft for `PPM.dbo.BOND_REQ`" in service
    assert "<update" in mapper_xml
    assert "UPDATE PPM.dbo.BOND_REQ SET /* REVIEW_REQUIRED assignments */" in mapper_xml
