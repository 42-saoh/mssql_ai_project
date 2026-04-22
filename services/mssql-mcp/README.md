# services/mssql-mcp

MSSQL Metadata MCP 서버의 시작점이다. 현재는 **read-only tool catalog**, profile registry, live readiness endpoint 를 가진 최소 skeleton 이다.

## 원칙

- 자유 SQL 실행기 금지
- row data 조회 금지
- metadata-only
- snapshot / evidence refs 계약 유지
- live 연결이 필요해도 metadata read-only 계정만 사용 권장

## 로컬 Docker SQL Server 연결 기준

사용자가 별도로 띄운 MSSQL 컨테이너에 **연결만** 한다.
이 저장소는 해당 DB 의 기동/중지, schema apply, row-data query 를 담당하지 않는다.

기본 전제:

- host-run (`make run-mcp`, 로컬 uvicorn): `MSSQL_METADATA_HOST=127.0.0.1`
- `docker/test` 컨테이너 내부: `MSSQL_METADATA_DOCKER_HOST=host.docker.internal`
- profile registry: `config/mssql/local_docker_profiles.yaml`
- 기본 profile id: master
- 기본 platform DB name: `master`

여러 DB 를 같은 SQL Server 인스턴스에서 함께 쓰는 경우에는 `config/mssql/local_docker_profiles.yaml` 에 profile 을 추가해서 `dbProfileId -> database` 매핑을 늘린다.

## 준비 절차

1. 루트에서 `.env.example` 을 `.env` 로 복사한다.
2. `PLATFORM_DB_*`, `MSSQL_METADATA_*` 값을 로컬 환경에 맞게 채운다.
3. 가능하면 metadata read-only 계정을 사용한다.
4. live metadata 확인이 필요하면 `MSSQL_ENABLE_LIVE_METADATA=1` 로 켠다.
5. `make run-mcp` 후 `GET /health/ready`, `GET /config/db-profiles` 로 확인한다.

## 현재 제공 endpoint

- `GET /health`
- `GET /health/ready`
- `GET /config/db-profiles`
- `GET /catalog/tools`

## 다음 구현 우선순위

1. tool schema 를 `spec/mcp/mssql_metadata_tool_catalog.yaml` 와 동기화
2. adapter layer 에 metadata read-only query 구현
3. contract tests 추가
4. 실제 MCP transport 연결

## 외부 DB 연결 주의

- metadata source DB 는 외부에서 관리한다.
- 이 저장소는 해당 DB 의 기동/중지, schema apply, row-data query 를 담당하지 않는다.
- 테스트는 fixture-first 를 기본으로 유지한다.
- live 연결은 **옵션** 이며, 연결되더라도 read-only metadata profile 만 사용한다.
