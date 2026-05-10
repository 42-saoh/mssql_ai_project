# Task

- ID: P23
- Title: LLM-assisted SP Analysis Quality Eval
- Priority: High
- Owner: split Codex tracks P23A-P23D
- Requested by: project owner

## Goal

P22 OpenAI LLM Agent Runtime 을 기반으로 stored procedure semantic analysis 품질을 simple/medium/complex suite 로 반복 평가할 수 있는 계약, fixture, runner, readiness 문서를 분리된 작업 단위로 만든다. P23 첫 슬라이스는 계약과 프롬프트 팩을 만드는 것이며, runtime 확장은 후속 P23B/P23C 트랙으로 분리한다.

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
  - fast/test profile 은 `gpt-5-nano` 로 고정한다.

## In Scope

- P23 quality eval contract 작성
- P23 seed fixture 작성
- P23A-P23D 병렬 작업 프롬프트 작성
- Manifest 의 split track, dependency, merge order 선언
- Contract asset test 추가

## Out of Scope

- P23 fixture 본문 전체 작성
- P23 eval runner 구현
- API/Web 기능 확장
- P24 document and Java/MyBatis draft generation
- P25 runtime hardening

## Inputs

- 대상 객체: synthetic stored procedure fixtures only
- 기존 계약:
  - `prompt:sp_semantic_analysis@0.1.0`
  - `schema:llm_semantic_analysis@0.1.0`
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
- 변경 가능 디렉터리:
  - `spec/eval/`
  - `fixtures/eval/`
  - `ops/codex-parallel/`
  - `tests/contract/`
  - 관련 docs/task 파일
- PPM 접근 실패 시 PLF fallback 금지

## Deliverables

- P23 eval contract
- P23 seed fixture
- P23A-P23D prompt pack
- Manifest update
- Contract prompt asset test
- EVAL/readiness docs sync

## Verification

- 실행할 테스트:
  - `make test PYTEST_ARGS="tests/contract/test_p23_llm_eval_contract_prompt_assets.py"`
- 계약 검증:
  - simple/medium/complex scenario 선언
  - `LLM_INFERENCE` evidence 선언
  - unsupported fact claim 의 `REVIEW_REQUIRED` 선언
  - `gpt-5-nano` fast/test profile 선언
  - no-raw-trace storage 금지 선언
- 수동 점검:
  - P23A-P23D 가 분리되어 있고 P24+ 범위를 구현하지 않음

## Done Definition

- P23 계약과 seed fixture 가 존재한다.
- P23A-P23D 프롬프트가 각자 허용/금지 경로와 검증 명령을 갖는다.
- Manifest 에 P23A -> P23B -> P23C -> P23D 병합 순서가 있다.
- Contract test 가 통과한다.
- P23 은 `production_ready: false` 로 남는다.

## Notes / Risks

- 가정: P22 runtime 은 별도 검증 완료 후 P23B/P23C 작업자가 사용할 수 있다.
- 오픈 이슈: 실제 quality scoring 방식과 fixture 본문은 P23B/P23C 에서 확정한다.
- 후속 작업: P24 LLM-assisted document and Java/MyBatis draft generation 은 P23 통과 이후 별도 브리프로 시작한다.
