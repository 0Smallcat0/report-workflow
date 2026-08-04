# Report Quality Benchmarks

This directory is the benchmark-first contract for improving
`report-workflow`. It is for workflow and skill maintenance, not for ordinary
report production.

## Purpose

Use these files when evaluating whether the skill or deterministic pipeline
should change. The benchmark process converts public report-writing guidance
into profile-specific rubrics, runs or designs controlled report cases, then
classifies gaps before any implementation work.

The benchmark rule is strict: references define quality criteria only. Do not
copy sample report prose, headings, formatting, or visual style into generated
reports unless the user supplied that template for their own report.

## Files

- `report_quality_matrix.md` summarizes profile-level quality expectations.
- `findings.json` records the current benchmark classification and ranked
  actions.
- `prepare_smoke.md` records the latest prepare-stage smoke across all built-in
  profiles.
- `evidence/full_benchmark_2026-05-13/summary.json` records the latest full
  controlled prepare-author-validate-render benchmark across all built-in
  profiles.
- `profile_cases/*.md` provides one controlled benchmark packet for each
  built-in `report_profile`.
- `fixtures/controlled_source.md` is a small synthetic source fixture that can
  be reused for smoke runs.
- `fixtures/chart_*.csv` are small deterministic chart fixtures that exercise
  bar, line, scatter, boxplot, and table-fallback recommendation paths through
  figure recommendation, plan audit, figure build, and visual-quality reporting.
- `../scripts/run_report_benchmarks.py` reruns the full controlled benchmark and
  refreshes compact QA snapshots. Use
  `python scripts/run_report_benchmarks.py --check` to verify archived evidence
  without rerunning the workflow.

## Gap Categories

Use only these categories when recording benchmark findings:

- `skill_guidance_gap`: the agent-facing skill does not tell the author how to
  make the right decision.
- `profile_policy_gap`: profile strictness or policy defaults do not match the
  intended report type.
- `deterministic_pipeline_gap`: deterministic parsing, validation, rendering,
  or packaging cannot express a needed quality signal.
- `render_template_gap`: the DOCX/template/render surface loses or distorts a
  required layout or style property.
- `agent_authoring_gap`: the agent wrote weak artifacts even though the current
  workflow contract was sufficient.
- `external_reference_gap`: the run lacked a credible external source,
  standard, or domain reference needed for the report's claims.

## Benchmark Loop

1. Select a single `report_profile`.
2. Read the matching `profile_cases/*.md` packet and the source fixture.
3. Run the normal workflow with that profile when feasible, or run
   `python scripts/run_report_benchmarks.py` for full controlled coverage.
   Preserve the resulting QA outputs outside ignored runtime folders when they
   are evidence for a durable change.
4. Compare `final_qa_summary`, `scholarly_quality_report`,
   `figure_visual_quality_report`, `template_style_map`, and the final DOCX
   against the packet rubric.
5. Classify every gap using the fixed categories above.
6. Implement only high-confidence changes. Prefer `skills/report-workflow` guidance and
   benchmark tests before changing core Python nodes.
7. Update `findings.json` and the profile packet with what changed, what stayed
   backlog, and what should not be changed.

## Source Policy

Accepted references are public, stable guidance from universities, journals,
governments, standards bodies, or similarly credible institutions. Prefer
rubrics and author instructions over isolated samples. When a sample is used,
extract only generalized criteria such as section purpose, evidence behavior,
figure/table expectations, and audience/tone.

Do not use benchmark references as `source_data` for a user report. They are
reference-only quality context.
