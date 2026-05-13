# Benchmark Case: engineering_lab_report

## Reference Signals

- Lab reports should state the hypothesis or question, describe methods,
  present observations/results, analyze the data, and conclude from the tested
  evidence.
- Methods need enough detail for replication, including apparatus, procedure,
  units, and limitations.
- Results should present honest data with tables or charts where useful; the
  discussion interprets the result and can acknowledge contradictory or
  inconclusive data.

Primary rubric sources:

- BCcampus Technical Writing Essentials, Lab Reports:
  https://opentextbc.ca/technicalwritingh5p/chapter/lab-reports/
- GMU Writing Center, IMRaD overview:
  https://writingcenter.gmu.edu/writing-resources/imrad/writing-an-imrad-report

## Controlled Run

- Fixture: `benchmarks/fixtures/controlled_source.md`
- Prompt: `Write an engineering lab report from the synthetic controlled source.`
- Profile: `engineering_lab_report`
- Required QA to inspect: `engineering_audit_report.json`,
  `scholarly_quality_report.json`, `figure_visual_quality_report.json`,
  `final_qa_summary.json`, and the rendered DOCX pages.

## Expected Output

- Preserves objectives, apparatus/procedure, data, calculations,
  results/discussion, conclusion, and references/appendix when supported.
- Uses table/chart output only from the accepted fixture values.
- Separates measured results from interpretation and limitations.
- Includes units for processing time and error/satisfaction percentages.
- Avoids personal reflection unless explicitly required by the user.

## Gap Categories To Check

Use the fixed categories from `benchmarks/README.md`; most failures here should
fall into `skill_guidance_gap`, `deterministic_pipeline_gap`,
`render_template_gap`, or `agent_authoring_gap`.
