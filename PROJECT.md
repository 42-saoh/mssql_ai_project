# PROJECT.md

## P36 Output Renewal Baseline

P36 redefines generated deliverables as six final artifact types:
`SP_ANALYSIS_DOC`, `DEPENDENCY_REPORT`, `DTO_DRAFT`, `SERVICE_DRAFT`,
`MAPPER_INTERFACE`, and `MAPPER_XML`.

`SP_ANALYSIS_DOC` follows the `MIGRATION_GUIDE.md` flow: SP overview, dependency
inventory, DML impact matrix, call flow, complexity analysis, and appendix.
`DEPENDENCY_REPORT` is now an evidence dossier for analysis/code generation evidence,
bounded sanitized SQL statement evidence, caveats, and next evidence to collect.

Retired public outputs are removed from new request/API/UI/generation contracts:
`DTO_MODEL_DRAFT`, `VO_DRAFT`, `MODEL_DRAFT`, and `DDL_DRAFT`. Existing storage rows
with retired artifact types are historical-only and must be preserved rather than
deleted when FK-linked history exists. P36 remains `production_ready: false`; no
row-data query, procedure execution, business DB DDL/DML, automatic DDL apply, or
automatic generated-source deployment is authorized.

## P38 Metadata Design Chat Baseline

P38 adds durable metadata design chat runs for table-design assistance. Users can
submit field names, descriptions, and table hints; the API searches related metadata
through read-only MCP tools and returns a `createTableScriptPreview` plus optional
`DTO_DRAFT` preview inside the design run result.

The table script is a non-executable manual-review preview, not a workflow artifact
and not an automatic migration. P38 does not revive retired public output contracts
and keeps `production_ready: false`: no row-data query, procedure execution, business
DB DDL/DML, automatic DDL apply, source deployment, raw prompt/provider response
storage, or secret storage is authorized.

## P40 Metadata Design Natural-Language Chat Baseline

P40 keeps the P38 durable run API and storage model but changes `/metadata/design`
into a natural-language chat experience. Users can describe a new table or a
follow-up refinement in Korean or English. The API returns sanitized
`interpretedIntent` and `appliedChanges` alongside metadata evidence,
`createTableScriptPreview`, and optional `DTO_DRAFT` preview.

`conversationMode=NEW_DESIGN` starts a new proposal. `REFINE_CURRENT` uses the latest
successful run in the same conversation as the baseline and applies add/remove/type
change instructions; missing or ambiguous baselines remain `REVIEW_REQUIRED`.
`designInputs.fields` remains API-compatible, but the Web UI no longer exposes field
row inputs. P40 adds no new DDL and keeps `production_ready: false`.

## P41 SP Operation Model Renewal Groundwork

P41 renews SP analysis and Java/MyBatis generation for complex stored procedures
such as `PPM.dbo.PCO_GU_ManageBond_PRC`. P41A-F now connect an internal
`SpOperationModel.v0.1` contract, deterministic sanitized statement evidence,
strict structured planning, and Java/MyBatis generation that can keep branch-level
DTO blueprints separate before source drafting.

The SP workflow now builds a sanitized operation-model AgentRun for
`JAVA_MYBATIS_DRAFT`: raw procedure definition text is used only as transient input
to the deterministic statement-evidence extractor, the planner output is validated
as `SpOperationModel.v0.1`, and `GenerationContext.request.operationModel` drives
multi-DTO rendering. If operation-model planning is disabled, unavailable, or fails,
the workflow records `P41_OPERATION_MODEL_REVIEW_REQUIRED` and renders an explicit
`OperationModelReviewRequired` DTO instead of silently falling back to the legacy
single procedure DTO.

The legacy single-DTO Java/MyBatis renderer remains supported when no
`operationModel` is supplied, and that path is still recorded as insufficient for
complex SPs through fixture-first evals. When `operationModel.dtoBlueprints` is
present, `JAVA_MYBATIS_DRAFT` keeps the same public artifact types while
rendering `DTO_DRAFT` as an internal multi-file bundle stored one artifact row per
DTO file path; `SERVICE_DRAFT`, `MAPPER_INTERFACE`, and `MAPPER_XML` remain single
files. P41 remains
`production_ready: false`, with no UI change, public API expansion, DB schema
change, live MCP public tool expansion, row-data access, procedure execution,
automatic DDL/DML apply, or generated-source deployment.

## P42 AI Draft Pack Renewal

P42 starts after the observed `job_6864d2734e` failure mode: Java/MyBatis
artifacts were not byte-empty, but all four were `OperationModelReviewRequired*`
fallback skeletons because operation-model planning failed before useful
ManageBond draft files were created.

P42A defines an internal `AiJavaMyBatisDraftPack.v0.1` contract and
fixture-first quality target for `PPM.dbo.PCO_GU_ManageBond_PRC`. The intended
P42 path lets the LLM draft the Java/MyBatis file bundle directly from
sanitized evidence, then uses deterministic validators and eval gates to block
blank files, single `ManageBondDTO` collapse, `OperationModelReviewRequired*`
fallback artifacts, raw SP/guide storage, and source apply/deploy claims.

Public artifact types remain unchanged: DTO files are still persisted as
`DTO_DRAFT` rows, while `SERVICE_DRAFT`, `MAPPER_INTERFACE`, and `MAPPER_XML`
remain single files. P42B-C added the strict runtime schema and static quality
validator, and P42D wires `JAVA_MYBATIS_DRAFT` to persist only validated AI Draft
Pack files. P42E adds a local API replay gate that submits a new ManageBond job
through the workflow with fake metadata/model gateways and verifies eleven
non-empty DTO artifacts plus one Service, Mapper interface, and Mapper XML.

If pack planning or validation fails, the workflow records
`P42_AI_DRAFT_PACK_FAILED` or `P42_AI_DRAFT_PACK_REVIEW_REQUIRED` and stores no
misleading Java/MyBatis fallback skeletons. Cross-database writes, called
procedure I/O, TVF/procedure kind uncertainty, result-shape variants, and
transaction boundaries remain `REVIEW_REQUIRED`. P42 remains
`production_ready: false`, with no UI change, public API expansion, DB schema
change, row-data access, procedure execution, automatic DDL/DML apply, or
generated-source deployment.

P42G adds an optional live confidence replay for the remaining P42E risk. It is
disabled by default with `P42_LIVE_REPLAY_GATE=0`; when explicitly enabled with
`P42_LIVE_REPLAY_MODE=sanitized_fixture`, it replays sanitized fixture facts
without live PPM metadata or raw SP external export and reruns the same P42 static
AI Draft Pack quality gate. The explicit `live_ppm` mode still exists for live
read-only metadata confidence evidence, but it requires raw-SP-to-remote-model
approval. Passing P42G is confidence evidence only, not production readiness or
automatic conversion approval, and the default fixture-first P42 acceptance
remains unchanged.

P42H removes runtime ManageBond-specific inventory overrides. ManageBond remains
the benchmark fixture, but the workflow now derives `expectedInventory` and
quality gates from sanitized operation contracts, DTO blueprints, statement
evidence, branch responsibilities, and review markers. If a complex operation
model collapses to two DTOs, leaves statements uncovered, or omits command/call
DTO responsibilities, the workflow records `P42_INVENTORY_CONTRACT_INCOMPLETE`
and persists no Java/MyBatis draft artifacts.

## P43 Framework Adoption Readiness

P43 evaluates whether a new agent/orchestration framework should be introduced
to improve general complex-SP analysis and AI Draft Pack quality. The initial
recommendation is adapter-first evaluation, not immediate migration: the current
Responses/httpx gateway remains the baseline, while OpenAI Agents SDK and
LangGraph are candidates only behind an internal framework adapter and policy
gate.

P43A adds `p43_framework_adoption@0.1.0`, a ManageBond benchmark fixture, a
task brief, sequential prompt pack, and static contract tests. P43 must not use
`PCO_GU_ManageBond_PRC` as a production-runtime answer key. ManageBond stays a
quality benchmark for detecting DTO collapse, weak branch/use-case coverage, raw
trace leakage, and fallback skeleton behavior.

P43B-E add the internal `AiGenerationFrameworkAdapter.v0.1` spike, fake baseline
and candidate adapters, sanitized tool/trace policy gates, and a replay gate that
compares the current Responses/httpx baseline with fake OpenAI Agents SDK and
LangGraph candidates. The replay preserves P42 quality on ManageBond and proves a
synthetic complex-SP collapse guard without ManageBond-specific runtime
hardcoding.

P43F historically recorded the framework adoption decision as `pilot`: real
framework work was gated behind the internal adapter and policy gates. P44
supersedes that direction with actual internal runtime adoption, while
Responses/httpx remains P-GPT compatibility and emergency rollback.

No framework dependency is installed in P43. P43 keeps `production_ready: false`
and does not authorize UI changes, public API expansion, DB schema changes,
public MCP route expansion, public artifact type changes, row-data access,
procedure execution, automatic DDL/DML apply, generated-source apply, deploy, raw
prompt/provider response storage, raw SP storage, raw guide body storage, or
secret storage.

## P44 Real Framework Runtime Adoption

P44 supersedes the active P43 `pilot` direction with actual internal runtime
adoption for AI Draft Pack generation. P43 remains historical readiness evidence;
P44 is the active contract in `spec/eval/p44_framework_runtime_adoption_contract.yaml`.

For OpenAI remote runs, `FrameworkRuntimeConfig.v0.1` selects OpenAI Agents SDK as
the primary generation runtime and LangGraph as the in-process stage orchestrator
for `AiJavaMyBatisDraftPack.v0.1`. The graph runs `file_inventory`, `file_content`,
`quality_gate`, `repair`, and `final` with no LangGraph persistent checkpointer;
the existing platform DB remains the only persisted workflow store. P-GPT
defaults to `responses_httpx`, but explicit internal SDK live evidence is
accepted for approved P-GPT-compatible endpoints when trace locks, sanitized
fixture inputs, and P42/P44 post-validation are present.

P44 changes the internal runtime only. It adds no public API, DB schema, UI,
public MCP route, or public artifact type. Generated artifacts stay draft-only:
`generated_artifacts_production_ready: false` and `productionReady=false` remain
required. Procedure execution, row data access, source apply, deploy, automatic
conversion approval, raw prompt storage, raw provider response storage, raw SP
definition storage, raw guide body storage, and secret storage remain forbidden.

P45 adds the optional live evidence gate `P44_OPENAI_AGENTS_LIVE_GATE=1` for the
adopted OpenAI Agents runtime. It requires OpenAI remote env plus trace redaction
locks and uses sanitized fixture inputs only; it does not require live PPM, row
data, or procedure execution. P-GPT-compatible endpoints are accepted as SDK
evidence only when `AI_GENERATION_RUNTIME=openai_agents` is explicit and
`OPENAI_BASE_URL` or `OPENAI_RESPONSES_URL` is configured. P46 records that
`responses_httpx` is no longer the active OpenAI default, but remains retained
for P-GPT default compatibility and emergency rollback; code deletion is not
approved in this slice.

## P47 Generic AI Draft Quality Uplift

P47 keeps the P44-P46 real framework adoption direction and raises AI Draft Pack
quality through generic evidence and prompt improvements, not target-specific
hardcoding. `prompt:ai_java_mybatis_draft_pack@0.2.0` adds a transient
`DraftPackEvidenceBundle.v0.1` with operation coverage, DTO responsibility,
mapper coverage, and `REVIEW_REQUIRED` marker contracts. The model should split
DTOs and wire Service/Mapper/XML methods from discovered operation ids,
statement evidence refs, and DTO roles; benchmark names such as ManageBond DTOs
remain comparison signals only.

The OpenAI live profile for AI Draft Pack generation is `openai_ai_draft_pack`.
`OPENAI_MODEL_AI_DRAFT_PACK` and `OPENAI_REASONING_EFFORT_AI_DRAFT_PACK` select
the high-quality live model path, defaulting to the analysis-model family rather
than the fast-test profile. P47 adds no public API, DB schema, UI, public MCP
route, public artifact type, source apply, deploy, row-data access, procedure
execution, or production readiness claim. Generated artifacts remain
`production_ready: false`.

## P48 Unified Structured Framework Runtime

P48 extends the adopted P44 OpenAI Agents SDK runtime from AI Draft Pack into all
internal structured LLM paths. `FrameworkModelGateway` wraps the existing
`ModelGateway` interface and routes SP semantic analysis, metadata tool
planning, metadata analysis, platform tool planning, and SP operation-model
planning through `OpenAIAgentsStructuredAdapter` under
`AiStructuredFrameworkAdapter.v0.1`. AI Draft Pack remains on the existing P44
`OpenAIAgentsFrameworkAdapter` plus LangGraph path in `WorkflowService`.

OpenAI remote structured calls now default to `openai_agents` for both official
OpenAI and P-GPT-compatible endpoints. `AI_STRUCTURED_LLM_RUNTIME=responses_httpx`
is retained only as an explicit emergency rollback path for structured calls.
P48 preserves evidence-ref repair,
planner fallback, tool allowlists, SP source text gates, metadata/design
sanitization, knowledge persistence sanitization, and `REVIEW_REQUIRED`
behavior. It also fixes the metadata design planner prompt metadata so
`toolNames` is present for remote structured validation.

P48 is internal only and keeps `production_ready: false`: no public API, DB
schema, UI, public MCP route, public artifact type, source apply, deploy, row
data query, procedure execution, automatic conversion approval, raw prompt or
provider response storage, raw SP storage, raw guide body storage, or secret
storage is authorized.

## P49 Framework Runtime Cleanup Index

P49 consolidates the P43-P48 framework-runtime contracts into one active cleanup
index: P48 is the active structured LLM runtime, P44 remains the active AI Draft
Pack OpenAI Agents plus LangGraph runtime, and P43 is historical readiness
evidence only. The cleanup is contract-backed and removes only scaffolding proven
unused by active runtime paths.

`responses_httpx` remains retained for P-GPT AI Draft Pack compatibility and
explicit emergency rollback, but is not the default structured LLM runtime. The
production-exported P43 baseline/fake framework adapter symbols are removed from
the runtime package and kept only as test helpers for historical fixture coverage.
P49 adds no public API, DB schema, UI, public MCP route, public artifact type,
source apply, deploy, row-data query, procedure execution, automatic conversion
approval, or production readiness claim.

## 한 줄 정의

MSSQL Stored Procedure 및 관련 DB 오브젝트를 분석·문서화하고, 메타데이터와 고품질 LLM 보강을 결합해 Java/MyBatis 전환 코드 초안을 생성하며, 검증 결과를 조직 지식으로 축적하는 중앙 통합형 Agent 플랫폼을 구축한다.

## 제품 목표

- MSSQL Stored Procedure 및 관련 오브젝트를 빠르고 일관되게 분석·문서화한다.
- Java/MyBatis 코드 초안을 표준 형식으로 생성한다.
- DB 메타데이터를 기반으로 테이블·컬럼·스키마 탐색과 보강을 지원한다.
- 프롬프트, 모델, 템플릿, DB 프로필을 중앙에서 관리한다.
- 생성 결과에 근거, 검증, caveat, 재현 가능성을 부여한다.
- 전환 과정에서 축적되는 규칙과 지식을 조직 자산으로 남긴다.

## 범위

### 포함

- MSSQL Stored Procedure, Table, Column, Index, PK/FK, Extended Property, Function, View 등 관련 메타데이터
- SP 분석 및 문서화
- 스키마 탐색, 메타데이터 보강, DTO 초안 생성
- Java/MyBatis Mapper XML, Mapper Interface, Service 초안 생성
- DB 변경은 자동 생성/적용하지 않고 manual SQL review asset 으로만 관리
- 검증, caveat, 버전 관리, 감사로그
- 초안 품질 요약, 근거 map, caveat, 다음 근거 수집 항목

### 제외

- DB 자동 DDL 실행
- 환경 직접 배포 자동화
- 무검증 상태의 자동 코드 반영
- 실제 데이터 조회 및 수정

## 핵심 산출물

- 중앙 통합형 Agent 플랫폼
- MSSQL Metadata MCP 서버
- SP 분석 문서 / 호출관계 및 의존성 결과
- 메타데이터 조회 및 구조 보강 결과
- Java/MyBatis DTO/Service/Mapper/Mapper XML 초안
- 검증/caveat 이력 및 deferred 승인 로그
- 관리자/사용자 가이드
- 시범 적용 및 검증 보고서

## 운영 원칙

- **Evidence-first**: 모든 분석과 생성은 메타데이터 또는 명시적 근거를 동반한다.
- **Tool-grounded AI-heavy hybrid**: metadata, dependency, static facts, evidence refs 는 툴/결정론 계층이 책임지고, SP 의미 해석과 migration/Java/MyBatis 전환 판단은 high-quality LLM 보강을 기본 사용한다.
- **Dependency evidence before inference**: dependency closure/reference resolution 은 raw SQL 이 아니라 MCP metadata evidence digest 로 LLM 과 guide renderer 에 전달하며, 불확실한 대상은 `REVIEW_REQUIRED` 로 유지한다.
- **Deterministic guardrails**: 파싱, 규칙, 검증, forbidden behavior 차단은 결정론적으로 구현한다.
- **Validation-gated**: 기본 제품 플로우는 Draft → Validate → `VALIDATION_COMPLETE` 에서 멈춘다. 사용자 review/approval 흐름 없이 초안 품질과 근거 caveat 를 제공한다.
- **Read-only metadata access**: DB 접근은 메타데이터 조회 전용이며 쓰기를 금지한다.
- **Docs-as-code**: 설계, 정책, 평가 규칙은 저장소 안에서 버전 관리한다.
- **Small reversible changes**: 초기 구현은 작은 기능 슬라이스와 빠른 검증을 우선한다.

## 초기 구현 기준

아래는 기준 문서를 만족시키기 위한 **초기 구현 기준**이다. 실제 저장소가 생기면 이 구조를 기본안으로 삼고, 코드가 확정된 뒤에는 문서를 코드와 함께 갱신한다.

```text
repo/
├─ AGENTS.md
├─ PROJECT.md
├─ ROLES.md
├─ SKILLS.md
├─ ARCHITECTURE.md
├─ TOOLS.md
├─ POLICY.md
├─ EVAL_SPEC.md
├─ TASK_TEMPLATE.md
├─ .codex/
│  ├─ config.toml
│  └─ agents/
├─ .agents/
│  └─ skills/
├─ apps/
│  ├─ web/                 # 중앙 포털 UI
│  └─ api/                 # API/BFF, workflow, validation
├─ services/
│  └─ mssql-mcp/           # MSSQL Metadata MCP 서버
├─ packages/
│  ├─ agent-runtime/       # OpenAI model gateway / prompt / structured LLM analysis
│  ├─ domain/              # Canonical models / contracts
│  ├─ analysis/            # SP parser / dependency logic
│  ├─ generation/          # Doc / code generators
│  ├─ validation/          # Rule validators / quality gates
│  └─ templates/           # Prompt / artifact templates
├─ db/
│  └─ schema/              # 플랫폼 DB DDL
├─ spec/
│  └─ openapi/             # OpenAPI source
├─ fixtures/               # 대표 SP / metadata / eval fixtures
├─ tests/
│  ├─ unit/
│  ├─ contract/
│  ├─ integration/
│  └─ e2e/
└─ docs/
   ├─ adr/
   ├─ admin-guide/
   └─ user-guide/
```

## 단계별 우선순위

### P0. 저장소 부트스트랩
- 루트 문서 세트 정비
- `.codex/config.toml`, custom agents, repo skills 정비
- 기본 품질 명령 규약 수립: `setup`, `fmt`, `lint`, `test`, `check`, `eval`

### P1. Metadata + Analysis MVP
- MSSQL Metadata MCP 서버
- CanonicalAnalysisModel
- SP 분석 문서 / 의존성 결과 생성
- ValidationReport 저장과 draft-quality caveat 추적

### P2. Generation MVP
- Java/MyBatis DTO/Service/Mapper/Mapper XML 초안 생성
- Artifact versioning
- Preview / validation-complete workflow
- Draft-quality validation workflow

### P3. 운영 고도화
- Prompt / model / template / profile registry
- High-quality semantic analysis profile 운영과 fixture-first eval gate 확장
- Eval fixture 확장
- 지식 자산화
- 운영 대시보드 / 모니터링

## 문서 사용 우선순위

1. `AGENTS.md` — Codex가 먼저 읽는 저장소 기본 규칙
2. `PROJECT.md` — 제품 목표, 범위, 우선순위
3. `ARCHITECTURE.md` — 구조와 경계
4. `POLICY.md` — 안전, 승인, 금지 행위
5. `TOOLS.md` — 로컬 도구, 명령, MCP, 환경
6. `EVAL_SPEC.md` — 완료 기준과 검증 기준
7. `TASK_TEMPLATE.md` — 작업 요청 포맷
8. `ROLES.md`, `SKILLS.md` — 역할과 재사용 워크플로우

## 현재 기준 자산

- OpenAPI 초안: `spec/openapi/ai_agent_platform_openapi_v1.yaml`
- Platform DB DDL 초안: `db/schema/ai_agent_platform_schema_v2_dbo_prefix.sql`
- Agent runtime DDL 초안: `db/schema/ai_agent_platform_schema_v3_agent_runtime.sql`
- P25 validation-complete status DDL 초안: `db/schema/ai_agent_platform_schema_v4_validation_complete_status.sql`
- Knowledge asset DDL draft: `db/schema/ai_agent_platform_schema_v6_draft_quality_no_review.sql`
- Metadata analysis run DDL draft: `db/schema/ai_agent_platform_schema_v7_metadata_analysis_runs.sql`
- Domain enum / mapping 기준: `packages/domain/src/ai_agent_domain/models.py`
- OpenAI LLM runtime package: `packages/agent-runtime/src/ai_agent_runtime`
- MSSQL Metadata MCP catalog: `spec/mcp/mssql_metadata_tool_catalog.yaml`
- Platform internal AI tool catalog: `spec/agent-tools/platform_ai_tool_catalog.yaml`
- Validation rules: `spec/validation/validation_rules.yaml`
- P24 SP migration guide quality contract: `spec/eval/p24_sp_migration_guide_quality_contract.yaml`
- P27 dependency evidence tooling design contract: `spec/eval/p27_dependency_evidence_tooling_contract.yaml`
- Machine-readable policy assets: `spec/policy/`
- Environment sample: `.env.example`
- Dockerized test runner: `docker/test/docker-compose.yml`
- Reproducibility locks: `requirements/lock/py314-dev.txt`, `pnpm-lock.yaml`

이 파일들은 현재 병렬 개발의 공유 기준선이다. Wave 0 이후 worker 는 `packages/domain`, `spec/openapi`, `db/schema`, `spec/policy`, `docker/test`, 루트 문서를 읽기 전용 기준으로 사용하고, 변경이 필요하면 코디네이터에게 blocker 로 올린다.

기본 product flow 는 request → metadata → analysis → generation → validation →
`VALIDATION_COMPLETE` 로 종료한다. 사용자 review/approval 화면과 approval API 는 제품 표면에서
제거한다. `REVIEW_REQUIRED` 는 사용자 승인 요구가 아니라 분석 불확실성/evidence caveat 로 해석한다.

## 병합 starter 추가 디렉터리

초기 구현 기준 외에, 실제 starter 레포에는 아래 디렉터리를 함께 둔다.

```text
repo/
├─ docker/
│  └─ test/                # dockerized test runners
├─ ops/
│  └─ codex-parallel/      # 병렬 Codex 실행 계획과 프롬프트
├─ scripts/                # 테스트/헬퍼 스크립트
├─ tasks/                  # 작업 브리프 샘플
├─ spec/
│  ├─ mcp/
│  └─ validation/
└─ docs/
   ├─ admin-guide/
   └─ user-guide/
```

## 외부 DB / 스키마 운영 원칙

- 플랫폼 DB 와 메타데이터 소스 DB 는 외부 인프라에서 관리한다.
- 저장소는 DB 기동/중지 자동화나 스키마 자동 적용 기능을 제공하지 않는다.
- 스키마 변경이 필요하면 `db/schema/` 아래에 버전 업 SQL 파일을 추가하고, 실제 적용은 사용자가 수동으로 수행한다.

## 테스트 실행 원칙

- 기본 검증은 `docker/test/` 아래 테스트 러너를 통해 수행한다.
- 외부 DB 가 필요한 테스트는 환경변수로 연결하되, 저장소가 DB lifecycle 을 관리하지는 않는다.
- Web 계열은 전용 자동화가 자리잡기 전까지 컨테이너 기반 build smoke 와 Playwright MCP smoke 를 병행할 수 있다.
- 호스트 compile-only 검증은 Python 3.14 런타임을 기준으로 수행하며, 실행명은 Makefile `PYTHON` 또는 `.env` `PYTHON` 값으로 조정한다.
