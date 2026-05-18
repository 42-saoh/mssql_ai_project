---
name: quality-gate-review
description: Run a focused pre-merge review for correctness, policy compliance, evidence coverage, tests, and docs drift.
---

# Trigger

Use this before merge or before handing work back to a reviewer.

# Checklist

- correctness risk
- policy violation
- missing or weak tests
- docs drift
- hidden breaking change
- missing review-required markers

# Framework Adoption Checks

- raw trace, prompt, provider response, SP definition, guide body, row data, secret, or failed Java/XML payload leakage
- framework persistence or checkpointer state without proven redaction
- candidate adapter bypassing P42 schema, deterministic inventory, repair, Java/MyBatis quality, or no-fallback gates
- ManageBond-specific runtime hardcoding or benchmark overfit
- missing rollback path to the current Responses/httpx gateway or baseline adapter
- dependency install, public switch, API/schema/UI/MCP/artifact expansion, source apply, deploy, row-data query, or procedure execution without an explicit policy gate

# Reporting

Report findings by severity and include concrete reproduction or rationale.
