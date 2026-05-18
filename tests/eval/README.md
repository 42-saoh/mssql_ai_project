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
replays `PCO_GU_ManageBond_PRC` when `P42_LIVE_REPLAY_GATE=1`.
`P42_LIVE_REPLAY_MODE=sanitized_fixture` uses sanitized fixture facts without live
PPM metadata or raw SP external export. `P42_LIVE_REPLAY_MODE=live_ppm` uses live
read-only PPM metadata and remains explicit confidence evidence only. The live
gate treats the ManageBond DTO list as benchmark metrics, not exact runtime
answer keys: additional split DTOs are allowed when the generated
Service/Mapper/XML wiring and P42 validator pass.

P43 adds `test_p43_framework_adapter_replay.py` for framework-adoption readiness. It compares
the baseline internal gateway adapter and fake candidate adapters with the same generic
inventory contract, reconstructs persisted ManageBond draft artifacts into
`AiJavaMyBatisDraftPack.v0.1`, reruns the P42 static validator, and verifies a synthetic
complex-SP guard so candidate success is not ManageBond-specific. P43F records the decision as
`pilot` with `production_ready: false` and the current Responses/httpx gateway as rollback.

P44 adds `test_p44_framework_runtime_replay.py` for actual framework runtime adoption. It runs
mocked OpenAI Agents SDK output through the real `OpenAIAgentsFrameworkAdapter` and actual
LangGraph stage graph, then reruns the same P42 static validator on ManageBond and a synthetic
complex SP. P44 keeps generated artifacts `production_ready: false`, uses ManageBond as a
benchmark only, and still forbids procedure execution, row data access, source apply, deploy, raw
prompt/provider response storage, raw SP/guide storage, and LangGraph checkpoint persistence.

P45 adds `test_p45_openai_agents_live_gate.py` as an optional live confidence gate. It skips by
default and runs only with `P44_OPENAI_AGENTS_LIVE_GATE=1`, OpenAI remote env, and OpenAI Agents
trace redaction locks. The live gate requires an official OpenAI Agents endpoint
(`OPENAI_BASE_URL` empty or `https://api.openai.com/v1`); custom/P-GPT-compatible
endpoints are blocked as unverified Agents SDK evidence. P46 records the rollback
decision: OpenAI stays on OpenAI Agents SDK plus LangGraph, while
`responses_httpx` remains only for P-GPT and emergency rollback.

P47 adds `test_p47_generic_ai_draft_quality_uplift_assets.py` as the contract/static evidence gate
for generic AI Draft Pack quality. It checks `DraftPackEvidenceBundle.v0.1`, coverage matrices,
the `openai_ai_draft_pack` model profile, and live-probe reporting that treats ManageBond DTO names
as benchmark metrics rather than generic pass/fail gates. P47 also verifies the
generic DTO reference guard for successful draft outputs, so Service/Mapper/XML
DTO responsibility wiring is enforced without ManageBond-specific hardcoding.

Passing fixture-first evals does not imply production readiness, publish/deploy approval,
automatic conversion approval, DDL apply, row-data access, or procedure execution.
