# AGENTS.md

This file gives repository-specific guidance to agents working on
`report-workflow`. Start with `AGENT_ONBOARDING.md` for the conceptual model and
`agent_skill/agent_instructions.md` for the skill operating procedure.

## Project Overview

`report-workflow` is a deterministic source-to-report pipeline for
evidence-backed DOCX reports. The Python package does not call an LLM provider.
It owns parsing, evidence normalization, artifact contracts, validation gates,
DOCX rendering, checkpoints, and published package assembly. The external agent
owns judgment, claim selection, outlining, and drafting.

The installed package lives under `src/report_workflow/`; `pyproject.toml`
uses `package-dir = {"" = "src"}`. Keep edits inside `src/report_workflow/`
unless the task explicitly targets docs, tests, packaging, or skill metadata.

## Commands

```powershell
pip install -r requirements.txt
pip install -e .

python -m compileall -q src tests
python -m unittest discover -s tests -v

report-workflow prepare --prompt "..." --source path\to\src.txt --output out\dir --profile engineering_lab_report
report-workflow prepare --prompt "..." --source data.csv:source_data --source base.docx:base_document --output out\dir --profile engineering_lab_report --intent revise_existing
report-workflow validate --job-id <job_id> [--verbose] [--dry-run] [--deep-audit]
report-workflow render --job-id <job_id>
report-workflow status --job-id <job_id>
report-workflow run --job-id <job_id> [--verbose]
report-workflow diff --job-id <a> --against <b>
report-workflow export --job-id <id> [--checkpoint <name>] [--output <file>]
report-workflow diagnose --job-id <id> [--verbose]
report-workflow invalidate-cache --job-id <id> [--sources] [--drafts]
```

`--source PATH:ROLE` may be repeated. Valid artifact roles are `source_data`
and `base_document`. The role suffix is parsed only when the trailing token is
one of those roles, so Windows paths such as `C:\path\to.txt` are safe.

CLI exit codes: `0` success, `1` crash, `2` hard-block failure, `3` waiting for
agent-authored artifacts.

## Public Contract

`report_profile` is the only public report-shape selector. Do not add or
document alternate public selectors. Built-in profile IDs:

- `engineering_lab_report`
- `academic_paper`
- `business_report`
- `proposal`
- `admissions_report`
- `admissions_project_report`
- `custom`

Profiles control blueprint selection, policy strictness, aliases, front matter,
abstract rules, citation behavior, figure/table contracts, tone rules, and
reference-template behavior. The workflow DAG should remain stable; nodes read
profile policy through `get_policy(state.spec.get("report_profile",
"academic_paper"))`.

## Stage Lists

`src/report_workflow/run_workflow.py` owns the canonical stage sequence. Each
stage contains deterministic substeps recorded in `job_events.jsonl` as
`STAGE/SUBSTEP`. Keep this section synchronized when changing stage lists.

Prepare:

```text
SPEC_PLAN -> SOURCE_INGEST -> EVIDENCE_BUILD -> FIGURE_RECOMMEND ->
NOTEBOOK_SYNC -> AGENT_TASKS
```

Validate:

```text
AGENT_ARTIFACTS -> PLAN_LOCK -> METADATA_GATE -> CONTENT_ASSEMBLY ->
DRAFT_GATES -> EVIDENCE_AND_CLAIMS -> FINAL_QA
```

Render:

```text
TEXT_POLISH -> DOCX_BUILD -> RENDER_QA -> REFERENCE_QA -> PUBLISH
```

`POST_RENDER_VALIDATE` writes both `post_render_validate_report.json` and
`post_render_layout_manifest.json`. The layout manifest is an audit artifact
for rendered DOCX structure: renderer used, file size, paragraph/table/figure
counts, heading summary, table previews, front-matter preview, related render QA
reports, and validation issues. `ARTIFACTS` packages it under `published/qa/`
when present. `ARTIFACTS` also writes `final_qa_summary.json` and
`final_qa_summary.md` as the delivery-level QA entry point, combining QA gate,
factuality, artifact lint, engineering audit, chart visual-quality review, and
scholarly-quality review, and render-layout evidence without adding a new hard gate.
It also writes `template_style_map.json` and `template_style_map.md`, explaining
the reference DOCX mode, renderer, applied reference status, key style
definitions, rendered style usage, and template-fidelity warnings.
For fixed-template metadata, `ARTIFACTS` writes
`template_field_fill_report.json` and `template_field_fill_report.md`, showing
which structured fields were rendered into the final DOCX.

Explicit quality commands, when implemented for a workflow branch, should stay
outside the default validate path unless the product contract changes.

## Agent Artifact Contract

Prepare writes task briefs under:

```text
output/<slug>--<job_id>/agent_tasks/
```

The agent writes into the run directory:

- `claim_matrix.json`
- `outline.json`
- `structured_drafts.json` as an optional low-drift input for new drafts
- `section_drafts/*.md`
- `sentence_map.jsonl`
- `revision_plan.json` for `task_intent=revise_existing`

Every evidence-backed sentence in section drafts must include
`[CITE:<evidence_id>]`, and those IDs must match `sentence_map.jsonl`.
When `structured_drafts.json` is supplied and canonical draft artifacts are
missing, `SECTION_DRAFT` compiles it into Markdown section drafts and
`sentence_map.jsonl`.
Use `query_evidence` for ledger lookup instead of loading huge ledgers into
context.
Use `lint_agent_artifacts` after creating or changing agent-owned artifacts to
write `artifact_lint_report.json` with artifact names, JSON paths, severity,
messages, and repair hints before running the full validate/render path.
For `engineering_lab_report`, use `run_engineering_audit` after drafts exist to
write `engineering_audit_report.json` with measurement extraction,
claim/evidence unit-support warnings, table-value support checks, unit notation
warnings, missing-unit notes, and simple calculation checks.
For `academic_paper` and `engineering_lab_report`, validation writes
`scholarly_quality_report.json` and `scholarly_quality_report.md` with
review-grade checks for article spine, introduction flow, methods
reproducibility, role separation, figure/table scholarly expectations, and
reference metadata quality.
Completed publications include `published/qa/final_qa_summary.json` and
`published/qa/final_qa_summary.md`; inspect those first when summarizing
delivery readiness for a user.
Use `published/qa/scholarly_quality_report.json` when the user asks whether an
academic or Chinese engineering report reads like a serious scholarly article.
Use `published/qa/figure_visual_quality_report.json` when the user asks about
chart readability issues such as overlapping labels, legend placement, or dense
heatmaps.
Use `published/qa/template_style_map.json` when the user asks how the reference
DOCX/template influenced the final render.
Use `published/qa/template_field_fill_report.json` when the user asks whether
cover or fixed-template fields were filled.

## Revision Mode

For `task_intent=revise_existing`, `BASE_DOCUMENT_PARSE` extracts sections from
the single `base_document` source into `base_document_sections.json`.
`REVISION_APPLY` reads that file plus `revision_plan.json` and writes the
merged draft. `section_drafts/*.md` are not merged into the final document in
this mode.

Do not edit `base_document_sections.json`, generated draft files, or checkpoint
JSON directly as an authoring shortcut. If disk artifacts are intentionally
changed during debugging, invalidate the affected checkpoint cache before
validating:

```powershell
report-workflow invalidate-cache --job-id <id> --sources --drafts
```

## Hard Gates

- Delivery mode is `fresh_doc`.
- Every publishable claim must cite existing evidence.
- Claim statuses `blocked`, `unverified`, and `disputed` are non-publishable.
- Claim type must be allowed by the cited evidence.
- Evidence-backed sentences must include matching `[CITE:<evidence_id>]`
  placeholders.
- Unresolved citation audit entries hard-fail.
- Placeholder prose, fake metadata, internal paths, and workflow artifacts must
  not leak into publication text.
- `DOCX_RENDER` requires `qa_decision=pass`.

## Debugging Guidance

For factuality failures, inspect the fresh `factuality_report.json` from the
run directory. The factuality checker reads canonical disk artifacts:

- `claim_matrix.json`
- `evidence_ledger.jsonl`
- `sentence_map.jsonl`

Editing checkpoint snapshots does not affect factuality checks.
For artifact-shape failures, run `lint_agent_artifacts` first and inspect
`artifact_lint_report.json`; it centralizes missing files, malformed JSON,
unknown section/claim/evidence IDs, and citation marker drift.
For engineering unit or calculation questions, inspect
`engineering_audit_report.json` before changing claim text or calculation prose.

For abstract failures, fix the authored abstract draft. Common blockers are
trailing ellipses, incomplete final sentences, leftover `[CITE:]` or `[Source:]`
markers, placeholder text, and profile-specific word-count violations.

## Adding A Substep

1. Add `src/report_workflow/nodes/<name>.py` with `run_<name>(state:
   ReportState) -> ReportState`.
2. Import it in `src/report_workflow/run_workflow.py`.
3. Insert it as a `WorkflowStep` inside the appropriate `prepare_stages()`,
   `validate_stages()`, or `render_stages()` stage.
4. Raise `QAHardBlockError` for hard gates so remediation and failed
   checkpoints are written.
5. Update this file and `CLAUDE.md` if the canonical stage sequence changes.
