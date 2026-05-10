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
- live IdP/JWKS 와 PLF role membership 검증이 없으면 productization blocker 를 유지함

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
- `make test` 와 이를 호출하는 `make check` 는 호스트 직접 실행 대신 컨테이너 기반 실행을 우선한다.
- 외부 DB 가 필요한 테스트는 환경변수로 연결하되, 저장소는 해당 DB 의 lifecycle 을 관리하지 않는다.
- 자동 테스트가 아직 없는 영역은 smoke/build 검증과 테스트 공백 보고를 함께 남긴다.
