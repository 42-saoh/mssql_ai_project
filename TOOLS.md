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
  - P27 fixture-first tools: `get_dependency_closure`, `resolve_dependency_reference`
    는 active/read-only MCP tool 이며 fixture/live repository handler 를 가진다. P28 기준
    `/api/v1/metadata/tools/{toolName}/invoke` 는 이 두 tool 만 public allowlist 로 호출한다.
    P29 기준 `/metadata/dependencies` Web diagnostic UI 와 workflow `get_dependency_closure`
    evidence wiring 이 이 route 를 사용한다. `resolve_dependency_reference` 는 workflow 에서
    자동 호출하지 않는다. `P27_HARD_LIVE_GATE=1` 은 명시적 PPM dependency evidence hard-live
    gate 이며 기본 테스트에는 포함하지 않는다
  - AI tool orchestration 은 public invocation route 를 넓히지 않는다. Workflow 내부 bounded
    planner 만 active/read-only catalog 전체를 후보로 보고, deterministic policy gate 통과 후
    내부 registry 로 실행한다.
  - `POST /api/v1/metadata/analyze` 도 같은 bounded planner 경계를 사용한다. 기존
    `GET /api/v1/metadata/search` 는 deterministic search 로 유지하고, analyze API 응답에만
    sanitized `aiToolEvidence`, `deterministicFacts`, object profiles, category insight groups,
    dependency graph, DTO readiness, metadata insights, review markers 를 반환한다.

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
- `MSSQL_METADATA_TDS_VERSION` 기본값은 `7.4` 이다. Chakra/legacy gateway 가 기본 TDS negotiation 을 거부하는 로컬 경로에서는 host-run MCP 에 한해 `MSSQL_METADATA_TDS_VERSION=7.0` 으로 낮춰 연결을 검증할 수 있다.
- `.env` 의 `MSSQL_METADATA_DEFAULT_PROFILE_ID=ppm` 은 registry 파일의 정적 default 보다 우선한다. `/health/ready` 로 PPM readiness 를 직접 보고 싶을 때 이 값을 사용한다.
- P21 no-mock portal 은 `PORTAL_API_MODE=http` 와 `PORTAL_API_BASE_URL` 을 요구한다. `P21_LIVE_PORTAL_GATE=1` 은 PLF workflow repository 와 read-only PPM metadata access 가 모두 준비된 경우에만 사용한다.
- P26+ 기준 API/Web 기본 분석 옵션은 high-quality hybrid semantic analysis 와 bounded AI tool
  orchestration
  (`useLlmAnalysis=true`, `useAiToolOrchestration=true`, `allowSpDefinitionToModel=true`, `llmProfileId=openai_sp_semantic_analysis`)
  이다. 그래도 기본 test/fixture 실행은 remote 호출을 하지 않는다. `LLM_ENABLE_REMOTE=1`,
  `LLM_ALLOW_SP_TEXT=1`, `OPENAI_API_KEY` 가 모두 준비된 경우에만 SP definition 을 OpenAI
  Responses API 입력으로 보낼 수 있다.
- Knowledge assetization 은 기본 `KNOWLEDGE_ASSETIZATION_ENABLED=1` 이며, SP workflow 와
  metadata analyze 의 `persistKnowledge=true` 기본값으로 sanitized versioned knowledge asset 을
  축적한다. rollout 중 꺼야 하면 env 를 `0` 으로 두고 skip marker 를 확인한다.

### OpenAI / LLM runtime

- remote provider: `LLM_REMOTE_PROVIDER=openai` (default) keeps the official OpenAI Responses request shape. `LLM_REMOTE_PROVIDER=pgpt` uses the private P-GPT Responses-compatible contract.
- P-GPT endpoint: set `OPENAI_BASE_URL=http://<host>/gpgpta01-gpt` to call `/v1/responses`, or set `OPENAI_RESPONSES_URL` to an exact endpoint override.
- P-GPT models: `PGPT_MODEL_ANALYSIS=gpt-4o`, `PGPT_MODEL_FAST_TEST=gpt-4o-mini`. These defaults are used only when `LLM_REMOTE_PROVIDER=pgpt`.

- 기본 semantic analysis model: `OPENAI_MODEL_ANALYSIS=gpt-5.5`
- fast/test model: 기본 `gpt-5-nano`; manual fast/test 실행에서는 `OPENAI_MODEL_FAST_TEST` 로 `openai_fast_test` profile 의 모델을 override 할 수 있음
- SP task fan-out concurrency: 기본 `LLM_SP_CONCURRENCY=2`
- 기본 adapter: `FakeModelGateway`
- remote adapter: `OpenAIModelGateway`
- provider payloads: official OpenAI sends `text.format.json_schema` and optional `reasoning`; P-GPT sends the minimal Postman-verified `model`, `instructions`, and message-array `input` body without `stream`, `max_output_tokens`, `text.format`, or `reasoning`.
- 구현 package: `packages/agent-runtime/src/ai_agent_runtime`
- transport: 기존 `httpx` dependency 로 Responses API `/v1/responses` 를 호출한다.
- SDK 의존성 `openai` 는 아직 추가하지 않았다. 새 dependency/lock 갱신은 별도 승인 대상이다.

## 로그와 추적

- 모든 장시간 작업은 `request_id`, `job_id`, `artifact_id` 를 로그 문맥에 포함한다.
- validation / approval / publish 이벤트는 감사 로그 대상이다.
- 생성 결과에는 `snapshot_id`, `registry_version_refs`, `generator_version` 을 남긴다.
- LLM trace 에는 raw prompt, raw SP definition, raw provider response text 를 남기지 않는다.
- LLM trace summary 는 hash/token/latency/status 중심으로 노출한다. AI tool orchestration
  component summary 는 stage, toolName, sanitized argument hash, output hash, status, latency,
  evidence count, error code 만 저장한다.

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
- `make test PYTEST_ARGS="tests/e2e tests/eval"` 은 fixture-first request → job → artifact → validation complete happy path 와 eval fixture 정합성을 검증한다.
- `LLM_LIVE_GATE=1 LLM_ENABLE_REMOTE=1 LLM_ALLOW_SP_TEXT=1 make test PYTEST_ARGS="tests/eval/test_p22_openai_live_agent_gate.py"` 는 선택적 OpenAI live gate 다. 기본 테스트는 fake gateway 로 수행한다.
- `make test PYTEST_ARGS="tests/eval/test_p23_llm_sp_analysis_quality.py tests/unit/agent_runtime tests/contract/test_p23_llm_eval_contract_prompt_assets.py"` 는 P23/P26 fixture-first LLM quality scoring runner 를 검증한다. 기본 실행은 `FakeModelGateway` 로 수행하며 네트워크를 사용하지 않는다. API/Web live 기본 profile 은 `openai_sp_semantic_analysis` / `gpt-5.5` 이고, optional high-quality live confidence 에서는 `OPENAI_MODEL_ANALYSIS` 로 모델을 바꿀 수 있다. `openai_fast_test` 는 `OPENAI_MODEL_FAST_TEST` 로 바꿀 수 있는 수동 fast/test 선택지다.
- `LLM_LIVE_GATE=1 LLM_ENABLE_REMOTE=1 LLM_ALLOW_SP_TEXT=1 make test PYTEST_ARGS="tests/eval/test_p23_openai_quality_live_gate.py"` 는 선택적 P23/P26 OpenAI high-quality semantic confidence gate 다. 기본 profile 은 `openai_sp_semantic_analysis` / `OPENAI_MODEL_ANALYSIS` 이며, 실패는 production readiness blocker 로 해석하지 않고 `production_ready: false` 를 유지한다.
- `make test PYTEST_ARGS="tests/eval/test_p24_sp_migration_guide_quality.py tests/contract/test_p24_sp_migration_guide_contract_prompt_assets.py"` 는 P24 fixture-first SP migration guide renderer/evaluator gate 를 검증한다. 기존 `SP_ANALYSIS_DOC` / `DEPENDENCY_REPORT` artifact type 을 재사용하고, `openai_fast_test` / 기본 `gpt-5-nano` 기준을 유지하며 live OpenAI 또는 live PPM 접근을 기본 필수로 만들지 않는다.
- `make test PYTEST_ARGS="tests/unit/test_mcp_catalog.py tests/unit/mcp/test_tool_registry.py tests/contract/mcp/test_tool_invocation_contract.py tests/contract/test_p27_dependency_evidence_tooling_prompt_assets.py tests/unit/api/test_metadata_service.py tests/unit/api/test_metadata_gateway.py tests/unit/api/test_ai_tool_orchestrator.py tests/unit/api/test_workflow_service.py tests/unit/api/test_route_surface.py tests/unit/web/test_p14_product_ui_static.py tests/integration/api/test_api_workflow_routes.py tests/e2e/test_fixture_workflow_happy_path.py tests/contract/test_openapi_and_env_sample_assets.py"` 는 P27/P28/P29/P29B dependency evidence tooling fixture-first 구현, catalog 계약, prompt/manifest 자산, API tool summary/safe invocation route, Web diagnostic UI, workflow closure evidence wiring, bounded AI tool orchestration, deferred storage/workflow boundary 를 검증한다. 새 dependency closure/resolver tool 과 AI-selected metadata tool execution 은 active/read-only/structured-input MCP tool 경계를 사용하며, raw SQL, row data, procedure execution, DDL/DML, raw definition storage, PPM-to-PLF fallback 을 허용하지 않는다. P29B 는 DB migration, persisted artifact type, workflow state transition 을 추가하지 않고 기존 sanitized `dependencyEvidence` digest 와 draft artifact evidence refs 를 유지한다.
- `make test PYTEST_ARGS="tests/unit/api/test_metadata_analysis_service.py tests/eval/test_p30_metadata_ai_mcp_analysis.py tests/integration/api/test_api_workflow_routes.py tests/contract/test_openapi_and_env_sample_assets.py tests/unit/web/test_p14_product_ui_static.py"` 는 metadata analyze API 응답 표면, bounded internal MCP execution, sanitized fact ids, adversarial planner blocking, Web analyze action 을 검증한다. P34 이후 기본 실행은 별도 knowledge asset 저장도 수행한다.
- `make test PYTEST_ARGS="tests/unit/api/test_metadata_analysis_service.py tests/eval/test_p30_metadata_ai_mcp_analysis.py tests/eval/test_p31_metadata_object_insight_depth.py tests/eval/test_p32_live_confidence_planner_effectiveness.py tests/integration/api/test_api_workflow_routes.py tests/contract/test_openapi_and_env_sample_assets.py tests/unit/web/test_p14_product_ui_static.py"` 는 metadata object depth 와 planner effectiveness fixture-first gate 를 함께 검증한다. `aiToolEvidence.plannerMetrics` 는 sanitized counts/ratios 만 포함하며 live confidence 는 기본 실행에서 `NOT_RUN_CONFIDENCE_ONLY` 로 남는다.
- `P32_LIVE_CONFIDENCE_GATE=1 LLM_LIVE_GATE=1 LLM_ENABLE_REMOTE=1 MSSQL_ENABLE_LIVE_METADATA=1 make test PYTEST_ARGS="tests/eval/test_p32_live_confidence_planner_effectiveness.py"` 는 선택적 P32 live confidence gate 다. `OPENAI_API_KEY` 와 read-only PPM metadata profile 이 필요하며, 실패는 production readiness blocker 가 아니라 confidence evidence 부족으로 해석한다.
- `make test PYTEST_ARGS="tests/unit/api/test_metadata_tool_cache.py tests/unit/api/test_workflow_service.py tests/unit/api/test_metadata_analysis_service.py tests/unit/api/test_batch_sp_analysis.py tests/integration/api/test_api_workflow_routes.py tests/eval/test_p33_performance_scale.py tests/contract/test_openapi_and_env_sample_assets.py tests/unit/web/test_p14_product_ui_static.py"` 는 P33 performance/scale fixture-first gate 다. Metadata MCP tool result cache, stable `contentHash`/fact id, planner cache hit/miss metrics, bounded SP batch endpoint, live PPM round reduction, workflow/MCP backpressure error codes, no raw leakage 를 검증한다.
- `make test PYTEST_ARGS="tests/unit/api/test_knowledge_asset_service.py tests/unit/api/test_workflow_service.py tests/unit/api/test_metadata_analysis_service.py tests/integration/api/test_api_workflow_routes.py tests/contract/test_openapi_and_env_sample_assets.py tests/eval/test_p34_knowledge_assetization.py tests/unit/web/test_p14_product_ui_static.py"` 는 P34 knowledge assetization fixture-first gate 다. v5 DDL contract, version reuse, fact graph/export, SP/metadata knowledge assets, no raw leakage 를 검증한다.
- `P27_HARD_LIVE_GATE=1 MSSQL_ENABLE_LIVE_METADATA=1 make test PYTEST_ARGS="tests/eval/test_p27_dependency_evidence_hard_live_gate.py"` 는 명시적 P27 hard-live gate 다. `selected_objects.yaml` 의 PPM simple/medium/complex procedure 를 대상으로 closure/resolver evidence 를 검증하며, gate 가 켜진 뒤 PPM profile/env 누락 또는 접근 실패는 skip 이 아니라 blocker failure 다.
- `scripts/install_web_workspace.sh` 는 docker/test 에서 `/pnpm/store` volume 을 pnpm store 로 사용해 worktree 안에 `.pnpm-store` 를 만들지 않는다.
- 새 테스트 스위트를 추가할 때는 가능하면 도커 실행 경로를 함께 제공한다.
- 외부 DB 연결이 필요한 경우 환경변수로 주입하되, 테스트 명령이 DB lifecycle 을 대신 관리하지는 않는다.
