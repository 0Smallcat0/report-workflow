# Benchmark Case: proposal

## Reference Signals

- Proposals are persuasive but should remain logical, credible, concrete, and
  audience-aware.
- Strong proposals define the problem, scope the project, show benefits and
  feasibility, and include practical details such as timeline, budget,
  resources, risks, and evaluation.
- Graphics should clarify the plan, budget, or timeline rather than decorate
  the pitch.

Primary rubric source:

- BCcampus Technical Writing Essentials, Proposals:
  https://opentextbc.ca/technicalwritingh5p/chapter/proposals/

## Controlled Run

- Fixture: `benchmarks/fixtures/controlled_source.md`
- Prompt: `Write a proposal to pilot the structured workflow for a small academic lab.`
- Profile: `proposal`
- Required QA to inspect: `final_qa_summary.json`,
  `figure_visual_quality_report.json`, `template_style_map.json`, and the
  budget/timeline sections.

## Expected Output

- Defines the problem and target audience before pitching the solution.
- Includes objectives, scope/deliverables, timeline, budget/resources, risks,
  mitigation, and evaluation.
- Uses the USD 4,800 and six-week fixture values without inventing extra budget
  lines or dates.
- Acknowledges training risk and one-week shadow period.
- Avoids advertisement-like language unsupported by evidence.

## Gap Categories To Check

Use the fixed categories from `benchmarks/README.md`; most failures here should
fall into `skill_guidance_gap`, `external_reference_gap`, or
`agent_authoring_gap`.
