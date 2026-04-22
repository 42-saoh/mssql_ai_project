# requirements/lock

이 디렉터리는 병렬 Codex worker 가 같은 Python 기준선으로 설치/테스트하도록 하는 잠금 자산을 둔다.

현재 기준:
- `py311-dev.txt` — Python 3.11 계열 로컬 개발/도커 테스트 공용 제약 파일

운영 원칙:
- `make setup` 와 `make test` 는 `scripts/install_python_locked.sh` 를 통해 이 파일을 사용한다.
- 의존성 범위를 바꾸면 먼저 코디네이터가 잠금 파일을 갱신하고, 그 뒤 worker 를 띄운다.
- Web 쪽은 별도의 `pnpm-lock.yaml` 을 coordinator 가 한 번 생성·커밋해서 공유한다.
