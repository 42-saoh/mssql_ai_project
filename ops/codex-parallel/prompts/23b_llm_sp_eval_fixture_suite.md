# P23B LLM SP Eval Fixture Suite

## 공통 운영 철학

- 현재 대화 요청과 실제 파일 구조를 최우선 기준으로 삼는다.
- P23A 계약을 기준으로 simple/medium/complex fixture 를 작성한다.
- `production_ready: false` 를 유지한다.
- `PLF` 는 platform DB, `PPM` 은 pilot analysis target DB 이며, PPM 접근 실패 시 PLF fallback 은 금지한다.
- row data, procedure execution, business DB DDL/DML, 자동 반영, secret 저장은 금지한다.
- raw prompt, raw SP definition, raw OpenAI response text 는 trace/API/Web 산출물에 저장하지 않는다.
- fast/test profile 기본값은 `gpt-5-nano` 이며 optional live confidence 에서는 `OPENAI_MODEL_FAST_TEST` 로 모델을 바꿀 수 있다.

## 목표

대표 simple/medium/complex stored procedure fixture 와 golden expected semantic outputs 를 만든다. 기본 테스트는 FakeModelGateway 를 사용하며 live OpenAI 호출은 optional gate 로만 둔다.

## 읽어야 할 기준 파일

- `PROJECT.md`
- `POLICY.md`
- `EVAL_SPEC.md`
- `spec/eval/p23_llm_sp_analysis_quality_contract.yaml`
- `fixtures/eval/llm_sp_analysis_quality_p23_v1.yaml`
- `packages/agent-runtime/src/ai_agent_runtime/**`
- `tests/eval/**`
- `tests/unit/agent_runtime/**`
- `tests/contract/test_p23_llm_eval_contract_prompt_assets.py`

## 허용 수정 경로

- `fixtures/eval/**`
- `tests/eval/**`
- `tests/fixtures/**`
- `EVAL_SPEC.md`
- `docs/integration-eval-status.md`

## 금지 경로

- `packages/agent-runtime/**` implementation rewrite
- `apps/api/**` 구현 변경
- `apps/web/**` 구현 변경
- `db/schema/**`
- 실제 고객/운영 SP 원문 fixture 저장
- PLF/PPM row data fixture 저장
- PPM 실패 시 PLF fallback

## 구현 범위

- `p23_simple_read_only_lookup`, `p23_medium_branching_transaction`, `p23_complex_dynamic_sql_cross_db` synthetic fixture 를 작성한다.
- 각 fixture 는 deterministic metadata/static-analysis facts, transient SP definition input, golden LLM semantic output 을 분리한다.
- Golden output 은 `business_rules`, `modernization_points`, `risk_flags`, `review_markers`, `assumptions` 만 포함한다.
- `LLM_INFERENCE` evidence 는 deterministic fact 와 연결하고, unsupported dependency/table/function claim 은 `REVIEW_REQUIRED` 로 기대값을 둔다.
- raw SP definition 은 test fixture 입력으로만 다루고 trace/storage expected output 에 포함하지 않는다.

## 검증 명령

- `make test PYTEST_ARGS="tests/eval/test_p23_llm_sp_analysis_quality.py tests/contract/test_p23_llm_eval_contract_prompt_assets.py"`
- `git diff --check`

## Blocker 보고 기준

- fixture 가 실제 운영 SP 원문이나 row data 를 포함함
- expected trace 에 raw prompt/raw SP definition/raw OpenAI response text 가 포함됨
- unsupported dependency/table/function claim 이 review 없이 accepted 로 남음
- simple/medium/complex 중 하나라도 coverage 가 빠짐
