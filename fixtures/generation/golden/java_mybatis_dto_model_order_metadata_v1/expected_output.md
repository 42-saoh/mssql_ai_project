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
- 사유: 생성 모드는 policy asset 의 generationModes 기준을 따른다.

## evidence_summary
- Table: `dbo.TB_ORDER` - synthetic metadata-only table fixture; no row data included
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
- target_application_write: `forbidden_without_human_review`

## diff_review_summary
- 모든 파일은 artifact preview/diff 대상으로만 생성한다.
- 실제 프로젝트 소스 반영, DDL/DML 실행, procedure 실행은 수행하지 않는다.
- reviewer 는 생성 diff 와 policy checklist 를 확인한 뒤 수동 적용 여부를 결정한다.

## sql_risk_markers
- PASS: NO_SQL_RENDERED - DTO/VO/Model drafts contain no executable SQL.
- REVIEW_REQUIRED: FIELD_MAPPING_REVIEW_REQUIRED - Field names and Java types remain draft mappings until reviewed.

## unconfirmed_areas
- REVIEW_REQUIRED: pk_columns
- REVIEW_REQUIRED: transaction_boundary
- REVIEW_REQUIRED: validation_group_usage
- REVIEW_REQUIRED: base_framework_usage
- REVIEW_REQUIRED: exact_exception_message_codes
- REVIEW_REQUIRED: controller_need
- REVIEW_REQUIRED: dto_vo_model_final_choice
- REVIEW_REQUIRED: sp_rebuild_feasibility

## message_and_config_examples
- message key example: `biz.info.order.metadata.retrieve.001`
- message value example: `주문 메타데이터 DTO/VO/Model 목록을 조회했습니다.`
- application yml example:

```yaml
pem:
  mybatis:
    config: classpath:/mybatis/pem/mybatis-config-pem.xml
```

## assumptions_and_todo
- REVIEW_REQUIRED: 모든 파일은 draft-only 이며 수동 검토 전 실제 프로젝트 반영 금지
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

## review_checklist
- [x] naming_rules_applied
- [x] package_pattern_applied
- [x] mapper_xml_namespace_matches_interface
- [x] sql_id_matches_mapper_method
- [x] evidence_included
- [x] assumptions_disclosed
- [x] project_exclusions_respected
- [ ] dto_vo_model_final_choice_reviewed
- [ ] field_mapping_reviewed
- [ ] generated_diff_reviewed_before_apply
