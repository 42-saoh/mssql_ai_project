# MSSQL Analysis Agent Platform Starter

MSSQL Stored Procedure 분석, 문서화, Java/MyBatis 전환 코드 초안 생성, 검증/승인 흐름을 위한 중앙 Agent 플랫폼 starter 저장소다.
현재 코드는 병렬 구현 트랙이 병합된 초기 통합 상태이며, 기본 검증은 fixture/stub 기반으로 동작한다.

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

## 현재 구현 상태

- implemented: FastAPI route skeleton, in-memory/API workflow tests, draft artifact rendering, validation checks, approval decision recording.
- fixture-first: MSSQL Metadata MCP tool invocation, API workflow metadata collection, e2e/eval happy path.
- stub/skeleton: Platform DB repository adapter, web portal shell, publish gate evaluation helper, full CanonicalAnalysisModel candidate.
- optional live: MCP readiness can probe an externally managed SQL Server when enabled; live tool query execution is still adapter-bound and not a completed metadata query implementation.
- follow-up: auth/RBAC, live metadata queries, publish API route, complete CanonicalAnalysisModel, broader eval suite, DDL draft renderer maturity.

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

1. `.env.example` 를 복사해 `.env` 를 만든다.
   - `MSSQL_METADATA_DEFAULT_PROFILE_ID=master`
   - `PLATFORM_DB_NAME=PLF`
   - password/token 값은 비워 두고 로컬 비밀 저장소나 `.env` 에서만 채운다.
2. Python/Web 의존성을 lockfile 기준으로 준비한다.
   - `make setup`
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

호스트에 `python` 명령이 없으면 `PYTHON=python3 make setup` 처럼 override 하거나, compile-only 확인은 `python3 -m compileall apps services packages tests` 로 수행한다.

## DB 와 스키마 운영 방식

- 플랫폼 DB 와 메타데이터 소스 DB 는 저장소 밖의 외부 환경에서 관리한다.
- 저장소는 DB 기동/중지 자동화를 제공하지 않는다.
- 스키마 변경이 필요하면 `db/schema/` 아래에 버전 업 SQL 파일을 추가하고, 실제 적용은 사용자가 수동으로 수행한다.
- 기본 metadata profile id 는 `master` 이며 `config/mssql/local_docker_profiles.yaml` 의 `master -> master`, `plf -> PLF` 매핑을 사용한다.
- 기본 e2e/eval 경로는 `fixtures/mcp/metadata_snapshot.json` 기반이므로 live MSSQL 이 필요하지 않다.

## Docker 기반 검증

- 기본 테스트 진입점은 `docker/test/` 아래의 도커 테스트 러너다.
- `make test` 는 파이썬 테스트를 도커 컨테이너 안에서 실행한다.
- `make test-web-smoke` 는 현재 단계에서 web 자동 테스트 대신 컨테이너 기반 build smoke 를 수행한다.
- UI 수동/반자동 smoke 가 필요하면 Playwright MCP 와 `browser-automation-smoke` skill 을 사용한다.
- P06 통합 검증 최소 경로는 `make test PYTEST_ARGS="tests/e2e tests/eval"` 이다.
