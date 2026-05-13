# MSSQL Analysis Agent Platform Starter

MSSQL Stored Procedure 분석, 문서화, Java/MyBatis 전환 코드 초안 생성, 검증 흐름을 위한 중앙 Agent 플랫폼 저장소다.
현재 active 검증 표면은 fixture-first baseline, quality gate, web smoke, explicit live confidence gate 로 통합되어 있다. Pxx 산출물은 `ops/codex-parallel` 과 `docs/test-gate-history.md` 에 이력 증거로 보존한다.

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

1. `.env.example` 또는 환경별 템플릿을 참고해 `.env` 를 만든다.
   - Mac local Docker + OpenAI: `config/env/mac-docker-openai.env.example`
   - Windows sandbox + P-GPT: `config/env/windows-sandbox-pgpt.env.example`
   - `MSSQL_METADATA_DEFAULT_PROFILE_ID=master`
   - `PLATFORM_DB_NAME=PLF`
   - `ppm` profile 은 항상 `PPM` 을 가리키며 PPM 실패 시 PLF 로 대체하지 않는다.
   - password/token 값은 비워 두고 로컬 비밀 저장소나 `.env` 에서만 채운다.
2. Python/Web 의존성을 lockfile 기준으로 준비한다.
   - `make setup`
   - Windows host where Python 3.14 is exposed as `python`: set `PYTHON=python` in `.env`, install Git Bash/GNU Make/pnpm, then run Makefile commands through `scripts/win_git_bash.ps1`.
   - Windows example: `powershell -ExecutionPolicy Bypass -File scripts/win_git_bash.ps1 make setup`
3. API 와 MCP 서버를 각각 실행한다.
   - `make run-api`
   - `make run-mcp`
4. 포털 UI 가 필요하면 실행한다.
   - `make run-web`
5. 테스트 러너 이미지를 준비한다.
   - `make test-build`
6. 기본 검증을 수행한다.
   - `make test-core`
   - `make test-quality`
   - `make test-web`
   - `make check`

Host Python must be Python 3.14. The executable name is host-specific: macOS/Linux commonly use `python3.14`, while this Windows workspace uses `.env` `PYTHON=python`.
On Windows, prefer `scripts/win_git_bash.ps1` for `make` and `pnpm` commands because the WinGet Links shim can fail under PowerShell while the real package path works from Git Bash.

## DB 와 스키마 운영 방식

- 플랫폼 DB 와 메타데이터 소스 DB 는 저장소 밖의 외부 환경에서 관리한다.
- 저장소는 DB 기동/중지 자동화를 제공하지 않는다.
- 스키마 변경이 필요하면 `db/schema/` 아래에 버전 업 SQL 파일을 추가하고, 실제 적용은 사용자가 수동으로 수행한다.
- 기본 metadata profile id 는 `master` 이며 `config/mssql/local_docker_profiles.yaml` 의 `master -> master`, `plf -> PLF`, `ppm -> PPM` 매핑을 사용한다. `PLF` 는 platform DB, `PPM` 은 pilot analysis target DB 이며, PPM 이 없거나 접근 불가하면 PLF로 임의 대체하지 않는다.
- 기본 e2e/eval 경로는 `fixtures/mcp/metadata_snapshot.json` 기반이므로 live MSSQL 이 필요하지 않다.

## Docker 기반 검증

- 기본 테스트 진입점은 `docker/test/` 아래의 도커 테스트 러너다.
- `make test` 는 파이썬 테스트를 도커 컨테이너 안에서 실행하는 저수준 진입점이다.
- `make test-core` 는 unit/contract/integration/e2e fixture baseline 을 실행한다.
- `make test-quality` 는 eval/quality fixture gate 를 실행한다.
- `make test-web` 는 web static/http smoke 와 build smoke 를 실행한다.
- `make test-live-confidence` 는 승인된 live 환경에서만 실행하는 confidence suite 다.
- UI 수동/반자동 smoke 가 필요하면 Playwright MCP 와 `browser-automation-smoke` skill 을 사용한다.
- `make test-core`, `make test-quality`, `make test-web` 는 live/remote flag 를 명령 레벨에서 끄므로 `.env` 에 live 값이 있어도 외부 DB/LLM 을 호출하지 않는다.
- Windows 에서는 같은 검증을 `powershell -ExecutionPolicy Bypass -File scripts/win_git_bash.ps1 make test-core` 형태로 실행한다.
