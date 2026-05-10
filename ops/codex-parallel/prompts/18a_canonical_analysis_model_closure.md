# P18A CanonicalAnalysisModel Contract Closure

## 공통 운영 철학

- 현재 대화 요청과 실제 파일 구조를 최우선 기준으로 삼는다.
- P17의 scoped live pilot `CONDITIONAL_GO`는 유지하되, 전체 플랫폼 production-ready 로 과장하지 않는다.
- `PLF` 는 platform DB, `PPM` 은 pilot analysis target DB 이다. PPM 이 없거나 접근 불가하면 PLF 로 대체하지 않고 blocker 로 보고한다.
- 실제 row data 조회, procedure execution, 자동 DDL/DML, 운영 DB 직접 변경, 승인 없는 publish/export 자동화는 금지한다.
- 비밀값, 실제 비밀번호, 토큰, 실데이터, raw SQL definition text 는 코드/문서/fixture/test snapshot 에 넣지 않는다.
- canonical contract 변경은 evidence-first 로 작게 진행한다. shared contract 변경이 불가하면 정확한 blocker 로 남긴다.
- 첫 응답에는 수정 예정 파일, 검증 명령, blocker 후보를 짧게 제시한다.

## 목표

현재 `CanonicalAnalysisModel-compatible-local-v0.2` 후보를 제품 계약으로 승격할 수 있는지 검증하고, 승격 가능한 최소 계약과 deterministic analysis mapping 을 구현한다. 승격할 수 없으면 `DOMAIN_CANONICAL_SCHEMA_MISSING` 등 정확한 blocker 를 기록하고 productization `NO_GO` 를 유지한다.

## 읽어야 할 기준 파일

- `ARCHITECTURE.md`
- `POLICY.md`
- `EVAL_SPEC.md`
- `docs/pilot-release-readiness.md`
- `docs/productization-architecture-gap-analysis.md`
- `fixtures/eval/canonical_analysis_candidate.json`
- `fixtures/eval/productization_gap_closure_p18_v1.yaml`
- `packages/domain/src/ai_agent_domain/models.py`
- `packages/analysis/src/ai_agent_analysis/**`
- `tests/unit/analysis/**`, `tests/eval/**`, `tests/contract/**`

## 허용 수정 경로

- `packages/domain/**`
- `packages/analysis/**`
- `fixtures/eval/productization_gap_closure_p18_v1.yaml`
- `fixtures/eval/canonical_analysis_candidate.json`
- `tests/unit/analysis/**`
- `tests/eval/**`
- `tests/contract/**`
- `docs/productization-architecture-gap-analysis.md`
- `docs/integration-eval-status.md`

## 금지 경로

- `apps/**`
- `services/mssql-mcp/**`
- `db/schema/**`
- `.env.example`에 secret 추가
- `config/mssql/local_docker_profiles.yaml` 임의 변경
- `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml`
- row data, procedure execution, raw definition text 를 evidence 로 저장

## 구현 범위

- Architecture 의 `CanonicalAnalysisModel` 필수 필드를 versioned domain model 또는 명시적 blocker 로 정리한다.
- release-critical canonical field 는 observed evidence 또는 `REVIEW_REQUIRED` blocker 중 하나로 귀결시킨다.
- dynamic SQL, 불완전 dependency, 근거 약한 business rule 은 확정값으로 만들지 않고 `REVIEW_REQUIRED` 를 유지한다.
- snapshot id, registry version refs, modernization points 같은 누락 필드는 구현하거나 정확한 blocker 로 기록한다.
- P17 scoped live pilot decision 은 변경하지 않는다.

## 검증 명령

- `make test PYTEST_ARGS="tests/unit/analysis tests/eval tests/contract"`
- `python3.14 -m compileall packages/analysis packages/domain tests`
- 필요 시 `make test PYTEST_ARGS="tests/eval/test_p18_productization_gap_closure.py"`

## Blocker 보고 기준

- domain canonical schema 변경이 coordinator 승인 없이 불가능함
- snapshot id 또는 registry version refs 를 안전하게 바인딩할 수 없음
- release-critical field 에 evidence refs 가 없음
- GO 판정을 위해 row data, procedure execution, raw definition text 저장, PLF fallback, auto publish/export 가 필요함
