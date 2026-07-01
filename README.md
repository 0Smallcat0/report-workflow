# Report Workflow

Report Workflow is a deterministic source-to-report pipeline for evidence-backed
DOCX reports. It is designed to run inside an agent environment such as Codex,
Claude Code, or Hermes.

The Python package does not call an LLM provider and does not require an API key.
It owns source parsing, evidence normalization, artifact contracts, validation
gates, DOCX rendering, and traceability packaging. The external agent owns
judgment and drafting by reading task briefs and producing required artifacts.

- **Operating the skill to generate a report** → `agent_skill/SKILL.md` and its
  `reference/` files.
- **Developing this repository** → [AGENTS.md](AGENTS.md) (authoritative
  contract: layout, stage lists, artifact contract, hard gates, extension points).

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
  --profile engineering_lab_report `
  --preflight-decisions C:\path\to\preflight_decisions.json `
  --template-field course_name="Control Systems"

report-workflow validate --job-id <job_id>
report-workflow render --job-id <job_id>
report-workflow status --job-id <job_id>
report-workflow run --job-id <job_id>
```

`prepare` requires a `--preflight-decisions` JSON record confirming the user's
install, degraded-render, and optional-feature decisions. Required dependencies
must actually pass preflight before start; a decision string alone does not
override a still-missing dependency. This mirrors the agent-skill
`preflight_decisions` contract instead of silently starting from the raw CLI.

`--source PATH:ROLE` may be repeated. Valid roles are `source_data` and
`base_document`. The role suffix is parsed only when the trailing token exactly
matches a valid role, so Windows paths such as `C:\path\to.txt` are safe.

CLI exit codes:

- `0`: success
- `1`: crash
- `2`: hard-block validation failure
- `3`: waiting for user decisions or agent-authored artifacts

## Report Profiles

`report_profile` is the only public report-shape selector. Built-in profiles:
`engineering_lab_report`, `academic_paper`, `business_report`, `proposal`,
`admissions_report`, `admissions_project_report`, and `custom`. The pipeline
infers a profile from the prompt unless `--profile` or `report_profile` is given.

Profile purposes and strictness are documented in
`agent_skill/reference/profiles.md`; the registry lives in
`src/report_workflow/profiles.py`.

## Workflow

1. **Prepare** parses sources and writes deterministic artifacts (`report_spec.json`,
   `report_profile.json`, `blueprint.json`, `source_registry.json`,
   `evidence_ledger.jsonl`, and `agent_tasks/*.md`).
2. **Author** — the external agent writes `claim_matrix.json`, `outline.json`,
   `section_drafts/*.md` (or `structured_drafts.json`), and `sentence_map.jsonl`.
3. **Validate and render** checks artifact completeness, section contracts,
   citation linkage, factuality, profile policy, figure contracts, and QA gates,
   then renders. `render` runs only after the validated checkpoint records
   `qa_decision=pass`, a passing `qa_summary.json`, a clean
   `factuality_report.json`, and no unresolved citation audit entries.

Final artifacts are packaged under `output/<slug>--<job_id>/published/`, with
delivery QA in `published/qa/` (`final_qa_summary.json`/`.md`, plus scholarly,
figure-visual, template-style-map, and template-field-fill reports where they
apply). See [AGENTS.md](AGENTS.md) for the canonical stage lists and the full QA
artifact contract.

## Reference Templates

Profiles control reference-template behavior. The default mode is
`style_reference` (use a DOCX as a style/layout reference); if the user asks to
exactly preserve the cover or format, the workflow upgrades to `fixed_template`.
A profile contract has priority over prompt and template hints. Engineering
exact-cover handling is detailed in
`agent_skill/reference/engineering-lab.md`.

## Quality Gates

Core hard gates: sources must register and parse; the evidence ledger must be
non-empty; claims must cite valid evidence IDs; claim status cannot be `blocked`,
`unverified`, or `disputed`; evidence-backed sentences must contain matching
`[CITE:<id>]` placeholders; citation audits must resolve; placeholder prose and
fake metadata are blocked; and render requires `qa_decision=pass`. Profile
policies adjust strictness for front matter, abstract structure, citation style,
reference verification, and figure/table contracts. The authoritative gate list
lives in [AGENTS.md](AGENTS.md).

## Benchmarks

Use `benchmarks/` when improving report quality across profiles. Run
`python scripts/run_report_benchmarks.py` for the seven-profile
prepare-author-validate-render benchmark, or
`python scripts/run_report_benchmarks.py --check` to validate archived evidence
without rerunning. The benchmark-first optimization method and gap taxonomy are
documented in `agent_skill/reference/benchmarking.md`.

## Tests

```powershell
python -m compileall -q src tests
python -m unittest discover -s tests -v
```
