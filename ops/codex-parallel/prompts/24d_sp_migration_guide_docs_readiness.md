# P24D SP Migration Guide Docs Readiness

## 공통 운영 철학

- 현재 대화 요청과 실제 파일 구조를 최우선 기준으로 삼는다.
- P24A~P24C 결과를 문서, readiness, 품질 게이트 관점에서 동기화한다.
- `production_ready: false` 를 유지한다.
- `PLF` 는 platform DB, `PPM` 은 pilot analysis target DB 이며, PPM 접근 실패 시 PLF fallback 은 금지한다.
- row data, procedure execution, business DB DDL/DML, 자동 반영, secret 저장은 금지한다.
- raw prompt, raw SP definition, raw OpenAI response text 는 문서 예시에도 포함하지 않는다.
- fast/test profile 은 `gpt-5-nano` 로 고정한다.

## 목표

P24 SP migration guide quality gate 가 어떤 조건에서 통과/보류/실패인지 문서화하고, P25 이후 실제 Java/MyBatis 확장이나 production readiness 주장과 분리한다.

## 읽어야 할 기준 파일

- `PROJECT.md`
- `ARCHITECTURE.md`
- `POLICY.md`
- `TOOLS.md`
- `EVAL_SPEC.md`
- `docs/integration-eval-status.md`
- `spec/eval/p24_sp_migration_guide_quality_contract.yaml`
- `fixtures/eval/**`
- `fixtures/generation/**`
- `tests/eval/**`
- `tests/unit/generation/**`
- `tests/contract/test_p24_sp_migration_guide_contract_prompt_assets.py`
- `ops/codex-parallel/REQUEST_MANIFEST.yaml`

## 허용 수정 경로

- `PROJECT.md`
- `ARCHITECTURE.md`
- `POLICY.md`
- `TOOLS.md`
- `EVAL_SPEC.md`
- `docs/**`
- `fixtures/eval/README.md`
- `fixtures/generation/README.md`
- `tests/eval/README.md`
- `tasks/0024-sp-migration-guide-quality.md`
- `ops/codex-parallel/**`

## 금지 경로

- runtime/API/Web behavior 변경
- `db/schema/**`
- raw prompt/raw SP definition/raw OpenAI response text 예시 추가
- live OpenAI gate 를 기본 필수 테스트로 문서화
- PPM 실패 시 PLF fallback
- P24 를 production-ready 또는 자동 전환 완료로 표현

## 구현 범위

- P24 contract, fixture, tests, prompt pack 의 상태를 문서화한다.
- P24 guide quality thresholds 와 pass/hold/fail interpretation 을 EVAL_SPEC 와 integration eval status 에 반영한다.
- Unsupported dependency/table/function/cross-DB claim 의 `REVIEW_REQUIRED` 처리 기준이 문서에 남아 있는지 확인한다.
- Existing artifact type reuse 와 draft-only Java/MyBatis readiness boundary 를 문서화한다.
- Optional live gate 는 confidence evidence 로만 표현한다.
- 후속 Java/MyBatis code generation 확장은 별도 계획으로 분리한다.

## 검증 명령

- `make test PYTEST_ARGS="tests/contract/test_p24_sp_migration_guide_contract_prompt_assets.py tests/eval"`
- `make test-web-smoke`
- `git diff --check`

## Blocker 보고 기준

- 문서가 P24 를 production-ready 로 표현함
- P24 문서와 contract/prompt/manifest 가 서로 다른 model/profile/prompt/schema ref 를 말함
- raw prompt/raw SP definition/raw OpenAI response text 금지 정책이 문서에서 누락됨
- P25+ 범위를 P24 작업에 섞어 구현 완료처럼 표현함
