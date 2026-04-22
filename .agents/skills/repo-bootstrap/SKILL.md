---
name: repo-bootstrap
description: Bootstrap a Codex-ready repo with docs, config, agents, skills, commands, and starter structure.
---

# Trigger

Use this skill when the repository needs first-time setup or a major structure refresh for Codex-driven local development.

# Inputs

- target stack
- required root docs
- desired repo layout
- required local commands
- safety constraints

# Steps

1. Create or normalize root docs: `AGENTS.md`, `PROJECT.md`, `ARCHITECTURE.md`, `TOOLS.md`, `POLICY.md`, `EVAL_SPEC.md`, `TASK_TEMPLATE.md`.
2. Add `.codex/config.toml` with safe defaults and explicit profiles.
3. Add project-scoped custom agents under `.codex/agents/`.
4. Add repo-scoped skills under `.agents/skills/`.
5. Create a minimal runnable tree for `apps/`, `services/`, `packages/`, `docs/`, `tests/`, `fixtures/`.
6. Add a small command surface such as `make setup`, `make check`, `make run-api`, `make run-mcp`.
7. Document what is real, what is stubbed, and what the next implementation slices are.

# Guardrails

- Do not invent unsafe deployment or DB write flows.
- Keep scope to bootstrap, not full production implementation.
- Prefer clear placeholders over fake completeness.
