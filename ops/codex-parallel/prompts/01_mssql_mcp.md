PROJECT.md, AGENTS.md, ARCHITECTURE.md, TOOLS.md, POLICY.md, EVAL_SPEC.md 를 읽고 기준으로 작업해.
추가로 `tasks/0002-metadata-mcp-mvp.md`, `spec/mcp/mssql_metadata_tool_catalog.yaml`, `services/mssql-mcp/README.md`, `config/mssql/local_docker_profiles.yaml`, `.env.example`, `tests/unit/test_mcp_catalog.py`, `tests/unit/test_mssql_mcp_live_config.py` 를 먼저 확인해.

너는 **MSSQL Metadata MCP 트랙 담당**이다.
이 작업은 병렬 worker 중 하나이며, 반드시 지정된 경로만 수정해.
공유 계약이 부족하면 임의 확장하지 말고 blocker 로 보고해. 단, MCP tool catalog 자체(`spec/mcp/**`)는 이 트랙의 소유 범위다.

Role:
- mcp_engineer

Preferred Skills:
- mcp-tooling-design
- contract-to-code

Task:
- `services/mssql-mcp` 에 read-only metadata MCP MVP 를 현재 skeleton 에서 한 단계 구현해.
- `tasks/0002-metadata-mcp-mvp.md` 의 최소 목표인 `get_procedure_definition`, `get_procedure_parameters`, `get_table_schema`, `search_tables` 를 우선 기준으로 삼아 tool schema, registry, adapter boundary, error model, fixture-backed response 를 맞춰.
- 현재 앱에 이미 있는 `/health`, `/health/ready`, `/config/db-profiles`, `/catalog/tools`, `settings.py`, `profiles.py`, `live_connection.py` 를 유지하면서 확장해.
- live DB 는 선택 사항이다. 기본 테스트는 fixture-first 로 통과해야 하고, `MSSQL_ENABLE_LIVE_METADATA=1` 일 때만 optional readiness/live adapter 를 사용해.

In Scope:
- MCP service entrypoint / app wiring 보강
- `spec/mcp/mssql_metadata_tool_catalog.yaml` 와 Python tool registry 동기화
- 정형 입력 기반 tool request/response model
- read-only enforcement layer
- snapshotId / collectedAt / evidenceRefs / error code response shape
- fixture adapter / fake repository
- optional live metadata adapter boundary. 단, 실제 DB 연결이 없어도 테스트 통과
- profile registry public response. secret/connection string 반환 금지
- contract tests / unit tests

Out of Scope:
- 실제 DB write 기능
- 자유 SQL 실행기
- 실제 데이터 row 조회
- API/BFF 구현
- Web UI 구현
- packages/domain 변경
- OpenAPI 변경. API surface 확장이 필요하면 blocker 보고
- DB 컨테이너 up/down 또는 schema apply 자동화

Target Files/Dirs:
- services/mssql-mcp/**
- spec/mcp/**
- tests/contract/mcp/**
- tests/unit/mcp/**
- tests/unit/test_mcp_catalog.py
- tests/unit/test_mssql_mcp_live_config.py
- tests/contract/test_local_mssql_connection_assets.py
- fixtures/mcp/**

Read-only References:
- PROJECT.md
- ARCHITECTURE.md
- POLICY.md
- .env.example
- config/mssql/local_docker_profiles.yaml
- spec/policy/platform_db_standardization_rules_for_ai.json

Constraints:
- packages/domain, spec/openapi, db/schema, 루트 문서는 수정 금지
- 메타데이터 read-only 만 허용
- tool 입력은 정형 파라미터 기반으로 유지하고 free-form SQL 문자열을 받지 않는다.
- 실제 MSSQL 연결이 없더라도 테스트 가능한 구조로 작성
- local DB up/down 전제를 만들지 않음
- `MSSQL_METADATA_PASSWORD` 등 비밀값을 응답, 로그, fixture, 문서에 넣지 않음
- `dbProfileId` 는 profile registry 의 id(`master`, `plf`, `ppm` 등)를 사용하고 database 이름과 분리해 다룬다.
- 확정 불가능한 metadata description 은 추론 표시 또는 review-required 성격으로 반환할 수 있게 한다.

Expected Deliverables:
- 실행 가능한 MCP service skeleton 보강
- tool registry / schema / adapter boundary
- fixture 기반 contract tests
- read-only guardrail tests
- optional live readiness 는 env-gated 로 유지

Verification:
- `make test PYTEST_ARGS="tests/contract/mcp tests/unit/mcp tests/unit/test_mcp_catalog.py tests/unit/test_mssql_mcp_live_config.py"`
- 필요 시 `python -m compileall services/mssql-mcp tests`
- `make run-mcp` smoke 는 환경이 준비된 경우에만 수행하고, live DB 없이는 강제하지 않음

Report Format:
- Changed Files
- What I Implemented
- Verification
- Open Risks / Blockers

추가 규칙:
- 첫 응답에서 수정 예정 파일, 예상 테스트 명령, blocker 후보를 짧게 제시해.
- `spec/mcp` 와 Python registry 가 어긋나면 먼저 어떤 쪽을 기준으로 맞출지 명시하고 작은 변경으로 정리해.
