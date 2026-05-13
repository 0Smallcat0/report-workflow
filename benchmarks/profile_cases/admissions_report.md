# Benchmark Case: admissions_report

## Reference Signals

- Admissions-facing writing should be focused, informative, and connected to
  research interests, qualifications, motivation, and career objectives.
- Personal context may matter, but it should complement rather than duplicate
  purpose-driven research and qualification evidence.
- For research programs, evidence of research potential and meaningful research
  experience should be foregrounded.

Primary rubric sources:

- Harvard Griffin GSAS, Statement of Purpose:
  https://gsas.harvard.edu/apply/applying-degree-programs/statement-purpose-personal-statement-and-writing-sample
- Harvard SEAS, Computer Science graduate application advice:
  https://seas.harvard.edu/news/what-know-you-apply-graduate-school-computer-science

## Controlled Run

- Fixture: `benchmarks/fixtures/controlled_source.md`
- Prompt: `Write an admissions-facing scholarly report about the structured workflow project.`
- Profile: `admissions_report`
- Required QA to inspect: `scholarly_quality_report.json`,
  `admissions_tone_report.json`, `final_qa_summary.json`, and tone/fit in the
  final DOCX.

## Expected Output

- Frames the project as evidence of research readiness and technical judgment.
- Explains motivation and career direction through the project evidence rather
  than autobiographical filler.
- Maintains a serious scholarly report structure while avoiding journal-only
  metadata that would distract admissions readers.
- Names limitations and learning from the pilot without overstating admission
  fit.
- Avoids generic praise, committee flattery, or unsupported personal claims.

## Gap Categories To Check

Use the fixed categories from `benchmarks/README.md`; most failures here should
fall into `skill_guidance_gap`, `profile_policy_gap`, or
`agent_authoring_gap`.
