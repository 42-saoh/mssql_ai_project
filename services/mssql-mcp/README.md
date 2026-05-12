# services/mssql-mcp

MSSQL Metadata MCP 서버의 시작점이다. 현재는 **read-only tool catalog**, profile registry, fixture-backed execution, env-gated live metadata execution 을 제공한다. 활성 catalog tool 은 fixture 경로와 live repository handler 를 모두 가진다.
P27 기준 `get_dependency_closure` 와 `resolve_dependency_reference` 는 fixture-first hardening 상태의 active/read-only dependency evidence tool 이다. 기존 API `/api/v1/metadata/tools` summary 에는 노출되지만, 전용 API invocation route, Web UI, workflow wiring 은 아직 없다. 명시적 `P27_HARD_LIVE_GATE=1` 을 켠 경우에만 PPM hard-live dependency evidence gate 를 실행한다.

## 원칙

- 자유 SQL 실행기 금지
- row data 조회 금지
- metadata-only
- snapshot / evidence refs 계약 유지
- live 연결이 필요해도 metadata read-only 계정만 사용 권장
- PPM metadata 가 필요할 때 PLF 로 대체하지 않고 blocker/error 로 보고

## 로컬 Docker SQL Server 연결 기준

사용자가 별도로 띄운 MSSQL 컨테이너에 **연결만** 한다.
이 저장소는 해당 DB 의 기동/중지, schema apply, row-data query 를 담당하지 않는다.

기본 전제:

- host-run (`make run-mcp`, 로컬 uvicorn): `MSSQL_METADATA_HOST=127.0.0.1`
- `docker/test` 컨테이너 내부: `MSSQL_METADATA_DOCKER_HOST=host.docker.internal`
- 기본 TDS protocol: `MSSQL_METADATA_TDS_VERSION=7.4`
- Chakra/legacy proxy 가 기본 TDS negotiation 을 거부하는 로컬 host-run 에서는
  `MSSQL_METADATA_TDS_VERSION=7.0`
- profile registry: `config/mssql/local_docker_profiles.yaml`
- 기본 metadata profile id: `master`
- runtime override: `.env` 의 `MSSQL_METADATA_DEFAULT_PROFILE_ID=ppm` 은 profile
  registry 의 정적 default 보다 우선한다.
- 기본 metadata DB name: `master`
- platform DB profile id: `plf`
- pilot analysis target profile id: `ppm`
- 기본 platform DB name: `PLF`

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
- `POST /tools/{toolName}/invoke`

## Tool invocation

MVP tool execution uses structured arguments only:

```json
{
  "arguments": {
    "dbProfileId": "master",
    "schema": "dbo",
    "tableName": "TB_ORDER"
  }
}
```

The response always carries `snapshotId`, `collectedAt`, `evidenceRefs`, and either
`data` or a documented `error.code`. Successful `data` payloads are standardized
with `sourceProfile`, `sourceDatabase`, `objectIdentity`, `caveats`, and
`reviewRequired`.

The default execution path is fixture-backed metadata from
`fixtures/mcp/metadata_snapshot.json`, so tests do not require a live SQL Server.
When `MSSQL_ENABLE_LIVE_METADATA=1`, tool invocation uses structured read-only
metadata queries against SQL Server catalog views such as `sys.objects`,
`sys.columns`, `sys.sql_modules`, `sys.sql_expression_dependencies`,
`sys.indexes`, `sys.key_constraints`, `sys.foreign_keys`,
`sys.check_constraints`, and `sys.extended_properties`.

Inventory tools expose definition availability, hash, length, detected patterns,
dependency summary, caveats, and review flags without returning definition text.
Direct definition tools (`get_procedure_definition`, `get_view_definition`,
`get_function_definition`) may return definition text for downstream analysis and
also return the same standardized hash/length/pattern/access/caveat fields.

`get_procedure_dependencies` exposes structured dependency resolution evidence
and is contractually extended for P27 with optional `resolutionConfidence`,
`resolutionEvidenceKind`, `unresolvedReason`, and `resolutionChain` fields.
Confirmed dependencies can be treated as deterministic facts only when catalog
evidence is unique and high confidence. Ambiguous names, dynamic SQL markers,
unresolved synonym targets, cross-server references without catalog confirmation,
and caller-dependent references remain `REVIEW_REQUIRED`.

P27 also exposes active read-only fixture-first tools:

- `get_dependency_closure`: bounded procedure/view/function dependency graph,
  default `maxDepth=2`, hard max `3`, catalog evidence only. TABLE objects are
  leaf nodes; only confirmed PROCEDURE/VIEW/FUNCTION targets are expanded.
- `resolve_dependency_reference`: structured resolver for unresolved,
  caller-dependent, cross-DB, or synonym references. It returns candidates and
  selects a target only when catalog evidence is unique.

These tools remain read-only and structured-input-only. `REVIEW_REQUIRED`
dependencies are always returned in `unresolved`; when
`includeReviewRequired=false`, they are hidden from closure graph nodes/edges but
not discarded. The tools must not accept free-form SQL, return row data, execute
procedures, perform DDL/DML, expose raw definition text, or fall back from PPM to
PLF.

`resolve_dependency_reference` selects a deterministic target only when the full
candidate set has exactly one `CONFIRMED` + `HIGH` confidence candidate. Synonym,
caller-dependent, dynamic SQL, cross-server, ambiguous, and unresolved references
remain `REVIEW_REQUIRED` until catalog metadata uniquely confirms them.

`search_metadata_objects` is the query-aware metadata search capability for API
and UI consumers. It searches procedure/table/view/function identities through
the same read-only MCP boundary and returns only object identity, source
profile/database, snapshot/evidence refs, caveats, review-required state, and
blocker codes. It does not return row data, execute procedures, perform DDL/DML,
or expose SQL definition text. PPM `template_only` object-name suppression is
owned by the API layer; this MCP service remains a generic metadata service.

`check_database_exists` preserves profile boundaries: `dbProfileId=ppm` checks
PPM, `dbProfileId=plf` checks PLF, and only the `master` server metadata profile
may probe a different `databaseName`. PPM metadata must never fall back to PLF.

Live query failures return safe diagnostic fields only: tool name, profile id,
database, timeout seconds, attempt count, and error class. Error details must not
include SQL text, connection strings, credentials, row samples, or procedure
execution output. The adapter does not perform hidden retries; workflow-level retry
can use the standardized timeout/attempt details.

## 다음 구현 우선순위

1. P27 dependency evidence 를 실제 PPM catalog 사례에서 더 넓게 검증하고 residual `REVIEW_REQUIRED` 원인을 줄이기
2. 실제 MCP transport 연결
3. optional integration smoke 추가
4. PPM dependency caveat 감소를 위한 더 강한 metadata evidence 전략 검증

## 외부 DB 연결 주의

- metadata source DB 는 외부에서 관리한다.
- 이 저장소는 해당 DB 의 기동/중지, schema apply, row-data query 를 담당하지 않는다.
- 테스트는 fixture-first 를 기본으로 유지한다.
- live 연결은 **옵션** 이며, 연결되더라도 read-only metadata profile 만 사용한다.
