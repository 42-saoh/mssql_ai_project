# ADR-0005 — 기본 테스트는 도커 테스트 러너를 통해 수행한다

## 상태
Accepted

## 결정
- 저장소 기본 테스트 명령은 `docker/test/` 의 컨테이너를 통해 실행한다.
- 파이썬 테스트는 `make test` 가 `python-test` 컨테이너를 기동해 수행한다.
- Web 전용 자동 테스트가 자리잡기 전까지 `make test-web-smoke` 로 build smoke 를 수행한다.
- 외부 DB 가 필요한 경우 연결 정보만 주입하고, DB lifecycle 은 별도 환경에서 관리한다.

## 이유
- 호스트 개발 환경 차이를 줄인다.
- Codex 병렬 실행 시 검증 환경을 더 일관되게 만든다.
- 테스트 중에도 local DB lifecycle 에 대한 숨은 의존성을 만들지 않는다.
