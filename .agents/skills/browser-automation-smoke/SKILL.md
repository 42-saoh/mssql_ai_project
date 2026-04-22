---
name: browser-automation-smoke
description: Use Playwright MCP for non-destructive local UI smoke tests, screenshots, and happy-path verification.
---

# Trigger

Use this skill when a task requires local UI verification, screenshot capture, or smoke testing for request/job/artifact screens.

# Inputs

- explicit base URL
- target routes or user journeys
- expected visible states or assertions
- auth/test-account constraints

# Steps

1. Confirm the app is running and the base URL is explicit.
2. Prefer `localhost` or an explicitly approved dev/test URL.
3. Use Playwright MCP for the smallest happy path needed: navigate, inspect, click, fill, and capture evidence.
4. Record visited routes, observed assertions, and any screenshots or artifacts captured.
5. Stop after smoke verification and report blockers instead of expanding scope.

# Guardrails

- No production or shared real accounts.
- No destructive mutations outside disposable fixtures or test data.
- Do not submit real payments, approvals, emails, or irreversible actions.
- Treat cookies, tokens, screenshots, traces, and storage state as sensitive and do not commit them.
