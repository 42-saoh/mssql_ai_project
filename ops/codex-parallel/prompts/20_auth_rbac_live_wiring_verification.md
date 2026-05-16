# P20 Auth/RBAC Live Wiring Verification

## 공통 운영 철학

- 현재 대화 요청과 실제 파일 구조를 최우선 기준으로 삼는다.
- P17의 scoped live pilot `CONDITIONAL_GO`는 유지하되, 전체 플랫폼 production-ready 로 과장하지 않는다.
- `PLF` 는 platform DB, `PPM` 은 pilot analysis target DB 이다. PPM 이 없거나 접근 불가하면 PLF 로 대체하지 않고 blocker 로 보고한다.
- 실제 row data 조회, procedure execution, 자동 DDL/DML, 운영 DB 직접 변경, 승인 없는 publish/export 자동화는 금지한다.
- OIDC/JWT token, secret, raw JWT claims, `AUTH_USERS` row dump, password, 실데이터를 코드/문서/fixture/test snapshot 에 넣지 않는다.
- Production auth/RBAC 를 mock header, 하드코딩 actor, fixture token 으로 가장하지 않는다.
- Live 검증이 실패하거나 실행 조건이 없으면 blocker 를 닫지 말고 원인별 blocker 로 보고한다.
- 첫 응답에는 수정 예정 파일, 검증 명령, blocker 후보를 짧게 제시한다.

## 목표

P19의 fixture-backed auth/RBAC enforcement 이후 남은 `AUTH_RBAC_LIVE_IDP_PLF_WIRING_UNVERIFIED` 를 승인된 live-like 환경에서 검증할 hard-live gate 를 추가한다.

`AUTH_RBAC_LIVE_GATE=1` 일 때만 IdP/JWKS token verification 과 PLF role lookup 을 수행한다. 기본 테스트는 fixture-first 로 유지하고, live gate 가 명시되지 않으면 운영 IdP/JWKS 또는 PLF 에 접근하지 않는다.

## 읽어야 할 기준 파일

- `ARCHITECTURE.md`
- `POLICY.md`
- `EVAL_SPEC.md`
- `apps/api/README.md`
- `apps/api/api_app/auth.py`
- `apps/api/api_app/dependencies.py`
- `apps/api/api_app/platform_db.py`
- `docs/admin-guide/auth-rbac-production-source.md`
- `fixtures/eval/productization_gap_closure_p18_v1.yaml`
- `tests/integration/api/test_api_auth_rbac.py`
- `tests/eval/**`
- `tests/contract/**`

## 허용 수정 경로

- `apps/api/**`
- `tests/eval/**`
- `tests/contract/**`
- `fixtures/eval/productization_gap_closure_p18_v1.yaml`
- `docs/admin-guide/**`
- `docs/user-guide/**`
- `docs/integration-eval-status.md`
- `.env.example` 은 secret 값 없이 env name 문서화만 허용

## 금지 경로

- `services/mssql-mcp/**`
- `packages/**`
- `db/schema/**`
- `spec/**`
- `config/mssql/local_docker_profiles.yaml`
- `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml`
- 실제 token/secret/raw JWT claims/PLF row data 저장
- validation route 호출로 운영 workflow write 또는 audit write 생성
- publish/export, deployment, DDL/DML, row data, procedure execution, PLF fallback

## 구현 범위

- `tests/eval/test_p20_auth_rbac_live_gate.py` 를 추가한다.
  - 기본 실행에서는 skip 한다.
  - `AUTH_RBAC_LIVE_GATE=1` 인데 필수 env 가 없으면 skip 이 아니라 blocker failure 로 처리한다.
- `apps/api/scripts/auth_rbac_live_probe.py` 또는 동등한 read-only helper 를 추가한다.
  - `OidcJwtVerifier` 와 `MssqlPlatformRepository.resolve_actor_roles()` 만 사용한다.
  - API validation route 를 호출하지 않는다.
  - workflow write, validation write, audit write 를 만들지 않는다.
- 필수 env name 은 아래로 고정한다.
  - `AUTH_RBAC_LIVE_GATE=1`
  - `AUTH_RBAC_ENFORCEMENT=1`
  - `OIDC_ISSUER`
  - `OIDC_AUDIENCE`
  - `OIDC_JWKS_URL`
  - `OIDC_USER_BEARER_TOKEN`
  - 기존 `PLATFORM_DB_*`
- 기대 검증은 아래로 제한한다.
  - user token 이 JWKS 로 검증되고 PLF actor 로 매핑된다.
  - missing/invalid token 은 401 semantics 를 유지한다.
  - mapped actor with insufficient role 은 403 semantics 를 유지한다.
  - 출력은 pass/fail, role category, blocker code, redacted summary 만 포함한다.
- 성공 시에만 `fixtures/eval/productization_gap_closure_p18_v1.yaml` 에 live wiring evidence 를 기록한다.
- 실패하거나 live gate 를 실행할 수 없으면 `AUTH_RBAC_LIVE_IDP_PLF_WIRING_UNVERIFIED` 를 유지하고 정확한 prerequisites 를 보고한다.

## 검증 명령

- `make test PYTEST_ARGS="tests/integration/api tests/e2e tests/eval"`
- `make test-web-smoke`
- `python3.14 -m compileall apps/api tests`
- Live gate:
  - `AUTH_RBAC_LIVE_GATE=1 AUTH_RBAC_ENFORCEMENT=1 make test PYTEST_ARGS="tests/eval/test_p20_auth_rbac_live_gate.py"`

## Blocker 보고 기준

- 승인된 IdP/JWKS endpoint 가 없거나 `OIDC_ISSUER`, `OIDC_AUDIENCE`, `OIDC_JWKS_URL` 이 불일치함
- user live token 을 안전한 local environment 또는 secret manager 로 주입할 수 없음
- user token 이 PLF actor 로 매핑되지 않음
- PLF `AUTH_USERS`, `AUTH_ROLES`, `AUTH_USER_ROLES` lookup 이 실패하거나 canonical role name 과 불일치함
- GO 판정을 위해 token/secret/raw claims/PLF row dump 저장, row data, procedure execution, DDL/DML, workflow write, audit write, PLF fallback, auto publish/export 가 필요함
