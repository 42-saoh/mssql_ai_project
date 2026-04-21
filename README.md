# Codex Project Scaffold

이 번들은 Codex CLI 로 로컬에서 개발을 시작하기 위한 루트 문서, repo-scoped agents, repo-scoped skills, 기본 config 를 포함한다.

## 포함 항목

- 루트 운영 문서
  - `PROJECT.md`
  - `AGENTS.md`
  - `ROLES.md`
  - `SKILLS.md`
  - `ARCHITECTURE.md`
  - `TOOLS.md`
  - `POLICY.md`
  - `EVAL_SPEC.md`
  - `TASK_TEMPLATE.md`
- Codex 설정
  - `.codex/config.toml`
  - `.codex/agents/*.toml`
- Repo skills
  - `.agents/skills/*/SKILL.md`
- 기존 설계 자산
  - `spec/openapi/ai_agent_platform_openapi_v1.yaml`
  - `db/schema/ai_agent_platform_schema_v2_dbo_prefix.sql`

## 권장 사용 순서

1. 이 파일 세트를 저장소 루트에 복사한다.
2. `AGENTS.md` 와 `PROJECT.md` 를 먼저 검토한다.
3. 설계 작업은 `architect` 역할, 구현 작업은 `platform_worker` 또는 `mcp_engineer`, 검토는 `reviewer` 역할로 분리한다.
4. 처음에는 기본 프로필 `safe-explore` 로 탐색한다.
5. 실제 편집이 필요하면 `dev-edit` 프로필을 사용한다.
6. 작업 전후로 `TASK_TEMPLATE.md` 와 `EVAL_SPEC.md` 를 기준으로 검증한다.

## 운영 메모

- 이 번들은 기준 문서를 바탕으로 만든 초기 세트다.
- 실제 코드베이스가 만들어지면 명령, 경로, 스택 선택을 코드에 맞게 갱신해야 한다.

## 추가 항목

추가로 아래 디렉터리와 자산을 포함한다.

- 애플리케이션 skeleton
  - `apps/api`
  - `apps/web`
  - `services/mssql-mcp`
- 패키지/계약/검증 자산
  - `packages/domain`
  - `packages/analysis`
  - `packages/generation`
  - `packages/validation`
  - `packages/templates`
  - `spec/mcp`
  - `spec/validation`
- 운영 자산
  - `docs/admin-guide`
  - `docs/user-guide`
  - `ops/codex-parallel`
  - `tasks`
  - `scripts`
  - `docker/test`

## 빠른 시작

1. `.env.example` 를 복사해 `.env.local` 을 만든다.
2. Python/Web 의존성을 준비한다.
   - `python -m pip install -e .[dev]`
   - `cd apps/web && pnpm install`
3. API 와 MCP 서버를 각각 실행한다.
   - `make run-api`
   - `make run-mcp`
4. 포털 UI 가 필요하면 실행한다.
   - `make run-web`
5. 테스트 러너 이미지를 준비한다.
   - `make test-build`
6. 기본 검증을 수행한다.
   - `make test`
   - `make test-web-smoke`
   - `make check`

## DB 와 스키마 운영 방식

- 플랫폼 DB 와 메타데이터 소스 DB 는 저장소 밖의 외부 환경에서 관리한다.
- 저장소는 DB 기동/중지 자동화를 제공하지 않는다.
- 스키마 변경이 필요하면 `db/schema/` 아래에 버전 업 SQL 파일을 추가하고, 실제 적용은 사용자가 수동으로 수행한다.

## Docker 기반 검증

- 기본 테스트 진입점은 `docker/test/` 아래의 도커 테스트 러너다.
- `make test` 는 파이썬 테스트를 도커 컨테이너 안에서 실행한다.
- `make test-web-smoke` 는 현재 단계에서 web 자동 테스트 대신 컨테이너 기반 build smoke 를 수행한다.
- UI 수동/반자동 smoke 가 필요하면 Playwright MCP 와 `browser-automation-smoke` skill 을 사용한다.

