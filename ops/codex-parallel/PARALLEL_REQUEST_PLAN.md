# PARALLEL_REQUEST_PLAN.md

## 목적

이 계획은 Codex CLI를 **로컬 환경에서 병렬로 실행**할 때 파일 충돌과 계약 흔들림을 줄이기 위한 운영 기준이다.
핵심은 다음 세 가지다.

1. 공유 계약은 먼저 고정한다.
2. 병렬 트랙은 디렉터리 경계를 명확히 나눈다.
3. 통합은 웨이브 단위로 한다.

현재 기준 저장소에는 OpenAPI skeleton, Platform DB DDL draft, MCP catalog, validation rules, Java/MyBatis generation policy, Platform DB standardization policy, `.env.example`, Python lockfile, pnpm lockfile 이 존재한다. 병렬 작업은 이 자산을 새로 상상하지 말고 먼저 읽은 뒤 좁게 이어간다.

## 운영 원칙

- 메인 코디네이터 세션 1개 + 작업 worktree별 Codex 세션 N개로 운영한다.
- 각 세션은 고유 브랜치와 고유 worktree를 가진다.
- 다른 트랙이 소유한 파일은 읽을 수는 있어도 수정하지 않는다.
- 공유 계약 변경이 필요하면 임의 확장하지 말고 코디네이터에게 blocker로 올린다.
- worker는 구현을 시작할 때 수정 예정 파일, 검증 명령, blocker 후보를 먼저 정리한다.
- worker는 구현을 마치면 변경 파일, 검증 결과, 남은 리스크를 반드시 남긴다.
- 실제 secret 은 `.env`, `.env.local`, OS keychain 등 비커밋 경로에만 둔다. `.env.example` 은 비밀값 없는 샘플이다.

## 공유 계약 동결 범위

아래 경로는 **Wave 0** 에서 먼저 고정한다. 이후 worker는 원칙적으로 수정하지 않는다.

- `AGENTS.md`
- `PROJECT.md`
- `ARCHITECTURE.md`
- `TOOLS.md`
- `POLICY.md`
- `EVAL_SPEC.md`
- `TASK_TEMPLATE.md`
- `.codex/**`
- `.agents/**`
- `.env.example`
- `packages/domain/**`
- `spec/openapi/**`
- `spec/policy/**`
- `db/schema/**`
- `Makefile`
- `pyproject.toml`
- `docker/test/**`
- `requirements/lock/**`
- `pnpm-lock.yaml`
- 루트 `package.json`, workspace 설정 파일

`spec/mcp/**` 는 P01 의 소유 범위지만, API/OpenAPI 또는 domain 계약 변경이 필요한 경우에는 코디네이터 blocker 로 올린다.

## 웨이브 구성

### Wave 0 — 코디네이터 베이스라인 고정

목적:
- 저장소 기본 구조 고정
- 공통 명령과 품질 게이트 준비
- 공유 계약 파일과 정책 파일 drift 점검
- `packages/domain`, `spec/openapi`, `spec/policy`, `db/schema`, `.env.example`, lockfile 을 기준선으로 고정

트랙:
- `P00` Base/Foundation

완료되면 이후 worker는 공유 계약 파일을 **읽기 전용 기준선**으로 취급한다.

---

### Wave 1 — 병렬 독립 트랙

#### P01 — MSSQL Metadata MCP
- 역할: `mcp_engineer`
- 권장 프로필: `dev-edit`
- 소유 경로:
  - `services/mssql-mcp/**`
  - `spec/mcp/**`
  - `tests/contract/mcp/**`
  - `tests/unit/mcp/**`
  - `tests/unit/test_mcp_catalog.py`
  - `tests/unit/test_mssql_mcp_live_config.py`
  - `tests/contract/test_local_mssql_connection_assets.py`
  - `fixtures/mcp/**`
- 읽기 전용 참조:
  - `.env.example`
  - `config/mssql/local_docker_profiles.yaml`
  - `spec/policy/platform_db_standardization_rules_for_ai.json`
- 산출물:
  - read-only metadata tool registry
  - `get_procedure_definition`, `get_procedure_parameters`, `get_table_schema`, `search_tables` 우선 구현
  - fixture-backed contract tests
  - adapter boundary / error model
  - optional live metadata readiness 는 env-gated 유지

#### P02 — Domain Analysis Core
- 역할: `template_engineer`
- 권장 프로필: `dev-edit`
- 소유 경로:
  - `packages/analysis/**`
  - `tests/unit/analysis/**`
  - `fixtures/analysis/**`
- 읽기 전용 참조:
  - `packages/domain/**`
  - `fixtures/mssql/**`
  - `fixtures/metadata/**`
  - `spec/policy/platform_db_standardization_rules_for_ai.json`
- 산출물:
  - SP parser skeleton
  - dependency / pattern detector
  - canonical transform 준비 helper 또는 domain 확장 blocker
  - analysis fixtures and tests

#### P03 — Generation & Validation Core
- 역할: `template_engineer`
- 권장 프로필: `dev-edit`
- 소유 경로:
  - `packages/generation/**`
  - `packages/validation/**`
  - `spec/validation/**`
  - `tests/unit/generation/**`
  - `tests/unit/validation/**`
  - `fixtures/generation/**`
- 읽기 전용 참조:
  - `packages/domain/**`
  - `spec/openapi/**`
  - `spec/policy/**`
  - `db/schema/**`
- 산출물:
  - artifact renderers
  - validation engine
  - evidence coverage checker
  - Java/MyBatis golden sample regression
  - generator/validator tests

#### P04 — Web Portal Shell
- 역할: `platform_worker`
- 권장 프로필: `dev-edit`
- 소유 경로:
  - `apps/web/**`
  - `tests/unit/web/**`
- 읽기 전용 참조:
  - `spec/openapi/**`
  - `.env.example`
  - `PROJECT.md`, `ARCHITECTURE.md`, `POLICY.md`
- 산출물:
  - Next.js shell
  - request/job/artifact preview mock screens
  - validation/review state display
  - local mock data / UI smoke checks

병합 순서:
- `P01`, `P02`, `P03`, `P04` 는 서로 파일 경계가 다르면 순서와 무관하게 병합 가능
- 다만 검증은 가능하면 `make test`, `make test-web-smoke` 같은 도커 기반 명령을 사용한다.
- 단, `P04` 가 API 타입을 임의로 만들지 말고 mock adapter로 경계를 분리한다.

---

### Wave 2 — API / Workflow 통합

#### P05 — API Workflow & Artifact Service
- 역할: `platform_worker`
- 권장 프로필: `dev-edit`
- 선행 조건:
  - `P01`, `P02`, `P03` 병합 완료
- 소유 경로:
  - `apps/api/**`
  - `tests/integration/api/**`
  - `tests/unit/api/**`
- 읽기 전용 참조:
  - `packages/domain/**`
  - `packages/analysis/**`
  - `packages/generation/**`
  - `packages/validation/**`
  - `services/mssql-mcp/**`
  - `spec/openapi/**`
  - `spec/mcp/**`
  - `spec/validation/**`
  - `db/schema/**`
- 산출물:
  - request/job/artifact/validation/validation endpoints
  - metadata profile/tools and registry version stub endpoints
  - workflow state machine
  - in-memory 또는 stub repository adapters
  - integration tests

---

### Wave 3 — 통합 검증 / 문서 동기화

#### P06 — Integration / Eval / Docs
- 역할: `docs_curator` + `reviewer`
- 권장 프로필: `dev-edit`
- 선행 조건:
  - `P04`, `P05` 병합 완료
- 소유 경로:
  - `tests/e2e/**`
  - `tests/eval/**`
  - `fixtures/eval/**`
  - `docs/**`
  - 필요 시 루트 문서 동기화
- 읽기 전용 참조:
  - `apps/**`
  - `services/**`
  - `packages/**`
  - `spec/**`
  - `db/schema/**`
  - `ops/codex-parallel/**`
- 산출물:
  - end-to-end happy path smoke
  - eval fixtures / reports
  - docs sync
  - known gaps / follow-up backlog

#### P07 — Final Read-only Review
- 역할: `reviewer`
- 권장 프로필: `review`
- 선행 조건:
  - `P06` 완료
- 소유 경로:
  - 없음. 읽기 전용 검토만 수행
- 산출물:
  - correctness / policy / docs drift review memo
  - release gate findings
  - must-fix before merge 와 follow-up later 구분

## 병합 순서

1. `P00`
2. `P01`, `P02`, `P03`, `P04`
3. `P05`
4. `P06`
5. `P07`

## 작업 중지 조건

아래 상황이면 범위를 넓히지 말고 중지 후 보고한다.

- 공유 계약 변경이 필요한데 owner가 자신이 아님
- 다른 트랙의 target path 를 건드려야만 구현이 가능함
- 실제 DB 접근, 실제 데이터 조회, 자동 DDL 실행이 필요해짐
- repo 차원의 local DB lifecycle 관리가 필요해짐
- 테스트/실행 명령이 준비되지 않아 최소 검증조차 불가능함
- secret 을 샘플/문서/fixture/test snapshot 에 넣어야만 진행할 수 있어 보임

## Worker 공통 보고 형식

모든 worker는 마지막에 아래 형식으로 보고한다.

```md
## Changed Files
- ...

## What I Implemented
- ...

## Verification
- command: result
- command: result

## Open Risks / Blockers
- ...
```


---

## P07 이후 Productization Wave

P00~P07은 starter/MVP의 큰 틀과 운영 철학을 유지하는 기준선이다. P08A~P16은 같은 병렬 worktree 방식과 Docker 테스트 격리, read-only metadata, draft-only generation, validation/evidence/audit 원칙을 유지하면서 productization target으로 전환한다.

### Productization 고정 DB 역할

- `PLF` = platform DB
- `PPM` = pilot analysis target DB
- `PPM`이 없거나 접근 불가하면 PLF로 대체하지 않는다. 이 경우 pilot object selection은 blocker-dependent 또는 template-only로 유지한다.

### P08A — PPM Pilot Object Discovery & Selection

- 소유 경로: `fixtures/pilot/ppm_object_selection_v1/**`, 관련 contract test, P08A 실행에 필요한 최소 MCP metadata discovery surface
- 목적: PPM DB에서 representative SP/Table/View/Function 후보를 metadata-only 방식으로 선정한다.
- 기존 MCP surface가 부족하면 P10 전체를 당기지 않고 P08A 내부에서 DB 존재 확인, procedure/table/view/function inventory, definition/parameter/dependency/schema/index/constraint/extended property 조회에 필요한 최소 surface만 보강한다.
- live metadata 가능 시 `selected_objects.yaml` 을 `selection_mode: live_metadata`로 갱신한다.
- live metadata 불가 시 실제 object 이름을 만들지 않고 blocker 후보를 남긴다.

### P08 — Product Architecture & Release Backlog

- starter/MVP 상태를 production target gap matrix로 전환한다.
- skeleton/stub/fixture-first/optional-live/production-ready 상태를 구분한다.
- PPM pilot object set을 product milestone/eval 기준에 연결한다.
- 산출물은 `docs/productization-architecture-gap-analysis.md`, `PRODUCTIZATION_RELEASE_BACKLOG.md`, `fixtures/eval/productization_readiness_v1.yaml` 로 둔다.
- P08 이후 worker는 위 산출물을 읽고 acceptance criteria, verification command, blocker 기준을 먼저 확인한다.

### P09 — API & Workflow Productization

- request/job/artifact/validation/evidence/audit lifecycle을 product API 흐름으로 정리한다.
- idempotency, error model, pagination, status model, API consistency를 점검한다.
- PPM pilot object set 기반 request/job/artifact fixture를 설계한다.

### P10 — MSSQL Metadata MCP Productionization

- metadata tool coverage를 procedure/table/search 중심에서 dependency/index/constraint/extended property/view/function evidence까지 확장한다.
- read-only query guard, profile handling, fixture/live separation, timeout/retry/error handling을 강화한다.
- PPM pilot object set을 integration/eval 기준으로 사용한다.

### P11 — SP Analysis & Evidence Engine

- SP definition, parameter, result-set hint, dependency, call graph, transaction/exception/dynamic SQL/temp table pattern을 evidence-first로 분석한다.
- confidence/review_required/TODO/evidenceRefs 표준화를 강화한다.
- PPM pilot SP를 simple/medium/complex fixture 기준으로 사용한다.

### P12 — Java/MyBatis Generation Factory

- Mapper XML, Mapper Interface, Service, DTO/VO/Model 초안 생성을 policy/template registry 기반 factory로 정리한다.
- generation manifest, golden sample, diff/review checklist를 확장한다.
- 생성물은 draft-only이며 사람이 최종 검토/승인한다.

### P13 — Validation, Approval & Audit Productization

- validation result, quality caveat checklist, quality evidence log, audit event model을 제품 workflow로 정리한다.
- 재현 가능한 실행 기록과 evidence coverage를 강화한다.
- PPM pilot artifacts 기준 validation/review scenario를 설계한다.

### P14 — Web Product UI

- 중앙 통합형 단일 플랫폼 UI로 request, metadata search, job status, artifact preview, validation result, quality caveat 화면을 정리한다.
- mock-first + API adapter 구조를 유지한다.
- PPM pilot object set을 demo/search/sample request fixture로 활용한다.

### P15 — Evaluation, Observability, Security & Ops

- eval fixtures, quality metrics, latency budget, logging/monitoring/audit, secret handling, read-only permission checks, Docker/test reproducibility를 정리한다.
- PPM pilot object set 기반 smoke/eval scenario를 정의한다.

### P16 — Pilot Release Readiness

- PPM 대표 SP/Table 대상 시범 적용 준비 상태를 점검한다.
- 산출물 품질 보고서, release checklist, admin/user guide, handoff package를 만든다.
- selected object manifest가 template-only이면 live pilot release는 blocker-dependent로 판정한다.

## Productization merge order

1. `P08A`
2. `P08`
3. `P09`, `P10`, `P11`, `P12`는 manifest 의존성 기준으로 병렬/순차 실행
4. `P13`, `P14`, `P15`
5. `P16`
6. `P17A`~`P17D`는 P16 live release blocker closure
7. `P18A`, `P18B`는 P17 이후 production-ready gap closure

---

## P17 Live Pilot Blocker Closure Wave

P16 결과가 `NO_GO`이면 P17을 실행한다. P17은 P16을 뒤집기 위한 임의 문서 수정이 아니라, P16의 active blocker를 evidence-first로 닫는 후속 wave다. P17D가 모든 evidence gate를 검증하면 scoped live pilot candidate 만 `CONDITIONAL_GO` 로 바꿀 수 있다.

### P17 실행 순서

1. `P17A` — dependency metadata evidence closure
   - `DEPENDENCY_METADATA_INCOMPLETE` 해소가 목표다.
   - selected PPM SP의 table/view/function/procedure dependency를 metadata-only evidence refs로 확인한다.
   - selected table을 SP dependency로 주장하려면 catalog evidence가 있어야 한다.
   - raw definition text, row data, procedure execution은 금지한다.
2. `P17B` — live pilot artifact validation closure
   - P17A가 확인한 pilot object set으로 draft-only artifact와 validation evidence를 만든다.
   - live release candidate는 `PASSED` validation과 release-critical `REVIEW_REQUIRED` 없음이 필요하다.
3. `P17C` — draft quality and audit evidence binding
   - human `APPROVE`를 같은 artifact/version 및 validation report에 바인딩한다.
   - worker가 approval을 합성하거나 대리 생성하면 안 된다.
4. `P17D` — final GO/NO-GO decision update
   - P17A~P17C와 hard-live gate가 모두 통과하면 `CONDITIONAL_GO`로 바꿀 수 있다.
   - 하나라도 부족하면 `NO_GO`를 유지하고 remaining blocker를 보고한다.

### P17 hard-live 필수 검증

```bash
P15_HARD_LIVE_GATE=1 MSSQL_ENABLE_LIVE_METADATA=1 make test PYTEST_ARGS="tests/e2e tests/eval"
P15_HARD_LIVE_GATE=1 MSSQL_ENABLE_LIVE_METADATA=1 make test PYTEST_ARGS="tests/e2e tests/eval tests/contract"
```

PPM 접근 실패 시 PLF로 대체하지 않는다. P17도 전체 플랫폼을 production-ready로 선언하지 않고, 조건부 pilot release candidate의 evidence 충족 여부만 판단한다.

---

## P18 Productization Gap Closure Wave

P17D 이후에도 전체 플랫폼은 production-ready 가 아니다. P18은 P17의 scoped `CONDITIONAL_GO` 범위 밖에 남은 두 productization gap 을 닫거나 deferred future hardening item 으로 정확히 분류하는 후속 wave 다.

### P18 실행 순서

1. `P18A` — CanonicalAnalysisModel contract closure
   - `CanonicalAnalysisModel-compatible-local-v0.2` 후보를 명시적 domain contract 로 승격하거나, 누락 필드를 정확한 blocker 로 기록한다.
   - release-critical canonical field 는 observed evidence 또는 `REVIEW_REQUIRED` blocker 로 귀결한다.
   - dynamic SQL, incomplete dependency, 근거 약한 inference 는 확정값으로 만들지 않는다.
2. `P18B` — Web HTTP adapter and auth/RBAC evidence closure
   - 기존 `PORTAL_API_MODE=http` 경로를 local API route smoke 로 검증 가능한 release evidence 로 만든다.
   - mock adapter 는 demo/dev 기본값으로 유지하되 release evidence 와 구분한다.
   - production auth/RBAC source of truth 가 없으면 `AUTH_RBAC_PRODUCTION_SOURCE_UNRESOLVED` blocker 를 유지한다. Source 는 문서화되었지만 live IdP/JWKS/PLF wiring 이 없으면 production-grade enterprise Auth/RBAC claim 전 deferred future hardening 으로 분류한다.

### P18 검증

```bash
make test PYTEST_ARGS="tests/unit/analysis tests/eval tests/contract"
python3.14 -m compileall packages/analysis packages/domain tests
make test PYTEST_ARGS="tests/integration/api tests/e2e tests/eval"
make test-web-smoke
make test
make test PYTEST_ARGS="tests/e2e tests/eval tests/contract"
python3.14 -m compileall apps services packages tests
```

P18도 row data, procedure execution, raw definition text 저장, 자동 DDL/DML, PLF fallback, 승인 없는 publish/export 를 허용하지 않는다. production auth/RBAC 를 mock header 로 가장해야만 통과할 수 있다면 productization decision 은 `NO_GO` 로 유지한다. Live wiring 미검증만 남은 경우에는 controlled `CONDITIONAL_GO` 와 deferred future hardening 으로 분리한다.
