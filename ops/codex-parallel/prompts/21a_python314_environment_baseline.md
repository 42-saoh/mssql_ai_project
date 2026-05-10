# P21A Python 3.14 Environment Baseline

## 공통 운영 철학

- 현재 대화 요청과 실제 파일 구조를 최우선 기준으로 삼는다.
- P20 Auth/RBAC live IdP/JWKS wiring 은 deferred future hardening 으로 유지한다.
- `production_ready: false` 를 유지하고, controlled open 과 full production-ready 를 혼동하지 않는다.
- `PLF` 는 platform DB, `PPM` 은 pilot analysis target DB 이다. PPM 이 없거나 접근 불가하면 PLF 로 대체하지 않는다.
- row data 조회, procedure execution, 자동 DDL/DML, publish/export, deployment 자동화는 금지한다.
- Python 3.14 를 현재 host+Docker 테스트 기준으로 둔다.

## 목표

P21 전체 작업의 실행 기반을 Python 3.14 로 고정한다. Host 명령, Docker test image, lock file, pyproject, Ruff target, 문서 재현성 기준이 모두 `python3.14` 와 `requirements/lock/py314-dev.txt` 를 가리키게 한다.

## 읽어야 할 기준 파일

- `PROJECT.md`
- `TOOLS.md`
- `EVAL_SPEC.md`
- `Makefile`
- `pyproject.toml`
- `docker/test/**`
- `requirements/lock/**`
- `ops/codex-parallel/REQUEST_MANIFEST.yaml`
- `tests/contract/**`

## 허용 수정 경로

- `Makefile`
- `pyproject.toml`
- `docker/test/**`
- `requirements/lock/**`
- `.env.example`
- `PROJECT.md`
- `TOOLS.md`
- `EVAL_SPEC.md`
- `docs/**`
- `ops/codex-parallel/**`
- `tests/contract/**`

## 금지 경로

- `services/mssql-mcp/**` 구현 변경
- `packages/**` 구현 변경
- `db/schema/**`
- `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml`
- secret/token/raw JWT claims/PLF row data 저장
- PLF fallback for PPM

## 구현 범위

- Docker test image 를 `python:3.14-slim` 로 변경한다.
- `requirements/lock/py314-dev.txt` 를 현재 재현성 lock 으로 추가/전환한다.
- Makefile 기본 `PYTHON` 은 `python3.14` 이며 `$(PYTHON) -m uvicorn`, `$(PYTHON) -m ruff` 실행 스타일을 사용한다.
- `requires-python = ">=3.14"` 와 Ruff `target-version = "py314"` 를 적용한다.
- 현재 문서, manifest, lockfile 안내에서 이전 Python lock file 을 active baseline 으로 부르지 않는다.

## 검증 명령

- `python3.14 -m compileall apps services packages tests`
- `make test PYTEST_ARGS="tests/contract/test_p21_no_mock_prompt_assets.py tests/contract/test_generation_goldens_and_repro_assets.py"`
- `make test`

## Blocker 보고 기준

- `python3.14` 가 host 에 없거나 Docker `python:3.14-slim` image 를 사용할 수 없음
- Python 3.14 에서 pinned dependency 가 설치되지 않음
- Ruff pinned version 이 `py314` target 을 지원하지 않음
- 이전 Python 문서/manifest 참조가 active baseline 으로 남아 있음
