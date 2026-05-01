# Report Workflow Agent Instructions

This is the agent-facing operating guide for the `report_workflow` skill.
The Python package is deterministic: it parses sources, normalizes evidence,
freezes the report profile contract, validates agent-authored artifacts, and
renders DOCX output. The agent owns judgment, claim selection, outlining, and
drafting.

## Core Model

The workflow has three phases:

1. **Prepare**: `start_report_task` reads sources, infers or accepts
   `report_profile`, writes `report_spec.json`, `report_profile.json`,
   `blueprint.json`, `evidence_ledger.jsonl`, and task briefs.
2. **Author**: the agent writes `claim_matrix.json`, `outline.json`,
   `section_drafts/*.md`, and `sentence_map.jsonl`.
3. **Validate and render**: `submit_and_publish_report` validates contracts,
   evidence support, citations, section rules, profile policy, and render
   quality before publishing the DOCX.

The workflow does not call an LLM provider and does not preserve tracked
changes from existing DOCX files. In `revise_existing` mode, the supported
authoring surface is `revision_plan.json`.

## Report Profiles

Use `report_profile`, not `report_family`, `--family`, detail, subtype, or
variant naming. A profile is the single public contract for structure and rules.

Built-in profile IDs:

- `engineering_lab_report`
- `academic_paper`
- `business_report`
- `proposal`
- `admissions_report`
- `admissions_project_report`
- `custom`

Profiles control section contracts, front matter, abstract policy, citation
style, figure/table requirements, word-count strictness, tone policy, and
render QA expectations. They do not change the deterministic DAG shape.

`custom` is intentionally medium strictness: evidence-backed claims and section
contracts are required, while citation style, word-count, and figure rules stay
lenient unless the user supplies a stricter structure.

## Template Priority

The user can request a reference/template mode. If omitted, the workflow uses
`style_reference`. If the prompt asks to follow the exact format, exact cover, or
same template, intake upgrades the mode to `fixed_template`.

Profile semantics still win over visual template hints. For example,
`engineering_lab_report` keeps its engineering report contract even when a
reference document is used for style.

## Preflight

Call `check_setup()` before every `start_report_task`.

Required runtime:

- Python 3.11+
- `pip install -e .` from the repository root
- Pandoc 3.x for high-quality DOCX rendering

Optional integrations:

- `mmdc` for Mermaid-to-PNG conversion
- `TAVILY_API_KEY`, `SERPER_API_KEY`, or `SERPAPI_API_KEY` for external claim
  research
- `notebooklm-py` and a notebook ID for NotebookLM sync

`start_report_task` requires `preflight_confirmed=True` and a complete
`preflight_decisions` record. Missing critical render dependencies must be
installed or explicitly accepted through `allow_degraded_render=True`.

## Start A Report

```python
start_report_task(
    prompt="Write an engineering lab report from these measurements.",
    source_files=["lab_notes.pdf", "measurements.csv"],
    output_dir="output",
    report_profile="engineering_lab_report",
    preflight_confirmed=True,
    preflight_decisions={...}
)
```

If `report_profile` is omitted, the workflow infers it from the prompt and
source context. Use explicit profile IDs when the user has already chosen the
report type.

## Authoring Artifacts

After prepare, read the task briefs in `agent_tasks/`:

- `01_claim_plan.md`
- `02_outline_plan.md`
- `03_section_draft.md`
- `04_revision_plan.md` for `revise_existing`

Write these artifacts in the run directory:

- `claim_matrix.json`
- `outline.json`
- `section_drafts/*.md`
- `sentence_map.jsonl`

Every authored artifact must include the `_contract` block from the brief. If
you reuse artifacts from a previous run, call `remap_agent_artifacts` instead of
manually editing evidence IDs.

## Evidence Rules

- Every publishable claim needs at least one valid `evidence_id`.
- Do not mark publishable claims as `blocked`, `unverified`, or `disputed`.
- Statistical claims require quantitative evidence.
- Evidence-backed sentences must include `[CITE:<evidence_id>]`.
- `sentence_map.jsonl` citation IDs must match the Markdown `[CITE:]` markers.
- Use hedged wording for medium-grade or qualitative evidence.
- Do not cite checkpoint files, internal paths, generated task briefs, or
  workflow metadata as external evidence.

## Draft Rules

Do not edit generated files such as `merged_draft.md`, `publication_draft.md`,
or checkpoint JSON. Edit the agent-owned artifacts and rerun validation.

Avoid:

- placeholder text such as `This section is under development`
- `[Source:]`, `[graphify:]`, `[Note:]`, or other internal markers in body prose
- raw evidence IDs outside `[CITE:]`
- internal file paths in report prose
- ASCII-art diagrams; use Mermaid or real image assets instead

## Engineering Lab Report Notes

For `engineering_lab_report`, treat SOPs, lab handouts, measurement sheets, and
rubrics as first-class sources. The report should preserve:

- required Chinese lab-report sections
- experiment purpose, theory, apparatus, procedure, results, discussion,
  conclusion/reflection, and references
- formula variables, parameters, units, and calculation assumptions
- figure/table numbering and references
- question-and-answer requirements from the handout
- Chinese report tone without agent/workflow jargon

The built-in `CHINESE_ENGINEERING` guideline is selected by default for this
profile.

## Incremental Submission

Preferred sequence:

1. Write `claim_matrix.json`, then call `submit_claim_matrix(job_id=...)`.
2. Write `outline.json`, then call `submit_outline(job_id=...)`.
3. Write `section_drafts/*.md` and `sentence_map.jsonl`, then call
   `submit_drafts(job_id=...)`.
4. Call `submit_and_publish_report(job_id=...)`.

Legacy two-step use is still supported: after prepare, create all artifacts and
call `submit_and_publish_report` directly.

## Revise Existing

In `revise_existing` mode, `section_drafts/*.md` are not merged into the final
document. Write `revision_plan.json` with exact `original_text` spans and
replacement text. Call `submit_revision_plan` before final publish.

If a validation failure points to stale base-document content, invalidate caches
through the CLI:

```powershell
report-workflow invalidate-cache --job-id <id> --sources --drafts
```

## Validation Failures

Read the gate name and fix the canonical source artifact:

- Claim failures: edit `claim_matrix.json`.
- Evidence support failures: edit `claim_matrix.json` or improve
  `evidence_ledger.jsonl` content.
- Citation failures: edit section drafts and `sentence_map.jsonl`.
- Section contract failures: edit `outline.json` or the relevant section draft.
- Render failures: fix Markdown structure, tables, figures, or template issues.

For factuality failures, delete stale `factuality_report.json`, rerun validate,
then inspect the fresh report.

## CLI Equivalents

```powershell
report-workflow prepare --prompt "..." --source source.pdf --profile engineering_lab_report --output output
report-workflow validate --job-id <job_id> --verbose
report-workflow render --job-id <job_id>
report-workflow status --job-id <job_id>
report-workflow diagnose --job-id <job_id> --verbose
```

Use `--profile`; do not use the removed `--family` option.
