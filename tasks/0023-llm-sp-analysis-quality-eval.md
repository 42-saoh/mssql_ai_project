# Task

- ID: P23
- Title: LLM-assisted SP Analysis Quality Eval
- Priority: High
- Owner: split Codex tracks P23A-P23D
- Requested by: project owner

## Goal

P22 OpenAI LLM Agent Runtime 을 기반으로 stored procedure semantic analysis 품질을 simple/medium/complex suite 로 반복 평가할 수 있는 계약, fixture, runner, readiness 문서를 정렬한다. P23D 기준으로 계약, authored fixture, fixture-first scoring runner, prompt pack, readiness 문서를 동기화하되 production readiness 는 주장하지 않는다.

## Context

- 관련 문서:
  - `PROJECT.md`
  - `ARCHITECTURE.md`
  - `TOOLS.md`
  - `POLICY.md`
  - `EVAL_SPEC.md`
- 관련 계약/프롬프트:
  - `spec/eval/p23_llm_sp_analysis_quality_contract.yaml`
  - `fixtures/eval/llm_sp_analysis_quality_p23_v1.yaml`
  - `ops/codex-parallel/prompts/23a_llm_sp_eval_contract_assets.md`
  - `ops/codex-parallel/prompts/23b_llm_sp_eval_fixture_suite.md`
  - `ops/codex-parallel/prompts/23c_llm_sp_eval_runner.md`
  - `ops/codex-parallel/prompts/23d_llm_sp_eval_docs_readiness.md`
- 선행 결정:
  - P22 runtime 은 OpenAI Responses API 를 adapter 뒤에 둔다.
  - raw SP definition 은 transient model input 으로만 허용하고 저장하지 않는다.
  - fast/test profile 기본값은 `gpt-5-nano` 이며 optional live confidence 에서는 `OPENAI_MODEL_FAST_TEST` 로 모델을 바꿀 수 있다.

## In Scope

- P23 quality eval contract/readiness 문서 동기화
- P23 authored fixture 와 fixture-first scoring runner 상태 문서화
- P23 quality threshold 와 pass/hold/fail 해석 정리
- P23A-P23D prompt pack 과 manifest 상태 확인
- Optional live quality gate 를 confidence signal 로 분리

## Out of Scope

- runtime/API/Web behavior 변경
- fixture YAML 또는 eval runner behavior 변경
- API/Web 기능 확장
- P24 document and Java/MyBatis draft generation
- P25 runtime hardening

## Inputs

- 대상 객체: synthetic stored procedure fixtures only
- 기존 계약:
  - `prompt:sp_semantic_analysis@0.3.0`
  - `schema:llm_semantic_analysis@0.3.0`
  - SP별 staged runtime, `LLM_SP_CONCURRENCY=2`, dynamic evidence schema
  - `model:openai_sp_semantic_analysis@0.1.0`
  - `model:openai_fast_test@gpt-5-nano@0.1.0`
- 샘플/fixture:
  - `fixtures/eval/llm_sp_analysis_quality_p23_v1.yaml`

## Constraints

- 정책 제약:
  - row data 조회 금지
  - procedure execution 금지
  - business DB DDL/DML 금지
  - 자동 반영/배포 금지
  - secret logging 금지
- 저장 금지:
  - raw prompt
  - raw SP definition
  - raw OpenAI response text
- P23D 문서 readiness 변경 가능 경로:
  - `ARCHITECTURE.md`
  - `EVAL_SPEC.md`
  - `docs/**`
  - `fixtures/eval/README.md`
  - `tests/eval/README.md`
  - `tasks/0023-llm-sp-analysis-quality-eval.md`
  - `ops/codex-parallel/**` 문서/프롬프트만, drift 가 확인된 경우에 한정
- PPM 접근 실패 시 PLF fallback 금지

## Deliverables

- P23 eval readiness docs sync
- EVAL_SPEC threshold/failure interpretation
- Integration eval status update
- fixtures/eval and tests/eval README update
- P23 task brief current-state update

## Verification

- 실행할 테스트:
  - `make test PYTEST_ARGS="tests/contract/test_p23_llm_eval_contract_prompt_assets.py tests/eval"`
  - `make test-web-smoke`
  - `git diff --check`
- 계약 검증:
  - simple/medium/complex scenario 선언
  - `LLM_INFERENCE` evidence 선언
  - unsupported fact claim 의 `REVIEW_REQUIRED` 선언
  - `gpt-5-nano` fast/test profile 기본값과 `OPENAI_MODEL_FAST_TEST` override 경계 선언
  - no-raw-trace storage 금지 선언
  - `semantic_recall >= 0.75`, `evidence_discipline >= 0.9`, `unreviewed_overclaims <= 0`, `storage_safety_findings <= 0`
- 수동 점검:
  - P23A-P23D 가 분리되어 있고 P24+ 범위를 구현하지 않음
  - optional live quality gate 를 기본 필수 테스트나 production readiness 기준으로 표현하지 않음

## Done Definition

- P23 계약, authored fixture, scoring runner, readiness 문서가 서로 같은 모델/profile/prompt/schema refs 를 말한다.
- P23A-P23D 프롬프트가 각자 허용/금지 경로와 검증 명령을 갖는다.
- Manifest 에 P23A -> P23B -> P23C -> P23D 병합 순서가 있다.
- Contract/eval docs verification 이 통과하거나 실행 불가 사유가 명시된다.
- P23 은 `production_ready: false` 로 남는다.

## Notes / Risks

- 가정: P22 runtime 과 P23C fixture-first scoring runner 는 현재 테스트 자산으로 검증 대상이다.
- 오픈 이슈: optional live quality gate 는 OpenAI env 가 명시적으로 준비된 경우의 confidence signal 이며 기본 readiness gate 가 아니다.
- 후속 작업: P24 LLM-assisted document and Java/MyBatis draft generation 은 P23 통과 이후 별도 브리프로 시작한다.
