# ADR-0003 — 산출물은 Draft → Validate 를 기본 경로로 하고 Review/Approve/Publish 는 deferred capability 로 유지한다

## 상태
Accepted, amended by P25

## 결정
P25 기본 제품 흐름은 request → metadata → analysis → generation → validation 이후 job 상태
`VALIDATION_COMPLETE` 에서 종료한다. Web review UI 와 기본 smoke/e2e 의 approval decision
호출은 비활성화한다.

산출물 상태 모델은 future/deferred capability 를 위해 아래 값을 유지한다.

- DRAFT
- VALIDATED
- REVIEW_PENDING
- APPROVED / REJECTED
- PUBLISHED

`REVIEW_REQUIRED` validation 결과는 사람 승인 요구가 아니라 근거 부족/분석 불확실성 caveat
이다. 따라서 validation 결과가 `REVIEW_REQUIRED` 여도 기본 산출물 상태는 보통 `DRAFT` 를
유지하며, `REVIEW_PENDING` 으로 자동 전환하지 않는다.

publish/export/deploy 기능은 여전히 deferred 이며, 재활성화 전에는 validation report 와
명시적 approval record 같은 별도 governance 근거가 필요하다.

## 이유
- 무검증 자동 반영을 금지한다.
- 결과 신뢰성과 추적성을 확보한다.
- 사용자 승인 기반 확정 경로는 삭제하지 않고 deferred capability 로 보존한다.
