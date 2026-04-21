# services/mssql-mcp

MSSQL Metadata MCP 서버의 시작점이다. 현재는 **read-only tool catalog** 와 health endpoint 를 가진 최소 skeleton 이다.

## 원칙

- 자유 SQL 실행기 금지
- row data 조회 금지
- metadata-only
- snapshot / evidence refs 계약 유지

## 다음 구현 우선순위

1. tool schema 를 `spec/mcp/mssql_metadata_tool_catalog.yaml` 와 동기화
2. adapter layer 에 metadata read-only query 구현
3. contract tests 추가
4. 실제 MCP transport 연결

## 외부 DB 연결 주의

- metadata source DB 는 외부에서 관리한다.
- 이 저장소는 해당 DB 의 기동/중지, schema apply, row-data query 를 담당하지 않는다.
- 테스트는 fixture-first 로 유지하고, 실제 연결이 필요해도 read-only metadata profile 만 사용한다.

