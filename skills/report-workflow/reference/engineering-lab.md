# Engineering Lab Reports

Load this reference when `report_profile` is `engineering_lab_report`. The
profile is the highest-priority semantic contract, above prompt or template
details. The built-in `CHINESE_ENGINEERING` guideline is selected by default.

## Contents

- [Profile Expectations](#profile-expectations)
- [Source and Evidence Boundaries](#source-and-evidence-boundaries)
- [External Reference / Database Lookup](#external-reference--database-lookup)
- [Reference DOCX and Exact-Cover Behavior](#reference-docx-and-exact-cover-behavior)
- [Figure and Table Hard Gates](#figure-and-table-hard-gates)
- [Symbols, Units, and Notation](#symbols-units-and-notation)
- [Chinese Engineering Publish Checklist](#chinese-engineering-publish-checklist)

## Profile Expectations

Treat SOPs, lab handouts, measurement sheets, and rubrics as first-class sources.
The report should preserve:

- Required Chinese lab-report sections.
- Experiment purpose, theory, apparatus, procedure, results, discussion,
  conclusion/reflection, and references.
- Requirement matrix coverage.
- Formula variables, parameters, symbols, units, and calculation assumptions.
- Calculation audit expectations.
- Figure/table numbering, references, and contracts.
- Question-and-answer requirements from the handout.
- Chinese report tone without agent/workflow jargon or mojibake.
- Render QA for cover/template drift, table compression, and image placement.

Call `run_engineering_audit` before publish when the report contains measured
values, formulas, or calculations. It writes `engineering_audit_report.json` with
recognized measurements, claim/evidence unit-support warnings, unit notation
warnings, table-value support checks, mixed-dimension unit notes, missing-unit
notes, and simple calculation result warnings. The audit tolerates page labels,
adjacent engineering units, and small rounding differences between prose and
table values; remaining warnings still need human review before you change claim
wording.

## Source and Evidence Boundaries

Only introduce experiment conditions, comparison groups, measured values, and
calculated results supported by the accepted `source_data` ledger. Do not infer
extra fan speeds, trial groups, or comparison rows from examples, reference-only
images, or similar prior reports.

Keep an explicit source-role ledger before drafting: `source_data`,
`base_document`, template/reference-format files, and reference-only context.
Only `source_data` may support measured values, calculated results, experiment
conditions, comparison groups, charts, or tables. Reference-only files may inform
terminology or expected discussion scope, but their numbers must not enter the
evidence ledger, calculations, figures, body text, or references.

## External Reference / Database Lookup

For domain-specific tables, charts, standards, calculators, or external
databases, prefer the user-supplied sources first. If a supplied scan or table is
not readable enough for a reliable value, state that limitation instead of
fabricating precise numbers.

If the user requests or allows external lookup, record the external source,
access date, input basis/units, mapping between source fields and report
quantities, assumptions, representative point, and calculation formulas. Label
derived values as estimates and use conservative significant figures. Per-unit or
normalized values may support per-unit comparisons, but aggregate totals require
the relevant scaling variable to be measured or explicitly supplied. Keep
external references separate from experiment measurements; cite them directly and
use them only for the specific theory/property/standard claim.

## Reference DOCX and Exact-Cover Behavior

- User-specified mode wins; the default is `style_reference`.
- If the prompt asks to exactly match the format or cover, use `fixed_template`.
- If a school cover must be copied exactly, treat the cover as a template-copy
  operation, not style imitation. Validate content through the workflow, then
  verify the final DOCX with a fixed-template render or a template-copy
  post-render pass and visual page QA. Inspect the cover page, tables, charts, and
  Chinese text before delivery.
- When the user says to copy a cover exactly and change only selected fields,
  preserve the original first-page OOXML paragraphs/runs and section properties;
  replace text inside existing runs where possible. Do not run global font,
  margin, paragraph-spacing, or style-normalization helpers over those cover
  paragraphs. If the body needs different styles, build or patch the body after
  the cover boundary, or splice a separately generated body behind the preserved
  cover.
- Exact-cover verification is a hard gate. Compare the copied cover against the
  template at the OOXML level after normalizing only the allowed field values
  such as title/date; the first-page paragraph order, run properties, font sizes,
  spacing, and section properties must otherwise match. Then render both the
  template and candidate DOCX and visually compare page 1. Text extraction or
  "same visible words" alone is not evidence that the cover was copied.
- When a reference DOCX is supplied for the whole report format, inspect body
  paragraphs, captions, tables, page margins, font sizes, and rendered page
  density from the reference; do not validate only the cover page.
- If the final document is generated or repaired outside the workflow renderer,
  rerun a template/style comparison after that post-render pass.

## Figure and Table Hard Gates

Treat these as hard gates before delivery:

- A figure caption or figure reference requires a real nearby embedded visual.
  Verify the final DOCX contains drawing/image objects and visually inspect the
  rendered PNG pages; extracted text showing a figure title is not enough.
- Build charts only from accepted `source_data`. Each chart needs one visible
  chart, a caption below it, labeled axes with units where applicable, and
  readable legends.
- Axis order must match the prose claim. If the text says a reading decreases as
  distance increases, the plotted distance axis should increase left-to-right
  unless the report explicitly explains a reversed axis. Captions, prose, and
  plotted direction must agree.
- Schematic labels must not overlap blocks, arrows, or plotted data. For compact
  DOCX figures, prefer labels outside shapes with leader lines.
- Use consistent total table width and readable padding for tables with the same
  report role. Render-check awkward page breaks, orphaned captions, and single-row
  table leftovers before delivery.
- Generated charts write `figure_visual_quality_report.json` with review-only
  checks for overlapping labels, legend placement, and heatmap density.
- Supported generated chart types: `bar`, `line`, `scatter`, `pie`, `table`,
  `histogram`, `boxplot`, `heatmap`, `error_bar`, and `stacked_bar`. Prefer the
  deterministic recommendation, and keep exact values as a table when the visual
  mapping is ambiguous.
- If a recommended starter chart contains `data_transform`, keep that metadata and
  chart payload unless you intentionally replace the derived view. The
  deterministic layer may have already handled group-by, pivot, wide-to-long,
  percent-of-total, sorting, or top-N cleanup; manual replacements need a specific
  `chart_selection_reason`.

## Symbols, Units, and Notation

- Use publication-ready engineering notation: table headers use `Name (unit)`
  formatting such as `P (kPa)` and `T (°C)`; formulas and prose use proper
  subscript notation through Word subscript runs or stable Unicode subscripts.
- Scan for mixed unit formats, raw underscores, broken symbol wraps, or missing
  degree symbols before delivery.
- Keep symbol semantics distinct: do not reuse the same symbol for quantities with
  different units or meanings. Add qualifiers such as rate, per-unit, average,
  nominal, measured, or estimated when needed. If a derived indicator is unusually
  high or conflicts with the primary measured result, frame it as an estimate,
  list the assumptions and likely error sources, and keep the source-supported
  measured result as primary unless the data justify otherwise.

## Chinese Engineering Publish Checklist

- `lint_agent_artifacts` has no errors and citation IDs match the current run.
- `run_engineering_audit` has been reviewed for unit support, table-value support,
  measured values, and simple calculations. Page labels, adjacent engineering
  units, and rounded table values are tolerated; review remaining warnings before
  changing claim wording.
- The draft covers the lab handout/SOP requirements, required questions,
  apparatus/procedure, results, discussion, conclusion/reflection, and references.
- Formula variables, parameters, units, table numbers, figure numbers, and prose
  references are consistent.
- Engineering symbols and units are publication-ready (see above).
- Every figure caption or reference has a nearby embedded visual, and the rendered
  PNG page shows the actual chart/image rather than only a caption or placeholder.
- Chinese prose is natural and contains no workflow/agent jargon, placeholder
  text, mojibake, or raw internal file paths.
- Delivery prose does not expose internal provenance labels such as page
  transcription notes, `source_notes`, local filenames, image names, or agent
  workflow artifacts unless the user requests a traceability appendix.
- If the user supplies forbidden phrases, source-use constraints, or known-bad
  comparison labels, scan the final DOCX text for them after any post-render edit.
- Template fields such as course, student ID, instructor, lab section, date, and
  department are supplied when the school/company template expects them.
- Before delivery, inspect `final_qa_summary_path`, then
  `scholarly_quality_report_path`, `template_field_fill_report_path`,
  `template_style_map_path`, and `post_render_layout_manifest_path` when returned.
