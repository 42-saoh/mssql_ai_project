PROJECT.md, AGENTS.md, ARCHITECTURE.md, TOOLS.md, POLICY.md, EVAL_SPEC.md 를 읽고 기준으로 작업해.
추가로 `spec/policy/project_ai_java_mybatis_generation_policy.yaml`, `spec/policy/platform_db_standardization_rules_for_ai.json`, `spec/validation/validation_rules.yaml`, `spec/openapi/ai_agent_platform_openapi_v1.yaml`, `fixtures/generation/golden/java_mybatis_sp_wrapper_order_request_v1/` 를 읽고 생성/검증 기준선으로 사용해.

너는 **Generation & Validation Core 트랙 담당**이다.
이 작업은 병렬 worker 중 하나이며, 공통 domain 계약과 OpenAPI 계약은 읽기 전용으로 사용한다.
정책/계약 명칭이 충돌하면 임의로 넓히지 말고, 구현 가능한 최소 매핑과 blocker 를 분리해서 보고해.

Role:
- template_engineer

Preferred Skills:
- contract-to-code
- quality-gate-review
- eval-fixture-authoring

Task:
- `packages/generation` 과 `packages/validation` 에 artifact generator 와 validation engine 의 최소 구현을 추가해.
- SP analysis document, dependency report, DTO/Java/MyBatis draft skeleton 수준의 deterministic renderer 를 만들고, evidence coverage / required section / status gate 검증을 추가해.
- Java/MyBatis 초안은 golden sample 의 `spWrapper` 출력 구조와 정책의 evidence/todo/review checklist 요구를 그대로 반영해.

In Scope:
- generation package 구조
- artifact renderer abstraction
- initial renderers for analysis doc / dependency report / Java/MyBatis code draft skeleton
- validation package 구조
- required section checks
- evidence coverage checks
- review-required marker checks
- validation report model usage 또는 validation-local result model
- unit tests and fixtures
- golden sample regression helper 또는 fixture 활용
- `spec/validation/validation_rules.yaml` 의 규칙을 읽거나 최소 동기화하는 helper

Out of Scope:
- packages/domain 변경
- API/BFF 구현
- Web UI 구현
- 실제 publish workflow 구현
- 실제 DDL 실행
- unsupported framework assumption 을 근거 없이 확정

Target Files/Dirs:
- packages/generation/**
- packages/validation/**
- spec/validation/**
- tests/unit/generation/**
- tests/unit/validation/**
- fixtures/generation/**

Read-only References:
- packages/domain/**
- spec/openapi/**
- spec/policy/**
- db/schema/**

Constraints:
- packages/domain, db/schema, spec/openapi 수정 금지
- deterministic renderer 우선
- 모든 생성물은 draft-only 로 다룬다.
- evidence 가 약한 항목은 `REVIEW_REQUIRED`, TODO, assumptions section 으로 명시한다.
- validation 없이 publish 하는 흐름을 만들지 않음
- golden sample 과 정책 파일에 없는 프레임워크 가정은 TODO 로 남긴다.
- OpenAPI artifact type(`SP_ANALYSIS_DOCUMENT`, `DEPENDENCY_REPORT`, `JAVA_MYBATIS_DRAFT` 등)과 validation rule type(`SP_ANALYSIS_DOC` 등)이 불일치하면 작은 alias mapping 또는 blocker 로 처리하고, 조용히 새 명칭을 만들지 않는다.

Expected Deliverables:
- generation core
- validation core
- rules/fixtures/tests
- golden sample 을 통과하는 최소 렌더러/검증기 기반선
- evidence/todo/review checklist 를 포함한 draft output

Verification:
- `make test PYTEST_ARGS="tests/unit/generation tests/unit/validation"`
- 필요 시 `make test PYTEST_ARGS="tests/contract/test_generation_goldens_and_repro_assets.py"`
- `python3.14 -m compileall packages/generation packages/validation tests/unit/generation tests/unit/validation`

Report Format:
- Changed Files
- What I Implemented
- Verification
- Open Risks / Blockers

추가 규칙:
- 첫 응답에서 수정 예정 파일, 예상 테스트 명령, blocker 후보를 짧게 제시해.
- 생성 결과가 실제 프로젝트에 바로 반영 가능한 코드처럼 보이더라도 반드시 draft/review-required 경계를 남겨.
