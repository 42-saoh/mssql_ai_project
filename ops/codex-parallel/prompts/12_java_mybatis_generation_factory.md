# P12 Java/MyBatis Generation Factory


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

PI 3기 표준에 맞춘 Java/MyBatis 초안 생성 factory를 template registry, naming policy, generation manifest, golden sample, diff/review checklist 중심으로 productization한다. 모든 생성물은 draft-only이며 사람이 최종 검토/승인한다.

## 읽어야 할 기준 파일

- `PROJECT.md`, `ARCHITECTURE.md`, `POLICY.md`, `EVAL_SPEC.md`
- `docs/productization-architecture-gap-analysis.md`
- `ops/codex-parallel/PRODUCTIZATION_RELEASE_BACKLOG.md`
- `fixtures/eval/productization_readiness_v1.yaml`
- `packages/generation/README.md`
- `packages/generation/src/ai_agent_generation/**`
- `packages/templates/**`
- `spec/policy/project_ai_java_mybatis_generation_policy.yaml`
- `spec/policy/platform_db_standardization_rules_for_ai.json`
- `fixtures/generation/**`
- `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml`
- `packages/analysis/**`
- `packages/validation/**`
- `tests/unit/generation/**`
- `tests/contract/test_generation_goldens_and_repro_assets.py`

## 허용 수정 경로

- `packages/generation/**`
- `packages/templates/**`
- `tests/unit/generation/**`
- `fixtures/generation/**`
- 필요한 경우 generation 관련 eval fixture

## 금지 경로

- `packages/domain/**`
- `packages/analysis/**`
- `packages/validation/**`
- `services/mssql-mcp/**`
- `spec/**`
- `db/schema/**`
- `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml`

## 구현 범위

- Mapper XML, Mapper Interface, Service, DTO/VO/Model 초안 생성을 template registry 기반으로 정리한다.
- package/class/method/path/namespace naming은 policy asset에서 읽고, 조용한 새 규칙을 만들지 않는다.
- generation manifest에는 input snapshot, template version, policy version, evidence refs, TODO/review checklist를 기록한다.
- golden sample을 확장하되 PPM manifest가 template-only이면 실제 object name 기반 golden을 만들지 않는다.
- 생성물 diff/review checklist에는 수동 검토 항목, 확정 불가 영역, SQL 위험 marker를 포함한다.
- 실제 프로젝트 소스에 생성물을 자동 반영하지 않는다.

## 검증 명령

- `make test PYTEST_ARGS="tests/unit/generation tests/contract/test_generation_goldens_and_repro_assets.py"`
- `python -m compileall packages/generation tests/unit/generation`
- 필요 시 `make test PYTEST_ARGS="tests/unit/validation"`

## Blocker 보고 기준

- policy asset 변경 없이는 naming/path/namespace를 일관되게 생성할 수 없음
- CanonicalAnalysisModel 또는 validation rule 변경이 필요함
- PPM pilot object가 template-only라 representative golden 확장이 불가함
- 생성물이 draft-only 경계를 넘어 실제 소스 반영처럼 동작해야 한다는 요구
- 비밀값 또는 실데이터를 fixture/golden에 넣어야 하는 요구
