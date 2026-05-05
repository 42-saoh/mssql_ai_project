# packages/analysis

Stored Procedure 분석의 fixture-first 구현을 둔다.

현재 제공 범위:

- procedure signature / parameter parser
- table, view, function, nested procedure call, call graph extraction
- transaction, TRY/CATCH, dynamic SQL, temp table, cursor, multi-result-set detector
- static result-set hint extraction
- business-rule summary, confidence, TODO, review marker, evidence assessment
- schema-search fixture enrichment
- `CanonicalAnalysisModel` compatible local candidate export

Reconciliation notes:

- Dynamic SQL 내부 의존성은 확정하지 않고 `REVIEW_REQUIRED` 로 낮춘다.
- CTE 내부 SELECT 는 client-visible result set 으로 보지 않고, CTE alias 는 table
  dependency 로 보고하지 않는다.
- PPM selected SP fixture 는 metadata-only evidence 만 유지한다. Procedure definition
  text, row data, procedure execution evidence 는 fixture 에 넣지 않는다.
- Full `CanonicalAnalysisModel` 확장은 `packages/domain/**` 변경이 필요하므로
  이 패키지에서는 `DOMAIN_CONTRACT_MISSING` blocker 로 보고한다.
