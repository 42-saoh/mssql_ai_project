# golden-java-mybatis-sp-wrapper-order-request-v1

## input_interpretation
- systemCode: PEM
- businessCodeLv1/businessCodeLv2: order/request
- entityName: OrderRequest
- generationMode: spWrapper
- resourceName: order-request
- spName: dbo.USP_ORDER_REQUEST_LIST
- tableName: dbo.ORD_REQ

## registry_versions
- policy: `policy:project_ai_java_mybatis_generation_policy.yaml@1.0.0`
- template: `template:java_mybatis_sp_wrapper@0.2.0`
- registry: `java_mybatis_templates_v1`

## generator_metadata
- generatorVersion: `generation-core-0.1.0`
- requestedOutputType: `JAVA_MYBATIS_DRAFT`
- artifactStatus: `DRAFT`
- evidenceCaveat: `true`
- draftQualityGate: `validation_only`

## input_snapshot
- sanitizedSnapshotHash: `9a64f54f70ebdb4a7bfd17b80da9388827abb111e358a0433d20a61433af92f5`
- sanitizedSnapshot:

```json
{
  "evidence": {
    "assumptions": [
      "페이징 정책은 아직 미확정이므로 TODO 로 남긴다.",
      "정렬 규칙은 SP 내부 기본 정렬을 그대로 유지한다."
    ],
    "sources": [
      {
        "locator": "",
        "name": "dbo.USP_ORDER_REQUEST_LIST",
        "reason": "조회 SQL 재구성 근거가 부족하므로 SP wrapper 유지",
        "snapshotId": null,
        "type": "storedProcedure"
      },
      {
        "locator": "",
        "name": "dbo.ORD_REQ",
        "reason": "DTO 필드 정의 및 컬럼 타입 근거",
        "snapshotId": null,
        "type": "table"
      }
    ]
  },
  "request": {
    "authorId": "AI",
    "businessCodeLv1": "order",
    "businessCodeLv2": "request",
    "columns": [
      {
        "dbType": "bigint",
        "description": "주문요청ID",
        "name": "ORD_REQ_ID",
        "nullable": false
      },
      {
        "dbType": "varchar(20)",
        "description": "고객ID",
        "name": "CUS_ID",
        "nullable": false
      },
      {
        "dbType": "varchar(20)",
        "description": "요청상태코드",
        "name": "REQ_STAT_CD",
        "nullable": false
      },
      {
        "dbType": "datetime2",
        "description": "요청일시",
        "name": "REQ_DTM",
        "nullable": false
      },
      {
        "dbType": "uniqueidentifier",
        "description": "등록사용자ID",
        "name": "CRE_USR_ID",
        "nullable": false
      }
    ],
    "commonFramework": "spring-mybatis",
    "description": "주문 요청 목록 조회용 Java/MyBatis SP wrapper 초안",
    "entityName": "OrderRequest",
    "generationMode": "spWrapper",
    "inputParams": [
      {
        "dbType": "varchar(20)",
        "name": "CUS_ID",
        "required": false
      },
      {
        "dbType": "varchar(20)",
        "name": "REQ_STAT_CD",
        "required": false
      }
    ],
    "javaTimePreferred": true,
    "messagePrefix": "order.request",
    "pkColumns": [
      "ORD_REQ_ID"
    ],
    "resourceName": "order-request",
    "resultShape": [
      "ORD_REQ_ID",
      "CUS_ID",
      "REQ_STAT_CD",
      "REQ_DTM",
      "CRE_USR_ID"
    ],
    "serviceInterfaceRequired": true,
    "spName": "dbo.USP_ORDER_REQUEST_LIST",
    "subSystemCode": "ORD",
    "systemCode": "PEM",
    "tableName": "dbo.ORD_REQ",
    "useLombok": false
  },
  "sampleId": "golden-java-mybatis-sp-wrapper-order-request-v1"
}
```

## generation_mode
- `spWrapper`
- 이유: 생성 모드는 policy asset의 generationModes 기준을 따릅니다.

## evidence_summary
- 저장 프로시저: `dbo.USP_ORDER_REQUEST_LIST` - 조회 SQL 재구성 근거가 부족하므로 SP wrapper 유지
- 테이블: `dbo.ORD_REQ` - DTO 필드 정의 및 컬럼 타입 근거
- DTO 필드 정의는 metadata column/result shape evidence 에 근거함
- 모든 생성물은 draft-only artifact 이며 자동 적용 대상이 아님

## evidence_refs
- MSSQL_METADATA: `dbo.USP_ORDER_REQUEST_LIST` locator=`조회 SQL 재구성 근거가 부족하므로 SP wrapper 유지`
- MSSQL_METADATA: `dbo.ORD_REQ` locator=`DTO 필드 정의 및 컬럼 타입 근거`

## package_structure
- `com.pec.pem.order.request.model`
- `com.pec.pem.order.request.service`
- `com.pec.pem.order.request.mapper`
- `src/main/resources/mybatis/pem/mappers/order/request`

## output_roles
- dto: DTO_DRAFT
- service: SERVICE_DRAFT
- mapperInterface: MAPPER_INTERFACE
- mapperXml: MAPPER_XML

## generated_files
- `src/main/java/com/pec/pem/order/request/model/OrderRequestDTO.java` (DTO_DRAFT)
- `src/main/java/com/pec/pem/order/request/service/OrderRequestService.java` (SERVICE_DRAFT)
- `src/main/java/com/pec/pem/order/request/mapper/OrderRequestMapper.java` (MAPPER_INTERFACE)
- `src/main/resources/mybatis/pem/mappers/order/request/OrderRequestMapperSQL.xml` (MAPPER_XML)

## code_draft
- DTO / Service / Mapper / Mapper XML 초안은 artifact file inventory 를 기준으로 한다.
- generated_source_application: `not_performed`
- target_application_write: `not_performed`

## draft_change_summary
- 모든 파일은 artifact preview/diff 대상으로만 생성되었습니다.
- 실제 프로젝트 소스 반영, DDL/DML 실행, procedure 실행은 수행하지 않습니다.
- 초안은 evidence map과 caveat를 함께 제공해 최초 설계 업무의 출발점을 줄입니다.

## sql_risk_markers
- 상태 REVIEW_REQUIRED: `SP_EXEC_WRAPPER` - Mapper XML은 EXEC 저장 프로시저 wrapper를 유지하며 생성 과정에서는 실행하지 않는다.
- 상태 REVIEW_REQUIRED: `SQL_REBUILD_NOT_CONFIRMED` - 더 강한 근거가 없으면 저장 프로시저 로직을 inline SQL로 재구성하지 않는다.
- 상태 REVIEW_REQUIRED: `PARAMETER_BINDING_REVIEW_REQUIRED` - 적용 전 procedure metadata 기준으로 parameter binding을 확인해야 한다.

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
- message key 예시: `biz.info.order.request.retrieve.001`
- message value 예시: `주문 요청 목록을 조회했습니다.`
- application yml 예시:

```yaml
pem:
  mybatis:
    config: classpath:/mybatis/pem/mybatis-config-pem.xml
```

## assumptions_and_todo
- REVIEW_REQUIRED: 모든 파일은 draft-only 이며 추가 근거 확보 전 자동 반영하지 않습니다.
- TODO(input): 페이징 정책은 아직 미확정이므로 TODO 로 남긴다.
- TODO(input): 정렬 규칙은 SP 내부 기본 정렬을 그대로 유지한다.
- TODO(policy.mustMarkUnknown): pk_columns
- TODO(policy.mustMarkUnknown): transaction_boundary
- TODO(policy.mustMarkUnknown): validation_group_usage
- TODO(policy.mustMarkUnknown): base_framework_usage
- TODO(policy.mustMarkUnknown): exact_exception_message_codes
- TODO(policy.mustMarkUnknown): controller_need
- TODO(policy.mustMarkUnknown): dto_vo_model_final_choice
- TODO(policy.mustMarkUnknown): sp_rebuild_feasibility

## quality_summary
- evidenceSources: `2`
- raw SQL text, row data, secrets, DDL/DML execution output은 포함하지 않습니다.
- Java/MyBatis 코드는 설계 초안이며 validation 결과와 caveat를 함께 읽어야 합니다.

## evidence_map
- generatedFiles: `4`
- primaryEvidence: 조회 SQL 재구성 근거가 부족하므로 SP wrapper 유지, DTO 필드 정의 및 컬럼 타입 근거
- DTO/model fields: metadata columns and result shape evidence
- Mapper/service shape: stored procedure signature and dependency/call-flow evidence

## known_caveats
- REVIEW_REQUIRED는 근거 보강 필요 상태를 의미합니다.
- TODO(input): 페이징 정책은 아직 미확정이므로 TODO 로 남긴다.
- TODO(input): 정렬 규칙은 SP 내부 기본 정렬을 그대로 유지한다.
- TODO(policy.mustMarkUnknown): pk_columns
- TODO(policy.mustMarkUnknown): transaction_boundary
- TODO(policy.mustMarkUnknown): validation_group_usage
- TODO(policy.mustMarkUnknown): base_framework_usage
- TODO(policy.mustMarkUnknown): exact_exception_message_codes
- TODO(policy.mustMarkUnknown): controller_need
- TODO(policy.mustMarkUnknown): dto_vo_model_final_choice
- TODO(policy.mustMarkUnknown): sp_rebuild_feasibility

## next_evidence_to_collect
- `dbo.USP_ORDER_REQUEST_LIST`의 confirmed dependency procedure별 input/output, DML, transaction boundary를 보강합니다.
- MyBatis resultMap이 필요한 nested/nullable/collection result shape evidence를 보강합니다.
- 호출부에서 기대하는 service method contract, message key, paging/sorting semantics를 보강합니다.

## draft_readiness
- Java/MyBatis package, class, mapper id, message key는 registry naming rule을 따릅니다.
- DML/call-flow caveat가 남은 경우 구현 깊이는 mapper/service skeleton 수준으로 제한합니다.
- `OrderRequest` 초안은 최초 설계 리드타임 단축용이며 자동 적용 경로가 없습니다.
