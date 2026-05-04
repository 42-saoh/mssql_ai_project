# P14 Web Product UI


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

중앙 통합형 단일 플랫폼 UI를 product demo 수준으로 발전시킨다. SP 분석 요청, metadata search, artifact preview, validation result, approval/review, job status/progress 화면을 mock-first + API adapter 구조로 정리한다.

## 읽어야 할 기준 파일

- `PROJECT.md`, `ARCHITECTURE.md`, `POLICY.md`
- `apps/web/README.md`
- `apps/web/app/**`
- `apps/web/components/**`
- `apps/web/lib/api/**`
- `apps/web/package.json`
- `spec/openapi/ai_agent_platform_openapi_v1.yaml`
- `fixtures/eval/**`
- `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml`
- `.env.example`
- `Makefile`
- `scripts/resolve_dev_ports.sh`

## 허용 수정 경로

- `apps/web/**`
- `tests/unit/web/**`

## 금지 경로

- `apps/api/**`
- `services/**`
- `packages/**`
- `spec/**`
- `db/schema/**`
- `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml`
- lockfile 변경. 신규 dependency가 반드시 필요하면 blocker 보고

## 구현 범위

- request 생성 화면에서 PPM pilot manifest 기반 sample request를 제공하되 template-only이면 실제 object name을 표시하지 않는다.
- metadata search 화면은 API adapter/mock adapter를 분리한다.
- artifact preview에는 draft-only, evidence refs, validation result, review_required/TODO를 명확히 보여준다.
- approval/review 화면은 실제 승인/배포 실행이 아니라 decision preview/recording UI 경계로 둔다.
- job status/progress는 workflow status와 failure/blocker 상태를 표시한다.
- 사용자가 별도 로컬 도구 설치 없이 웹을 통해 사용할 방향으로 정보 구조를 정리한다.

## 검증 명령

- `make test-web-smoke`
- 가능하면 `pnpm --filter @mssql-agent/web lint` 또는 현재 package script 확인 후 실행
- API mock path 변경 시 관련 TypeScript build smoke 확인

## Blocker 보고 기준

- OpenAPI/API contract 변경 없이는 화면 요구를 충족할 수 없음
- 신규 dependency/lockfile 변경이 필요함
- PPM pilot manifest가 template-only라 demo object selector를 실제 이름으로 구성할 수 없음
- approval/publish 액션이 정책 경계를 넘어 실제 배포처럼 동작해야 함
- auth/RBAC 실제 구현이 필요한 범위로 커짐
