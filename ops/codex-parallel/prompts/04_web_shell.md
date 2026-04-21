PROJECT.md, AGENTS.md, ARCHITECTURE.md, TOOLS.md, POLICY.md 를 읽고 기준으로 작업해.

너는 **Web Portal Shell 트랙 담당**이다.
이 작업은 병렬 worker 중 하나이며, backend 계약을 임의 확장하지 않고 mock adapter 로 경계를 유지해야 한다.

Role:
- platform_worker

Preferred Skills:
- contract-to-code
- browser-automation-smoke

Task:
- `apps/web` 에 중앙 포털의 최소 shell 을 구현해.
- request 생성 화면, job 상태 화면, artifact preview 화면의 초안을 만들고, API 미구현 상태를 고려해 mock data adapter 를 사용해.

In Scope:
- web app scaffold
- routes/pages for request form, jobs, artifacts
- UI state for draft/validated/review_pending/approved
- mock data layer
- smoke/unit tests if feasible

Out of Scope:
- 실제 API 구현
- packages/domain 변경
- spec/openapi 변경
- auth real integration
- production styling perfection

Target Files/Dirs:
- apps/web/**
- tests/unit/web/**

Constraints:
- spec/openapi 는 읽기 전용으로 사용
- mock layer 와 API client layer 를 분리
- 다른 트랙 파일 수정 금지
- 현재 단계는 shell 과 정보 구조가 목적

Expected Deliverables:
- web shell app
- mock screens for core flows
- basic tests or smoke guidance

Verification:
- `make test-web-smoke`
- 로컬 base URL 이 준비되면 승인된 범위에서 Playwright MCP smoke
- 실행이 불가능하면 실행 막는 이유를 구체적으로 보고

Report Format:
- Changed Files
- What I Implemented
- Verification
- Open Risks / Blockers
