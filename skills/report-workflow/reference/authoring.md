# Authoring Reference

Detailed authoring guidance for `report-workflow`. The short controlled loop is
in `SKILL.md`; load this file for artifact shapes, evidence rules, source-role
boundaries, controlled-submission failure handling, and validation repair.

## Contents

- [Source Roles](#source-roles)
- [Authoring Artifacts](#authoring-artifacts)
- [Structured Drafts (Preferred New-Draft Path)](#structured-drafts-preferred-new-draft-path)
- [Evidence and Citation Rules](#evidence-and-citation-rules)
- [Draft Rules](#draft-rules)
- [Controlled Submission Details](#controlled-submission-details)
- [Reusing a Previous Run](#reusing-a-previous-run)
- [Validation Failure Repair](#validation-failure-repair)

## Source Roles

Valid `source_files` roles are `source_data` and `base_document`. Legacy string
paths are accepted for new drafts.

- Only `source_data` may support measured values, calculated results, experiment
  conditions, comparison groups, charts, or tables.
- When a scanned PDF or reference image must be manually transcribed, save the
  transcription as Markdown or text and pass it with `role: "source_data"`. The
  workflow treats `source_data` `.md` and `.txt` files as accepted internal
  project sources, even when named `source_notes.md`. Never use generated
  workflow artifacts as source evidence.
- If the user marks files as "reference only", do not pass them as `source_data`,
  do not let their measurements enter the evidence ledger, and do not cite or list
  them in the delivered report unless the user changes their role.
- When external references are needed for theory, standards, or reference data,
  keep them separate from experiment measurements. Cite the external source, use
  it only for the specific theory/property claim, and never use it to invent
  missing measured values or extra trial groups.

For academic-style profiles, pass structured front matter when available:
`title`, `author_block`, `affiliation_block`, `correspondence`, and `keywords`.
For school/company fixed templates, pass `template_fields` such as `course_name`,
`student_id`, `instructor`, `lab_section`, `date`, or `department`. Use
`project_identity` when a report must preserve specific project terms, domain
context, forbidden terms, or author metadata.

## Authoring Artifacts

After prepare, read the task briefs in `agent_tasks/`:

- `01_claim_plan.md`
- `02_outline_plan.md`
- `03_section_draft.md`
- `04_revision_plan.md` (for `revise_existing`)

Write these artifacts in the run directory:

- `claim_matrix.json`
- `outline.json`
- `structured_drafts.json` (preferred low-drift draft input)
- `section_drafts/*.md`
- `sentence_map.jsonl`

Every authored artifact must include the `_contract` block from the brief.
Optionally call `lint_artifacts` after edits for fast read-only feedback; it
writes `artifact_lint_report.json` with severity, artifact name, JSON path,
message, and repair hint.

## Structured Drafts (Preferred New-Draft Path)

`structured_drafts.json` may replace manual section Markdown and sentence-map
authoring for new drafts:

```json
{
  "sections": {
    "results": {
      "sentences": [
        {
          "text": "The pilot program enrolled 42 participants.",
          "claim_ids": ["c1"],
          "evidence_ids": ["E001"],
          "wording_strength": "hedged"
        }
      ]
    }
  }
}
```

When validation sees `structured_drafts.json` and the canonical draft files are
missing, the pipeline writes `section_drafts/*.md`, inserts `[CITE:]` markers from
`evidence_ids`, and writes `sentence_map.jsonl`.

Use manual `section_drafts/*.md` plus `sentence_map.jsonl` only when the draft
needs direct Markdown control or when repairing generated canonical drafts.

## Evidence and Citation Rules

- Every publishable claim needs at least one valid `evidence_id`.
- Do not mark publishable claims as `blocked`, `unverified`, or `disputed`.
- Statistical claims require quantitative evidence.
- Every evidence-backed sentence must include `[CITE:<evidence_id>]`.
- `sentence_map.jsonl` citation IDs must match the Markdown `[CITE:]` markers.
- For sentences supported by multiple entries, emit separate markers such as
  `[CITE:E001] [CITE:E002]`. Legacy `[CITE:E001,E002]` is accepted by validation,
  but newly generated drafts should emit separate markers.
- Use hedged wording for medium-grade or qualitative evidence.
- Do not cite internal workflow files, evidence ledgers, claim matrices,
  traceability appendices, generated task briefs, or workflow metadata.
- Use `query_evidence(job_id=..., query="...")` for relevance-ranked browsing when
  the ledger is large; use `evidence_ids=[...]` for exact lookups instead of
  loading the whole ledger into context.

## Draft Rules

Do not edit generated files such as `merged_draft.md`, `publication_draft.md`,
`base_document_sections.json`, publication outputs, checkpoint JSON, or the
harness manifest as an authoring shortcut. Edit only the agent-owned artifacts
allowed by the current harness stage, then rerun validation.

Avoid in body prose:

- placeholder text such as `This section is under development`
- `[Source:]`, `[graphify:]`, `[Note:]`, or other internal markers
- raw evidence IDs outside `[CITE:]`
- internal file paths
- ASCII-art diagrams; use Mermaid or real image assets instead (see
  [figures.md](figures.md))
- snake_case/camelCase data identifiers (`median_processing_minutes`,
  `structured_workflow`) — translate every column or field name into plain
  language with units: "median processing time (minutes)"
- recommendation ids (`figrec_1`) or dataset filenames (`chart_source`) in
  body text or figure captions — captions must describe the finding and its
  units ("Figure 1: Median processing time per note, manual baseline vs
  structured workflow (minutes)"), not the mechanics of the chart
- one template sentence repeated for several figures or results with only a
  noun swapped — vary each lead-in around what that specific figure shows

State grounded numbers instead of writing around them: when the evidence
contains the value, put it in the sentence ("the error rate fell from 9.0% to
3.5%"), reusing the evidence's own figures and units so the content checks
pass. A quantitative section with no numbers reads as evasive even when every
claim is verified.

## Document Language

Write body prose in the language of the source evidence. When the evidence is
Chinese-dominant, the `03_section_draft.md` brief says so and lists the
canonical Chinese section headings; the pipeline detects the document language
deterministically and renders section headings from the blueprint's localized
titles (`title_zh`), so do not hand-translate headings or mix English
boilerplate sentences into a Chinese document. English documents keep the
blueprint's English titles unchanged.

For `academic_paper` and `engineering_lab_report`, make Methods/Procedure
reproducible: name the source or sample basis, procedure, parameters or
instrument/software settings, and supported inclusion, exclusion, calibration,
normalization, or transform rules. In academic introductions, explicitly signal
the problem or gap, objective, and contribution before moving to results.

## Controlled Submission Details

Preferred sequence:

1. Call `get_next_action(job_id=...)`.
2. Read the returned `task_brief_path` and `read_first_paths`.
3. Edit only files listed in `allowed_write_paths`.
4. Call `submit_action(job_id=...)`.
5. Repeat until the returned `status` is `completed`.

Failure returns:

- `validation_failed`: repair only the returned `allowed_repair_paths` using
  `repair_context`.
- `scope_violation`: undo or isolate the out-of-scope artifact changes before
  retrying the same stage. Do not manually advance stages by editing
  `harness_manifest.json`.
- `blocked_non_author_repair`: the failure is outside the current controlled
  authoring surface. Inspect the returned evidence paths; it needs a workflow,
  source, environment, or deterministic-code fix, not edits to read-only workflow
  artifacts or the harness manifest.

For `engineering_lab_report`, call `audit_engineering_report` after drafts exist.
Call `publish_report` when the controlled harness reaches the publish
stage or all required artifacts are already present.

## Reusing a Previous Run

If you reuse artifacts from an older run, call
`remap_agent_artifacts(job_id=..., previous_job_id=...)` first in dry-run mode,
then rerun with `write=True` only after the mapping is reasonable. Do not manually
edit evidence IDs.

## Validation Failure Repair

Read the gate name and fix the canonical source artifact:

- Artifact shape or ID drift: run `lint_artifacts`, then edit the JSON path
  or file named in `artifact_lint_report.json`.
- Claim or evidence-support failures: edit `claim_matrix.json` or improve
  `evidence_ledger.jsonl` content. Do not edit checkpoint JSON.
- Citation failures: edit section drafts and `sentence_map.jsonl`.
- Section contract failures: edit `outline.json` or the relevant section draft.
- Engineering unit/calculation findings: inspect `engineering_audit_report.json`
  before changing claim text.
- Factuality failures: delete stale `factuality_report.json`, rerun validate, then
  inspect the fresh report.
- Render failures: fix Markdown structure, tables, figures, or template artifacts,
  rerun validation, then render.
