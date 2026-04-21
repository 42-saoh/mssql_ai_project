PROJECT.md, AGENTS.md, ARCHITECTURE.md, TOOLS.md, POLICY.md, EVAL_SPEC.md 를 읽고 기준으로 작업해.

너는 **MSSQL Metadata MCP 트랙 담당**이다.
이 작업은 병렬 worker 중 하나이며, 반드시 지정된 경로만 수정해.
공유 계약이 부족하면 임의 확장하지 말고 blocker 로 보고해.

Role:
- mcp_engineer

Preferred Skills:
- mcp-tooling-design

Task:
- `services/mssql-mcp` 에 read-only metadata MCP 서비스 골격을 구현해.
- `spec/mcp/mssql_metadata_tool_catalog.yaml` 를 기준으로 tool registry, input/output schema, error model, fixture-backed adapter 를 추가해.
- live DB 의존 없이 contract-first + fixture-first 로 진행해.

In Scope:
- MCP service entrypoint / app wiring
- tool catalog loader 또는 정적 registry
- read-only enforcement layer
- snapshot/evidence response shape
- fixture adapter / fake repository
- contract tests / unit tests

Out of Scope:
- 실제 DB write 기능
- 자유 SQL 실행기
- 실제 데이터 row 조회
- API/BFF 구현
- Web UI 구현
- packages/domain 변경

Target Files/Dirs:
- services/mssql-mcp/**
- spec/mcp/**
- tests/contract/mcp/**
- tests/unit/mcp/**
- fixtures/mcp/**

Constraints:
- packages/domain, spec/openapi, db/schema, 루트 문서는 수정 금지
- 메타데이터 read-only 만 허용
- tool 입력은 정형 파라미터 기반으로 유지
- 실제 MSSQL 연결이 없더라도 테스트 가능한 구조로 작성
- local DB up/down 전제를 만들지 않음
- snapshot_id, evidence refs, error code 모델을 명확히 남김

Expected Deliverables:
- 실행 가능한 MCP service skeleton
- tool registry / adapter boundary
- fixture 기반 contract tests
- read-only guardrail tests

Verification:
- `make test PYTEST_ARGS="tests/contract/mcp tests/unit/mcp"`
- 가능한 범위에서 service import / smoke

Report Format:
- Changed Files
- What I Implemented
- Verification
- Open Risks / Blockers
