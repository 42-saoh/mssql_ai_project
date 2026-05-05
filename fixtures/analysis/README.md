# fixtures/analysis

Stable expected outputs for fixture-first SP analysis tests.

- `expected_sp_analysis_core_v1.json` captures the required fields for the initial parser,
  dependency, detector, result-set hint, confidence/TODO, and schema-search enrichment slice.
- `sp_complex_patterns_v1.sql` is a synthetic SP fixture covering cursor, nested procedure
  calls, function references, view-reference review, and multiple result sets.
- `ppm_selected_sp_evidence_v1.yaml` records metadata-only PPM simple/medium/complex SP
  identities from the pilot manifest without SQL definition text or row data.
- Dynamic SQL dependencies are intentionally marked `REVIEW_REQUIRED`; the static parser does
  not assert generated SQL internals.
