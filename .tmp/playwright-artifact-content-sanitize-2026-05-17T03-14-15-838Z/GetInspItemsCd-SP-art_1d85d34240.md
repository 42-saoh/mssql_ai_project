# GetInspItemsCd SP 분석 초안

## input_interpretation
- systemCode: PPM
- entityName: GetInspItemsCd
- spName: dbo.GetInspItemsCd
- tableName: dbo.PEX_INSP_ITEMS

## analysis_summary
- 상태: 초안(`DRAFT`)
- Evidence caveat: SP 내부 제어 흐름과 비즈니스 규칙은 canonical analysis 확정 후 보강
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
<!-- claim:claim_sp_overview status=EVIDENCE_CAVEAT evidenceRefs=ev_metadata_1 -->
- 판단: sp_overview section은 sanitized metadata/static fact를 근거로 렌더링됩니다. 상태=근거 보강 필요 근거=ev_metadata_1
| 항목 | 값 | 상태 | 근거 |
|---|---|---|---|
| 대상 SP | dbo.GetInspItemsCd | Confirmed | ev_metadata_1 |
| 메타데이터 프로필 | ppm | Confirmed | ev_metadata_1 |
| 입력 파라미터 수 | 1 | Confirmed | ev_metadata_1 |
| 결과 필드 후보 수 | 13 | Evidence caveat | static.analysis.migration_guide |

- targetRef: `dbo.GetInspItemsCd`
- fixtureId: `req_49c1be15cc`
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
<!-- claim:claim_feature_branch_taxonomy status=EVIDENCE_CAVEAT evidenceRefs=static.analysis.migration_guide -->
- 판단: feature_branch_taxonomy section은 sanitized metadata/static fact를 근거로 렌더링됩니다. 상태=근거 보강 필요 근거=static.analysis.migration_guide
| 기능/분기 | 조건/트리거 | 상태 | 요약 | 근거 |
|---|---|---|---|---|
| SELECT 영향 | static DML scan | Confirmed | PEX_INSP_ITEMS에 대한 SELECT 영향이 감지되었습니다. | static.dml.select.pex_insp_items |
| readOnlyLookup | LLM_INFERENCE_EVIDENCE_CAVEAT | Evidence caveat | 의존성은 동일 DB/스키마의 dbo.PEX_INSP_ITEMS 단일 테이블 참조로 수집되었습니다. | metadata:dbo.GetInspItemsCd:sys.sql_expression_dependencies, metadata:dbo.PEX_INSP_ITEMS:sys.objects,sys.schemas:referenced_id, metadata:dbo.GetInspItemsCd:sys.sql_modules, metadata:dbo.GetInspItemsCd:sys.sql_modules:hash-pattern, metadata:dbo.PEX_INSP_ITEMS:sys.columns, metadata:dbo.GetInspItemsCd:sys.parameters |
| overview | LLM_INFERENCE_EVIDENCE_CAVEAT | Evidence caveat | dbo.GetInspItemsCd는 단순 조회형 저장 프로시저로 분류되며, 동적 SQL/트랜잭션/예외처리 패턴 증거는 없습니다. | metadata:dbo.GetInspItemsCd:sys.objects, metadata:dbo.GetInspItemsCd:sys.sql_modules, metadata.procedureDefinitionHash |
| dependency_inventory | LLM_INFERENCE_EVIDENCE_CAVEAT | Evidence caveat | 확정 의존성은 동일 DB의 dbo.PEX_INSP_ITEMS 단일 테이블 참조입니다. | metadata:dbo.GetInspItemsCd:sys.sql_expression_dependencies, metadata:PEX_INSP_ITEMS:sys.sql_expression_dependencies, metadata:dbo.PEX_INSP_ITEMS:sys.objects,sys.schemas:referenced_id |
| dml_matrix | LLM_INFERENCE_EVIDENCE_CAVEAT | Evidence caveat | 실제 비즈니스 동작은 SELECT 기반 읽기입니다. 소스 주석성 문구로 인한 DML_WRITE 신호는 정합성 재검토가 필요합니다. | metadata:dbo.GetInspItemsCd:sys.sql_modules, metadata.procedureDefinitionHash |
| call_flow | LLM_INFERENCE_EVIDENCE_CAVEAT | Evidence caveat | 호출 흐름은 입력(@InspItemsCd) → 단일 SELECT → 결과 반환의 1단계 조회 플로우로 단순합니다. | metadata:dbo.GetInspItemsCd:sys.parameters, metadata:dbo.GetInspItemsCd:sys.sql_modules |
| risk_metrics | LLM_INFERENCE_EVIDENCE_CAVEAT | Evidence caveat | 복잡도는 낮지만 결과형상 계약 및 파라미터 사용 의도 불일치 가능성이 주요 검토 포인트입니다. | metadata:dbo.GetInspItemsCd:sys.parameters, metadata:dbo.GetInspItemsCd:sys.sql_modules, metadata.procedureDefinitionHash |
| metadata_extraction_appendix | LLM_INFERENCE_EVIDENCE_CAVEAT | Evidence caveat | 테이블 메타데이터상 PEX_INSP_ITEMS의 PK/클러스터드 유니크 인덱스는 INSP_ITEMS_CD이며, 반환 컬럼 3개는 모두 테이블 컬럼으로 매핑 가능합니다. | metadata:dbo.PEX_INSP_ITEMS:sys.columns, mcp.get_table_constraints.939285cd60b1, mcp.get_table_indexes.cade9cb3f984 |
| migration_strategy | LLM_INFERENCE_EVIDENCE_CAVEAT | Evidence caveat | 우선순위는 조회 SQL의 Java/MyBatis 직접 이관이며, 이후 파라미터 필터 의도 확정에 따라 메서드 분리 또는 조건 보강 전략을 적용합니다. | metadata:dbo.GetInspItemsCd:sys.parameters, metadata:dbo.GetInspItemsCd:sys.sql_modules, platform.list_registry_versions.37dfbec3eb7e, metadata:dbo.GetInspItemsCd:sys.objects |
| DETERMINISTIC_SAFETY_NET_LOOKUP_GUIDE | LLM_INFERENCE_EVIDENCE_CAVEAT | Evidence caveat | 마이그레이션 가이드는 조회 입력, 읽기 의존성, result-shape 확인 메모를 포함해야 합니다. | mcp.get_table_constraints.939285cd60b1, mcp.get_table_indexes.cade9cb3f984, mcp.get_extended_properties.51cd70011e11 |

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
<!-- claim:claim_dependency_inventory status=EVIDENCE_CAVEAT evidenceRefs=static.analysis.migration_guide -->
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
- llmMigrationGuideInsight: dependency_inventory status=INFERRED_DESCRIPTION evidenceRefs=metadata:dbo.GetInspItemsCd:sys.sql_expression_dependencies, metadata:PEX_INSP_ITEMS:sys.sql_expression_dependencies, metadata:dbo.PEX_INSP_ITEMS:sys.objects,sys.schemas:referenced_id summary=확정 의존성은 동일 DB의 dbo.PEX_INSP_ITEMS 단일 테이블 참조입니다. whatToExtractNext=None

<!-- section:dml_impact_matrix -->
## 4. DML 영향 매트릭스
<!-- section-title:DML 영향 매트릭스 -->
<!-- contract-title:DML 영향 매트릭스 -->
- 근거: static.analysis.migration_guide
<!-- claim:claim_dml_impact_matrix status=EVIDENCE_CAVEAT evidenceRefs=static.analysis.migration_guide -->
- 판단: dml_impact_matrix section은 sanitized metadata/static fact를 근거로 렌더링됩니다. 상태=근거 보강 필요 근거=static.analysis.migration_guide
| 테이블 | SELECT | INSERT | UPDATE | DELETE | MERGE | 키/조인/조건 요약 | 중요 컬럼/패턴 | 근거 |
|---|---|---|---|---|---|---|---|---|
| `PEX_INSP_ITEMS` | Y |  |  |  |  | Evidence caveat: predicate/key 추출은 추가 근거 확인이 필요합니다. | Evidence caveat: 중요 컬럼 패턴은 LLM 출력만으로 추론하지 않습니다. | static.dml.select.pex_insp_items |

| 작업 | 대상 | 단계 | 상태 | evidenceRefs | 영향 |
|---|---|---|---|---|---|
| SELECT | `PEX_INSP_ITEMS` | static_dml_scan | Confirmed | static.dml.select.pex_insp_items | PEX_INSP_ITEMS에 대한 SELECT 참조를 감지했습니다. |

<!-- section:call_flow -->
## 5. 분기 단위 호출 흐름
<!-- section-title:분기 단위 호출 흐름 -->
<!-- contract-title:분기 단위 호출 흐름 -->
- 근거: static.analysis.migration_guide
<!-- claim:claim_call_flow status=EVIDENCE_CAVEAT evidenceRefs=static.analysis.migration_guide -->
- 판단: call_flow section은 sanitized metadata/static fact를 근거로 렌더링됩니다. 상태=근거 보강 필요 근거=static.analysis.migration_guide
- 입력:
  - 메타데이터에서 확인한 procedure 파라미터입니다.
- 분기: branch_dml_1 phase=static_dml_scan evidenceRefs=static.dml.select.pex_insp_items 조건=PEX_INSP_ITEMS에 대한 SELECT 참조를 감지했습니다.
  - 동작: SELECT dependency=PEX_INSP_ITEMS evidenceRefs=static.dml.select.pex_insp_items
- 결과 / 출력:
  - 결과 shape 후보는 appendix mappings에 렌더링됩니다.
- 오류 처리: Evidence caveat: 정상/예외/resource cleanup 분기를 확인합니다.
- llmInsightBoundary: `LLM_INFERENCE_EVIDENCE_CAVEAT`
- llmMigrationGuideInsight: call_flow status=EVIDENCE_CAVEAT evidenceRefs=metadata:dbo.GetInspItemsCd:sys.parameters, metadata:dbo.GetInspItemsCd:sys.sql_modules summary=호출 흐름은 입력(@InspItemsCd) → 단일 SELECT → 결과 반환의 1단계 조회 플로우로 단순합니다. whatToExtractNext=None

<!-- section:critical_phase_analysis -->
## 6. 핵심 단계 분석
<!-- section-title:핵심 단계 분석 -->
<!-- contract-title:핵심 단계 분석 -->
- 근거: static.analysis.migration_guide
<!-- claim:claim_critical_phase_analysis status=EVIDENCE_CAVEAT evidenceRefs=static.analysis.migration_guide -->
- 판단: critical_phase_analysis section은 sanitized metadata/static fact를 근거로 렌더링됩니다. 상태=근거 보강 필요 근거=static.analysis.migration_guide
- branchCount: `1`
- dmlOperationCount: `1`
| Phase | 주요 읽기 | 주요 쓰기 | 위험/검토점 | 상태 | 근거 |
|---|---|---|---|---|---|
| static_dml_scan | PEX_INSP_ITEMS | Evidence caveat | NORMALIZED_PROVIDER_RISKFLAGS_0, NORMALIZED_PROVIDER_RISKFLAGS_1 | Confirmed | static.dml.select.pex_insp_items |
- Evidence caveat: 단계 순서와 트랜잭션 의미는 추가 근거 확인이 필요합니다.

<!-- section:complexity_risk_metrics -->
## 7. 복잡도 및 위험 지표
<!-- section-title:복잡도 및 위험 지표 -->
<!-- contract-title:복잡도 및 위험 지표 -->
- 근거: static.analysis.migration_guide
<!-- claim:claim_complexity_risk_metrics status=EVIDENCE_CAVEAT evidenceRefs=static.analysis.migration_guide -->
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
- risk: NORMALIZED_PROVIDER_RISKFLAGS_0 status=EVIDENCE_CAVEAT severity=WARNING evidenceRefs=metadata:dbo.GetInspItemsCd:sys.sql_modules, metadata:dbo.GetInspItemsCd:sys.sql_modules:hash-pattern, metadata:dbo.PEX_INSP_ITEMS:sys.columns, metadata:dbo.GetInspItemsCd:sys.parameters, metadata.procedureDefinitionHash
- risk: NORMALIZED_PROVIDER_RISKFLAGS_1 status=EVIDENCE_CAVEAT severity=WARNING evidenceRefs=metadata:dbo.GetInspItemsCd:sys.parameters, metadata:dbo.GetInspItemsCd:sys.sql_modules, metadata:dbo.GetInspItemsCd:sys.sql_modules:hash-pattern, metadata:dbo.PEX_INSP_ITEMS:sys.columns

<!-- section:migration_strategy -->
## 8. 전환 전략 및 Java/MyBatis 초안 준비도
<!-- section-title:전환 전략 및 Java/MyBatis 초안 준비도 -->
<!-- contract-title:전환 전략 및 Java/MyBatis 초안 준비도 -->
- 근거: static.analysis.migration_guide
<!-- claim:claim_migration_strategy status=EVIDENCE_CAVEAT evidenceRefs=static.analysis.migration_guide -->
- 판단: migration_strategy section은 sanitized metadata/static fact를 근거로 렌더링됩니다. 상태=근거 보강 필요 근거=static.analysis.migration_guide
- javaMyBatisReadiness: `draft_notes_only`
- generated_source_application: `not_performed`
- automatic_conversion_completion: `not_claimed`
- target_application_write: `not_performed`
- Evidence caveat: Java/MyBatis 초안에는 근거 보강과 위험 caveat가 남아 있습니다.
- llmInsightBoundary: `LLM_INFERENCE_EVIDENCE_CAVEAT`
- llmConversionGuidance: NORMALIZED_PROVIDER_CONVERSIONGUIDANCE_0 status=EVIDENCE_CAVEAT evidenceRefs=metadata:dbo.GetInspItemsCd:sys.sql_modules, mcp.get_table_constraints.939285cd60b1, mcp.get_table_indexes.cade9cb3f984, metadata:dbo.PEX_INSP_ITEMS:sys.columns, metadata.procedureDefinitionHash summary=Java/MyBatis 변환 시 단일 SELECT 조회로 매핑하고, 결과 컬럼(INSP_ITEMS_CD, INSP_ITEMS_NM, INSP_ITEMS_DESC) 기준의 전용 DTO를 우선 설계합니다.
- llmConversionGuidance: NORMALIZED_PROVIDER_CONVERSIONGUIDANCE_1 status=EVIDENCE_CAVEAT evidenceRefs=mcp.get_table_constraints.939285cd60b1, mcp.get_table_indexes.cade9cb3f984, metadata:dbo.GetInspItemsCd:sys.parameters, metadata:dbo.GetInspItemsCd:sys.sql_modules, metadata:dbo.PEX_INSP_ITEMS:sys.objects,sys.schemas:referenced_id summary=PEX_INSP_ITEMS_PK(클러스터드, 유니크, 키 INSP_ITEMS_CD) 인덱스/PK 메타데이터를 기준으로 조건절 및 바인딩 설계를 단순화할 수 있습니다.
- llmConversionGuidance: NORMALIZED_PROVIDER_CONVERSIONGUIDANCE_2 status=EVIDENCE_CAVEAT evidenceRefs=mcp.get_table_indexes.cade9cb3f984, mcp.get_table_constraints.939285cd60b1, platform.list_registry_versions.37dfbec3eb7e, metadata:dbo.GetInspItemsCd:sys.objects summary=PEX_INSP_ITEMS_PK(클러스터드 PK, INSP_ITEMS_CD) 인덱스 특성을 고려해 접두 검색/정확 검색 전략을 분리 설계하면 성능 안정성에 유리합니다.
- llmConversionGuidance: DETERMINISTIC_SAFETY_NET_LOOKUP_CONVERSION_GUIDANCE status=EVIDENCE_CAVEAT evidenceRefs=mcp.get_table_constraints.939285cd60b1, mcp.get_table_indexes.cade9cb3f984, mcp.get_extended_properties.51cd70011e11 summary=결정론적 DTO 계약이 검증될 때까지 조회 parameter binding과 결과 매핑은 Evidence caveat로 유지합니다.
- llmInsightBoundary: `LLM_INFERENCE_EVIDENCE_CAVEAT`
- llmMigrationGuideInsight: migration_strategy status=EVIDENCE_CAVEAT evidenceRefs=metadata:dbo.GetInspItemsCd:sys.parameters, metadata:dbo.GetInspItemsCd:sys.sql_modules, platform.list_registry_versions.37dfbec3eb7e, metadata:dbo.GetInspItemsCd:sys.objects summary=우선순위는 조회 SQL의 Java/MyBatis 직접 이관이며, 이후 파라미터 필터 의도 확정에 따라 메서드 분리 또는 조건 보강 전략을 적용합니다. whatToExtractNext=현업 검색 시나리오(정확일치/부분일치/전체조회)와 서비스 계층 반환 DTO 계약을 수집해 Mapper 인터페이스 시그니처 확정

<!-- section:appendix_mappings -->
## 9. 파라미터 및 코드 매핑 부록
<!-- section-title:파라미터 및 코드 매핑 부록 -->
<!-- contract-title:파라미터 및 코드 매핑 부록 -->
- 근거: ev_metadata_1
<!-- claim:claim_appendix_mappings status=EVIDENCE_CAVEAT evidenceRefs=ev_metadata_1 -->
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
<!-- claim:claim_metadata_extraction_appendix status=EVIDENCE_CAVEAT evidenceRefs=static.analysis.migration_guide -->
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
- llmMigrationGuideInsight: metadata_extraction_appendix status=INFERRED_DESCRIPTION evidenceRefs=metadata:dbo.PEX_INSP_ITEMS:sys.columns, mcp.get_table_constraints.939285cd60b1, mcp.get_table_indexes.cade9cb3f984 summary=테이블 메타데이터상 PEX_INSP_ITEMS의 PK/클러스터드 유니크 인덱스는 INSP_ITEMS_CD이며, 반환 컬럼 3개는 모두 테이블 컬럼으로 매핑 가능합니다. whatToExtractNext=None

<!-- section:evidence_assumptions_review -->
## 11. 근거, 가정, 품질 caveat
<!-- section-title:근거, 가정, 품질 caveat -->
<!-- contract-title:근거, 가정, 품질 caveat -->
- 근거: static.analysis.migration_guide
<!-- claim:claim_evidence_assumptions_review status=EVIDENCE_CAVEAT evidenceRefs=static.analysis.migration_guide -->
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
  - claimCode=NORMALIZED_PROVIDER_RISKFLAGS_0 claimType=risk status=EVIDENCE_CAVEAT obligation=low_evidence_business_rule_claims evidenceRefs=metadata:dbo.GetInspItemsCd:sys.sql_modules, metadata:dbo.GetInspItemsCd:sys.sql_modules:hash-pattern, metadata:dbo.PEX_INSP_ITEMS:sys.columns, metadata:dbo.GetInspItemsCd:sys.parameters, metadata.procedureDefinitionHash
  - claimCode=NORMALIZED_PROVIDER_RISKFLAGS_1 claimType=risk status=EVIDENCE_CAVEAT obligation=low_evidence_business_rule_claims evidenceRefs=metadata:dbo.GetInspItemsCd:sys.parameters, metadata:dbo.GetInspItemsCd:sys.sql_modules, metadata:dbo.GetInspItemsCd:sys.sql_modules:hash-pattern, metadata:dbo.PEX_INSP_ITEMS:sys.columns
- 가정: Evidence caveat Evidence caveat: metadata는 MSSQL MCP registry 경계를 통해 수집되며 이 integration slice에서는 platform DB workflow repository에 저장됩니다.
- 가정: Evidence caveat Evidence caveat: LLM semantic analysis is inferred and remains a validation caveat.
- 가정: Evidence caveat Provider returned a structured assumption object; text was not stored.
- 가정: Evidence caveat DETERMINISTIC_SAFETY_NET은 허용된 결정론적 fact id만 사용해 초안 claim을 추가했습니다.
- 가정: Evidence caveat confirmed dependency procedure semantic outputs are draft-only evidence aids.

## quality_summary
- status: draft-quality evidence caveats tracked
- raw SQL text, row data, secrets, execution output은 포함하지 않습니다.

## evidence_map
- claims are tied to evidenceRefs or Evidence caveat caveats.

## known_caveats
- Evidence caveat는 근거 보강 필요 상태를 의미합니다.

## next_evidence_to_collect
- DML matrix, branch call-flow, transaction boundary, Java/MyBatis mapping evidence를 보강합니다.

## draft_readiness
- Ready as a migration-guide draft; no publish, deploy, DDL, DML, or source apply path is included.

## llm_semantic_analysis
- 상태: 근거 보강 필요(`Evidence caveat`)
- 비즈니스 규칙(NORMALIZED_PROVIDER_BUSINESSRULES_0): dbo.GetInspItemsCd는 입력 파라미터 @InspItemsCd를 가지며, PEX_INSP_ITEMS에서 INSP_ITEMS_CD, INSP_ITEMS_NM, INSP_ITEMS_DESC를 조회하는 읽기 중심 조회 프로시저로 해석됩니다.
- 비즈니스 규칙(NORMALIZED_PROVIDER_BUSINESSRULES_1): 입력 파라미터는 @InspItemsCd 1개(varchar)로 정의되어 있으나, 정적 분석 기준 실제 WHERE 조건 반영 여부는 추가 검증이 필요합니다.
- 비즈니스 규칙(NORMALIZED_PROVIDER_BUSINESSRULES_2): 결과셋은 INSP_ITEMS_CD, INSP_ITEMS_NM, INSP_ITEMS_DESC 3개 컬럼으로 추정되며, 별칭/타입 매핑 계약은 명시 확인이 필요합니다.
- 비즈니스 규칙(DETERMINISTIC_SAFETY_NET_READ_ONLY_LOOKUP): 결정론적 fact가 읽기 전용 조회 동작을 보여 주며, 초안 비즈니스 맥락으로 검토해야 합니다.
- 현대화 포인트(NORMALIZED_PROVIDER_MODERNIZATIONPOINTS_0): Java/MyBatis 변환 시 @InspItemsCd 미사용 가능성을 우선 점검하고, 실제 요구사항이 접두/부분검색이면 MyBatis 바인딩(예: CONCAT 또는 사전 가공)으로 명확히 고정하는 보완이 필요합니다.
- 현대화 포인트(DETERMINISTIC_SAFETY_NET_LOOKUP_DTO_SHAPE): 조회 입력과 result-shape fact는 Java/MyBatis 전환 전에 명시적인 DTO 필드로 매핑해야 합니다.
- 전환 가이드(NORMALIZED_PROVIDER_CONVERSIONGUIDANCE_0): Java/MyBatis 변환 시 단일 SELECT 조회로 매핑하고, 결과 컬럼(INSP_ITEMS_CD, INSP_ITEMS_NM, INSP_ITEMS_DESC) 기준의 전용 DTO를 우선 설계합니다.
- 전환 가이드(NORMALIZED_PROVIDER_CONVERSIONGUIDANCE_1): PEX_INSP_ITEMS_PK(클러스터드, 유니크, 키 INSP_ITEMS_CD) 인덱스/PK 메타데이터를 기준으로 조건절 및 바인딩 설계를 단순화할 수 있습니다.
- 전환 가이드(NORMALIZED_PROVIDER_CONVERSIONGUIDANCE_2): PEX_INSP_ITEMS_PK(클러스터드 PK, INSP_ITEMS_CD) 인덱스 특성을 고려해 접두 검색/정확 검색 전략을 분리 설계하면 성능 안정성에 유리합니다.
- 전환 가이드(DETERMINISTIC_SAFETY_NET_LOOKUP_CONVERSION_GUIDANCE): 결정론적 DTO 계약이 검증될 때까지 조회 parameter binding과 결과 매핑은 Evidence caveat로 유지합니다.
- 가이드 인사이트(readOnlyLookup): 의존성은 동일 DB/스키마의 dbo.PEX_INSP_ITEMS 단일 테이블 참조로 수집되었습니다.
- 가이드 인사이트(overview): dbo.GetInspItemsCd는 단순 조회형 저장 프로시저로 분류되며, 동적 SQL/트랜잭션/예외처리 패턴 증거는 없습니다.
- 가이드 인사이트(dependency_inventory): 확정 의존성은 동일 DB의 dbo.PEX_INSP_ITEMS 단일 테이블 참조입니다.
- 가이드 인사이트(dml_matrix): 실제 비즈니스 동작은 SELECT 기반 읽기입니다. 소스 주석성 문구로 인한 DML_WRITE 신호는 정합성 재검토가 필요합니다. 다음 추출 항목=주석 라인과 실행 SQL 라인을 분리해 쓰기 연산 존재 여부를 재판별하고, 최종 DML 매트릭스를 SELECT only로 확정할지 검토
- 가이드 인사이트(call_flow): 호출 흐름은 입력(@InspItemsCd) → 단일 SELECT → 결과 반환의 1단계 조회 플로우로 단순합니다.
- 가이드 인사이트(risk_metrics): 복잡도는 낮지만 결과형상 계약 및 파라미터 사용 의도 불일치 가능성이 주요 검토 포인트입니다. 다음 추출 항목=실사용 호출부 기준 기대 결과 건수/정렬/널 처리 규칙과 @InspItemsCd 검색 규칙 명세 확보
- 가이드 인사이트(metadata_extraction_appendix): 테이블 메타데이터상 PEX_INSP_ITEMS의 PK/클러스터드 유니크 인덱스는 INSP_ITEMS_CD이며, 반환 컬럼 3개는 모두 테이블 컬럼으로 매핑 가능합니다.
- 가이드 인사이트(migration_strategy): 우선순위는 조회 SQL의 Java/MyBatis 직접 이관이며, 이후 파라미터 필터 의도 확정에 따라 메서드 분리 또는 조건 보강 전략을 적용합니다. 다음 추출 항목=현업 검색 시나리오(정확일치/부분일치/전체조회)와 서비스 계층 반환 DTO 계약을 수집해 Mapper 인터페이스 시그니처 확정
- 가이드 인사이트(DETERMINISTIC_SAFETY_NET_LOOKUP_GUIDE): 마이그레이션 가이드는 조회 입력, 읽기 의존성, result-shape 확인 메모를 포함해야 합니다.
- 근거 caveat(NORMALIZED_PROVIDER_REVIEWMARKERS_0): MyBatis XML에서 @InspItemsCd 파라미터가 WHERE 절에 정확히 반영되는지 확인이 필요합니다.
- 근거 caveat(LLM_OUTPUT_LANGUAGE_EVIDENCE_CAVEAT): 일부 사람이 읽는 자유 텍스트가 한국어가 아니어서 근거 보강이 필요합니다. JSON 키, enum/status/code, evidence ref 같은 기계 계약 식별자는 그대로 유지했습니다.
- 근거 caveat(SOURCE_CONTEXT_TRUNCATED): Source context was bounded to selected spans for model input.

## evidence_summary
- 저장 프로시저: `dbo.GetInspItemsCd` - COLLECTED
- 테이블: `dbo.PEX_INSP_ITEMS` - MSSQL MCP table schema metadata 근거입니다.
- 의존성 근거: `dbo.GetInspItemsCd` - MSSQL MCP dependency closure 근거입니다.
- 의존성 근거: `PEX_INSP_ITEMS` - MSSQL MCP dependency closure 근거입니다.
- 의존성 근거: `dbo.PEX_INSP_ITEMS` - MSSQL MCP dependency closure 근거입니다.
- LLM 추론: `08f27991bf806a818ce0f658943ccedc1e2580458b22baaf3a5d297e7b2676bd` - 08f27991bf806a818ce0f658943ccedc1e2580458b22baaf3a5d297e7b2676bd

## assumptions_and_todo
- TODO: Evidence caveat: metadata는 MSSQL MCP registry 경계를 통해 수집되며 이 integration slice에서는 platform DB workflow repository에 저장됩니다.
- TODO: Evidence caveat: LLM semantic analysis is inferred and remains a validation caveat.
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
- LLM 추론: `08f27991bf806a818ce0f658943ccedc1e2580458b22baaf3a5d297e7b2676bd` - 08f27991bf806a818ce0f658943ccedc1e2580458b22baaf3a5d297e7b2676bd

## known_caveats
- Evidence caveat items mean evidence needs to be strengthened.

## next_evidence_to_collect
- Confirm transaction boundary, branch conditions, DML targets, and call-flow depth.

## draft_readiness
- Ready as a draft analysis input; no execution or apply path is included.
