# golden-java-mybatis-dto-model-order-metadata-v1

## input_interpretation
- systemCode: PEM
- businessCodeLv1/businessCodeLv2: order/metadata
- entityName: OrderMetadata
- generationMode: metadataObject
- resourceName: order-metadata
- spName: 
- tableName: dbo.TB_ORDER

## registry_versions
- policy: `policy:project_ai_java_mybatis_generation_policy.yaml@1.0.0`
- template: `template:java_mybatis_dto_model_bundle@0.1.0`
- registry: `java_mybatis_templates_v1`

## generator_metadata
- generatorVersion: `generation-core-0.1.0`
- requestedOutputType: `DTO_MODEL_DRAFT`
- artifactStatus: `DRAFT`
- evidenceCaveat: `true`
- draftQualityGate: `validation_only`

## input_snapshot
- sanitizedSnapshotHash: `8850f7880cdf3aba79c472483b3878e825005d11c81a9690bb6f5e1224496d0c`
- sanitizedSnapshot:

```json
{
  "evidence": {
    "assumptions": [
      "DTO/VO/Model 최종 선택은 모듈 관례 확인 후 확정한다.",
      "STATUS_CD 값 도메인은 metadata 만으로 확정하지 않는다."
    ],
    "sources": [
      {
        "locator": "fixtures/mcp/metadata_snapshot.json#/tables/0",
        "name": "dbo.TB_ORDER",
        "reason": "synthetic metadata-only table fixture; no row data included",
        "snapshotId": "mcp-fixture-snapshot-0001",
        "type": "table"
      }
    ]
  },
  "request": {
    "authorId": "AI",
    "businessCodeLv1": "order",
    "businessCodeLv2": "metadata",
    "columns": [
      {
        "dbType": "int",
        "description": "주문ID",
        "name": "ORDER_ID",
        "nullable": false
      },
      {
        "dbType": "int",
        "description": "고객ID",
        "name": "CUSTOMER_ID",
        "nullable": false
      },
      {
        "dbType": "date",
        "description": "주문일자",
        "name": "ORDER_DATE",
        "nullable": false
      },
      {
        "dbType": "varchar(30)",
        "description": "상태코드",
        "name": "STATUS_CD",
        "nullable": false
      }
    ],
    "commonFramework": "spring-mybatis",
    "description": "주문 메타데이터 DTO/VO/Model 초안",
    "entityName": "OrderMetadata",
    "generationMode": "metadataObject",
    "javaTimePreferred": true,
    "messagePrefix": "order.metadata",
    "pkColumns": [
      "ORDER_ID"
    ],
    "resourceName": "order-metadata",
    "resultShape": [
      "ORDER_ID",
      "CUSTOMER_ID",
      "ORDER_DATE",
      "STATUS_CD"
    ],
    "subSystemCode": "ORD",
    "systemCode": "PEM",
    "tableName": "dbo.TB_ORDER",
    "useLombok": false
  },
  "sampleId": "golden-java-mybatis-dto-model-order-metadata-v1"
}
```

## generation_mode
- `metadataObject`
- 이유: 생성 모드는 policy asset의 generationModes 기준을 따릅니다.

## evidence_summary
- 테이블: `dbo.TB_ORDER` - synthetic metadata-only table fixture; no row data included
- DTO 필드 정의는 metadata column/result shape evidence 에 근거함
- 모든 생성물은 draft-only artifact 이며 자동 적용 대상이 아님

## evidence_refs
- MSSQL_METADATA: `dbo.TB_ORDER` locator=`fixtures/mcp/metadata_snapshot.json#/tables/0` snapshotId=`mcp-fixture-snapshot-0001`

## package_structure
- `com.pec.pem.order.metadata.model`

## output_roles
- dto: DTO_DRAFT
- vo: VO_DRAFT
- model: MODEL_DRAFT

## generated_files
- `src/main/java/com/pec/pem/order/metadata/model/OrderMetadataDTO.java` (DTO_DRAFT)
- `src/main/java/com/pec/pem/order/metadata/model/OrderMetadataVO.java` (VO_DRAFT)
- `src/main/java/com/pec/pem/order/metadata/model/OrderMetadataModel.java` (MODEL_DRAFT)

## code_draft
- DTO / VO / Model 초안은 metadata-only field evidence 를 기준으로 한다.
- generated_source_application: `not_performed`
- target_application_write: `not_performed`

## draft_change_summary
- 모든 파일은 artifact preview/diff 대상으로만 생성되었습니다.
- 실제 프로젝트 소스 반영, DDL/DML 실행, procedure 실행은 수행하지 않습니다.
- 초안은 evidence map과 caveat를 함께 제공해 최초 설계 업무의 출발점을 줄입니다.

## sql_risk_markers
- 상태 PASS: `NO_SQL_RENDERED` - DTO/VO/Model 초안에는 실행 가능한 SQL이 포함되지 않는다.
- 상태 REVIEW_REQUIRED: `FIELD_MAPPING_REVIEW_REQUIRED` - field name과 Java type은 검토 전까지 초안 mapping으로 유지한다.

## llm_conversion_guidance
- status: NO_CONVERSION_GUIDANCE_RETURNED

## unconfirmed_areas
- REVIEW_REQUIRED: `pk_columns` 항목은 추가 근거 확보 전까지 caveat로 유지합니다.
- REVIEW_REQUIRED: `transaction_boundary` 항목은 추가 근거 확보 전까지 caveat로 유지합니다.
- REVIEW_REQUIRED: `validation_group_usage` 항목은 추가 근거 확보 전까지 caveat로 유지합니다.
- REVIEW_REQUIRED: `base_framework_usage` 항목은 추가 근거 확보 전까지 caveat로 유지합니다.
- REVIEW_REQUIRED: `exact_exception_message_codes` 항목은 추가 근거 확보 전까지 caveat로 유지합니다.
- REVIEW_REQUIRED: `controller_need` 항목은 추가 근거 확보 전까지 caveat로 유지합니다.
- REVIEW_REQUIRED: `dto_vo_model_final_choice` 항목은 추가 근거 확보 전까지 caveat로 유지합니다.
- REVIEW_REQUIRED: `sp_rebuild_feasibility` 항목은 추가 근거 확보 전까지 caveat로 유지합니다.

## message_and_config_examples
- message key 예시: `biz.info.order.metadata.retrieve.001`
- message value 예시: `주문 메타데이터 DTO/VO/Model 목록을 조회했습니다.`
- application yml 예시:

```yaml
pem:
  mybatis:
    config: classpath:/mybatis/pem/mybatis-config-pem.xml
```

## assumptions_and_todo
- REVIEW_REQUIRED: 모든 파일은 draft-only 이며 추가 근거 확보 전 자동 반영하지 않습니다.
- TODO(input): DTO/VO/Model 최종 선택은 모듈 관례 확인 후 확정한다.
- TODO(input): STATUS_CD 값 도메인은 metadata 만으로 확정하지 않는다.
- TODO(policy.mustMarkUnknown): pk_columns
- TODO(policy.mustMarkUnknown): transaction_boundary
- TODO(policy.mustMarkUnknown): validation_group_usage
- TODO(policy.mustMarkUnknown): base_framework_usage
- TODO(policy.mustMarkUnknown): exact_exception_message_codes
- TODO(policy.mustMarkUnknown): controller_need
- TODO(policy.mustMarkUnknown): dto_vo_model_final_choice
- TODO(policy.mustMarkUnknown): sp_rebuild_feasibility

## quality_summary
- evidenceSources: `1`
- raw SQL text, row data, secrets, DDL/DML execution output은 포함하지 않습니다.
- Java/MyBatis 코드는 설계 초안이며 validation 결과와 caveat를 함께 읽어야 합니다.

## evidence_map
- generatedFiles: `3`
- primaryEvidence: fixtures/mcp/metadata_snapshot.json#/tables/0
- DTO/model fields: metadata columns and result shape evidence
- Mapper/service shape: stored procedure signature and dependency/call-flow evidence

## known_caveats
- REVIEW_REQUIRED는 근거 보강 필요 상태를 의미합니다.
- TODO(input): DTO/VO/Model 최종 선택은 모듈 관례 확인 후 확정한다.
- TODO(input): STATUS_CD 값 도메인은 metadata 만으로 확정하지 않는다.
- TODO(policy.mustMarkUnknown): pk_columns
- TODO(policy.mustMarkUnknown): transaction_boundary
- TODO(policy.mustMarkUnknown): validation_group_usage
- TODO(policy.mustMarkUnknown): base_framework_usage
- TODO(policy.mustMarkUnknown): exact_exception_message_codes
- TODO(policy.mustMarkUnknown): controller_need
- TODO(policy.mustMarkUnknown): dto_vo_model_final_choice
- TODO(policy.mustMarkUnknown): sp_rebuild_feasibility

## next_evidence_to_collect
- ``의 confirmed dependency procedure별 input/output, DML, transaction boundary를 보강합니다.
- MyBatis resultMap이 필요한 nested/nullable/collection result shape evidence를 보강합니다.
- 호출부에서 기대하는 service method contract, message key, paging/sorting semantics를 보강합니다.

## draft_readiness
- Java/MyBatis package, class, mapper id, message key는 registry naming rule을 따릅니다.
- DML/call-flow caveat가 남은 경우 구현 깊이는 mapper/service skeleton 수준으로 제한합니다.
- `OrderMetadata` 초안은 최초 설계 리드타임 단축용이며 자동 적용 경로가 없습니다.
