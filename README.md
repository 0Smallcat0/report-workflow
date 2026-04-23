# Report Workflow

Report Workflow is an agent-skill-driven source-to-report pipeline. It runs
inside Codex, Hermes, Claude Code, or a similar agent environment.

The Python package does not call an LLM provider and does not require an API key.
It owns deterministic work: source parsing, evidence normalization, artifact
contracts, validation, DOCX rendering, and traceability packaging. The external
agent owns judgment and writing by reading task briefs and producing the required
artifacts.

---

## Prerequisites

### System Dependencies

| Dependency | Required | Install | Purpose |
|-----------|----------|---------|---------|
| **Python 3.11+** | Yes | — | Runtime |
| **pandoc 3.x** | Yes | `winget install JohnMacFarlane.Pandoc` (Windows) or `apt install pandoc` (Linux) | DOCX rendering (primary path) |

> **Why pandoc?** The DOCX renderer uses pandoc as the primary Markdown→DOCX conversion path. This produces correctly rendered tables, code blocks, nested lists, and inline formatting. If pandoc is not installed, the pipeline falls back to a limited python-docx regex-based converter, which may produce broken tables and formatting artifacts.

### Python Dependencies

```powershell
pip install -r requirements.txt
pip install -e .
```

### Verify Installation

```powershell
pandoc --version          # Should show 3.x
python -c "import report_workflow; print('OK')"
```

### Optional Integration Dependencies

These enable advanced features but are **never required** — the pipeline gracefully skips when they are missing.

| Dependency | Feature | Setup |
|------------|---------|-------|
| **notebooklm-py** | NotebookLM knowledge sync | `pip install notebooklm-py` + browser auth |
| **TAVILY_API_KEY** | Web research for claim verification | Set environment variable (recommended backend) |
| **SERPER_API_KEY** | Alternative web research backend | Set environment variable |
| **SERPAPI_API_KEY** | Alternative web research backend | Set environment variable |

---

## Workflow

### 1. Prepare

```powershell
report-workflow prepare `
  --prompt "write an academic report from this source" `
  --source C:\path\to\source.txt `
  --output C:\path\to\out `
  --title "Deterministic Compilation Architecture for Quantitative Trading Strategy Generation" `
  --author "Example Student" `
  --affiliation "Department of Engineering, Example University" `
  --correspondence "student@example.edu" `
  --keyword "deterministic compilation" `
  --keyword "StrategyIR"
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

### 2. Agent Work (4-Step Incremental)

Use your agent environment to read `agent_tasks/*.md` and create artifacts
**one step at a time**, validating after each:

| Step | Artifact | Validate Tool |
|------|----------|---------------|
| 2a | `claim_matrix.json` | `submit_claim_matrix` |
| 2b | `outline.json` | `submit_outline` |
| 2c | `section_drafts/*.md` + `sentence_map.jsonl` | `submit_drafts` |

Each step checkpoints independently, preventing context window exhaustion
on large projects. The task briefs define the exact required shapes and hard
rules.

> **Legacy mode**: You can also create all artifacts at once and skip directly
> to step 3. This is faster for small projects but risky for large ones.

### 3. Validate + Render

```powershell
report-workflow validate --job-id <job_id>
report-workflow render --job-id <job_id>
```

Or via the agent tool:

```
submit_and_publish_report(job_id="<job_id>")
```

Render uses pandoc with a reference template (`templates/reference.docx`) for
academic styling (A4, Times New Roman 12pt, 1.5× line spacing). Output:

```text
~/.hermes/workflow_runs/<job_id>/rendered_report.docx
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

---

## Agent Skill Tools

| Tool | Purpose |
|------|---------|
| `start_report_task` | Start workflow, parse sources, generate task briefs. Accepts `enable_research`, `enable_notebook_sync`, `notebooklm_notebook_id` |
| `submit_claim_matrix` | Validate claim_matrix.json (Step 2a) |
| `submit_outline` | Validate outline.json (Step 2b) |
| `submit_drafts` | Validate section drafts + sentence map (Step 2c) |
| `submit_and_publish_report` | Full validate + render pipeline |
| `query_evidence` | Browse or look up evidence entries by ID |
| `remap_agent_artifacts` | Remap evidence IDs from a previous run |
| `submit_revision_plan` | Pre-validate revision_plan.json |
| `preview_revision_diff` | Read-only diff preview for revision plans |

---

## Supported Features

- `fresh_doc` delivery mode
- Report families: `academic_report`, `work_report`, `hybrid_report`
- Source parsing for `txt`, `docx`, `csv`, `xlsx`, `json`, `pdf`, `md`, `py`, `js`
- Deterministic evidence ledger, claim matrix validation, outline validation,
  sentence map validation, citation audit, factuality linkage, QA summary
- DOCX output via pandoc (primary) or python-docx (fallback)
- Post-render validation (paragraph count, heading structure, text length)
- **External web research** for claim verification (Tavily, Serper, SerpAPI, BrowserMCP)
- **NotebookLM knowledge sync** for source context and analysis Q&A
- **Claim verification** with coverage scoring and status upgrades
- **Chinese engineering report** guidelines and CJK parser enrichment
- **Matplotlib figure generation** from agent-authored figure plans

## Not Supported

- Embedded LLM provider calls
- Word native tracked changes
- Preserving an existing document's formatting
- Automatic figure generation from ASCII art (requires manual image creation)
- Production CI or monitoring

---

## Quality Gates

The hard gates are:

- Source files must register and parse
- Evidence ledger must be non-empty (minimum 5 entries for academic mode)
- Claims must have evidence
- Claim/evidence/sentence-map linkage must be valid
- Claim status cannot be `blocked`, `unverified`, or `disputed`
- Evidence-backed sentences must include matching `[CITE:<id>]` placeholders
- Citation audit must have no unresolved citations
- Pre-render sanity gate blocks prompt leakage, template metadata leakage, and noisy front matter keywords
- Final DOCX is rendered only after `qa_decision=pass`
- Post-render validation checks DOCX structure (headings, paragraph count)

> **Note:** `graph_analysis` and `research_document` evidence diversity are
> checked as warnings, not hard blocks. `code_artifact` is preferred for
> implementation-scoped claims, but architecture/system claims may be grounded
> by graphify/docs/spec evidence.

---

## Tests

```powershell
python -m unittest discover -s tests -v
```
