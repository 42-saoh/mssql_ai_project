# 관리자 가이드

## 현재 관리 대상
- DB profiles
- prompt / template / model versions
- user roles
- approval policy
- audit log

## 현재 구현 상태

- implemented: API route surface, workflow state 기록, validation report 저장, approval decision 기록, audit event 기록.
- fixture-first: metadata collection 과 e2e/eval 기본 경로.
- stub/skeleton: publish route, full registry admin.
- optional live: MSSQL MCP readiness probe. live metadata query execution 은 아직 completed feature 가 아니다.
- follow-up: published version 승격 UI/API, live auth/RBAC wiring verification, live read-only metadata adapter.
- not production-ready: P17D live pilot release 와 P18/P19 opening posture 는 scoped/controlled CONDITIONAL_GO 이며, P20 live IdP/JWKS 와 운영 PLF role membership 검증 전까지 production-grade enterprise Auth/RBAC 또는 `production_ready: true` 로 보지 않는다.
- auth/RBAC source: production actor identity 는 verified OIDC/JWT 이고 role source 는 PLF `AUTH_USERS`, `AUTH_ROLES`, `AUTH_USER_ROLES` 이다. 상세 기준은 `docs/admin-guide/auth-rbac-production-source.md` 를 따른다.

## 기본 운영 절차
1. `.env.example` 을 기준으로 `.env` 를 만들고 비밀값은 커밋하지 않는다.
2. `config/mssql/local_docker_profiles.yaml` 에서 metadata 기본 profile `master` 와 platform profile `plf` 을 확인한다.
3. schema 변경이 필요하면 `db/schema/` 에 versioned SQL 만 추가하고 실제 DB 적용은 외부 운영자가 수동 수행한다.
4. 검증은 `make test PYTEST_ARGS="tests/e2e tests/eval"` 과 필요한 경우 `make test`, `make test-web-smoke` 로 수행한다.
5. approval decision 은 현재 기록 기능이며 publish 나 배포를 자동 수행하지 않는다.
6. Web HTTP adapter route smoke 는 `python3 tests/e2e/web_http_adapter_smoke.py` 로 실행한다. 이 검증은 fixture-backed local API route evidence 이며 production auth/RBAC evidence 가 아니다.
7. Auth/RBAC route enforcement 검증은 `make test PYTEST_ARGS="tests/integration/api/test_api_auth_rbac.py"` 로 실행한다. 이 검증은 runtime-generated JWT 와 fixture PLF role repository 를 사용하며 운영 IdP/JWKS 검증을 대체하지 않는다.

## P15 hard-live eval 운영

- 기본 eval 은 fixture-first 재현성을 유지하며 live PPM 을 호출하지 않는다.
- P15 hard-live eval 은 `P15_HARD_LIVE_GATE=1`, `MSSQL_ENABLE_LIVE_METADATA=1`, `ppm` profile 의 `PPM` read-only metadata 접근을 요구한다.
- PPM 접근 실패, metadata 권한 부족, live 연결 부재는 blocker 이며 PLF 로 대체하지 않는다.
- read-only permission check 는 database 존재/접근성, procedure/table/view/function inventory, procedure dependency, table schema metadata 를 확인한다.
- latency 는 PPM readiness, metadata inventory smoke, fixture workflow smoke 로 나누어 측정하며 현재 live gate 와 product target 을 구분한다.
- correlation id 는 request/job/metadata/artifact/validation/approval/audit 문맥에 전달되어야 한다.
- 로그와 audit 에 connection string, credential, cookie, raw definition text, row data 를 남기지 않는다.

## P16/P17 pilot readiness 운영

- P16 readiness package 는 `docs/pilot-release-readiness.md`, `ops/codex-parallel/P16_PILOT_RELEASE_HANDOFF.md`, `fixtures/eval/pilot_release_readiness_p16_v1.yaml` 을 기준으로 검토한다.
- 현재 PPM manifest 는 `live_metadata` 이므로 대표 object identity 를 문서와 fixture 에 참조할 수 있다.
- P17A 는 selected stored procedure suite majority 기준으로 `DEPENDENCY_METADATA_INCOMPLETE` 를 닫았지만, selected table 은 confirmed `related_procedures` evidence 가 있을 때만 selected procedure dependency 로 주장한다.
- P17D 이후 live pilot release 는 scoped draft-only candidate 에 한해 CONDITIONAL_GO 이며, fixture-first/demo handoff 는 계속 GO WITH LIMITATIONS 이다.
- live pilot 조건을 유지하려면 PPM hard-live 검증, passed validation, human `APPROVE`, audit trace 가 같은 artifact/version 에 묶여야 한다.
- P18/P19 productization readiness 는 `fixtures/eval/productization_gap_closure_p18_v1.yaml` 의 HTTP adapter smoke evidence, auth/RBAC source 문서화, fixture-backed enforcement 를 반영해 controlled conditional open 으로 해석한다. Live IdP/JWKS 와 PLF role lookup 검증은 production-grade enterprise Auth/RBAC claim 전 future hardening 이다.

## 스키마 변경 운영

- 플랫폼 DB 구조 변경이 필요하면 `db/schema/` 에 versioned SQL 파일을 추가한다.
- 실제 DB 적용은 관리자/운영자가 외부 DB 환경에 수동으로 수행한다.
- 저장소의 Makefile/Codex 작업은 DB apply 를 수행하지 않는다.
- SQL Server lifecycle, schema apply, row-data 조회/수정은 저장소 책임이 아니다.
