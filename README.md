# Report Workflow Local MVP

Report Workflow is an agent-skill-driven source-to-report pipeline. It is meant
to run inside Codex, Hermes, Claude Code, or a similar agent environment.

The Python package does not call an LLM provider and does not require an API key.
It owns deterministic work: source parsing, evidence normalization, artifact
contracts, validation, DOCX rendering, and traceability packaging. The external
agent owns judgment and writing by reading task briefs and producing the required
artifacts.

## Install

```powershell
pip install -r requirements.txt
pip install -e .
```

## Workflow

### 1. Prepare

```powershell
report-workflow prepare `
  --prompt "write an academic report from this source" `
  --source C:\path\to\source.txt `
  --output C:\path\to\out
```

Prepare writes deterministic artifacts and agent task briefs under:

```text
~/.hermes/workflow_runs/<job_id>/
```

Key files:

- `report_spec.json`
- `blueprint.json`
- `source_registry.json`
- `evidence_ledger.jsonl`
- `evidence_store_manifest.json`
- `agent_tasks/01_claim_plan.md`
- `agent_tasks/02_outline_plan.md`
- `agent_tasks/03_section_draft.md`

### 2. Agent Work

Use your agent environment to read `agent_tasks/*.md` and create:

- `claim_matrix.json`
- `outline.json`
- `section_drafts/*.md`
- `sentence_map.jsonl`

The task briefs define the exact required shapes and hard rules.

### 3. Validate

```powershell
report-workflow validate --job-id <job_id>
```

Validate loads the agent-authored artifacts and runs deterministic gates.

### 4. Render

```powershell
report-workflow render --job-id <job_id>
```

Render requires `qa_decision=pass`, then writes:

```text
<output>/final.docx
~/.hermes/published/<job_id>/
```

### Convenience

For a prepared run that already has all agent artifacts:

```powershell
report-workflow run --job-id <job_id>
```

To inspect state:

```powershell
report-workflow status --job-id <job_id>
```

## MVP Support

Supported:

- `fresh_doc` delivery mode
- report families: `academic_report`, `work_report`, `hybrid_report`
- source parsing for `txt`, `docx`, `csv`, `xlsx`, `json`, and `pdf`
- deterministic evidence ledger, claim matrix validation, outline validation,
  sentence map validation, citation audit, factuality linkage report, QA summary,
  DOCX output

Not supported in this MVP:

- embedded LLM provider calls
- agent fallback parsing after deterministic parser failure
- Word native tracked changes
- preserving an existing document's formatting
- diagnostics, research retrieval, figure planning, waiver governance, or revision automation in the MVP path
- production CI or monitoring

## Quality Gates

The MVP hard gates are:

- source files must register and parse
- evidence ledger must be non-empty
- claims must have evidence
- claim/evidence/sentence-map linkage must be valid
- claim status cannot be `blocked`, `unverified`, or `disputed`
- claim type must be allowed by linked evidence
- evidence-backed sentences must include matching `[CITE:<id>]` placeholders
- citation audit must have no unresolved citations
- final DOCX is rendered only after `qa_decision=pass`

Diagnostics such as consistency, style, guideline, figure, research, waiver, and
revision checks are intentionally outside the MVP path. Add them later as
explicit commands rather than implicit prepare/validate/render steps.

## Tests

```powershell
python -m unittest discover -s tests -v
```
