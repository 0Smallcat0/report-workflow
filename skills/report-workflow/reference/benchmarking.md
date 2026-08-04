# Benchmark-First Optimization

Load this reference **only** when the task is to improve `report-workflow` itself.
Ordinary report generation should continue through the normal start, author,
validate, render, and publish flow and never carry this as extra burden.

When asked to improve report quality across report types, start from the
repo-local benchmark contract before changing the skill or Python pipeline:

1. Read `benchmarks/README.md`, `benchmarks/report_quality_matrix.md`, and
   `benchmarks/findings.json`.
2. Read the profile packet under `benchmarks/profile_cases/` for the active
   `report_profile`.
3. Treat public sample reports, rubrics, journal instructions, and admissions or
   business guidance as reference-only quality context. They are never
   `source_data`, and must not be copied into generated reports as prose,
   headings, page design, figures, or universal style rules.
4. Run or design one controlled case per profile. Use
   `benchmarks/fixtures/controlled_source.md` for smoke coverage when no user
   source exists. For full built-in profile coverage, run
   `python scripts/run_report_benchmarks.py`. The full benchmark also uses
   `benchmarks/fixtures/chart_*.csv` to exercise deterministic bar, line, scatter,
   boxplot, and table-fallback source-data figure guidance. Use
   `python scripts/run_report_benchmarks.py --check` to validate archived
   benchmark evidence without rerunning the workflow.
5. Inspect the relevant QA artifacts for the profile: `final_qa_summary`,
   `scholarly_quality_report`, `figure_visual_quality_report`, `template_style_map`,
   and profile-specific reports such as `engineering_audit_report`,
   `admissions_tone_report`, or `reference_relevance_report`.
6. Classify every finding with exactly one benchmark category from
   `benchmarks/findings.json`: `skill_guidance_gap`, `profile_policy_gap`,
   `deterministic_pipeline_gap`, `render_template_gap`, `agent_authoring_gap`, or
   `external_reference_gap`.
7. Implement only high-confidence changes after the benchmark evidence is written.
   Prefer `skills/report-workflow` guidance, benchmark artifacts, and regression tests before
   Python pipeline changes. Add or tighten deterministic hard gates only when
   repeated benchmark evidence shows the current QA artifacts cannot express the
   quality failure.

Preserve `report_profile` as the only public report-shape selector. Benchmark
work must not introduce `report_family`, subtype, detail, variant, or
sample-specific public options.
