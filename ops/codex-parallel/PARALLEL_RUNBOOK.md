# PARALLEL_RUNBOOK.md

## 1. 준비

- 메인 브랜치를 최신으로 맞춘다.
- 작업 전 루트 저장소가 깨끗한지 확인한다.
- Codex는 같은 파일을 동시에 수정하지 않도록 운영한다.
- 병렬 worker는 각자 **별도 worktree** 에서 실행한다.

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
```

## 4. 사전 고정 작업

병렬 worker 를 띄우기 전에 coordinator 가 아래를 한 번 끝내 둔다.

```bash
corepack enable
corepack use pnpm@10.0.0
pnpm install            # pnpm-lock.yaml 생성 및 커밋
make test-build
make dev-ports
```

- `pnpm-lock.yaml` 은 coordinator 가 한 번 생성하고 commit 해서 모든 worker 가 같은 잠금 파일을 공유하게 한다.
- Python 의존성은 `requirements/lock/py311-dev.txt` 와 `scripts/install_python_locked.sh` 기준으로 맞춘다.
- 로컬 Docker MSSQL 을 붙일 때는 `.env` 를 먼저 만들고 `PLATFORM_DB_*`, `MSSQL_METADATA_*` 를 채운다.
- metadata profile registry 는 `config/mssql/local_docker_profiles.yaml` 을 공유 기준으로 사용한다.
- host-run 은 `127.0.0.1`, `docker/test` 내부 연결은 `host.docker.internal` 기본값을 사용한다.

## 5. Codex 세션 배치

### 코디네이터 세션
- 위치: 메인 체크아웃 또는 `../wt/p00-baseline`
- 권장 프로필: `safe-explore` → 필요 시 `dev-edit`
- 시작 프롬프트: `prompts/00_coordinator_baseline.md`

### Worker 세션
- 각 worktree마다 별도 터미널에서 실행
- 권장 프로필: `dev-edit`
- 각 세션에 해당 prompt 파일 내용을 그대로 입력

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

## 8. 운영 규칙

- 한 worktree에 한 개의 쓰기 세션만 둔다.
- worker는 자신의 `Target Paths` 바깥을 수정하지 않는다.
- block 되면 임의 확장 대신 코디네이터에게 blocker를 올린다.
- merge 전에는 각 worker가 자기 worktree 안에서 자체 검증을 완료한다.

## 9. 권장 검증 순서

- 가장 좁은 단위 테스트
- 해당 서비스/패키지 전용 contract 또는 integration 테스트
- 마지막에 필요한 최소 smoke test

예시:

```bash
pytest tests/unit/analysis -q
pytest tests/contract/mcp -q
pytest tests/integration/api -q
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
- worker가 공유 계약 변경이 필요하다고 보고하면, 코디네이터가 별도 작은 패치로 먼저 반영하고 다시 병렬 작업을 이어간다.

## 12. 금지 사항

- 실제 데이터 조회/수정
- 자동 DDL 실행
- 무검증 상태 머지
- 다른 track 소유 경로 수정
- 파괴적 git 명령 사용

## 추가 검증 규칙

- 가능한 기본 검증은 `make test` 와 `make test-web-smoke` 를 사용한다.
- 외부 DB 가 필요한 경우 각 worktree 에 환경변수만 주입하고, 저장소 차원의 DB up/down 절차는 만들지 않는다.
- Web 테스트는 `pnpm-lock.yaml` 이 커밋된 상태를 기본으로 삼고, 잠금 없는 설치는 예외 상황에서만 허용한다.
