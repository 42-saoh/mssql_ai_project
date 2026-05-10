# P23A LLM SP Eval Contract Assets

## 공통 운영 철학

- 현재 대화 요청과 실제 파일 구조를 최우선 기준으로 삼는다.
- P22 OpenAI LLM Agent Runtime 을 전제로 하되, P23A 는 구현 확장이 아니라 계약/자산 정렬 작업이다.
- `production_ready: false` 를 유지한다.
- `PLF` 는 platform DB, `PPM` 은 pilot analysis target DB 이며, PPM 접근 실패 시 PLF fallback 은 금지한다.
- row data, procedure execution, business DB DDL/DML, 자동 반영, secret 저장은 금지한다.
- raw prompt, raw SP definition, raw OpenAI response text 는 저장하거나 API/Web 에 노출하지 않는다.
- fast/test profile 은 `gpt-5-nano` 로 고정한다.

## 목표

P23 LLM-assisted SP analysis quality eval 을 simple/medium/complex suite 로 분리 실행할 수 있도록 계약 파일, seed fixture, prompt pack 기준을 만든다. 이 트랙은 평가 러너나 실제 fixture 본문을 구현하지 않는다.

## 읽어야 할 기준 파일

- `PROJECT.md`
- `ARCHITECTURE.md`
- `POLICY.md`
- `EVAL_SPEC.md`
- `TOOLS.md`
- `TASK_TEMPLATE.md`
- `spec/eval/p23_llm_sp_analysis_quality_contract.yaml`
- `fixtures/eval/llm_sp_analysis_quality_p23_v1.yaml`
- `ops/codex-parallel/REQUEST_MANIFEST.yaml`
- `ops/codex-parallel/prompts/23*.md`
- `tests/contract/test_p23_llm_eval_contract_prompt_assets.py`

## 허용 수정 경로

- `spec/eval/p23_llm_sp_analysis_quality_contract.yaml`
- `fixtures/eval/llm_sp_analysis_quality_p23_v1.yaml`
- `ops/codex-parallel/REQUEST_MANIFEST.yaml`
- `ops/codex-parallel/prompts/23*.md`
- `tests/contract/test_p23_llm_eval_contract_prompt_assets.py`
- `EVAL_SPEC.md`
- `docs/integration-eval-status.md`
- `tasks/0023-llm-sp-analysis-quality-eval.md`

## 금지 경로

- `packages/agent-runtime/**` 구현 변경
- `apps/api/**` 구현 변경
- `apps/web/**` 구현 변경
- `services/mssql-mcp/**` 구현 변경
- `db/schema/**` 변경
- raw prompt/raw SP definition/raw OpenAI response text 저장 경로 추가
- PPM 실패 시 PLF fallback

## 구현 범위

- P23 contract 에 simple/medium/complex scenario matrix, allowed LLM output fields, `LLM_INFERENCE`, `REVIEW_REQUIRED`, trace 저장 허용/금지 범위를 명시한다.
- Seed fixture 에 P23B 가 채워야 할 fixture id, expected output 최소 조건, no-raw-trace storage check 를 선언한다.
- Manifest 에 P23A~P23D 를 독립 트랙으로 추가하고 `merge_order` 를 P23A -> P23B -> P23C -> P23D 로 고정한다.
- P23A 는 문서/계약/프롬프트 자산만 만들고 runtime behavior 는 바꾸지 않는다.

## 검증 명령

- `make test PYTEST_ARGS="tests/contract/test_p23_llm_eval_contract_prompt_assets.py"`
- `git diff --check`

## Blocker 보고 기준

- P23 계약이 `production_ready: true` 를 주장함
- fast/test profile 이 `gpt-5-nano` 가 아님
- raw prompt, raw SP definition, raw OpenAI response text 저장을 허용함
- LLM 이 새 dependency/table/function 사실을 단정했을 때 `REVIEW_REQUIRED` 로 낮추는 계약이 없음
- P23A 가 runtime/API/Web 구현 변경을 포함함
