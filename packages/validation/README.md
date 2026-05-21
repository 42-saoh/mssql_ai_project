# packages/validation

Draft artifact validation for evidence coverage, required sections, and policy caveats.

Current implementation:

- `ai_agent_validation.load_validation_rules` reads `spec/validation/validation_rules.yaml`.
- `validate_artifact` checks required sections, evidence coverage, and `REVIEW_REQUIRED` caveat markers.
- OpenAPI requested output group and persisted artifact type aliases are resolved only through `ARTIFACT_TYPE_ALIASES`.
- `summarize_validation_report` returns deterministic validation counts, missing evidence, and `qualityCaveats`.
- The package does not create publish or decision gates.
