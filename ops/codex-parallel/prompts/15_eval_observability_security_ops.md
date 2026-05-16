# P15 Evaluation, Observability, Security & Ops


## 공통 운영 철학

- 현재 대화 요청과 첨부 ZIP의 실제 파일 구조를 최우선 기준으로 삼는다.
- P00~P07의 worktree 병렬 개발, Docker 테스트 격리, read-only metadata, draft-only generation, validation/evidence/audit 원칙을 유지한다.
- `PLF` 는 platform DB, `PPM` 은 pilot analysis target DB 이다. PPM 이 없거나 접근 불가하면 PLF 로 대체하지 않고 blocker 로 보고한다.
- 실제 row data 조회, procedure 실행, 자동 DDL/DML, 운영 DB 직접 변경, 승인 없는 배포 자동화는 금지한다.
- 비밀값, 실제 비밀번호, 토큰, 실데이터는 코드/문서/fixture/test snapshot 에 넣지 않는다.
- skeleton/stub/fixture-first/optional-live/production-ready 상태를 구분해서 기록한다.
- 공유 contract/policy/common 파일 수정이 필요하면 worker가 임의로 수정하지 말고 coordinator에게 blocker로 보고한다.
- 첫 응답에는 수정 예정 파일, 검증 명령, blocker 후보를 짧게 제시한다.


## 목표

eval fixtures, representative pilot scenarios, quality metrics, latency/performance budget, logging/monitoring, audit log, secret handling, read-only DB permission checks, Docker/test reproducibility, 운영 문서를 productization한다.

## 읽어야 할 기준 파일

- `PROJECT.md`, `ARCHITECTURE.md`, `TOOLS.md`, `POLICY.md`, `EVAL_SPEC.md`
- `docs/productization-architecture-gap-analysis.md`
- `ops/codex-parallel/PRODUCTIZATION_RELEASE_BACKLOG.md`
- `fixtures/eval/productization_readiness_v1.yaml`
- `.env.example`
- `Makefile`
- `docker/test/**`
- `scripts/**`
- `requirements/lock/py314-dev.txt`
- `pnpm-lock.yaml`
- `fixtures/eval/**`
- `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml`
- `docs/**`
- `tests/e2e/**`
- `tests/eval/**`

## 허용 수정 경로

- `fixtures/eval/**`
- `tests/eval/**`
- `tests/e2e/**`
- `docs/**`
- `ops/codex-parallel/**`
- `docker/test/**`

## 금지 경로

- `apps/**`
- `services/**`
- `packages/**`
- `spec/**`
- `db/schema/**`
- `.env.example` 비밀값 추가
- `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml`

## 구현 범위

- PPM pilot object set 기반 smoke/eval scenario를 정의한다. template-only이면 live eval은 blocker-dependent로 표시한다.
- 품질 지표: evidence coverage, review_required ratio, validation pass rate, generation reproducibility, draft artifact completeness를 정의한다.
- latency/performance budget은 product target과 current stub/fixture baseline을 구분한다.
- logging/monitoring/audit 문서는 secret redaction과 correlation id를 포함한다.
- read-only DB permission check 절차를 문서화한다.
- Docker/test reproducibility와 worktree port strategy를 점검한다.
- 실제 운영 배포 자동화를 추가하지 않는다.

## 검증 명령

- `make test PYTEST_ARGS="tests/e2e tests/eval"`
- `python3.14 -m compileall tests`
- `bash -n scripts/*.sh`
- 필요 시 `make test PYTEST_ARGS="tests/contract"`

## Blocker 보고 기준

- live PPM eval이 필요한데 PPM DB/권한/live 연결이 없음
- secret redaction 또는 audit logging 요구가 현재 contract 변경을 요구함
- Docker/test reproducibility가 host 환경 의존성 때문에 보장 불가
- latency/performance 측정을 위한 instrumentation이 앱/서비스 변경을 요구함
- 보안 정책과 실제 구현이 충돌
