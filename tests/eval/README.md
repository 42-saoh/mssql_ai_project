이 디렉터리는 fixture/rubric 기반 eval 검증을 둔다. active 진입점은 P번호별 명령이 아니라 consolidated gate 다.

## Active Gate

```bash
make test-quality
```

`make test-quality` 는 `tests/suites.yaml` 의 `@quality` alias 를 실행한다. 명령 레벨에서 `P15_HARD_LIVE_GATE`, `P21_LIVE_PORTAL_GATE`, `P27_HARD_LIVE_GATE`, `P32_LIVE_CONFIDENCE_GATE`, `P35_KNOWLEDGE_LIVE_GATE`, `AUTH_RBAC_LIVE_GATE`, `LLM_LIVE_GATE`, `LLM_ENABLE_REMOTE`, `LLM_ALLOW_SP_TEXT`, `MSSQL_ENABLE_LIVE_METADATA` 를 모두 0 으로 고정하므로 live DB, OpenAI, P-GPT, IdP/JWKS 를 호출하지 않는다.

## Explicit Live Confidence

```bash
make test-live-confidence
```

이 명령은 `@live-confidence` alias 를 실행하는 명시적 live confidence 진입점이다. 승인된 환경에서 필요한 gate flag, `OPENAI_API_KEY`, PLF `PLATFORM_DB_*`, read-only PPM metadata, 수동 적용된 DDL, 선택적으로 approved test IdP/JWKS token 을 준비한 경우에만 실행한다. 성공해도 confidence evidence 일 뿐 production readiness, publish/deploy approval, automatic conversion approval 로 해석하지 않는다.

## History

P15~P35 세부 명령과 해석 이력은 `docs/test-gate-history.md` 에 보존한다. 개별 eval 파일과 fixture 는 evidence asset 이므로 삭제하지 않는다.

## Boundaries

- PPM 이 없거나 접근 불가하면 PLF 로 대체하지 않는다.
- eval fixture 는 synthetic/sanitized 데이터만 포함한다.
- raw prompt, raw SP definition, raw provider response, row data, secret 은 test output/report/storage payload 에 저장하지 않는다.
- DB lifecycle, DDL apply, procedure execution, row-data query 는 테스트 명령이 수행하지 않는다.
