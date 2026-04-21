# ADR-0003 — 산출물은 Draft → Validate → Review → Approve → Publish 흐름을 따른다

## 상태
Accepted

## 결정
모든 산출물은 아래 상태 전이를 따른다.

- DRAFT
- VALIDATED
- REVIEW_PENDING
- APPROVED / REJECTED
- PUBLISHED

publish 전에 validation report 와 approval record 가 필요하다.

## 이유
- 무검증 자동 반영을 금지한다.
- 결과 신뢰성과 추적성을 확보한다.
- 사용자 승인 기반 확정을 구조적으로 강제한다.
