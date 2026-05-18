---
name: ai-draft-pack-authoring
description: Author and refine AiJavaMyBatisDraftPack.v0.1 outputs for P42 AI Draft Pack work. Use when Codex needs to design file inventory, draft DTO/Service/Mapper/MapperXML content, repair AI draft packs, preserve REVIEW_REQUIRED markers, or block OperationModelReviewRequired fallback skeletons for Java/MyBatis SP conversion.
---

# AI Draft Pack Authoring

## Workflow

1. Read the P42 contract and fixture first:
   - `spec/eval/p42_ai_draft_pack_contract.yaml`
   - `fixtures/eval/ai_draft_pack_p42_manage_bond_v1.yaml`
2. Use only sanitized evidence, branch summaries, DTO names, method names, target refs, and review markers.
3. Design file inventory before writing content:
   - one `DTO_DRAFT` file per query/result/command/batch/call DTO
   - one `SERVICE_DRAFT`
   - one `MAPPER_INTERFACE`
   - one `MAPPER_XML`
4. Draft or repair content so every file has a clear role, operation ids, evidence refs, and `REVIEW_REQUIRED` markers for weak evidence.
5. Block fallback skeletons and DTO collapse before handing output to validators.

## P42 Guardrails

- Do not store raw SP text, raw guide body, raw prompt text, raw provider response, row data, or secrets.
- Do not run procedure execution, row-data queries, DDL/DML apply, deploy, publish, or source apply.
- Treat `OperationModelReviewRequired*`, single `ManageBondDTO`, blank content, and missing DTO references as blockers.
- Keep cross-DB write, called procedure I/O, TVF/procedure uncertainty, result-shape variants, and transaction boundaries as `REVIEW_REQUIRED`.

## Output Checklist

- DTO files remain split by business use case.
- Service, Mapper interface, and Mapper XML stay single-file drafts.
- Method names expose branch/use-case intent.
- Generated SQL snippets are sanitized skeletons only.
- `production_ready` remains false.
