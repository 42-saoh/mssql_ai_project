# PARALLEL_RUNBOOK.md

## 1. 준비

- 메인 브랜치를 최신으로 맞춘다.
- 작업 전 루트 저장소가 깨끗한지 확인한다.
- Codex는 같은 파일을 동시에 수정하지 않도록 운영한다.
- 병렬 worker는 각자 **별도 worktree** 에서 실행한다.
- 현재 기준 자산은 OpenAPI skeleton, Platform DB DDL draft, MCP catalog, validation rules, policy files, `.env.example`, `pnpm-lock.yaml`, Python lockfile 이다.

## 2. 권장 디렉터리 구조

```text
repo/                     # 메인 체크아웃 (코디네이터)
../wt/p00-baseline
../wt/p01-mssql-mcp
../wt/p02-domain-analysis
../wt/p03-generation-validation
../wt/p04-web-shell
../wt/p05-api-workflow
../wt/p06-integration-eval
../wt/p07-final-review
```

## 3. worktree 생성 예시

```bash
git switch main
git pull --ff-only
mkdir -p ../wt

git worktree add ../wt/p00-baseline -b feat/p00-baseline
git worktree add ../wt/p01-mssql-mcp -b feat/p01-mssql-mcp
git worktree add ../wt/p02-domain-analysis -b feat/p02-domain-analysis
git worktree add ../wt/p03-generation-validation -b feat/p03-generation-validation
git worktree add ../wt/p04-web-shell -b feat/p04-web-shell
git worktree add ../wt/p05-api-workflow -b feat/p05-api-workflow
git worktree add ../wt/p06-integration-eval -b feat/p06-integration-eval
git worktree add ../wt/p07-final-review -b feat/p07-final-review
```

## 4. 사전 고정 작업

병렬 worker 를 띄우기 전에 coordinator 가 아래를 한 번 확인한다.

```bash
git status --short
corepack enable
corepack use pnpm@10.33.0
pnpm install --frozen-lockfile
cp .env.example .env        # 로컬 전용. 비밀값을 채운 뒤 커밋하지 않는다.
make docker-project-name
make dev-ports
make test-build
python -m compileall apps services packages tests
```

- 호스트에 `python` alias 가 없으면 `python3 -m compileall apps services packages tests` 로 같은 compile-only 검증을 수행한다.
- `pnpm-lock.yaml` 은 현재 기준 저장소에 존재한다. coordinator 는 잠금 파일을 임의 재생성하지 말고 필요 시 명시적인 dependency 변경 작업에서만 갱신한다.
- Python 의존성은 `requirements/lock/py311-dev.txt` 와 `scripts/install_python_locked.sh` 기준으로 맞춘다.
- `.env.example` 은 비밀값 없는 샘플이다. 실제 credential 은 `.env`, `.env.local`, OS keychain 등 저장소 밖/비커밋 경로에 둔다.
- 로컬 Docker MSSQL 을 붙일 때는 `.env` 를 만들고 `PLATFORM_DB_*`, `MSSQL_METADATA_*` 를 채운다.
- metadata profile registry 는 `config/mssql/local_docker_profiles.yaml` 을 공유 기준으로 사용한다.
- 기본 metadata profile id 는 `master`, platform profile id 는 `plf`(`PLF`), pilot analysis target profile id 는 `ppm`(`PPM`) 이다. 같은 SQL Server 인스턴스의 DB는 profile 로 분리한다. PPM 이 없거나 접근 불가하면 PLF로 대체하지 않고 blocker 로 보고한다.
- host-run 은 `127.0.0.1`, `docker/test` 내부 연결은 `host.docker.internal` 기본값을 사용한다.
- Docker 기반 테스트와 smoke 명령은 worktree 루트의 `.env` 가 있으면 `docker compose --env-file .env` 와 동등하게 주입한다. 외부 PLF/PPM live 검증을 직접 `docker compose` 로 실행할 때도 `--env-file .env` 를 명시해 false `LIVE_METADATA_UNAVAILABLE` blocker 를 피한다.
- `.env.example` 이 있더라도 새 작업의 기본 복사 원본은 비밀값 없는 `.env.example` 로 둔다.

## 5. Codex 세션 배치

### 코디네이터 세션
- 위치: 메인 체크아웃 또는 `../wt/p00-baseline`
- 권장 프로필: `safe-explore` → 필요 시 `dev-edit`
- 시작 프롬프트: `prompts/00_coordinator_baseline.md`

### Worker 세션
- 각 worktree마다 별도 터미널에서 실행
- 권장 프로필: `dev-edit`
- 각 세션에 해당 prompt 파일 내용을 입력
- 각 prompt 의 첫 응답에는 수정 예정 파일, 예상 검증 명령, blocker 후보가 포함되어야 한다.

예시:

```bash
cd ../wt/p01-mssql-mcp
codex --profile dev-edit
# prompts/01_mssql_mcp.md 내용을 붙여 넣기
```

## 6. 도커 격리 규칙

- 각 worktree 는 `Makefile` 이 자동 계산한 `COMPOSE_PROJECT_NAME` 으로 테스트를 수행한다.
- 현재 worktree 에서 `make docker-project-name` 을 실행하면 적용될 compose project name 을 바로 확인할 수 있다.
- `make test`, `make test-web-smoke`, `make test-build` 는 현재 worktree 경로를 `WORKTREE_PATH` 로 주입하므로 bind mount 와 build context 도 worktree 별로 분리된다.
- `make test`, `make test-web-smoke`, `make test-build`, `make test-shell`, `make test-web-shell`, `make test-down`, `make test-reset` 는 `.env` 가 있으면 Docker Compose env-file 로 함께 넘긴다. `.env` 가 없으면 비밀값 없는 기본값으로 fixture-first 테스트를 수행한다.
- 캐시 volume / 네트워크 / 컨테이너 이름은 compose project 단위로 묶이므로 branch 별 병렬 검증 충돌을 줄일 수 있다.
- 종료 후 정리가 필요하면 `make test-down`, 캐시까지 초기화하려면 `make test-reset` 을 사용한다.
- 코디네이터가 다른 worktree 를 대신 검증해야 할 때만 `WORKTREE_PATH=/abs/path/to/worktree make test` 형태의 명시적 override 를 사용한다.

## 7. 호스트 포트 전략

- `make dev-ports` 는 현재 worktree 기준 `APP_PORT`, `MCP_PORT`, `WEB_PORT` 를 출력한다.
- 기본 규칙은 `pNN-*` worktree 가 `8000+NN / 8100+NN / 3000+NN` 을 쓰는 방식이다.
- 예: `p01-mssql-mcp -> 8001 / 8101 / 3001`, `p04-web-shell -> 8004 / 8104 / 3004`.
- `pNN-*` 형식이 아닌 worktree 는 경로 기반 hash slot 을 써서 충돌 가능성을 낮춘다.
- 슬롯을 사람이 고정하고 싶으면 `WORKTREE_PORT_SLOT=21 make dev-ports` 처럼 override 한다.
- API/MCP/Web worker 는 하드코딩된 8000/8100/3000 을 전제로 하지 말고 `make run-api`, `make run-mcp`, `make run-web` 를 사용한다.
- `.env.example` 의 `APP_PORT`, `MCP_PORT`, `WEB_PORT` 는 비워 두는 것이 기본이다. 그래야 Makefile 이 worktree 기준 포트를 계산한다.
- `.env.example` 의 password/token 값도 비워 둔다. worker 는 실제 credential 을 공유 계약 파일에 기록하지 않는다.

## 8. 운영 규칙

- 한 worktree에 한 개의 쓰기 세션만 둔다.
- worker는 자신의 `Target Paths` 바깥을 수정하지 않는다.
- block 되면 임의 확장 대신 코디네이터에게 blocker를 올린다.
- merge 전에는 각 worker가 자기 worktree 안에서 자체 검증을 완료한다.
- 공유 계약(`packages/domain`, `spec/openapi`, `db/schema`, `spec/policy`, 루트 문서)은 P00 이후 읽기 전용 기준선으로 취급한다.

## 9. 권장 검증 순서

- 가장 좁은 단위 테스트
- 해당 서비스/패키지 전용 contract 또는 integration 테스트
- 마지막에 필요한 최소 smoke test

예시:

```bash
make test PYTEST_ARGS="tests/unit/analysis"
make test PYTEST_ARGS="tests/contract/mcp tests/unit/mcp"
make test PYTEST_ARGS="tests/integration/api tests/unit/api"
make test-web-smoke
```

## 10. 병합 절차

1. worker 종료 보고 확인
2. 해당 worktree에서 테스트 재실행
3. diff 리뷰
4. 메인 통합 브랜치에 순차 병합
5. 병합 직후 `P07` 최종 리뷰 수행

## 11. 충돌 처리 원칙

- 코드 충돌보다 **계약 충돌**을 먼저 해결한다.
- `packages/domain`, `spec/openapi`, `db/schema`, 루트 문서는 코디네이터가 소유한다.
- `spec/mcp` 는 P01 이 소유하되 OpenAPI/API 경계 변경이 필요하면 코디네이터에게 blocker 로 올린다.
- worker가 공유 계약 변경이 필요하다고 보고하면, 코디네이터가 별도 작은 패치로 먼저 반영하고 다시 병렬 작업을 이어간다.

## 12. 금지 사항

- 실제 데이터 조회/수정
- 자동 DDL 실행
- 무검증 상태 머지
- 다른 track 소유 경로 수정
- 파괴적 git 명령 사용
- secret 을 문서, fixture, 로그, `.env.example` 에 기록

## 추가 검증 규칙

- 가능한 기본 검증은 `make test` 와 `make test-web-smoke` 를 사용한다.
- 외부 DB 가 필요한 경우 각 worktree 에 환경변수만 주입하고, 저장소 차원의 DB up/down 절차는 만들지 않는다.
- Web 테스트는 `pnpm-lock.yaml` 이 커밋된 상태를 기본으로 삼고, 잠금 없는 설치는 예외 상황에서만 허용한다.


## 13. P07 이후 Productization Wave 운영

P00~P07은 starter/MVP 통합을 위한 기존 기준선으로 유지한다. P08A~P16은 같은 worktree/Docker/read-only metadata/draft-only/approval-gated 철학을 유지하면서 productization target으로 전환하는 후속 wave다.

### DB 역할 기준

- `PLF`: platform DB. workflow/artifact/approval/audit 저장소 기준이다.
- `PPM`: pilot analysis target DB. 대표 SP/Table/View/Function 후보 선정 및 이후 eval/demo/golden 후보 기준이다.
- `PPM`이 같은 로컬 MSSQL 인스턴스에 없거나 접근 권한이 없으면 PLF로 대체하지 않는다. `PPM_DB_NOT_FOUND`, `PPM_DB_ACCESS_DENIED`, `LIVE_METADATA_UNAVAILABLE` 등 blocker로 보고한다.
- `config/mssql/local_docker_profiles.yaml` 의 `ppm -> PPM`, `plf -> PLF`, `master -> master` profile 구분을 사용한다.

### Productization worktree 예시

```bash
git worktree add ../wt/p08a-ppm-pilot-object-selection -b feat/p08a-ppm-pilot-object-selection
git worktree add ../wt/p08-product-architecture-backlog -b feat/p08-product-architecture-backlog
git worktree add ../wt/p09-api-workflow-productization -b feat/p09-api-workflow-productization
git worktree add ../wt/p10-mssql-mcp-productization -b feat/p10-mssql-mcp-productization
git worktree add ../wt/p11-sp-analysis-evidence -b feat/p11-sp-analysis-evidence
git worktree add ../wt/p12-java-mybatis-generation-factory -b feat/p12-java-mybatis-generation-factory
git worktree add ../wt/p13-validation-approval-audit -b feat/p13-validation-approval-audit
git worktree add ../wt/p14-web-product-ui -b feat/p14-web-product-ui
git worktree add ../wt/p15-eval-observability-security-ops -b feat/p15-eval-observability-security-ops
git worktree add ../wt/p16-pilot-release-readiness -b feat/p16-pilot-release-readiness
```

### Productization 실행 순서

1. `P08A` — PPM pilot object selection. live metadata에 필요한 surface가 부족하면 P10 전체가 아니라 P08A 내부에서 최소 metadata discovery surface만 선행 보강한 뒤 선정한다. 그래도 불가하면 template-only와 blocker 기록.
2. `P08` — product architecture, release backlog, acceptance criteria.
3. `P09`~`P12` — API/MCP/analysis/generation productization 병렬 또는 의존성 순차 구현. P10은 P08A의 최소 discovery surface를 product-level MCP로 확장·경화한다.
4. `P13`~`P15` — validation/approval/audit, Web UI, eval/observability/security/ops 고도화.
5. `P16` — pilot release readiness, handoff package, go/no-go 판정.

### Productization 공통 규칙

- `fixtures/pilot/ppm_object_selection_v1/selected_objects.yaml` 은 P08A 이후 worker가 공통으로 읽는 pilot 기준이다.
- selected object manifest가 `selection_mode: template_only`이면 worker는 실제 object 이름을 임의 생성하지 않는다.
- shared contract/policy/common 파일(`packages/domain`, `spec/openapi`, `spec/policy`, `db/schema`, 루트 정책 문서 등) 변경이 필요하면 worker가 직접 수정하지 않고 coordinator에게 blocker로 보고한다.
- Java/MyBatis 생성물은 계속 draft-only이며 사람이 최종 검토/승인한다.
- metadata-only 경계는 유지한다. 실제 row data 조회, procedure 실행, 자동 DDL, 운영 DB 직접 변경은 금지한다.
