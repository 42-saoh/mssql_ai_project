# ADR-0004 — DB 는 외부에서 관리하고 스키마 변경은 versioned SQL 로만 반영한다

## 상태
Accepted

## 결정
- 플랫폼 DB 와 metadata source DB 는 저장소 밖의 외부 환경에서 관리한다.
- 저장소는 DB up/down, schema apply, shared DB mutation 을 제공하지 않는다.
- 스키마 변경은 `db/schema/` 아래의 versioned SQL 파일 추가로만 표현한다.
- 실제 DB 반영은 사용자/운영자의 수동 절차로 수행한다.

## 이유
- 범위 밖인 자동 DDL 실행을 구조적으로 차단한다.
- 외부 DB 관리 정책과 저장소 책임을 명확히 분리한다.
- 변경 이력을 코드 리뷰 가능한 형태로 남긴다.
