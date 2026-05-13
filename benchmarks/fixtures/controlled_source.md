# Synthetic Controlled Source Fixture

This fixture is synthetic and exists only to test report-shape behavior across
profiles. It is not a real client, lab, admissions, or business source.

## Project Context

The pilot project tested a document intake workflow for a small academic lab.
The workflow converted intake notes into a structured evidence ledger, a claim
matrix, and a final DOCX report package.

## Measurements

| condition | participants | median_processing_minutes | error_rate_percent | reviewer_satisfaction_percent |
| --- | ---: | ---: | ---: | ---: |
| baseline_manual | 42 | 28 | 7.5 | 71 |
| structured_workflow | 42 | 20 | 4.1 | 84 |

## Procedure

1. Collect intake notes from the same 42 participants.
2. Process each note once with the baseline manual method.
3. Process each note once with the structured workflow.
4. Compare median processing time, detected error rate, and reviewer
   satisfaction.

## Constraints

- The study is a pilot and should not be generalized beyond the tested intake
  workflow.
- Processing time was measured in minutes per note.
- Error rate was measured as the percentage of notes needing reviewer repair.
- Reviewer satisfaction was collected on a post-run survey and should be
  treated as supportive, not primary, evidence.

## Proposal Inputs

- Estimated implementation effort: six weeks.
- Estimated direct setup cost: USD 4,800.
- Main risk: reviewers may need training before the structured workflow is
  used consistently.
- Proposed mitigation: run two onboarding sessions and a one-week shadow period
  before full adoption.

## Admissions/Project Inputs

- The project demonstrates evidence handling, workflow design, QA thinking, and
  an ability to turn ambiguous notes into auditable artifacts.
- The strongest project lesson is that reliability depends on explicit evidence
  boundaries rather than more polished prose.
- The project is relevant to graduate study in human-centered computing,
  technical communication, or applied information systems.
