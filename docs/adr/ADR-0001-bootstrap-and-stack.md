# ADR-0001 — 스타터 레포와 초기 스택

## 상태
Accepted

## 배경
프로젝트는 MSSQL SP 분석·문서화, 메타데이터 탐색, Java/MyBatis 코드 초안 생성, 검증/승인을 지원해야 한다.
초기 단계에서는 작은 슬라이스로 빠르게 구현 가능한 구조가 필요하다.

## 결정
- 루트는 Codex-friendly monorepo 로 시작한다.
- `apps/api` 는 FastAPI 로 시작한다.
- `apps/web` 는 Next.js 로 시작한다.
- `services/mssql-mcp` 는 Python 기반 read-only metadata service skeleton 으로 시작한다.
- 계약은 `spec/` 와 `db/schema/` 아래에 저장한다.
- 문서와 정책은 저장소 루트 문서로 버전 관리한다.

## 결과
- 빠른 부트스트랩과 로컬 개발 시작이 쉬워진다.
- 스택 확정 전에도 구조와 계약을 먼저 고정할 수 있다.
- 구현이 커지면 세부 패키지 분리가 필요하다.

## 추가 메모
- 기본 자동 검증 경로는 도커 테스트 러너를 사용한다.
- 플랫폼 DB 와 metadata source DB 는 외부 환경에서 관리하며, 저장소가 local DB lifecycle 을 소유하지 않는다.

