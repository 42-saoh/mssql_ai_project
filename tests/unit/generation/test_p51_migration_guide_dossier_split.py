from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from ai_agent_analysis.guide_metrics import migration_guide_static_metrics
from ai_agent_domain import ArtifactType
from ai_agent_generation import GenerationContext, build_migration_guide_payload, render_artifact

from tests.helpers.p42_manage_bond import SANITIZED_MANAGE_BOND_SQL


FORBIDDEN_GUIDE_MARKERS = (
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

EXPECTED_GUIDE_HEADINGS = [
    "# Migration Guide: PPM.dbo.PCO_GU_ManageBond_PRC",
    "## 1. SP 개요 (Overview)",
    "### 1.1 기본 정보",
    "### 1.2 주요 기능",
    "### 1.3 지원 서브시스템",
    "### 1.4 주요 업무 코드 / 보증유형코드",
    "## 2. 의존성 인벤토리 (Dependency Inventory)",
    "### 2.1 테이블 의존성",
    "#### 2.1.1 Confirmed - PPM Database",
    "#### 2.1.2 Confirmed - Cross-DB References (ERP)",
    "#### 2.1.3 Confirmed - Cross-DB References (HRM)",
    "#### 2.1.4 Confirmed - Cross-DB References (TCM)",
    "### 2.2 UDF 의존성",
    "### 2.3 Stored Procedure 의존성",
    "### 2.4 동적 SQL 분석",
    "## 3. DML 영향도 매트릭스 (Data Change Impact Matrix)",
    "### 3.1 PPM Database",
    "### 3.2 ERP Database",
    "### 3.3 HRM Database",
    "### 3.4 TCM Database",
    "## 4. 호출 흐름 (Call Flow)",
    "### 4.1 전체 구조",
    "### 4.2 세부 Phase 분석",
    "## 5. SP 복잡도 분석 (Complexity Analysis)",
    "### 5.1 정량 메트릭",
    "### 5.2 Cross-DB 트랜잭션 리스크",
    "## 6. Appendix",
    "### 6.1 입력 파라미터 전체 목록",
    "### 6.2 상태코드 매핑",
    "### 6.3 확인 필요 항목",
]

REQUIRED_DOSSIER_SECTIONS = (
    "## generation_evidence_summary",
    "## sp_analysis_evidence",
    "## java_mybatis_evidence",
    "## sql_statement_evidence",
    "## dependency_closure_evidence",
    "## semantic_inference_evidence",
    "## evidence_map",
    "## known_caveats",
    "## next_evidence_to_collect",
    "## draft_readiness",
)


def test_p51_migration_guide_matches_golden_heading_order_and_stays_human_facing() -> None:
    guide, dossier = _render_pair()

    assert _markdown_headings(guide.content) == EXPECTED_GUIDE_HEADINGS
    for marker in FORBIDDEN_GUIDE_MARKERS:
        assert marker not in guide.content

    for code in ("R", "A", "C", "U", "D", "VENDOR_U", "ONLINE_U"):
        assert f"@CRUDFlag = '{code}'" in guide.content

    assert "[입력]" in guide.content
    assert "├─► @CRUDFlag = 'R'" in guide.content
    assert "└─► @CRUDFlag = 'ONLINE_U'" in guide.content
    assert "| Table | SELECT | INSERT | UPDATE | DELETE | Keys/Join/Where 요약 | 중요 컬럼/값 패턴 |" in guide.content
    assert "| operation | target | phase | impact | evidence |" not in guide.content.lower()
    assert "static_dml_scan" not in guide.content

    assert "static.dml.select.ppm_dbo_pco_guar" not in guide.content
    assert "상세 근거는 Evidence Dossier 참조" in guide.content
    assert "## evidence_map" in dossier.content


def test_p51_evidence_dossier_preserves_removed_evidence_and_audit_sections() -> None:
    guide, dossier = _render_pair()

    for section in REQUIRED_DOSSIER_SECTIONS:
        assert section in dossier.content
    for marker in (
        "LLM_INFERENCE_EVIDENCE_CAVEAT",
        "evidenceRefs=",
        "reviewMarker:",
        "unsupported_claim",
        "section_expectation",
        "section_claim",
        "static.dml.",
        "sanitized skeleton",
        "agent-runtime.modelInvocation.outputHash",
    ):
        assert marker in dossier.content

    moved_evidence_ids = {
        "static.dml.select.ppm_dbo_pco_guar",
        "static.dml.update.erp_dbo_xxeai_trx_header_ii",
        "static.dml.update.ppm_dbo_pcs_advm_payrpt",
    }
    for evidence_id in moved_evidence_ids:
        assert evidence_id not in guide.content
        assert evidence_id in dossier.content


def _render_pair():
    context = _context()
    return (
        render_artifact(ArtifactType.SP_ANALYSIS_DOC, context),
        render_artifact(ArtifactType.DEPENDENCY_REPORT, context),
    )


def _context() -> GenerationContext:
    static_metrics = migration_guide_static_metrics(
        SANITIZED_MANAGE_BOND_SQL,
        source_name="tests.helpers.p42_manage_bond.SANITIZED_MANAGE_BOND_SQL",
    )
    guide = build_migration_guide_payload(
        target_ref="dbo.PCO_GU_ManageBond_PRC",
        db_profile_id="ppm",
        metadata={
            "evidenceRefs": [
                {
                    "type": "MSSQL_METADATA",
                    "objectRef": "dbo.PCO_GU_ManageBond_PRC",
                    "locator": "mcp.get_procedure_metadata",
                }
            ],
            "tableSchemas": [
                {
                    "schema": "dbo",
                    "tableName": "PCO_GUAR",
                    "description": "Bond guarantee table",
                    "descriptionStatus": "CONFIRMED",
                    "columns": [],
                }
            ],
        },
        static_analysis={
            "migrationGuideStaticMetrics": static_metrics,
            "dependencies": {
                "called_procedures": [
                    {
                        "full_name": "PPM.dbo.PCS_PY_SaveInvoicePrepaidReg_PRC",
                        "status": "OBSERVED",
                    }
                ]
            },
        },
        llm_analysis=_llm_analysis(),
        input_params=_input_params(),
        result_shape=["CTRT_NO", "ORDR_NO", "GUAR_TP_CD", "GUAR_ST_CD"],
        sample_id="p51-manage-bond-split",
    )
    return GenerationContext.from_mapping(
        {
            "sampleId": "p51-manage-bond-split",
            "request": {
                "systemCode": "P51",
                "businessCodeLv1": "migration",
                "businessCodeLv2": "guide",
                "entityName": "ManageBond",
                "resourceName": "manage-bond",
                "description": "보증 관리 전환 가이드",
                "generationMode": "migrationGuide",
                "spName": "dbo.PCO_GU_ManageBond_PRC",
                "inputParams": _input_params(),
                "resultShape": ["CTRT_NO", "ORDR_NO", "GUAR_TP_CD", "GUAR_ST_CD"],
                "migrationGuide": guide,
                "llmAnalysis": _llm_analysis(),
                "llmTrace": {
                    "agentRunId": "p51-split-test",
                    "outputHash": "hash_agent-runtime.modelInvocation.outputHash_fixture",
                },
            },
            "evidence": {
                "sources": [
                    {
                        "type": "storedProcedure",
                        "name": "dbo.PCO_GU_ManageBond_PRC",
                        "reason": "ev_metadata_fixture",
                        "locator": "mcp.get_procedure_metadata",
                    },
                    {
                        "type": "llmInference",
                        "name": "semantic summary",
                        "reason": "agent-runtime.modelInvocation.outputHash",
                        "locator": "agent-runtime.modelInvocation.outputHash",
                    },
                ],
                "assumptions": ["Needs verification: status-code labels require authoritative code table evidence."],
            },
        }
    )


def _input_params() -> list[dict[str, Any]]:
    return [
        {"name": "CRUDFlag", "dbType": "varchar(20)", "required": False},
        {"name": "GUBUNFlag", "dbType": "varchar(1)", "required": False},
        {"name": "ContractNum", "dbType": "varchar(10)", "required": False},
        {"name": "OrdNum", "dbType": "smallint", "required": False},
        {"name": "BondKindCode", "dbType": "varchar(3)", "required": False},
        {"name": "Sequence", "dbType": "smallint", "required": False},
        {"name": "ApprovalYN", "dbType": "varchar(1)", "required": False},
        {"name": "CurrencyInsureAmt", "dbType": "decimal(18,3)", "required": False},
        {"name": "UserID", "dbType": "varchar(50)", "required": False},
        {"name": "SValue", "dbType": "varchar(max)", "required": False},
    ]


def _llm_analysis() -> dict[str, Any]:
    evidence_refs = ["static.dml.update.ppm_dbo_pco_guar"]
    return {
        "businessRules": [
            {
                "category": "NORMALIZED_PROVIDER_BUSINESS_RULE",
                "summary": "보증 승인/수정 규칙은 deterministic branch evidence와 함께 검토한다.",
                "status": "REVIEW_REQUIRED",
                "evidenceRefs": evidence_refs,
            }
        ],
        "riskFlags": [
            {
                "code": "NORMALIZED_PROVIDER_RISK_FLAG",
                "severity": "WARNING",
                "summary": "Cross-DB update requires transaction policy review.",
                "status": "REVIEW_REQUIRED",
                "evidenceRefs": ["static.dml.update.erp_dbo_xxeai_trx_header_ii"],
            }
        ],
        "conversionGuidance": [
            {
                "code": "NORMALIZED_PROVIDER_CONVERSION_GUIDANCE",
                "summary": "Mapper methods should be split by business branch.",
                "status": "REVIEW_REQUIRED",
                "evidenceRefs": evidence_refs,
            }
        ],
        "migrationGuideInsights": [
            {
                "section": "migrationGuideInsight:call_flow",
                "summary": "CRUDFlag branches drive the human guide call flow.",
                "status": "REVIEW_REQUIRED",
                "evidenceRefs": ["static.branch.crudflag.r"],
            }
        ],
        "reviewMarkers": [
            {
                "code": "CROSS_DB_WRITE_REVIEW_REQUIRED",
                "summary": "ERP write needs manual verification.",
                "evidenceRefs": ["static.dml.update.erp_dbo_xxeai_trx_header_ii"],
            }
        ],
    }


def _markdown_headings(markdown: str) -> list[str]:
    return [
        line.strip()
        for line in markdown.splitlines()
        if re.match(r"^#{1,4}\s+", line)
    ]
