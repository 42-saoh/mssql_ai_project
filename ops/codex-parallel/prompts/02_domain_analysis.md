PROJECT.md, AGENTS.md, ARCHITECTURE.md, TOOLS.md, POLICY.md, EVAL_SPEC.md 를 읽고 기준으로 작업해.
추가로 `tasks/0003-analysis-canonical-model.md`, `packages/domain/src/ai_agent_domain/models.py`, `fixtures/mssql/`, `fixtures/metadata/schema_search_order_domain.json`, `spec/policy/platform_db_standardization_rules_for_ai.json` 를 확인해.

너는 **Domain Analysis Core 트랙 담당**이다.
이 작업은 병렬 worker 중 하나이며, 현재 병렬 경계에서는 `packages/domain` 을 읽기 전용 기준선으로 사용한다.
공통 domain 계약 확장이 꼭 필요하면 직접 수정하지 말고 blocker 로 보고해.

Role:
- template_engineer

Preferred Skills:
- contract-to-code
- eval-fixture-authoring

Task:
- `packages/analysis` 에 SP 분석 코어의 최소 구현을 추가해.
- 기존 `fixtures/mssql` 의 대표 SP fixture 를 사용해 SP parser skeleton, dependency extraction, transaction/exception/dynamic SQL/temp table detector 를 구성해.
- 결과는 향후 `CanonicalAnalysisModel` 로 변환 가능한 명시적 구조로 정리하되, 현재 `packages/domain` 에 없는 계약을 임의로 추가하지 않는다.

In Scope:
- analysis package 구조
- SP text parsing helpers
- procedure name / parameter / called procedure / table reference extraction skeleton
- transaction / TRY-CATCH / dynamic SQL / temp table detector
- dependency/call graph extraction skeleton
- schema search fixture 를 활용한 metadata enrichment helper
- analysis-local result model 또는 dict schema. 단, domain 계약 확장은 blocker
- representative fixtures and unit tests

Out of Scope:
- packages/domain 변경
- generation/validation 구현
- API/BFF 구현
- live DB access
- prompt/template registry 구현
- Java/MyBatis 생성

Target Files/Dirs:
- packages/analysis/**
- tests/unit/analysis/**
- fixtures/analysis/**

Read-only References:
- packages/domain/**
- fixtures/mssql/**
- fixtures/metadata/**
- spec/mcp/**
- spec/policy/platform_db_standardization_rules_for_ai.json

Constraints:
- packages/domain 수정 금지
- 구현은 fixture-first, deterministic-first
- 확정 불가능한 결과는 `REVIEW_REQUIRED`, `INFERRED_DESCRIPTION`, 또는 동등한 marker 로 표현 가능한 구조 유지
- 실제 SQL parser 완성보다 테스트 가능한 구조와 핵심 패턴 식별을 우선
- row data 조회나 live DB 연결을 만들지 않는다.
- 동적 SQL 내부 의존성처럼 확실하지 않은 분석은 단정하지 말고 uncertainty/review marker 로 남긴다.

Expected Deliverables:
- analysis core package
- parser/detector skeleton
- canonical conversion 준비 helper 또는 blocker 메모
- analysis unit tests and fixtures

Verification:
- `make test PYTEST_ARGS="tests/unit/analysis"`
- `python3.14 -m compileall packages/analysis tests/unit/analysis`

Report Format:
- Changed Files
- What I Implemented
- Verification
- Open Risks / Blockers

추가 규칙:
- 첫 응답에서 수정 예정 파일, 예상 테스트 명령, blocker 후보를 짧게 제시해.
- `tasks/0003` 의 domain expansion 요구와 병렬 경계가 충돌하면, 구현 가능한 analysis-local slice 와 coordinator blocker 를 분리해서 보고해.
