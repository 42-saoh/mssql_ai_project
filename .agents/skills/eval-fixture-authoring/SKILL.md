---
name: eval-fixture-authoring
description: Create representative fixtures, evaluation rubrics, and reproducibility checks for analysis and generation.
---

# Trigger

Use this when generator, parser, validator, or workflow logic changes and fixture coverage needs to grow.

# Steps

1. Pick a representative scenario.
2. Create the smallest realistic fixture.
3. Define expected fields and review-required fields separately.
4. Add pass/fail or score thresholds.
5. Store outputs in stable, diff-friendly formats.

# Framework Replay Fixtures

- Compare baseline and candidate adapters with the same generic inventory contract.
- Include at least one synthetic complex-SP collapse guard when a named benchmark such as ManageBond is used.
- Treat named procedures as benchmark fixtures only, not runtime answer keys.
- Reconstruct generated draft artifacts into the versioned schema and rerun deterministic quality validators.
- Assert no raw prompt, provider response, SP text, guide body, row data, secret, or unsafe trace data is stored.

# Output

- fixture inputs
- expected outputs
- eval runner or pytest case
- short rubric
