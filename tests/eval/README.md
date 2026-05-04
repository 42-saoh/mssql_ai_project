이 디렉터리는 fixture/rubric 기반 eval 검증을 둔다. 기본 검증은 도커 테스트 러너를 경유한다.

현재 suite 는 `fixtures/eval/` 의 file-based assets 를 읽어 sample request, canonical candidate, artifact summary, rubric 을 검증하고, fixture-backed workflow 결과와 비교한다.

실행:

```bash
make test PYTEST_ARGS="tests/eval"
```
