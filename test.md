# GetInspItemsCd SP 분석 초안

## input_interpretation
- systemCode: PPM
- entityName: GetInspItemsCd
- spName: dbo.GetInspItemsCd
- tableName: dbo.PEX_INSP_ITEMS

## analysis_summary
- 상태: 초안(`DRAFT`)
- REVIEW_REQUIRED: SP 내부 제어 흐름과 비즈니스 규칙은 canonical analysis 확정 후 보강
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

## sp_overview
- title: SP 개요 및 기본 정보
- evidenceRefs: ev_metadata_1
- claim: claim_sp_overview status=REVIEW_REQUIRED evidenceRefs=ev_metadata_1 요약=sp_overview section은 sanitized metadata/static fact를 근거로 렌더링됩니다.
- targetRef: `dbo.GetInspItemsCd`
- fixtureId: `req_154ca72df9`
- status: DRAFT
- productionReady: `false`
- artifactsUnderTest: SP_ANALYSIS_DOC, DEPENDENCY_REPORT
- metadataProfileId: `ppm`
- targetDb: `PPM`
- platformDb: `PLF`
- plfFallback: `forbidden`

## feature_branch_taxonomy
- title: 주요 기능과 분기/플래그 분류
- evidenceRefs: static.analysis.migration_guide
- claim: claim_feature_branch_taxonomy status=REVIEW_REQUIRED evidenceRefs=static.analysis.migration_guide 요약=feature_branch_taxonomy section은 sanitized metadata/static fact를 근거로 렌더링됩니다.
- fact: fact_target_identity type=PROCEDURE_IDENTITY evidenceRefs=ev_metadata_1 요약=전환 가이드 대상은 dbo.GetInspItemsCd입니다.
- fact: fact_parameter_inventory type=PROCEDURE_PARAMETERS evidenceRefs=ev_metadata_1 요약=메타데이터에서 파라미터 1개를 확인했습니다.
- fact: fact_result_shape type=RESULT_SHAPE evidenceRefs=static.analysis.migration_guide 요약=결과 필드 후보 13개를 사용할 수 있습니다.

## dependency_inventory
- title: 의존성 목록
- evidenceRefs: static.analysis.migration_guide
- claim: claim_dependency_inventory status=REVIEW_REQUIRED evidenceRefs=static.analysis.migration_guide 요약=dependency_inventory section은 sanitized metadata/static fact를 근거로 렌더링됩니다.
### 확인됨
| 유형 | 이름 | 참조 방식 | 근거 | 비고 |
|---|---|---|---|---|
| reference | `|PPM|dbo|PEX_INSP_ITEMS|TABLE` | REFERENCED_ID | PEX_INSP_ITEMS, dbo.PEX_INSP_ITEMS | REFERENCED_ID CATALOG_OBJECT_ID |
| table | `PEX_INSP_ITEMS` | static parser | static.analysis.migration_guide | 정적 parser에서 확인한 참조입니다.  |

### 검증 필요
| 유형 | 이름/후보 | 불확실한 이유 | 다음 추출 항목 | 비고 |
|---|---|---|---|---|
| 없음 | 없음 | 없음 | 없음 | 검토 필요한 의존성 후보가 없습니다. |

## dml_impact_matrix
- title: DML 영향 매트릭스
- evidenceRefs: static.analysis.migration_guide
- claim: claim_dml_impact_matrix status=REVIEW_REQUIRED evidenceRefs=static.analysis.migration_guide 요약=dml_impact_matrix section은 sanitized metadata/static fact를 근거로 렌더링됩니다.
| 테이블 | SELECT | INSERT | UPDATE | DELETE | MERGE | 키/조인/조건 요약 | 중요 컬럼/패턴 | 근거 |
|---|---|---|---|---|---|---|---|---|
| `PEX_INSP_ITEMS` | Y |  |  |  |  | REVIEW_REQUIRED: predicate/key 추출은 검토자 확인이 필요합니다. | REVIEW_REQUIRED: 중요 컬럼 패턴은 LLM 출력만으로 추론하지 않습니다. | static.dml.select.pex_insp_items |

| 작업 | 대상 | 단계 | 상태 | evidenceRefs | 영향 |
|---|---|---|---|---|---|
| SELECT | `PEX_INSP_ITEMS` | static_dml_scan | Confirmed | static.dml.select.pex_insp_items | PEX_INSP_ITEMS에 대한 SELECT 참조를 감지했습니다. |

## call_flow
- title: 분기 단위 호출 흐름
- evidenceRefs: static.analysis.migration_guide
- claim: claim_call_flow status=REVIEW_REQUIRED evidenceRefs=static.analysis.migration_guide 요약=call_flow section은 sanitized metadata/static fact를 근거로 렌더링됩니다.
- 입력:
  - 메타데이터에서 확인한 procedure 파라미터입니다.
- 분기: branch_dml_1 phase=static_dml_scan evidenceRefs=static.dml.select.pex_insp_items 조건=PEX_INSP_ITEMS에 대한 SELECT 참조를 감지했습니다.
  - 동작: SELECT dependency=PEX_INSP_ITEMS evidenceRefs=static.dml.select.pex_insp_items
- 결과 / 출력:
  - 결과 shape 후보는 appendix mappings에 렌더링됩니다.
- 오류 처리: REVIEW_REQUIRED: 정상/예외/resource cleanup 분기를 확인합니다.

## critical_phase_analysis
- title: 핵심 단계 분석
- evidenceRefs: static.analysis.migration_guide
- claim: claim_critical_phase_analysis status=REVIEW_REQUIRED evidenceRefs=static.analysis.migration_guide 요약=critical_phase_analysis section은 sanitized metadata/static fact를 근거로 렌더링됩니다.
- branchCount: `1`
- dmlOperationCount: `1`
- REVIEW_REQUIRED: 단계 순서와 트랜잭션 의미는 검토자 확인이 필요합니다.

## complexity_risk_metrics
- title: 복잡도 및 위험 지표
- evidenceRefs: static.analysis.migration_guide
- claim: claim_complexity_risk_metrics status=REVIEW_REQUIRED evidenceRefs=static.analysis.migration_guide 요약=complexity_risk_metrics section은 sanitized metadata/static fact를 근거로 렌더링됩니다.
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
- risk: NORMALIZED_PROVIDER_RISKFLAGS_0 status=REVIEW_REQUIRED severity=WARNING evidenceRefs=metadata:dbo.GetInspItemsCd:sys.parameters, metadata:dbo.GetInspItemsCd:sys.sql_modules, platform.search_knowledge_facts.09e85e30508c

## migration_strategy
- title: 전환 전략 및 Java/MyBatis 초안 준비도
- evidenceRefs: static.analysis.migration_guide
- claim: claim_migration_strategy status=REVIEW_REQUIRED evidenceRefs=static.analysis.migration_guide 요약=migration_strategy section은 sanitized metadata/static fact를 근거로 렌더링됩니다.
- javaMyBatisReadiness: `draft_notes_only`
- generated_source_application: `not_performed`
- automatic_conversion_completion: `not_claimed`
- target_application_write: `forbidden_without_human_review`
- REVIEW_REQUIRED: Java/MyBatis 적용 전 근거와 위험을 수동 검토해야 합니다.
- llmInsightBoundary: `LLM_INFERENCE_REVIEW_REQUIRED`
- llmConversionGuidance: NORMALIZED_PROVIDER_CONVERSIONGUIDANCE_0 status=REVIEW_REQUIRED evidenceRefs=metadata:dbo.GetInspItemsCd:sys.sql_modules, metadata:dbo.PEX_INSP_ITEMS:sys.columns, metadata:dbo.GetInspItemsCd:sys.sql_expression_dependencies, metadata:dbo.GetInspItemsCd:sys.parameters summary=MyBatis 단일 SELECT 매퍼로 우선 전환하고 결과 컬럼은 INSP_ITEMS_CD, INSP_ITEMS_NM, INSP_ITEMS_DESC에 매핑하는 구성이 적합합니다.
- llmConversionGuidance: NORMALIZED_PROVIDER_CONVERSIONGUIDANCE_1 status=REVIEW_REQUIRED evidenceRefs=metadata:dbo.GetInspItemsCd:sys.parameters, metadata:dbo.GetInspItemsCd:sys.sql_modules summary=@InspItemsCd를 LIKE 조건에 반영할지 또는 API/Mapper에서 제거할지 업무 규칙 확인 후 최종 SQL과 메서드 시그니처를 확정해야 합니다.
- llmConversionGuidance: DETERMINISTIC_SAFETY_NET_LOOKUP_CONVERSION_GUIDANCE status=REVIEW_REQUIRED evidenceRefs=mcp.get_table_constraints.939285cd60b1, mcp.get_table_indexes.cade9cb3f984, mcp.get_extended_properties.51cd70011e11 summary=결정론적 DTO 계약이 검증될 때까지 조회 parameter binding과 결과 매핑은 REVIEW_REQUIRED로 유지합니다.
- llmMigrationGuideInsight: readOnlyLookup status=REVIEW_REQUIRED evidenceRefs=metadata:dbo.GetInspItemsCd:sys.sql_modules, metadata:dbo.PEX_INSP_ITEMS:sys.columns, metadata.procedureDefinitionHash, metadata:dbo.GetInspItemsCd:sys.parameters, metadata:dbo.GetInspItemsCd:sys.sql_expression_dependencies, metadata:dbo.PEX_INSP_ITEMS:sys.objects,sys.schemas:referenced_id, metadata:dbo.GetInspItemsCd:sys.sql_modules:hash-pattern summary=정적 메타데이터 기준으로 단일 result set과 3개 컬럼 매핑 구조입니다. whatToExtractNext=Java DTO 필드명/타입 규칙과 ResultMap 네이밍 규칙을 수집해 매핑 계약을 확정합니다.
- llmMigrationGuideInsight: parameterHandling status=REVIEW_REQUIRED evidenceRefs=metadata:dbo.GetInspItemsCd:sys.parameters, metadata:dbo.GetInspItemsCd:sys.sql_modules, platform.search_knowledge_facts.09e85e30508c summary=정의된 입력 파라미터와 조회 필터의 결합 의도를 변환 전에 확정해야 합니다. whatToExtractNext=호출 서비스/화면의 검색 요구사항을 기준으로 @InspItemsCd의 동일일치/부분일치/전체조회 의도를 확인합니다.
- llmMigrationGuideInsight: dependencyScope status=INFERRED_DESCRIPTION evidenceRefs=metadata:dbo.GetInspItemsCd:sys.sql_expression_dependencies, metadata:dbo.PEX_INSP_ITEMS:sys.objects,sys.schemas:referenced_id, metadata:PEX_INSP_ITEMS:sys.sql_expression_dependencies summary=현재 확인된 정적 의존성은 SAME_DATABASE 내 dbo.PEX_INSP_ITEMS 단일 테이블 참조입니다. whatToExtractNext=None
- llmMigrationGuideInsight: resultMapping status=INFERRED_DESCRIPTION evidenceRefs=metadata:dbo.GetInspItemsCd:sys.sql_modules, metadata:dbo.PEX_INSP_ITEMS:sys.columns summary=결과셋 1개와 3개 컬럼 중심의 고정 스키마 매핑 구조로 정리 가능합니다. whatToExtractNext=None
- llmMigrationGuideInsight: NORMALIZED_PROVIDER_MIGRATIONGUIDEINSIGHTS_0 status=INFERRED_DESCRIPTION evidenceRefs=metadata:dbo.GetInspItemsCd:sys.objects, metadata:dbo.GetInspItemsCd:sys.sql_modules, metadata:dbo.GetInspItemsCd:sys.parameters summary=개요: 단일 테이블 조회 중심의 단순 read-only 프로시저입니다. Needs verification: @InspItemsCd 사용 의도 확인이 필요합니다. whatToExtractNext=호출 서비스/화면/API의 검색 조건 정의를 수집해 @InspItemsCd의 실제 사용 정책(미사용 유지/부분일치/정확일치)을 확정합니다.
- llmMigrationGuideInsight: NORMALIZED_PROVIDER_MIGRATIONGUIDEINSIGHTS_1 status=INFERRED_DESCRIPTION evidenceRefs=metadata:dbo.GetInspItemsCd:sys.sql_expression_dependencies, metadata:dbo.PEX_INSP_ITEMS:sys.objects,sys.schemas:referenced_id summary=의존성 인벤토리: SAME_DATABASE 범위에서 dbo.PEX_INSP_ITEMS 단일 테이블 의존성이 확인되었습니다. whatToExtractNext=None
- llmMigrationGuideInsight: NORMALIZED_PROVIDER_MIGRATIONGUIDEINSIGHTS_3 status=INFERRED_DESCRIPTION evidenceRefs=metadata:dbo.GetInspItemsCd:sys.sql_expression_dependencies, metadata:dbo.GetInspItemsCd:sys.sql_modules summary=호출 흐름: 내부 프로시저/함수 호출 없이 단일 SELECT 흐름으로 파악됩니다. whatToExtractNext=None
- llmMigrationGuideInsight: NORMALIZED_PROVIDER_MIGRATIONGUIDEINSIGHTS_4 status=REVIEW_REQUIRED evidenceRefs=metadata:dbo.GetInspItemsCd:sys.parameters, metadata:dbo.GetInspItemsCd:sys.sql_modules summary=리스크 메트릭: 구조 복잡도는 낮지만 파라미터-필터 정합성 불확실성으로 검토가 필요합니다. whatToExtractNext=기존 애플리케이션 호출부에서 @InspItemsCd 전달값 사용 경로를 추적해 요구사항 불일치 여부를 확인합니다.
- llmMigrationGuideInsight: NORMALIZED_PROVIDER_MIGRATIONGUIDEINSIGHTS_5 status=INFERRED_DESCRIPTION evidenceRefs=mcp.get_table_constraints.939285cd60b1, mcp.get_table_indexes.cade9cb3f984, metadata:dbo.PEX_INSP_ITEMS:sys.columns summary=메타데이터 추출 부록: PK/클러스터드 유니크 인덱스가 INSP_ITEMS_CD 기준으로 확인되어 DTO 키 매핑 기준으로 활용 가능합니다. whatToExtractNext=None
- llmMigrationGuideInsight: NORMALIZED_PROVIDER_MIGRATIONGUIDEINSIGHTS_6 status=REVIEW_REQUIRED evidenceRefs=metadata:dbo.GetInspItemsCd:sys.parameters, metadata:dbo.GetInspItemsCd:sys.sql_modules, platform.list_registry_versions.cdc0fe95b4ff summary=마이그레이션 전략: read-only Mapper 우선 전환 후 파라미터 유지/제거 정책을 검증 단계에서 확정하는 접근이 적합합니다. whatToExtractNext=서비스 메서드 시그니처와 API 계약을 수집해 MyBatis 파라미터 객체 및 SQL 바인딩 정책을 확정합니다.
- llmMigrationGuideInsight: DETERMINISTIC_SAFETY_NET_LOOKUP_GUIDE status=REVIEW_REQUIRED evidenceRefs=mcp.get_table_constraints.939285cd60b1, mcp.get_table_indexes.cade9cb3f984, mcp.get_extended_properties.51cd70011e11 summary=마이그레이션 가이드는 조회 입력, 읽기 의존성, result-shape 검토 메모를 포함해야 합니다. whatToExtractNext=None

## appendix_mappings
- title: 파라미터 및 코드 매핑 부록
- evidenceRefs: ev_metadata_1
- claim: claim_appendix_mappings status=REVIEW_REQUIRED evidenceRefs=ev_metadata_1 요약=appendix_mappings section은 sanitized metadata/static fact를 근거로 렌더링됩니다.
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

## metadata_extraction_appendix
- title: 수동 메타데이터 추출 부록
- evidenceRefs: static.analysis.migration_guide
- claim: claim_metadata_extraction_appendix status=REVIEW_REQUIRED evidenceRefs=static.analysis.migration_guide 요약=metadata_extraction_appendix section은 sanitized metadata/static fact를 근거로 렌더링됩니다.
- 정책: 수동 검토자 보조용입니다. 원천 메타데이터 DB에 대해 SSMS에서 실행하되, procedure 실행, row data 조회, DDL/DML 적용, raw definition 붙여넣기는 금지합니다.
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

## evidence_assumptions_review
- title: 근거, 가정, REVIEW_REQUIRED 마커
- evidenceRefs: static.analysis.migration_guide
- claim: claim_evidence_assumptions_review status=REVIEW_REQUIRED evidenceRefs=static.analysis.migration_guide 요약=evidence_assumptions_review section은 sanitized metadata/static fact를 근거로 렌더링됩니다.
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
- reviewRequiredFindings:
  - claimCode=NORMALIZED_PROVIDER_RISKFLAGS_0 claimType=risk status=REVIEW_REQUIRED obligation=low_evidence_business_rule_claims evidenceRefs=metadata:dbo.GetInspItemsCd:sys.parameters, metadata:dbo.GetInspItemsCd:sys.sql_modules, platform.search_knowledge_facts.09e85e30508c
- 가정: REVIEW_REQUIRED REVIEW_REQUIRED: metadata는 MSSQL MCP registry 경계를 통해 수집되며 이 integration slice에서는 platform DB workflow repository에 저장됩니다.
- 가정: REVIEW_REQUIRED REVIEW_REQUIRED: LLM semantic analysis is inferred and remains a validation caveat.
- 가정: REVIEW_REQUIRED Provider returned a structured assumption object; text was not stored.
- 가정: REVIEW_REQUIRED DETERMINISTIC_SAFETY_NET은 허용된 결정론적 fact id만 사용해 초안 claim을 추가했습니다.

## llm_semantic_analysis
- 상태: 검토 필요(`REVIEW_REQUIRED`)
- 비즈니스 규칙(NORMALIZED_PROVIDER_BUSINESSRULES_0): dbo.GetInspItemsCd는 dbo.PEX_INSP_ITEMS를 조회하여 INSP_ITEMS_CD, INSP_ITEMS_NM, INSP_ITEMS_DESC 형태의 단일 결과 집합을 반환하는 조회성 프로시저로 해석됩니다.
- 비즈니스 규칙(NORMALIZED_PROVIDER_BUSINESSRULES_1): @InspItemsCd 파라미터가 정의되어 있으나 필터 의도와 실제 사용 정합성은 추가 확인이 필요합니다.
- 비즈니스 규칙(DETERMINISTIC_SAFETY_NET_READ_ONLY_LOOKUP): 결정론적 fact가 읽기 전용 조회 동작을 보여 주며, 초안 비즈니스 맥락으로 검토해야 합니다.
- 현대화 포인트(DETERMINISTIC_SAFETY_NET_LOOKUP_DTO_SHAPE): 조회 입력과 result-shape fact는 Java/MyBatis 전환 전에 명시적인 DTO 필드로 매핑해야 합니다.
- 전환 가이드(NORMALIZED_PROVIDER_CONVERSIONGUIDANCE_0): MyBatis 단일 SELECT 매퍼로 우선 전환하고 결과 컬럼은 INSP_ITEMS_CD, INSP_ITEMS_NM, INSP_ITEMS_DESC에 매핑하는 구성이 적합합니다.
- 전환 가이드(NORMALIZED_PROVIDER_CONVERSIONGUIDANCE_1): @InspItemsCd를 LIKE 조건에 반영할지 또는 API/Mapper에서 제거할지 업무 규칙 확인 후 최종 SQL과 메서드 시그니처를 확정해야 합니다.
- 전환 가이드(DETERMINISTIC_SAFETY_NET_LOOKUP_CONVERSION_GUIDANCE): 결정론적 DTO 계약이 검증될 때까지 조회 parameter binding과 결과 매핑은 REVIEW_REQUIRED로 유지합니다.
- 가이드 인사이트(readOnlyLookup): 정적 메타데이터 기준으로 단일 result set과 3개 컬럼 매핑 구조입니다. 다음 추출 항목=Java DTO 필드명/타입 규칙과 ResultMap 네이밍 규칙을 수집해 매핑 계약을 확정합니다.
- 가이드 인사이트(parameterHandling): 정의된 입력 파라미터와 조회 필터의 결합 의도를 변환 전에 확정해야 합니다. 다음 추출 항목=호출 서비스/화면의 검색 요구사항을 기준으로 @InspItemsCd의 동일일치/부분일치/전체조회 의도를 확인합니다.
- 가이드 인사이트(dependencyScope): 현재 확인된 정적 의존성은 SAME_DATABASE 내 dbo.PEX_INSP_ITEMS 단일 테이블 참조입니다.
- 가이드 인사이트(resultMapping): 결과셋 1개와 3개 컬럼 중심의 고정 스키마 매핑 구조로 정리 가능합니다.
- 가이드 인사이트(NORMALIZED_PROVIDER_MIGRATIONGUIDEINSIGHTS_0): 개요: 단일 테이블 조회 중심의 단순 read-only 프로시저입니다. Needs verification: @InspItemsCd 사용 의도 확인이 필요합니다. 다음 추출 항목=호출 서비스/화면/API의 검색 조건 정의를 수집해 @InspItemsCd의 실제 사용 정책(미사용 유지/부분일치/정확일치)을 확정합니다.
- 가이드 인사이트(NORMALIZED_PROVIDER_MIGRATIONGUIDEINSIGHTS_1): 의존성 인벤토리: SAME_DATABASE 범위에서 dbo.PEX_INSP_ITEMS 단일 테이블 의존성이 확인되었습니다.
- 가이드 인사이트(NORMALIZED_PROVIDER_MIGRATIONGUIDEINSIGHTS_3): 호출 흐름: 내부 프로시저/함수 호출 없이 단일 SELECT 흐름으로 파악됩니다.
- 가이드 인사이트(NORMALIZED_PROVIDER_MIGRATIONGUIDEINSIGHTS_4): 리스크 메트릭: 구조 복잡도는 낮지만 파라미터-필터 정합성 불확실성으로 검토가 필요합니다. 다음 추출 항목=기존 애플리케이션 호출부에서 @InspItemsCd 전달값 사용 경로를 추적해 요구사항 불일치 여부를 확인합니다.
- 가이드 인사이트(NORMALIZED_PROVIDER_MIGRATIONGUIDEINSIGHTS_5): 메타데이터 추출 부록: PK/클러스터드 유니크 인덱스가 INSP_ITEMS_CD 기준으로 확인되어 DTO 키 매핑 기준으로 활용 가능합니다.
- 가이드 인사이트(NORMALIZED_PROVIDER_MIGRATIONGUIDEINSIGHTS_6): 마이그레이션 전략: read-only Mapper 우선 전환 후 파라미터 유지/제거 정책을 검증 단계에서 확정하는 접근이 적합합니다. 다음 추출 항목=서비스 메서드 시그니처와 API 계약을 수집해 MyBatis 파라미터 객체 및 SQL 바인딩 정책을 확정합니다.
- 가이드 인사이트(DETERMINISTIC_SAFETY_NET_LOOKUP_GUIDE): 마이그레이션 가이드는 조회 입력, 읽기 의존성, result-shape 검토 메모를 포함해야 합니다.
- 검토 마커(NORMALIZED_PROVIDER_REVIEWMARKERS_0): @InspItemsCd의 실제 사용 의도와 호출부 전달 규칙을 확인해야 Mapper 파라미터 유지/제거를 확정할 수 있습니다.
- 검토 마커(LLM_OUTPUT_LANGUAGE_REVIEW_REQUIRED): 일부 사람이 읽는 자유 텍스트가 한국어가 아니어서 결과 검토가 필요합니다. JSON 키, enum/status/code, evidence ref 같은 기계 계약 식별자는 그대로 유지했습니다.

## evidence_summary
- 저장 프로시저: `dbo.GetInspItemsCd` - COLLECTED
- 테이블: `dbo.PEX_INSP_ITEMS` - MSSQL MCP table schema metadata 근거입니다.
- 의존성 근거: `dbo.GetInspItemsCd` - MSSQL MCP dependency closure 근거입니다.
- 의존성 근거: `PEX_INSP_ITEMS` - MSSQL MCP dependency closure 근거입니다.
- 의존성 근거: `dbo.PEX_INSP_ITEMS` - MSSQL MCP dependency closure 근거입니다.
- LLM 추론: `15d95b01bf3ee738786f9330cfee6c2bba78793a268615de3fa98f1234a1e9d7` - 15d95b01bf3ee738786f9330cfee6c2bba78793a268615de3fa98f1234a1e9d7

## assumptions_and_todo
- TODO: REVIEW_REQUIRED: metadata는 MSSQL MCP registry 경계를 통해 수집되며 이 integration slice에서는 platform DB workflow repository에 저장됩니다.
- TODO: REVIEW_REQUIRED: LLM semantic analysis is inferred and remains a validation caveat.
- TODO: Provider returned a structured assumption object; text was not stored.
- TODO: DETERMINISTIC_SAFETY_NET은 허용된 결정론적 fact id만 사용해 초안 claim을 추가했습니다.
- TODO: transaction boundary 확인
- TODO: dynamic SQL/temp table 여부는 analysis engine 결과로 확정

## review_checklist
- [x] evidence_included
- [x] draft_only_boundary_marked
- [ ] reviewer_confirms_business_rules