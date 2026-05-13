# Benchmark Case: business_report

## Reference Signals

- Business reports vary by purpose and audience, but formal versions typically
  include preliminary material, an executive summary, findings,
  recommendations, references, and appendices where needed.
- Executive summaries should give the aim, work performed, main findings,
  conclusions, and recommendations without detailed tables or references.
- The body should connect problem, investigation, findings, and actionable
  recommendations.

Primary rubric sources:

- Monash Student Academic Success, Business report writing:
  https://www.monash.edu/student-academic-success/excel-at-writing/annotated-assessment-samples/business-and-economics/buseco-report-writing
- BCcampus Technical Writing Essentials, Recommendation and Feasibility
  Reports:
  https://opentextbc.ca/technicalwritingh5p/chapter/long-reports-recommendation-reports-and-feasibility-studies/

## Controlled Run

- Fixture: `benchmarks/fixtures/controlled_source.md`
- Prompt: `Write a business report recommending whether to adopt the structured workflow.`
- Profile: `business_report`
- Required QA to inspect: `final_qa_summary.json`,
  `figure_visual_quality_report.json`, `template_style_map.json`, and the
  executive summary text.

## Expected Output

- Opens with a concise executive summary aimed at a decision-maker.
- States the decision problem and compares baseline/manual vs structured
  workflow evidence.
- Converts findings into recommendations with constraints and implementation
  risks.
- Uses charts or tables only when they clarify the decision.
- Avoids academic article boilerplate and excessive literature framing.

## Gap Categories To Check

Use the fixed categories from `benchmarks/README.md`; most failures here should
fall into `skill_guidance_gap`, `agent_authoring_gap`, or
`render_template_gap`.
