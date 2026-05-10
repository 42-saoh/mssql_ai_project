# 사용자 가이드

## 기본 흐름
1. 분석 또는 생성 요청 등록
2. job 상태 확인
3. draft artifact 미리보기
4. validation report 확인
5. reviewer 승인/반려
6. approval decision 기록 확인

## 현재 사용 가능한 경로

- API happy path 는 fixture-backed metadata 로 request → job → artifact → validation → approval decision recording 까지 검증된다.
- web portal 은 기본적으로 mock adapter 기반 shell 이며, P18B 에서 local API/BFF HTTP 연결 smoke evidence 를 추가했다.
- API validation/approval write action 은 `AUTH_RBAC_ENFORCEMENT=1` 일 때 verified OIDC/JWT actor 와 PLF role membership 이 있는 `REVIEWER` 또는 `ADMIN` 만 수행할 수 있다.
- Live IdP/JWKS 와 운영 PLF role lookup 검증은 future hardening 으로 남아 있으므로, 현재 시스템은 controlled conditional use 로 해석한다.
- 기본 metadata profile 은 `master` 이고, sample fixture target 은 `dbo.usp_GetOrderSummary` 이다.
- P16/P17D 기준 PPM 대표 object identity 는 `live_metadata` manifest 에서 온 것이며, live pilot release 는 scoped draft-only candidate 로만 CONDITIONAL_GO 다.

## 주의
- 결과는 초안이며 검토가 필요하다.
- 실제 데이터 조회 기능은 제공하지 않는다.
- DDL/배포는 자동 실행되지 않는다.
- publish endpoint 는 아직 제공하지 않는다.
- live MSSQL 연결은 optional readiness/probe 성격이며, 기본 검증은 fixture-first 로 동작한다.

## 테스트와 검증

- 요청 결과 확인에 앞서 저장소 차원의 자동 검증은 도커 테스트 러너를 통해 수행한다.
- 최소 통합/eval 검증은 `make test PYTEST_ARGS="tests/e2e tests/eval"` 이다.
- Web HTTP adapter smoke 는 `python3 tests/e2e/web_http_adapter_smoke.py` 로 실행한다.
- UI smoke 가 필요한 경우 로컬/승인된 dev URL 에 대해서만 Playwright MCP 를 사용한다.

## P15 live eval 주의

운영 준비도 검증에서는 명시적으로 PPM live metadata gate 를 켤 수 있다. 기본 검증은 fixture-first 로 동작하고, `P15_HARD_LIVE_GATE=1` 을 켠 경우 `dbProfileId=ppm` 이 `PPM` 에 read-only metadata 로 연결되어야 한다. PPM 이 없거나 권한이 없으면 테스트는 실패한다. 실패 시 PLF 로 대체하지 않고 blocker 로 보고한다.

P15 보고서/로그에서 확인해야 하는 항목은 correlation id, evidence coverage, review-required 비율, validation 상태, draft artifact completeness, latency budget, audit stage, redaction 상태다. raw definition text, row data, credential 은 화면/로그/fixture 에 포함하지 않는다.

## P16/P17/P18 readiness 결과 해석

- `docs/pilot-release-readiness.md` 는 현재 live pilot release 를 scoped CONDITIONAL_GO 로 판정한다.
- fixture-first/demo handoff 는 GO WITH LIMITATIONS 이며, 결과물은 계속 draft-only 이다.
- P17A dependency gate 는 selected SP suite majority 기준으로 통과했지만, SP 와 table 사이의 확정 dependency 는 manifest 의 confirmed `related_procedures` evidence 가 있을 때만 해석한다.
- 승인 화면이나 API decision 기록은 publish, 배포, DDL 적용을 수행하지 않는다.
- P18/P19 productization readiness 는 CanonicalAnalysisModel, web HTTP adapter smoke evidence, production auth/RBAC source 문서화, fixture-backed enforcement 를 기록해 controlled CONDITIONAL_GO 로 해석한다. 단, live IdP/JWKS 와 PLF role lookup 검증 전까지 production-grade enterprise Auth/RBAC 또는 `production_ready: true` 로 주장하지 않는다.
