---
name: java-mybatis-draft-validator
description: Validate Java/MyBatis DTO, Service, Mapper interface, and MapperXML draft artifacts for P42. Use when Codex needs to check non-empty content, multi-DTO separation, Service/Mapper/XML DTO references, forbidden raw SP or row data text, procedure execution claims, REVIEW_REQUIRED coverage, or ManageBondDTO collapse blockers.
---

# Java/MyBatis Draft Validator

## Workflow

1. Identify expected artifact files and roles from the relevant contract or fixture.
2. Check file inventory:
   - multiple branch/use-case `DTO_DRAFT` files for complex SPs
   - exactly one `SERVICE_DRAFT`
   - exactly one `MAPPER_INTERFACE`
   - exactly one `MAPPER_XML`
3. Check content quality:
   - no blank or placeholder-only files
   - no `OperationModelReviewRequired*`
   - no single `ManageBondDTO` collapse for ManageBond
   - Service, Mapper interface, and Mapper XML reference the required DTO classes
4. Check policy markers:
   - uncertain facts are marked `REVIEW_REQUIRED`
   - generated content does not claim production readiness, deployment, source apply, or automatic conversion
5. Report blockers separately from review-required caveats.

## Blockers

- Empty or nearly empty Java/XML content.
- Missing required DTO files.
- Single DTO collapse for branch-heavy SPs.
- Fallback classes such as `OperationModelReviewRequired`.
- Raw SP dump, raw guide body, raw prompt/provider response, row data, secrets, or executable business SQL.
- Procedure execution, row-data query, deploy, publish, DDL/DML apply, or source apply language.

## ManageBond Minimum Checks

- Required DTOs include `ManageBondSearchCriteria`, `ManageBondSearchRow`, `ApproveAdvanceBondCommand`, `ApproveDefectBondCommand`, `FinanceTransferCommand`, `CreateBondCommand`, `CreateRetentionBondBatchItem`, `UpdateBondCommand`, `DeleteBondCommand`, `VendorBondUpdateCommand`, and `OnlineBondUpdateCommand`.
- Required methods include read, approve, finance transfer, create, retention batch, update, delete, vendor update, and online update use cases.
- Cross-DB write, called procedure I/O, TVF/procedure uncertainty, and transaction boundary gaps remain `REVIEW_REQUIRED`.
