# docker/test

이 디렉터리는 저장소 기본 검증에 사용할 도커 테스트 러너를 둔다.

원칙:
- 테스트 컨테이너는 애플리케이션 코드 검증만 담당한다.
- 플랫폼 DB / 메타데이터 소스 DB 의 기동/중지는 여기서 관리하지 않는다.
- 외부 DB 가 필요한 경우 연결 정보만 환경변수로 주입한다.

현재 서비스:
- `python-test` — `make test` 가 사용하는 pytest 러너
- `web-test` — `make test-web-smoke` 가 사용하는 web build smoke 러너

병렬 Codex worker 운영 규칙:
- 각 worktree 는 서로 다른 `COMPOSE_PROJECT_NAME` 으로 실행한다.
- 루트 `Makefile` 은 `scripts/compose_project_name.sh` 로 현재 worktree 기준 프로젝트 이름을 계산한다.
- `WORKTREE_PATH` 환경변수로 현재 worktree 루트를 주입하므로 build context 와 bind mount 도 worktree 별로 분리된다.
- 캐시 volume 과 네트워크는 compose project 단위로 분리되므로, 여러 branch/worktree 가 같은 서비스명을 써도 충돌을 줄일 수 있다.

권장 명령:
- `make docker-project-name` — 현재 worktree 에 대응하는 compose project name 확인
- `make test-build` — 현재 worktree 용 테스트 러너 이미지 빌드
- `make test` — 현재 worktree 용 python 테스트 실행
- `make test-web-smoke` — 현재 worktree 용 web smoke 실행
- `make test-shell` — python 테스트 러너 쉘 진입
- `make test-web-shell` — web 테스트 러너 쉘 진입
- `make test-down` — 현재 worktree compose 리소스 정리
- `make test-reset` — 현재 worktree compose 리소스와 cache volume 정리

운영 팁:
- 병렬 worker 는 반드시 각자 worktree 루트에서 `make` 명령을 실행한다.
- 코디네이터가 다른 worktree 를 대신 검증해야 하면 `WORKTREE_PATH=/abs/path/to/worktree make test` 처럼 경로를 명시할 수 있다.
- `TEST_COMPOSE_PROJECT_PREFIX` 를 바꾸면 compose project prefix 를 팀 규칙에 맞게 맞출 수 있다.
