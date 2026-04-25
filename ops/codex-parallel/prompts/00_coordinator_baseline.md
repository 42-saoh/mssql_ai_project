PROJECT.md, AGENTS.md, ARCHITECTURE.md, TOOLS.md, POLICY.md, EVAL_SPEC.md, TASK_TEMPLATE.md 를 먼저 읽고 기준으로 작업해.
추가로 현재 기준 자산인 `spec/openapi/ai_agent_platform_openapi_v1.yaml`, `db/schema/ai_agent_platform_schema_v2_dbo_prefix.sql`, `spec/mcp/mssql_metadata_tool_catalog.yaml`, `spec/validation/validation_rules.yaml`, `spec/policy/**`, `.env.sample`, `Makefile`, `docker/test/docker-compose.yml`, `requirements/lock/py311-dev.txt`, `pnpm-lock.yaml` 을 확인해.

너는 이 저장소의 **코디네이터 겸 베이스라인 고정 담당**이다.
이번 작업은 병렬 개발에 들어가기 전에 공유 계약과 공통 골격이 현재 파일 기준으로 흔들리지 않는지 점검하고, 필요한 최소 보완만 수행하는 단계다.
큰 구조를 다시 만들지 말고, 이미 존재하는 기준선을 읽고 검증 가능한 상태로 고정해.

Role:
- architect
- platform_worker

Preferred Skills:
- repo-bootstrap
- contract-to-code
- docs-sync

Task:
- 병렬 개발의 기준선이 되는 저장소 골격, 공유 계약, 실행 명령, 정책 파일, lockfile 상태를 점검해.
- 현재 존재하는 OpenAPI skeleton, Platform DB DDL draft, MCP catalog, validation rules, policy assets, `.env.sample`, Docker test runner, worktree port resolver 가 서로 모순되지 않게 최소 보완해.
- 이후 worker가 충돌 없이 작업할 수 있도록 디렉터리 경계와 검증 명령을 명확히 남겨.

In Scope:
- 루트 문서 정합성 점검 및 최소 보완
- `.codex/config.toml`, `.codex/agents`, `.agents/skills` 의 현재 역할/스킬 경계 확인
- `Makefile`, `pyproject.toml`, root `package.json`, `apps/web/package.json`, `pnpm-lock.yaml` 의 재현성 기준 확인
- `packages/domain` 의 최소 공통 계약 확인. 확장이 필요하면 작은 계약 패치로만 처리하고 worker 영역 구현은 하지 않음
- `spec/openapi/`, `spec/mcp/`, `spec/validation/`, `spec/policy/`, `db/schema/` 의 존재와 상호 명칭 drift 점검
- `.env.sample` 은 비밀값 없는 기본 샘플로 유지하고, `.env` 또는 실제 credential 은 생성/커밋하지 않음
- `docker/test/`, `scripts/compose_project_name.sh`, `scripts/resolve_dev_ports.sh`, 설치 스크립트의 병렬 worktree 기준 확인
- 필요한 경우 prompt pack 또는 runbook 의 경로/명령 drift 최소 수정
- 공유 계약 존재 여부를 보장하는 contract test 보강

Out of Scope:
- MSSQL MCP 상세 tool adapter 구현
- 분석 엔진 상세 구현
- 생성기/검증기 상세 구현
- API 세부 workflow 구현
- Web UI 상세 구현
- 실제 DB 접속을 전제로 한 테스트 강제
- DB schema 자동 적용 또는 DB lifecycle 관리

Target Files/Dirs:
- AGENTS.md
- PROJECT.md
- ARCHITECTURE.md
- TOOLS.md
- POLICY.md
- EVAL_SPEC.md
- TASK_TEMPLATE.md
- .codex/**
- .agents/**
- Makefile
- pyproject.toml
- package.json
- apps/web/package.json
- .env.sample
- packages/domain/**
- db/schema/**
- spec/openapi/**
- spec/mcp/**
- spec/validation/**
- spec/policy/**
- docs/adr/**
- docker/test/**
- requirements/lock/**
- scripts/**
- ops/codex-parallel/**
- tests/contract/**
- 빈 디렉터리 골격

Constraints:
- 이후 worker가 사용할 공유 기준선이므로 변경은 명확하고 작게 만든다.
- 다른 트랙 구현 영역까지 선점하지 않는다.
- 실제 데이터 접근 금지
- 자동 DDL 실행 금지
- DB lifecycle 관리 금지
- 무검증 자동 반영 금지
- 비밀값을 `.env.sample`, 문서, fixture, 테스트에 넣지 않는다.
- 이미 있는 `pnpm-lock.yaml` 과 `requirements/lock/py311-dev.txt` 를 재현성 기준으로 취급한다.
- OpenAPI, DDL, domain, validation rule 간 명칭 불일치가 보이면 임의 확장보다 blocker 또는 작은 계약 정리로 처리한다.

Expected Deliverables:
- 현재 파일 기준으로 고정된 병렬 작업 기준선
- 공유 계약/정책/lockfile/환경 샘플 drift 점검 결과
- 필요한 경우 최소 contract test 보강
- 각 worker가 읽기 전용으로 참조해야 할 경계 정리

Verification:
- `make docker-project-name`
- `make dev-ports`
- `python -m compileall apps services packages tests`
- `make test`
- `make test-web-smoke`
- 실행이 불가능하면 정확한 실패 원인, 필요한 환경, 비어 있는 영역을 보고

Report Format:
- Changed Files
- What I Implemented
- Verification
- Open Risks / Follow-ups

추가 규칙:
- 첫 응답에서 수정 예정 파일, 예상 테스트 명령, blocker 후보를 짧게 제시해.
- 이 단계가 끝난 뒤 worker는 `packages/domain`, `spec/openapi`, `db/schema`, `spec/policy`, `docker/test`, 루트 문서를 읽기 전용 기준으로 사용한다.
- 이 경계를 넘는 구현은 하지 마.
