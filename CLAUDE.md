# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **For agents:** See **`AGENT_ONBOARDING.md`** at the repo root for the agent-facing entry point document — explains the workflow concept, three-phase architecture, tool usage, and common failure modes. Start there if you are a newly onboarded agent.

## Project Overview

`report-workflow` is a **deterministic source-to-report pipeline** designed to run inside an agent environment (Claude Code, Codex, Hermes, etc.). The Python package does **not** call any LLM and does not require an API key — it owns parsing, evidence normalization, artifact contracts, validation gates, and DOCX rendering. The external agent owns judgment and drafting by reading generated task briefs and producing required artifacts.

## Canonical Package Location

**The installed package lives at [src/report_workflow/](src/report_workflow/).** `pyproject.toml` sets `package-dir = {"" = "src"}`, so `import report_workflow` resolves there. A staged-for-deletion set of root-level legacy directories (`nodes/`, `parsers/`, `validators/`, `connectors/`, plus `state.py`, `run_workflow.py`) may still appear in `git status` — those files are already removed from disk and are NOT the workflow; all edits belong under `src/report_workflow/`.

## Commands

```powershell
# Install (editable)
pip install -r requirements.txt
pip install -e .

# Or via setup helper
./setup_skill.ps1

# Run tests (unittest)
python -m unittest discover -s tests -v

# Run a single test
python -m unittest tests.test_mvp_workflow.StageWorkflowTests.test_full_staged_agent_artifact_workflow

# CLI (exposed by entry point `report-workflow = report_workflow.cli:main`)
report-workflow prepare  --prompt "..." --source path\to\src.txt [--source base.docx:base_document] --output out\dir \
                         [--family academic_report|work_report|hybrid_report] [--intent new_draft|revise_existing]
report-workflow validate --job-id <job_id> [--verbose]       # --verbose prints per-node pass/fail
report-workflow render   --job-id <job_id>
report-workflow status   --job-id <job_id>
report-workflow run      --job-id <job_id> [--verbose]        # validate + render an already-prepared run
report-workflow diff     --job-id <a> --against <b>           # compare two checkpoints
report-workflow export   --job-id <id> [--checkpoint <name>] [--output <file>]   # dump checkpoint JSON
```

**Source role syntax**: `--source PATH:ROLE` tags a file as `source_data` (default) or `base_document`; `--source` is repeatable. The role suffix is only parsed when the trailing token exactly matches a valid role — bare Windows paths like `C:\path\to.txt` are safe.

**CLI exit codes**: `0` success · `1` crash · `2` hard-block failure · `3` waiting on agent artifacts (stderr lists missing paths).

## High-Level Architecture

### Three-stage orchestration with mandatory agent handoff

The workflow is split so the deterministic Python work and the agent's authoring work are strictly separate. [src/report_workflow/run_workflow.py](src/report_workflow/run_workflow.py) defines three node lists; when editing, **keep these in sync with this doc** — drift here breaks debugging.

1. **`prepare_nodes()`** (sync, runs from `prepare` CLI):
   `CONTRACT_SNAPSHOT → INTAKE → GUIDELINE_SELECT → BLUEPRINT_PLAN → CORPUS_BUILD → SOURCE_PARSE → BASE_DOCUMENT_PARSE → EVIDENCE_NORMALIZE → EVIDENCE_STORE → AGENT_TASKS`
   Ends in status `awaiting_agent_artifacts`. Writes task briefs to `~/.hermes/workflow_runs/<job_id>/agent_tasks/01_claim_plan.md`, `02_outline_plan.md`, `03_section_draft.md`.

2. **Agent authoring (external)** — agent reads the briefs and writes into `~/.hermes/workflow_runs/<job_id>/`:
   - `claim_matrix.json`
   - `outline.json`
   - `section_drafts/*.md` (one per blueprint section; must embed `[CITE:<evidence_id>]`)
   - `sentence_map.jsonl`

3. **`validate_nodes()`** (22 nodes — runs from `validate` CLI):
   `CLAIM_PLAN → OUTLINE_PLAN → CHART_RECOMMENDER → SECTION_PLAN_FREEZE → FRONT_MATTER_BUILD → SECTION_DRAFT → ABSTRACT_COMPRESS → ABSTRACT_SANITY_CHECK → METHODS_PROTOCOL_BUILD → FIGURE_BUILD → CAPTION_INTERPRETER → REVISION_APPLY → MERGE_DRAFT → RESULTS_SANITY_PASS → MAIN_TEXT_ARTIFACT_FILTER → CITATION_BIND → SECTION_ROLE_CHECK → FACTUALITY_CHECK → CONSISTENCY_CHECK → GUIDELINE_CHECK → FIGURE_CONTRACT_CHECK → QA_GATE`
   Ends in status `validated` with `state.qa.qa_decision` set. Any `QAHardBlockError` here triggers a remediation plan and a `FAILED` checkpoint.

4. **`render_nodes()`** (runs from `render` CLI, requires `qa_decision == "pass"`):
   `LANGUAGE_SANITY_PASS → PUBLICATION_STYLE_PASS → DOCX_RENDER → SOURCE_APPENDIX_RENDER → FINAL_PUBLISH → SUPPLEMENTARY_PACKAGE_BUILD → ARTIFACTS`

`run_workflow()` (convenience) runs prepare, then validate+render only if agent artifacts already exist; otherwise it raises `AgentWorkRequired`. `resume_workflow()` picks up from the last checkpoint: `awaiting_agent_artifacts` resumes at `validate_nodes() + render_nodes()`, `validated` resumes at `render_nodes()`, anything else resumes mid-list at `runtime["current_node"]`.

### State & persistence

`ReportState` ([src/report_workflow/state.py](src/report_workflow/state.py)) is the single source of truth — a pydantic model carrying `spec`, `plan`, `sources`, `drafts`, `citations`, `qa`, `output`, `runtime`. After every node, `state.checkpoint(node_name)` writes `checkpoint_<NODE>.json` and `checkpoint_latest.json` under `~/.hermes/workflow_runs/<job_id>/`. `ReportState.resume(job_id)` reloads from `checkpoint_latest.json`. Final packaged artifacts are copied to `~/.hermes/published/<job_id>/` by [nodes/artifacts.py](src/report_workflow/nodes/artifacts.py).

### Error contract

All control flow uses two exception types from [src/report_workflow/errors.py](src/report_workflow/errors.py):

- `AgentWorkRequired(missing_artifacts=[...])` — subclass of `QAHardBlockError`. Signals the workflow is paused; CLI exits 3 and prints the missing artifact paths.
- `QAHardBlockError` — a hard gate failure. `_run_nodes` catches it, writes a remediation plan via `nodes.remediation_router.write_remediation_plan`, appends a `FAILED` checkpoint, and re-raises.

### Agent skill entry points

The repo is also packaged as an agent skill. [agent_skill/skill.yaml](agent_skill/skill.yaml) declares two tools:

- `start_report_task` → `src/report_workflow/agent_wrapper.py:start_report_task` (wraps `prepare_workflow`)
- `submit_and_publish_report` → `agent_wrapper.py:submit_and_publish_report` (wraps `validate_workflow` + `render_workflow`)

[agent_skill/agent_instructions.md](agent_skill/agent_instructions.md) is the canonical agent-side procedure: call start, read the three task briefs, write the four artifacts, call submit.

## MVP Hard Rules (enforced by gates)

From [nodes/factuality_check.py](src/report_workflow/nodes/factuality_check.py), [nodes/qa_gate.py](src/report_workflow/nodes/qa_gate.py), and [nodes/intake.py](src/report_workflow/nodes/intake.py):

- Delivery mode is **only `fresh_doc`**. `tracked_review` / `preserve_format` hints in the prompt hard-fail at `INTAKE`.
- Every claim must have ≥1 `evidence_id` that exists in `evidence_ledger.jsonl`.
- Claim `status` ∈ {`blocked`, `unverified`, `disputed`} is non-publishable and blocks.
- `claim_type` must be in the evidence's `allowed_claim_types` (e.g. statistical claim requires quantitative evidence).
- Every evidence-backed sentence in section drafts must contain `[CITE:<evidence_id>]` matching `sentence_map.citation_ids` — missing placeholders hard-fail at `QA_GATE`.
- `citation_audit` entries with `resolved=False` hard-fail at `QA_GATE`.
- `DOCX_RENDER` refuses to run unless `qa_decision == "pass"` and refuses placeholder text `"This section is under development"`.

## Report Families & Blueprints

`state.spec.report_family` drives which YAML blueprint in [src/report_workflow/blueprints/](src/report_workflow/blueprints/) is loaded at `BLUEPRINT_PLAN`. Inference logic is in `nodes/intake.py:infer_report_family` (override with `--family`). Supported: `academic_report` (IMRAD), `work_report` (executive summary / findings / recommendations), `hybrid_report`. The blueprint's `section_order` is the authoritative list of required section IDs — `outline.json` and `section_drafts/` must cover every required section (references and appendix are optional in specific families).

## Debugging QA Gate Failures

When `report-workflow validate` fails at `QA_GATE` with "factuality blocked claims: N", use this checklist:

### Step 1: Read the fresh factuality report

```powershell
# ALWAYS delete the stale factuality report before inspecting
Remove-Item "$env:USERPROFILE\.hermes\workflow_runs\<job_id>\factuality_report.json" -Force
# Then re-run validate to get a FRESH report
report-workflow validate --job-id <job_id>
# Now read the new factuality_report.json
python -c "import json; print(json.load(open('...\\factuality_report.json',encoding='utf-8'))['claims'])"
```

**Why delete first**: `factuality_report.json` is written fresh on each run, but the `hard_fail_reasons` stored in `checkpoint_latest.json` reflect the LAST run's reasons — not the current state of your edits.

### Step 2: Identify the canonical source files

**The factuality checker reads from these files on disk — NOT from checkpoint files:**

| What | File | Notes |
|------|------|-------|
| Claim matrix | `~/.hermes/workflow_runs/<job_id>/claim_matrix.json` | **Canonical source** — loaded by `CLAIM_PLAN` node; `factuality_check` reads from this, NOT from checkpoint-embedded `claim_matrix` |
| Evidence content | `~/.hermes/workflow_runs/<job_id>/evidence_ledger.jsonl` | **Canonical source** — loaded via `state.sources["evidence_ledger_path"]` on every run |
| Checkpoint state | `~/.hermes/workflow_runs/<job_id>/checkpoint_*.json` | Checkpoint files embed a snapshot of claim_matrix but are NOT what the factuality checker reads |
| Factuality report | `~/.hermes/workflow_runs/<job_id>/factuality_report.json` | Written fresh each validate run; READ THIS to see current failures |

**Editing checkpoint files has NO EFFECT on factuality checks.** Edit `claim_matrix.json` and `evidence_ledger.jsonl` directly.

### Step 3: Understand factuality failure types

**3a. Term overlap failures** (e.g., "Claim key terms not in evidence (29% coverage): deterministic, compilation, ..."):
- The FE checker extracts key terms (≥5-letter words, excluding stopwords) from the claim text
- It requires ≥40% of those terms to appear as substrings in the evidence content
- Fix: Either (a) add more evidence content with those terms, or (b) rewrite the claim text to use terms that exist in your evidence

**3b. Numeric overlap failures** (e.g., "Claim number '226'edges not found in evidence content"):
- The numeric extractor requires the `"number + space + unit"` pattern (e.g., `226 edges`, NOT `226edges`)
- Example: `'226edges'` (no space) will NOT match — the evidence must contain `'226 edges'` (with a space)
- The regex pattern is `\d+ +[a-zA-Z]` (minimum 1 space between number and unit)
- Fix: Ensure evidence contains `"226 edges"` with a space, not `"226edges"`

**3c. Quote failures** (e.g., 'Quoted phrase "..." not found verbatim in evidence'):
- Claims with `"quoted text"` require that exact phrase to appear in evidence
- Fix: Remove the quote from the claim, or add the quoted phrase to the evidence content

### Step 4: Fix evidence, not just claim texts

- Augment `evidence_ledger.jsonl` directly (add new sentences to `content` field)
- After editing, delete `factuality_report.json` and re-run validate
- The `source_role` and `source_type` fields don't affect FE checks — only `content` matters

### Step 5: Verify before re-running

After editing `claim_matrix.json` or `evidence_ledger.jsonl`, verify:
1. The claim's `evidence_ids` list actually points to evidence that covers the claim's key terms
2. For numeric claims, the evidence contains `"<number> <unit>"` (with space) matching the claim
3. Evidence content is ASCII/Latin-readable (FE check skips term overlap for >30% non-ASCII text)

## Debugging ABSTRACT_SANITY_CHECK Failures

`ABSTRACT_SANITY_CHECK` runs after `ABSTRACT_COMPRESS` in `validate_nodes()`. It raises `QAHardBlockError` for any of these issues:

| Check | Failure message example | Root cause | Fix |
|-------|------------------------|------------|-----|
| Trailing ellipses | `Line 1: trailing ellipsis: '# Abstract This report presents...'` | Abstract ends mid-sentence with `that.....` dots | Agent must rewrite abstract with complete sentences |
| Incomplete sentence | `Missing ending punctuation: 'The results demonstrate that'` | No `.` `!` `?` at end of last sentence | Rewrite to end with proper punctuation |
| Incomplete comparative | `Incomplete comparative: 'more X than enforceable'` | Malformed `more X than Y` pattern | Rewrite the comparative phrase |
| Internal marker | `Internal marker残留: [CITE:E001]` | `[CITE:]`, `[Source:]`, `[graphify:]` left in abstract | `abstract_compress` strips these, but agent should avoid |
| Placeholder text | `Placeholder text found: This section is under development` | Abstract was not written | Agent must write a real abstract |
| Abstract too short | `Abstract too short: 23 words (minimum 150)` | Abstract has too few words OR compression destroyed content | See below |

### "Abstract too short" failure — the most common case

**Symptom**: `Abstract too short: N words (minimum 150)` where N is very small (e.g., 22 words).

**Root cause A — the abstract genuinely has <150 words of real content:**
The agent wrote a short abstract (e.g., 170 words) that ends mid-sentence with trailing dots (`that.....`). When `ABSTRACT_COMPRESS` tries to fit it within the 150-word limit, it can only take complete sentences from the beginning, leaving only a fragment.

**Fix**: The agent must write a new abstract that:
- Has 180–220 words
- Uses structured headings: **Background:** **Objective:** **Methods:** **Principal Findings:** **Significance:**
- Each section is a self-contained paragraph (15–30 words each)
- NO trailing dots, NO incomplete sentences, NO mid-thought truncation
- NO `[CITE:]`, `[Source:]`, or `[graphify:]` markers

**Root cause B — `_detect_abstract_structure` failed to split sections:**
If the abstract has `# Abstract` as a markdown heading but no `##` section headings, the entire text is treated as one sentence-less blob. The heading `# Abstract` itself has no period, so the sentence-splitting in `ABSTRACT_COMPRESS` treats it as part of the first "sentence", causing massive over-truncation.

**Fix**: Add `##`-level section headings in the abstract draft:
```markdown
# Abstract
**Background:** This report presents...
**Objective:** The study investigates...
**Methods:** Using graph-based analysis...
**Principal Findings:** Results demonstrate...
**Significance:** This work contributes...
```

**Root cause C — `_rebuild_abstract` outputs original text instead of compressed:**
A bug where `compressed_sections` was computed but the output loop used `active_sections` (original text) instead. This is fixed in the codebase, but if you see this on an older run, the compressed result was never actually used.

### Verifying abstract quality before running validate

Before calling `report-workflow validate`, manually check the abstract draft:

```powershell
# Count words (should be 180-220)
python -c "import re; t=open('section_drafts\\abstract.md',encoding='utf-8').read(); print(len(re.findall(r'\b\w+\b',t)), 'words')"

# Check for trailing dots / incomplete endings
python -c "t=open('section_drafts\\abstract.md',encoding='utf-8').read(); import re; \
  if re.search(r'\.{3,}$', t.rstrip()): print('FAIL: trailing dots at end'); \
  elif re.search(r'\b(that|which|because)\s*$', t, re.MULTILINE): print('FAIL: incomplete ending'); \
  else: print('PASS: no trailing ellipses')"

# Check section headings exist
python -c "t=open('section_drafts\\abstract.md',encoding='utf-8').read(); \
  import re; headings=re.findall(r'^##\s+\w+', t, re.MULTILINE); \
  print('Section headings found:', headings if headings else 'NONE - abstract needs ## headings')"
```

## Testing Notes

Tests live in [tests/test_mvp_workflow.py](tests/test_mvp_workflow.py) and patch `report_workflow.preflight.importlib.util.find_spec` to simulate installed packages. They use `tempfile.TemporaryDirectory` for outputs but still write run data under the real `~/.hermes/workflow_runs/<job_id>/`. When adding tests that touch workflow runs, use the `_prepare` + `_write_agent_artifacts` helpers to stage a realistic agent handoff before calling `validate_workflow`.

## Adding a new node

1. Create `src/report_workflow/nodes/<name>.py` exposing a `run_<name>(state: ReportState) -> ReportState` function. It must return the mutated state — never mutate and return `None`.
2. Import it at the top of [run_workflow.py](src/report_workflow/run_workflow.py) and insert `("<UPPER_NAME>", run_<name>)` into the correct tuple list (`prepare_nodes`, `validate_nodes`, or `render_nodes`). The string name is also the checkpoint filename suffix (`checkpoint_<NAME>.json`).
3. Raise `QAHardBlockError` from [errors.py](src/report_workflow/errors.py) for hard-fail conditions — this triggers the remediation-plan write and `FAILED` checkpoint. Any other exception bubbles up as a crash.
4. Update the node list in this file so the sequence stays authoritative.
