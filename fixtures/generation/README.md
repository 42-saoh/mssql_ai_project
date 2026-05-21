# fixtures/generation

Generation fixtures provide deterministic examples for renderer and validation tests.

Current golden sample:

- `golden/java_mybatis_sp_wrapper_order_request_v1/`: Java/MyBatis draft bundle baseline.

P36 removed the metadata-only DTO/VO/Model golden because `DTO_MODEL_DRAFT`, `VO_DRAFT`,
`MODEL_DRAFT`, and `DDL_DRAFT` are no longer public generation targets.

New P36 fixture/eval expectations live in `tests/eval/test_p36_output_renewal_quality.py` and
cover the migration-guide SP analysis flow, evidence dossier dependency report, and
evidence-backed Java/MyBatis draft reconstruction.
