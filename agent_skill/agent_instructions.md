# Report Workflow Agent Instructions

This is the agent-facing operating guide for the `report_workflow` skill.
The Python package is deterministic: it parses sources, normalizes evidence,
freezes the report profile contract, validates agent-authored artifacts, and
renders DOCX output. The agent owns judgment, claim selection, outlining, and
drafting.

## Core Model

The workflow has three phases:

1. **Prepare**: `start_report_task` reads sources, infers or accepts
   `report_profile`, writes `report_spec.json`, `report_profile.json`,
   `blueprint.json`, `evidence_ledger.jsonl`, and task briefs.
2. **Author**: the agent writes `claim_matrix.json`, `outline.json`, and either
   `structured_drafts.json` or canonical `section_drafts/*.md` plus
   `sentence_map.jsonl`.
3. **Validate and render**: `submit_and_publish_report` validates contracts,
   evidence support, citations, section rules, profile policy, and render
   quality before publishing the DOCX. Successful render validation writes a
   `post_render_layout_manifest.json` audit artifact with renderer, file size,
   paragraph/table/figure counts, headings, table previews, related render QA
   reports, and issues.
   Publish packaging writes `final_qa_summary.json` and
   `final_qa_summary.md` to consolidate QA gate, factuality, artifact lint,
   engineering audit, chart visual-quality review, and render-layout evidence
   for delivery review.
   It also writes `template_style_map.json` and `template_style_map.md` to
   explain reference-DOCX mode, renderer choice, applied-reference status, key
   style definitions, and rendered style usage.
   Fixed-template metadata is audited through
   `template_field_fill_report.json` and `template_field_fill_report.md`.

The workflow does not call an LLM provider and does not preserve tracked
changes from existing DOCX files. In `revise_existing` mode, the supported
authoring surface is `revision_plan.json`.

## Report Profiles

Use `report_profile`, not `report_family`, `--family`, detail, subtype, or
variant naming. A profile is the single public contract for structure and rules.

Built-in profile IDs:

- `engineering_lab_report`
- `academic_paper`
- `business_report`
- `proposal`
- `admissions_report`
- `admissions_project_report`
- `custom`

Profiles control section contracts, front matter, abstract policy, citation
style, figure/table requirements, word-count strictness, tone policy, and
render QA expectations. They do not change the deterministic DAG shape.

`custom` is intentionally medium strictness: evidence-backed claims and section
contracts are required, while citation style, word-count, and figure rules stay
lenient unless the user supplies a stricter structure.

## Template Priority

The user can request a reference/template mode. If omitted, the workflow uses
`style_reference`. If the prompt asks to follow the exact format, exact cover, or
same template, intake upgrades the mode to `fixed_template`.

Profile semantics still win over visual template hints. For example,
`engineering_lab_report` keeps its engineering report contract even when a
reference document is used for style.

## Preflight

Call `check_setup()` before every `start_report_task`.

Required runtime:

- Python 3.11+
- `pip install -e .` from the repository root
- Pandoc 3.x for high-quality DOCX rendering

For Windows runs that include Chinese text, configure the console and Python
stdio for UTF-8 before calling CLI commands or inline Python helpers:

```powershell
$OutputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::InputEncoding = [System.Text.UTF8Encoding]::new($false)
[Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)
$env:PYTHONIOENCODING = 'utf-8'
```

This prevents cp950 preflight crashes and mojibake in template fields or
Chinese source notes.

Optional integrations:

- `mmdc` for Mermaid-to-PNG conversion
- `TAVILY_API_KEY`, `SERPER_API_KEY`, or `SERPAPI_API_KEY` for external claim
  research
- `notebooklm-py` and a notebook ID for NotebookLM sync

`start_report_task` requires `preflight_confirmed=True` and a complete
`preflight_decisions` record. Required dependencies must actually pass
preflight before start. Missing critical render dependencies must be installed
or explicitly accepted with `install_decisions` set to `accept_degraded` and
`allow_degraded_render=True`.

## Start A Report

```python
start_report_task(
    prompt="Write an engineering lab report from these measurements.",
    source_files=[
        {"path": "lab_notes.pdf", "role": "source_data"},
        {"path": "measurements.csv", "role": "source_data"},
    ],
    output_dir="output",
    report_profile="engineering_lab_report",
    task_intent="new_draft",
    template_fields={
        "course_name": "Control Systems",
        "student_id": "S12345"
    },
    preflight_confirmed=True,
    preflight_decisions={...}
)
```

If `report_profile` is omitted, the workflow infers it from the prompt and
source context. Use explicit profile IDs when the user has already chosen the
report type.

When scanned PDFs or reference images need manual transcription, create a
Markdown or text transcription and pass it as `role: "source_data"`. Source-data
`.md` and `.txt` files are accepted as internal project sources even when their
names contain `notes`; never use generated workflow artifacts as source
evidence.
Keep an explicit source-role ledger before drafting: `source_data`,
`base_document`, template/reference-format files, and reference-only context.
Only `source_data` may support experiment conditions, measured values,
calculated results, comparison groups, tables, or charts. Reference-only files
may inform interpretation and expected discussion scope, but their numbers must
not enter the evidence ledger, calculations, figures, body text, or references.
External references may support theory, standards, or reference data only. Keep
them separate from experiment measurements, cite them directly, and do not use
them to fill missing measurements, create comparison groups, or override the
source-data ledger.

For revision workflows, pass one base document explicitly:

```python
start_report_task(
    prompt="Revise this report using the supplied measurements.",
    source_files=[
        {"path": "old_report.docx", "role": "base_document"},
        {"path": "measurements.csv", "role": "source_data"},
    ],
    output_dir="output",
    report_profile="engineering_lab_report",
    task_intent="revise_existing",
    preflight_confirmed=True,
    preflight_decisions={...}
)
```

## Authoring Artifacts

After prepare, read the task briefs in `agent_tasks/`:

- `01_claim_plan.md`
- `02_outline_plan.md`
- `03_section_draft.md`
- `04_revision_plan.md` for `revise_existing`

Write these artifacts in the run directory:

- `claim_matrix.json`
- `outline.json`
- `structured_drafts.json` as the preferred low-drift draft input
- `section_drafts/*.md`
- `sentence_map.jsonl`

Every authored artifact must include the `_contract` block from the brief. If
you reuse artifacts from a previous run, call `remap_agent_artifacts` instead of
manually editing evidence IDs.
After any artifact edit, call `lint_agent_artifacts(job_id=...)` when you want
fast read-only feedback before a full validation run. It writes
`artifact_lint_report.json` with severity, artifact name, JSON path, message,
and repair hint.

`structured_drafts.json` may replace manual section Markdown and sentence-map
authoring for new drafts. Use this shape:

```json
{
  "sections": {
    "results": {
      "sentences": [
        {
          "text": "The pilot program enrolled 42 participants.",
          "claim_ids": ["c1"],
          "evidence_ids": ["E001"],
          "wording_strength": "hedged"
        }
      ]
    }
  }
}
```

When `submit_drafts` sees `structured_drafts.json` and the canonical draft files
are missing, the pipeline writes `section_drafts/*.md`, inserts `[CITE:]`
markers from `evidence_ids`, and writes `sentence_map.jsonl`.

For sentences with multiple supporting entries, emit separate markers such as
`[CITE:E001] [CITE:E002]`. Legacy comma-delimited markers such as
`[CITE:E001,E002]` are accepted for older artifacts, but separate markers are
the preferred output.

## Evidence Rules

- Every publishable claim needs at least one valid `evidence_id`.
- Do not mark publishable claims as `blocked`, `unverified`, or `disputed`.
- Statistical claims require quantitative evidence.
- Evidence-backed sentences must include `[CITE:<evidence_id>]`.
- `sentence_map.jsonl` citation IDs must match the Markdown `[CITE:]` markers.
- Use hedged wording for medium-grade or qualitative evidence.
- Do not cite checkpoint files, internal paths, generated task briefs, or
  workflow metadata as external evidence.
- Use `query_evidence(job_id=..., query="...")` for relevance-ranked browsing
  when the ledger is large; use `evidence_ids=[...]` for exact lookups.

## Draft Rules

Do not edit generated files such as `merged_draft.md`, `publication_draft.md`,
or checkpoint JSON. Edit the agent-owned artifacts and rerun validation.

Avoid:

- placeholder text such as `This section is under development`
- `[Source:]`, `[graphify:]`, `[Note:]`, or other internal markers in body prose
- raw evidence IDs outside `[CITE:]`
- internal file paths in report prose
- ASCII-art diagrams; use Mermaid or real image assets instead

## Engineering Lab Report Notes

For `engineering_lab_report`, treat SOPs, lab handouts, measurement sheets, and
rubrics as first-class sources. The report should preserve:

- required Chinese lab-report sections
- experiment purpose, theory, apparatus, procedure, results, discussion,
  conclusion/reflection, and references
- formula variables, parameters, units, and calculation assumptions
- figure/table numbering and references
- question-and-answer requirements from the handout
- Chinese report tone without agent/workflow jargon

Use `run_engineering_audit` before publish when the report contains measured
values, formulas, or calculations. Review `engineering_audit_report.json` for
claim/evidence unit-support warnings, table-value support checks, unit notation
drift, missing-unit notes, and simple arithmetic mismatches.
The audit tolerates page labels, adjacent engineering units, and small rounding
differences between prose and table values; remaining warnings still need human
review before changing claim wording.

For domain-specific tables, charts, standards, calculators, or external
databases, prefer the user-supplied sources. If a scanned chart or table is not
readable enough to support a value, say so instead of fabricating precise
numbers. When the user requests or allows external lookup, record the external
source, access date, input basis/units, mapping between source fields and
report quantities, assumptions, representative point, and calculation formulas.
Mark derived values as estimates and use conservative significant figures.
Per-unit or normalized values may support per-unit comparisons, but aggregate
totals require the relevant scaling variable to be measured or explicitly
supplied.

If the user asks to copy a school cover or exact template, use `fixed_template`
for the workflow pass where possible and verify the final DOCX visually. If the
renderer cannot preserve the cover exactly, keep the workflow output as the
validated content source and use a template-copy post-render pass, then inspect
the rendered pages for cover, table, chart, and Chinese text layout.
If the prompt supplies a reference DOCX for whole-report style, inspect the
reference body as well as the cover: margins, paragraph density, font sizes,
captions, tables, and page breaks. After any post-render repair, compare the
exact-cover paragraph order, visible text, run font sizes, spacing, and body
page density again; only requested fields such as title or date may differ.

Before delivery, treat figure and format checks as hard gates:

- A figure caption or figure reference requires a real nearby embedded visual.
  Verify the final DOCX contains drawing/image objects and visually inspect the
  rendered PNG pages; extracted text showing a figure title is not enough.
- Build charts only from accepted `source_data`. Each chart needs labeled axes,
  units where applicable, readable legends, and a caption below the visual.
- Generated charts write `figure_visual_quality_report.json` with review-only
  checks for overlapping labels, legend placement, and heatmap density.
- Supported generated chart types are `bar`, `line`, `scatter`, `pie`,
  `table`, `histogram`, `boxplot`, `heatmap`, `error_bar`, and
  `stacked_bar`. Prefer the deterministic recommendation, and keep exact
  values as a table when the visual mapping is ambiguous.
- If a recommended starter chart contains `data_transform`, keep that metadata
  and chart payload unless you intentionally replace the derived view. The
  deterministic layer may have already handled group-by, pivot, wide-to-long,
  percent-of-total, sorting, or top-N cleanup; manual replacements need a
  specific `chart_selection_reason`.
- Use publication-ready engineering notation: table headers such as `P (kPa)`
  and `T (°C)`, and formula/prose symbols rendered with Word subscript runs or
  stable Unicode subscripts when needed. Scan for mixed unit formats, raw
  underscores, missing degree symbols, and broken symbol wraps.
- Keep symbol semantics distinct: do not reuse the same symbol for quantities
  with different units or meanings. Add qualifiers such as rate, per-unit,
  average, nominal, measured, or estimated when needed. If a derived indicator
  is unusually high or conflicts with the primary measured result, state that
  it is an estimate, list the assumptions and likely error sources, and keep
  the source-supported measured result as primary unless the data justify
  otherwise.
- Scan the final DOCX text for user-provided forbidden phrases and internal
  provenance leaks such as page-transcription labels, `source_notes`, local
  filenames, reference image names, or workflow artifact names.

The built-in `CHINESE_ENGINEERING` guideline is selected by default for this
profile.

## Incremental Submission

Preferred sequence:

1. Write `claim_matrix.json`, then call `submit_claim_matrix(job_id=...)`.
2. Write `outline.json`, then call `submit_outline(job_id=...)`.
3. Write `structured_drafts.json` or `section_drafts/*.md` plus
   `sentence_map.jsonl`, then call `submit_drafts(job_id=...)`.
4. Optionally call `lint_agent_artifacts(job_id=...)` after edits or before
   full validation to catch shape errors and ID drift early.
5. For `engineering_lab_report`, call `run_engineering_audit(job_id=...)`
   after drafts exist to check units, table-value support, measurement support, and simple
   calculations.
6. Call `submit_and_publish_report(job_id=...)`.

Legacy two-step use is still supported: after prepare, create all artifacts and
call `submit_and_publish_report` directly.

When `submit_and_publish_report` succeeds, use
`post_render_layout_manifest_path` if you need evidence about final DOCX
structure. The same file is packaged under
`published/qa/post_render_layout_manifest.json` when present.
For delivery readiness, inspect `final_qa_summary_path` first. It is packaged
with a Markdown sibling under `published/qa/final_qa_summary.json` and
`published/qa/final_qa_summary.md`.
For chart readability review, inspect `figure_visual_quality_report_path`; the
published package includes `published/qa/figure_visual_quality_report.json`.
For template questions, inspect `template_style_map_path`; the published
package includes `published/qa/template_style_map.json` and
`published/qa/template_style_map.md`.
For cover or fixed-template field questions, inspect
`template_field_fill_report_path`; the published package includes
`published/qa/template_field_fill_report.json` and
`published/qa/template_field_fill_report.md`.

## Revise Existing

In `revise_existing` mode, `section_drafts/*.md` are not merged into the final
document. Write `revision_plan.json` with exact `original_text` spans and
replacement text. Call `submit_revision_plan` before final publish.

If a validation failure points to stale base-document content, invalidate caches
through the CLI:

```powershell
report-workflow invalidate-cache --job-id <id> --sources --drafts
```

## Validation Failures

Read the gate name and fix the canonical source artifact:

- Claim failures: edit `claim_matrix.json`.
- Evidence support failures: edit `claim_matrix.json` or improve
  `evidence_ledger.jsonl` content.
- Citation failures: edit section drafts and `sentence_map.jsonl`.
- Section contract failures: edit `outline.json` or the relevant section draft.
- Artifact shape failures: inspect `artifact_lint_report.json` first; it points
  to the artifact and JSON path that should be edited.
- Engineering unit/calculation findings: inspect `engineering_audit_report.json`.
- Render failures: fix Markdown structure, tables, figures, or template issues.

For factuality failures, delete stale `factuality_report.json`, rerun validate,
then inspect the fresh report.

## CLI Equivalents

```powershell
report-workflow prepare --prompt "..." --source source.pdf --profile engineering_lab_report --output output --preflight-decisions preflight_decisions.json
report-workflow validate --job-id <job_id> --verbose
report-workflow render --job-id <job_id>
report-workflow status --job-id <job_id>
report-workflow diagnose --job-id <job_id> --verbose
```

Use `--profile`; do not use the removed `--family` option. CLI `prepare`
requires the same explicit user preflight decision record as `start_report_task`.
