# EVAL_SPEC.md

## 목적

이 문서는 저장소에서 "완료"를 판단하는 평가 규격을 정의한다.  
핵심 원칙은 **기능 통과만으로 충분하지 않다**는 점이다.  
정확성, 근거, 정책 준수, 재현 가능성, 문서 정합성까지 함께 본다.

## 평가 원칙

- 단위 테스트보다 계약/행동 검증을 우선하는 영역을 분리한다.
- 생성 계열 기능은 fixture 와 rubric 으로 평가한다.
- 동일 입력 + 동일 snapshot + 동일 registry version 조합이면 결과가 재현 가능해야 한다.
- 품질 게이트는 자동 검증 + 수동 리뷰 포인트 둘 다 남긴다.

## 평가 축

| 축 | 질문 |
|---|---|
| Contract correctness | API/MCP/DDL/Canonical 모델이 계약대로 동작하는가 |
| Analysis quality | SP 구조, 의존성, 패턴 식별이 정확한가 |
| Generation quality | 문서/코드/DDL 초안 형식과 필수 정보가 올바른가 |
| Evidence coverage | 결과가 근거를 갖거나 검토 필요로 표기되는가 |
| Policy compliance | 금지 행위를 하지 않았는가 |
| Reproducibility | 동일 조건에서 결과가 안정적으로 재현되는가 |
| Docs sync | 코드/계약/문서가 어긋나지 않는가 |

## 필수 평가 스위트

### 1. Metadata MCP Contract
대상:
- tool input schema
- tool output schema
- error model
- read-only enforcement

필수 체크:
- 자유 SQL 입력 불가
- snapshot/evidence 필드 존재
- 오류 코드가 문서화된 형태와 일치
- 실제 데이터 접근 도구 없음

통과 기준:
- 필수 contract test 100% 통과

### 2. Analysis Model Accuracy
대상:
- procedure parameters
- call graph
- read/write dependencies
- transaction / exception / dynamic SQL / temp table flags

필수 체크:
- 대표 fixture 에 대해 required fields 누락 없음
- 분석 결과가 canonical schema 에 적합
- 불확실한 추론은 review_required 로 표시

통과 기준:
- required field presence 100%
- 대표 fixture 기준 핵심 필드 exact match 또는 허용된 불확실성 표기

### 3. Generation Format Conformance
대상:
- SP analysis doc
- dependency report
- Mapper XML / Interface / Service
- DTO / VO / Model
- DDL draft

필수 체크:
- artifact type 별 필수 섹션 존재
- naming/package 규칙 충족
- generator version / evidence refs 존재

통과 기준:
- required section presence 100%
- naming/package rule violations 0

### 4. Validation / Approval Workflow
대상:
- validation reports
- preview
- approval records
- publish gating

필수 체크:
- validation 없이 publish 불가
- approval decision trace 저장
- reject 후 재검증 없이 publish 불가

통과 기준:
- 상태 전이 규칙 위반 0

### 5. Policy & Security
대상:
- forbidden action checks
- secrets handling
- unsafe command use
- doc drift
- production auth/RBAC source and enforcement evidence

필수 체크:
- 실제 데이터 접근 코드 없음
- 자동 DDL 실행 경로 없음
- 민감 환경값 log/fixture 유출 없음
- 정책 문서와 구현이 모순되지 않음
- production identity source 가 verified OIDC/JWT 로 문서화되어 있고 role source 가 PLF auth table 로 연결됨
- validation/approval enforcement 구현 시 unauthorized negative test 가 존재함
- live IdP/JWKS 와 PLF role membership 검증이 없으면 production-grade enterprise Auth/RBAC claim 을 금지하고 deferred future hardening 으로 유지함

통과 기준:
- P0 위반 0
- auth/RBAC source 문서화가 없거나 mock header/hardcoded actor 로 production 을 가장하면 blocker

### 6. Reproducibility
대상:
- same input / same snapshot / same registry versions

필수 체크:
- hash 또는 stable normalized output 비교
- generator version and registry refs persisted

통과 기준:
- 결정론적 결과가 필요한 artifact 는 동일 결과
- 비결정론 허용 artifact 는 차이 범위가 문서화됨

### 7. Integration Happy Path
대상:
- request submission
- job status
- draft artifact preview
- validation report
- approval decision recording

필수 체크:
- 기본 경로는 `master` metadata profile 과 fixture-backed MCP snapshot 을 사용
- job 은 `REVIEW_PENDING`, current step 은 `VALIDATE`
- persisted artifact type 이 OpenAPI requested output group 과 구분됨
- 승인 decision 은 기록만 수행하며 publish 상태로 전이하지 않음

통과 기준:
- `make test PYTEST_ARGS="tests/e2e tests/eval"` 통과
- `PUBLISHED` 상태, 자동 DDL, row-data access 흐름 0건

### 8. P21 No-Mock Portal Gate
대상:
- Python 3.14 host/Docker baseline
- Web HTTP-only runtime path
- PLF workflow repository
- PPM read-only metadata access

필수 체크:
- `requirements/lock/py314-dev.txt`, `python:3.14-slim`, `requires-python >=3.14`, Ruff `py314` target 이 현재 기준임
- Web functional pages 는 mock adapter 나 demo ids 에 의존하지 않음
- `/artifacts/[artifactId]` page-load 는 validation write 를 만들지 않고 latest validation GET 만 수행함
- `/review/decision` 은 preview-only 가 아니라 approval decision API 를 호출함
- `P21_LIVE_PORTAL_GATE=1` 에서 PLF/PPM env 가 없으면 skip 이 아니라 blocker failure 로 보고함

통과 기준:
- `make test PYTEST_ARGS="tests/contract/test_p21_no_mock_prompt_assets.py tests/eval/test_p21_live_portal_no_mock_gate.py"` 통과
- `make test-web-smoke` 통과
- live gate 성공 전에는 `production_ready: false` 유지

### 9. P22 OpenAI LLM Agent Runtime Gate
대상:
- `packages/agent-runtime` model gateway / prompt renderer / structured parser
- `SPAnalysisOptions` typed LLM options
- `GET /api/v1/jobs/{jobId}/agent-runs`
- no-raw-trace platform storage and web trace summary

필수 체크:
- 기본 테스트는 `FakeModelGateway` 를 사용하고 외부 OpenAI API 를 호출하지 않음
- fast/test profile 기본값은 `gpt-5-nano` 이며 optional live confidence 에서는 `OPENAI_MODEL_FAST_TEST` 로 모델을 바꿀 수 있음
- remote 실행은 `LLM_ENABLE_REMOTE=1`, `LLM_ALLOW_SP_TEXT=1`, `OPENAI_API_KEY` gate 를 요구
- raw prompt, raw SP definition, raw OpenAI response text 는 DB/API/artifact/test output 에 저장하지 않음
- structured output 은 `schema:llm_semantic_analysis@0.1.0` strict JSON schema 를 통과해야 함
- LLM inference evidence 는 validation 에서 `REVIEW_REQUIRED` 로 유지됨

통과 기준:
- `make test PYTEST_ARGS="tests/unit/agent_runtime tests/unit/api/test_workflow_service.py tests/integration/api/test_api_workflow_routes.py tests/contract/test_p22_agent_runtime_assets.py tests/eval/test_p22_openai_live_agent_gate.py"` 통과
- `make test-web-smoke` 또는 HTTP adapter smoke 에서 LLM trace summary 표시 확인
- 선택 live gate 는 아래 명령으로 별도 수행하며, 기본 게이트에 포함하지 않음

```bash
LLM_LIVE_GATE=1 LLM_ENABLE_REMOTE=1 LLM_ALLOW_SP_TEXT=1 make test PYTEST_ARGS="tests/eval/test_p22_openai_live_agent_gate.py"
```

### 10. P23 LLM SP Analysis Quality Eval Contract
대상:
- `spec/eval/p23_llm_sp_analysis_quality_contract.yaml`
- `fixtures/eval/llm_sp_analysis_quality_p23_v1.yaml`
- `tests/eval/test_p23_llm_sp_analysis_quality.py`
- `ops/codex-parallel/prompts/23*.md`
- P23A~P23D split execution manifest

필수 체크:
- P23 은 P22 runtime 이후의 평가 확장으로 분리한다
- P23A 는 계약/프롬프트 자산을 만들고, P23B 는 synthetic simple/medium/complex fixture 와 fake-gateway 검증을 추가한다
- P23C 는 P23B fixture 를 `FakeModelGateway` 로 반복 실행하고 quality score 를 계산한다
- simple/medium/complex stored procedure scenario matrix 와 authored fixture 를 유지한다
- fast/test profile 기본값은 `gpt-5-nano` 이며 optional live confidence 에서는 `OPENAI_MODEL_FAST_TEST` 로 모델을 바꿀 수 있다
- LLM 보강 필드는 `business_rules`, `modernization_points`, `risk_flags`, `review_markers`, `assumptions` 로 제한한다
- `LLM_INFERENCE` evidence 와 unsupported dependency/table/function claim 의 `REVIEW_REQUIRED` 처리 기준을 둔다
- scoring runner 는 semantic recall, evidence discipline, overclaim control, storage safety 를 검증하며 raw prompt/SP/provider response text 를 저장하지 않는다
- raw prompt, raw SP definition, raw OpenAI response text, row data, secret 은 fixture trace/API/Web 산출물에 저장하지 않는다
- optional live gate 는 confidence signal 이며 기본 계약 검증이나 production readiness 의 필수 조건이 아니다

판정 해석:
- 통과: 기본 fixture-first P23 테스트가 통과하고 `semantic_recall >= 0.75`, `evidence_discipline >= 0.9`, `unreviewed_overclaims <= 0`, `storage_safety_findings <= 0` 을 만족한다.
- 보류: fixture-first gate 는 통과했지만 optional live confidence gate 가 skip/fail/unavailable 이거나 로컬 검증 prerequisites 가 준비되지 않았다. 이 경우 P23 confidence signal 만 부족한 상태이며 production readiness 로 해석하지 않는다.
- 실패/blocker: quality threshold 미달, raw prompt/SP/provider response 저장, `production_ready: true` 주장, PPM-to-PLF fallback, model/profile/prompt/schema drift, 또는 P24 document/code generation 범위를 P23 완료로 표현하는 경우다.

통과 기준:
- `make test PYTEST_ARGS="tests/eval/test_p23_llm_sp_analysis_quality.py tests/unit/agent_runtime tests/contract/test_p23_llm_eval_contract_prompt_assets.py"` 통과
- P23A -> P23B -> P23C -> P23D 병합 순서가 manifest 에 명시됨
- optional live quality gate 는 아래 명령으로 별도 수행하며, 실패해도 production blocker 로 과장하지 않음
- P23D 완료 후에도 별도 production readiness gate 전까지 `production_ready: false` 유지

```bash
LLM_LIVE_GATE=1 LLM_ENABLE_REMOTE=1 LLM_ALLOW_SP_TEXT=1 make test PYTEST_ARGS="tests/eval/test_p23_openai_quality_live_gate.py"
```

### 11. P24 SP Migration Guide Quality Eval Contract

P24C implementation status: fixture-first renderer/evaluator coverage is now
implemented for the existing `SP_ANALYSIS_DOC` and `DEPENDENCY_REPORT` artifact
types. The evaluator scores the rendered artifact pair with no new persisted
artifact type, no API/schema changes, no live DB access, no raw prompt/SP/provider
response storage, and `production_ready: false`.

대상:
- `spec/eval/p24_sp_migration_guide_quality_contract.yaml`
- `fixtures/eval/sp_migration_guide_quality_p24_v1.yaml`
- `tests/eval/test_p24_sp_migration_guide_quality.py`
- `tests/contract/test_p24_sp_migration_guide_contract_prompt_assets.py`

필수 체크:
- P24A 는 contract/prompt/task/manifest 자산을 고정하고, P24B 는 sanitized fixture-first guide quality expectation 을 추가하며, P24C 는 기존 artifact type renderer/evaluator 로 fixture 를 점수화한다
- simple/medium/complex synthetic scenarios 가 required section taxonomy, dependency inventory, DML matrix, branch call flow, critical phase/risk metrics, appendix mappings, evidence refs 를 포함한다
- P24C 는 기존 `SP_ANALYSIS_DOC` 와 `DEPENDENCY_REPORT` 를 재사용하고 새 persisted artifact type, API/Web/DB schema 변경, live DB access 를 만들지 않는다
- fast/test profile 기본값은 `gpt-5-nano` 이며 optional live confidence 에서는 `OPENAI_MODEL_FAST_TEST` 로 모델을 바꿀 수 있다
- fixture 와 expected report 는 raw prompt, raw SP definition, raw OpenAI response text, row data, secret, 사용자 제공 guide 본문, 실제 운영 SP 원문을 저장하지 않는다
- unsupported dependency/table/function/cross-DB claim 과 low-evidence business-rule claim 은 모두 `REVIEW_REQUIRED` 로 남긴다
- PPM 접근 실패 시 PLF fallback 은 금지하고 `production_ready: false` 를 유지한다
- Java/MyBatis 는 `draft_only_readiness_notes` 로만 다루며 generated source application 은 수행하지 않는다

판정 해석:
- 통과: fixture-first renderer/evaluator report 가 모든 P24 threshold 를 만족하고 `productionReady: false`, storage safety findings 0, PLF fallback 없음, unsupported claim `REVIEW_REQUIRED` 를 유지한다.
- 보류: 필수 fixture-first gate 는 통과했지만 optional live confidence evidence 가 skip/fail/unavailable 이거나 로컬 검증 prerequisites 가 준비되지 않았다. 이는 confidence evidence 부족이며 production readiness 로 해석하지 않는다.
- 실패/blocker: threshold 미달, raw prompt/SP/provider response/row data/secret 저장, PPM-to-PLF fallback, `production_ready: true` 또는 자동 전환 완료 주장, automatic conversion/apply, row data 조회, procedure execution, business DB DDL/DML 요구, 또는 P25+ Java/MyBatis 확장을 P24 완료로 표현하는 경우다.

통과 기준:
- `required_section_coverage >= 1.0`
- `evidence_linked_claim_coverage >= 0.9`
- `dml_matrix_coverage >= 0.9`
- `branch_call_flow_coverage >= 0.85`
- `unsupported_claim_review_required_ratio >= 1.0`
- `storage_safety_findings <= 0`

```bash
make test PYTEST_ARGS="tests/eval/test_p24_sp_migration_guide_quality.py tests/contract/test_p24_sp_migration_guide_contract_prompt_assets.py"
```

## 초기 fixture 세트

`fixtures/` 아래에 최소 아래 대표 사례를 둔다.

1. `sp_simple_crud`
   - 단순 입력/출력
   - 기본 CRUD 패턴

2. `sp_txn_with_try_catch`
   - 명시적 transaction
   - TRY/CATCH

3. `sp_with_dynamic_sql`
   - dynamic SQL 탐지
   - review_required 경계

4. `sp_with_temp_table`
   - temp table 사용
   - intermediate result 추론

5. `schema_search_order_domain`
   - 주문 도메인 테이블/컬럼 유사 검색
   - logical/physical name mapping

## PR / 작업 단위 최소 게이트

| 변경 종류 | 최소 검증 |
|---|---|
| 문서만 변경 | 링크/예시/명령 검토 |
| API contract 변경 | schema validation + contract test |
| MCP tool 변경 | contract test + read-only enforcement test |
| parser/analysis 변경 | fixture 기반 analysis eval |
| generator 변경 | artifact format eval + evidence coverage |
| policy/approval 변경 | workflow state test + reviewer checklist |
| auth/RBAC source 변경 | ADR/admin guide sync + role matrix contract test |
| auth/RBAC enforcement 변경 | 401/403 negative route test + audit actor binding test |
| OpenAI/LLM runtime 변경 | fake gateway unit + no-raw-trace contract + optional live gate 문서화 |
| LLM analysis quality eval 변경 | P23 contract prompt asset test + fixture-first fake eval + optional live gate 문서화 |
| SP migration guide quality eval 변경 | P24 contract prompt asset test + fixture-first renderer/evaluator section/evidence/DML/call-flow eval |

## 평가 산출물 형식

가능하면 각 평가 실행은 아래 구조의 JSON 또는 동등한 구조를 남긴다.

```json
{
  "suite": "analysis-model-accuracy",
  "fixture": "sp_txn_with_try_catch",
  "status": "pass",
  "metrics": {
    "required_fields_present": true,
    "exact_match_fields": 12,
    "review_required_fields": 2
  },
  "artifacts": [
    "analysis_result.json",
    "validation_report.json"
  ]
}
```

현재 P06 eval fixture 는 `fixtures/eval/` 아래 file-based interface 로 둔다.

- `request.json`
- `canonical_analysis_candidate.json`
- `artifact_payloads.json`
- `rubric.yaml`

## 완료 판정

아래를 모두 만족해야 완료다.

- 필수 평가 스위트 통과
- 정책 위반 없음
- 문서 동기화 완료
- 남은 리스크가 명시됨
- 사람이 검토해야 하는 부분이 분리되어 제시됨

## 테스트 실행 환경

- 기본 검증 경로는 `docker/test/` 아래의 도커 테스트 러너다.
- Python 실행 기준은 host 와 Docker 모두 3.14 이다.
- `make test` 와 이를 호출하는 `make check` 는 호스트 직접 실행 대신 컨테이너 기반 실행을 우선한다.
- 외부 DB 가 필요한 테스트는 환경변수로 연결하되, 저장소는 해당 DB 의 lifecycle 을 관리하지 않는다.
- 자동 테스트가 아직 없는 영역은 smoke/build 검증과 테스트 공백 보고를 함께 남긴다.
