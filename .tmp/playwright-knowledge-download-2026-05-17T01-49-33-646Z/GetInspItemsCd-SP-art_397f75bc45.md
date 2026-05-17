# GetInspItemsCd SP 분석 초안

## input_interpretation
- systemCode: PPM
- entityName: GetInspItemsCd
- spName: dbo.GetInspItemsCd
- tableName: dbo.PEX_INSP_ITEMS

## analysis_summary
- 상태: 초안(`DRAFT`)
- 근거 보강 필요: SP 내부 제어 흐름과 비즈니스 규칙은 canonical analysis 확정 후 보강
- generationMode: spWrapper

## procedure_signature
- `InspItemsCd` varchar required=true

## result_shape
- `INSP_ITEMS_CD`
- `INSP_ITEMS_CLASS_CD`
- `INSP_ITEMS_NM`
- `INSP_ITEMS_DESC`
- `INSP_ITEMS_DIV_CD`
- `SUPI_INSP_ITEMS_CD`
- `WIH_INSP_YN`
- `INSP_ITEMS_SEQ_NO`
- `VLD_YN`
- `CRE_USR_ID`
- `CRE_DTM`
- `UPD_USR_ID`
- `UPD_DTM`

## dependency_summary
- 저장 프로시저: `dbo.GetInspItemsCd`
- 테이블: `dbo.PEX_INSP_ITEMS`

<!-- section:sp_overview -->
## 1. SP 개요 및 기본 정보
<!-- section-title:SP 개요 및 기본 정보 -->
<!-- contract-title:SP 개요 및 기본 정보 -->
- 근거: ev_metadata_1
<!-- claim:claim_sp_overview status=evidence_caveat evidenceRefs=ev_metadata_1 -->
- 판단: sp_overview section은 sanitized metadata/static fact를 근거로 렌더링됩니다. 상태=근거 보강 필요 근거=ev_metadata_1
| 항목 | 값 | 상태 | 근거 |
|---|---|---|---|
| 대상 SP | dbo.GetInspItemsCd | Confirmed | ev_metadata_1 |
| 메타데이터 프로필 | ppm | Confirmed | ev_metadata_1 |
| 입력 파라미터 수 | 1 | Confirmed | ev_metadata_1 |
| 결과 필드 후보 수 | 13 | 근거 보강 필요 | static.analysis.migration_guide |

- targetRef: `dbo.GetInspItemsCd`
- fixtureId: `req_6a824d7e23`
- status: DRAFT
- productionReady: `false`
- artifactsUnderTest: SP_ANALYSIS_DOC, DEPENDENCY_REPORT
- metadataProfileId: `ppm`
- targetDb: `PPM`
- platformDb: `PLF`
- plfFallback: `forbidden`

<!-- section:feature_branch_taxonomy -->
## 2. 주요 기능과 분기/플래그 분류
<!-- section-title:주요 기능과 분기/플래그 분류 -->
<!-- contract-title:주요 기능과 분기/플래그 분류 -->
- 근거: static.analysis.migration_guide
<!-- claim:claim_feature_branch_taxonomy status=evidence_caveat evidenceRefs=static.analysis.migration_guide -->
- 판단: feature_branch_taxonomy section은 sanitized metadata/static fact를 근거로 렌더링됩니다. 상태=근거 보강 필요 근거=static.analysis.migration_guide
| 기능/분기 | 조건/트리거 | 상태 | 요약 | 근거 |
|---|---|---|---|---|
| SELECT 영향 | static DML scan | Confirmed | PEX_INSP_ITEMS에 대한 SELECT 영향이 감지되었습니다. | static.dml.select.pex_insp_items |
| overview | LLM_INFERENCE_EVIDENCE_CAVEAT | 근거 보강 필요 | 프로시저 정의 접근 가능 및 비암호화 상태는 확인되었으나, 운영 의도(파라미터 활용/정렬/반환량)는 메타데이터만으로 확정할 수 없습니다. | metadata:dbo.GetInspItemsCd:sys.objects, metadata.procedureDefinitionHash, metadata:dbo.GetInspItemsCd:sys.parameters, metadata:dbo.GetInspItemsCd:sys.sql_modules |
| dependency_inventory | LLM_INFERENCE_EVIDENCE_CAVEAT | 근거 보강 필요 | 동일 DB 내 dbo.PEX_INSP_ITEMS 단일 테이블 참조는 확인되었고, 추가 간접 의존성 존재 여부는 후속 검증이 필요합니다. | mcp.get_dependency_closure.7d8c98adf992, mcp.get_related_db_objects.4e8b9dd1bdae, metadata:dbo.GetInspItemsCd:sys.sql_expression_dependencies, metadata:dbo.PEX_INSP_ITEMS:sys.objects,sys.schemas:referenced_id |
| query-parameterization | LLM_INFERENCE_EVIDENCE_CAVEAT | 근거 보강 필요 | 파라미터 정의와 실제 필터 반영 사이 의미 불일치 가능성이 있어 Java 메서드 시그니처 확정 전 검토가 필요합니다. | metadata:dbo.GetInspItemsCd:sys.parameters, metadata:dbo.GetInspItemsCd:sys.sql_modules |
| result-mapping | LLM_INFERENCE_EVIDENCE_CAVEAT | 근거 보강 필요 | 반환 컬럼 후보 3개는 식별되나 템플릿성 흔적이 있어 최종 SELECT/alias/타입 매핑 확정 전 재검증이 필요합니다. | metadata:dbo.GetInspItemsCd:sys.sql_modules, metadata:dbo.GetInspItemsCd:sys.sql_modules:hash-pattern, metadata:dbo.PEX_INSP_ITEMS:sys.columns |
| call_flow | LLM_INFERENCE_EVIDENCE_CAVEAT | 근거 보강 필요 | 분기/루프/트랜잭션/TRY-CATCH 없는 단순 조회 흐름으로 보이나, 호출자 후처리 존재 여부는 확인이 필요합니다. | metadata:dbo.GetInspItemsCd:sys.sql_modules:hash-pattern, mcp.get_dependency_closure.7d8c98adf992 |
| migration_strategy | LLM_INFERENCE_EVIDENCE_CAVEAT | 근거 보강 필요 | Java Service + MyBatis Mapper 직변환 후보이나 파라미터 활용 정책 확정이 선행되어야 합니다. | metadata:dbo.GetInspItemsCd:sys.parameters, metadata:dbo.GetInspItemsCd:sys.sql_modules, platform.list_registry_versions.82c6b9e03ac7 |
| dml_matrix | LLM_INFERENCE_EVIDENCE_CAVEAT | 근거 보강 필요 | Confirmed: SELECT 기반 읽기 동작으로 분류됩니다. Needs verification: 템플릿성 주석 흔적이 있어 변경 이력에서 쓰기 연산 도입 여부를 확인할 필요가 있습니다. | metadata:dbo.GetInspItemsCd:sys.sql_modules, metadata:dbo.GetInspItemsCd:sys.sql_modules:hash-pattern |
| metadata_extraction_appendix | LLM_INFERENCE_EVIDENCE_CAVEAT | 근거 보강 필요 | Confirmed: 객체/파라미터/의존성/컬럼 메타데이터가 확보되었습니다. Needs verification: extended properties가 비어 있어 도메인 설명 보강이 필요합니다. | mcp.get_extended_properties.51cd70011e11, metadata:dbo.PEX_INSP_ITEMS:sys.columns, metadata:dbo.GetInspItemsCd:sys.objects |
| DETERMINISTIC_SAFETY_NET_LOOKUP_GUIDE | LLM_INFERENCE_EVIDENCE_CAVEAT | 근거 보강 필요 | 마이그레이션 가이드는 조회 입력, 읽기 의존성, result-shape 검토 메모를 포함해야 합니다. | mcp.get_extended_properties.51cd70011e11, mcp.get_related_db_objects.4e8b9dd1bdae |

<!-- fact:fact_target_identity type=PROCEDURE_IDENTITY evidenceRefs=ev_metadata_1 -->
- 근거 사실: 전환 가이드 대상은 dbo.GetInspItemsCd입니다. 유형=PROCEDURE_IDENTITY 근거=ev_metadata_1
<!-- fact:fact_parameter_inventory type=PROCEDURE_PARAMETERS evidenceRefs=ev_metadata_1 -->
- 근거 사실: 메타데이터에서 파라미터 1개를 확인했습니다. 유형=PROCEDURE_PARAMETERS 근거=ev_metadata_1
<!-- fact:fact_result_shape type=RESULT_SHAPE evidenceRefs=static.analysis.migration_guide -->
- 근거 사실: 결과 필드 후보 13개를 사용할 수 있습니다. 유형=RESULT_SHAPE 근거=static.analysis.migration_guide

<!-- section:dependency_inventory -->
## 3. 의존성 목록
<!-- section-title:의존성 목록 -->
<!-- contract-title:의존성 목록 -->
- 근거: static.analysis.migration_guide
<!-- claim:claim_dependency_inventory status=evidence_caveat evidenceRefs=static.analysis.migration_guide -->
- 판단: dependency_inventory section은 sanitized metadata/static fact를 근거로 렌더링됩니다. 상태=근거 보강 필요 근거=static.analysis.migration_guide
### 확인됨
| 유형 | 이름 | 참조 방식 | 근거 | 비고 |
|---|---|---|---|---|
| reference | `|PPM|dbo|PEX_INSP_ITEMS|TABLE` | REFERENCED_ID | PEX_INSP_ITEMS, dbo.PEX_INSP_ITEMS | REFERENCED_ID CATALOG_OBJECT_ID |
| table | `PEX_INSP_ITEMS` | static parser | static.analysis.migration_guide | 정적 parser에서 확인한 참조입니다.  |

### 근거 보강 필요
| 유형 | 이름/후보 | 불확실한 이유 | 다음 추출 항목 | 비고 |
|---|---|---|---|---|
| 없음 | 없음 | 없음 | 없음 | 근거 보강이 필요한 의존성 후보가 없습니다. |
- llmInsightBoundary: `LLM_INFERENCE_EVIDENCE_CAVEAT`
- llmMigrationGuideInsight: dependency_inventory status=evidence_caveat evidenceRefs=mcp.get_dependency_closure.7d8c98adf992, mcp.get_related_db_objects.4e8b9dd1bdae, metadata:dbo.GetInspItemsCd:sys.sql_expression_dependencies, metadata:dbo.PEX_INSP_ITEMS:sys.objects,sys.schemas:referenced_id summary=동일 DB 내 dbo.PEX_INSP_ITEMS 단일 테이블 참조는 확인되었고, 추가 간접 의존성 존재 여부는 후속 검증이 필요합니다. whatToExtractNext=뷰/함수/동적 SQL 경유 간접 참조 유무를 배포 산출물과 대조하세요.

<!-- section:dml_impact_matrix -->
## 4. DML 영향 매트릭스
<!-- section-title:DML 영향 매트릭스 -->
<!-- contract-title:DML 영향 매트릭스 -->
- 근거: static.analysis.migration_guide
<!-- claim:claim_dml_impact_matrix status=evidence_caveat evidenceRefs=static.analysis.migration_guide -->
- 판단: dml_impact_matrix section은 sanitized metadata/static fact를 근거로 렌더링됩니다. 상태=근거 보강 필요 근거=static.analysis.migration_guide
| 테이블 | SELECT | INSERT | UPDATE | DELETE | MERGE | 키/조인/조건 요약 | 중요 컬럼/패턴 | 근거 |
|---|---|---|---|---|---|---|---|---|
| `PEX_INSP_ITEMS` | Y |  |  |  |  | 근거 보강 필요: predicate/key 추출은 추가 근거 확인이 필요합니다. | 근거 보강 필요: 중요 컬럼 패턴은 LLM 출력만으로 추론하지 않습니다. | static.dml.select.pex_insp_items |

| 작업 | 대상 | 단계 | 상태 | evidenceRefs | 영향 |
|---|---|---|---|---|---|
| SELECT | `PEX_INSP_ITEMS` | static_dml_scan | Confirmed | static.dml.select.pex_insp_items | PEX_INSP_ITEMS에 대한 SELECT 참조를 감지했습니다. |

<!-- section:call_flow -->
## 5. 분기 단위 호출 흐름
<!-- section-title:분기 단위 호출 흐름 -->
<!-- contract-title:분기 단위 호출 흐름 -->
- 근거: static.analysis.migration_guide
<!-- claim:claim_call_flow status=evidence_caveat evidenceRefs=static.analysis.migration_guide -->
- 판단: call_flow section은 sanitized metadata/static fact를 근거로 렌더링됩니다. 상태=근거 보강 필요 근거=static.analysis.migration_guide
- 입력:
  - 메타데이터에서 확인한 procedure 파라미터입니다.
- 분기: branch_dml_1 phase=static_dml_scan evidenceRefs=static.dml.select.pex_insp_items 조건=PEX_INSP_ITEMS에 대한 SELECT 참조를 감지했습니다.
  - 동작: SELECT dependency=PEX_INSP_ITEMS evidenceRefs=static.dml.select.pex_insp_items
- 결과 / 출력:
  - 결과 shape 후보는 appendix mappings에 렌더링됩니다.
- 오류 처리: 근거 보강 필요: 정상/예외/resource cleanup 분기를 확인합니다.
- llmInsightBoundary: `LLM_INFERENCE_EVIDENCE_CAVEAT`
- llmMigrationGuideInsight: call_flow status=evidence_caveat evidenceRefs=metadata:dbo.GetInspItemsCd:sys.sql_modules:hash-pattern, mcp.get_dependency_closure.7d8c98adf992 summary=분기/루프/트랜잭션/TRY-CATCH 없는 단순 조회 흐름으로 보이나, 호출자 후처리 존재 여부는 확인이 필요합니다. whatToExtractNext=애플리케이션 호출부에서 본 프로시저 결과에 대한 후처리(필터/정렬/재가공) 유무를 확인하세요.

<!-- section:critical_phase_analysis -->
## 6. 핵심 단계 분석
<!-- section-title:핵심 단계 분석 -->
<!-- contract-title:핵심 단계 분석 -->
- 근거: static.analysis.migration_guide
<!-- claim:claim_critical_phase_analysis status=evidence_caveat evidenceRefs=static.analysis.migration_guide -->
- 판단: critical_phase_analysis section은 sanitized metadata/static fact를 근거로 렌더링됩니다. 상태=근거 보강 필요 근거=static.analysis.migration_guide
- branchCount: `1`
- dmlOperationCount: `1`
| Phase | 주요 읽기 | 주요 쓰기 | 위험/검토점 | 상태 | 근거 |
|---|---|---|---|---|---|
| static_dml_scan | PEX_INSP_ITEMS | 근거 보강 필요 | RESULT_SHAPE_NEEDS_VERIFICATION, PARAMETER_SEMANTIC_GAP, NORMALIZED_PROVIDER_RISKFLAGS_0, NORMALIZED_PROVIDER_RISKFLAGS_1, RESULT_SHAPE_UNCERTAIN, PARAMETER_CONTRACT_GAP, RESULT_SHAPE_UNCERTAINTY | Confirmed | static.dml.select.pex_insp_items |
- 근거 보강 필요: 단계 순서와 트랜잭션 의미는 추가 근거 확인이 필요합니다.

<!-- section:complexity_risk_metrics -->
## 7. 복잡도 및 위험 지표
<!-- section-title:복잡도 및 위험 지표 -->
<!-- contract-title:복잡도 및 위험 지표 -->
- 근거: static.analysis.migration_guide
<!-- claim:claim_complexity_risk_metrics status=evidence_caveat evidenceRefs=static.analysis.migration_guide -->
- 판단: complexity_risk_metrics section은 sanitized metadata/static fact를 근거로 렌더링됩니다. 상태=근거 보강 필요 근거=static.analysis.migration_guide
- complexityScore: `1`
- branchCount: `1`
- dmlOperationCount: `1`
| 지표 | 건수 | 근거/규칙 | 비고 | 근거 |
|---|---:|---|---|---|
| LOC | 21 | Non-empty source lines after trimming whitespace. |  | static.analysis.migration_guide |
| BEGIN_END_BLOCK | 1 | Minimum of BEGIN and END tokens. |  | static.analysis.migration_guide |
| IF | 0 | IF keyword count. |  | static.analysis.migration_guide |
| ELSE | 0 | ELSE keyword count. |  | static.analysis.migration_guide |
| WHILE | 0 | WHILE keyword count. |  | static.analysis.migration_guide |
| CASE | 0 | CASE keyword count. |  | static.analysis.migration_guide |
| GOTO | 0 | GOTO keyword count. |  | static.analysis.migration_guide |
| RETURN | 0 | RETURN keyword count. |  | static.analysis.migration_guide |
| CURSOR_SIGNAL | 0 | DECLARE CURSOR / OPEN / FETCH / CLOSE / DEALLOCATE signal count. |  | static.analysis.migration_guide |
| TRY_CATCH_BLOCK | 0 | BEGIN TRY/CATCH token count. |  | static.analysis.migration_guide |
| TRANSACTION_SIGNAL | 0 | Transaction control or @@TRANCOUNT signal count. |  | static.analysis.migration_guide |
| DYNAMIC_SQL_SIGNAL | 0 | sp_executesql, EXEC(...), or EXEC @variable signal count. |  | static.analysis.migration_guide |
| CROSS_DB_REFERENCE | 0 | Unique three- or four-part identifier count. |  | static.analysis.migration_guide |
- risk: RESULT_SHAPE_NEEDS_VERIFICATION status=evidence_caveat severity=WARNING evidenceRefs=metadata:dbo.GetInspItemsCd:sys.sql_modules, metadata:dbo.PEX_INSP_ITEMS:sys.columns
- risk: PARAMETER_SEMANTIC_GAP status=evidence_caveat severity=WARNING evidenceRefs=metadata:dbo.GetInspItemsCd:sys.parameters, metadata:dbo.GetInspItemsCd:sys.sql_modules
- risk: NORMALIZED_PROVIDER_RISKFLAGS_0 status=evidence_caveat severity=WARNING evidenceRefs=metadata:dbo.GetInspItemsCd:sys.sql_modules, metadata:dbo.PEX_INSP_ITEMS:sys.columns, metadata.procedureDefinitionHash
- risk: NORMALIZED_PROVIDER_RISKFLAGS_1 status=evidence_caveat severity=WARNING evidenceRefs=metadata:dbo.GetInspItemsCd:sys.parameters, metadata:dbo.GetInspItemsCd:sys.sql_modules
- risk: RESULT_SHAPE_UNCERTAIN status=evidence_caveat severity=WARNING evidenceRefs=metadata:dbo.GetInspItemsCd:sys.sql_modules, metadata:dbo.PEX_INSP_ITEMS:sys.columns, metadata.procedureDefinitionHash
- risk: PARAMETER_CONTRACT_GAP status=evidence_caveat severity=WARNING evidenceRefs=metadata:dbo.GetInspItemsCd:sys.parameters, metadata:dbo.GetInspItemsCd:sys.sql_modules
- risk: RESULT_SHAPE_UNCERTAINTY status=evidence_caveat severity=WARNING evidenceRefs=metadata:dbo.GetInspItemsCd:sys.sql_modules, metadata:dbo.PEX_INSP_ITEMS:sys.columns, metadata.procedureDefinitionHash

<!-- section:migration_strategy -->
## 8. 전환 전략 및 Java/MyBatis 초안 준비도
<!-- section-title:전환 전략 및 Java/MyBatis 초안 준비도 -->
<!-- contract-title:전환 전략 및 Java/MyBatis 초안 준비도 -->
- 근거: static.analysis.migration_guide
<!-- claim:claim_migration_strategy status=evidence_caveat evidenceRefs=static.analysis.migration_guide -->
- 판단: migration_strategy section은 sanitized metadata/static fact를 근거로 렌더링됩니다. 상태=근거 보강 필요 근거=static.analysis.migration_guide
- javaMyBatisReadiness: `draft_notes_only`
- generated_source_application: `not_performed`
- automatic_conversion_completion: `not_claimed`
- target_application_write: `not_performed`
- 근거 보강 필요: Java/MyBatis 초안에는 근거 보강과 위험 caveat가 남아 있습니다.
- llmInsightBoundary: `LLM_INFERENCE_EVIDENCE_CAVEAT`
- llmConversionGuidance: MYBATIS_SINGLE_SELECT_BASELINE status=evidence_caveat evidenceRefs=metadata:dbo.GetInspItemsCd:sys.parameters, metadata:dbo.GetInspItemsCd:sys.sql_modules, metadata:dbo.PEX_INSP_ITEMS:sys.columns summary=Java/MyBatis 전환은 단일 select 매퍼와 String 입력 파라미터, 3필드 DTO 매핑을 기본안으로 시작하되 파라미터 실제 사용 규칙 확정이 선행되어야 합니다.
- llmConversionGuidance: NORMALIZED_PROVIDER_CONVERSIONGUIDANCE_0 status=evidence_caveat evidenceRefs=metadata:dbo.GetInspItemsCd:sys.parameters, metadata:dbo.GetInspItemsCd:sys.sql_modules, metadata:dbo.PEX_INSP_ITEMS:sys.columns summary=MyBatis 단일 select 매퍼와 3개 필드 DTO 매핑을 기본안으로 시작하되, 최종 결과 매핑은 검증 후 확정하세요.
- llmConversionGuidance: NORMALIZED_PROVIDER_CONVERSIONGUIDANCE_1 status=evidence_caveat evidenceRefs=metadata:dbo.GetInspItemsCd:sys.parameters, metadata:dbo.GetInspItemsCd:sys.sql_modules, mcp.get_related_db_objects.4e8b9dd1bdae, metadata:PEX_INSP_ITEMS:sys.sql_expression_dependencies summary=@InspItemsCd의 WHERE 바인딩 의도를 먼저 확정한 뒤 Java 메서드 파라미터 계약을 고정하세요.
- llmConversionGuidance: JAVA_MYBATIS_BASELINE_SELECT status=evidence_caveat evidenceRefs=metadata:dbo.GetInspItemsCd:sys.sql_modules, metadata:dbo.GetInspItemsCd:sys.parameters, metadata:dbo.PEX_INSP_ITEMS:sys.columns summary=Java Service + MyBatis Mapper로 1개 select 매퍼를 우선 구성하고, DTO는 INSP_ITEMS_CD/INSP_ITEMS_NM/INSP_ITEMS_DESC 3개 필드를 기본안으로 두십시오.
- llmConversionGuidance: JAVA_MYBATIS_PARAMETER_POLICY status=evidence_caveat evidenceRefs=metadata:dbo.GetInspItemsCd:sys.parameters, metadata:dbo.GetInspItemsCd:sys.sql_modules, mcp.get_related_db_objects.4e8b9dd1bdae summary=@InspItemsCd를 WHERE LIKE에 바인딩할지, 미사용 파라미터로 제거할지 업무 규칙을 먼저 확정한 뒤 Mapper 파라미터 타입(String)과 SQL 조건식을 고정하십시오.
- llmConversionGuidance: JAVA_MYBATIS_READONLY_CLASSIFICATION status=evidence_caveat evidenceRefs=metadata:dbo.GetInspItemsCd:sys.sql_modules, metadata:dbo.GetInspItemsCd:sys.sql_modules:hash-pattern, mcp.get_dependency_closure.7d8c98adf992 summary=현재는 읽기 전용 조회 패턴으로 분류되지만 템플릿성 주석 흔적이 있어 향후 DML 유입 여부를 형상 이력으로 교차 검증하십시오.
- llmConversionGuidance: MYBATIS_BASELINE_MAPPING status=evidence_caveat evidenceRefs=metadata:dbo.GetInspItemsCd:sys.parameters, metadata:dbo.PEX_INSP_ITEMS:sys.columns, metadata:dbo.GetInspItemsCd:sys.sql_modules summary=MyBatis는 단일 select 매퍼와 String 파라미터(@InspItemsCd), 3개 필드 DTO 매핑을 기본안으로 시작하되 파라미터 사용 의도 확인 후 확정하는 것이 적절합니다.
- llmConversionGuidance: DETERMINISTIC_SAFETY_NET_LOOKUP_CONVERSION_GUIDANCE status=evidence_caveat evidenceRefs=mcp.get_extended_properties.51cd70011e11, mcp.get_related_db_objects.4e8b9dd1bdae summary=결정론적 DTO 계약이 검증될 때까지 조회 parameter binding과 결과 매핑은 근거 보강 필요로 유지합니다.
- llmInsightBoundary: `LLM_INFERENCE_EVIDENCE_CAVEAT`
- llmMigrationGuideInsight: migration_strategy status=evidence_caveat evidenceRefs=metadata:dbo.GetInspItemsCd:sys.parameters, metadata:dbo.GetInspItemsCd:sys.sql_modules, platform.list_registry_versions.82c6b9e03ac7 summary=Java Service + MyBatis Mapper 직변환 후보이나 파라미터 활용 정책 확정이 선행되어야 합니다. whatToExtractNext=요구사항 문서에서 검색 파라미터 필수 여부와 LIKE 매칭 정책을 확정하세요.

<!-- section:appendix_mappings -->
## 9. 파라미터 및 코드 매핑 부록
<!-- section-title:파라미터 및 코드 매핑 부록 -->
<!-- contract-title:파라미터 및 코드 매핑 부록 -->
- 근거: ev_metadata_1
<!-- claim:claim_appendix_mappings status=evidence_caveat evidenceRefs=ev_metadata_1 -->
- 판단: appendix_mappings section은 sanitized metadata/static fact를 근거로 렌더링됩니다. 상태=근거 보강 필요 근거=ev_metadata_1
- parameters:
  - name=InspItemsCd sanitizedType=varchar evidenceRefs=ev_metadata_1
- 결과 필드:
  - name=INSP_ITEMS_CD evidenceRefs=static.analysis.migration_guide
  - name=INSP_ITEMS_CLASS_CD evidenceRefs=static.analysis.migration_guide
  - name=INSP_ITEMS_NM evidenceRefs=static.analysis.migration_guide
  - name=INSP_ITEMS_DESC evidenceRefs=static.analysis.migration_guide
  - name=INSP_ITEMS_DIV_CD evidenceRefs=static.analysis.migration_guide
  - name=SUPI_INSP_ITEMS_CD evidenceRefs=static.analysis.migration_guide
  - name=WIH_INSP_YN evidenceRefs=static.analysis.migration_guide
  - name=INSP_ITEMS_SEQ_NO evidenceRefs=static.analysis.migration_guide
  - name=VLD_YN evidenceRefs=static.analysis.migration_guide
  - name=CRE_USR_ID evidenceRefs=static.analysis.migration_guide
  - name=CRE_DTM evidenceRefs=static.analysis.migration_guide
  - name=UPD_USR_ID evidenceRefs=static.analysis.migration_guide
  - name=UPD_DTM evidenceRefs=static.analysis.migration_guide

<!-- section:metadata_extraction_appendix -->
## 10. 수동 메타데이터 추출 부록
<!-- section-title:수동 메타데이터 추출 부록 -->
<!-- contract-title:수동 메타데이터 추출 부록 -->
- 근거: static.analysis.migration_guide
<!-- claim:claim_metadata_extraction_appendix status=evidence_caveat evidenceRefs=static.analysis.migration_guide -->
- 판단: metadata_extraction_appendix section은 sanitized metadata/static fact를 근거로 렌더링됩니다. 상태=근거 보강 필요 근거=static.analysis.migration_guide
- 정책: 수동 메타데이터 보강용입니다. 원천 메타데이터 DB에 대해 SSMS에서 실행하되, procedure 실행, row data 조회, DDL/DML 적용, raw definition 붙여넣기는 금지합니다.
### definition_hash_length
- 제목: SP definition hash/length 확인
```sql
DECLARE @SchemaName sysname = N'dbo';
DECLARE @ObjectName sysname = N'GetInspItemsCd';
DECLARE @FullName nvarchar(517) = QUOTENAME(@SchemaName) + N'.' + QUOTENAME(@ObjectName);
SELECT DB_NAME() AS database_name, s.name AS schema_name, o.name AS object_name,
       CONVERT(varchar(64), HASHBYTES('SHA2_256', CONVERT(varbinary(max), sm.definition)), 2) AS definition_sha256,
       DATALENGTH(sm.definition) AS definition_bytes
FROM sys.objects o
JOIN sys.schemas s ON s.schema_id = o.schema_id
JOIN sys.sql_modules sm ON sm.object_id = o.object_id
WHERE s.name = @SchemaName AND o.name = @ObjectName;
```
- 결과 붙여넣기 템플릿: | database_name | schema_name | object_name | definition_sha256 | definition_bytes | status |
### parameters
- 제목: Procedure parameters 확인
```sql
DECLARE @SchemaName sysname = N'dbo';
DECLARE @ObjectName sysname = N'GetInspItemsCd';
DECLARE @FullName nvarchar(517) = QUOTENAME(@SchemaName) + N'.' + QUOTENAME(@ObjectName);
SELECT p.parameter_id, p.name, TYPE_NAME(p.user_type_id) AS data_type,
       p.max_length, p.precision, p.scale, p.is_output
FROM sys.parameters p
WHERE p.object_id = OBJECT_ID(@FullName)
ORDER BY p.parameter_id;
```
- 결과 붙여넣기 템플릿: | parameter_id | name | data_type | max_length | precision | scale | is_output | status |
### static_dependencies
- 제목: Static catalog dependencies 확인
```sql
DECLARE @SchemaName sysname = N'dbo';
DECLARE @ObjectName sysname = N'GetInspItemsCd';
DECLARE @FullName nvarchar(517) = QUOTENAME(@SchemaName) + N'.' + QUOTENAME(@ObjectName);
SELECT referenced_server_name, referenced_database_name, referenced_schema_name,
       referenced_entity_name, referenced_class_desc, is_caller_dependent, is_ambiguous
FROM sys.sql_expression_dependencies
WHERE referencing_id = OBJECT_ID(@FullName);
```
- 결과 붙여넣기 템플릿: | server | database | schema | entity | class | caller_dependent | ambiguous | status |
### referenced_entities
- 제목: Referenced entities DMV 확인
```sql
DECLARE @SchemaName sysname = N'dbo';
DECLARE @ObjectName sysname = N'GetInspItemsCd';
DECLARE @FullName nvarchar(517) = QUOTENAME(@SchemaName) + N'.' + QUOTENAME(@ObjectName);
SELECT referenced_schema_name, referenced_entity_name, referenced_minor_name,
       referenced_class_desc, is_selected, is_updated, is_select_all
FROM sys.dm_sql_referenced_entities(@FullName, N'OBJECT');
```
- 결과 붙여넣기 템플릿: | schema | entity | minor_name | class | selected | updated | select_all | status |
### dynamic_sql_indicators
- 제목: Dynamic SQL 및 외부 참조 indicator 확인
```sql
DECLARE @SchemaName sysname = N'dbo';
DECLARE @ObjectName sysname = N'GetInspItemsCd';
DECLARE @FullName nvarchar(517) = QUOTENAME(@SchemaName) + N'.' + QUOTENAME(@ObjectName);
SELECT CASE WHEN sm.definition LIKE '%sp_executesql%' THEN 1 ELSE 0 END AS has_sp_executesql,
       CASE WHEN sm.definition LIKE '%EXEC(%' OR sm.definition LIKE '%EXEC (@%' THEN 1 ELSE 0 END AS has_exec_string,
       CASE WHEN sm.definition LIKE '%OPENQUERY%' THEN 1 ELSE 0 END AS has_openquery
FROM sys.sql_modules sm
WHERE sm.object_id = OBJECT_ID(@FullName);
```
- 결과 붙여넣기 템플릿: | has_sp_executesql | has_exec_string | has_openquery | status | what_to_extract_next |
### temp_table_review
- 제목: Temp table/table variable 검토 indicator 확인
```sql
DECLARE @SchemaName sysname = N'dbo';
DECLARE @ObjectName sysname = N'GetInspItemsCd';
DECLARE @FullName nvarchar(517) = QUOTENAME(@SchemaName) + N'.' + QUOTENAME(@ObjectName);
SELECT CASE WHEN sm.definition LIKE '%CREATE TABLE #%' THEN 1 ELSE 0 END AS has_temp_table,
       CASE WHEN sm.definition LIKE '%DECLARE @% TABLE%' THEN 1 ELSE 0 END AS has_table_variable
FROM sys.sql_modules sm
WHERE sm.object_id = OBJECT_ID(@FullName);
```
- 결과 붙여넣기 템플릿: | has_temp_table | has_table_variable | status | what_to_extract_next |
- 붙여넣기 템플릿:
  - | 유형 | 이름 | 참조 방식 | 근거 | 비고 |
  - | 유형 | 이름/후보 | 불확실한 이유 | 다음 추출 항목 | 비고 |
- llmInsightBoundary: `LLM_INFERENCE_EVIDENCE_CAVEAT`
- llmMigrationGuideInsight: metadata_extraction_appendix status=evidence_caveat evidenceRefs=mcp.get_extended_properties.51cd70011e11, metadata:dbo.PEX_INSP_ITEMS:sys.columns, metadata:dbo.GetInspItemsCd:sys.objects summary=Confirmed: 객체/파라미터/의존성/컬럼 메타데이터가 확보되었습니다. Needs verification: extended properties가 비어 있어 도메인 설명 보강이 필요합니다. whatToExtractNext=용어사전/테이블 명세에서 컬럼 의미와 값 도메인 설명을 추가 추출하세요.

<!-- section:evidence_assumptions_review -->
## 11. 근거, 가정, 품질 caveat
<!-- section-title:근거, 가정, 품질 caveat -->
<!-- contract-title:근거, 가정, 품질 caveat -->
- 근거: static.analysis.migration_guide
<!-- claim:claim_evidence_assumptions_review status=evidence_caveat evidenceRefs=static.analysis.migration_guide -->
- 판단: evidence_assumptions_review section은 sanitized metadata/static fact를 근거로 렌더링됩니다. 상태=근거 보강 필요 근거=static.analysis.migration_guide
- evidenceRefs:
  - id=ev_metadata_1 type=MSSQL_METADATA objectRef=dbo.GetInspItemsCd locator=sys.sql_modules
  - id=ev_metadata_2 type=MSSQL_METADATA objectRef=dbo.GetInspItemsCd locator=sys.parameters
  - id=ev_metadata_3 type=MSSQL_METADATA objectRef=dbo.GetInspItemsCd locator=sys.sql_expression_dependencies
  - id=ev_metadata_4 type=MSSQL_METADATA objectRef=dbo.GetInspItemsCd locator=sys.sql_modules:hash-pattern
  - id=ev_metadata_5 type=MSSQL_METADATA objectRef=dbo.GetInspItemsCd locator=sys.objects
  - id=ev_metadata_6 type=MSSQL_METADATA objectRef=dbo.GetInspItemsCd locator=sys.objects
  - id=ev_metadata_7 type=MSSQL_METADATA objectRef=PEX_INSP_ITEMS locator=sys.sql_expression_dependencies
  - id=ev_metadata_8 type=MSSQL_METADATA objectRef=dbo.PEX_INSP_ITEMS locator=sys.objects,sys.schemas:referenced_id
  - id=ev_metadata_9 type=MSSQL_METADATA objectRef=dbo.PEX_INSP_ITEMS locator=sys.columns
  - id=static.analysis.migration_guide type=STATIC_ANALYSIS objectRef=dbo.GetInspItemsCd locator=analysis.migrationGuideStaticMetrics
- knownCaveats:
  - claimCode=RESULT_SHAPE_NEEDS_VERIFICATION claimType=risk status=evidence_caveat obligation=low_evidence_business_rule_claims evidenceRefs=metadata:dbo.GetInspItemsCd:sys.sql_modules, metadata:dbo.PEX_INSP_ITEMS:sys.columns
  - claimCode=PARAMETER_SEMANTIC_GAP claimType=risk status=evidence_caveat obligation=low_evidence_business_rule_claims evidenceRefs=metadata:dbo.GetInspItemsCd:sys.parameters, metadata:dbo.GetInspItemsCd:sys.sql_modules
  - claimCode=NORMALIZED_PROVIDER_RISKFLAGS_0 claimType=risk status=evidence_caveat obligation=low_evidence_business_rule_claims evidenceRefs=metadata:dbo.GetInspItemsCd:sys.sql_modules, metadata:dbo.PEX_INSP_ITEMS:sys.columns, metadata.procedureDefinitionHash
  - claimCode=NORMALIZED_PROVIDER_RISKFLAGS_1 claimType=risk status=evidence_caveat obligation=low_evidence_business_rule_claims evidenceRefs=metadata:dbo.GetInspItemsCd:sys.parameters, metadata:dbo.GetInspItemsCd:sys.sql_modules
  - claimCode=RESULT_SHAPE_UNCERTAIN claimType=risk status=evidence_caveat obligation=low_evidence_business_rule_claims evidenceRefs=metadata:dbo.GetInspItemsCd:sys.sql_modules, metadata:dbo.PEX_INSP_ITEMS:sys.columns, metadata.procedureDefinitionHash
  - claimCode=PARAMETER_CONTRACT_GAP claimType=risk status=evidence_caveat obligation=low_evidence_business_rule_claims evidenceRefs=metadata:dbo.GetInspItemsCd:sys.parameters, metadata:dbo.GetInspItemsCd:sys.sql_modules
  - claimCode=RESULT_SHAPE_UNCERTAINTY claimType=risk status=evidence_caveat obligation=low_evidence_business_rule_claims evidenceRefs=metadata:dbo.GetInspItemsCd:sys.sql_modules, metadata:dbo.PEX_INSP_ITEMS:sys.columns, metadata.procedureDefinitionHash
- 가정: 근거 보강 필요 근거 보강 필요: metadata는 MSSQL MCP registry 경계를 통해 수집되며 이 integration slice에서는 platform DB workflow repository에 저장됩니다.
- 가정: 근거 보강 필요 근거 보강 필요: LLM semantic analysis is inferred; treat it as an evidence caveat.
- 가정: 근거 보강 필요 Provider returned a structured assumption object; text was not stored.
- 가정: 근거 보강 필요 DETERMINISTIC_SAFETY_NET은 허용된 결정론적 fact id만 사용해 초안 claim을 추가했습니다.
- 가정: 근거 보강 필요 confirmed dependency procedure semantic outputs are draft-only evidence aids.

## quality_summary
- status: draft-quality evidence caveats tracked
- raw SQL text, row data, secrets, execution output은 포함하지 않습니다.

## evidence_map
- claims are tied to evidenceRefs or evidence caveats.

## known_caveats
- 근거 보강 필요는 근거 보강 필요 상태를 의미합니다.

## next_evidence_to_collect
- DML matrix, branch call-flow, transaction boundary, Java/MyBatis mapping evidence를 보강합니다.

## draft_readiness
- Ready as a migration-guide draft; no publish, deploy, DDL, DML, or source apply path is included.

## llm_semantic_analysis
- 상태: 근거 보강 필요(`근거 보강 필요`)
- 비즈니스 규칙(NORMALIZED_PROVIDER_BUSINESSRULES_0): dbo.GetInspItemsCd는 dbo.PEX_INSP_ITEMS를 대상으로 단일 조회 결과셋(3개 컬럼)을 반환하는 읽기 중심 프로시저로 해석됩니다.
- 비즈니스 규칙(NORMALIZED_PROVIDER_BUSINESSRULES_1): @InspItemsCd 파라미터가 정의되어 있으나, 정적 분석 근거상 WHERE 조건의 상수 패턴 사용으로 인해 실제 바인딩 의도 확인이 필요합니다.
- 비즈니스 규칙(DETERMINISTIC_SAFETY_NET_READ_ONLY_LOOKUP): 결정론적 fact가 읽기 전용 조회 동작을 보여 주며, 초안 비즈니스 맥락으로 검토해야 합니다.
- 현대화 포인트(DETERMINISTIC_SAFETY_NET_LOOKUP_DTO_SHAPE): 조회 입력과 result-shape fact는 Java/MyBatis 전환 전에 명시적인 DTO 필드로 매핑해야 합니다.
- 전환 가이드(MYBATIS_SINGLE_SELECT_BASELINE): Java/MyBatis 전환은 단일 select 매퍼와 String 입력 파라미터, 3필드 DTO 매핑을 기본안으로 시작하되 파라미터 실제 사용 규칙 확정이 선행되어야 합니다.
- 전환 가이드(NORMALIZED_PROVIDER_CONVERSIONGUIDANCE_0): MyBatis 단일 select 매퍼와 3개 필드 DTO 매핑을 기본안으로 시작하되, 최종 결과 매핑은 검증 후 확정하세요.
- 전환 가이드(NORMALIZED_PROVIDER_CONVERSIONGUIDANCE_1): @InspItemsCd의 WHERE 바인딩 의도를 먼저 확정한 뒤 Java 메서드 파라미터 계약을 고정하세요.
- 전환 가이드(JAVA_MYBATIS_BASELINE_SELECT): Java Service + MyBatis Mapper로 1개 select 매퍼를 우선 구성하고, DTO는 INSP_ITEMS_CD/INSP_ITEMS_NM/INSP_ITEMS_DESC 3개 필드를 기본안으로 두십시오.
- 전환 가이드(JAVA_MYBATIS_PARAMETER_POLICY): @InspItemsCd를 WHERE LIKE에 바인딩할지, 미사용 파라미터로 제거할지 업무 규칙을 먼저 확정한 뒤 Mapper 파라미터 타입(String)과 SQL 조건식을 고정하십시오.
- 전환 가이드(JAVA_MYBATIS_READONLY_CLASSIFICATION): 현재는 읽기 전용 조회 패턴으로 분류되지만 템플릿성 주석 흔적이 있어 향후 DML 유입 여부를 형상 이력으로 교차 검증하십시오.
- 전환 가이드(MYBATIS_BASELINE_MAPPING): MyBatis는 단일 select 매퍼와 String 파라미터(@InspItemsCd), 3개 필드 DTO 매핑을 기본안으로 시작하되 파라미터 사용 의도 확인 후 확정하는 것이 적절합니다.
- 전환 가이드(DETERMINISTIC_SAFETY_NET_LOOKUP_CONVERSION_GUIDANCE): 결정론적 DTO 계약이 검증될 때까지 조회 parameter binding과 결과 매핑은 근거 보강 필요로 유지합니다.
- 가이드 인사이트(overview): 프로시저 정의 접근 가능 및 비암호화 상태는 확인되었으나, 운영 의도(파라미터 활용/정렬/반환량)는 메타데이터만으로 확정할 수 없습니다. 다음 추출 항목=인터페이스 계약서에서 입력 파라미터 사용 규칙, 정렬 기준, 최대 반환 건수를 확인하세요.
- 가이드 인사이트(dependency_inventory): 동일 DB 내 dbo.PEX_INSP_ITEMS 단일 테이블 참조는 확인되었고, 추가 간접 의존성 존재 여부는 후속 검증이 필요합니다. 다음 추출 항목=뷰/함수/동적 SQL 경유 간접 참조 유무를 배포 산출물과 대조하세요.
- 가이드 인사이트(query-parameterization): 파라미터 정의와 실제 필터 반영 사이 의미 불일치 가능성이 있어 Java 메서드 시그니처 확정 전 검토가 필요합니다. 다음 추출 항목=LIKE 조건 바인딩 여부 또는 미사용 파라미터 제거 여부를 업무 규칙으로 확정하세요.
- 가이드 인사이트(result-mapping): 반환 컬럼 후보 3개는 식별되나 템플릿성 흔적이 있어 최종 SELECT/alias/타입 매핑 확정 전 재검증이 필요합니다. 다음 추출 항목=최종 SELECT 확정본 기준으로 컬럼 alias, Java 타입, nullable 정책을 추출하세요.
- 가이드 인사이트(call_flow): 분기/루프/트랜잭션/TRY-CATCH 없는 단순 조회 흐름으로 보이나, 호출자 후처리 존재 여부는 확인이 필요합니다. 다음 추출 항목=애플리케이션 호출부에서 본 프로시저 결과에 대한 후처리(필터/정렬/재가공) 유무를 확인하세요.
- 가이드 인사이트(migration_strategy): Java Service + MyBatis Mapper 직변환 후보이나 파라미터 활용 정책 확정이 선행되어야 합니다. 다음 추출 항목=요구사항 문서에서 검색 파라미터 필수 여부와 LIKE 매칭 정책을 확정하세요.
- 가이드 인사이트(dml_matrix): Confirmed: SELECT 기반 읽기 동작으로 분류됩니다. Needs verification: 템플릿성 주석 흔적이 있어 변경 이력에서 쓰기 연산 도입 여부를 확인할 필요가 있습니다. 다음 추출 항목=형상관리 이력에서 INSERT/UPDATE/DELETE 도입 기록 유무를 확인하세요.
- 가이드 인사이트(metadata_extraction_appendix): Confirmed: 객체/파라미터/의존성/컬럼 메타데이터가 확보되었습니다. Needs verification: extended properties가 비어 있어 도메인 설명 보강이 필요합니다. 다음 추출 항목=용어사전/테이블 명세에서 컬럼 의미와 값 도메인 설명을 추가 추출하세요.
- 가이드 인사이트(DETERMINISTIC_SAFETY_NET_LOOKUP_GUIDE): 마이그레이션 가이드는 조회 입력, 읽기 의존성, result-shape 검토 메모를 포함해야 합니다.
- 근거 caveat(AI_TOOL_PLANNER_DETERMINISTIC_FALLBACK): 도구 플래너 결과가 비어 결정론적 read-only fallback으로 수집되어, 해석 결과는 보수적으로 검토해야 합니다.
- 근거 caveat(LLM_OUTPUT_LANGUAGE_EVIDENCE_CAVEAT): 일부 사람이 읽는 자유 텍스트가 한국어가 아니어서 결과 검토가 필요합니다. JSON 키, enum/status/code, evidence ref 같은 기계 계약 식별자는 그대로 유지했습니다.
- 근거 caveat(SOURCE_CONTEXT_TRUNCATED): Source context was bounded to selected spans for model input.

## evidence_summary
- 저장 프로시저: `dbo.GetInspItemsCd` - COLLECTED
- 테이블: `dbo.PEX_INSP_ITEMS` - MSSQL MCP table schema metadata 근거입니다.
- 의존성 근거: `dbo.GetInspItemsCd` - MSSQL MCP dependency closure 근거입니다.
- 의존성 근거: `PEX_INSP_ITEMS` - MSSQL MCP dependency closure 근거입니다.
- 의존성 근거: `dbo.PEX_INSP_ITEMS` - MSSQL MCP dependency closure 근거입니다.
- LLM 추론: `3a0ef37e8c70b1fc8b496d9fd3352a820a1ca3c7ba6cb67d8d77d007eac44820` - 3a0ef37e8c70b1fc8b496d9fd3352a820a1ca3c7ba6cb67d8d77d007eac44820

## assumptions_and_todo
- TODO: 근거 보강 필요: metadata는 MSSQL MCP registry 경계를 통해 수집되며 이 integration slice에서는 platform DB workflow repository에 저장됩니다.
- TODO: 근거 보강 필요: LLM semantic analysis is inferred; treat it as an evidence caveat.
- TODO: Provider returned a structured assumption object; text was not stored.
- TODO: DETERMINISTIC_SAFETY_NET은 허용된 결정론적 fact id만 사용해 초안 claim을 추가했습니다.
- TODO: confirmed dependency procedure semantic outputs are draft-only evidence aids.
- TODO: transaction boundary 확인
- TODO: dynamic SQL/temp table 여부는 analysis engine 결과로 확정

## quality_summary
- evidence_included: true
- draft_only_boundary_marked: true
- business rules are draft caveats when not evidence-linked

## evidence_map
- 저장 프로시저: `dbo.GetInspItemsCd` - COLLECTED
- 테이블: `dbo.PEX_INSP_ITEMS` - MSSQL MCP table schema metadata 근거입니다.
- 의존성 근거: `dbo.GetInspItemsCd` - MSSQL MCP dependency closure 근거입니다.
- 의존성 근거: `PEX_INSP_ITEMS` - MSSQL MCP dependency closure 근거입니다.
- 의존성 근거: `dbo.PEX_INSP_ITEMS` - MSSQL MCP dependency closure 근거입니다.
- LLM 추론: `3a0ef37e8c70b1fc8b496d9fd3352a820a1ca3c7ba6cb67d8d77d007eac44820` - 3a0ef37e8c70b1fc8b496d9fd3352a820a1ca3c7ba6cb67d8d77d007eac44820

## known_caveats
- Evidence caveat items mean evidence needs to be strengthened.

## next_evidence_to_collect
- Confirm transaction boundary, branch conditions, DML targets, and call-flow depth.

## draft_readiness
- Ready as a draft analysis input; no execution or apply path is included.
