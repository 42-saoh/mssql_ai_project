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

Passing fixture-first evals does not imply production readiness, publish/deploy approval,
automatic conversion approval, DDL apply, row-data access, or procedure execution.
