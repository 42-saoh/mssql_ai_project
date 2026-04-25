PROJECT.md, AGENTS.md, ARCHITECTURE.md, TOOLS.md, POLICY.md 를 읽고 기준으로 작업해.
추가로 `spec/openapi/ai_agent_platform_openapi_v1.yaml`, `apps/web/package.json`, `apps/web/app/`, `.env.sample`, `Makefile`, `scripts/resolve_dev_ports.sh` 를 확인해.

너는 **Web Portal Shell 트랙 담당**이다.
이 작업은 병렬 worker 중 하나이며, backend 계약을 임의 확장하지 않고 mock adapter 로 경계를 유지해야 한다.
현재 web 은 Next.js App Router 기반 starter 이며, pnpm lockfile 이 이미 존재한다.

Role:
- platform_worker

Preferred Skills:
- contract-to-code
- browser-automation-smoke

Task:
- `apps/web` 에 중앙 포털의 최소 shell 을 구현해.
- request 생성 화면, job 상태 화면, artifact preview 화면, validation/review 상태 표시의 초안을 만들고, API 미구현 상태를 고려해 mock data adapter 를 사용해.
- 화면의 데이터 shape 는 OpenAPI skeleton 을 읽고 맞추되, API client 와 mock adapter 를 분리해 이후 P05 API 와 연결하기 쉽게 만든다.

In Scope:
- Next.js app shell / routes / components
- request form for SP analysis target and output selection
- job status view using draft/validating/review_pending/approved/rejected 상태
- artifact preview view with evidence refs, validation status, review checklist placeholder
- mock data layer and API client boundary
- basic smoke/unit tests if feasible
- README 또는 작은 usage note. 단, 동작/명령이 바뀐 경우에만

Out of Scope:
- 실제 API 구현
- packages/domain 변경
- spec/openapi 변경
- auth real integration
- production styling perfection
- destructive approval action 또는 실제 publish 호출

Target Files/Dirs:
- apps/web/**
- tests/unit/web/**

Read-only References:
- spec/openapi/**
- PROJECT.md
- ARCHITECTURE.md
- POLICY.md
- .env.sample
- Makefile

Constraints:
- spec/openapi 는 읽기 전용으로 사용
- mock layer 와 API client layer 를 분리
- 다른 트랙 파일 수정 금지
- 현재 단계는 shell 과 정보 구조가 목적
- 포트는 하드코딩하지 말고 `make run-web` / `WEB_PORT` / `scripts/resolve_dev_ports.sh` 기준을 따른다.
- mock 화면에서도 실제 데이터 조회, 자동 DDL 실행, 무검증 코드 반영처럼 보이는 액션을 만들지 않는다.

Expected Deliverables:
- web shell app
- mock screens for request/job/artifact/validation-review flows
- basic tests or smoke guidance
- P05 API 연결을 위한 작은 client boundary

Verification:
- `make test-web-smoke`
- 로컬 base URL 이 준비되면 승인된 범위에서 Playwright MCP smoke
- 실행이 불가능하면 실행 막는 이유를 구체적으로 보고

Report Format:
- Changed Files
- What I Implemented
- Verification
- Open Risks / Blockers

추가 규칙:
- 첫 응답에서 수정 예정 파일, 예상 테스트 명령, blocker 후보를 짧게 제시해.
- Next.js/React 문맥이 불확실하면 `apps/web/package.json` 의 버전을 먼저 보고 필요한 경우에만 context7-docs 로 확인해.
