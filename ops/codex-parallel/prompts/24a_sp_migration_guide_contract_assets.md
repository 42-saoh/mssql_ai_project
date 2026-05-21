# P24A SP Migration Guide Contract Assets

## 공통 운영 철학

- 현재 대화 요청과 실제 파일 구조를 최우선 기준으로 삼는다.
- P24A 는 구현 확장이 아니라 계약/프롬프트/작업 브리프 자산 정렬 작업이다.
- `production_ready: false` 를 유지한다.
- `PLF` 는 platform DB, `PPM` 은 pilot analysis target DB 이며, PPM 접근 실패 시 PLF fallback 은 금지한다.
- row data, procedure execution, business DB DDL/DML, 자동 반영, secret 저장은 금지한다.
- raw prompt, raw SP definition, raw OpenAI response text 는 저장하거나 문서 예시로 복사하지 않는다.
- fast/test profile 기본값은 `gpt-5-nano` 이며 optional live confidence 에서는 `OPENAI_MODEL_FAST_TEST` 로 모델을 바꿀 수 있다.

## 목표

사용자가 제공한 `MIGRATION_GUIDE.md` 는 구조/품질 reference 로만 사용하고, 그 이상의 SP migration guide 품질을 평가할 수 있는 P24 계약과 prompt pack 을 만든다. 이 트랙은 renderer/eval runner/API/Web 을 변경하지 않는다.

## 읽어야 할 기준 파일

- `PROJECT.md`
- `ARCHITECTURE.md`
- `POLICY.md`
- `TOOLS.md`
- `EVAL_SPEC.md`
- `TASK_TEMPLATE.md`
- `packages/generation/README.md`
- `packages/generation/src/ai_agent_generation/documents.py`
- `fixtures/generation/README.md`
- `spec/policy/project_ai_java_mybatis_generation_policy.yaml`
- `spec/eval/p23_llm_sp_analysis_quality_contract.yaml`
- `spec/eval/p24_sp_migration_guide_quality_contract.yaml`
- `ops/codex-parallel/REQUEST_MANIFEST.yaml`
- `tasks/0024-sp-migration-guide-quality.md`
- `tests/contract/test_p24_sp_migration_guide_contract_prompt_assets.py`

## 허용 수정 경로

- `spec/eval/p24_sp_migration_guide_quality_contract.yaml`
- `ops/codex-parallel/REQUEST_MANIFEST.yaml`
- `ops/codex-parallel/prompts/24*.md`
- `tasks/0024-sp-migration-guide-quality.md`
- `tests/contract/test_p24_sp_migration_guide_contract_prompt_assets.py`

## 금지 경로

- `packages/generation/**` 구현 변경
- `packages/agent-runtime/**` 구현 변경
- `apps/api/**` 구현 변경
- `apps/web/**` 구현 변경
- `services/mssql-mcp/**` 구현 변경
- `db/schema/**`
- 사용자 제공 guide 본문이나 실제 PPM SP 원문 fixture 저장
- raw prompt/raw SP definition/raw OpenAI response text 예시 추가
- PPM 실패 시 PLF fallback

## 구현 범위

- P24 contract 에 required guide sections, Confirmed/Needs verification dependency split, manual metadata extraction appendix, report fields, quality thresholds, storage safety, `REVIEW_REQUIRED` obligations 를 명시한다.
- P24 v0.3 contract 에 사용자-facing 한국어 heading, 숨김 section anchor, overview/feature/critical phase 표 품질 요구사항을 명시한다.
- P24A~P24D prompt pack 과 manifest split tracks 를 추가한다.
- P24 task brief 를 작성한다.
- Contract test 로 P24 prompt/contract/manifest/task boundaries 를 고정한다.
- `SP_ANALYSIS_DOC`, `DEPENDENCY_REPORT` 기존 artifact type 을 우선 사용하고 새 persisted artifact type 은 만들지 않는다고 명시한다.

## 검증 명령

- `make test PYTEST_ARGS="tests/contract/test_p24_sp_migration_guide_contract_prompt_assets.py"`
- `git diff --check`

## Blocker 보고 기준

- P24 계약이 `production_ready: true` 를 주장함
- P24A 가 renderer/runtime/API/Web/DB schema 변경을 포함함
- 사용자 제공 guide 내용, raw prompt, raw SP definition, raw OpenAI response text 를 repo asset 에 복사함
- quality thresholds 또는 required section taxonomy 가 누락됨
- unsupported dependency/table/function/cross-DB claim 이 `REVIEW_REQUIRED` 없이 accepted 로 남음
- PPM 실패 시 PLF fallback 을 허용함
