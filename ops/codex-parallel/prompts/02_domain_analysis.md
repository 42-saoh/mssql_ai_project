PROJECT.md, AGENTS.md, ARCHITECTURE.md, TOOLS.md, POLICY.md, EVAL_SPEC.md 를 읽고 기준으로 작업해.

너는 **Domain Analysis Core 트랙 담당**이다.
이 작업은 병렬 worker 중 하나이며, `packages/domain` 은 읽기 전용 기준선으로 사용한다.

Role:
- template_engineer

Preferred Skills:
- contract-to-code

Task:
- `packages/analysis` 에 SP 분석 코어의 최소 구현을 추가해.
- fixture 기반으로 SP parser skeleton, dependency extraction, transaction/exception/dynamic SQL/temp table detector 를 구성해.
- 결과는 기존 공통 계약으로 변환 가능한 형태로 정리해.

In Scope:
- analysis package 구조
- SP text parsing helpers
- pattern detectors
- dependency/call graph extraction skeleton
- canonical transform helpers
- representative fixtures and unit tests

Out of Scope:
- packages/domain 변경
- generation/validation 구현
- API/BFF 구현
- live DB access
- prompt/template registry 구현

Target Files/Dirs:
- packages/analysis/**
- tests/unit/analysis/**
- fixtures/analysis/**

Constraints:
- packages/domain 수정 금지
- 구현은 fixture-first, deterministic-first
- 확정 불가능한 결과는 review_required 성격으로 표시 가능한 구조 유지
- 실제 SQL parser 완성보다 테스트 가능한 구조와 핵심 패턴 식별을 우선

Expected Deliverables:
- analysis core package
- parser/detector skeleton
- canonical conversion helpers
- analysis unit tests and fixtures

Verification:
- `make test PYTEST_ARGS="tests/unit/analysis"`
- 필요한 최소 smoke import

Report Format:
- Changed Files
- What I Implemented
- Verification
- Open Risks / Blockers
