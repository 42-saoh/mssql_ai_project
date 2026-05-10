# P21D Eval Docs Readiness

## 공통 운영 철학

- 현재 대화 요청과 실제 파일 구조를 최우선 기준으로 삼는다.
- P17 scoped live pilot `CONDITIONAL_GO` 와 P20 Auth/RBAC live wiring deferred posture 를 보존한다.
- `production_ready: false` 를 유지한다.
- `PLF` 는 platform DB, `PPM` 은 pilot analysis target DB 이며, PPM 접근 실패 시 PLF fallback 은 금지한다.
- row data, procedure execution, business DB DDL/DML, publish/export/deployment, secret 저장은 금지한다.
- Python 3.14 를 active reproducibility baseline 으로 문서화한다.

## 목표

P21 no-mock functional portal 계약, live gate, prompt pack, readiness 문서를 동기화한다. P21 은 controlled live app 전환이며 full production-ready enterprise Auth/RBAC 주장이 아니다.

## 읽어야 할 기준 파일

- `PROJECT.md`
- `ARCHITECTURE.md`
- `TOOLS.md`
- `POLICY.md`
- `EVAL_SPEC.md`
- `apps/api/README.md`
- `apps/web/README.md`
- `docs/**`
- `fixtures/eval/**`
- `tests/eval/**`
- `tests/contract/**`
- `ops/codex-parallel/**`

## 허용 수정 경로

- `fixtures/eval/live_portal_no_mock_p21_v1.yaml`
- `tests/eval/**`
- `tests/contract/**`
- `docs/**`
- `apps/api/README.md`
- `apps/web/README.md`
- `fixtures/eval/README.md`
- `tests/eval/README.md`
- `ops/codex-parallel/**`
- `.env.example`

## 금지 경로

- `services/mssql-mcp/**` 구현 변경
- `packages/**` 구현 변경
- `db/schema/**`
- `config/mssql/local_docker_profiles.yaml`
- `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml`
- token/secret/raw JWT claims/PLF row data 저장
- mock auth/RBAC production claim
- PLF fallback for PPM

## 구현 범위

- `fixtures/eval/live_portal_no_mock_p21_v1.yaml` 를 기존 파일 기준으로 갱신하고 Python 3.14, PLF required, PPM required, Web HTTP API only, `production_ready: false` 를 명시한다.
- P21 functional pages `/`, `/requests/new`, `/metadata/search`, `/jobs/[jobId]`, `/artifacts/[artifactId]`, `/review/decision` 를 fixture 에 선언한다.
- `tests/contract/test_p21_no_mock_prompt_assets.py` 를 기존 파일 기준으로 유지/갱신해 prompt/manifest/fixture/docs/env/compose/no-mock 계약을 검증한다.
- `tests/eval/test_p21_live_portal_no_mock_gate.py` 를 기존 파일 기준으로 갱신해 default skip without PLF/PPM access, live prerequisite blocker failure, explicit live pass path 를 검증한다.
- 문서에서 이전 Python active baseline 을 Python 3.14 로 교체한다.
- Auth/RBAC live wiring 은 production-grade enterprise Auth/RBAC 주장 전 요구사항으로 남기되 current controlled open blocker 로 만들지 않는다.

## 검증 명령

- `python3.14 -m compileall apps services packages tests`
- `make test PYTEST_ARGS="tests/eval/test_p21_live_portal_no_mock_gate.py tests/contract/test_p21_no_mock_prompt_assets.py tests/eval"`
- `make test-web-smoke`

## Blocker 보고 기준

- P21 fixture 가 `production_ready: true` 또는 full production-ready 를 주장함
- P21 live portal gate 가 missing PLF/PPM 을 skip 처리함
- docs/manifest/env sample 이 Python 3.14 또는 P21 env 이름과 불일치함
- Web no-mock/runtime HTTP contract 를 테스트가 검증하지 못함
- live 검증 성공 없이 P21 live gate evidence 를 성공으로 기록함
