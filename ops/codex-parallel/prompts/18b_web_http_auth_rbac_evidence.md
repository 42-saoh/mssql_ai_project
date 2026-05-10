# P18B Web HTTP Adapter And Auth/RBAC Evidence Closure

## 공통 운영 철학

- 현재 대화 요청과 실제 파일 구조를 최우선 기준으로 삼는다.
- P17의 scoped live pilot `CONDITIONAL_GO`는 유지하되, 전체 플랫폼 production-ready 로 과장하지 않는다.
- `PLF` 는 platform DB, `PPM` 은 pilot analysis target DB 이다. PPM 이 없거나 접근 불가하면 PLF 로 대체하지 않고 blocker 로 보고한다.
- 실제 row data 조회, procedure execution, 자동 DDL/DML, 운영 DB 직접 변경, 승인 없는 publish/export 자동화는 금지한다.
- 비밀값, 실제 비밀번호, 토큰, 실데이터, raw SQL definition text 는 코드/문서/fixture/test snapshot 에 넣지 않는다.
- production auth/RBAC 를 mock header 나 하드코딩 actor 로 가장하지 않는다. 출처가 불명확하면 blocker 로 남긴다.
- 첫 응답에는 수정 예정 파일, 검증 명령, blocker 후보를 짧게 제시한다.

## 목표

기존 `PORTAL_API_MODE=http` 경계를 release evidence 로 만들 수 있도록 web-to-API HTTP smoke 를 추가하고, production auth/RBAC 는 구현 증거 또는 명시적 blocker 로 정리한다. 인증/권한 source of truth 가 확정되지 않았으면 `AUTH_RBAC_PRODUCTION_SOURCE_UNRESOLVED` 를 유지한다.

## 읽어야 할 기준 파일

- `ARCHITECTURE.md`
- `POLICY.md`
- `EVAL_SPEC.md`
- `apps/web/README.md`
- `apps/api/README.md`
- `apps/web/lib/api/portal-api.ts`
- `apps/web/lib/api/http-client.ts`
- `apps/web/lib/api/mock-adapter.ts`
- `fixtures/eval/productization_gap_closure_p18_v1.yaml`
- `tests/unit/web/**`, `tests/integration/api/**`, `tests/e2e/**`, `tests/eval/**`

## 허용 수정 경로

- `apps/web/**`
- `apps/api/**`
- `fixtures/eval/productization_gap_closure_p18_v1.yaml`
- `tests/unit/web/**`
- `tests/integration/api/**`
- `tests/e2e/**`
- `tests/eval/**`
- `docs/admin-guide/**`
- `docs/user-guide/**`
- `docs/integration-eval-status.md`

## 금지 경로

- `services/mssql-mcp/**`
- `packages/domain/**`
- `packages/analysis/**`
- `packages/generation/**`
- `packages/validation/**`
- `spec/**`
- `db/schema/**`
- `.env.example`에 secret 추가
- `config/mssql/local_docker_profiles.yaml` 임의 변경
- `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml`
- fake production auth/RBAC, row data, procedure execution, raw definition text 저장

## 구현 범위

- HTTP adapter 가 `PortalApi` interface 의 request/job/artifact/validation/approval/metadata/registry 경로를 모두 호출하는지 smoke 로 증명한다.
- mock adapter 는 demo/dev 기본값으로 유지하되, release evidence 와 혼동하지 않게 문서화한다.
- production actor identity source, role source, role-to-action matrix 가 없으면 `AUTH_RBAC_PRODUCTION_SOURCE_UNRESOLVED` blocker 를 유지한다.
- 권한 구현을 추가하는 경우 validation/approval action 의 unauthorized negative test 를 포함한다.
- UI/API 경로가 publish/export, deployment, DDL/DML, row data, procedure execution, PLF fallback 을 암시하거나 수행하지 않게 한다.

## 검증 명령

- `make test PYTEST_ARGS="tests/integration/api tests/e2e tests/eval"`
- `make test-web-smoke`
- `python3.14 -m compileall apps/api tests`
- 승인된 로컬 dev server 를 사용한 web-to-API smoke 가 있으면 해당 명령을 추가로 실행한다.

## Blocker 보고 기준

- production auth/RBAC source of truth 가 확정되지 않음
- HTTP smoke 가 local API route 를 통과하지 못함
- mock-only evidence 로 production readiness 를 주장해야 함
- GO 판정을 위해 row data, procedure execution, raw definition text 저장, PLF fallback, auto publish/export 가 필요함
