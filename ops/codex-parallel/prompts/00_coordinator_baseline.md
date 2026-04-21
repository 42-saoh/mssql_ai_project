PROJECT.md, AGENTS.md, ARCHITECTURE.md, TOOLS.md, POLICY.md, EVAL_SPEC.md, TASK_TEMPLATE.md 를 먼저 읽고 기준으로 작업해.

너는 이 저장소의 **코디네이터 겸 베이스라인 고정 담당**이다.
이번 작업은 병렬 개발에 들어가기 전에 공유 계약과 공통 골격을 고정하는 단계다.
다른 worker가 이후 병렬로 구현할 수 있도록 공통 경계를 먼저 준비해.

Role:
- architect
- platform_worker

Preferred Skills:
- repo-bootstrap
- contract-to-code

Task:
- 병렬 개발의 기준선이 되는 저장소 골격과 공유 계약을 고정해.
- 루트 문서, `.codex` 설정, 공통 명령, `packages/domain`, `spec/openapi`, `db/schema`, `docker/test` 를 정리해.
- 이후 worker가 충돌 없이 작업할 수 있도록 디렉터리 경계와 최소 실행 골격을 만든다.

In Scope:
- 루트 문서 정합성 점검 및 최소 보완
- `.codex/config.toml`, `.codex/agents`, `.agents/skills` 정비
- `Makefile`, `pyproject.toml`, workspace 수준 설정 추가
- `packages/domain` 에 CanonicalAnalysisModel, status enum, artifact enum 등 최소 공통 계약 추가
- `spec/openapi/` 와 `db/schema/` 에 현재 기준 파일 배치
- `docker/test/` 에 공통 테스트 러너 기준선 배치
- `apps/`, `services/`, `packages/`, `tests/`, `fixtures/`, `docs/adr/` 의 최소 디렉터리 골격 추가

Out of Scope:
- MSSQL MCP 상세 구현
- 분석 엔진 상세 구현
- 생성기/검증기 상세 구현
- API 세부 로직 구현
- Web UI 상세 구현

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
- packages/domain/**
- db/schema/**
- spec/openapi/**
- docs/adr/**
- docker/test/**
- 빈 디렉터리 골격

Constraints:
- 이후 worker가 사용할 공유 기준선이므로 명확하고 작게 만든다.
- 다른 트랙 구현 영역까지 선점하지 않는다.
- 실제 데이터 접근 금지
- 자동 DDL 실행 금지
- DB lifecycle 관리 금지
- 무검증 자동 반영 금지
- 병렬 worker가 수정할 필요가 없을 정도로 최소 계약만 만든다.

Expected Deliverables:
- 병렬 작업 가능한 저장소 골격
- 공통 domain 계약
- 현재 기준 OpenAPI/DDL 배치
- 공통 실행/검증 명령 초안

Verification:
- 가능한 범위에서 `python -m compileall apps services packages tests`
- `make test`
- `make test-web-smoke`
- 실패 시 정확한 실패 원인과 비어 있는 영역을 보고

Report Format:
- Changed Files
- What I Implemented
- Verification
- Open Risks / Follow-ups

추가 규칙:
- 이 단계가 끝난 뒤 worker는 `packages/domain`, `spec/openapi`, `db/schema`, `docker/test`, 루트 문서를 읽기 전용 기준으로 사용한다.
- 이 경계를 넘는 구현은 하지 마.
