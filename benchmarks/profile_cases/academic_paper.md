# Benchmark Case: academic_paper

## Reference Signals

- Academic papers commonly use IMRaD as a base structure, but the structure
  must still follow the audience and venue.
- The introduction should motivate the problem and gap; methods should support
  reproducibility; results should report findings; discussion should interpret
  them.
- Journal-grade output should handle references, methods detail, figure
  captions, author contributions, competing interests, data availability, or
  similar metadata when the venue requires them.

Primary rubric sources:

- Purdue OWL, Organization and Structure:
  https://owl.purdue.edu/owl/graduate_writing/graduate_writing_topics/graduate_writing_organization_structure_new.html
- Nature Scientific Reports submission guidelines:
  https://www.nature.com/srep/author-instructions/submission-guidelines
- MIT Communication Lab, Methods and Results guidance:
  https://mitcommlab.mit.edu/be/commkit/journal-article-methods/
  and https://mitcommlab.mit.edu/eecs/commkit/journal-article-results/

## Controlled Run

- Fixture: `benchmarks/fixtures/controlled_source.md`
- Prompt: `Write an academic paper evaluating the structured workflow pilot.`
- Profile: `academic_paper`
- Required QA to inspect: `scholarly_quality_report.json`,
  `reference_reality_report.json`, `figure_visual_quality_report.json`,
  `final_qa_summary.json`, and rendered references/figures.

## Expected Output

- Uses a thesis/gap/contribution spine rather than a generic report summary.
- Reports the pilot values objectively in Results and reserves interpretation
  for Discussion.
- Provides reproducible method detail without author-centered wording.
- Treats the fixture as pilot evidence, not a publication-grade general claim.
- Does not invent DOI, data availability, ethics, or conflict declarations.

## Gap Categories To Check

Use the fixed categories from `benchmarks/README.md`; most failures here should
fall into `profile_policy_gap`, `external_reference_gap`,
`deterministic_pipeline_gap`, or `agent_authoring_gap`.
