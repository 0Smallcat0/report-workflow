---
name: report-workflow
description: Use when Codex needs to generate, revise, validate, or publish evidence-backed DOCX reports with the local report_workflow pipeline. Supports report profiles, optional web research, optional NotebookLM sync, and Chinese engineering lab reports.
---

# Report Workflow Skill

Use this skill to operate the local deterministic pipeline:

```text
prepare -> agent authoring -> validate -> render -> publish
```

The pipeline does not call an LLM. It parses sources, builds an evidence ledger,
checks agent-authored artifacts, renders DOCX, and packages outputs.
After DOCX render validation, it writes `post_render_layout_manifest.json` with
renderer, document size, paragraph/table/figure counts, heading and table
previews, related render QA report paths, and any render validation issues.
At publish time, it also writes `final_qa_summary.json` and
`final_qa_summary.md`, a delivery-level summary that links QA gate,
factuality, artifact lint, engineering audit, and render-layout evidence.
It writes `template_style_map.json` and `template_style_map.md` to explain the
reference DOCX mode, renderer, applied-reference status, key style definitions,
and rendered style usage.
For fixed-template metadata, it writes `template_field_fill_report.json` and
`template_field_fill_report.md` to show which structured fields were filled in
the final DOCX.

## Required Setup

Run before starting a report:

```python
check_setup()
```

Then ask the user about every pending install and optional integration reported
by `check_setup()`. `start_report_task` requires `preflight_confirmed=True` and
a complete `preflight_decisions` record.
Required dependencies must pass preflight after installation; do not treat an
`install` or `installed` decision as proof when `check_setup()` still reports
the dependency missing.
The raw CLI `prepare` entry point also requires a `--preflight-decisions` JSON
file with the same decision record, so command-line runs cannot bypass this
user-confirmation step.

Core dependencies:

- Python 3.11+
- `pip install -e .` in the repo root
- Pandoc 3.x for high-quality DOCX rendering

Optional:

- `mmdc` for Mermaid diagrams
- Tavily, Serper, or SerpAPI keys for web research
- `notebooklm-py` for NotebookLM sync

## Preflight Decision Examples

Always start from the `required_preflight_decisions` object returned by
`check_setup()`. The examples below show common completed shapes, not shortcuts.

All required setup is ready and optional integrations are skipped:

```python
preflight_confirmed=True,
preflight_decisions={
    "confirmed_by_user": True,
    "install_decisions": {},
    "feature_decisions": {
        "web_research": "skip",
        "notebook_sync": "skip"
    }
}
```

Pandoc is missing and the user explicitly accepts degraded DOCX rendering:

```python
allow_degraded_render=True,
preflight_confirmed=True,
preflight_decisions={
    "confirmed_by_user": True,
    "install_decisions": {
        "pandoc": "accept_degraded"
    },
    "feature_decisions": {
        "web_research": "skip",
        "notebook_sync": "skip"
    }
}
```

Web research and NotebookLM are enabled after the user confirms the available
backend/API key and provides a NotebookLM notebook ID:

```python
enable_research=True,
enable_notebook_sync=True,
notebooklm_notebook_id="notebook-id-from-user",
preflight_confirmed=True,
preflight_decisions={
    "confirmed_by_user": True,
    "install_decisions": {},
    "feature_decisions": {
        "web_research": "enable",
        "notebook_sync": "enable"
    }
}
```

If `check_setup()` still reports a required dependency missing, install and
rerun setup. Do not force-start by changing the decision record.

## Tool Surface

`agent_skill/skill.yaml` exposes these agent tools:

<!-- report-workflow:tool-surface:start -->
- `check_setup`
- `start_report_task`
- `submit_claim_matrix`
- `submit_outline`
- `submit_drafts`
- `lint_agent_artifacts`
- `run_engineering_audit`
- `submit_and_publish_report`
- `query_evidence`
- `remap_agent_artifacts`
- `submit_revision_plan`
- `preview_revision_diff`
<!-- report-workflow:tool-surface:end -->

Keep this short skill, `skill.yaml`, and `agent_instructions.md` synchronized.
From the repo root, update generated blocks before syncing:

```powershell
python scripts/render_skill_docs.py --write
python scripts/sync_codex_skill.py
python scripts/sync_codex_skill.py --write
```

Use `python scripts/render_skill_docs.py --check` in validation to catch stale
generated tool lists.

## Report Profiles

Pass `report_profile` when the user specifies a report type. Otherwise the
pipeline infers one from the prompt.

Built-in profiles:

- `engineering_lab_report`
- `academic_paper`
- `business_report`
- `proposal`
- `admissions_report`
- `admissions_project_report`
- `custom`

Do not use `report_family`, `--family`, `--detail`, variant, or subtype naming.

## Start a Run

```python
start_report_task(
    prompt="write an engineering lab report from these sources",
    source_files=[
        {"path": "/path/to/source.pdf", "role": "source_data"},
    ],
    output_dir="/path/to/output",
    report_profile="engineering_lab_report",
    task_intent="new_draft",
    template_fields={
        "course_name": "Control Systems",
        "student_id": "S12345"
    },
    preflight_confirmed=True,
    preflight_decisions={
        "confirmed_by_user": True,
        "install_decisions": {},
        "feature_decisions": {
            "web_research": "skip",
            "notebook_sync": "skip"
        }
    },
)
```

Use `task_intent="revise_existing"` with exactly one
`{"path": "...", "role": "base_document"}` entry when revising an existing
document. Legacy string paths are still accepted for new drafts.

For academic-style profiles, pass structured front matter when available:
`title`, `author_block`, `affiliation_block`, `correspondence`, and `keywords`.
For school/company fixed templates, pass `template_fields` for fields such as
`course_name`, `student_id`, `instructor`, `lab_section`, `date`, or
`department`.

Use `project_identity` when a report must preserve specific project terms,
domain context, forbidden terms, or author metadata.

## Authoring Flow

Use incremental submission by default:

1. Read `agent_tasks/01_claim_plan.md`, write `claim_matrix.json`, call
   `submit_claim_matrix`.
2. Read `agent_tasks/02_outline_plan.md`, write `outline.json`, call
   `submit_outline`.
3. Read `agent_tasks/03_section_draft.md`, then write `structured_drafts.json`
   by default and call `submit_drafts`.
4. Optionally call `lint_agent_artifacts` after any artifact edit to get a
   consolidated `artifact_lint_report.json` with JSON paths and repair hints.
5. For `engineering_lab_report`, call `run_engineering_audit` after drafts
   exist to inspect units, table-value support, measurement support, and simple
   calculations.
6. Call `submit_and_publish_report`.

Every evidence-backed sentence in drafts must include `[CITE:<evidence_id>]`.
When using `structured_drafts.json`, provide sentence `evidence_ids`; the
pipeline inserts matching `[CITE:]` markers and writes `sentence_map.jsonl`.
Use manual `section_drafts/*.md` plus `sentence_map.jsonl` only when the draft
needs direct Markdown control or when repairing generated canonical drafts.
Do not cite internal workflow files, evidence ledgers, claim matrices, or
traceability appendices in the main report.

Use `query_evidence(job_id=..., query="...")` for relevance-ranked evidence
lookup instead of loading large ledgers into context. If you reuse artifacts
from an older run, call `remap_agent_artifacts(job_id=..., previous_job_id=...)`
first in dry-run mode, then rerun with `write=True` only after the mapping is
reasonable.

## Revision Flow

Use `task_intent="revise_existing"` only when a base document is supplied with
role `base_document`. In this mode, `section_drafts/*.md` are not merged into
the final document. Instead:

1. Read `agent_tasks/04_revision_plan.md` and `base_document_sections.json`.
2. Write `revision_plan.json` with exact `original_text` spans and replacement
   text.
3. Call `preview_revision_diff` for a read-only diff preview.
4. Call `submit_revision_plan` to validate spans and conflicts before publish.
5. Call `submit_and_publish_report` only after the revision plan validates.

## Engineering Lab Reports

For `engineering_lab_report`, preserve the profile contract above prompt or
template details. The profile expects:

- SOP/handout/lab-instruction grounding.
- Requirement matrix coverage.
- Formula, parameter, symbol, and unit audit.
- Calculation audit.
- Figure/table contract.
- Chinese document rules and mojibake avoidance.
- Render QA for cover/template drift, table compression, and image placement.
Use `run_engineering_audit` to write `engineering_audit_report.json` before
publish when units, table-backed claims, measurement claims, or arithmetic need
explicit checking.

Reference DOCX behavior:

- User-specified mode wins.
- Default is `style_reference`.
- If the prompt asks to exactly match the format or cover, use `fixed_template`.

Chinese engineering publish checklist:

- `lint_agent_artifacts` has no errors and citation IDs match the current run.
- `run_engineering_audit` has been reviewed for unit support, table-value
  support, measured values, and simple calculations.
- The draft covers the lab handout/SOP requirements, required questions,
  apparatus/procedure, results, discussion, conclusion/reflection, and
  references.
- Formula variables, parameters, units, table numbers, figure numbers, and
  prose references are consistent.
- Chinese prose is natural and contains no workflow/agent jargon, placeholder
  text, mojibake, or raw internal file paths.
- Template fields such as course, student ID, instructor, lab section, date,
  and department are supplied when the school/company template expects them.
- Before delivery, inspect `final_qa_summary_path`, then
  `template_field_fill_report_path`, `template_style_map_path`, and
  `post_render_layout_manifest_path` when those paths are returned.

## Publish Gate

Do not treat a rendered DOCX as delivered unless the workflow returns completed
status and no later gate marks it non-publishable. If validation fails, edit the
agent artifact that caused the failure and rerun validation.

Failure repair order:

- Artifact shape or ID drift: run `lint_agent_artifacts`, then edit the JSON
  path or file named in `artifact_lint_report.json`.
- Claim support or factuality failure: edit `claim_matrix.json`, draft wording,
  or `sentence_map.jsonl`; do not edit checkpoint JSON.
- Engineering unit, table-value, or arithmetic concerns: inspect
  `engineering_audit_report.json` before changing claim text.
- Revision failures: edit `revision_plan.json` exact spans, then rerun
  `preview_revision_diff` and `submit_revision_plan`.
- Render failures: fix Markdown/table/figure/template artifacts, rerun
  validation, then render.

For completed runs, inspect `final_qa_summary_path` or packaged
`published/qa/final_qa_summary.json` first when reporting final delivery
readiness; the Markdown sibling is packaged as `published/qa/final_qa_summary.md`.
Inspect `post_render_layout_manifest_path` or packaged
`published/qa/post_render_layout_manifest.json` when you need render-structure
evidence for the delivered DOCX.
Use `template_style_map_path` or packaged
`published/qa/template_style_map.json` when the user asks how a template or
reference DOCX affected the final document.
Use `template_field_fill_report_path` or packaged
`published/qa/template_field_fill_report.json` when the user asks whether cover
or fixed-template fields were filled.
