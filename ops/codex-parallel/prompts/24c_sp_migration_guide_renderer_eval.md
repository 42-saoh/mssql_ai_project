# P24C SP Migration Guide Renderer Eval

## 공통 운영 철학

- 현재 대화 요청과 실제 파일 구조를 최우선 기준으로 삼는다.
- P24A 계약과 P24B fixture 를 기준으로 renderer/eval runner 를 가장 작은 슬라이스로 개선한다.
- `production_ready: false` 를 유지한다.
- `PLF` 는 platform DB, `PPM` 은 pilot analysis target DB 이며, PPM 접근 실패 시 PLF fallback 은 금지한다.
- row data, procedure execution, business DB DDL/DML, 자동 반영, secret 저장은 금지한다.
- raw prompt, raw SP definition, raw OpenAI response text 는 report/artifact/storage/test output 에 저장하지 않는다.
- fast/test profile 기본값은 `gpt-5-nano` 이며 optional live confidence 에서는 `OPENAI_MODEL_FAST_TEST` 로 모델을 바꿀 수 있다.

## 목표

기존 `SP_ANALYSIS_DOC` 와 `DEPENDENCY_REPORT` 렌더링을 P24 migration guide 품질 계약에 맞게 끌어올리고, fixture-first quality evaluator 를 추가한다. 새 persisted artifact type 은 만들지 않는다.

## 읽어야 할 기준 파일

- `PROJECT.md`
- `ARCHITECTURE.md`
- `POLICY.md`
- `EVAL_SPEC.md`
- `spec/eval/p24_sp_migration_guide_quality_contract.yaml`
- `packages/generation/README.md`
- `packages/generation/src/ai_agent_generation/documents.py`
- `packages/generation/src/ai_agent_generation/models.py`
- `fixtures/eval/**`
- `fixtures/generation/**`
- `tests/unit/generation/**`

## 허용 수정 경로

- `packages/generation/**`
- `fixtures/eval/**`
- `fixtures/generation/**`
- `tests/eval/**`
- `tests/unit/generation/**`
- `tests/contract/test_generation_goldens_and_repro_assets.py`
- `EVAL_SPEC.md`
- `docs/integration-eval-status.md`

## 금지 경로

- `packages/domain/**` enum 추가
- `apps/api/**` public API 변경
- `apps/web/**` behavior 변경
- `services/mssql-mcp/**`
- `db/schema/**`
- 새 persisted artifact type 추가
- raw prompt/raw SP definition/raw OpenAI response text 저장
- PPM 실패 시 PLF fallback

## 구현 범위

- Existing `SP_ANALYSIS_DOC` renderer 에 P24 required sections 를 반영한다.
- Dependency/DML/call-flow/phase/risk/appended mapping 섹션은 deterministic facts 와 evidence refs 에서만 구성한다.
- Dependency inventory 는 `Confirmed` 와 `Needs verification` 을 분리하고, 불확실한 행에는 추가 추출할 metadata-only evidence 를 적는다.
- Manual metadata extraction appendix 는 SSMS 수동 실행용 metadata-only query/result paste template 만 포함하며 row data/procedure execution/DDL/DML/raw definition output 을 금지한다.
- 불확실한 dependency/table/function/cross-DB/business-rule claim 은 `REVIEW_REQUIRED` 로 표기한다.
- Quality evaluator 는 `status`, `productionReady`, `scores`, `thresholds`, `evidenceRefs`, `sectionCoverage`, `reviewRequiredFindings`, `storageSafetyFindings` 를 반환한다.
- Java/MyBatis 내용은 migration strategy/readiness note 로 연결하되 generated source application 은 수행하지 않는다.

## 검증 명령

- `make test PYTEST_ARGS="tests/eval/test_p24_sp_migration_guide_quality.py tests/unit/generation tests/contract/test_generation_goldens_and_repro_assets.py tests/contract/test_p24_sp_migration_guide_contract_prompt_assets.py"`
- `make test-web-smoke`
- `git diff --check`

## Blocker 보고 기준

- required section coverage 100% 를 fixture-first 로 만족할 수 없음
- 새 artifact type/API/schema 없이는 진행 불가하다고 판단됨
- renderer 가 raw SP definition, raw prompt, raw OpenAI response text 를 저장함
- 실제 DB DDL/DML/procedure execution 또는 row data 조회가 필요함
- P24C 결과를 production-ready 또는 자동 전환 완료로 표현함
