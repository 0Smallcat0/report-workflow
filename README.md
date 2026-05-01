# Report Workflow

Report Workflow is a deterministic source-to-report pipeline for evidence-backed
DOCX reports. It is designed to run inside an agent environment such as Codex,
Claude Code, or Hermes.

The Python package does not call an LLM provider and does not require an API key.
It owns source parsing, evidence normalization, artifact contracts, validation
gates, DOCX rendering, and traceability packaging. The external agent owns
judgment and drafting by reading task briefs and producing required artifacts.

## Install

```powershell
pip install -r requirements.txt
pip install -e .
```

Required external tool:

```powershell
pandoc --version
```

Pandoc 3.x is the primary DOCX renderer. Without pandoc, the workflow falls
back to a limited `python-docx` renderer and the output may have degraded table,
list, and layout fidelity.

Optional integrations:

- `mmdc` (`npm install -g @mermaid-js/mermaid-cli`) for Mermaid diagrams.
- `TAVILY_API_KEY`, `SERPER_API_KEY`, or `SERPAPI_API_KEY` for optional web research.
- `notebooklm-py` for optional NotebookLM sync.

## CLI

```powershell
report-workflow prepare `
  --prompt "write an engineering lab report from these sources" `
  --source C:\path\to\source.txt `
  --output C:\path\to\out `
  --profile engineering_lab_report

report-workflow validate --job-id <job_id>
report-workflow render --job-id <job_id>
report-workflow status --job-id <job_id>
report-workflow run --job-id <job_id>
```

`--source PATH:ROLE` may be repeated. Valid roles are `source_data` and
`base_document`. The role suffix is parsed only when the trailing token exactly
matches a valid role, so Windows paths such as `C:\path\to.txt` are safe.

CLI exit codes:

- `0`: success
- `1`: crash
- `2`: hard-block validation failure
- `3`: waiting for agent-authored artifacts

## Report Profiles

`report_profile` is the public report-shape contract. It replaces the old
`report_family` and detail/subtype model.

Built-in profiles:

- `engineering_lab_report`: engineering experiment reports, including Chinese
  engineering report requirements, requirement matrices, formula/unit audits,
  calculation audits, figure/table contracts, and render QA.
- `academic_paper`: IMRaD-style academic papers with strict abstract,
  front-matter, citation, and reference expectations.
- `business_report`: executive/work reports with findings and recommendations.
- `proposal`: proposals with problem, objectives, approach, scope, timeline,
  budget/resources, risks, and evaluation sections.
- `admissions_report`: admissions-facing scholarly reports.
- `admissions_project_report`: admissions-facing project reports with relaxed
  publication metadata requirements.
- `custom`: user-defined or mixed reports with medium strictness. Claims and
  section contracts remain evidence-backed; citation format, word counts, and
  figure rules default to lenient.

The pipeline infers a profile from the prompt unless `--profile` or
`report_profile` is provided.

## Workflow

### 1. Prepare

`prepare` parses sources and writes deterministic artifacts:

- `report_spec.json`
- `report_profile.json`
- `blueprint.json`
- `source_registry.json`
- `evidence_ledger.jsonl`
- `agent_tasks/01_claim_plan.md`
- `agent_tasks/02_outline_plan.md`
- `agent_tasks/03_section_draft.md`

### 2. Agent Authoring

The external agent reads the task briefs and writes:

- `claim_matrix.json`
- `outline.json`
- `section_drafts/*.md`
- `sentence_map.jsonl`

Use the incremental validation tools when operating through the agent skill:

- `submit_claim_matrix`
- `submit_outline`
- `submit_drafts`

### 3. Validate and Render

`validate` checks artifact completeness, section contracts, citation linkage,
factuality, profile policy, figure contracts, and QA gates. `render` runs only
after `qa_decision=pass`.

Final artifacts are packaged under:

```text
output/<slug>--<job_id>/published/
```

## Reference Templates

Profiles control reference-template behavior.

- Default mode is `style_reference`: use a DOCX as a style/layout reference.
- If the user explicitly asks to exactly preserve cover or format, the workflow
  upgrades to `fixed_template`.
- A profile contract has priority over prompt and template hints.

For `engineering_lab_report`, the profile remains the highest-priority semantic
contract even when a school/company template DOCX is supplied.

## Quality Gates

The core hard gates are:

- Sources must register and parse.
- Evidence ledger must be non-empty.
- Claims must cite valid evidence IDs.
- Claim status cannot be `blocked`, `unverified`, or `disputed`.
- Evidence-backed sentences must contain matching `[CITE:<id>]` placeholders.
- Citation audit entries must resolve.
- Placeholder prose and template metadata are blocked.
- Render runs only after `qa_decision=pass`.

Profile policies adjust strictness for front matter, abstract structure, citation
style, reference verification, figure/table contracts, and section roles.

## Tests

```powershell
python -m compileall -q src tests
python -m unittest discover -s tests -v
```
