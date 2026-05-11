# CLAUDE.md

This file gives agent-facing development guidance for this repository. Start
with `AGENT_ONBOARDING.md` for the conceptual overview.

## Project Overview

`report-workflow` is a deterministic source-to-report pipeline. The installed
package lives under `src/report_workflow/`; `pyproject.toml` uses
`package-dir = {"" = "src"}`.

The package does not call an LLM. It parses sources, normalizes evidence,
validates agent-authored artifacts, renders DOCX, and packages outputs. The
external agent writes claims, outlines, section drafts, and sentence maps.

## Commands

```powershell
pip install -r requirements.txt
pip install -e .

python -m compileall -q src tests
python -m unittest discover -s tests -v

report-workflow prepare --prompt "..." --source path\to\src.txt --output out\dir --profile engineering_lab_report
report-workflow validate --job-id <job_id> [--verbose] [--dry-run] [--deep-audit]
report-workflow render --job-id <job_id>
report-workflow status --job-id <job_id>
report-workflow run --job-id <job_id> [--verbose]
report-workflow diff --job-id <a> --against <b>
report-workflow export --job-id <id> [--checkpoint <name>] [--output <file>]
```

CLI exit codes: `0` success, `1` crash, `2` hard-block failure, `3` waiting for
agent artifacts.

## Profile Contract

`report_profile` is the only public report-shape selector. Do not add new
`report_family`, `--family`, `--detail`, subtype, or variant paths.

Profile registry: `src/report_workflow/profiles.py`

Built-in profile IDs:

- `engineering_lab_report`
- `academic_paper`
- `business_report`
- `proposal`
- `admissions_report`
- `admissions_project_report`
- `custom`

Profiles control blueprint, policy, aliases, strictness, and reference-template
behavior. The workflow DAG should remain stable; nodes read profile policy.

## Node Lists

`src/report_workflow/run_workflow.py` owns the canonical node sequence.

Prepare:

```text
INTAKE -> GUIDELINE_SELECT -> BLUEPRINT_PLAN -> CORPUS_BUILD ->
SOURCE_PARSE -> BASE_DOCUMENT_PARSE -> EVIDENCE_NORMALIZE ->
EVIDENCE_STORE -> FIGURE_RECOMMEND -> NOTEBOOK_SYNC -> AGENT_TASKS
```

Validate:

```text
AGENT_ARTIFACT_INTAKE -> PLAN_FREEZE -> DOC_METADATA_GATE ->
METHODS_PROTOCOL_BUILD -> FIGURE_PLAN_AUDIT -> FIGURE_BUILD -> DRAFT_ASSEMBLY ->
PROJECT_IDENTITY_GATE -> ADMISSIONS_TONE_GATE -> SECTION_ROLE_CHECK ->
CITATION_LAYER -> FACTUALITY_CHECK -> RESEARCH_EXECUTE ->
CLAIM_VERIFY_EXECUTE -> FIGURE_QUALITY -> QA_GATE
```

Render:

```text
STYLE_PASS -> PUBLICATION_NATURALNESS_PASS ->
ADMISSIONS_MONOGRAPH_POLISH -> HEADING_CONTRACT_CHECK -> DOCX_RENDER ->
POST_RENDER_REPAIR -> POST_RENDER_VALIDATE -> VISUAL_RENDER_CHECK ->
REFERENCE_REALITY_CHECK -> REFERENCE_RELEVANCE_GATE ->
SOURCE_APPENDIX_RENDER -> FINAL_PUBLISH ->
SUPPLEMENTARY_PACKAGE_BUILD -> ARTIFACTS
```

Keep documentation synchronized when changing these lists.

`ARTIFACTS` packages delivery QA files under `published/qa/`, including
`final_qa_summary.json` and `final_qa_summary.md`. These summarize QA gate,
factuality, artifact lint, engineering audit, chart visual-quality review, and
render-layout evidence without adding a hard gate.
`template_style_map.json` and `template_style_map.md` explain reference-DOCX
mode, renderer choice, applied-reference status, key style definitions, rendered
style usage, and template-fidelity warnings.
`template_field_fill_report.json` and `template_field_fill_report.md` audit
fixed-template/front-matter field values in the final DOCX.

## State and Persistence

`ReportState` is the source of truth. It carries `spec`, `plan`, `sources`,
`drafts`, `citations`, `qa`, `output`, `runtime`, `flags`, `knowledge_sync`, and
`research`.

Each node writes `checkpoint_<NODE>.json` and `checkpoint_latest.json` under:

```text
output/<slug>--<job_id>/
```

## Blueprints and Policies

`BLUEPRINT_PLAN` loads the YAML file declared by the frozen profile contract.
`section_order` is authoritative for required `outline.json` and
`section_drafts/*.md` coverage.

Use profile policy instead of string-branching:

```python
from ..policies import get_policy

policy = get_policy(state.spec.get("report_profile", "academic_paper"))
```

## Engineering Lab Profile

`engineering_lab_report` is the built-in engineering experiment profile. It
requires source-grounded claims and supports:

- Requirement matrices.
- Formula, parameter, symbol, and unit audit expectations.
- Calculation audit expectations.
- Figure/table contracts.
- Chinese engineering report headings and unit/symbol consistency.
- Render QA for table compression, images, cover/template drift, and layout.

Reference DOCX behavior:

- Default: `style_reference`.
- Prompt asks exact format/cover: `fixed_template`.
- Explicit user mode wins.
- Profile semantics remain highest priority.

## Agent Skill Tools

`agent_skill/skill.yaml` exposes:

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

## Hard Rules

- Delivery mode is `fresh_doc`.
- Every claim must cite valid evidence.
- `blocked`, `unverified`, and `disputed` claims are non-publishable.
- Evidence-backed draft sentences must include matching `[CITE:<id>]` markers.
- Citation audits must resolve.
- Placeholder prose, fake metadata, and internal workflow artifacts must not leak
  into publication text.
- `DOCX_RENDER` requires `qa_decision=pass`.

## Git Hygiene

This repo may start dirty. Do not revert changes you did not make. Before
committing, verify that the diff boundary is clean and that unrelated dirty files
or generated output are not included.
