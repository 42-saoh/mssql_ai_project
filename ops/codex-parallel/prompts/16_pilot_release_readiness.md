# P16 Pilot Release Readiness


## 공통 운영 철학

- 현재 대화 요청과 첨부 ZIP의 실제 파일 구조를 최우선 기준으로 삼는다.
- P00~P07의 worktree 병렬 개발, Docker 테스트 격리, read-only metadata, draft-only generation, validation/approval/audit 원칙을 유지한다.
- `PLF` 는 platform DB, `PPM` 은 pilot analysis target DB 이다. PPM 이 없거나 접근 불가하면 PLF 로 대체하지 않고 blocker 로 보고한다.
- 실제 row data 조회, procedure 실행, 자동 DDL/DML, 운영 DB 직접 변경, 승인 없는 배포 자동화는 금지한다.
- 비밀값, 실제 비밀번호, 토큰, 실데이터는 코드/문서/fixture/test snapshot 에 넣지 않는다.
- skeleton/stub/fixture-first/optional-live/production-ready 상태를 구분해서 기록한다.
- 공유 contract/policy/common 파일 수정이 필요하면 worker가 임의로 수정하지 말고 coordinator에게 blocker로 보고한다.
- 첫 응답에는 수정 예정 파일, 검증 명령, blocker 후보를 짧게 제시한다.


## 목표

PPM 대표 SP/Table 대상 시범 적용 준비 상태를 점검하고, 산출물 품질 보고서, 한계/개선사항, release checklist, admin/user guide, handoff package를 만든다.

## 읽어야 할 기준 파일

- `README.md`, `PROJECT.md`, `ARCHITECTURE.md`, `TOOLS.md`, `POLICY.md`, `EVAL_SPEC.md`
- `docs/**`
- `ops/codex-parallel/**`
- `fixtures/eval/**`
- `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml`
- `tests/e2e/**`
- `tests/eval/**`
- `apps/**`, `services/**`, `packages/**`, `spec/**`, `db/schema/**` 는 읽기 전용 검토

## 허용 수정 경로

- `docs/**`
- `fixtures/eval/**`
- `ops/codex-parallel/**`
- `tests/eval/**`

## 금지 경로

- `apps/**`
- `services/**`
- `packages/**`
- `spec/**`
- `db/schema/**`
- `.env.example`에 secret 추가
- `config/mssql/local_docker_profiles.yaml` 임의 변경
- `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml`

## 구현 범위

- P08A~P15 산출물을 기준으로 pilot release readiness checklist를 작성한다.
- PPM pilot object manifest가 `live_metadata`이면 대표 SP/Table/View/Function 기준 적용 결과를 평가한다.
- manifest가 `template_only`이면 live pilot release는 blocker-dependent로 판정하고 실제 object name을 만들지 않는다.
- 산출물 품질 보고서에는 evidence coverage, validation result, review_required, known limitations, manual approval status를 포함한다.
- admin/user guide는 실제 구현된 기능과 stub/fixture/optional-live 기능을 구분한다.
- go/no-go 기준을 정책 위반, 검증 실패, live metadata blocker, 승인 누락 중심으로 정리한다.

## 검증 명령

- `make test`
- `make test-web-smoke`
- `make test PYTEST_ARGS="tests/e2e tests/eval tests/contract"`
- `python -m compileall apps services packages tests`

## Blocker 보고 기준

- PPM 대표 object set이 template-only라 live pilot release를 판단할 수 없음
- PPM DB 없음, 접근 권한 없음, metadata read-only 권한 부족
- SP definition/dependency metadata 불완전
- validation/approval/audit evidence가 release gate 통과 기준에 미달
- 자동 DDL/운영 DB 변경/무승인 publish 같은 금지 흐름이 요구됨
- 문서가 production-ready로 주장하지만 구현 근거가 skeleton/stub/fixture-first에 그침
