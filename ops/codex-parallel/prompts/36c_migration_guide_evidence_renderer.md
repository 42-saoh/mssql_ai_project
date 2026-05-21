# P36C Migration Guide And Evidence Renderer

## Role

template_engineer

## Context

Use `MIGRATION_GUIDE.md` flow and `spec/eval/p36_output_renewal_contract.yaml`.

## Task

Rewrite:

- `SPAnalysisDocumentRenderer` to render the six-section migration guide flow:
  1. SP 개요 (Overview)
  2. 의존성 인벤토리 (Dependency Inventory)
  3. DML 영향도 매트릭스 (Data Change Impact Matrix)
  4. 호출 흐름 (Call Flow)
  5. SP 복잡도 분석 (Complexity Analysis)
  6. Appendix
- `DependencyReportRenderer` to render an evidence dossier covering SP analysis and Java/MyBatis generation evidence.

## Constraints

- SQL evidence must be bounded sanitized statement evidence.
- Do not include full SP definition.
- Mark weak inferences with `REVIEW_REQUIRED`.
- Keep output deterministic.

## Acceptance

- Renderer/eval tests assert required headings, evidence refs, caveats, next evidence, and no full SP body storage.
