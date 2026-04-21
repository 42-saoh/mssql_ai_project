# PARALLEL_REQUEST_PLAN.md

## 목적

이 계획은 Codex CLI를 **로컬 환경에서 병렬로 실행**할 때 파일 충돌과 계약 흔들림을 줄이기 위한 운영 기준이다.
핵심은 다음 세 가지다.

1. 공유 계약은 먼저 고정한다.
2. 병렬 트랙은 디렉터리 경계를 명확히 나눈다.
3. 통합은 웨이브 단위로 한다.

## 운영 원칙

- 메인 코디네이터 세션 1개 + 작업 worktree별 Codex 세션 N개로 운영한다.
- 각 세션은 고유 브랜치와 고유 worktree를 가진다.
- 다른 트랙이 소유한 파일은 읽을 수는 있어도 수정하지 않는다.
- 공유 계약 변경이 필요하면 임의 확장하지 말고 코디네이터에게 blocker로 올린다.
- worker는 구현을 마치면 변경 파일, 검증 결과, 남은 리스크를 반드시 남긴다.

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
- `packages/domain/**`
- `spec/openapi/**`
- `db/schema/**`
- `Makefile`
- `pyproject.toml`
- `docker/test/**`
- 루트 `package.json`, workspace 설정 파일

## 웨이브 구성

### Wave 0 — 코디네이터 베이스라인 고정

목적:
- 저장소 기본 구조 고정
- 공통 명령과 품질 게이트 준비
- 공유 계약 파일 고정
- `packages/domain`, `spec/openapi`, `db/schema` 를 기준선으로 배치

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
  - `fixtures/mcp/**`
- 산출물:
  - read-only metadata tool registry
  - tool input/output schema implementation
  - fixture-backed contract tests
  - adapter boundary / error model

#### P02 — Domain Analysis Core
- 역할: `template_engineer`
- 권장 프로필: `dev-edit`
- 소유 경로:
  - `packages/analysis/**`
  - `tests/unit/analysis/**`
  - `fixtures/analysis/**`
- 읽기 전용 참조:
  - `packages/domain/**`
- 산출물:
  - SP parser skeleton
  - dependency / pattern detector
  - canonical transform helpers
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
- 산출물:
  - artifact renderers
  - validation engine
  - evidence coverage checker
  - generator/validator tests

#### P04 — Web Portal Shell
- 역할: `platform_worker`
- 권장 프로필: `dev-edit`
- 소유 경로:
  - `apps/web/**`
  - `tests/unit/web/**`
- 읽기 전용 참조:
  - `spec/openapi/**`
  - `PROJECT.md`, `ARCHITECTURE.md`
- 산출물:
  - Next.js shell
  - request/job/artifact preview mock screens
  - local mock data / UI smoke checks

병합 순서:
- `P01`, `P02`, `P03`, `P04` 는 서로 파일 경계가 다르면 순서와 무관하게 병합 가능
- 다만 검증은 가능하면 `make test`, `make test-web-smoke` 같은 도커 기반 명령을 사용한다.
- 단, `P04` 가 API 타입을 임의로 만들지 말고 mock adapter로 경계를 분리한다

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
  - `spec/openapi/**`
  - `db/schema/**`
- 산출물:
  - request/job/artifact/approval endpoints
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
