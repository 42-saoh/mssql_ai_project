PROJECT.md, AGENTS.md, ARCHITECTURE.md, TOOLS.md, POLICY.md, EVAL_SPEC.md 를 읽고 기준으로 작업해.
추가로 `spec/openapi/ai_agent_platform_openapi_v1.yaml`, `apps/api/README.md`, `apps/api/api_app/`, `packages/domain/src/ai_agent_domain/models.py`, P01/P02/P03 병합 산출물을 확인해.

너는 **API / Workflow 통합 트랙 담당**이다.
이 작업은 Wave 1 산출물이 병합된 뒤 수행하는 통합 단계다.
읽기 전용 기준선과 병합된 packages 를 사용해 `apps/api` 를 구성해.

Role:
- platform_worker

Preferred Skills:
- contract-to-code
- quality-gate-review

Task:
- `apps/api` 에 request/job/artifact/validation/approval/metadata/registry 최소 API 를 OpenAPI skeleton 과 최대한 맞춰 구현해.
- workflow state machine, in-memory 또는 stub repository, service wiring, integration tests 를 추가해.
- 현재 starter 에 이미 있는 `/health`, `/api/v1/requests/sp-analysis`, `/api/v1/jobs/{job_id}` 를 유지하면서 OpenAPI 의 누락 endpoint 를 좁은 slice 로 채워.

In Scope:
- FastAPI app structure 정리
- request/job/artifact routes
- artifact preview and validation endpoint skeleton
- deferred approval decision recording skeleton
- metadata profile/tools proxy 또는 stub route
- registry version binding stub route
- workflow transitions: submitted → collecting_metadata → analyzing → generating → validating → validation_complete / failed
- validation/approval/publish gate skeleton. publish 실행이 아니라 gate 표현만
- in-memory repositories or stub persistence adapters
- integration tests and unit tests

Out of Scope:
- 실 DB persistence 완성
- 실제 배포 구성
- Web app 구현
- MSSQL MCP 상세 수정
- generation/analysis core 상세 수정
- OpenAPI 계약 대변경
- 실제 DDL 실행 또는 운영 DB 변경

Target Files/Dirs:
- apps/api/**
- tests/integration/api/**
- tests/unit/api/**

Read-only References:
- packages/domain/**
- packages/analysis/**
- packages/generation/**
- packages/validation/**
- services/mssql-mcp/**
- spec/openapi/**
- spec/mcp/**
- spec/validation/**
- db/schema/**

Constraints:
- packages/domain, packages/analysis, packages/generation, packages/validation 는 읽기 전용 참조
- spec/openapi, db/schema 변경이 필요하면 blocker 로 보고
- 실제 데이터 접근 금지
- validation gate 없는 publish 경로 금지
- 비밀값, DB connection string, row-data 를 API 응답으로 노출하지 않음
- 상태/enum 명칭이 domain/OpenAPI/DDL 사이에서 불일치하면 조용히 새 enum 을 만들지 말고 alias, TODO, blocker 중 하나로 명확히 처리

Expected Deliverables:
- runnable API skeleton
- workflow services and in-memory repositories
- OpenAPI-aligned route coverage for first integration slice
- integration tests
- clear TODOs for real persistence / auth integration / MCP transport integration

Verification:
- `make test PYTEST_ARGS="tests/integration/api tests/unit/api"`
- 필요한 최소 unit tests
- `python3.14 -m compileall apps/api tests/integration/api tests/unit/api`
- app import / route smoke

Report Format:
- Changed Files
- What I Implemented
- Verification
- Open Risks / Blockers

추가 규칙:
- 첫 응답에서 수정 예정 파일, 예상 테스트 명령, blocker 후보를 짧게 제시해.
- OpenAPI skeleton 과 현재 starter API 가 어긋나는 부분은 구현으로 맞출 수 있는 것과 계약 논의가 필요한 것을 분리해.
