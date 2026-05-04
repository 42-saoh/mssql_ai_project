이 디렉터리는 request → job → artifact → validation → approval decision recording 흐름을 검증한다.

현재 e2e 기본 경로는 fixture-backed MSSQL MCP metadata 를 사용하며 live MSSQL 을 요구하지 않는다. 기본 sample 은 metadata profile `master`, target `dbo.usp_GetOrderSummary` 이다.

실행:

```bash
make test PYTEST_ARGS="tests/e2e"
```
