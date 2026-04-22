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

# Output

- fixture inputs
- expected outputs
- eval runner or pytest case
- short rubric
