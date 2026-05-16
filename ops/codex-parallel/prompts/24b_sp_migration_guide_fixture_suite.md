# P24B SP Migration Guide Fixture Suite

## 공통 운영 철학

- 현재 대화 요청과 실제 파일 구조를 최우선 기준으로 삼는다.
- P24A 계약을 기준으로 synthetic fixture 와 golden quality expectations 를 작성한다.
- `production_ready: false` 를 유지한다.
- `PLF` 는 platform DB, `PPM` 은 pilot analysis target DB 이며, PPM 접근 실패 시 PLF fallback 은 금지한다.
- row data, procedure execution, business DB DDL/DML, 자동 반영, secret 저장은 금지한다.
- raw prompt, raw SP definition, raw OpenAI response text 는 fixture output/report/storage 에 저장하지 않는다.
- fast/test profile 기본값은 `gpt-5-nano` 이며 optional live confidence 에서는 `OPENAI_MODEL_FAST_TEST` 로 모델을 바꿀 수 있다.

## 목표

P24 migration guide 품질을 검증할 synthetic simple/medium/complex fixture 와 expected section coverage 를 만든다. 실제 운영 SP 원문이나 사용자 제공 guide 본문은 fixture 로 저장하지 않는다.

## 읽어야 할 기준 파일

- `PROJECT.md`
- `POLICY.md`
- `EVAL_SPEC.md`
- `spec/eval/p24_sp_migration_guide_quality_contract.yaml`
- `packages/generation/README.md`
- `packages/generation/src/ai_agent_generation/documents.py`
- `fixtures/generation/README.md`
- `tests/unit/generation/**`
- `tests/contract/test_p24_sp_migration_guide_contract_prompt_assets.py`

## 허용 수정 경로

- `fixtures/eval/**`
- `fixtures/generation/**`
- `tests/eval/**`
- `tests/contract/test_p24_sp_migration_guide_contract_prompt_assets.py`
- `EVAL_SPEC.md`
- `docs/integration-eval-status.md`

## 금지 경로

- `packages/generation/**` renderer 구현 변경
- `apps/api/**`
- `apps/web/**`
- `services/mssql-mcp/**`
- `db/schema/**`
- 실제 운영 SP 원문 또는 사용자 제공 guide 본문 저장
- PLF/PPM row data fixture 저장
- PPM 실패 시 PLF fallback

## 구현 범위

- Synthetic guide fixture 는 section taxonomy, Confirmed/Needs verification dependency inventory, table-level DML matrix, call flow, phase/risk metrics, manual metadata extraction appendix, evidence refs 를 포함한다.
- Fixture 는 기준 guide-style rendering expectation 으로 한국어 heading, 숨김 section anchor, overview/feature/critical phase 표 필수 요소를 기록한다.
- Guide expected output 은 raw SP text 없이 sanitized facts 와 review markers 만 사용한다.
- Unsupported dependency/table/function/cross-DB claims 는 모두 `REVIEW_REQUIRED` 기대값을 둔다.
- Fixture 는 기존 `SP_ANALYSIS_DOC` 와 `DEPENDENCY_REPORT` 품질 확장을 검증하며 새 persisted artifact type 을 요구하지 않는다.
- Quality thresholds 는 contract 의 required section coverage, evidence-linked claim coverage, DML matrix coverage, branch/call-flow coverage, storage safety 기준을 따른다.

## 검증 명령

- `make test PYTEST_ARGS="tests/eval/test_p24_sp_migration_guide_quality.py tests/contract/test_p24_sp_migration_guide_contract_prompt_assets.py"`
- `git diff --check`

## Blocker 보고 기준

- fixture 에 실제 운영 SP 원문, row data, 사용자 제공 guide 본문이 포함됨
- expected output 이 raw prompt/raw SP definition/raw OpenAI response text 를 포함함
- required guide section 중 하나라도 빠짐
- unsupported claim 이 `REVIEW_REQUIRED` 없이 accepted 로 남음
- P24B 가 renderer/runtime behavior 변경을 포함함
