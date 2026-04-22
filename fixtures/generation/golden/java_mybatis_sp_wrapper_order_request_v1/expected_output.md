# golden-java-mybatis-sp-wrapper-order-request-v1

## input_interpretation
- systemCode: PEM
- businessCodeLv1/businessCodeLv2: order/request
- entityName: OrderRequest
- generationMode: spWrapper
- resourceName: order-request
- spName: dbo.USP_ORDER_REQUEST_LIST
- tableName: dbo.ORD_REQ

## generation_mode
- `spWrapper`
- 사유: SP 내부 조회 로직을 SQL 로 재구성할 근거가 아직 충분하지 않음

## evidence_summary
- Stored Procedure: `dbo.USP_ORDER_REQUEST_LIST`
- Table: `dbo.ORD_REQ`
- DTO 필드 정의는 테이블 컬럼과 결과 shape 에 근거함
- Mapper XML 은 SP 직접 호출 wrapper 로 유지함

## package_structure
- `com.pec.pem.order.request.model`
- `com.pec.pem.order.request.service`
- `com.pec.pem.order.request.mapper`
- `src/main/resources/mybatis/pem/mappers/order/request`

## generated_files
- `src/main/java/com/pec/pem/order/request/model/OrderRequestDTO.java`
- `src/main/java/com/pec/pem/order/request/service/OrderRequestService.java`
- `src/main/java/com/pec/pem/order/request/mapper/OrderRequestMapper.java`
- `src/main/resources/mybatis/pem/mappers/order/request/OrderRequestMapperSQL.xml`

## code_draft
- DTO / Service / Mapper / Mapper XML 초안은 동일 디렉터리의 `src/` 아래 파일을 기준으로 한다.

## message_and_config_examples
- message key example: `biz.info.orderrequest.retrieve.001`
- message value example: `주문 요청 목록을 조회했습니다.`
- application yml example:

```yaml
pem:
  mybatis:
    config: classpath:/mybatis/pem/mybatis-config-pem.xml
```

## assumptions_and_todo
- TODO: 페이징 조건 파라미터 유무 확인
- TODO: transaction boundary 확인 후 서비스 계층 주석 보강
- TODO: controller 필요 여부 확인
- TODO: exact exception/message code 확정
- TODO: 향후 evidence 가 충분해지면 `spRebuild` 전환 가능성 재평가

## review_checklist
- [x] naming_rules_applied
- [x] package_pattern_applied
- [x] mapper_xml_namespace_matches_interface
- [x] sql_id_matches_mapper_method
- [x] evidence_included
- [x] assumptions_disclosed
- [x] project_exclusions_respected
