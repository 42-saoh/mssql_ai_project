# P23C LLM SP Eval Runner

## 공통 운영 철학

- 현재 대화 요청과 실제 파일 구조를 최우선 기준으로 삼는다.
- P23A 계약과 P23B fixture 를 기준으로 평가 러너를 얇게 추가한다.
- `production_ready: false` 를 유지한다.
- `PLF` 는 platform DB, `PPM` 은 pilot analysis target DB 이며, PPM 접근 실패 시 PLF fallback 은 금지한다.
- row data, procedure execution, business DB DDL/DML, 자동 반영, secret 저장은 금지한다.
- raw prompt, raw SP definition, raw OpenAI response text 는 저장하거나 테스트 결과에 출력하지 않는다.
- fast/test profile 기본값은 `gpt-5-nano` 이며 optional live confidence 에서는 `OPENAI_MODEL_FAST_TEST` 로 모델을 바꿀 수 있다.

## 목표

P23 fixture suite 를 FakeModelGateway 로 반복 검증하고, optional live gate 에서만 OpenAI Responses API 를 호출하는 eval runner 를 추가한다. 기본 CI/로컬 검증은 외부 네트워크 없이 통과해야 한다.

## 읽어야 할 기준 파일

- `PROJECT.md`
- `ARCHITECTURE.md`
- `POLICY.md`
- `TOOLS.md`
- `EVAL_SPEC.md`
- `spec/eval/p23_llm_sp_analysis_quality_contract.yaml`
- `fixtures/eval/llm_sp_analysis_quality_p23_v1.yaml`
- `packages/agent-runtime/src/ai_agent_runtime/**`
- `tests/eval/**`
- `tests/unit/agent_runtime/**`

## 허용 수정 경로

- `tests/eval/**`
- `tests/unit/agent_runtime/**`
- `fixtures/eval/**`
- `packages/agent-runtime/src/ai_agent_runtime/**`
- `Makefile`
- `.env.example`
- `EVAL_SPEC.md`
- `TOOLS.md`

## 금지 경로

- `services/mssql-mcp/**` read/write behavior 변경
- `apps/api/**` Web/API feature expansion
- `apps/web/**` feature expansion
- `db/schema/**`
- default test 에서 remote OpenAI call 강제
- PPM 실패 시 PLF fallback

## 구현 범위

- FakeModelGateway 기반 quality score 계산을 추가한다.
- Eval runner 는 LLM 보강 항목의 evidence type 을 `LLM_INFERENCE` 로 유지한다.
- contract 의 thresholds 를 읽거나 동일 상수로 반영해 semantic recall, evidence discipline, overclaim control, storage safety 를 검증한다.
- optional live gate 는 `LLM_LIVE_GATE=1 LLM_ENABLE_REMOTE=1 LLM_ALLOW_SP_TEXT=1` 일 때만 실행한다.
- Live gate 도 raw prompt/raw SP definition/raw OpenAI response text 를 저장하거나 로그 출력하지 않는다.
- 새 dependency/table/function claim 은 validator 결과에서 `REVIEW_REQUIRED` 를 요구한다.

## 검증 명령

- `make test PYTEST_ARGS="tests/eval/test_p23_llm_sp_analysis_quality.py tests/unit/agent_runtime tests/contract/test_p23_llm_eval_contract_prompt_assets.py"`
- `LLM_LIVE_GATE=1 LLM_ENABLE_REMOTE=1 LLM_ALLOW_SP_TEXT=1 make test PYTEST_ARGS="tests/eval/test_p23_openai_quality_live_gate.py"` optional
- `git diff --check`

## Blocker 보고 기준

- 기본 테스트가 OpenAI API key 또는 network 를 요구함
- raw prompt/raw SP definition/raw OpenAI response text 가 assertion output, DB payload, artifact, API response 에 남음
- score 가 fixture 별로 재현 가능하지 않음
- optional live gate 실패를 production blocker 로 과장함
