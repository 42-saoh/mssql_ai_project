# 관리자 가이드 초안

## 관리 대상
- DB profiles
- prompt / template / model versions
- user roles
- approval policy
- audit log

## 기본 운영 절차
1. DB profile 등록
2. model / prompt / template version 등록
3. 운영용 published version 승격
4. user / role 권한 부여
5. validation / approval 운영 점검

## 스키마 변경 운영

- 플랫폼 DB 구조 변경이 필요하면 `db/schema/` 에 versioned SQL 파일을 추가한다.
- 실제 DB 적용은 관리자/운영자가 외부 DB 환경에 수동으로 수행한다.
- 저장소의 Makefile/Codex 작업은 DB apply 를 수행하지 않는다.

