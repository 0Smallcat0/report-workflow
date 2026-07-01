# Revision Flow (`revise_existing`)

Load this reference when `task_intent="revise_existing"`. Use this mode only when
a base document is supplied with role `base_document` (exactly one entry).

In `revise_existing` mode, `section_drafts/*.md` are **not** merged into the final
document. The supported authoring surface is `revision_plan.json`.

## Steps

1. Call `get_controlled_next_action` until the harness returns the
   `revision_plan` stage.
2. Read `agent_tasks/04_revision_plan.md` and `base_document_sections.json`.
3. Write `revision_plan.json` with exact `original_text` spans and replacement
   text inside the returned `allowed_write_paths`.
4. Optionally call `preview_revision_diff` for a read-only diff preview.
5. Call `submit_controlled_action` to validate the revision plan and advance.

`submit_revision_plan` remains available only as a legacy compatibility helper;
the default public flow should use `get_controlled_next_action` and
`submit_controlled_action` so `revision_plan.json` edits stay within the harness
write-scope contract.

## Stale Base-Document Content

If a validation failure points to stale base-document content, invalidate caches
through the CLI:

```powershell
report-workflow invalidate-cache --job-id <id> --sources --drafts
```
