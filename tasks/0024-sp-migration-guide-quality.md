# Task

- ID: P24
- Title: SP Migration Guide Quality Contract
- Priority: High
- Owner: split Codex tracks P24A-P24D
- Requested by: project owner

## Goal

사용자가 제공한 migration guide 수준 이상의 SP 분석/이관 가이드 품질을 계약화한다. P24A 는 contract, prompt pack, manifest wiring, task brief, contract test 만 추가하며 renderer/eval runner/API/Web/DB behavior 는 바꾸지 않는다. P24B 는 sanitized fixture suite 를 추가했고, P24C 는 기존 `SP_ANALYSIS_DOC` 와 `DEPENDENCY_REPORT` renderer/evaluator 로 fixture-first scoring 을 구현했다. P24D 는 이 상태를 문서/readiness 관점에서 동기화한다.

## Context

- 관련 문서:
  - `PROJECT.md`
  - `ARCHITECTURE.md`
  - `TOOLS.md`
  - `POLICY.md`
  - `EVAL_SPEC.md`
- 관련 계약/프롬프트:
  - `spec/eval/p24_sp_migration_guide_quality_contract.yaml`
  - `ops/codex-parallel/prompts/24a_sp_migration_guide_contract_assets.md`
  - `ops/codex-parallel/prompts/24b_sp_migration_guide_fixture_suite.md`
  - `ops/codex-parallel/prompts/24c_sp_migration_guide_renderer_eval.md`
  - `ops/codex-parallel/prompts/24d_sp_migration_guide_docs_readiness.md`
- 선행 결정:
  - P23 fixture-first LLM semantic analysis quality eval 이 존재한다.
  - P12 Java/MyBatis generation factory 는 draft-only boundary 를 유지한다.
  - 사용자 제공 `MIGRATION_GUIDE.md` 는 structure/quality reference 로만 사용하고 본문을 repo asset 으로 복사하지 않는다.

## In Scope

- P24 migration guide quality contract 작성
- P24A-P24D prompt pack 작성
- Manifest 의 split track, dependency, merge order 선언
- P24 task brief 작성
- P24A contract prompt asset test 추가
- P24B sanitized simple/medium/complex fixture 와 expected quality report 작성
- P24C 기존 artifact type renderer/evaluator scoring 검증
- P24D pass/hold/fail interpretation 과 docs readiness 동기화

## Out of Scope

- 새 persisted artifact type 추가
- P24A 범위의 renderer/eval runner 구현
- runtime/API/Web behavior 변경
- DB schema 변경
- fixture 에 실제 운영 SP 원문 또는 사용자 제공 guide 본문 저장
- Java/MyBatis source draft 확장 구현
- production readiness 주장

## Inputs

- 대상 객체: synthetic stored procedure migration guide fixtures only
- 기존 계약:
  - `p24_sp_migration_guide_quality@0.1.0`
  - `prompt:sp_migration_guide_generation@0.1.0`
  - `schema:sp_migration_guide_quality_report@0.1.0`
  - `template:sp_migration_guide@0.1.0`
- 참고 파일:
  - user-provided `MIGRATION_GUIDE.md` as quality/structure reference only

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
  - row data
  - secrets
- 변경 가능 디렉터리:
  - `spec/eval/`
  - `ops/codex-parallel/`
  - `tasks/`
  - `tests/contract/`
- PPM 접근 실패 시 PLF fallback 금지

## Deliverables

- P24 quality contract
- P24A-P24D prompt pack
- P24 split-track manifest update
- P24 task brief
- P24 contract prompt asset test
- P24 sanitized fixture suite and fixture-first quality evaluator coverage
- P24D docs readiness updates for pass/hold/fail boundaries

## Verification

- 실행할 테스트:
  - `make test PYTEST_ARGS="tests/contract/test_p24_sp_migration_guide_contract_prompt_assets.py tests/eval"`
  - `make test-web-smoke`
  - `git diff --check`
- 계약 검증:
  - required section coverage threshold
  - evidence-linked claim coverage threshold
  - DML matrix and branch/call-flow coverage thresholds
  - unsupported claim `REVIEW_REQUIRED` obligation
  - no raw prompt/SP/provider/row/secret storage policy
- 수동 점검:
  - P24A-P24D 가 분리되어 있고 P24A 가 구현 변경을 포함하지 않음
  - 사용자 제공 guide 본문을 repo 에 복사하지 않음

## Done Definition

- P24 계약과 prompt pack 이 존재한다.
- Manifest 에 P24A -> P24B -> P24C -> P24D 병합 순서가 있다.
- Contract test 가 통과한다.
- Fixture-first P24 renderer/evaluator eval 이 통과한다.
- P24 는 `production_ready: false` 로 남는다.

## Notes / Risks

- P24C 는 기존 persisted artifact type 재사용을 기준으로 닫혔으며, 새 artifact type 추가는 범위 밖이다.
- Optional live confidence evidence 는 기본 필수 테스트가 아니며 production readiness claim 으로 해석하지 않는다.
- 후속 작업: Java/MyBatis draft generation 확장은 guide readiness note 와 별도 구현 트랙으로 유지한다.
