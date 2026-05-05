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
  - request/job/artifact/validation/approval endpoints
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

P00~P07은 starter/MVP의 큰 틀과 운영 철학을 유지하는 기준선이다. P08A~P16은 같은 병렬 worktree 방식과 Docker 테스트 격리, read-only metadata, draft-only generation, validation/approval/audit 원칙을 유지하면서 productization target으로 전환한다.

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

- request/job/artifact/validation/approval/audit lifecycle을 product API 흐름으로 정리한다.
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

- validation result, reviewer checklist, approval decision log, audit event model을 제품 workflow로 정리한다.
- 재현 가능한 실행 기록과 evidence coverage를 강화한다.
- PPM pilot artifacts 기준 validation/review scenario를 설계한다.

### P14 — Web Product UI

- 중앙 통합형 단일 플랫폼 UI로 request, metadata search, job status, artifact preview, validation result, approval/review 화면을 정리한다.
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
