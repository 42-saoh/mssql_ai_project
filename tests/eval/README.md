# tests/eval

Fixture/rubric-based eval tests live here. The consolidated quality gate is still `make test-quality`
when the dockerized test interface is available.

P36 adds `test_p36_output_renewal_quality.py` for the output-renewal contract. It checks the six
final artifact types, migration-guide SP analysis document, evidence dossier dependency report,
bounded sanitized SQL statement evidence, and evidence-backed Java/MyBatis drafts.

P40 adds `test_p40_metadata_design_natural_language_chat.py` for the natural-language metadata
design chat contract. It checks sanitized interpreted intent, applied changes, new-design and
refine flows, metadata evidence, table script previews, DTO previews, and no retired artifact
revival.

P41 adds `test_p41_sp_operation_model.py` for the SP operation-model renewal groundwork. It checks
the `PCO_GU_ManageBond_PRC` fixture, branch-level operation coverage, multi-DTO blueprint
expectations, `REVIEW_REQUIRED` markers, storage safety, and the current single-DTO renderer gap.

P42 adds `test_p42_manage_bond_ai_draft_quality.py` for AI Draft Pack quality and pairs it with
workflow/API replay tests. It checks the required ManageBond DTO inventory, single
Service/Mapper/XML file expectations, fallback skeleton blockers, DTO-collapse blockers,
`REVIEW_REQUIRED` uncertainty markers, storage safety, and that persisted artifacts can be
reconstructed into a valid `AiJavaMyBatisDraftPack.v0.1` payload.

Passing fixture-first evals does not imply production readiness, publish/deploy approval,
automatic conversion approval, DDL apply, row-data access, or procedure execution.
