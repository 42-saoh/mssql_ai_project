PROJECT.md, AGENTS.md, ARCHITECTURE.md, TOOLS.md, POLICY.md, EVAL_SPEC.md 를 읽고 기준으로 작업해.

너는 **API / Workflow 통합 트랙 담당**이다.
이 작업은 Wave 1 산출물이 병합된 뒤 수행하는 통합 단계다.
읽기 전용 기준선과 병합된 packages 를 사용해 `apps/api` 를 구성해.

Role:
- platform_worker

Preferred Skills:
- contract-to-code

Task:
- `apps/api` 에 request/job/artifact/validation/approval 최소 API 를 구현해.
- workflow state machine, in-memory 또는 stub repository, service wiring, integration tests 를 추가해.
- `spec/openapi` 와 가능한 범위에서 정합성을 맞춰.

In Scope:
- FastAPI app structure
- request/job/artifact routes
- workflow transitions
- validation/approval/publish gate skeleton
- in-memory repositories or stub persistence adapters
- integration tests

Out of Scope:
- 실 DB persistence 완성
- 실제 배포 구성
- Web app 구현
- MSSQL MCP 상세 수정
- generation/analysis core 수정

Target Files/Dirs:
- apps/api/**
- tests/integration/api/**
- tests/unit/api/**

Constraints:
- packages/domain, packages/analysis, packages/generation, packages/validation 는 읽기 전용 참조
- spec/openapi, db/schema 변경이 필요하면 blocker 로 보고
- 실제 데이터 접근 금지
- approval gate 없는 publish 경로 금지

Expected Deliverables:
- runnable API skeleton
- workflow services
- integration tests
- clear TODOs for real persistence / auth integration

Verification:
- `make test PYTEST_ARGS="tests/integration/api tests/unit/api"`
- 필요한 최소 unit tests
- app import / route smoke

Report Format:
- Changed Files
- What I Implemented
- Verification
- Open Risks / Blockers
