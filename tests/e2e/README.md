이 디렉터리는 request → job → artifact 흐름이 붙은 뒤 e2e 검증을 추가할 자리다.

현재 자동화가 아직 없더라도, e2e 검증이 추가되면 `make test PYTEST_ARGS="tests/e2e"` 형태로 도커 테스트 러너에서 실행한다.
