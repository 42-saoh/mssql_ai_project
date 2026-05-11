# TOOLS.md

## 목적

이 문서는 로컬 개발에서 사용할 도구, 명령 규약, MCP 구성을 정의한다.  
실제 저장소에 아직 명령이 없더라도, 부트스트랩 단계에서는 이 문서를 기준으로 표준 명령을 만든다.

## Codex 운용 기준

### 기본 프로필

- 기본: `safe-explore`
  - 읽기 전용 탐색
  - 설계/리뷰/조사 작업에 사용

### 구현 프로필

- 구현: `dev-edit`
  - workspace 내 편집 허용
  - 작은 기능 슬라이스 구현에 사용

### 리뷰 프로필

- 리뷰: `review`
  - 읽기 전용
  - correctness / security / docs drift 점검에 사용

## 표준 루트 명령

아래 명령은 저장소가 갖춰야 할 표준 루트 인터페이스다.  
없으면 부트스트랩 단계에서 추가한다.

| 명령 | 목적 |
|---|---|
| `make setup` | 로컬 개발 의존성 설치 및 환경 초기화 |
| `make fmt` | 코드 포맷팅 |
| `make lint` | 정적 분석 및 lint |
| `make test` | 도커 테스트 러너에서 파이썬 테스트 실행 |
| `make check` | `fmt + lint + dockerized test` 또는 동등한 게이트 |
| `make run-api` | API/BFF 로컬 실행 |
| `make run-web` | 포털 로컬 실행 |
| `make run-mcp` | MSSQL Metadata MCP 서버 로컬 실행 |
| `make eval` | eval/fixture/rubric 실행 |
| `make test-build` | 도커 테스트 러너 이미지 준비 |
| `make test-web-smoke` | 도커 컨테이너에서 web build smoke 실행 |

## 권장 로컬 도구

### 공통 CLI
- `git`
- `rg`
- `fd`
- `jq`
- `sed`, `awk`
- `make`

### Python 계열
- Python 3.14 runtime. macOS/Linux commonly expose it as `python3.14`; Windows may use `.env` `PYTHON=python`.
- `uv` 또는 `pip`
- `pytest`
- `ruff`
- `mypy`

### Web 계열
- `node`
- `pnpm`
- `eslint`
- `vitest`

### DB / 인프라
- `docker compose`
- `sqlcmd` 또는 동등한 MSSQL CLI

## MCP 서버 기준

### 필수 MCP
- `mssqlMetadata`
  - 목적: MSSQL 메타데이터 조회
  - 범위: procedure/table/column/index/constraint/function/view/extended property
  - 제약: 읽기 전용, 자유 SQL 금지, 실제 데이터 접근 금지

### 선택 MCP
- `openaiDeveloperDocs`
  - 목적: OpenAI/Codex 관련 공식 문서 확인
  - 사용 시점: Codex config, skills, AGENTS, MCP, subagents 관련 규칙 확인
- `context7`
  - 목적: 최신 프레임워크/라이브러리 문서 확인
  - 사용 시점: FastAPI, Next.js, Pydantic, Playwright 등 외부 라이브러리 최신 문맥이 필요한 구현
- `playwright`
  - 목적: 로컬/승인된 dev URL 에 대한 비파괴적 UI smoke 검증
  - 사용 시점: request/job/artifact 화면 확인, build 이후 기본 동작 검증

## 환경 파일 규칙

- `.env.example` 를 항상 유지한다.
- `.env.example` 은 비밀값 없는 샘플이며 password/token 값은 비워 둔다.
- 실제 비밀 값은 gitignore 된 `.env`, `.env.local` 또는 OS keychain 에 둔다.
- 비밀 값은 테스트 fixture, snapshot, log, docs 에 넣지 않는다.
- MCP/DB 연결 문자열은 로컬 개발용 프로필과 분리한다.
- 기본 metadata profile id 는 `master`, platform profile id 는 `plf`, pilot analysis target profile id 는 `ppm` 이며, profile registry 는 `config/mssql/local_docker_profiles.yaml` 을 기준으로 한다.
- 기본 metadata profile id 는 `master` 이며, profile registry 는 `config/mssql/local_docker_profiles.yaml` 을 기준으로 한다.
- 현재 local registry 의 `master` profile 은 metadata source 의 `master` database 를, `plf` profile 은 platform DB `PLF` 를, `ppm` profile 은 pilot analysis target DB `PPM` 을 가리킨다. PPM 이 없거나 접근 불가하면 PLF로 임의 대체하지 않는다.
- P21 no-mock portal 은 `PORTAL_API_MODE=http` 와 `PORTAL_API_BASE_URL` 을 요구한다. `P21_LIVE_PORTAL_GATE=1` 은 PLF workflow repository 와 read-only PPM metadata access 가 모두 준비된 경우에만 사용한다.
- P22 OpenAI LLM runtime 은 기본값에서 remote 호출을 하지 않는다. `LLM_ENABLE_REMOTE=1`,
  `LLM_ALLOW_SP_TEXT=1`, `OPENAI_API_KEY` 가 모두 준비된 경우에만 SP definition 을 OpenAI
  Responses API 입력으로 보낼 수 있다.

### OpenAI / LLM runtime

- 기본 semantic analysis model: `OPENAI_MODEL_ANALYSIS=gpt-5.5`
- fast/test model: 기본 `gpt-5-nano`; optional live confidence testing 에서는 `OPENAI_MODEL_FAST_TEST` 로 `openai_fast_test` profile 의 모델을 override 할 수 있음
- 기본 adapter: `FakeModelGateway`
- remote adapter: `OpenAIModelGateway`
- 구현 package: `packages/agent-runtime/src/ai_agent_runtime`
- transport: 기존 `httpx` dependency 로 Responses API `/v1/responses` 를 호출한다.
- SDK 의존성 `openai` 는 아직 추가하지 않았다. 새 dependency/lock 갱신은 별도 승인 대상이다.

## 로그와 추적

- 모든 장시간 작업은 `request_id`, `job_id`, `artifact_id` 를 로그 문맥에 포함한다.
- validation / approval / publish 이벤트는 감사 로그 대상이다.
- 생성 결과에는 `snapshot_id`, `registry_version_refs`, `generator_version` 을 남긴다.
- LLM trace 에는 raw prompt, raw SP definition, raw provider response text 를 남기지 않는다.
- LLM trace summary 는 hash/token/latency/status 중심으로 노출한다.

## 명령 사용 규칙

- 먼저 가장 좁은 검증을 돌린다.
- 실패한 명령은 원인 분석 없이 반복 실행하지 않는다.
- 외부 네트워크가 필요한 설치나 문서 조회는 목적을 분명히 하고 최소화한다.
- 저장소 바깥을 쓰는 명령, 파괴적 git 명령, 공유 DB를 건드리는 명령은 기본 금지다.
- Windows PowerShell 에서는 WinGet Links shim 의 `make.exe`/`pnpm.exe` 를 직접 실행하지 않는다. `scripts/win_git_bash.ps1` 를 통해 Git Bash 를 열고 WinGet 실제 package 경로를 PATH 앞에 붙인 뒤 표준 명령을 실행한다.

### Windows Git Bash Helper

Windows 에서 Makefile 의 POSIX shell 구문을 안정적으로 실행하려면 아래 helper 를 사용한다.

```powershell
powershell -ExecutionPolicy Bypass -File scripts/win_git_bash.ps1 make test PYTEST_ARGS="tests/contract/test_p24_sp_migration_guide_contract_prompt_assets.py"
```

이 helper 는 `C:\Program Files\Git\bin\bash.exe` 를 우선 사용하고, `%LOCALAPPDATA%\Microsoft\WinGet\Packages` 아래의 `ezwinports.make` 와 `pnpm.pnpm` 실제 설치 경로를 Git Bash `PATH` 앞에 추가한다.

## 권장 초기 기술 스택

초기 구현 기준으로 아래 조합을 권장한다.  
팀이 다른 스택을 확정하면 이 문서를 먼저 갱신한다.

- `apps/web`: Next.js + TypeScript
- `apps/api`: Python + FastAPI
- `services/mssql-mcp`: Python
- `packages/*`: Python packages 중심
- `Platform DB`: SQL Server
- `Object Storage`: 로컬 파일시스템 시작, 이후 S3 호환 스토리지 확장 가능

## 외부 DB / 스키마 운영

- 플랫폼 DB 와 메타데이터 소스 DB 는 외부 인프라에서 관리한다.
- 저장소는 DB up/down 명령이나 local DB lifecycle 을 제공하지 않는다.
- 스키마 변경이 필요하면 `db/schema/` 아래에 버전 업 SQL 파일을 추가하고, 실제 적용은 사용자가 수동으로 수행한다.
- `sqlcmd` 또는 동등한 CLI 는 필요하면 수동 운영 절차에서만 사용한다.

## Docker 기반 테스트 실행

- `docker/test/docker-compose.yml` 이 기본 테스트 러너 정의를 가진다.
- `make test` 는 Python 3.14 컨테이너 안에서 파이썬 테스트를 실행한다.
- `make test-web-smoke` 는 현재 web 자동 테스트 공백을 보완하는 컨테이너 기반 build smoke 다.
- `make test PYTEST_ARGS="tests/e2e tests/eval"` 은 fixture-first request → job → artifact → validation → approval recording happy path 와 eval fixture 정합성을 검증한다.
- `LLM_LIVE_GATE=1 LLM_ENABLE_REMOTE=1 LLM_ALLOW_SP_TEXT=1 make test PYTEST_ARGS="tests/eval/test_p22_openai_live_agent_gate.py"` 는 선택적 OpenAI live gate 다. 기본 테스트는 fake gateway 로 수행한다.
- `make test PYTEST_ARGS="tests/eval/test_p23_llm_sp_analysis_quality.py tests/unit/agent_runtime tests/contract/test_p23_llm_eval_contract_prompt_assets.py"` 는 P23C fixture-first LLM quality scoring runner 를 검증한다. 기본 실행은 `FakeModelGateway`, `openai_fast_test`, 기본 `gpt-5-nano` 로 수행하며 네트워크를 사용하지 않는다. optional live confidence 에서는 `OPENAI_MODEL_FAST_TEST` 로 모델을 바꿀 수 있다.
- `LLM_LIVE_GATE=1 LLM_ENABLE_REMOTE=1 LLM_ALLOW_SP_TEXT=1 make test PYTEST_ARGS="tests/eval/test_p23_openai_quality_live_gate.py"` 는 선택적 P23 OpenAI quality confidence gate 다. 실패는 production readiness blocker 로 해석하지 않으며 `production_ready: false` 를 유지한다.
- `make test PYTEST_ARGS="tests/eval/test_p24_sp_migration_guide_quality.py tests/contract/test_p24_sp_migration_guide_contract_prompt_assets.py"` 는 P24 fixture-first SP migration guide renderer/evaluator gate 를 검증한다. 기존 `SP_ANALYSIS_DOC` / `DEPENDENCY_REPORT` artifact type 을 재사용하고, `openai_fast_test` / 기본 `gpt-5-nano` 기준을 유지하며 live OpenAI 또는 live PPM 접근을 기본 필수로 만들지 않는다.
- `scripts/install_web_workspace.sh` 는 docker/test 에서 `/pnpm/store` volume 을 pnpm store 로 사용해 worktree 안에 `.pnpm-store` 를 만들지 않는다.
- 새 테스트 스위트를 추가할 때는 가능하면 도커 실행 경로를 함께 제공한다.
- 외부 DB 연결이 필요한 경우 환경변수로 주입하되, 테스트 명령이 DB lifecycle 을 대신 관리하지는 않는다.
