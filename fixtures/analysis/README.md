# fixtures/analysis

Stable expected outputs for fixture-first SP analysis tests.

- `expected_sp_analysis_core_v1.json` captures the required fields for the initial parser,
  dependency, detector, and schema-search enrichment slice.
- Dynamic SQL dependencies are intentionally marked `REVIEW_REQUIRED`; the static parser does
  not assert generated SQL internals.
