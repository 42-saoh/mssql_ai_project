# P23D LLM SP Eval Docs Readiness

## 공통 운영 철학

- 현재 대화 요청과 실제 파일 구조를 최우선 기준으로 삼는다.
- P23A~P23C 결과를 문서, readiness, 품질 게이트 관점에서 동기화한다.
- `production_ready: false` 를 유지한다.
- `PLF` 는 platform DB, `PPM` 은 pilot analysis target DB 이며, PPM 접근 실패 시 PLF fallback 은 금지한다.
- row data, procedure execution, business DB DDL/DML, 자동 반영, secret 저장은 금지한다.
- raw prompt, raw SP definition, raw OpenAI response text 는 문서 예시에도 포함하지 않는다.
- fast/test profile 은 `gpt-5-nano` 로 고정한다.

## 목표

P23 LLM-assisted SP analysis quality eval 이 어떤 조건에서 통과/보류/실패인지 문서화하고, P24 이후 document/code generation 확장 전에 남은 리스크를 분리한다.

## 읽어야 할 기준 파일

- `PROJECT.md`
- `ARCHITECTURE.md`
- `POLICY.md`
- `TOOLS.md`
- `EVAL_SPEC.md`
- `docs/integration-eval-status.md`
- `spec/eval/p23_llm_sp_analysis_quality_contract.yaml`
- `fixtures/eval/llm_sp_analysis_quality_p23_v1.yaml`
- `tests/eval/**`
- `tests/contract/**`
- `ops/codex-parallel/REQUEST_MANIFEST.yaml`

## 허용 수정 경로

- `PROJECT.md`
- `ARCHITECTURE.md`
- `POLICY.md`
- `TOOLS.md`
- `EVAL_SPEC.md`
- `docs/**`
- `fixtures/eval/README.md`
- `tests/eval/README.md`
- `tasks/0023-llm-sp-analysis-quality-eval.md`
- `ops/codex-parallel/**`

## 금지 경로

- runtime/API/Web behavior 변경
- `db/schema/**`
- raw prompt/raw SP definition/raw OpenAI response text 예시 추가
- live OpenAI gate 를 기본 필수 테스트로 문서화
- PPM 실패 시 PLF fallback

## 구현 범위

- P23 contract, fixture, tests, prompt pack 의 상태를 문서화한다.
- P23 quality thresholds 와 failure interpretation 을 EVAL_SPEC 와 integration eval status 에 반영한다.
- `LLM_INFERENCE` evidence 와 unsupported dependency/table/function claim 의 `REVIEW_REQUIRED` 처리 기준이 문서에 남아 있는지 확인한다.
- Optional live gate 는 evidence 로 남기되 production readiness 기준이 아니라 P23 confidence signal 로만 표현한다.
- P24 document and Java/MyBatis draft generation 은 P23 통과 후 별도 계획으로 분리한다.

## 검증 명령

- `make test PYTEST_ARGS="tests/contract/test_p23_llm_eval_contract_prompt_assets.py tests/eval"`
- `make test-web-smoke`
- `git diff --check`

## Blocker 보고 기준

- 문서가 P23 을 production-ready 로 표현함
- P23 문서와 contract/fixture/manifest 가 서로 다른 모델명, profile, prompt/schema ref 를 말함
- raw prompt/raw SP definition/raw OpenAI response text 금지 정책이 문서에서 누락됨
- P24+ 범위를 P23 작업에 섞어 구현 완료처럼 표현함
