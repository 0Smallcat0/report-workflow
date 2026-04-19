# Agent Onboarding: Report Workflow

This document is the **entry point** for any agent encountering this workflow for the first time. Read this before reading `agent_skill/agent_instructions.md` or calling any workflow tools.

---

## What Is This Workflow?

**Report Workflow** is a deterministic source-to-report pipeline. Given source files (research papers, code repositories, datasets, etc.), it produces a structured, citation-linked, publication-ready document.

**What it is NOT:**
- It does NOT call an LLM provider. The Python package owns no generative AI.
- It does NOT write the report content. That judgment belongs to you — the agent.
- It does NOT support tracked changes or formatting preservation of existing documents.

**Two-part model:**
- **Pipeline (Python):** Deterministic work — parsing, evidence normalization, validation gates, DOCX rendering, artifact contracts.
- **Agent (you):** Judgment and writing — reading task briefs, producing claims, outlines, section drafts.

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
- Evidence previews (excerpts from source files the pipeline has already parsed)

### Phase 2: Author (You Run)

You read the briefs and produce four artifacts, saved into `~/.hermes/workflow_runs/<job_id>/`:

| Artifact | Description |
|----------|-------------|
| `claim_matrix.json` | Claims with evidence IDs, roles (primary/supporting/background), and status |
| `outline.json` | Section allocation — which claims go where |
| `section_drafts/*.md` | Per-section prose with `[CITE:<evidence_id>]` placeholders |
| `sentence_map.jsonl` | Sentence-level citation tracking |

**You MUST follow the schemas and hard rules in the briefs.** The pipeline will validate your artifacts and hard-block if rules are violated.

### Phase 3: Validate + Render (Pipeline Runs)

Once you call `submit_and_publish_report`, the pipeline:
1. Validates all artifacts against deterministic gates
2. Resolves citations and strips internal markers
3. Renders a final DOCX

If validation fails, you get an error message. Fix the artifacts and call `submit_and_publish_report` again.

---

## The Two Entry Point Tools

The `report_workflow` skill exposes two tools:

### `start_report_task`

Starts a new workflow run. Call this once per report request.

```
start_report_task(
  prompt="write an academic report from these source files",
  source_files=["/path/to/paper.pdf", "/path/to/code/"],
  output_dir="/path/to/output/"
)
```

Returns: `job_id`, status (`awaiting_agent_artifacts`), and a list of missing artifacts.

### `submit_and_publish_report`

Validates your artifacts and renders the final DOCX. Call this after producing all four artifacts.

```
submit_and_publish_report(job_id="<job_id>")
```

- **Success:** Returns path to `final.docx`
- **Failure:** Returns validation error message. Read it, fix artifacts, call again.

---

## Report Families

The workflow supports three report families. The family determines which validation rules apply.

| Family | Use Case | Key Rules |
|--------|----------|-----------|
| `academic_report` | Journal submissions, theses, graduate admissions | Thesis required, structured abstract, IMRaD semantics, DOI verification |
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

---

## Citation Format Rules

**Correct:**
- `[CITE:E001]` — evidence-backed claim
- `[CITE:multiple: E001, E002]` — multiple evidence for one claim

**Will hard-fail:**
- `[Source: anything here]` — internal marker, not a citation
- `[graphify: anything here]` — internal marker
- Bare evidence IDs without brackets

---

## Academic Report-Specific Rules

If the report family is `academic_report`, these additional rules apply:

### Thesis
- A `thesis_statement` must appear in the outline's introduction section
- 1–3 primary claims required; they must directly support the thesis
- `supporting` and `background` claims back or contextualize primary claims — they are NOT co-equal contributions

### Section Semantics (IMRaD)
- **Introduction:** No raw results, no percentages, no "our results/findings"
- **Methods:** No conclusions, no "significant" findings; write as research protocol (past tense)
- **Results:** Present only findings (data, measurements); no interpretation
- **Discussion:** Interpret results, compare with related work; no raw numbers that belong in Results

### Abstract
- Structured headings: Background, Objective, Methods, Principal Findings, Significance
- 150–220 words
- No trailing ellipses, no incomplete sentences
- No internal markers

### Figures
- Reference each figure by number in body text **before** the figure appears: "Figure 1 shows..."
- Collect captions in a `figure_captions.md` file

---

## What Happens at Validation Time

When you call `submit_and_publish_report`, the pipeline runs these gates in order:

1. **CLAIM_PLAN** — claim_matrix.json schema and claim role validation
2. **OUTLINE_PLAN** — outline.json schema and section coverage
3. **PAPER_SCOPE_FREEZE** — thesis presence, RQ validity, claim allocation (academic)
4. **SECTION_PLAN_FREEZE** — all claims covered by outline sections
5. **FRONT_MATTER_BUILD** — front matter completeness (academic)
6. **ABSTRACT_CHECK** — abstract structure and word count (academic)
7. **SECTION_DRAFT** — all required sections exist and are non-empty
8. **METHODS_PROTOCOL_BUILD** — methods written as research protocol (academic)
9. **FIGURE_BUILD** — figure generation from figure_plan.json (if matplotlib available)
10. **REVISION_APPLY** — revision directive application
11. **MERGE_DRAFT** — merge all sections, strip internal markers, remove audit tables
12. **SECTION_ROLE_CHECK** — IMRaD semantics enforced before citation stripping
13. **CITATION_BIND** — resolve `[CITE:]` placeholders, verify citation audit
14. **REFERENCE_VERIFY** — DOI/arXiv verification (academic hard block)
15. **FACTUALITY_CHECK** — claim evidence linkage, numeric overlap, term overlap
16. **FIGURE_QUALITY** — figure contract, no audit tables in main text (academic)
17. **QA_GATE** — aggregate all hard failures; if any exist, block rendering

**If QA_GATE passes:** DOCX is rendered and published.

**If QA_GATE fails:** You get a list of hard failure reasons. Fix the root cause in your artifacts.

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
| `~/.hermes/published/<job_id>/` | Final published outputs |
| `~/.hermes/workflow_runs/<job_id>/checkpoint_*.json` | Pipeline state checkpoints |
| `~/.hermes/workflow_runs/<job_id>/evidence_ledger.jsonl` | Evidence extracted by pipeline |

---

## Common Failure Modes

| Error | Cause | Fix |
|-------|-------|-----|
| `missing citation placeholders for evidence-backed sentences` | Sentence in section draft cites evidence but lacks `[CITE:<id>]` | Add `[CITE:Exxx]` to the sentence |
| `thesis required in academic mode` | No `thesis_statement` in outline | Add thesis to introduction section |
| `unverifiable reference in academic mode` | DOI or arXiv doesn't resolve | Fix the reference or remove it |
| `audit table in main text` | Claim-Evidence Matrix table found in publication draft | These belong in supplementary, not main text |
| `section role violation` | IMRaD semantics broken (e.g., results in Introduction) | Move content to correct section |

---

## How to Debug

When validation fails:

1. **Read the error message carefully** — it names the specific gate that failed and why
2. **Check the relevant brief** — `agent_tasks/01_claim_plan.md`, etc. contain the rules
3. **Edit the artifact** — fix the JSON or Markdown file that caused the failure
4. **Call `submit_and_publish_report` again** — do NOT call `start_report_task` again (that creates a new run)

---

## Read Next

- **`agent_skill/agent_instructions.md`** — Step-by-step tool usage
- **`workflow/minimal-high-quality-workflow.md`** — Post-refactor design and architecture reference
- **`CLAUDE.md`** — Developer context (project overview, debugging guides)
