# Report Workflow Agent Instructions

> This document is the **complete reference** for operating the `report_workflow` skill.
> It contains everything you need: background concepts, prerequisites, tool usage,
> artifact schemas, validation rules, debugging, and file locations.

---

## What Is This Workflow?

**Report Workflow** is a deterministic source-to-report pipeline. Given source files
(research papers, code repositories, datasets, etc.), it produces a structured,
citation-linked, publication-ready DOCX document.

**What it is NOT:**
- It does NOT call an LLM provider. The Python package owns no generative AI.
- It does NOT write the report content. That judgment belongs to you — the agent.
- It does NOT support tracked changes or formatting preservation of existing documents.

**Two-part model:**
- **Pipeline (Python):** Deterministic work — parsing, evidence normalization, validation gates, DOCX rendering (via pandoc), artifact contracts.
- **Agent (you):** Judgment and writing — reading task briefs, producing claims, outlines, section drafts.

---

## Prerequisites

Before first use, ensure the host system has these dependencies installed.
The pipeline runs a **preflight check** on `start_report_task` and will surface
warnings about missing tools in the `warnings` field of the return value.

### Core Dependencies

| Dependency | Required? | Install Command | Purpose |
|------------|-----------|-----------------|---------|
| Python 3.11+ | **Required** | — | Runtime |
| Package install | **Required** | `pip install -e .` in repo root | Installs the `report_workflow` package and all Python dependencies (pydantic, python-docx, pdfplumber, pandas, pyyaml, matplotlib, Pillow) |
| **pandoc 3.x** | **Critical** | `winget install JohnMacFarlane.Pandoc` (Win) / `apt install pandoc` (Linux) / `brew install pandoc` (Mac) | High-quality DOCX rendering with TOC, tables, and academic styling. **Without pandoc, the pipeline silently falls back to a limited python-docx converter with degraded table/list formatting and no TOC.** |
| **mmdc** (mermaid-cli) | Optional | `npm install -g @mermaid-js/mermaid-cli` | Converts `mermaid` code fences to PNG diagrams. Without mmdc, diagrams remain as code blocks. |

### Optional Integration Dependencies

These enable advanced features but are **never required** — the pipeline gracefully
skips when they are missing and logs a warning.

| Dependency | Feature Flag | Setup | What Happens When Missing |
|------------|-------------|-------|---------------------------|
| **notebooklm-py** | `enable_notebook_sync=True` | `pip install notebooklm-py` + browser auth | NOTEBOOK_SYNC node skips with warning |
| **TAVILY_API_KEY** | `enable_research=True` | Set env var (get key from [tavily.com](https://tavily.com)) | Falls back to next backend or ManualAgent no-op |
| **SERPER_API_KEY** | `enable_research=True` | Set env var (get key from [serper.dev](https://serper.dev)) | Falls back to next backend or ManualAgent no-op |
| **SERPAPI_API_KEY** | `enable_research=True` | Set env var (get key from [serpapi.com](https://serpapi.com)) | Falls back to next backend or ManualAgent no-op |
| **BROWSER_MCP_SEARCH_COMMAND** | `enable_research=True` | Set env var with command template | Falls back to ManualAgent no-op |

**Verification commands:**
```bash
pandoc --version    # Should return 3.x
mmdc --version      # Optional — confirms mermaid-cli is installed
python -c "import report_workflow"  # Confirms package is installed
python -c "from report_workflow.connectors.research_backends import get_backend_capability_matrix; import json; print(json.dumps(get_backend_capability_matrix(), indent=2))"  # Shows research backend status
```

> **How preflight works**: Missing Python packages → **hard-block** (workflow won't start).
> Missing pandoc/mmdc → **warnings** in the return dict (workflow starts, but output quality degrades).
> Missing API keys / notebooklm-py → optional nodes silently skip (no degradation to core pipeline).
> Always check the `warnings` field in tool return values.

---

## First-Time Setup & Configuration

The workflow uses two configuration files in the project root for persistent settings:

### `.env` — API Keys and Secrets

Copy `.env.example` to `.env` and fill in the values. API keys set here are loaded
automatically on every `start_report_task()` call.

```bash
# Required for web research feature (at least one):
TAVILY_API_KEY=tvly-xxxxx          # Recommended — sign up at tavily.com
SERPER_API_KEY=                     # Alternative — sign up at serper.dev
SERPAPI_API_KEY=                    # Alternative — sign up at serpapi.com
```

### `workflow_config.yaml` — Feature Flags

Controls which optional features are enabled by default. Edit this file to
change defaults without passing parameters every time.

```yaml
features:
  enable_research: true         # Enable web research for claim verification
  enable_notebook_sync: false   # Enable NotebookLM knowledge sync
```

### Priority Order

Configuration is loaded from multiple sources (highest priority wins):
1. **Function parameters** passed to `start_report_task(enable_research=True)`
2. **Environment variables** (e.g., `TAVILY_API_KEY`)
3. **`.env` file** in project root
4. **`workflow_config.yaml`** in project root

---

## Feature Discovery (Critical for Agents)

**Call `check_setup()` BEFORE `start_report_task` — on EVERY run.**

`check_setup` is a lightweight, zero-parameter tool that:
- Checks all dependencies (Python packages, pandoc, mmdc)
- Scans for API keys (`.env`, environment variables)
- Discovers available optional features
- Returns a `message` with human-readable setup results
- Returns `agent_should_ask_user` — a list of features to ask the user about

**You MUST read and act on `agent_should_ask_user`:**

1. Present each option to the user and let them decide
2. **Check `requires_user_input`** — if non-empty, you need to collect specific
   information from the user (API keys, notebook URLs, etc.)
3. **Check `ask_every_time`** — some features (like NotebookLM) need fresh input
   on every run because each report uses different resources
4. Only proceed to `start_report_task` after collecting all required inputs

### Example: First Use (No API Key Yet)

```
Agent calls check_setup()
  ↓
Return message includes:
  "1. 要啟用「外部網路研究」嗎？
      目前尚未設定任何搜尋 API key。
      📝 需要使用者提供:
         - 請提供 Tavily API Key（推薦，至 tavily.com 註冊取得）
           範例: tvly-xxxxxxxxxx
           → Agent 收到後寫入 .env: TAVILY_API_KEY=<使用者提供的值>
   2. 要啟用「NotebookLM 知識同步」嗎？
      📝 需要使用者提供:
         - 請提供此報告對應的 NotebookLM 筆記本網址或 ID
           範例: https://notebooklm.google.com/notebook/abc123
      ⚡ 注意: 此項每次執行報告都需要確認"
  ↓
Agent asks user:
  "這個工作流支援外部研究和 NotebookLM 整合功能：
   1. 外部研究 — 需要提供 Tavily API Key，要啟用嗎？
   2. NotebookLM — 需要提供筆記本網址，要啟用嗎？"
  ↓
User says: "兩個都要，Tavily key 是 tvly-abc123，
           NotebookLM 網址是 https://notebooklm.google.com/notebook/xyz789"
  ↓
Agent writes "TAVILY_API_KEY=tvly-abc123" to .env file
Agent calls start_report_task(
    ...,
    enable_research=True,
    enable_notebook_sync=True,
    notebooklm_notebook_id="xyz789",
)
  ↓
Proceed with report authoring
```

### Example: Repeat Use (API Key Already in .env)

```
Agent calls check_setup()
  ↓
Return message includes:
  "1. 要啟用「外部網路研究」嗎？
      目前後端狀態: Tavily=✓   ← API key already exists!
   2. 要啟用「NotebookLM 知識同步」嗎？
      📝 需要使用者提供:
         - 請提供此報告對應的 NotebookLM 筆記本網址或 ID
      ⚡ 注意: 此項每次執行報告都需要確認"
  ↓
Agent asks user:
  "偵測到已有 Tavily API key，要啟用外部研究嗎？
   另外，要使用 NotebookLM 嗎？需要提供此報告對應的筆記本網址。"
  ↓
User says: "研究開啟，NotebookLM 這次不用"
  ↓
Agent calls start_report_task(..., enable_research=True)
  ↓
Proceed with report authoring (no need to re-enter API key)
```

> **Key rules**:
> 1. `requires_user_input` is empty → just ask "yes/no" to enable
> 2. `requires_user_input` is non-empty → ask "yes/no" AND collect the required info
> 3. `ask_every_time: true` → this feature needs fresh input on EVERY run
> 4. API keys go into `.env` (persist across runs); notebook IDs go as `start_report_task` parameters (change per report)


## The Three-Phase Architecture

The workflow is split into three strictly ordered phases. You interact primarily between Phase 1 and Phase 2.

### Phase 1: Prepare (Pipeline Runs Automatically)

When you call `start_report_task`, the pipeline parses source files, extracts evidence,
and writes **task briefs** — Markdown files that instruct you what to produce and in what format.

**Pipeline produces these files in `~/.hermes/workflow_runs/<job_id>/`:**

| File | Purpose |
|------|---------|
| `evidence_ledger.jsonl` | All evidence entries extracted from your source files |
| `blueprint.json` | Report structure blueprint (section definitions) |
| `agent_tasks/01_claim_plan.md` | Task brief: how to write `claim_matrix.json` |
| `agent_tasks/02_outline_plan.md` | Task brief: how to write `outline.json` |
| `agent_tasks/03_section_draft.md` | Task brief: how to write section drafts + sentence map |
| `section_skeletons/*.md` | Starter files with correct headings and CITE examples |
| `project_identity.json` | Project identity contract (if provided) |

**These briefs define:**
- The required JSON schema for each artifact
- Hard rules that will cause validation to fail if violated
- Evidence previews (a compact table of the first 20 evidence entries)

### Phase 2: Author (You — 4-Step Incremental)

You read the briefs and produce artifacts **one at a time**, validating after each step.
This prevents context window exhaustion on large projects.

| Step | Tool | Artifact You Create | What Pipeline Validates |
|------|------|---------------------|------------------------|
| 2a | `submit_claim_matrix` | `claim_matrix.json` | JSON schema, evidence linkage, claim roles |
| 2b | `submit_outline` | `outline.json` | Blueprint coverage, section allocation, results_mode |
| 2c | `submit_drafts` | `section_drafts/*.md` + `sentence_map.jsonl` | Non-empty sections, sentence tracking, no forbidden patterns |

Each step checkpoints independently. If your context window is exhausted mid-task,
the workflow can be resumed from the last successful checkpoint.

> **Legacy mode**: You can also create all artifacts at once and skip directly to Phase 3.
> This works for small projects but is risky for large codebases.

### Phase 3: Validate + Render (Pipeline Runs Automatically)

Once you call `submit_and_publish_report`, the pipeline:
1. Validates all artifacts against 13+ deterministic gates
2. Resolves `[CITE:xxx]` markers and generates a formal reference list
3. Runs factuality checks (claim-evidence term overlap)
4. **Optionally executes external research** (`RESEARCH_EXECUTE`) for blocked/disputed claims
5. **Optionally cross-verifies claims** (`CLAIM_VERIFY_EXECUTE`) against research results
6. Checks section role semantics (IMRaD boundaries)
7. Renders a final DOCX via pandoc (with academic styling template)
8. Post-validates the rendered DOCX structure
9. Publishes to the output directory

If validation fails, you get an error message with specific gate failures.
Fix the artifacts and call `submit_and_publish_report` again.

---

## The Evidence Layer (Critical Concept)

Everything in this workflow is **evidence-backed**. The pipeline extracts evidence
units from your source files and assigns each an `evidence_id` (e.g., `E001`, `E002`).

**Your claims must cite evidence:**
- In `claim_matrix.json`, each claim has an `evidence_ids` list
- In `section_drafts/*.md`, every evidence-backed sentence must contain `[CITE:<evidence_id>]`
- The pipeline validates that every `evidence_id` in your prose actually exists in the evidence ledger

**Internal markers that will hard-fail:**
- `[Source:]`, `[graphify:]`, `[Note:]` — not allowed in submission text
- Raw evidence IDs (E001, E002) in body prose — use `[CITE:]` instead
- `.py` filenames, internal paths — not allowed in body prose

> **Context-saving tip**: The task briefs include a compact summary of the first 20
> evidence entries. For large projects, use `query_evidence` to look up specific entries
> by ID or page through them, rather than loading the full `evidence_ledger.jsonl`.

---

## Step-by-Step Workflow

### Step 0: Environment Check & Feature Setup (Every Run)

1. Call `check_setup()` (no parameters).
2. Read the `message` field — it contains a human-readable summary.
3. If `agent_should_ask_user` is non-empty, present each option to the user.
4. For each item with `requires_user_input`, collect the needed info from the user:
   - **API keys** → write to `.env` file (persists, won't ask again next time)
   - **NotebookLM URL** → pass as `notebooklm_notebook_id` parameter (changes per report)
5. Note the user's choices — you will pass them as flags to `start_report_task`.

### Step 1: Start the Workflow

1. Call `start_report_task` with:
   - `prompt`: the user's report request
   - `source_files`: list of file paths to use as source data
   - `output_dir`: where to put the final DOCX
   - `report_family`: `academic_report`, `work_report`, or `hybrid_report`
   - For `academic_report`, also pass structured front matter: `title`, `author_block`, `affiliation_block`, `correspondence`, `keywords`
   - If the report must preserve a known project identity, pass `project_identity`
   - Pass `enable_research=True` if the user confirmed in Step 0
   - Pass `enable_notebook_sync=True` if the user confirmed in Step 0

2. The tool returns `status: "awaiting_agent_artifacts"` along with a `job_id`.
   **Check the `warnings` field** — it will tell you about missing external tools.

3. The task briefs are at `~/.hermes/workflow_runs/<job_id>/agent_tasks/`.

### Step 2: Read Task Briefs & Write Artifacts (Incremental)

Read the task briefs and create artifacts **one at a time**, validating after each step.

#### Step 2a: Claim Matrix
1. Read `01_claim_plan.md` and the evidence summary.
2. Use `query_evidence` to look up specific evidence entries as needed.
3. Create `claim_matrix.json` in `~/.hermes/workflow_runs/<job_id>/`.
4. Call `submit_claim_matrix` with your `job_id` to validate.
5. If validation fails, fix claim_matrix.json and call again.

#### Step 2b: Outline
1. Read `02_outline_plan.md`.
2. Create `outline.json` in the run directory.
3. Call `submit_outline` with your `job_id` to validate.
4. If validation fails, fix outline.json and call again.

#### Step 2c: Section Drafts
1. Read `03_section_draft.md`.
2. Start from the generated `section_skeletons/*.md` files (correct headings, CITE examples).
3. Create `section_drafts/*.md` files for each section and `sentence_map.jsonl`.
4. Call `submit_drafts` with your `job_id` to validate.
5. If validation fails, fix the drafts and call again.

### Step 3: Submit & Publish
1. Once all 3 steps above pass, call `submit_and_publish_report` with your `job_id`.
2. This runs the full validation pipeline and renders the DOCX via pandoc.
3. **Check the `warnings` field** — it will tell you if pandoc fallback was used.
4. **If it fails**: Read the error message, fix the failing artifact, and call again.
5. **If it succeeds**: Provide the final DOCX path to the user.

---

## Tool Reference

The `report_workflow` skill exposes 10 tools:

### `check_setup` (Step 0 — First Use)

Pre-flight environment check. Call **before** `start_report_task` on first use.

```python
check_setup()
```

**Returns:** `status`, `message` (human-readable), `feature_discovery`, `agent_should_ask_user`, `config_summary`, `preflight`.

The `message` field contains a formatted summary. Read it and present the `agent_should_ask_user` items to the user.

### `start_report_task` (Step 1)

Starts a new workflow run. Call this **once** per report request.

```python
start_report_task(
    prompt="write an academic report from these source files",
    source_files=["/path/to/paper.pdf", "/path/to/code/"],
    output_dir="/path/to/output/",
    report_family="academic_report",
    title="Your Report Title",
    author_block="Author Name",
    affiliation_block="Department, University",
    correspondence="email@example.edu",
    keywords=["keyword1", "keyword2"],
    project_identity={...},              # optional — see below
    enable_research=True,                # optional — enable web claim research
    enable_notebook_sync=False,          # optional — enable NotebookLM sync
    notebooklm_notebook_id=None,         # optional — specific notebook ID
    notebooklm_storage_path=None,        # optional — auth file path
)
```

**Returns:** `job_id`, `status`, `message`, and optionally `warnings`.

**`project_identity` shape** (pass when the report must preserve a known project):
```json
{
  "required_terms": ["deterministic compilation", "StrategyIR"],
  "required_context_terms": ["compiler architecture"],
  "forbidden_terms": ["Research Author", "Research University"],
  "canonical_title_terms": ["deterministic", "compilation"],
  "domain_context": "Taiwan equities",
  "author_metadata": {
    "author_block": "Example Student",
    "affiliation_block": "Department of Engineering, Example University",
    "correspondence": "student@example.edu"
  }
}
```

**`enable_research`** — When `True`, the pipeline runs `RESEARCH_EXECUTE` and `CLAIM_VERIFY_EXECUTE` after factuality check. Requires at least one API key env var (`TAVILY_API_KEY`, `SERPER_API_KEY`, or `SERPAPI_API_KEY`). Without keys, tasks are marked as "pending" for manual follow-up.

**`enable_notebook_sync`** — When `True`, the pipeline runs `NOTEBOOK_SYNC` after evidence store to sync context from a NotebookLM notebook. Requires `pip install notebooklm-py` and authenticated browser session.

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

Runs full validation + render. Can be called after all 3 steps, or directly after `start_report_task` if all artifacts were created at once (legacy mode).

```python
submit_and_publish_report(job_id="<job_id>")
```

**Success returns:** `final_docx_path`, `published_report_path`, `renderer_used`, `workflow_success=true`, and optionally `warnings`.
**Failure returns:** `error_details` explaining which gate failed.

### `query_evidence`

Look up specific evidence entries by ID or browse the ledger in pages.
Use this instead of loading `evidence_ledger.jsonl` to save context window space.

```python
query_evidence(job_id="<job_id>", evidence_ids=["E001", "E002"])
query_evidence(job_id="<job_id>", offset=0, limit=20)  # paginated browse
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

Pre-validates `revision_plan.json` for `revise_existing` workflows.
Checks that all `original_text` matches exist in the base document.

```python
submit_revision_plan(job_id="<job_id>")
```

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

The pipeline infers the family from your prompt, but you can override it with `report_family`.

---

## Revise-Existing Mode

When a **canonical base document** (clean Markdown) already exists, use `revise_existing` mode:

1. Start with `intent="revise_existing"` and include the base document as a source file with role `base_document`.
2. Do **NOT** rewrite the entire document from scratch. Make targeted section-by-section corrections.
3. Preserve the thesis spine, heading structure, and overall framing of the base document.
4. Only modify content that needs factual correction, metric updates, or structural fixes.

### Revision Workflow Procedure

1. Create `revision_plan.json` following `04_revision_plan.md` brief.
2. Call `submit_revision_plan` to pre-validate your changes. This checks:
   - Every `original_text` exists in the base document
   - No overlapping/conflicting changes in the same section
3. If validation fails, fix `revision_plan.json` and call again.
4. Optionally call `preview_revision_diff` to see a read-only diff preview.
5. Once validated, call `submit_and_publish_report` to apply and render.

> **Important**: If any `original_text` cannot be found in the base document, the pipeline will **hard block**. Ensure you copy the exact text from the base document (≥20 characters for unambiguous matching).

### Pre-render Sanity Gates

Before calling `submit_and_publish_report`, verify the merged markdown against these hard gates:

| Gate | Check |
|------|-------|
| No duplicated headings | Each heading text appears exactly once |
| No duplicated References | Only one `## References` section |
| No placeholder metadata | No `[Author Name]`, `[University]`, `[email@domain.com]` |
| Correct metrics | All project-specific numbers match confirmed values |
| No unresolved citations | No `[CITE:xxx]` remaining |
| No internal markers | No `[Source:]`, `[graphify:]`, `[Note:]` |
| No ASCII art code fences | No ``` blocks with box-drawing characters |
| No orphan appendix | No traceability/debug content after main body |
| No End-of-Report sentinel | No "End of Main Report" text |
| Facts Freeze compliance | If `facts_freeze.json` exists in run dir, all its values must be in text |

If **any** gate fails, fix the markdown before rendering.

---

## Academic Report Mode Rules

When the report family is `academic_report` (for graduate school admissions, journal submissions, or thesis chapters), the following **hard blocks** apply. These are enforced by the pipeline and will cause validation to fail.

### Claim Matrix
- Every claim MUST have a `claim_role` field: `primary`, `supporting`, or `background`.
- 1–3 primary claims required. Primary claims must directly support the thesis/contribution.
- `supporting` and `background` claims back or contextualize primary claims. They must NOT be presented as co-equal contributions.
- Claims with `status: blocked|unverified|disputed` cannot be published.

### Section Drafts

#### Forbidden Patterns (will hard-fail)
- **Internal markers**: `[Source:]`, `[graphify:]`, `[Note:]` in main text prose. Use `[CITE:<evidence_id>]` ONLY in citation contexts.
- **Internal paths**: Evidence IDs (E001, E002), `.py` filenames, internal paths (e.g. `~/.hermes/...`, `D:\...`) in body text.
- **Internal tables**: Claim-Evidence Matrix tables, Community-to-Contribution Mapping tables, or any table with "Claim ID", "Evidence ID", "Status" column headers.
- **Placeholder metadata**: `[Author Name]`, `[University]`, `[email@domain.com]`. Use real values or leave blank (pipeline will auto-fill).

#### Methods Section
- Write as a **research protocol**: describe what you did, not what the system does.
- Use past tense: "we performed X", "we applied Y".
- Use passive voice where appropriate: "X was applied to Y", "measurements were taken".
- Do NOT write as system documentation: avoid present-tense architectural descriptions.
- Do NOT include raw results here: findings belong in Results, not Methods.

#### Results Section
- Present only findings: data, measurements, observations.
- Do NOT interpret results here: interpretation belongs in Discussion.
- Do NOT include Claim-Evidence Matrix or audit tables.
- Numeric claims must include units with spaces: "226 edges" not "226edges".

#### Discussion Section
- Interpret results, don't just restate them.
- Address each primary claim from the claim matrix.
- Compare with related work where applicable.

#### Figures
- Reference each figure by number in the body text **before** the figure appears.
- Format: "Figure 1 shows..." or "see Figure 2".
- Collect all figure captions in a `figure_captions.md` file.
- **Recommended**: Use ````mermaid` code fences for diagrams (flowcharts, sequence diagrams, etc.). The pipeline auto-converts them to PNG if `mmdc` is installed.
- **Forbidden**: ASCII art diagrams (box-drawing characters like ┌─┐). They will be flagged by the pre-render sanity gate.

#### Abstract
- Two accepted formats depending on the `report_subtype`:
  - **Structured (Journal style)**: 180–220 words. Must use exactly 5 headings (`## Background:`, `## Objective:`, etc.).
  - **Plain Paragraph (Admissions/Project style)**: 150-250 words. Single continuous paragraph with no sub-headings.
- Citation-free: no `[CITE:]` markers.
- No duplicated text from other sections.
- No trailing ellipses (`...`), no incomplete sentences.
- No internal markers: `[Source:]`, `[graphify:]`.

### Citation Format
- Use only `[CITE:<evidence_id>]` for evidence-backed claims in section drafts.
- Do NOT use bare `[Source:...]` or `[graphify:...]` — these are pipeline-internal markers that will not resolve and will hard-fail at CITATION_BIND.
- For figures from graph analysis, use `[CITE:<evidence_id>]` that points to the graph figure evidence.

### Section Role Boundaries
- Introduction: no raw results, no percentages, no "our results/findings"
- Methods: no conclusions, no "significant" findings
- Results: no interpretation ("suggests that", "indicates that"), no raw percentages without context
- Discussion: no raw numbers that belong in Results

---

## Front Matter

For `academic_report`, front matter is now strict:

- do not rely on prompt-derived title/author metadata
- do not expect generic fallbacks
- provide structured values through `start_report_task` when possible
- keywords must be thesis-aligned academic terms, not repo/tooling noise

If structured front matter is missing, the pipeline hard-fails instead of fabricating publication metadata.

---

## DOCX Rendering Details

The final DOCX is rendered using a two-tier approach:

1. **Primary: pandoc** — Produces robust output with correct tables, code blocks, nested lists, and inline formatting. Uses a reference template (`templates/reference.docx`) for academic styling (A4, Times New Roman 12pt, 1.5× line spacing, heading hierarchy). Includes auto-generated Table of Contents (depth 3).

2. **Fallback: python-docx** — A regex-based converter used only when pandoc is unavailable. Known limitations: tables may not render correctly, complex formatting may break, no TOC support. **If this fallback is used, a warning will appear in the return value.**

After rendering, the pipeline runs **post-render validation** that checks:
- DOCX file exists and is not suspiciously small
- Heading structure is present
- Total text length meets minimum threshold

The renderer used is recorded in the return value as `renderer_used`.

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
| `Pre-render sanity check failed` | Placeholder metadata, internal markers, etc. | Read the issue list and fix each item |
| `QA gate failed` | One or more hard-block quality gates didn't pass | Check `hard_fail_reasons` in error details |

---

## How to Debug

When validation fails:

1. **Read the error message carefully** — it names the specific gate that failed and why
2. **Check the relevant brief** — `agent_tasks/01_claim_plan.md`, etc. contain the rules
3. **Edit the artifact** — fix the JSON or Markdown file that caused the failure
4. **Call `submit_and_publish_report` again** — do NOT call `start_report_task` again (that creates a new run)
5. **Check `warnings`** — the return value may contain non-blocking warnings about degraded quality

---

## Final Delivery Self-Audit

Do not deliver solely because `qa_decision=pass`. Before reporting success, check:

- title, thesis, abstract, introduction, and conclusion still describe the same project identity
- front matter uses real author/institution/contact values and contains no `**` or placeholder residue
- every Figure reference has a matching caption and rendered object
- references are publication-grade and project-bearing, not generic bibliography padding
- admissions-facing tone remains scholarly and does not address the committee directly
- `renderer_used` is `pandoc` (not `python-docx (fallback)`) for production quality

If validation reports evidence IDs from another run, do not repair them by hand.
Call `remap_agent_artifacts(job_id="<current>", previous_job_id="<old>", write=false)`;
if the dry-run maps every referenced ID, call again with `write=true`.

Only report success when the workflow returns `status=completed` and
`workflow_success=true`. Do not manually copy `rendered_report.docx` from a run
that failed a later render/publish gate.

Scratch scripts belong under the workflow run directory or system temp. Do not
leave `fix_*.py`, `strip_figures*.py`, `run_start.py`, or similar repair files
in the repository root.

---

## Key Files and Locations

| Path | Purpose |
|------|---------|
| `~/.hermes/workflow_runs/<job_id>/` | Working directory for a run |
| `~/.hermes/workflow_runs/<job_id>/agent_tasks/` | Task briefs written by pipeline |
| `~/.hermes/workflow_runs/<job_id>/section_skeletons/` | Starter section templates |
| `~/.hermes/workflow_runs/<job_id>/evidence_ledger.jsonl` | Evidence extracted by pipeline |
| `~/.hermes/workflow_runs/<job_id>/blueprint.json` | Report structure blueprint |
| `~/.hermes/workflow_runs/<job_id>/claim_matrix.json` | Your claim artifact |
| `~/.hermes/workflow_runs/<job_id>/outline.json` | Your outline artifact |
| `~/.hermes/workflow_runs/<job_id>/section_drafts/*.md` | Your section drafts |
| `~/.hermes/workflow_runs/<job_id>/sentence_map.jsonl` | Your sentence map artifact |
| `~/.hermes/workflow_runs/<job_id>/rendered_report.docx` | Final rendered DOCX |
| `~/.hermes/workflow_runs/<job_id>/pandoc_input.md` | Markdown fed to pandoc |
| `~/.hermes/workflow_runs/<job_id>/checkpoint_*.json` | Pipeline state checkpoints |
| `~/.hermes/published/<job_id>/` | Final published outputs |
| `~/.hermes/workflow_runs/<job_id>/research_results.json` | Research backend results (when `enable_research=True`) |
| `~/.hermes/workflow_runs/<job_id>/claim_verification_results.json` | Claim verification report (when `enable_research=True`) |
| `~/.hermes/workflow_runs/<job_id>/notebook_sync_results.json` | NotebookLM sync results (when `enable_notebook_sync=True`) |

---

## Hard Prohibitions

- Do not fabricate `Research Author`, `Research University`, or template email metadata.
- Do not publish front matter with `**` or bracket placeholders.
- Do not introduce forbidden project-drift terms from `project_identity`.
- Do not use claim, outline, or sentence-map artifacts from another run without remapping evidence IDs.
- Do not edit `.hermes` checkpoint files, `base_document_sections.json`, or evidence ledgers by hand to make gates pass.
- Do not create temporary repair scripts in the repository root; place scratch scripts under the run directory or system temp and remove them.
- Do not cite internal workflow files, evidence ledgers, claim matrices, or traceability appendices in the main report.
- Do not leave generic bibliography padding in an admissions project report.
