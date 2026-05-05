이 디렉터리는 fixture/rubric 기반 eval 검증을 둔다. 기본 검증은 도커 테스트 러너를 경유한다.

현재 suite 는 `fixtures/eval/` 의 file-based assets 를 읽어 sample request, canonical candidate, artifact summary, rubric 을 검증하고, fixture-backed workflow 결과와 비교한다.

P15 부터 `eval_observability_security_ops_p15_v1.yaml` 은 hard-live gate 로 동작한다. `MSSQL_ENABLE_LIVE_METADATA=1`, `dbProfileId=ppm`, source database `PPM`, read-only metadata 권한이 없으면 테스트는 skip 이 아니라 failure/blocker 로 보고한다. live PPM eval 은 PLF 로 fallback 하지 않는다.

실행:

```bash
make test PYTEST_ARGS="tests/eval"
```

P15 hard-live 검증을 포함하려면 worktree 의 `.env` 또는 승인된 환경변수에 PPM read-only metadata 연결 정보를 주입한 뒤 같은 명령을 실행한다. fixture-first workflow latency/reproducibility 검증은 계속 synthetic sample 로 수행하지만, P15 suite 전체는 live PPM gate 를 통과해야 한다.
