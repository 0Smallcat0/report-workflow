# Benchmark Case: custom

## Reference Signals

- Custom reports should choose a dominant rhetorical purpose rather than blend
  every possible report convention.
- Hybrid or white-paper-style reports should keep a problem-solution structure,
  use objective tone, cite authoritative evidence, and make recommendations
  only after the evidence and criteria justify them.
- Recommendation and feasibility reports need explicit criteria, options,
  analysis, conclusions, and recommendations.

Primary rubric sources:

- GMU Writing Center, White Papers:
  https://writingcenter.gmu.edu/writing-resources/different-genres/white-papers
- BCcampus Technical Writing Essentials, Recommendation and Feasibility
  Reports:
  https://opentextbc.ca/technicalwritingh5p/chapter/long-reports-recommendation-reports-and-feasibility-studies/

## Controlled Run

- Fixture: `benchmarks/fixtures/controlled_source.md`
- Prompt: `Write a custom hybrid report that explains and evaluates the structured workflow pilot.`
- Profile: `custom`
- Required QA to inspect: `final_qa_summary.json`,
  `figure_visual_quality_report.json`, `template_style_map.json`, and final
  section coherence.

## Expected Output

- Selects one dominant shape, such as white paper, recommendation report, or
  hybrid technical summary.
- States the criteria for judging the structured workflow.
- Separates evidence, interpretation, and recommendation.
- Keeps citation and metadata requirements lighter than `academic_paper` unless
  the user asks for publication style.
- Avoids incoherent mixtures of academic, business, proposal, and admissions
  conventions.

## Gap Categories To Check

Use the fixed categories from `benchmarks/README.md`; most failures here should
fall into `skill_guidance_gap`, `profile_policy_gap`, or
`agent_authoring_gap`.
