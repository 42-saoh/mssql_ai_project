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
- web portal 은 mock adapter 기반 shell 이며 API/BFF HTTP 연결 smoke 는 follow-up 이다.
- 기본 metadata profile 은 `master` 이고, sample fixture target 은 `dbo.usp_GetOrderSummary` 이다.
- P16 기준 PPM 대표 object identity 는 `live_metadata` manifest 에서 온 것이지만, live pilot release 는 아직 NO-GO 다.

## 주의
- 결과는 초안이며 검토가 필요하다.
- 실제 데이터 조회 기능은 제공하지 않는다.
- DDL/배포는 자동 실행되지 않는다.
- publish endpoint 는 아직 제공하지 않는다.
- live MSSQL 연결은 optional readiness/probe 성격이며, 기본 검증은 fixture-first 로 동작한다.

## 테스트와 검증

- 요청 결과 확인에 앞서 저장소 차원의 자동 검증은 도커 테스트 러너를 통해 수행한다.
- 최소 통합/eval 검증은 `make test PYTEST_ARGS="tests/e2e tests/eval"` 이다.
- UI smoke 가 필요한 경우 로컬/승인된 dev URL 에 대해서만 Playwright MCP 를 사용한다.

## P15 live eval 주의

운영 준비도 검증에서는 PPM live metadata gate 가 켜질 수 있다. 이 경우 `dbProfileId=ppm` 이 `PPM` 에 read-only metadata 로 연결되어야 하며, PPM 이 없거나 권한이 없으면 테스트는 실패한다. 실패 시 PLF 로 대체하지 않고 blocker 로 보고한다.

P15 보고서/로그에서 확인해야 하는 항목은 correlation id, evidence coverage, review-required 비율, validation 상태, draft artifact completeness, latency budget, audit stage, redaction 상태다. raw definition text, row data, credential 은 화면/로그/fixture 에 포함하지 않는다.

## P16 readiness 결과 해석

- `docs/pilot-release-readiness.md` 는 현재 live pilot release 를 NO-GO 로 판정한다.
- fixture-first/demo handoff 는 GO WITH LIMITATIONS 이며, 결과물은 계속 draft-only 이다.
- `DEPENDENCY_METADATA_INCOMPLETE` 가 남아 있으므로 SP 와 table 사이의 확정 dependency 로 해석하면 안 된다.
- 승인 화면이나 API decision 기록은 publish, 배포, DDL 적용을 수행하지 않는다.
- live pilot release 후보는 passed validation 과 human `APPROVE` 가 audit context 와 함께 남은 뒤 다시 검토해야 한다.
