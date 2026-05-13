# Benchmark Case: admissions_project_report

## Reference Signals

- Admissions project reports should show research potential through concrete
  project decisions, obstacles, evidence handling, and learning.
- They should connect the project to future graduate direction without becoming
  a personal statement or a rigid faculty-targeting essay.
- Project evidence can be internal when it directly supports the candidate's
  work and the profile allows relaxed publication metadata.

Primary rubric sources:

- Harvard Griffin GSAS, Statement of Purpose:
  https://gsas.harvard.edu/apply/applying-degree-programs/statement-purpose-personal-statement-and-writing-sample
- Harvard SEAS, Computer Science graduate application advice:
  https://seas.harvard.edu/news/what-know-you-apply-graduate-school-computer-science

## Controlled Run

- Fixture: `benchmarks/fixtures/controlled_source.md`
- Prompt: `Write an admissions project report showing what the structured workflow project demonstrates.`
- Profile: `admissions_project_report`
- Required QA to inspect: `reference_relevance_report.json`,
  `project_identity_report.json`, `final_qa_summary.json`, and final tone.

## Expected Output

- Shows the project problem, design choices, evidence boundaries, QA decisions,
  and limitations.
- Connects the project to graduate readiness and future research direction.
- Uses internal project evidence without pretending it is peer-reviewed
  literature.
- Avoids unnecessary publication metadata and venue-style claims.
- Avoids over-specific professor or lab targeting unless the user supplies it.

## Gap Categories To Check

Use the fixed categories from `benchmarks/README.md`; most failures here should
fall into `skill_guidance_gap`, `profile_policy_gap`, `external_reference_gap`,
or `agent_authoring_gap`.
