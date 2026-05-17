# POLICY.md

## P36 Output Renewal Policy

- P36 deliverables stay `production_ready: false`.
- SQL evidence in generated artifacts must be bounded sanitized statement evidence, never a full SP definition.
- `DEPENDENCY_REPORT` is an evidence dossier and must keep caveats and next-evidence items visible.
- Java/MyBatis drafts are review-required reconstruction aids, not deployable source.
- `DTO_MODEL_DRAFT`, `VO_DRAFT`, `MODEL_DRAFT`, and `DDL_DRAFT` are retired public outputs for new requests.
- Row-data queries, procedure execution, business DB DDL/DML, automatic DDL apply, automatic source deployment, raw prompt/provider response storage, and secret storage remain forbidden.

## P38 Metadata Design Chat Policy

- Metadata design chat runs may store sanitized request/result/error JSON only in `METADATA_DESIGN_RUNS`.
- `createTableScriptPreview` is a non-executable manual-review preview, not an artifact and not an apply path.
- `DTO_DRAFT` in a design result is a preview inside run JSON only; it is not workflow artifact persistence.
- Metadata lookup remains read-only through MCP tools; row data, procedure execution, business DB DDL/DML, automatic DDL apply, publish/deploy/source apply, raw prompt/provider response storage, and secret storage remain forbidden.
- Missing or inferred names, types, descriptions, PK/FK, index, or relationship decisions must stay `REVIEW_REQUIRED`.

## P41 SP Operation Model Renewal Policy

- `SpOperationModel.v0.1` is an internal draft planning contract, not production-ready conversion evidence.
- P41 operation fixtures may store sanitized branch, statement, target, field-candidate, evidence-ref,
  and DTO-blueprint facts only.
- User-provided guide files may be used as quality references, but raw SP definitions, raw guide body
  copies, raw prompts, raw provider responses, row data, secrets, and executable SQL snippets must not
  be persisted in repo fixtures or platform storage.
- Cross-database writes, uncertain TVF/procedure kind, called procedure I/O, and branch-specific
  result-shape uncertainty must remain `REVIEW_REQUIRED`.
- P41A does not authorize UI changes, public artifact type expansion, live MCP tool expansion,
  procedure execution, row-data access, automatic DDL/DML apply, or generated-source deployment.

## P35 Source Context Policy

- Full stored procedure definitions must not be sent to the model by default. The semantic runtime
  uses `ProcedureSourceMap` plus bounded retrieved spans as transient source context.
- Retrieved span text is allowed only when `allowSpDefinitionToModel=true`,
  `sourceContextMode=RETRIEVED_SPANS`, `LLM_ENABLE_REMOTE=1`, and `LLM_ALLOW_SP_TEXT=1` are
  explicitly satisfied for remote model use.
- Stored platform data, artifacts, knowledge assets, exports, audit logs, and API responses may keep
  sanitized `analysisCoverage`, `sourceContextSummary`, span ids, line ranges, risk tags, object refs,
  and evidence refs. They must not keep selected span text, full SP definitions, raw prompt text,
  provider responses, row data, or snippets derived from source text.
- Context budget fallback is an evidence caveat. `LLM_CONTEXT_BUDGET_REVIEW_REQUIRED` is not production
  approval or automatic conversion evidence.
- Dependency procedure semantic fan-out is allowed only for confirmed same-profile PROCEDURE
  dependencies and confirmed same-server cross-database PROCEDURE dependencies selected from MCP
  dependency closure evidence with catalog-backed `SAME_SERVER_CROSS_DATABASE_CATALOG` resolution.
  Child AgentRuns may store sanitized analysis output and source context summaries, but never raw
  dependency definitions, selected span text, prompt bodies, provider responses, row data, or
  snippets.

## 절대 금지

다음은 저장소와 Codex 운영에서 금지한다.

- 실제 데이터 조회 / 수정
- 공유 DB 또는 운영 DB에 대한 자동 DDL 실행
- 환경 직접 배포 자동화
- 무검증 상태의 자동 코드 반영
- 저장소 밖 파일 수정
- 파괴적 git 명령의 무단 실행
- 비밀값의 코드/문서/로그/fixture 저장

## 데이터 접근 정책

- DB 접근은 메타데이터 조회 전용이다.
- 앱/생성기/분석 로직은 MSSQL 에 직접 접근하지 않는다.
- 메타데이터 접근은 `services/mssql-mcp` 경계로 집중한다.
- Dependency closure/reference resolution 은 structured MCP metadata evidence 만 사용하며 자유 SQL,
  raw definition 저장, row data, procedure execution, business DB DDL/DML 을 허용하지 않는다.
- 실제 row data 를 요구하는 기능은 범위 밖으로 간주한다.

## 승인 정책

### 자동 허용
- 저장소 내 읽기
- 검색, diff, 정적 분석
- 테스트/포맷/lint
- 문서 수정
- 저장소 내부의 작은 코드 수정

### 명시적 승인 필요
- 새 런타임 의존성 추가
- migration/DDL 변경
- 샘플 데이터 또는 fixture 구조 대규모 변경
- 네트워크가 필요한 설치/업데이트
- 파일 이동/삭제가 큰 작업
- 기본 규칙을 바꾸는 `.codex/config.toml` 수정

### 기본 금지
- 운영/공유 환경 반영
- shared DB write
- production credential 사용
- 외부 SaaS 로 민감 데이터 전송
- production auth/RBAC 를 mock header, hardcoded actor, fixture token 으로 가장하는 행위

### 외부 LLM / OpenAI 전송 정책

- OpenAI API 호출은 `LLM_ENABLE_REMOTE=1` 이 설정된 경우에만 허용한다.
- Stored Procedure definition 원문을 모델 입력으로 보내려면 request option
  `allowSpDefinitionToModel=true` 와 환경변수 `LLM_ALLOW_SP_TEXT=1` 이 모두 필요하다.
- P26 기본 API/Web 옵션은 high-quality semantic analysis 를 선택하지만, live OpenAI 실행은
  `LLM_ENABLE_REMOTE=1`, `LLM_ALLOW_SP_TEXT=1`, `OPENAI_API_KEY` 가 준비된 경우에만 허용한다.
  기본 fixture/test 실행은 fake gateway 를 사용해 외부 OpenAI 를 호출하지 않는다.
- SP definition 원문은 transient request input 으로만 허용하며 플랫폼 DB, artifact,
  audit log, test snapshot, API response 에 저장하지 않는다.
- raw prompt text, raw OpenAI response text, token/secret, provider credential 은 저장하거나
  노출하지 않는다.
- 저장 가능한 trace 는 provider, model, model profile, prompt/schema version, input/prompt/output
  hash, token usage, latency, status, schema-valid structured output, sanitized component invocation
  summary 로 제한한다.
- LLM inference 는 metadata fact 가 아니며 dependency/table/function/procedure 사실을 확정하는
  근거로 사용할 수 없다. 해당 보강은 `LLM_INFERENCE` evidence 와 `REVIEW_REQUIRED` 검토점으로
  남긴다.
- LLM claim 의 `evidenceRefs` 는 deterministic fact id 만 사용할 수 있다. prompt/input/output hash,
  provider response id, raw SQL snippet 같은 trace 값은 claim evidence 로 사용할 수 없다.
- Dynamic SQL, unsafe cross-database, unsupported dependency/table/function/procedure claim 은 LLM 출력에
  marker 가 없더라도 deterministic guard 가 `REVIEW_REQUIRED` 로 보강해야 한다.
- AI metadata tool orchestration 은 bounded planner 방식만 허용한다. LLM 은 tool request plan 을
  strict schema 로 제안할 수 있지만 실제 MCP 실행은 workflow 의 allowlisted active/read-only catalog,
  profile 고정, call budget, structured argument guard, sanitized output storage 를 통과해야 한다.
  public metadata invoke API allowlist 는 이 기능 때문에 확장하지 않는다.
- Metadata analysis API 의 AI-MCP orchestration 도 같은 경계를 따른다. `POST /api/v1/metadata/analyze`
  는 기존 search endpoint 를 LLM 호출 경로로 바꾸지 않고, 기본적으로 sanitized response 와
  versioned knowledge asset 을 함께 만든다. 분석 응답과 knowledge storage 에는 sanitized evidence
  digest, deterministic fact id, object profile/graph/dto readiness 요약만 포함하고 raw definition,
  row data, free-form SQL, procedure execution, DDL/DML, secrets, raw prompt/provider response text 는
  포함하지 않는다.
- `POST /api/v1/metadata/analysis-runs` and polling storage use the same sanitized metadata
  analysis payloads. Durable run storage may keep request/result/error JSON only; it must not keep
  row data, raw SQL/SP definitions, procedure execution output, DDL/DML controls, secrets, raw
  prompts, raw provider responses, approval decisions, reviewer identity, or human review records.
- AI platform context tool orchestration 은 bounded planner 방식만 허용한다. LLM 은
  `spec/agent-tools/platform_ai_tool_catalog.yaml` 의 internal/read-only tool request plan 을 제안할 수
  있지만 실제 실행은 current job/db profile/target scope gate 와 내부 platform registry 가 수행한다.
  public invoke API 는 만들지 않는다. 반환/저장 가능한 값은 sanitized `platformToolEvidence`,
  `platform.<toolName>.<hash>` fact, component summary 로 제한하며 artifact full content, raw SQL/SP
  definition, row data, procedure execution, DDL/DML, approval/review write, export creation, secrets,
  raw prompt/provider response text 는 금지한다.
- Knowledge assetization 은 조직 지식 축적 경로이지만 draft/evidence-caveated knowledge 로만 해석한다.
  `SP_ANALYSIS`, `DEPENDENCY_EVIDENCE`, `METADATA_PROFILE`, `DTO_READINESS`,
  `CANONICAL_ANALYSIS` asset 과 JSONL/GRAPH_JSON export 는 sanitized facts/edges 만 포함해야 하며,
  자동 전환 승인, production readiness, publish/deploy/apply 근거로 사용할 수 없다.
- Knowledge lifecycle uses `DRAFT`, `REVIEW_REQUIRED`, and `ARCHIVED`. `REVIEW_REQUIRED` is an
  evidence caveat, not a human review workflow. `ARCHIVED` is terminal.
- Human knowledge review comments, reviewer identity writes, and approval decisions are absent
  from the current product/API/DB surface.
- Knowledge redaction marker 는 원문에서 파생된 hash, length, snippet 을 남기지 않으며,
  fact graph edge 는 같은 asset version 의 fact id 를 참조하거나 `REVIEW_REQUIRED` endpoint fact 로 남긴다.

## 생성 결과 정책

- 모든 생성 결과는 초안이다. 승인 전 확정본이 아니다.
- 근거가 명확한 내용과 추론 기반 내용을 구분한다.
- 불확실한 결과는 `REVIEW_REQUIRED` 또는 동등한 상태를 표시한다. P25 이후 이 표기는 사용자 승인 플로우 요구가 아니라 분석 불확실성/evidence caveat 의미다.
- artifact 는 버전, 생성기 버전, snapshot, registry refs 를 추적 가능해야 한다.
- P25 기본 product flow 는 validation 이후 `VALIDATION_COMPLETE` 에서 멈추며 review UI 를 노출하지 않는다. Approval API/server code 는 deferred capability 로 남기되 기본 workflow 완료 조건이나 production readiness 근거로 사용하지 않는다.
- SP migration guide quality gate 는 `SP_ANALYSIS_DOC` 와 `DEPENDENCY_REPORT` 초안 품질 평가로만 해석한다. 통과 결과도 production-ready, 자동 전환 완료, 자동 적용 승인으로 표현하지 않는다.
- Unsupported dependency/table/function/unsafe cross-DB claim 과 low-evidence business-rule claim 은 `REVIEW_REQUIRED` 로 유지한다.
- Ambiguous dependency, unresolved synonym target, dynamic SQL marker, unsafe cross-database target, cross-server target without catalog confirmation, caller-dependent reference 는 deterministic fact 로 승격하지 않고 `REVIEW_REQUIRED` 로 유지한다.

## 코드 변경 정책

- 작은 단위로 수정한다.
- 관련 없는 리팩터링은 섞지 않는다.
- 공용 계약을 바꾸면 소비자와 문서를 함께 갱신한다.
- 테스트 가능성이 낮은 구조를 도입하지 않는다.
- 숨겨진 글로벌 상태보다 명시적 의존성 주입을 우선한다.

## 문서 정책

아래가 바뀌면 문서를 같이 수정한다.

- 서비스 경계
- API contract
- DB schema
- Canonical model
- tool surface
- quality gate
- local commands / runbook

## 보안 규칙

- 비밀값은 환경변수 또는 로컬 비밀 저장소에서만 읽는다.
- 로그에는 SQL connection string, tokens, passwords, cookies 를 남기지 않는다.
- 테스트 fixture 는 비식별/합성 데이터만 사용한다.
- 외부 문서 조회는 공식 문서를 우선한다.
- Production actor identity 는 verified OIDC/JWT 같은 검증된 upstream identity boundary 에서만 온다.
- Production role source 는 PLF platform DB 의 `AUTH_USERS`, `AUTH_ROLES`, `AUTH_USER_ROLES` membership 으로 문서화하고 검증한다.
- Production auth/RBAC enforcement 는 `AUTH_RBAC_ENFORCEMENT=1` 과 승인된 `OIDC_ISSUER`, `OIDC_AUDIENCE`, `OIDC_JWKS_URL` 설정 없이는 production-ready 로 주장할 수 없다.
- Verified identity 가 없으면 401, verified identity 는 있으나 role-to-action matrix 를 만족하지 못하면 403 으로 분리한다.

## 검증 정책

- 기능 구현에는 최소 하나의 검증 수단이 필요하다.
- 핵심 계약 변경에는 contract test 가 필요하다.
- generator/validator 변경에는 fixture 기반 eval 이 필요하다.
- 정책 위반이 하나라도 있으면 작업은 완료가 아니다.

## 예외 처리

정책 예외가 정말 필요하면 다음을 반드시 남긴다.

- 왜 예외가 필요한지
- 범위를 어디까지 허용하는지
- 위험 완화책
- 사후 복구 방법

## 외부 DB / 스키마 변경 정책

- 저장소는 플랫폼 DB 나 메타데이터 소스 DB 의 기동/중지를 관리하지 않는다.
- 스키마 변경은 `db/schema/` 아래의 versioned SQL 파일로만 표현한다.
- `db/schema/` 의 SQL 을 실제 DB 에 적용하는 행위는 사용자/운영자의 수동 절차이며, Codex 작업 범위 밖이다.
- 외부 DB 가 필요하더라도 로컬 임시 DB container 를 저장소 기본 워크플로우에 강제하지 않는다.

## 테스트 실행 정책

- 기본 테스트 명령은 도커 테스트 러너를 통해 수행한다.
- 새 테스트 스위트를 추가할 때는 가능하면 도커 실행 경로를 같이 제공한다.
- 테스트가 외부 DB 에 의존하면 연결 정보만 주입하고, DB lifecycle 은 별도 환경에서 관리한다.
