---
name: report-workflow
description: Generate, revise, validate, or publish evidence-backed DOCX reports through a deterministic prepare -> author -> validate -> render pipeline. Use when the user wants a lab report, academic paper, business report, proposal, or admissions report delivered as a .docx, especially Chinese engineering lab reports or when report claims must cite sources. Not for slides, spreadsheets, PDFs, or free-form prose with no source evidence.
license: See LICENSE
---

# Report Workflow Skill

Operate the local deterministic pipeline:

```text
prepare -> author -> validate -> render -> publish
```

The Python package does **not** call an LLM. It parses sources, builds an evidence
ledger, checks agent-authored artifacts, renders DOCX, and packages outputs. You
own judgment: claim selection, outlining, and drafting. Keep this file as the
entry point and open a `reference/` file when a step needs detail.

## Reference Library

Read the matching file only when the task reaches that step. Each file is one
level deep and self-contained.

| When you are… | Read |
| --- | --- |
| Checking deps, building `preflight_decisions` | [reference/setup-and-preflight.md](reference/setup-and-preflight.md) |
| Choosing / understanding a profile | [reference/profiles.md](reference/profiles.md) |
| Calling a tool and need its parameters | [reference/tools.md](reference/tools.md) |
| Writing claims, outlines, drafts, citations | [reference/authoring.md](reference/authoring.md) |
| Adding a figure, chart, schematic, or diagram | [reference/figures.md](reference/figures.md) |
| Doing an `engineering_lab_report` | [reference/engineering-lab.md](reference/engineering-lab.md) |
| Revising an existing DOCX | [reference/revision.md](reference/revision.md) |
| Improving `report-workflow` itself | [reference/benchmarking.md](reference/benchmarking.md) |

## Core Model

1. **Prepare** — `start_report` reads sources, infers or accepts
   `report_profile`, and writes `report_spec.json`, `report_profile.json`,
   `blueprint.json`, `evidence_ledger.jsonl`, and task briefs.
2. **Author** — use the controlled harness: `get_next_action` returns
   the current task, read-first files, and allowed write paths;
   `submit_action` validates the stage and records evidence in
   `harness_manifest.json`.
3. **Validate and render** — `publish_report` validates contracts,
   evidence, citations, section rules, profile policy, and render quality, then
   packages the DOCX with QA artifacts under `published/qa/`.

## Invoking the Tools (Any Harness)

The tools are Python functions in `report_workflow.agent_wrapper` that take simple
arguments and return JSON-serializable dicts. Call them the way your harness
supports:

- **Codex / OpenAI-style harness**: the tools declared in `skill.yaml` are exposed
  directly by name, e.g. `start_report(...)`.
- **Claude Code or any shell-capable agent**: use the CLI for deterministic steps,
  or call any wrapper tool via Python:

  ```bash
  report-workflow prepare --prompt "..." --source src.pdf --profile academic_paper \
    --output out --preflight-decisions preflight_decisions.json
  report-workflow validate --job-id <job_id>
  report-workflow render --job-id <job_id>
  # Optional on prepare/render/run: --reference-docx corporate.docx to follow
  # a user-supplied Word template's styles, margins, and header/footer.

  # any wrapper tool, harness-neutral:
  python -c "import json; from report_workflow.agent_wrapper import get_next_action as f; print(json.dumps(f(job_id='<job_id>')))"
  ```

CLI exit codes: `0` success, `1` crash, `2` hard-block validation failure,
`3` waiting for user decisions or agent-authored artifacts. Full signatures and
parameters: [reference/tools.md](reference/tools.md).

## Required Setup

Python 3.11+, `pip install -e .`, and Pandoc 3.x for high-quality DOCX rendering.
Call `check_environment` before every `start_report`, ask the user about every
pending install and optional integration, then pass `preflight_confirmed=True`
with a complete `preflight_decisions` record. Required dependencies must actually
pass preflight; a decision string does not override a still-missing dependency.
Details, UTF-8 setup, and decision examples: [reference/setup-and-preflight.md](reference/setup-and-preflight.md).

## Tool Surface

`skill.yaml` and [reference/tools.md](reference/tools.md) document these tools:

<!-- report-workflow:tool-surface:start -->
- `check_environment`
- `start_report`
- `get_next_action`
- `submit_action`
- `lint_artifacts`
- `register_derived_evidence`
- `audit_engineering_report`
- `publish_report`
- `query_evidence`
- `remap_agent_artifacts`
- `submit_revision_plan`
- `preview_revision_diff`
<!-- report-workflow:tool-surface:end -->

`check_environment` and `start_report` run preparation; the `*_controlled_*` tools
drive staged authoring; `lint_artifacts`, `audit_engineering_report`, and
`query_evidence` are read-only helpers; `publish_report` validates and
renders; `submit_revision_plan` / `preview_revision_diff` support revision.

## Report Profiles

Pass `report_profile` when the user specifies a type; otherwise the pipeline
infers one. Built-ins:

- `engineering_lab_report`
- `academic_paper`
- `business_report`
- `proposal`
- `admissions_report`
- `admissions_project_report`
- `custom`

Do not use `report_family`, `--family`, `--detail`, variant, or subtype naming.
Profile contract, custom-profile rules, and template priority:
[reference/profiles.md](reference/profiles.md).

## Start a Run

```python
start_report(
    prompt="write an engineering lab report from these sources",
    source_files=[{"path": "/path/to/source.pdf", "role": "source_data"}],
    output_dir="/path/to/output",
    report_profile="engineering_lab_report",
    task_intent="new_draft",
    template_fields={"course_name": "Control Systems", "student_id": "S12345"},
    preflight_confirmed=True,
    preflight_decisions={
        "confirmed_by_user": True,
        "install_decisions": {},
        "feature_decisions": {"web_research": "skip", "notebook_sync": "skip"},
    },
)
```

Use `task_intent="revise_existing"` with exactly one `base_document` entry when
revising. Source-role boundaries, front matter, and `project_identity`:
[reference/authoring.md](reference/authoring.md).

## Authoring Flow

Use the controlled workflow by default:

1. Call `get_next_action(job_id=...)`.
2. Read the returned `task_brief_path` and `read_first_paths`.
3. Edit only files listed in `allowed_write_paths`.
4. Call `submit_action(job_id=...)`.
5. Repeat until the returned `status` is `completed`.

`structured_drafts.json` is the preferred low-drift new-draft input; the pipeline
generates `section_drafts/*.md`, `[CITE:]` markers, and `sentence_map.jsonl` from
it. Every evidence-backed sentence needs `[CITE:<evidence_id>]`. Optionally call
`lint_artifacts` for fast read-only feedback. Artifact shapes, evidence
rules, draft rules, controlled-submission failure handling, and validation repair:
[reference/authoring.md](reference/authoring.md).

## Figures

Actively choose the visual surface before drafting. Use the deterministic chart
path for source-data values, Mermaid for editable diagrams, and AI illustrations
only for non-quantitative schematics that invent no data. Taxonomy, profile
defaults, insertion contract, and the prompt pattern:
[reference/figures.md](reference/figures.md).

## Engineering Lab Reports

For `engineering_lab_report`, the profile is the highest-priority contract, above
prompt or template details. It expects SOP grounding, requirement-matrix coverage,
formula/unit/calculation audits, figure/table contracts, and Chinese document
rules. Call `audit_engineering_report` before publish. Full expectations,
exact-cover behavior, figure hard gates, and the Chinese publish checklist:
[reference/engineering-lab.md](reference/engineering-lab.md).

## Revision

Use `task_intent="revise_existing"` only with a `base_document`. In this mode,
`section_drafts/*.md` are not merged; author `revision_plan.json` exact spans
through the controlled harness. Steps and cache invalidation:
[reference/revision.md](reference/revision.md).

## Publish Gate

Do not treat a rendered DOCX as delivered unless the workflow returns `completed`
and no later gate marks it non-publishable. Core hard gates: sources parse; the
evidence ledger is non-empty; claims cite valid evidence IDs; no `blocked`,
`unverified`, or `disputed` claims; evidence-backed sentences carry matching
`[CITE:]` markers; citation audits resolve; no placeholder prose or leaked
workflow metadata; render requires `qa_decision=pass`.

For completed runs, inspect in this order when the paths are returned:
`final_qa_summary_path` first, then `scholarly_quality_report_path`,
`figure_visual_quality_report_path`, `post_render_layout_manifest_path`,
`template_style_map_path`, and `template_field_fill_report_path`. The same files
are packaged under `published/qa/`. Failure repair order:
[reference/authoring.md](reference/authoring.md).

## Improving This Skill

This section is for improving `report-workflow` itself, not ordinary report
generation. Use **Benchmark-First Optimization**: establish a baseline with
`python scripts/run_report_benchmarks.py`, or validate archived evidence with
`python scripts/run_report_benchmarks.py --check`, before changing behavior. Full
method and gap taxonomy: [reference/benchmarking.md](reference/benchmarking.md).

## Keeping Docs in Sync

`SKILL.md`, `skill.yaml`, and `reference/` are the source of truth. The generated
tool blocks and `reference/tools.md` are produced from `skill.yaml`:

```powershell
python scripts/render_skill_docs.py --check   # fail if generated docs are stale
python scripts/render_skill_docs.py --write   # regenerate tool blocks + reference/tools.md
python scripts/sync_codex_skill.py --write    # install/update the packaged skill copy
```
