# Agent Onboarding: Report Workflow

This document provides a **comprehensive conceptual overview** of the report workflow.
For the complete operational reference (prerequisites, tools, rules, debugging),
see `agent_skill/agent_instructions.md` — it is fully self-contained and does not
require reading this document first.

---

## What Is This Workflow?

**Report Workflow** is a deterministic source-to-report pipeline. Given source files (research papers, code repositories, datasets, etc.), it produces a structured, citation-linked, publication-ready DOCX document.

**What it is NOT:**
- It does NOT call an LLM provider. The Python package owns no generative AI.
- It does NOT write the report content. That judgment belongs to you — the agent.
- It does NOT support tracked changes or formatting preservation of existing documents.

**Two-part model:**
- **Pipeline (Python):** Deterministic work — parsing, evidence normalization, validation gates, DOCX rendering (via pandoc), artifact contracts.
- **Agent (you):** Judgment and writing — reading task briefs, producing claims, outlines, section drafts.

---

## Prerequisites

Before using this workflow, ensure the host system has all required dependencies.

### Core Dependencies (Required)

| Dependency | Required? | Install Command | Purpose |
|------------|-----------|-----------------|---------|
| Python 3.11+ | **Required** | — | Runtime |
| Package install | **Required** | `pip install -e .` in repo root | Installs `report_workflow` and all Python deps |
| **pandoc 3.x** | **Critical** | `winget install JohnMacFarlane.Pandoc` (Win) / `apt install pandoc` (Linux) / `brew install pandoc` (Mac) | DOCX rendering. **Without pandoc, the pipeline silently falls back to a limited python-docx converter with degraded table/list formatting and no TOC.** |
| **mmdc** (mermaid-cli) | Optional | `npm install -g @mermaid-js/mermaid-cli` | Converts `mermaid` code fences to PNG diagrams. |

### Optional Integration Dependencies

These enable advanced features but are **never required** — the pipeline gracefully skips when they are missing.

| Dependency | Feature | Setup | What Happens When Missing |
|------------|---------|-------|---------------------------|
| **notebooklm-py** | NotebookLM knowledge sync | `pip install notebooklm-py` + browser auth | NOTEBOOK_SYNC node logs warning and skips |
| **TAVILY_API_KEY** | Web research (recommended) | Set env var with API key from [tavily.com](https://tavily.com) | Falls back to next backend or no-op |
| **SERPER_API_KEY** | Web research (alternative) | Set env var with API key from [serper.dev](https://serper.dev) | Falls back to next backend or no-op |
| **SERPAPI_API_KEY** | Web research (alternative) | Set env var with API key from [serpapi.com](https://serpapi.com) | Falls back to next backend or no-op |
| **BROWSER_MCP_SEARCH_COMMAND** | Shell-based browser search | Set env var with command template | Falls back to next backend or no-op |

### Verification Commands

```bash
pandoc --version                         # Should return 3.x
mmdc --version                           # Optional — confirms mermaid-cli
python -c "import report_workflow"       # Confirms package is installed
python -c "from report_workflow.connectors.research_backends import get_backend_capability_matrix; import json; print(json.dumps(get_backend_capability_matrix(), indent=2))"  # Shows research backend status
```

> **How preflight works**: Missing Python packages → **hard-block** (workflow won't start).
> Missing pandoc/mmdc → **warnings** in the return dict (workflow starts, but output quality degrades).
> Missing API keys → optional nodes silently skip (no degradation to core pipeline).
> Always check the `warnings` field in tool return values.

---

## The Three-Phase Architecture

The workflow is split into three strictly ordered phases. You interact primarily between Phase 1 and Phase 2.

### Phase 1: Prepare (Pipeline Runs)

The pipeline parses source files and writes **task briefs** — Markdown files that instruct you what to produce and in what format.

**You receive:**
- `~/.hermes/workflow_runs/<job_id>/agent_tasks/01_claim_plan.md`
- `~/.hermes/workflow_runs/<job_id>/agent_tasks/02_outline_plan.md`
- `~/.hermes/workflow_runs/<job_id>/agent_tasks/03_section_draft.md`

**These briefs define:**
- The required JSON schema for each artifact
- Hard rules that will cause validation to fail if violated
- Evidence previews (a compact table of the first 20 evidence entries from the parsed sources)

**You also receive:**
- `~/.hermes/workflow_runs/<job_id>/section_skeletons/*.md` — starter files with correct headings and CITE examples. Use these as your starting point for section drafts!

**Optional prepare nodes (when enabled):**
- **NOTEBOOK_SYNC**: If `enable_notebook_sync=True`, syncs context from a NotebookLM notebook after evidence store. Results go to `notebook_sync_results.json`.

### Phase 2: Author (You Run — 4-Step Incremental)

You read the briefs and produce artifacts **one at a time**, validating after each step. This prevents context window exhaustion on large projects.

| Step | Tool | Artifact | What it validates |
|------|------|----------|------------------|
| 2a | `submit_claim_matrix` | `claim_matrix.json` | Schema, evidence linkage, claim roles |
| 2b | `submit_outline` | `outline.json` | Blueprint coverage, section allocation |
| 2c | `submit_drafts` | `section_drafts/*.md` + `sentence_map.jsonl` | Non-empty sections, sentence tracking |

Each step checkpoints independently. If the agent's context window is exhausted mid-task, the workflow can be resumed from the last successful checkpoint.

> **Legacy mode**: You can also create all artifacts at once and skip directly to Phase 3. This works for small projects but is risky for large codebases.

### Phase 3: Validate + Render (Pipeline Runs)

Once you call `submit_and_publish_report`, the pipeline:
1. Validates all artifacts against deterministic gates
2. Resolves citations and strips internal markers
3. Runs factuality and consistency checks
4. **Optionally runs external research** (`RESEARCH_EXECUTE`) for blocked claims
5. **Optionally cross-verifies claims** (`CLAIM_VERIFY_EXECUTE`) against research results
6. Renders a final DOCX via pandoc (with academic styling template)
7. Post-validates the rendered DOCX structure

If validation fails, you get an error message. Fix the artifacts and call `submit_and_publish_report` again.

---

## The Nine Agent Tools

The `report_workflow` skill exposes nine tools:

### `start_report_task`

Starts a new workflow run. Call this once per report request.

```python
start_report_task(
  prompt="write an academic report from these source files",
  source_files=["/path/to/paper.pdf", "/path/to/code/"],
  output_dir="/path/to/output/",
  title="Deterministic Compilation Architecture for Quantitative Trading Strategy Generation",
  author_block="Example Student",
  affiliation_block="Department of Engineering, Example University",
  correspondence="student@example.edu",
  keywords=["deterministic compilation", "StrategyIR", "abstract syntax tree compilation"],
  enable_research=True,              # Optional: enable web research for claim verification
  enable_notebook_sync=False,        # Optional: enable NotebookLM sync
  notebooklm_notebook_id=None,       # Optional: specific notebook ID
  notebooklm_storage_path=None,      # Optional: auth storage path
)
```

Returns: `job_id`, status (`awaiting_agent_artifacts`), guidance on next steps, and optionally a `warnings` field listing missing external tools (e.g., pandoc not installed).

For `academic_report`, provide structured front matter whenever available. The workflow no longer fabricates generic publication metadata from the task prompt.

> **Always check the `warnings` field** in the return value. It will tell you about missing external tools that degrade output quality.

### `submit_claim_matrix` (Step 2a)

Validates `claim_matrix.json`. Call after creating it.

```python
submit_claim_matrix(job_id="<job_id>")
```

### `submit_outline` (Step 2b)

Validates `outline.json`. Requires Step 2a to be complete.

```python
submit_outline(job_id="<job_id>")
```

### `submit_drafts` (Step 2c)

Validates `section_drafts/*.md` and `sentence_map.jsonl`. Requires Steps 2a+2b.

```python
submit_drafts(job_id="<job_id>")
```

### `submit_and_publish_report` (Final)

Runs full validation + render. Can be called after all 3 steps, or directly after `start_report_task` if all artifacts were created at once.

```python
submit_and_publish_report(job_id="<job_id>")
```

- **Success:** Returns path to rendered DOCX, the renderer used (pandoc or fallback), and optionally a `warnings` field if quality was degraded (e.g., pandoc fallback used).
- **Failure:** Returns validation error message. Read it, fix artifacts, call again.

### `query_evidence`

Allows you to look up specific evidence entries by ID or browse the ledger in pages, without loading the massive `evidence_ledger.jsonl` file into your context window.

```python
query_evidence(job_id="<job_id>", evidence_ids=["E001", "E002"])
query_evidence(job_id="<job_id>", offset=0, limit=20)
```

### `remap_agent_artifacts`

Remap evidence IDs when reusing artifacts from a previous run.

```python
# Dry-run first
remap_agent_artifacts(job_id="<current>", previous_job_id="<old>", write=False)
# Apply if mapping is complete
remap_agent_artifacts(job_id="<current>", previous_job_id="<old>", write=True)
```

### `submit_revision_plan` (Revision Workflow)

Pre-validates a `revision_plan.json` for `revise_existing` workflows. Checks that all `original_text` matches exist in the base document and detects conflicting changes.

```python
submit_revision_plan(job_id="<job_id>")
```

Returns a diff preview showing exactly what each change would do. Call this before `submit_and_publish_report`.

### `preview_revision_diff` (Revision Workflow)

Read-only preview of what the revision plan would change. Does NOT apply changes.

```python
preview_revision_diff(job_id="<job_id>")
```

---

## Report Families

| Family | Use Case | Key Rules |
|--------|----------|-----------|
| `academic_report` | Journal submissions, theses, graduate admissions | Thesis required, IMRaD semantics, DOI verification, structured abstract |
| `work_report` | Executive reports, internal documents | Executive summary required, recommendations required |
| `hybrid_report` | Mixed academic/professional | Rules from both |

The pipeline infers the family from your prompt, but you can override it with the `report_family` parameter.

---

## The Evidence Layer (Critical Concept)

Everything in this workflow is **evidence-backed**. The pipeline extracts evidence units from your source files and assigns each an `evidence_id` (e.g., `E001`, `E002`).

**Your claims must cite evidence:**
- In `claim_matrix.json`, each claim has an `evidence_ids` list
- In `section_drafts/*.md`, every evidence-backed sentence must contain `[CITE:<evidence_id>]`
- The pipeline validates that every `evidence_id` in your prose actually exists in the evidence ledger

**Internal markers that will hard-fail:**
- `[Source:]`, `[graphify:]`, `[Note:]` — not allowed in submission text
- Raw evidence IDs (E001, E002) in body prose — use `[CITE:]` instead
- `.py` filenames, internal paths — not allowed in body prose

> **Context-saving tip**: The task briefs include a compact summary of the first 20 evidence entries. For large projects, use the `query_evidence` tool to look up specific entries by ID or page through them, rather than loading the full `evidence_ledger.jsonl`.

---

## Optional Features (Post-Integration)

### External Research for Claim Verification

When `enable_research=True` is passed to `start_report_task`:

1. **RESEARCH_EXECUTE** runs after FACTUALITY_CHECK — blocked/disputed/unverified claims are researched via the best available web backend
2. **CLAIM_VERIFY_EXECUTE** runs after RESEARCH_EXECUTE — cross-references research results against blocked claims and upgrades their verification status

**Backend selection** (automatic, in priority order):
1. **Tavily** (requires `TAVILY_API_KEY`) — recommended, supports deep research
2. **Serper** (requires `SERPER_API_KEY`) — Google search via Serper API
3. **SerpAPI** (requires `SERPAPI_API_KEY`) — Google search via SerpAPI
4. **BrowserMCP** (requires `BROWSER_MCP_SEARCH_COMMAND`) — shell-based browser
5. **ManualAgent** (always available) — no-op fallback, marks tasks as "pending"

**Output files in run directory:**
- `research_results.json` — raw research results with sources and confidence scores
- `claim_verification_results.json` — claim-level coverage assessment and status upgrades

### NotebookLM Knowledge Sync

When `enable_notebook_sync=True` is passed to `start_report_task`:

1. **NOTEBOOK_SYNC** runs after EVIDENCE_STORE — connects to Google NotebookLM
2. Auto-selects a notebook matching the report topic (or use `notebooklm_notebook_id`)
3. Asks analysis questions: missing constants, factual inconsistencies, improvement suggestions
4. Results are stored in `state.knowledge_sync.buffer` and `notebook_sync_results.json`

**Setup:**
```bash
pip install notebooklm-py
# Authenticate via browser (one-time):
python -c "from notebooklm import NotebookLMClient; import asyncio; asyncio.run(NotebookLMClient.authenticate())"
```

### Chinese Engineering Reports

The pipeline includes a guideline for Chinese engineering lab reports (`CHINESE_ENGINEERING.json`):
- **Required sections**: 實驗簡介 → 實驗結果(圖、表)與分析 → 問題與討論 → 心得與建議 → 參考文獻
- **Typography**: 標楷體 (DFKai-SB) for Chinese, Times New Roman for Latin, 12pt
- **Tone gates**: forbidden jargon (NotebookLM, workflow, agent), subjective term warnings, first-person policy
- **Parser enrichment**: automatic formula/constant/question/table detection for CJK-heavy documents

---

## DOCX Rendering

The pipeline renders DOCX using a two-tier approach:

1. **Primary: pandoc** — Produces robust output with correct tables, code blocks, nested lists, and inline formatting. Uses a reference template (`templates/reference.docx`) for academic styling (A4, Times New Roman 12pt, 1.5× line spacing, heading hierarchy).

2. **Fallback: python-docx** — A regex-based converter used only when pandoc is unavailable. Known limitations: tables may not render correctly, complex formatting may break.

After rendering, the pipeline runs **post-render validation** that checks:
- DOCX file exists and is not suspiciously small
- Heading structure is present
- Total text length meets minimum threshold

The renderer used is recorded in `state.output["renderer_used"]`.

---

## Known Limitations and Workarounds

### Figures / Diagrams

The pipeline supports **automatic mermaid diagram conversion** if `mmdc` (mermaid-cli) is installed:

- Write diagrams as ````mermaid` code fences in your section drafts
- The pipeline converts them to PNG images before DOCX rendering
- If mmdc is not installed, mermaid blocks are preserved as code blocks (with a warning)
- ASCII art diagrams (box-drawing characters) are **not supported** and will be flagged by the pre-render sanity gate

### Large Codebases

For projects with hundreds of source files and thousands of evidence entries:
- Use the 4-step incremental workflow (not the legacy all-at-once approach)
- Read evidence in chunks, not the full ledger
- Keep section drafts concise — the pipeline merges them

### Traceability Appendix

The source appendix is rendered as a separate `traceability_appendix.docx`. It is **not** mixed into the main document. If the appendix content is not readable enough for your use case, it may need manual restructuring.

---

## Quality Gates Summary

| Gate | Severity | Description |
|------|----------|-------------|
| Evidence count ≥ 5 | Hard block | Minimum evidence entries for academic mode |
| `code_artifact` evidence present | Hard block | Required for code-based projects |
| `graph_analysis` evidence present | Warning | Recommended but not required |
| `research_document` evidence present | Warning | Recommended but not required |
| Claim-evidence linkage valid | Hard block | All claims must reference valid evidence IDs |
| Citations resolved | Hard block | No unresolved `[CITE:xxx]` in final text |
| No internal markers | Hard block | No `[Source:]`, `[graphify:]`, etc. in publication text |
| Section role semantics (IMRaD) | Hard block | Academic mode: correct content in correct sections |
| FE term overlap ≥ 20% (code) / 40% (other) | Hard block | Evidence must actually support the claim text |
| Facts Freeze | Hard block | If `facts_freeze.json` exists, all its values must be in final DOCX |
| Post-render DOCX valid | Warning | Heading structure, paragraph count, text length |

---

## Common Failure Modes

| Error | Cause | Fix |
|-------|-------|-----|
| `missing citation placeholders` | Sentence cites evidence but lacks `[CITE:<id>]` | Add `[CITE:Exxx]` to the sentence |
| `thesis required in academic mode` | No `thesis_statement` in outline | Add thesis to introduction section |
| `audit table in main text` | Claim-Evidence Matrix table in publication draft | Move to supplementary |
| `section role violation` | IMRaD semantics broken | Move content to correct section |
| `DOCX render failed` | pandoc not installed | Install pandoc 3.x |
| `Merged draft is empty` | Section drafts missing or not created | Create section_drafts/*.md files |

---

## How to Debug

When validation fails:

1. **Read the error message carefully** — it names the specific gate that failed and why
2. **Check the relevant brief** — `agent_tasks/01_claim_plan.md`, etc. contain the rules
3. **Edit the artifact** — fix the JSON or Markdown file that caused the failure
4. **Call `submit_and_publish_report` again** — do NOT call `start_report_task` again (that creates a new run)

---

## Key Files and Locations

| Path | Purpose |
|------|---------|
| `~/.hermes/workflow_runs/<job_id>/` | Working directory for a run |
| `~/.hermes/workflow_runs/<job_id>/agent_tasks/` | Task briefs written by pipeline |
| `~/.hermes/workflow_runs/<job_id>/claim_matrix.json` | Your claim artifact |
| `~/.hermes/workflow_runs/<job_id>/outline.json` | Your outline artifact |
| `~/.hermes/workflow_runs/<job_id>/section_drafts/*.md` | Your section drafts |
| `~/.hermes/workflow_runs/<job_id>/sentence_map.jsonl` | Your sentence map artifact |
| `~/.hermes/workflow_runs/<job_id>/rendered_report.docx` | Final rendered DOCX |
| `~/.hermes/workflow_runs/<job_id>/pandoc_input.md` | Markdown fed to pandoc |
| `~/.hermes/published/<job_id>/` | Final published outputs |
| `~/.hermes/workflow_runs/<job_id>/checkpoint_*.json` | Pipeline state checkpoints |
| `~/.hermes/workflow_runs/<job_id>/evidence_ledger.jsonl` | Evidence extracted by pipeline |
| `~/.hermes/workflow_runs/<job_id>/research_results.json` | Research backend results (when enabled) |
| `~/.hermes/workflow_runs/<job_id>/claim_verification_results.json` | Claim verification report (when enabled) |
| `~/.hermes/workflow_runs/<job_id>/notebook_sync_results.json` | NotebookLM sync results (when enabled) |

---

## Read Next

- **`agent_skill/agent_instructions.md`** — Complete self-contained reference (prerequisites, tools, rules, debugging, file locations)
- **`agent_skill/SKILL.md`** — Quick-reference execution contract with prerequisites table
- **`agent_skill/skill.yaml`** — Tool definitions and parameters
- **`CLAUDE.md`** — Developer context (project overview, debugging guides)
