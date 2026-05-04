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
