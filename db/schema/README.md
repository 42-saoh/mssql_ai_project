# db/schema

This directory keeps Platform DB schema changes as versioned SQL drafts.

Rules:

- SQL files in this directory are design/review/manual-apply assets only.
- Codex and the API must not automatically execute or apply these files.
- Older DDL files remain historical drafts unless explicitly superseded in docs.
- External DB startup, shutdown, and migration application are managed outside this repository.

## Current Manual Drafts

- `ai_agent_platform_schema_v6_draft_quality_no_review.sql`: draft-quality knowledge assets without human review/approval product tables.
- `ai_agent_platform_schema_v7_metadata_analysis_runs.sql`: durable metadata analysis run submit/polling storage.
- `ai_agent_platform_schema_v8_canonical_target_keys_consolidated.sql`: canonical target key columns and indexes for requests, jobs, agent runs, artifacts, and knowledge assets.

`CANON_TRGT_KEY_TXT` stores the server-derived key in the format
`mssql:<dbProfileId>:<database|->:<objectType>:<schema>.<name>`.
