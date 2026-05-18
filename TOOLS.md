# TOOLS.md

## P36 Verification Notes

P36 uses the normal dockerized test interface when available. The key targeted suites are:

- `tests/contract/test_p36_output_renewal_contract_prompt_assets.py`
- `tests/eval/test_p36_output_renewal_quality.py`
- `tests/unit/generation`
- `tests/contract/test_openapi_and_env_sample_assets.py`
- `tests/unit/api/test_workflow_service.py`
- `tests/integration/api/test_api_workflow_routes.py`
- `tests/unit/web/test_p14_product_ui_static.py`

The v9 DB SQL is manual-review/manual-apply only. It is non-destructive for existing
FK-linked retired artifact rows and blocks only new retired artifact inserts/type changes.
Tooling must not apply it automatically.

## P41 Verification Notes

P41 validates the SP operation model renewal with fixture-first tests plus workflow
wiring tests for `JAVA_MYBATIS_DRAFT`. The baseline P41A contract/fixture gate is:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/win_git_bash.ps1 make test PYTEST_ARGS="tests/contract/test_p41_sp_operation_model_prompt_assets.py tests/eval/test_p41_sp_operation_model.py"
```

The full P41A-F targeted quality gate adds the schema, deterministic extractor,
structured planner, workflow `operationModel` injection, multi-DTO artifact storage,
multi-DTO Java/MyBatis renderer, and P36 generation regression:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/win_git_bash.ps1 make test PYTEST_ARGS="tests/unit/api/test_workflow_service.py tests/integration/api/test_api_workflow_routes.py tests/unit/generation tests/eval/test_p36_output_renewal_quality.py tests/eval/test_p41_sp_operation_model.py tests/unit/agent_runtime/test_sp_operation_planner.py tests/unit/analysis/test_sp_statement_evidence_extractor.py tests/unit/agent_runtime/test_sp_operation_model_schema.py tests/contract/test_p41_sp_operation_model_prompt_assets.py"
```

The fixture uses sanitized expectations from the external `MIGRATION_GUIDE.md` reference
for `PCO_GU_ManageBond_PRC`; it does not store raw SP text and does not require live DB,
row-data access, procedure execution, OpenAI network calls, public API expansion, DB schema
changes, or a new public MCP invoke tool. `DTO_DRAFT` may be a multi-file bundle only inside
the unchanged `JAVA_MYBATIS_DRAFT` artifact contract. Workflow tests verify that a new
manage-bond job stores DTO bundle files individually and preserves a review-required fallback
operation model when planning is disabled or unavailable.

## P42 Verification Notes

P42 validates the AI Draft Pack path with fixture-first contract tests, static quality gates,
workflow wiring tests, and a route-level ManageBond replay. The P42A groundwork gate is:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/win_git_bash.ps1 make test PYTEST_ARGS="tests/contract/test_p42_ai_draft_pack_prompt_assets.py tests/eval/test_p42_manage_bond_ai_draft_quality.py"
```

P42B-E implement schema/gateway, deterministic code-draft validation, workflow artifact
persistence, and ManageBond replay. P42F synchronizes docs and runs the final targeted gate,
including P41 and P36 regression:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/win_git_bash.ps1 make test PYTEST_ARGS="tests/contract/test_p42_ai_draft_pack_prompt_assets.py tests/eval/test_p42_manage_bond_ai_draft_quality.py tests/unit/agent_runtime/test_ai_draft_pack_schema.py tests/unit/agent_runtime/test_ai_draft_pack_planner.py tests/unit/validation/test_ai_draft_pack_validator.py tests/unit/api/test_workflow_service.py tests/integration/api/test_api_workflow_routes.py tests/contract/test_p41_sp_operation_model_prompt_assets.py tests/eval/test_p41_sp_operation_model.py tests/unit/agent_runtime/test_sp_operation_model_schema.py tests/unit/agent_runtime/test_sp_operation_planner.py tests/unit/analysis/test_sp_statement_evidence_extractor.py tests/unit/generation tests/eval/test_p36_output_renewal_quality.py"
```

The P42 fixture uses sanitized expectations from the external `MIGRATION_GUIDE.md` reference
for `PCO_GU_ManageBond_PRC`; it does not store raw guide body, raw SP text, row data, raw
prompts, or provider responses and does not require live DB, procedure execution, OpenAI network
calls, public API expansion, DB schema changes, or a new public MCP invoke tool. The P42E replay
uses `FakeModelGateway` and `tests/helpers/p42_manage_bond.py`, and acceptance requires non-empty
multi-DTO artifacts plus preserved `REVIEW_REQUIRED` uncertainty markers.

P42H keeps that ManageBond fixture as a benchmark only. Runtime workflow inventory is derived
from sanitized operation contracts and DTO blueprints. Collapsed complex-SP inventories or missing
write/call DTO responsibilities fail as `P42_INVENTORY_CONTRACT_INCOMPLETE` before any Java/MyBatis
draft artifacts are persisted.

P42G is an optional live confidence replay for the residual P42E risk. It is not part of the
default fixture gate and must be enabled explicitly:

```powershell
$env:P42_LIVE_REPLAY_GATE="1"
$env:LLM_LIVE_GATE="1"
$env:LLM_ENABLE_REMOTE="1"
$env:LLM_ALLOW_SP_TEXT="1"
$env:MSSQL_ENABLE_LIVE_METADATA="1"
$env:MSSQL_METADATA_CONNECT_TIMEOUT_SECONDS="20"
powershell -ExecutionPolicy Bypass -File scripts/win_git_bash.ps1 make test PYTEST_ARGS="tests/eval/test_p42_live_ai_draft_pack_replay_gate.py"
```

The probe uses an in-memory repository, live read-only `ppm` metadata, and the existing
OpenAI-compatible Responses/httpx gateway. It does not execute the stored procedure, query row
data, write platform DB rows, apply generated source, or claim production readiness.

## P43 Framework Adoption Verification Notes

P43 evaluates whether a new agent/orchestration framework should be adopted. It
does not install a framework in P43A and does not switch runtime behavior. The
static groundwork gate is:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/win_git_bash.ps1 make test PYTEST_ARGS="tests/contract/test_p43_framework_adoption_prompt_assets.py"
```

The final P43 decision gate records a `pilot` recommendation. It compares the
current Responses/httpx baseline against fake candidate adapters, preserves
P42/P41/P36 regressions, and keeps `production_ready: false`:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/win_git_bash.ps1 make test PYTEST_ARGS="tests/eval/test_p43_framework_adapter_replay.py tests/unit/agent_runtime/test_framework_adapter.py tests/unit/api/test_workflow_service.py tests/unit/validation/test_ai_draft_pack_validator.py tests/contract/test_p43_framework_adoption_prompt_assets.py tests/eval/test_p42_manage_bond_ai_draft_quality.py tests/eval/test_p41_sp_operation_model.py tests/eval/test_p36_output_renewal_quality.py"
```

Candidate framework testing must use sanitized fixtures and fake adapters by
default. Optional live replay remains a separate confidence signal and must not
execute stored procedures, query row data, store raw prompts/provider responses,
or apply generated source.

P43D framework policy checks are part of the static gate. Candidate adapters must
pass `P43_FRAMEWORK_TOOL_CONTEXT_BLOCKED` checks before stage execution and
`P43_FRAMEWORK_RAW_TRACE_BLOCKED` checks before storing trace summaries. Stored
framework trace components are limited to adapter ids, candidate framework,
stage/status, component ids, counts, hashes, blocker/failure codes, and numeric
policy-safe metrics. OpenAI Agents SDK tracing must be disabled or configured to
exclude sensitive inputs/outputs before adoption; LangGraph persistence must use
a redacted serializer/checkpointer boundary before adoption.

The P43F decision report is `docs/framework-adoption-decision-p43.md`. Its
rollback path is the current Responses/httpx gateway plus
`BaselineResponsesFrameworkAdapter`; it does not authorize framework dependency
installation or a production runtime switch.

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
| `make test` | 도커 테스트 러너에서 선택한 `PYTEST_ARGS` 실행 |
| `make test-core` | fixture-only unit/contract/integration/e2e baseline |
| `make test-quality` | fixture-only eval/quality gate |
| `make test-web` | Web static/http smoke + build smoke |
| `make test-live-confidence` | 명시적 live DB/LLM/Auth confidence suite |
| `make check` | `fmt + lint + test-core + test-quality` |
| `make run-api` | API/BFF 로컬 실행 |
| `make run-web` | 포털 로컬 실행 |
| `make run-mcp` | MSSQL Metadata MCP 서버 로컬 실행 |
| `make eval` | `make test-quality` alias |
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
    Same-server cross-database dependency catalog checks run only from the PPM profile context.
    There is no PLF fallback. External catalog timeout/permission/connect/query failures are
    retryable tool failures, not hangs or partial deterministic dependency evidence.
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

## Platform internal AI tools

- catalog: `spec/agent-tools/platform_ai_tool_catalog.yaml`
- 목적: LLM semantic analysis 전에 플랫폼 내부 read-only context 를 보강한다.
- v1 active tools:
  - `platform.search_knowledge_facts`
  - `platform.list_knowledge_assets`
  - `platform.get_knowledge_version_graph`
  - `platform.list_job_artifacts`
  - `platform.get_latest_validation_report`
  - `platform.list_job_agent_runs`
  - `platform.list_registry_versions`
- 제약: 내부 workflow 전용이며 public invoke API 를 만들지 않는다. current job/db profile/target
  scope 를 벗어나지 않고, artifact full content, raw SQL/SP definition, row data, procedure
  execution, DDL/DML, approval/review write, export creation, secrets, raw prompt/provider response 를
  요청하거나 저장하지 않는다.

## 환경 파일 규칙

- `.env.example` 를 항상 유지한다.
- `.env.example` 은 비밀값 없는 공통 샘플이며 password/token 값은 비워 둔다.
- 환경별 시작점은 `config/env/mac-docker-openai.env.example` 과
  `config/env/windows-sandbox-pgpt.env.example` 로 분리한다.
- Windows sandbox + P-GPT 환경은 platform persistence 용 `PLATFORM_DB_*` 와 PPM metadata
  discovery 용 `MSSQL_METADATA_*` 가 서로 다른 SQL Server host 를 가리킬 수 있다.
- 실제 비밀 값은 gitignore 된 `.env`, `.env.local` 또는 OS keychain 에 둔다.
- 비밀 값은 테스트 fixture, snapshot, log, docs 에 넣지 않는다.
- MCP/DB 연결 문자열은 로컬 개발용 프로필과 분리한다.
- 기본 metadata profile id 는 `master`, platform profile id 는 `plf`, pilot analysis target profile id 는 `ppm` 이며, profile registry 는 `config/mssql/local_docker_profiles.yaml` 을 기준으로 한다.
- 현재 local registry 의 `master` profile 은 metadata source 의 `master` database 를, `plf` profile 은 platform DB `PLF` 를, `ppm` profile 은 pilot analysis target DB `PPM` 을 가리킨다. PPM 이 없거나 접근 불가하면 PLF로 임의 대체하지 않는다.
- `MSSQL_METADATA_TDS_VERSION` 기본값은 `7.4` 이다. Chakra/legacy gateway 가 기본 TDS negotiation 을 거부하는 로컬 경로에서는 host-run MCP 에 한해 `MSSQL_METADATA_TDS_VERSION=7.0` 으로 낮춰 연결을 검증할 수 있다.
- `.env` 의 `MSSQL_METADATA_DEFAULT_PROFILE_ID=ppm` 은 registry 파일의 정적 default 보다 우선한다. `/health/ready` 로 PPM readiness 를 직접 보고 싶을 때 이 값을 사용한다.
- P21 no-mock portal 은 `PORTAL_API_MODE=http` 와 `PORTAL_API_BASE_URL` 을 요구한다. `P21_LIVE_PORTAL_GATE=1` 은 PLF workflow repository 와 read-only PPM metadata access 가 모두 준비된 경우에만 사용한다.
- P26+ 기준 API/Web 기본 분석 옵션은 high-quality hybrid semantic analysis, bounded AI MCP tool
  orchestration, bounded platform context tool orchestration
  (`useLlmAnalysis=true`, `useAiToolOrchestration=true`,
  `usePlatformToolOrchestration=true`, `allowSpDefinitionToModel=true`,
  `llmProfileId=openai_sp_semantic_analysis`)
  이다. 그래도 기본 test/fixture 실행은 remote 호출을 하지 않는다. `LLM_ENABLE_REMOTE=1`,
  `LLM_ALLOW_SP_TEXT=1`, `OPENAI_API_KEY` 가 모두 준비된 경우에만 SP definition 을 OpenAI
  Responses API 입력으로 보낼 수 있다.
- Knowledge assetization 은 기본 `KNOWLEDGE_ASSETIZATION_ENABLED=1` 이며, SP workflow 와
  metadata analyze 의 `persistKnowledge=true` 기본값으로 sanitized versioned knowledge asset 을
  축적한다. rollout 중 꺼야 하면 env 를 `0` 으로 두고 skip marker 를 확인한다. v6 schema 는
  manual-apply only 이며, 필수 table 누락은 `KNOWLEDGE_SCHEMA_REQUIRED` 로 반환된다.
- Knowledge lifecycle/search uses `db/schema/ai_agent_platform_schema_v6_draft_quality_no_review.sql`.
  Readiness checks require lifecycle/archive columns and critical search indexes in addition to the
  P34 tables. Missing objects return `KNOWLEDGE_SCHEMA_REQUIRED`; Codex/API do not auto-apply DDL.
  `REVIEW_REQUIRED` remains an evidence caveat, not a human review or conversion approval.
- `P35_KNOWLEDGE_LIVE_GATE=1` is an explicit confidence-only live gate for recent P34/P35
  knowledge behavior. It requires live OpenAI, read-only `ppm`/`PPM` metadata, and a manually
  prepared PLF v6 schema. It writes normal PLF workflow/knowledge/export/audit records, but never
  writes review records, reads row data, executes procedures, applies DDL, or treats caveats as
  production approval.
For external PLF/PPM targets that complete TCP open but need a longer TDS handshake, run live
confidence gates with `MSSQL_METADATA_CONNECT_TIMEOUT_SECONDS=20` and
`PLATFORM_DB_CONNECT_TIMEOUT_SECONDS=20`.

## P35 Source Context Runtime

- `sourceContextMode=RETRIEVED_SPANS` is the default SP semantic analysis mode.
  The workflow builds a sanitized `ProcedureSourceMap`, selects bounded source spans for each
  semantic stage, and sends only those transient spans to the model when
  `allowSpDefinitionToModel=true` and `LLM_ALLOW_SP_TEXT=1`.
- `sourceContextMode=NONE` disables raw source span prompt input and leaves the model with
  metadata/static evidence digest only.
- Runtime budget knobs:
  `LLM_SEMANTIC_INPUT_TOKEN_BUDGET=64000`,
  `LLM_SEMANTIC_SOURCE_TOKEN_BUDGET=32000`,
  `LLM_SP_MAX_RETRIEVED_SPANS=24`.
- Confirmed dependency procedure fan-out is controlled by
  `sourceDependencyMode=CONFIRMED_PROCEDURES`, `LLM_SP_DEPENDENCY_DEPTH=2`, and
  `LLM_SP_MAX_DEPENDENCY_TASKS=8`. Same-server cross-database procedures are eligible only when
  dependency closure already confirmed them with catalog-backed `SAME_SERVER_CROSS_DATABASE_CATALOG`
  evidence; their definitions are fetched internally through `get_procedure_definition` with
  `referencedDatabase`. Public MCP/API raw definition access is not expanded.
- Agent run traces may expose sanitized `analysisCoverage` and `sourceContextSummary`, but never
  raw prompt text, selected span text, full SP definitions, row data, or raw provider responses.

### OpenAI / LLM runtime

- remote provider: `LLM_REMOTE_PROVIDER=openai` (default) keeps the official OpenAI Responses request shape. `LLM_REMOTE_PROVIDER=pgpt` uses the private P-GPT Responses-compatible contract.
- P-GPT endpoint: set `OPENAI_BASE_URL=http://<host>/gpgpta01-gpt` to call `/v1/responses`, or set `OPENAI_RESPONSES_URL` to an exact endpoint override.
- P-GPT models: `PGPT_MODEL_ANALYSIS=gpt-4o`, `PGPT_MODEL_FAST_TEST=gpt-4o-mini`. These defaults are used only when `LLM_REMOTE_PROVIDER=pgpt`.
- P-GPT structured-output drift is handled strict-first: semantic output and metadata tool plans are validated before any normalizer runs. The fallback normalizers only remove unsupported fields, normalize safe aliases/status/severity, and record sanitized path/code metadata; raw prompt/provider/SP text is not stored and schemas/OpenAPI stay strict.

- 기본 semantic analysis model: `OPENAI_MODEL_ANALYSIS=gpt-5.5`
- fast/test model: 기본 `gpt-5-nano`; manual fast/test 실행에서는 `OPENAI_MODEL_FAST_TEST` 로 `openai_fast_test` profile 의 모델을 override 할 수 있음
- SP task fan-out concurrency: 기본 `LLM_SP_CONCURRENCY=2`
- Platform context tool call budget: 기본 `PLATFORM_TOOL_MAX_CALLS=3`
- 기본 adapter: `FakeModelGateway`
- remote adapter: `OpenAIModelGateway`
- provider payloads: official OpenAI sends `text.format.json_schema` and optional `reasoning`; P-GPT sends the minimal Postman-verified `model`, `instructions`, and message-array `input` body without `stream`, `max_output_tokens`, `text.format`, or `reasoning`.
- 구현 package: `packages/agent-runtime/src/ai_agent_runtime`
- transport: 기존 `httpx` dependency 로 Responses API `/v1/responses` 를 호출한다.
- SDK 의존성 `openai` 는 아직 추가하지 않았다. 새 dependency/lock 갱신은 별도 승인 대상이다.

## 로그와 추적

- 모든 장시간 작업은 `request_id`, `job_id`, `artifact_id` 를 로그 문맥에 포함한다.
- request / job / validation / knowledge export 이벤트는 감사 로그 대상이다.
- 생성 결과에는 `snapshot_id`, `registry_version_refs`, `generator_version` 을 남긴다.
- LLM trace 에는 raw prompt, raw SP definition, raw provider response text 를 남기지 않는다.
- LLM trace summary 는 hash/token/latency/status 중심으로 노출한다. AI MCP/platform tool orchestration
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

선행 `NAME=value` 인자는 Git Bash 내부에서 환경 변수로 전달된다. 예를 들어
`powershell -ExecutionPolicy Bypass -File scripts/win_git_bash.ps1 P35_KNOWLEDGE_LIVE_GATE=1 make test ...`
형태로 optional live gate 를 켤 수 있다.

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
- `make test` 는 Python 3.14 컨테이너 안에서 `PYTEST_ARGS` 대상만 실행하는 저수준 pytest 진입점이다.
- `make test-core` 는 `@core` suite 를 실행하며 unit/contract/integration/e2e fixture baseline 을 검증한다.
- `make test-quality` 는 `@quality` suite 를 실행하며 eval/quality fixture gate 를 검증한다.
- `make test-web` 는 `@web` suite 와 Web build smoke 를 함께 실행한다.
- `make test-live-confidence` 는 `@live-confidence` suite 를 실행하는 명시적 live confidence 진입점이다. 실행 전 승인된 환경에서 `OPENAI_API_KEY`, PLF `PLATFORM_DB_*`, read-only PPM metadata, 필요한 live gate flag, 수동 적용된 DDL 을 준비해야 한다.
- `make test-core`, `make test-quality`, `make test-web` 는 명령 레벨에서 live/remote flag 를 0 으로 고정해 로컬 `.env` 에 live 값이 있어도 DB/LLM 을 호출하지 않는다.
- `PYTEST_ARGS="@core"` 같은 alias 는 `tests/suites.yaml` 에서 관리한다. Pxx 세부 명령 이력은 `docs/test-gate-history.md` 에 보존한다.
- `scripts/install_web_workspace.sh` 는 docker/test 에서 `/pnpm/store` volume 을 pnpm store 로 사용해 worktree 안에 `.pnpm-store` 를 만들지 않는다.
- 새 테스트 스위트를 추가할 때는 가능하면 `tests/suites.yaml` alias 와 도커 실행 경로를 함께 제공한다.
- 외부 DB 연결이 필요한 경우 환경변수로 주입하되, 테스트 명령이 DB lifecycle 을 대신 관리하지는 않는다.
- `scripts/install_web_workspace.sh` 는 docker/test 에서 `/pnpm/store` volume 을 pnpm store 로 사용해 worktree 안에 `.pnpm-store` 를 만들지 않는다.
- 새 테스트 스위트를 추가할 때는 가능하면 도커 실행 경로를 함께 제공한다.
- 외부 DB 연결이 필요한 경우 환경변수로 주입하되, 테스트 명령이 DB lifecycle 을 대신 관리하지는 않는다.
