PROJECT.md, AGENTS.md, ARCHITECTURE.md, TOOLS.md, POLICY.md, EVAL_SPEC.md 를 읽고 기준으로 작업해.
추가로 `spec/openapi/ai_agent_platform_openapi_v1.yaml`, `spec/mcp/mssql_metadata_tool_catalog.yaml`, `spec/validation/validation_rules.yaml`, `spec/policy/**`, `.env.sample`, `ops/codex-parallel/REQUEST_MANIFEST.yaml` 를 확인해.

너는 **통합 검증 / Eval / Docs Sync 트랙 담당**이다.
이 단계는 앞선 트랙의 결과가 병합된 뒤 저장소를 한 번 정리하고, 최소 end-to-end 와 문서 정합성을 맞추는 목적이다.

Role:
- docs_curator
- reviewer

Preferred Skills:
- eval-fixture-authoring
- docs-sync
- browser-automation-smoke
- quality-gate-review

Task:
- 현재 병합된 결과를 기준으로 e2e/eval fixture 를 추가하고, 루트 문서와 운영 문서를 동기화해.
- 구현된 내용과 문서가 어긋나는 부분을 정리하고, follow-up backlog 를 남겨.
- 실제 구현이 없는 기능을 완료된 것처럼 문서화하지 말고, skeleton / stub / optional live / fixture-first 상태를 구분해.

In Scope:
- e2e or smoke tests for happy path
- eval fixtures / sample canonical payloads / sample artifact payloads
- docs sync for changed commands, paths, architecture notes
- OpenAPI/MCP/validation/policy drift memo
- known gaps / next slices documentation
- `.env.sample` 기준 환경 안내 정리. 단, 비밀값 예시는 넣지 않음

Out of Scope:
- 대규모 신규 기능 구현
- 계약 대변경
- 실제 배포 자동화
- DB schema 자동 적용
- 실제 데이터 조회/수정

Target Files/Dirs:
- tests/e2e/**
- tests/eval/**
- fixtures/eval/**
- docs/**
- 필요 시 루트 문서

Read-only References:
- apps/**
- services/**
- packages/**
- spec/**
- db/schema/**
- ops/codex-parallel/**
- .env.sample

Constraints:
- 신규 구현보다 통합 검증과 정합성 유지에 집중
- 문서에는 실제 구현된 것만 반영
- 남은 TODO 는 숨기지 말고 분리해서 기록
- 실 DB 연결은 optional 로만 설명하고, e2e 기본 경로는 fixture/stub 기반으로 유지
- 정책 위반 가능성이 있는 자동 publish, 자동 DDL, row-data access 흐름은 만들거나 문서화하지 않음

Expected Deliverables:
- e2e/eval assets
- synced docs
- follow-up backlog or known gaps memo
- 최소 happy path 가 어디까지 검증되는지 명확한 설명

Verification:
- `make test PYTEST_ARGS="tests/e2e tests/eval"`
- 가능하면 `make test` 와 `make test-web-smoke`
- 문서와 구현 비교 결과 요약

Report Format:
- Changed Files
- What I Implemented
- Verification
- Open Risks / Follow-ups

추가 규칙:
- 첫 응답에서 수정 예정 파일, 예상 테스트 명령, blocker 후보를 짧게 제시해.
- docs-sync 는 정확성을 우선한다. 멋진 로드맵보다 현재 동작/비동작 경계를 분명히 써.
