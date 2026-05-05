# docker/test

이 디렉터리는 저장소 기본 검증에 사용할 도커 테스트 러너를 둔다.

## 원칙
- 저장소는 외부 DB 의 lifecycle 을 소유하지 않는다.
- 테스트 컨테이너는 현재 worktree 를 bind mount 해서 사용한다.
- 병렬 Codex worker 는 worktree 별 `COMPOSE_PROJECT_NAME` 으로 격리된다.
- 외부 MSSQL 이 필요할 경우 **연결만** 허용하고, up/down 은 사용자가 관리한다.

## 현재 서비스:
- `python-test` — `make test` 가 사용하는 pytest 러너
- `web-test` — `make test-web-smoke` 가 사용하는 web build smoke 러너

## 병렬 Codex worker 운영 규칙:
- 각 worktree 는 서로 다른 `COMPOSE_PROJECT_NAME` 으로 실행한다.
- 루트 `Makefile` 은 `scripts/compose_project_name.sh` 로 현재 worktree 기준 프로젝트 이름을 계산한다.
- `WORKTREE_PATH` 환경변수로 현재 worktree 루트를 주입하므로 build context 와 bind mount 도 worktree 별로 분리된다.
- 캐시 volume 과 네트워크는 compose project 단위로 분리되므로, 여러 branch/worktree 가 같은 서비스명을 써도 충돌을 줄일 수 있다.

## 재현성 규칙:
- Python 의존성은 `requirements/lock/py311-dev.txt` 제약 파일을 통해 설치한다.
- `make test` 와 `make setup` 은 `scripts/install_python_locked.sh` 를 호출해 같은 Python 잠금 기준을 사용한다.
- Web 의존성은 커밋된 `pnpm-lock.yaml` 을 기준으로 반드시 `--frozen-lockfile` 로 설치한다.
- `web-test` 는 compose volume `/pnpm/store` 를 pnpm store 로 사용해 worktree 안의 `.pnpm-store` 생성을 피한다.
- 잠금 없는 임시 설치가 정말 필요하면 `ALLOW_UNLOCKED_PNPM_INSTALL=1 make test-web-smoke` 로만 예외 실행한다.

## 권장 명령:
- `make docker-project-name` — 현재 worktree 에 대응하는 compose project name 확인
- `make dev-ports` — 현재 worktree 에 대응하는 APP/MCP/WEB 포트 확인
- `make test-build` — 현재 worktree 용 테스트 러너 이미지 빌드
- `make test` — 현재 worktree 용 python 테스트 실행
- `make test-web-smoke` — 현재 worktree 용 web smoke 실행
- `make test-shell` — python 테스트 러너 쉘 진입
- `make test-web-shell` — web 테스트 러너 쉘 진입
- `make test-down` — 현재 worktree compose 리소스 정리
- `make test-reset` — 현재 worktree compose 리소스와 cache volume 정리

## 운영 팁:
- 병렬 worker 는 반드시 각자 worktree 루트에서 `make` 명령을 실행한다.
- 코디네이터가 다른 worktree 를 대신 검증해야 하면 `WORKTREE_PATH=/abs/path/to/worktree make test` 처럼 경로를 명시할 수 있다.
- `TEST_COMPOSE_PROJECT_PREFIX` 를 바꾸면 compose project prefix 를 팀 규칙에 맞게 맞출 수 있다.

## 병렬 실행

- `make test-build`, `make test`, `make test-web-smoke` 는 worktree 별 compose project name 을 사용한다.
- `make docker-project-name` 으로 현재 worktree 의 compose project name 을 확인할 수 있다.
- `make test-down` 은 현재 worktree compose project 만 정리한다.
- `make test-reset` 은 현재 worktree compose project 의 volume 까지 초기화한다.

## 로컬 Docker MSSQL 연결

사용자가 별도로 띄운 SQL Server 컨테이너에 테스트 컨테이너가 붙을 수 있도록 `host.docker.internal` 을 기본 gateway 로 넣어 두었다.

- host-run 값: `.env` 에 `MSSQL_METADATA_HOST=127.0.0.1`, `PLATFORM_DB_HOST=127.0.0.1`
- docker/test 내부 값: `.env` 에 `MSSQL_METADATA_DOCKER_HOST=host.docker.internal`, `PLATFORM_DB_DOCKER_HOST=host.docker.internal`
- 기본 profile registry: `config/mssql/local_docker_profiles.yaml`
- 기본 metadata profile id: `master`
- platform DB profile id: `plf`

live metadata smoke 가 필요하면 `.env` 에서 `MSSQL_ENABLE_LIVE_METADATA=1` 로 켠 뒤 테스트 컨테이너 또는 로컬 `run-mcp` 프로세스에서 readiness endpoint 를 확인한다. live tool query execution 은 아직 optional adapter boundary 이며, 기본 테스트/e2e/eval 은 fixture-first 로 유지한다.

P15 hard-live gate 는 명시 실행할 때만 live PPM 을 호출한다. 기본 `make test` 와 `make test PYTEST_ARGS="tests/e2e tests/eval"` 은 fixture-first 재현성을 유지한다. hard-live gate 를 통과시키려면 `.env` 또는 승인된 환경변수에 아래 조건을 충족해야 한다.

- `P15_HARD_LIVE_GATE=1`
- `MSSQL_ENABLE_LIVE_METADATA=1`
- `MSSQL_METADATA_*` 값은 read-only metadata 접근 가능한 계정을 가리킴
- `MSSQL_METADATA_PROFILE_FILE` 의 `ppm` profile 이 `PPM` 을 가리킴
- docker/test 내부 연결은 `MSSQL_METADATA_DOCKER_HOST` 로 주입됨

PPM 이 없거나 접근 권한이 없으면 PLF 로 대체하지 않는다. 이 실패는 `LIVE_PPM_EVAL_REQUIRED`, `LIVE_METADATA_UNAVAILABLE`, `PPM_DB_NOT_FOUND`, `PPM_DB_ACCESS_DENIED`, `METADATA_READ_ONLY_PERMISSION_INSUFFICIENT` 같은 blocker 로 취급한다.

worktree 포트 전략은 계속 `make dev-ports` 를 기준으로 한다. P15 eval 자체는 API/MCP/Web dev server port 를 점유하지 않지만, 병렬 worker 가 수동 smoke 를 병행할 때는 hard-coded 8000/8100/3000 대신 worktree 별 계산값을 사용한다.

## 예시

```bash
cp .env.example .env
make test-build
make test
make test PYTEST_ARGS="tests/e2e tests/eval"
P15_HARD_LIVE_GATE=1 MSSQL_ENABLE_LIVE_METADATA=1 make test PYTEST_ARGS="tests/e2e tests/eval"
make test-web-smoke
```
