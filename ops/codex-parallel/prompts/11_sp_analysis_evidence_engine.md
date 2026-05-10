# P11 SP Analysis & Evidence Engine


## 공통 운영 철학

- 현재 대화 요청과 첨부 ZIP의 실제 파일 구조를 최우선 기준으로 삼는다.
- P00~P07의 worktree 병렬 개발, Docker 테스트 격리, read-only metadata, draft-only generation, validation/approval/audit 원칙을 유지한다.
- `PLF` 는 platform DB, `PPM` 은 pilot analysis target DB 이다. PPM 이 없거나 접근 불가하면 PLF 로 대체하지 않고 blocker 로 보고한다.
- 실제 row data 조회, procedure 실행, 자동 DDL/DML, 운영 DB 직접 변경, 승인 없는 배포 자동화는 금지한다.
- 비밀값, 실제 비밀번호, 토큰, 실데이터는 코드/문서/fixture/test snapshot 에 넣지 않는다.
- skeleton/stub/fixture-first/optional-live/production-ready 상태를 구분해서 기록한다.
- 공유 contract/policy/common 파일 수정이 필요하면 worker가 임의로 수정하지 말고 coordinator에게 blocker로 보고한다.
- 첫 응답에는 수정 예정 파일, 검증 명령, blocker 후보를 짧게 제시한다.


## 목표

Stored Procedure 분석을 evidence-first engine으로 발전시킨다. definition, parameters, dependency, call graph, transaction/exception/dynamic SQL/temp table pattern, business rule summary를 confidence/review_required/TODO와 함께 표준화한다.

## 읽어야 할 기준 파일

- `PROJECT.md`, `ARCHITECTURE.md`, `POLICY.md`, `EVAL_SPEC.md`
- `docs/productization-architecture-gap-analysis.md`
- `ops/codex-parallel/PRODUCTIZATION_RELEASE_BACKLOG.md`
- `fixtures/eval/productization_readiness_v1.yaml`
- `packages/analysis/README.md`
- `packages/analysis/src/ai_agent_analysis/**`
- `packages/domain/src/ai_agent_domain/models.py`
- `fixtures/mssql/**`
- `fixtures/analysis/**`
- `fixtures/mcp/metadata_snapshot.json`
- `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml`
- `spec/policy/platform_db_standardization_rules_for_ai.json`
- `tests/unit/analysis/**`

## 허용 수정 경로

- `packages/analysis/**`
- `tests/unit/analysis/**`
- `fixtures/analysis/**`
- `fixtures/eval/**`

## 금지 경로

- `packages/domain/**`
- `services/mssql-mcp/**`
- `packages/generation/**`
- `packages/validation/**`
- `spec/**`
- `db/schema/**`
- `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml`

## 구현 범위

- SP signature, parameters, result-set hints, dependencies, nested procedure calls, table/view/function references를 분석한다.
- transaction, TRY/CATCH, dynamic SQL, temp table, cursor, multi-result-set 패턴 detector를 강화한다.
- business rule summary는 evidence refs가 있는 부분과 추론 부분을 구분한다.
- confidence, review_required, TODO, evidenceRefs를 정형 shape로 출력한다.
- PPM pilot SP가 선정되어 있으면 simple/medium/complex fixture로 활용하고, template-only이면 기존 synthetic fixture 기반으로만 확장한다.
- CanonicalAnalysisModel 변경이 필요하면 packages/domain을 직접 수정하지 말고 blocker로 보고한다.

## 검증 명령

- `make test PYTEST_ARGS="tests/unit/analysis"`
- `python3.14 -m compileall packages/analysis tests/unit/analysis`
- 필요 시 `make test PYTEST_ARGS="tests/eval"`

## Blocker 보고 기준

- domain canonical contract 확장 없이는 evidence shape를 안정화할 수 없음
- PPM pilot SP가 template-only라 live representative fixture를 만들 수 없음
- SP definition metadata 권한 부족
- dependency metadata가 incomplete해서 confidence를 높일 수 없음
- dynamic SQL 내부 의존성을 확정해야 하는 요구가 들어옴
