# ADR-0002 — MSSQL Metadata MCP는 읽기 전용 경계로 유지한다

## 상태
Accepted

## 결정
- 앱과 생성기는 MSSQL 에 직접 접근하지 않는다.
- 메타데이터 접근은 `services/mssql-mcp` 경계에 집중한다.
- MCP 도구는 정형 파라미터만 받고 자유 SQL surface 를 만들지 않는다.
- row data 조회와 DDL/DML 실행은 범위 밖으로 둔다.

## 이유
- 보안과 범위 통제를 강화한다.
- 사실 수집 경로를 표준화한다.
- 검증 및 재현 가능성을 높인다.
