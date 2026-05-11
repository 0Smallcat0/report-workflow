---
name: report-workflow
description: Use when Codex needs to generate, revise, validate, or publish evidence-backed DOCX reports with the local report_workflow pipeline. Supports report profiles, optional web research, optional NotebookLM sync, and Chinese engineering lab reports.
---

# Report Workflow Skill

Use this skill to operate the local deterministic pipeline:

```text
prepare -> agent authoring -> validate -> render -> publish
```

The pipeline does not call an LLM. It parses sources, builds an evidence ledger,
checks agent-authored artifacts, renders DOCX, and packages outputs.
After DOCX render validation, it writes `post_render_layout_manifest.json` with
renderer, document size, paragraph/table/figure counts, heading and table
previews, related render QA report paths, and any render validation issues.
At publish time, it also writes `final_qa_summary.json` and
`final_qa_summary.md`, a delivery-level summary that links QA gate,
factuality, artifact lint, engineering audit, chart visual-quality review, and
render-layout evidence.
It writes `template_style_map.json` and `template_style_map.md` to explain the
reference DOCX mode, renderer, applied-reference status, key style definitions,
and rendered style usage.
For fixed-template metadata, it writes `template_field_fill_report.json` and
`template_field_fill_report.md` to show which structured fields were filled in
the final DOCX.

## Required Setup

Run before starting a report:

```python
check_setup()
```

Then ask the user about every pending install and optional integration reported
by `check_setup()`. `start_report_task` requires `preflight_confirmed=True` and
a complete `preflight_decisions` record.
Required dependencies must pass preflight after installation; do not treat an
`install` or `installed` decision as proof when `check_setup()` still reports
the dependency missing.
The raw CLI `prepare` entry point also requires a `--preflight-decisions` JSON
file with the same decision record, so command-line runs cannot bypass this
user-confirmation step.

Core dependencies:

- Python 3.11+
- `pip install -e .` in the repo root
- Pandoc 3.x for high-quality DOCX rendering

On Windows runs that include Chinese text, configure UTF-8 before calling the
CLI or inline Python helpers:

```powershell
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:PYTHONIOENCODING = 'utf-8'
```

This avoids cp950 crashes or mojibake in preflight output, template fields, and
Chinese source notes.

Optional:

- `mmdc` for Mermaid diagrams
- Tavily, Serper, or SerpAPI keys for web research
- `notebooklm-py` for NotebookLM sync

## Preflight Decision Examples

Always start from the `required_preflight_decisions` object returned by
`check_setup()`. The examples below show common completed shapes, not shortcuts.

All required setup is ready and optional integrations are skipped:

```python
preflight_confirmed=True,
preflight_decisions={
    "confirmed_by_user": True,
    "install_decisions": {},
    "feature_decisions": {
        "web_research": "skip",
        "notebook_sync": "skip"
    }
}
```

Pandoc is missing and the user explicitly accepts degraded DOCX rendering:

```python
allow_degraded_render=True,
preflight_confirmed=True,
preflight_decisions={
    "confirmed_by_user": True,
    "install_decisions": {
        "pandoc": "accept_degraded"
    },
    "feature_decisions": {
        "web_research": "skip",
        "notebook_sync": "skip"
    }
}
```

Web research and NotebookLM are enabled after the user confirms the available
backend/API key and provides a NotebookLM notebook ID:

```python
enable_research=True,
enable_notebook_sync=True,
notebooklm_notebook_id="notebook-id-from-user",
preflight_confirmed=True,
preflight_decisions={
    "confirmed_by_user": True,
    "install_decisions": {},
    "feature_decisions": {
        "web_research": "enable",
        "notebook_sync": "enable"
    }
}
```

If `check_setup()` still reports a required dependency missing, install and
rerun setup. Do not force-start by changing the decision record.

## Tool Surface

`agent_skill/skill.yaml` exposes these agent tools:

<!-- report-workflow:tool-surface:start -->
- `check_setup`
- `start_report_task`
- `submit_claim_matrix`
- `submit_outline`
- `submit_drafts`
- `lint_agent_artifacts`
- `run_engineering_audit`
- `submit_and_publish_report`
- `query_evidence`
- `remap_agent_artifacts`
- `submit_revision_plan`
- `preview_revision_diff`
<!-- report-workflow:tool-surface:end -->

Keep this short skill, `skill.yaml`, and `agent_instructions.md` synchronized.
From the repo root, update generated blocks before syncing:

```powershell
python scripts/render_skill_docs.py --write
python scripts/sync_codex_skill.py
python scripts/sync_codex_skill.py --write
```

Use `python scripts/render_skill_docs.py --check` in validation to catch stale
generated tool lists.

## Report Profiles

Pass `report_profile` when the user specifies a report type. Otherwise the
pipeline infers one from the prompt.

Built-in profiles:

- `engineering_lab_report`
- `academic_paper`
- `business_report`
- `proposal`
- `admissions_report`
- `admissions_project_report`
- `custom`

Do not use `report_family`, `--family`, `--detail`, variant, or subtype naming.

## Start a Run

```python
start_report_task(
    prompt="write an engineering lab report from these sources",
    source_files=[
        {"path": "/path/to/source.pdf", "role": "source_data"},
    ],
    output_dir="/path/to/output",
    report_profile="engineering_lab_report",
    task_intent="new_draft",
    template_fields={
        "course_name": "Control Systems",
        "student_id": "S12345"
    },
    preflight_confirmed=True,
    preflight_decisions={
        "confirmed_by_user": True,
        "install_decisions": {},
        "feature_decisions": {
            "web_research": "skip",
            "notebook_sync": "skip"
        }
    },
)
```

Use `task_intent="revise_existing"` with exactly one
`{"path": "...", "role": "base_document"}` entry when revising an existing
document. Legacy string paths are still accepted for new drafts.

When a scanned PDF or reference image must be manually transcribed, save the
transcription as Markdown or text and pass it with `role: "source_data"`. The
workflow treats `source_data` `.md` and `.txt` files as accepted internal
project sources, even if the file is named `source_notes.md`; do not use
generated workflow artifacts as source evidence.
If the user marks files as "reference only", do not pass them as
`source_data`, do not let their measurements enter the evidence ledger, and do
not cite or list them in the delivered report unless the user explicitly
changes their role.
Before drafting, keep a short source-role ledger that separates `source_data`,
`base_document`, template/reference format files, and reference-only context.
Only `source_data` may support measured values, calculated results, experiment
conditions, comparison groups, charts, or tables. Reference-only files may help
interpret terminology or expected discussion scope, but their numbers must not
enter the report, source ledger, calculations, figures, or references.
When external references are needed for theory, standards, or reference data,
keep them separate from experiment measurements. Cite the external source, use
it only for the specific theory/property claim, and never use it to invent
missing measured values or extra trial groups.

For academic-style profiles, pass structured front matter when available:
`title`, `author_block`, `affiliation_block`, `correspondence`, and `keywords`.
For school/company fixed templates, pass `template_fields` for fields such as
`course_name`, `student_id`, `instructor`, `lab_section`, `date`, or
`department`.

Use `project_identity` when a report must preserve specific project terms,
domain context, forbidden terms, or author metadata.

## Authoring Flow

Use incremental submission by default:

1. Read `agent_tasks/01_claim_plan.md`, write `claim_matrix.json`, call
   `submit_claim_matrix`.
2. Read `agent_tasks/02_outline_plan.md`, write `outline.json`, call
   `submit_outline`.
3. Read `agent_tasks/03_section_draft.md`, then write `structured_drafts.json`
   by default and call `submit_drafts`.
4. Optionally call `lint_agent_artifacts` after any artifact edit to get a
   consolidated `artifact_lint_report.json` with JSON paths and repair hints.
5. For `engineering_lab_report`, call `run_engineering_audit` after drafts
   exist to inspect units, table-value support, measurement support, and simple
   calculations.
6. Call `submit_and_publish_report`.

Every evidence-backed sentence in drafts must include `[CITE:<evidence_id>]`.
When using `structured_drafts.json`, provide sentence `evidence_ids`; the
pipeline inserts matching `[CITE:]` markers and writes `sentence_map.jsonl`.
For sentences supported by multiple evidence entries, prefer one marker per
entry, such as `[CITE:E001] [CITE:E002]`. Legacy markers such as
`[CITE:E001,E002]` are accepted by validation, but newly generated drafts should
emit separate markers.
Use manual `section_drafts/*.md` plus `sentence_map.jsonl` only when the draft
needs direct Markdown control or when repairing generated canonical drafts.
Do not cite internal workflow files, evidence ledgers, claim matrices, or
traceability appendices in the main report.

Use `query_evidence(job_id=..., query="...")` for relevance-ranked evidence
lookup instead of loading large ledgers into context. If you reuse artifacts
from an older run, call `remap_agent_artifacts(job_id=..., previous_job_id=...)`
first in dry-run mode, then rerun with `write=True` only after the mapping is
reasonable.

## Revision Flow

Use `task_intent="revise_existing"` only when a base document is supplied with
role `base_document`. In this mode, `section_drafts/*.md` are not merged into
the final document. Instead:

1. Read `agent_tasks/04_revision_plan.md` and `base_document_sections.json`.
2. Write `revision_plan.json` with exact `original_text` spans and replacement
   text.
3. Call `preview_revision_diff` for a read-only diff preview.
4. Call `submit_revision_plan` to validate spans and conflicts before publish.
5. Call `submit_and_publish_report` only after the revision plan validates.

## Engineering Lab Reports

For `engineering_lab_report`, preserve the profile contract above prompt or
template details. The profile expects:

- SOP/handout/lab-instruction grounding.
- Requirement matrix coverage.
- Formula, parameter, symbol, and unit audit.
- Calculation audit.
- Figure/table contract.
- Chinese document rules and mojibake avoidance.
- Render QA for cover/template drift, table compression, and image placement.
Use `run_engineering_audit` to write `engineering_audit_report.json` before
publish when units, table-backed claims, measurement claims, or arithmetic need
explicit checking.
Only introduce experiment conditions, comparison groups, measured values, and
calculated results that are supported by the accepted source-data ledger. Do
not infer extra fan speeds, trial groups, or comparison rows from examples,
reference-only images, or similar prior reports.
For domain-specific tables, charts, standards, calculators, or external
databases, use the user-supplied sources first. If the supplied scan or table
is not readable enough for a reliable value, state that limitation. If the user
requests or allows external lookup, record the source, access date, input
basis/units, mapping between source fields and report quantities, assumptions,
representative point, and formulas. Label derived values as estimates and use
conservative significant figures. Do not compute aggregate totals from per-unit
or normalized values unless the required scaling variable is measured or
otherwise explicitly supplied.

Reference DOCX behavior:

- User-specified mode wins.
- Default is `style_reference`.
- If the prompt asks to exactly match the format or cover, use `fixed_template`.
- If a school cover must be copied exactly, validate content through the
  workflow, then verify the final DOCX with a fixed-template render or a
  template-copy post-render pass and visual page QA. Inspect the cover page,
  tables, charts, and Chinese text before delivery.
- When the user says to copy a cover exactly and change only selected fields,
  preserve the original first-page paragraphs and runs; replace text inside
  existing runs where possible, and compare the cover text, order, font sizes,
  and spacing against the template before delivery.
- When a reference DOCX is supplied for the whole report format, inspect body
  paragraphs, captions, tables, page margins, font sizes, and rendered page
  density from the reference; do not validate only the cover page.
- If the final document is generated or repaired outside the workflow renderer,
  rerun a template/style comparison after that post-render pass. Compare the
  exact-cover paragraph order, visible text, run font sizes, spacing, and
  the body page density against the reference; only intentional field changes
  such as title or date may differ.

Chinese engineering publish checklist:

- `lint_agent_artifacts` has no errors and citation IDs match the current run.
- `run_engineering_audit` has been reviewed for unit support, table-value
  support, measured values, and simple calculations.
- Engineering audit page labels, adjacent engineering units, and rounded table
  values are tolerated, but review remaining warnings before changing claim
  wording.
- The draft covers the lab handout/SOP requirements, required questions,
  apparatus/procedure, results, discussion, conclusion/reflection, and
  references.
- Formula variables, parameters, units, table numbers, figure numbers, and
  prose references are consistent.
- Engineering symbols and units are publication-ready: table headers use
  `Name (unit)` formatting such as `P (kPa)` and `T (°C)`; formulas and prose
  use proper subscript notation through Word subscript runs or stable Unicode
  subscripts; scan for mixed unit formats, raw underscores, broken symbol
  wraps, or missing degree symbols before delivery.
- Keep symbol semantics distinct: do not reuse the same symbol for quantities
  with different units or meanings. Add qualifiers such as rate, per-unit,
  average, nominal, measured, or estimated when needed. If a derived indicator
  is unusually high or conflicts with the primary measured result, explicitly
  frame it as an estimate, list the assumptions and likely error sources, and
  keep the source-supported measured result as primary unless the data justify
  otherwise.
- Every figure caption or figure reference has a nearby embedded visual, and
  the rendered PNG page shows the actual chart/image rather than only a
  caption or placeholder.
- Every chart is built only from accepted source-data values. Each figure has
  one visible chart, a caption below the chart, labeled axes with units where
  applicable, and readable legends. Verify the DOCX has embedded drawing/image
  objects and visually inspect rendered PNG pages; text extraction that finds
  a figure title is not evidence that the chart exists.
- Generated charts also write `figure_visual_quality_report.json`, which flags
  review-only visual risks such as overlapping tick labels, legends covering
  plotted data, and heatmaps that are too dense for report scale.
- Supported generated chart types are `bar`, `line`, `scatter`, `pie`,
  `table`, `histogram`, `boxplot`, `heatmap`, `error_bar`, and
  `stacked_bar`. Prefer the deterministic recommendation, and keep exact
  values as a table when the visual mapping is ambiguous.
- If a starter chart includes `data_transform`, preserve that metadata and
  plotted data. The workflow may have already applied group-by, pivot,
  wide-to-long, percent-of-total, sorting, or top-N transforms; do not hand
  recalculate those values unless the manual replacement is explained in
  `chart_selection_reason`.
- Chinese prose is natural and contains no workflow/agent jargon, placeholder
  text, mojibake, or raw internal file paths.
- Delivery prose does not expose internal provenance labels such as page
  transcription notes, `source_notes`, local filenames, image names, or agent
  workflow artifacts unless the user specifically requests an appendix for
  traceability.
- If the user supplies forbidden phrases, source-use constraints, or known-bad
  comparison labels, scan the final DOCX text for them after any post-render
  edit.
- Template fields such as course, student ID, instructor, lab section, date,
  and department are supplied when the school/company template expects them.
- Before delivery, inspect `final_qa_summary_path`, then
  `template_field_fill_report_path`, `template_style_map_path`, and
  `post_render_layout_manifest_path` when those paths are returned.

## Publish Gate

Do not treat a rendered DOCX as delivered unless the workflow returns completed
status and no later gate marks it non-publishable. If validation fails, edit the
agent artifact that caused the failure and rerun validation.

Failure repair order:

- Artifact shape or ID drift: run `lint_agent_artifacts`, then edit the JSON
  path or file named in `artifact_lint_report.json`.
- Claim support or factuality failure: edit `claim_matrix.json`, draft wording,
  or `sentence_map.jsonl`; do not edit checkpoint JSON.
- Engineering unit, table-value, or arithmetic concerns: inspect
  `engineering_audit_report.json` before changing claim text.
- Revision failures: edit `revision_plan.json` exact spans, then rerun
  `preview_revision_diff` and `submit_revision_plan`.
- Render failures: fix Markdown/table/figure/template artifacts, rerun
  validation, then render.

For completed runs, inspect `final_qa_summary_path` or packaged
`published/qa/final_qa_summary.json` first when reporting final delivery
readiness; the Markdown sibling is packaged as `published/qa/final_qa_summary.md`.
Inspect `figure_visual_quality_report_path` or packaged
`published/qa/figure_visual_quality_report.json` when chart readability needs
review.
Inspect `post_render_layout_manifest_path` or packaged
`published/qa/post_render_layout_manifest.json` when you need render-structure
evidence for the delivered DOCX.
Use `template_style_map_path` or packaged
`published/qa/template_style_map.json` when the user asks how a template or
reference DOCX affected the final document.
Use `template_field_fill_report_path` or packaged
`published/qa/template_field_fill_report.json` when the user asks whether cover
or fixed-template fields were filled.
