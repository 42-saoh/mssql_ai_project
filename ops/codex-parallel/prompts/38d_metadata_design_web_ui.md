# P38D Metadata Design Web UI

## Role

platform_worker with contract-to-code and browser-automation-smoke.

## Task

Implement the `/metadata/design` UI.

- Add chat-style input for message, metadata profile, table hints, and field rows.
- Submit through internal Web proxy routes and poll design run status.
- Render related metadata, standardization mappings, table script preview, and DTO preview.
- Provide client-side `.sql` and `.java` Blob downloads.

## Constraints

No publish, deploy, apply, execution, or row-data controls may be added.

## Acceptance

Web routes, page, proxy polling, preview, and Blob download controls are statically tested and build in test-web-smoke with production_ready=false.
