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

## Required Setup

Run before starting a report:

```python
check_setup()
```

Then ask the user about every pending install and optional integration reported
by `check_setup()`. `start_report_task` requires `preflight_confirmed=True` and
a complete `preflight_decisions` record.

Core dependencies:

- Python 3.11+
- `pip install -e .` in the repo root
- Pandoc 3.x for high-quality DOCX rendering

Optional:

- `mmdc` for Mermaid diagrams
- Tavily, Serper, or SerpAPI keys for web research
- `notebooklm-py` for NotebookLM sync

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
    source_files=["/path/to/source.pdf"],
    output_dir="/path/to/output",
    report_profile="engineering_lab_report",
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

For academic-style profiles, pass structured front matter when available:
`title`, `author_block`, `affiliation_block`, `correspondence`, and `keywords`.

Use `project_identity` when a report must preserve specific project terms,
domain context, forbidden terms, or author metadata.

## Authoring Flow

Use incremental submission by default:

1. Read `agent_tasks/01_claim_plan.md`, write `claim_matrix.json`, call
   `submit_claim_matrix`.
2. Read `agent_tasks/02_outline_plan.md`, write `outline.json`, call
   `submit_outline`.
3. Read `agent_tasks/03_section_draft.md`, write `section_drafts/*.md` and
   `sentence_map.jsonl`, call `submit_drafts`.
4. Call `submit_and_publish_report`.

Every evidence-backed sentence in drafts must include `[CITE:<evidence_id>]`.
Do not cite internal workflow files, evidence ledgers, claim matrices, or
traceability appendices in the main report.

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

Reference DOCX behavior:

- User-specified mode wins.
- Default is `style_reference`.
- If the prompt asks to exactly match the format or cover, use `fixed_template`.

## Publish Gate

Do not treat a rendered DOCX as delivered unless the workflow returns completed
status and no later gate marks it non-publishable. If validation fails, edit the
agent artifact that caused the failure and rerun validation.
