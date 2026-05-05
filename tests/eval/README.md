이 디렉터리는 fixture/rubric 기반 eval 검증을 둔다. 기본 검증은 도커 테스트 러너를 경유한다.

현재 suite 는 `fixtures/eval/` 의 file-based assets 를 읽어 sample request, canonical candidate, artifact summary, rubric 을 검증하고, fixture-backed workflow 결과와 비교한다.

P15 부터 `eval_observability_security_ops_p15_v1.yaml` 은 hard-live gate 계약을 정의한다. 기본 `tests/eval` 실행은 fixture-first 재현성을 유지하고 live PPM 을 호출하지 않는다. `P15_HARD_LIVE_GATE=1` 로 명시 실행한 경우에만 live PPM metadata gate 를 활성화하며, 이때 `MSSQL_ENABLE_LIVE_METADATA=1`, `dbProfileId=ppm`, source database `PPM`, read-only metadata 권한이 없으면 skip 이 아니라 failure/blocker 로 보고한다. live PPM eval 은 PLF 로 fallback 하지 않는다.

실행:

```bash
make test PYTEST_ARGS="tests/eval"
```

P15 hard-live 검증을 포함하려면 worktree 의 `.env` 또는 승인된 환경변수에 PPM read-only metadata 연결 정보를 주입한 뒤 아래처럼 명시 플래그를 켠다.

```bash
P15_HARD_LIVE_GATE=1 MSSQL_ENABLE_LIVE_METADATA=1 make test PYTEST_ARGS="tests/e2e tests/eval"
```

fixture-first workflow latency/reproducibility 검증은 계속 synthetic sample 로 수행한다. fixture snapshot 이나 fixture-backed metadata search 를 검증하는 테스트는 필요한 경우 `MSSQL_ENABLE_LIVE_METADATA=0` 을 test 단위에서 고정한다.
