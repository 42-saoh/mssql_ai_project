PROJECT.md, AGENTS.md, ARCHITECTURE.md, TOOLS.md, POLICY.md, EVAL_SPEC.md 를 읽고 기준으로 작업해.

너는 **Generation & Validation Core 트랙 담당**이다.
이 작업은 병렬 worker 중 하나이며, 공통 domain 계약은 읽기 전용으로 사용한다.

Role:
- template_engineer

Preferred Skills:
- contract-to-code
- quality-gate-review

Task:
- `packages/generation` 과 `packages/validation` 에 artifact generator 와 validation engine 의 최소 구현을 추가해.
- SP analysis doc, dependency report, DTO draft 또는 mapper skeleton 수준의 렌더러를 만들고, evidence coverage / required section / status gate 검증을 추가해.

In Scope:
- generation package 구조
- artifact renderer abstraction
- initial renderers for analysis doc / dependency report / code draft skeleton
- validation package 구조
- required section checks
- evidence coverage checks
- validation report model usage
- unit tests and fixtures

Out of Scope:
- packages/domain 변경
- API/BFF 구현
- Web UI 구현
- 실제 publish workflow 구현

Target Files/Dirs:
- packages/generation/**
- packages/validation/**
- spec/validation/**
- tests/unit/generation/**
- tests/unit/validation/**
- fixtures/generation/**

Constraints:
- packages/domain, db/schema, spec/openapi 수정 금지
- deterministic renderer 우선
- 근거가 약한 항목은 명시적으로 다룰 수 있는 구조 유지
- validation 없이 publish 하는 흐름을 만들지 않음

Expected Deliverables:
- generation core
- validation core
- rules/fixtures/tests

Verification:
- `make test PYTEST_ARGS="tests/unit/generation tests/unit/validation"`

Report Format:
- Changed Files
- What I Implemented
- Verification
- Open Risks / Blockers
