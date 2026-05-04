PROJECT.md, AGENTS.md, ARCHITECTURE.md, TOOLS.md, POLICY.md, EVAL_SPEC.md 를 읽고 기준으로 작업해.
추가로 `spec/openapi/ai_agent_platform_openapi_v1.yaml`, `spec/mcp/mssql_metadata_tool_catalog.yaml`, `spec/validation/validation_rules.yaml`, `spec/policy/**`, `.env.example`, `.env.example`, `ops/codex-parallel/REQUEST_MANIFEST.yaml` 를 확인해.

너는 **최종 읽기 전용 리뷰어**다.
이 작업은 코드를 수정하지 않고 correctness, policy compliance, docs drift, missing tests, unsafe assumptions 를 점검하는 최종 게이트다.

Role:
- reviewer

Preferred Skills:
- quality-gate-review

Task:
- 병합된 전체 저장소를 읽기 전용으로 검토해.
- correctness, policy compliance, contract drift, missing tests, docs drift, unsafe assumptions 를 우선 순위로 정리해.
- 실제 릴리스 전에 막아야 하는 항목과 후속 개선 항목을 구분해.

In Scope:
- 전체 diff 또는 현재 저장소 상태 리뷰
- 정책 위반 여부 점검
- 테스트 누락 / 위험한 가정 탐지
- 문서와 구현의 불일치 점검
- OpenAPI ↔ API route ↔ domain enum ↔ DDL 상태/타입 명칭 drift 점검
- MCP catalog ↔ Python registry ↔ tests drift 점검
- generation policy ↔ golden sample ↔ validation rules drift 점검
- `.env.example` / `.env.example` / docs 의 secret handling 점검
- Docker/worktree/port strategy 문서와 Makefile/scripts 정합성 점검

Out of Scope:
- 코드 수정
- 대규모 재설계
- 실제 DB 접속 강제
- 스타일 취향 위주의 리뷰

Target Files/Dirs:
- 전체 저장소 읽기 전용 검토

Constraints:
- 읽기 전용
- 모호한 지적보다 재현 가능하고 우선순위 있는 finding 위주
- 스타일 취향보다 correctness / security / policy / docs drift 우선
- 정책 위반 가능성이 있으면 반드시 severity 를 높게 부여
- secrets, row data, 자동 DDL, 무검증 publish 경로는 P0/P1 위험으로 다룬다.

Expected Deliverables:
- review memo
- severity 별 findings
- must-fix before merge / can-follow-up later 구분
- 실행한 read-only 검증 명령과 결과

Verification:
- 실행 가능한 최소 read-only 확인 명령
- 필요한 경우 `make test`, `make test-web-smoke`, `make dev-ports` 결과 재확인
- 실행하지 못한 명령은 이유를 명시

반드시 아래 형식으로 답해:
- Findings
- Severity
- Rationale / Repro Steps
- Suggested Fix
- Residual Risk
