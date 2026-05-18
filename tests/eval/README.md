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
workflow/API replay tests. Fixture-first tests check the required ManageBond DTO inventory, while
live replay treats that inventory as a benchmark minimum and allows additional split DTOs. Both
paths enforce single Service/Mapper/XML file expectations, fallback skeleton blockers,
DTO-collapse blockers, `REVIEW_REQUIRED` uncertainty markers, storage safety, and that persisted
artifacts can be reconstructed into a valid `AiJavaMyBatisDraftPack.v0.1` payload.

P42H keeps ManageBond as the benchmark fixture while requiring workflow inventory derivation to
stay generic. The runtime contract computes expected DTO and method inventory from operation
contracts, DTO blueprints, statement evidence, and branch responsibilities. Complex SPs that
collapse to two DTOs or leave write/call responsibilities without command-style DTOs fail with
`P42_INVENTORY_CONTRACT_INCOMPLETE` instead of accepting a weak draft.

P42G adds `test_p42_live_ai_draft_pack_replay_gate.py` as an optional live confidence gate.
It is disabled by default, fails before live access when required env is missing, and only
replays `PCO_GU_ManageBond_PRC` with live read-only PPM metadata and the remote
OpenAI-compatible gateway when `P42_LIVE_REPLAY_GATE=1`. The live gate treats the
ManageBond DTO list as a minimum benchmark count, not an exact runtime answer key: additional
split DTOs are allowed when the generated Service/Mapper/XML wiring and P42 validator pass.

Passing fixture-first evals does not imply production readiness, publish/deploy approval,
automatic conversion approval, DDL apply, row-data access, or procedure execution.
