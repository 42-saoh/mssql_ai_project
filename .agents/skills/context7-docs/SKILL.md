---
name: context7-docs
description: Use Context7 MCP to fetch up-to-date framework/library docs and turn them into narrow, actionable implementation guidance.
---

# Trigger

Use this skill when the task depends on current framework/library/API documentation, configuration keys, migration notes, or CLI reference.

# Inputs

- exact library or framework names
- likely version information from lockfiles, manifests, imports, or task brief
- the specific implementation question to answer
- affected files or stack area

# Steps

1. Identify the exact library/framework and the most likely version from the repository first.
2. Query Context7 with narrow requests. Prefer explicit package names or known library ids when available.
3. Pull only the vendor/reference pages required for the current task.
4. Translate the documentation into concrete repo changes, commands, tests, or notes.
5. Record the version assumption and the source used in the task report or updated docs.

# Framework Adoption Notes

- For OpenAI Agents SDK, LangGraph, or another orchestration framework, use official/vendor docs for tracing, configuration, persistence, and checkpointer behavior before changing the adopted runtime or proposing a new slice.
- Record the exact docs source and date-sensitive version assumption in the decision report or task notes.
- Summarize docs as policy-relevant findings; do not paste proprietary prompts, raw SP text, raw guide body, provider payloads, row data, secrets, or generated Java/XML payloads into external tools.
- If docs show default tracing or persistence that can capture sensitive inputs or outputs, treat runtime changes as blocked until redaction is proven.

# Guardrails

- Do not use this skill for project-internal facts that are already in repo docs or code.
- Do not send secrets, credentials, connection strings, raw prompts, raw provider responses, raw SP definitions, raw guide body, row data, failed Java/XML payloads, or large proprietary code blobs to external documentation tools.
- Prefer official/vendor docs over blogs and summaries.
- If vendor docs conflict with project policy, follow project policy and report the conflict.
