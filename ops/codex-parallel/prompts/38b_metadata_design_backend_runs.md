# P38B Metadata Design Backend Runs

## Role

platform_worker with contract-to-code and quality-gate-review.

## Task

Implement durable metadata design run backend support.

- Add API schemas for design requests, results, proposals, and run status.
- Add repository protocol, memory repository, and platform repository support for `METADATA_DESIGN_RUNS`.
- Add run submit/poll/conversation helpers and FastAPI routes.
- Extend recovery worker to reclaim queued and stale running design runs.

## Constraints

Keep result JSON sanitized. Do not store raw prompts, provider responses, row data, or full SQL/SP definitions.

## Acceptance

API, memory repository, platform repository, route, and recovery worker tests cover create/claim/succeed/fail/poll/conversation behavior with production_ready=false.
