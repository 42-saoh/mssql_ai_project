## Role

platform_worker with contract-to-code and browser-automation-smoke.

## Task

Convert `/metadata/design` to a chat transcript and natural-language compose
experience. Keep metadata profile, conversation mode, optional table name hint,
preview panels, and `.sql`/`.java` client downloads.

## Constraints

- Remove visible field row inputs from the Web UI.
- Do not add apply, execute, deploy, publish, or source-write controls.
- Keep 1920x1080 layout stable with no horizontal overflow.
- Do not connect previews to workflow artifact storage.

## Acceptance

- Static Web tests confirm chat UI, `conversationMode`, preview/download
  controls, and absence of field row UI.
- Browser smoke at 1920x1080 verifies new design and follow-up refine previews.
