---
name: sp-business-logic-migration-eval
description: Evaluate complex stored procedure migration outputs against MIGRATION_GUIDE.md-style business logic expectations. Use when Codex needs to compare generated Java/MyBatis or operation artifacts with CRUDFlag, BondKindCode, GUBUNFlag, SValue, DTO/method responsibility mapping, REVIEW_REQUIRED markers, and PCO_GU_ManageBond_PRC quality targets.
---

# SP Business Logic Migration Eval

## Workflow

1. Identify the reference guide or sanitized fixture used as the quality target.
2. Extract business branches and branch variables from sanitized evidence:
   - `CRUDFlag`
   - `BondKindCode`
   - `GUBUNFlag`
   - `SValue`
3. Map each branch to expected responsibilities:
   - query criteria/result DTOs
   - command, batch item, and call request DTOs
   - Service methods
   - Mapper interface methods
   - Mapper XML statement ids
4. Compare generated artifacts with the expected map.
5. Report missing branches, collapsed DTOs, overclaimed facts, and missing `REVIEW_REQUIRED` markers.

## Guardrails

- Use `MIGRATION_GUIDE.md` as a quality reference only; do not copy raw guide body into fixtures or artifacts.
- Do not store raw SP text, raw prompt text, raw provider response, row data, or secrets.
- Do not run procedure execution, row-data queries, DDL/DML apply, deploy, publish, or source apply.
- LLM-inferred facts are draft-only unless backed by deterministic evidence.

## Default ManageBond Target

- Default target: `PPM.dbo.PCO_GU_ManageBond_PRC`.
- Use ManageBond as a benchmark quality target only, not as a production-runtime answer key or hardcoded generator branch.
- Required branches: `R`, `A`, `C`, `U`, `D`, `VENDOR_U`, `ONLINE_U`.
- Required uncertainty markers include cross-DB write, called procedure I/O, TVF/procedure kind, result-shape variants, and transaction boundaries.
- A passing draft must show business flow in separate DTOs and branch/use-case methods, not in one merged DTO.
