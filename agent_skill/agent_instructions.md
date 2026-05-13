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
2. **Author**: the agent uses the controlled harness by default:
   `get_controlled_next_action` returns the current task, read-first files,
   and allowed write paths; `submit_controlled_action` validates that stage and
   records evidence in `harness_manifest.json`.
3. **Validate and render**: `submit_and_publish_report` validates contracts,
   evidence support, citations, section rules, profile policy, and render
   quality before publishing the DOCX. Successful render validation writes a
   `post_render_layout_manifest.json` audit artifact with renderer, file size,
   paragraph/table/figure counts, headings, table previews, related render QA
   reports, and issues.
   Publish packaging writes `final_qa_summary.json` and
   `final_qa_summary.md` to consolidate QA gate, factuality, artifact lint,
   engineering audit, scholarly-quality review, chart visual-quality review,
   and render-layout evidence for delivery review.
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
Choose one dominant report convention from the prompt and sources, then use any
secondary conventions only as supporting cues. Do not blend every built-in
profile into one report shape.

## Benchmark-First Optimization

Use this workflow only when the task is to improve `report-workflow` itself.
Do not use it as an extra burden during ordinary report generation.

When evaluating quality improvements across report types:

1. Read `benchmarks/README.md`, `benchmarks/report_quality_matrix.md`, and
   `benchmarks/findings.json`.
2. Read the profile packet under `benchmarks/profile_cases/` for the active
   `report_profile`.
3. Use public report examples, rubrics, journal instructions, and admissions or
   business guidance only to extract quality criteria. They are reference-only
   context, never `source_data`, and they must not be copied into generated
   reports as prose, headings, page design, figures, or universal style rules.
4. Run or design one controlled case per profile. Use
   `benchmarks/fixtures/controlled_source.md` for smoke coverage when no user
   source exists. For full built-in profile coverage, run
   `python scripts/run_report_benchmarks.py` and preserve useful QA evidence
   outside ignored runtime folders before changing behavior. The full benchmark
   also uses `benchmarks/fixtures/chart_*.csv` to exercise deterministic bar,
   line, scatter, boxplot, and table-fallback source-data figure guidance. Use
   `python scripts/run_report_benchmarks.py --check` to validate archived
   benchmark evidence without rerunning the workflow.
5. Inspect the relevant QA artifacts for the profile: `final_qa_summary`,
   `scholarly_quality_report`, `figure_visual_quality_report`,
   `template_style_map`, and profile-specific reports such as
   `engineering_audit_report`, `admissions_tone_report`, or
   `reference_relevance_report`.
6. Classify every finding with exactly one of the benchmark categories:
   `skill_guidance_gap`, `profile_policy_gap`,
   `deterministic_pipeline_gap`, `render_template_gap`,
   `agent_authoring_gap`, or `external_reference_gap`.
7. Implement only high-confidence changes after the benchmark evidence is
   written. Prefer `agent_skill` guidance, benchmark artifacts, and regression
   tests before Python pipeline changes. Add or tighten deterministic hard
   gates only when repeated benchmark evidence shows the current QA artifacts
   cannot express the quality failure.

Keep `report_profile` as the only public report-shape selector. Benchmark work
must not introduce `report_family`, subtype, detail, variant, or
sample-specific public options.

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
For admissions profiles, pass explicit `project_identity` when the report must
preserve named project terms, domain context, forbidden drift terms, or author
metadata. Do not infer an admissions project spine from a previous benchmark or
unrelated project; keep the supplied identity terms visible in the title/thesis,
introduction, and conclusion.
Keep admissions evidence anchored to the supplied source record: research fit,
readiness, project significance, and contribution claims need concrete source
support, not committee flattery or unsupported autobiography.

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

When validation sees `structured_drafts.json` and the canonical draft files are
missing, the pipeline writes `section_drafts/*.md`, inserts `[CITE:]`
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
`base_document_sections.json`, publication outputs, or checkpoint JSON. Edit
only the agent-owned artifacts allowed by the current harness stage and rerun
validation.

Avoid:

- placeholder text such as `This section is under development`
- `[Source:]`, `[graphify:]`, `[Note:]`, or other internal markers in body prose
- raw evidence IDs outside `[CITE:]`
- internal file paths in report prose
- ASCII-art diagrams; use Mermaid or real image assets instead

For `academic_paper` and `engineering_lab_report`, make Methods/Procedure
reproducible: name the source or sample basis, procedure, parameters or
instrument/software settings, and supported inclusion, exclusion, calibration,
normalization, or transform rules. In academic introductions, explicitly signal
the problem or gap, objective, and contribution before moving to results.

## Non-Quantitative Figures vs Data Charts

This guidance applies only while generating or revising a report with
`report-workflow`. For standalone image, diagram, or slide requests, use the
appropriate visual skill directly instead of broadening this workflow.

Actively choose the visual surface before drafting. Do not wait for the user to
ask for a figure when a non-quantitative visual would make a method, mechanism,
setup, workflow, architecture, or concept easier to understand.

- Data charts: use only accepted `source_data` values, plotted comparisons,
  scored matrices, axes, or source-backed quantitative claims and the
  deterministic path through `figure_recommendations.json`,
  `section_drafts/figure_plan.json`, `FIGURE_PLAN_AUDIT`, and `FIGURE_BUILD`.
  Do not replace source-data-backed charts, tables, plotted values, materiality
  matrices, rankings, or quantitative comparisons with AI-generated images.
- Mermaid diagrams: use for editable flow/process/architecture/decision,
  sequence, or state diagrams.
- Academic, engineering, or corporate illustrations: use image generation or
  request an illustration asset when the report needs a polished
  non-quantitative schematic rather than an editable diagram.

Compact taxonomy for non-quantitative illustration assets:

- Academic/scientific: graphical abstract, method pipeline, mechanism/pathway,
  multi-scale or nested view, lifecycle/cycle, qualitative condition comparison,
  or conceptual framework.
- Engineering: apparatus/test setup, system or control architecture, test bench
  workflow, device/material cross-section, or safety/operation concept.
- Business-report/corporate-report: value chain, value creation model, business
  model or capability map, process map/swimlane/BPMN-lite,
  stakeholder/ecosystem map, roadmap/change journey, or qualitative
  risk/control/materiality map.

Profile defaults:

- `engineering_lab_report`: use non-quantitative illustrations selectively for
  apparatus/setup, experiment workflow, control/system architecture, test bench
  workflow, cross-section, safety concept, or operation concept.
- `business_report`, `proposal`, `admissions_report`,
  `admissions_project_report`, and `custom`: proactively consider 1-2 value
  chain, concept map, roadmap, stakeholder/ecosystem, process overview, or
  operating-model visuals when they improve readability and do not claim data.
- `academic_paper`: use only publication-style graphical abstract, method,
  mechanism, conceptual, or multi-scale figures that do not imply unsupported
  results.

When Codex image generation or the `imagegen` skill is available and the user
expects a complete report, generate the non-quantitative illustration asset
instead of leaving only a prompt. If image generation is unavailable, write the
reusable prompt and mark the figure as pending external asset creation.

Generated illustration insertion contract:

- Save or copy generated PNG assets into the current run directory under
  `figures/<descriptive_slug>.png`; leave the original generated image in place.
- Embed these assets directly in the relevant `section_drafts/*.md` with
  Markdown image syntax such as
  `![Schematic - Apparatus setup](figures/apparatus_setup.png)`.
- Do not add direct imagegen assets to `section_drafts/figure_plan.json`,
  outline `figure_ids`, or `[FIGURE:<id>]` placeholders. Those are for
  deterministic `FIGURE_BUILD` manifest-backed charts unless the workflow
  explicitly produced a matching manifest entry.
- Avoid numbered prose references such as "Figure 1" for direct imagegen assets
  unless they are backed by an existing outline/manifest figure ID. Use nearby
  wording such as "the schematic below" plus a short unnumbered caption.

AI academic, engineering, or corporate illustrations are illustrative only. They
must not invent numeric values, axes, tick marks, color-scale ranges, equations,
measured outcomes, comparison results, rankings, scores, experimental results,
or source-backed claims. If the visual requires plotted measurements, scored
positions, or evidence-backed priorities, use the deterministic chart path or
keep the exact values in a table.

Prompt pattern for a non-quantitative illustration:

```text
Goal/concept: <one-sentence concept the figure explains>
Visual family: <academic/scientific | engineering | business-report/corporate-report>
Figure type (examples, non-exhaustive): <apparatus setup | test bench workflow |
device/material cross-section | safety/operation concept | method pipeline |
system/control architecture | scientific schematic | mechanism/pathway |
multi-scale/nested view | lifecycle/cycle | graphical abstract | value chain |
value creation model | business model/capability map |
process map/swimlane/BPMN-lite | stakeholder/ecosystem map |
roadmap/change journey | qualitative risk/control/materiality map |
concept illustration>
Layout style: <linear | circular | parallel | nested | storyboard | map/network>
Audience: <technical reviewers | lab instructor | executives | admissions reviewers>
Required labels: <labels that are source-supported or explicitly requested>
Source basis: <accepted source ids, user instructions, or "conceptual only">
Evidence boundary: <what the visual may explain, and what it must not claim>
Forbidden content: no fabricated data, axes, tick marks, color scales,
equations, measured outcomes, rankings, scores, comparison results,
experimental results, or claims not present in the sources
Style: white background, publication font, precise geometry, muted palette,
3-4 colors maximum, clear visual hierarchy, readable in grayscale
```

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

## Controlled Submission

Preferred sequence:

1. Call `get_controlled_next_action(job_id=...)`.
2. Read the returned `task_brief_path` and `read_first_paths`.
3. Edit only files listed in `allowed_write_paths`.
4. Call `submit_controlled_action(job_id=...)`.
5. Repeat until the returned `status` is `completed`.

When `submit_controlled_action` returns `validation_failed`, repair only
`allowed_repair_paths` using `repair_context`. When it returns
`scope_violation`, restore or isolate out-of-scope artifact changes and retry
the same stage. Do not manually advance stages by editing
`harness_manifest.json`.
When it returns `blocked_non_author_repair`, inspect the evidence paths and
stop editing author artifacts for that stage; the failure needs a workflow,
source, environment, or deterministic-code fix outside the controlled authoring
surface.

Optionally call `lint_agent_artifacts(job_id=...)` after edits or before full
validation to catch shape errors and ID drift early. For
`engineering_lab_report`, call `run_engineering_audit(job_id=...)` after drafts
exist to check units, table-value support, measurement support, and simple
calculations. Call `submit_and_publish_report(job_id=...)` when the controlled
harness reaches the publish stage or all required artifacts are already present.

When `submit_and_publish_report` succeeds, use
`post_render_layout_manifest_path` if you need evidence about final DOCX
structure. The same file is packaged under
`published/qa/post_render_layout_manifest.json` when present.
For delivery readiness, inspect `final_qa_summary_path` first. It is packaged
with a Markdown sibling under `published/qa/final_qa_summary.json` and
`published/qa/final_qa_summary.md`.
For academic and engineering scholarly structure review, inspect
`scholarly_quality_report_path`; the published package includes
`published/qa/scholarly_quality_report.json` and
`published/qa/scholarly_quality_report.md`.
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
document. Use `get_controlled_next_action` until the harness returns the
`revision_plan` stage, then write `revision_plan.json` with exact
`original_text` spans and replacement text inside the allowed write scope.
Use `preview_revision_diff` as an optional read-only check, then call
`submit_controlled_action` to validate and advance. `submit_revision_plan`
remains a compatibility helper, not the default authoring path.

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
