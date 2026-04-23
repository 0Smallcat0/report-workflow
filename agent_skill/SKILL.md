---
name: report-workflow
description: Use when Codex needs to generate, revise, validate, or publish evidence-backed DOCX reports with the local report_workflow pipeline, especially academic/admissions reports that must preserve project identity, front matter truth, citation traceability, figure consistency, and scholarly tone. Supports optional external research (Tavily/Serper/SerpAPI) and NotebookLM integration.
---

# Report Workflow

Use this skill to operate the local deterministic prepare -> agent author -> validate -> render report pipeline. Keep `AGENT_ONBOARDING.md` as the long conceptual reference; this file is the execution contract.

## Prerequisites

Before first use, ensure the host system has these dependencies installed.
The pipeline checks for them at startup and will warn about missing tools.

### Core Dependencies (Required)

| Dependency | Required? | Install Command | Purpose |
|------------|-----------|-----------------|---------|
| Python 3.11+ | **Required** | — | Runtime |
| `pip install -e .` | **Required** | `pip install -e .` in repo root | Install the package and Python dependencies |
| **pandoc 3.x** | **Critical** | `winget install JohnMacFarlane.Pandoc` (Win) / `apt install pandoc` (Linux) / `brew install pandoc` (Mac) | High-quality DOCX rendering with TOC, tables, and academic styling. Without it, the pipeline silently falls back to a limited python-docx converter with degraded output. |
| **mmdc** (mermaid-cli) | Optional | `npm install -g @mermaid-js/mermaid-cli` | Converts `mermaid` code fences to PNG diagrams. Without it, diagrams remain as code blocks. |

### Optional Integration Dependencies

These are only needed if you enable the corresponding features. The pipeline **never** hard-blocks on these — it gracefully skips features when dependencies are missing.

| Dependency | Feature Flag | Install / Configure | Purpose |
|------------|-------------|---------------------|---------|
| **notebooklm-py** | `enable_notebook_sync=True` | `pip install notebooklm-py` + authenticate via browser | Sync knowledge from Google NotebookLM notebooks (source context, analysis Q&A) |
| **Tavily API key** | `enable_research=True` | Set env var `TAVILY_API_KEY` | Automated web research for external claim verification (recommended) |
| **Serper API key** | `enable_research=True` | Set env var `SERPER_API_KEY` | Alternative Google search backend for claim verification |
| **SerpAPI key** | `enable_research=True` | Set env var `SERPAPI_API_KEY` | Alternative Google search backend for claim verification |
| **Browser MCP** | `enable_research=True` | Set env var `BROWSER_MCP_SEARCH_COMMAND` | Shell-based browser search for claim verification |

> **How it works**: When `enable_research=True`, the pipeline auto-selects the best available backend in priority order: Tavily → Serper → SerpAPI → BrowserMCP → ManualAgent (no-op fallback). If no API key is configured, research tasks are marked as "pending" for manual follow-up — the workflow still completes.

> **Note**: The pipeline runs a preflight check when you call `start_report_task`. Missing Python packages will **hard-block**. Missing pandoc/mmdc will produce **warnings** in the return value — look for the `warnings` field.

### Configuration Files

| File | Purpose | Tracked in Git? |
|------|---------|-----------------|
| `.env.example` | Template — copy to `.env` and fill in API keys | ✅ Yes |
| `.env` | Your actual API keys (auto-loaded on every run) | ❌ No (gitignored) |
| `workflow_config.yaml` | Persistent feature flags (enable_research, enable_notebook_sync) | ✅ Yes |

### Feature Discovery (Critical)

**On first use, call `check_setup()` BEFORE `start_report_task`.** This returns:
- Environment status (missing packages, tools)
- `agent_should_ask_user` — features the user should be asked about
- Exact install commands for any missing dependencies

**Do NOT silently skip available features.** If `agent_should_ask_user` is non-empty,
present each option to the user and let them decide before starting the workflow.



## Start

0. **First use only**: Call `check_setup()` — read the `agent_should_ask_user` list, ask the user about each feature, then proceed.
1. Call `start_report_task` once with `prompt`, `source_files`, `output_dir`, and `report_family`.
   Pass `enable_research=True` and/or `enable_notebook_sync=True` if the user confirmed.
2. For academic/admissions reports, pass structured front matter whenever known: `title`, `author_block`, `affiliation_block`, `correspondence`, `keywords`.
3. Pass `project_identity` when the report must preserve a known project. Use this shape:

```json
{
  "required_terms": ["deterministic compilation", "StrategyIR", "AST", "Taiwan equities"],
  "required_context_terms": ["compiler architecture", "domain-specific intermediate representation"],
  "forbidden_terms": ["U.S. equity markets", "StrategySpec JSON", "Research Author", "Research University", "research@university.edu"],
  "canonical_title_terms": ["deterministic", "compilation", "StrategyIR", "compiler"],
  "domain_context": "Taiwan equities",
  "author_metadata": {
    "author_block": "Example Student",
    "affiliation_block": "Department of Engineering, Example University",
    "correspondence": "student@example.edu"
  }
}
```

4. To enable **external research** for claim verification, add `enable_research=True`.
5. To enable **NotebookLM** integration, add `enable_notebook_sync=True` (and optionally `notebooklm_notebook_id`).

## Authoring Flow

Use the incremental path by default.

1. Read `agent_tasks/01_claim_plan.md`, write `claim_matrix.json`, then call `submit_claim_matrix`.
2. Read `agent_tasks/02_outline_plan.md`, write `outline.json`, then call `submit_outline`.
3. Read `agent_tasks/03_section_draft.md`, write `section_drafts/*.md` and `sentence_map.jsonl`, then call `submit_drafts`.
4. Call `submit_and_publish_report` only after the step-level validations pass.

Avoid legacy all-at-once submission unless the source set is small and the artifact contracts are already clear.

If you reuse artifacts from another job, do not manually copy old evidence IDs.
Call `remap_agent_artifacts(job_id="<current>", previous_job_id="<old>", write=false)`
to inspect the mapping, then call it with `write=true` if the mapping is complete.

## Optional Features (Post-Integration)

### External Research (`enable_research=True`)

When enabled, the pipeline runs **RESEARCH_EXECUTE** and **CLAIM_VERIFY_EXECUTE** after `FACTUALITY_CHECK`:
- Blocked/disputed/unverified claims are automatically researched via configured backends
- Research results are cross-referenced with claims and their status can be upgraded to "externally_verified"
- Results are saved to `research_results.json` and `claim_verification_results.json` in the run directory
- **Requires**: At least one API key (`TAVILY_API_KEY`, `SERPER_API_KEY`, or `SERPAPI_API_KEY`). Without keys, tasks fall back to the ManualAgent (no-op) backend.

### NotebookLM Sync (`enable_notebook_sync=True`)

When enabled, the pipeline runs **NOTEBOOK_SYNC** after `EVIDENCE_STORE`:
- Connects to Google NotebookLM and selects a notebook matching your report topic
- Asks analysis questions about missing constants, factual inconsistencies, and improvement opportunities
- Results are added to `state.knowledge_sync.buffer` for downstream use
- **Requires**: `pip install notebooklm-py` and authenticated browser session

### Chinese Engineering Reports

The pipeline includes built-in support for Chinese engineering lab reports via `guidelines/CHINESE_ENGINEERING.json`:
- Required sections: 實驗簡介, 實驗結果, 問題與討論, 心得與建議, 參考文獻
- Typography rules: 標楷體 (DFKai-SB) for Chinese, Times New Roman for Latin
- Tone gates: forbidden jargon, subjective term warnings, first-person policy
- Parser enrichment: automatic formula, constant, and question detection for CJK-heavy documents

## Intent Rules

For `new_draft`:
- Freeze the project identity before claim planning.
- Keep deterministic compilation, StrategyIR, AST/compiler architecture, and the declared market/domain context as the thesis spine.
- Treat LLM generation, debate gates, Bayesian/HMM/HRP/DRL modules as supporting modules unless the prompt explicitly makes them the core contribution.
- Do not turn a project report into a topic-adjacent framework paper.

For `revise_existing`:
- Preserve the base document thesis, heading structure, front matter, and mature narrative.
- Use `revision_plan.json`; do not rewrite the whole document from scratch.
- Call `submit_revision_plan` before publish and inspect the diff preview when edits touch front matter, figures, or section transitions.

## Delivery Gates

Do not deliver solely because `qa_decision=pass`. Before final response, verify:

- Identity: title, thesis, abstract, introduction, and conclusion still describe the same project.
- Metadata: no fake/template author, affiliation, email, or leftover Markdown markers.
- Figures: every `Figure N` mention has a caption and rendered object, or the reference is removed.
- References: keep only publication-grade references that carry the project thesis or claim topics.
- Tone: admissions-facing but scholarly; do not address the admissions committee directly.

If any delivery gate fails, fix the agent artifacts and rerun validation/render.
Only treat a run as delivered when the workflow returns `status=completed` and
`workflow_success=true`. A rendered DOCX that fails a later gate is not a final
deliverable and must not be copied manually to the output directory.

## Hard Prohibitions

- Do not fabricate `Research Author`, `Research University`, or template email metadata.
- Do not publish front matter with `**` or bracket placeholders.
- Do not introduce forbidden project-drift terms from `project_identity`.
- Do not use claim, outline, or sentence-map artifacts from another run without remapping evidence IDs.
- Do not edit `.hermes` checkpoint files, `base_document_sections.json`, or evidence ledgers by hand to make gates pass.
- Do not create temporary repair scripts in the repository root; place scratch scripts under the run directory or system temp and remove them.
- Do not cite internal workflow files, evidence ledgers, claim matrices, or traceability appendices in the main report.
- Do not leave generic bibliography padding in an admissions project report.
