# AGENTS.md

Authoritative repository guide for agents developing `report-workflow`. This is
the single source of truth for the repo's development contract: concepts, layout,
commands, stage lists, artifact contract, hard gates, and extension points.

- Operating the skill to generate a report → `skills/report-workflow/SKILL.md` and its
  `reference/` files.
- Human-facing overview and install → `README.md`.
- `CLAUDE.md` and `AGENT_ONBOARDING.md` are thin entry points that defer here.

## Concepts

`report-workflow` is a deterministic source-to-report pipeline for evidence-backed
DOCX reports. The Python package does not call an LLM. It owns parsing, evidence
normalization, artifact contracts, validation gates, DOCX rendering, checkpoints,
and published package assembly. The external agent owns judgment, claim
selection, outlining, and drafting.

Three phases:

1. **Prepare** — parse sources, normalize evidence, select/freeze a report
   profile, load a blueprint, and write agent task briefs.
2. **Author** — the agent writes `claim_matrix.json`, `outline.json`, drafts
   (`structured_drafts.json` or `section_drafts/*.md`), and `sentence_map.jsonl`.
3. **Validate + Render** — the pipeline validates artifacts, resolves citations,
   checks factuality and profile contracts, renders DOCX, and packages outputs
   with QA artifacts under `published/qa/`.

## Project Layout

The installed package lives under `src/report_workflow/`; `pyproject.toml` uses
`package-dir = {"" = "src"}`. Keep edits inside `src/report_workflow/` unless the
task explicitly targets docs, tests, packaging, or skill metadata.

Key files:

- `src/report_workflow/profiles.py`: profile registry, aliases, inference, and
  reference-template mode selection.
- `src/report_workflow/blueprints/*.yaml`: profile-specific section structures.
- `src/report_workflow/policies/policy_pack.py`: profile policy objects used by
  validation gates.
- `src/report_workflow/nodes/intake.py`: intake, profile selection, and frozen
  `report_profile.json` creation.
- `src/report_workflow/nodes/blueprint_plan.py`: blueprint loading from the
  selected profile.
- `src/report_workflow/run_workflow.py`: canonical prepare/validate/render node
  lists.
- `src/report_workflow/agent_wrapper.py`: agent-skill entry points.
- `src/report_workflow/mcp_server.py`: MCP server (`report-workflow-mcp`,
  optional `[mcp]` extra) exposing `verify_claims`, `list_report_profiles`,
  and `get_workflow_status`; see `docs/mcp.md`.

## Commands

```powershell
pip install -r requirements.txt
pip install -e .

python -m compileall -q src tests
python -m unittest discover -s tests -v

report-workflow prepare --prompt "..." --source path\to\src.txt --output out\dir --profile engineering_lab_report
report-workflow prepare --prompt "..." --source data.csv:source_data --source base.docx:base_document --output out\dir --profile engineering_lab_report --intent revise_existing
report-workflow validate --job-id <job_id> [--verbose] [--dry-run] [--deep-audit]
report-workflow render --job-id <job_id>
report-workflow status --job-id <job_id>
report-workflow run --job-id <job_id> [--verbose]
report-workflow diff --job-id <a> --against <b>
report-workflow export --job-id <id> [--checkpoint <name>] [--output <file>]
report-workflow diagnose --job-id <id> [--verbose]
report-workflow invalidate-cache --job-id <id> [--sources] [--drafts]
```

`--source PATH:ROLE` may be repeated. Valid artifact roles are `source_data`
and `base_document`. The role suffix is parsed only when the trailing token is
one of those roles, so Windows paths such as `C:\path\to.txt` are safe. CLI
`prepare` requires the same explicit user preflight decision record as the
agent-skill entry point; a recorded `install`/`installed` choice does not
override a still-missing dependency.

CLI exit codes: `0` success, `1` crash, `2` hard-block failure, `3` waiting for
agent-authored artifacts.

## Public Contract

`report_profile` is the only public report-shape selector. Do not add or document
alternate public selectors, subtypes, or detail levels. Built-in profile IDs:

- `engineering_lab_report`
- `academic_paper`
- `business_report`
- `proposal`
- `admissions_report`
- `admissions_project_report`
- `custom`

Profiles control blueprint selection, policy strictness, aliases, front matter,
abstract rules, citation behavior, figure/table contracts, tone rules, and
reference-template behavior. The workflow DAG should remain stable; nodes read
profile policy through `get_policy(...)`. Profile descriptions for operators live
in `skills/report-workflow/reference/profiles.md`.

## Scope

The pipeline is feature-complete for what it set out to do. Seven profiles, two
languages, a user-supplied `.docx` template, revision of an existing document,
the CLI, the agent skill, and the MCP gate surface are the whole product. Work
from here is defect repair, not expansion.

Settled, and not to be reopened without the owner saying so in the current
session:

- No eighth profile, and no second public selector for report shape. See
  "Public Contract" above: `report_family`, family flags, detail levels,
  subtypes, and variants are all gone and stay gone.
- No semantic layer in the checker. The gates are lexical so the verdict is
  reproducible; entailment is what an NLI model or an LLM judge is for, and this
  project is the deterministic pass in front of one.
- No second rendering backend. pandoc, with `python-docx` as the degraded
  fallback.
- No venue or journal formatting. `--reference-docx` delegates layout to the
  user's own template.
- No web UI, hosted service, or anything requiring an account.
- No inflating a benchmark by deleting cases. The documented misses in the
  adversarial corpus mark the measured edge of lexical checking; they are the
  credibility, not a backlog.

A misleading message is a defect, not a cosmetic issue. Several releases exist
because the tool reported the wrong reason for stopping, and the wrong reason
costs a reader more than the stop does.

`CONTRIBUTING.md` states the same boundary for people arriving from outside.

## Stage Lists

`src/report_workflow/run_workflow.py` owns the canonical stage sequence. Each
stage contains deterministic substeps recorded in `job_events.jsonl` as
`STAGE/SUBSTEP`. Keep this section synchronized when changing stage lists.

Prepare:

```text
SPEC_PLAN -> SOURCE_INGEST -> EVIDENCE_BUILD -> FIGURE_RECOMMEND ->
NOTEBOOK_SYNC -> AGENT_TASKS
```

Validate:

```text
AGENT_ARTIFACTS -> PLAN_LOCK -> METADATA_GATE -> CONTENT_ASSEMBLY ->
DRAFT_GATES -> EVIDENCE_AND_CLAIMS -> FINAL_QA
```

Render:

```text
TEXT_POLISH -> DOCX_BUILD -> RENDER_QA -> REFERENCE_QA -> PUBLISH
```

`POST_RENDER_VALIDATE` writes `post_render_validate_report.json` and
`post_render_layout_manifest.json` (an audit artifact for rendered DOCX
structure: renderer used, file size, paragraph/table/figure counts, heading
summary, table previews, front-matter preview, related render QA reports, and
issues). `ARTIFACTS` packages QA files under `published/qa/`, including
`final_qa_summary.json`/`.md` (the delivery-level QA entry point combining QA
gate, factuality, artifact lint, engineering audit, chart visual-quality review,
and scholarly-quality review, and render-layout evidence),
`template_style_map.json`/`.md` (reference-DOCX mode, renderer, applied-reference
status, key styles, rendered style usage, template-fidelity warnings), and
`template_field_fill_report.json`/`.md` (which structured fields were rendered
into the final DOCX). These summaries do not add new hard gates.

## State and Persistence

`ReportState` is the source of truth. It carries `spec`, `plan`, `sources`,
`drafts`, `citations`, `qa`, `output`, `runtime`, `flags`, `knowledge_sync`, and
`research`. Each stage writes `checkpoint_<STAGE>.json` and
`checkpoint_latest.json` under `output/<slug>--<job_id>/`.

## Blueprints and Policies

`BLUEPRINT_PLAN` loads the YAML file declared by the frozen profile contract.
`section_order` is authoritative for required `outline.json` and
`section_drafts/*.md` coverage. Use profile policy instead of string-branching:

```python
from ..policies import get_policy

policy = get_policy(state.spec.get("report_profile", "academic_paper"))
```

## Agent Artifact Contract

Prepare writes task briefs under `output/<slug>--<job_id>/agent_tasks/`. The agent
writes into the run directory:

- `claim_matrix.json`
- `outline.json`
- `structured_drafts.json` as an optional low-drift input for new drafts
- `section_drafts/*.md`
- `sentence_map.jsonl`
- `revision_plan.json` for `task_intent=revise_existing`

Every evidence-backed sentence in section drafts must include
`[CITE:<evidence_id>]`, and those IDs must match `sentence_map.jsonl`. When
`structured_drafts.json` is supplied and canonical draft artifacts are missing,
`SECTION_DRAFT` compiles it into Markdown section drafts and `sentence_map.jsonl`.

Read-only helpers: `query_evidence` for ledger lookup instead of loading huge
ledgers into context; `lint_artifacts` to write `artifact_lint_report.json`
(artifact names, JSON paths, severity, messages, repair hints) before the full
validate/render path; `audit_engineering_report` (for `engineering_lab_report`) to
write `engineering_audit_report.json` with measurement extraction, unit-support
warnings, table-value support checks, and simple calculation checks.

For `academic_paper` and `engineering_lab_report`, validation writes
`scholarly_quality_report.json`/`.md` with review-grade checks for article spine,
introduction flow, methods reproducibility, role separation, figure/table
scholarly expectations, and reference metadata quality. When summarizing delivery
readiness, inspect `published/qa/final_qa_summary.json` first, then the
scholarly-quality, figure-visual-quality, template-style-map, and
template-field-fill reports as the user's question requires. Operator-facing
inspection order and the engineering publish checklist live in
`skills/report-workflow/reference/engineering-lab.md`.

## Revision Mode

For `task_intent=revise_existing`, `BASE_DOCUMENT_PARSE` extracts sections from the
single `base_document` source into `base_document_sections.json`.
`REVISION_APPLY` reads that file plus `revision_plan.json` and writes the merged
draft. `section_drafts/*.md` are not merged into the final document in this mode.

Do not edit `base_document_sections.json`, generated draft files, or checkpoint
JSON directly as an authoring shortcut. If disk artifacts are intentionally
changed during debugging, invalidate the affected checkpoint cache before
validating:

```powershell
report-workflow invalidate-cache --job-id <id> --sources --drafts
```

## Hard Gates

- Delivery mode is `fresh_doc`.
- Every publishable claim must cite existing evidence.
- Claim statuses `blocked`, `unverified`, and `disputed` are non-publishable.
- Claim type must be allowed by the cited evidence.
- Evidence-backed sentences must include matching `[CITE:<evidence_id>]`
  placeholders.
- Unresolved citation audit entries hard-fail.
- Placeholder prose, fake metadata, internal paths, and workflow artifacts must
  not leak into publication text.
- `DOCX_RENDER` requires `qa_decision=pass`.

## Debugging Guidance

For factuality failures, inspect the fresh `factuality_report.json` from the run
directory. The factuality checker reads canonical disk artifacts (`claim_matrix.json`,
`evidence_ledger.jsonl`, `sentence_map.jsonl`); editing checkpoint snapshots does
not affect factuality checks. For artifact-shape failures, run
`lint_artifacts` first and inspect `artifact_lint_report.json`. For
engineering unit or calculation questions, inspect
`engineering_audit_report.json` before changing claim text or calculation prose.
For abstract failures, fix the authored abstract draft; common blockers are
trailing ellipses, incomplete final sentences, leftover `[CITE:]` or `[Source:]`
markers, placeholder text, and profile-specific word-count violations.

## Adding A Substep

1. Add `src/report_workflow/nodes/<name>.py` with `run_<name>(state:
   ReportState) -> ReportState`.
2. Import it in `src/report_workflow/run_workflow.py`.
3. Insert it as a `WorkflowStep` inside the appropriate `prepare_stages()`,
   `validate_stages()`, or `render_stages()` stage.
4. Raise `QAHardBlockError` for hard gates so remediation and failed checkpoints
   are written.
5. Update the Stage Lists section above if the canonical stage sequence changes.

## Git Hygiene

This repo may start dirty. Do not revert changes you did not make. Before
committing, verify that the diff boundary is clean and that unrelated dirty files
or generated output are not included.

## Verification

Before claiming a change is complete, run:

```powershell
python -m compileall -q src tests
python -m unittest discover -s tests -v
```

If a change touches profile behavior or skill docs, also run the documentation
contract tests:

```powershell
python -m unittest tests.test_roadmap_contracts.DocumentationContractTests -v
python scripts/render_skill_docs.py --check
```

If a change touches the factuality gates (`nodes/factuality_check.py`), also
re-verify the archived benchmark evidence (CI runs both):

```powershell
python scripts/run_report_benchmarks.py --check
python scripts/run_adversarial_benchmark.py --check
```

If gate behavior changed intentionally, regenerate the adversarial archive
(`python scripts/run_adversarial_benchmark.py`) and review the diff — corpus
expectations are assertions, so unexplained verdict drift is a regression.

A change that touches what reaches the deliverable — citation binding, source
tables, figure placement, the blueprints — also moves the report-quality
benchmark, which compares a live pipeline run against a recorded unassisted
write-up of the same source:

```powershell
python scripts/run_report_quality_benchmark.py --check
```

Two rules for that one. Do not edit
`benchmarks/fixtures/unassisted_baseline.md` to widen a gap — it is a recorded
artifact, and adjusting it is how a benchmark stops meaning anything. Do not
delete a dimension the harness loses; the archive records two losses on
purpose, and one of them is a fact about the metric rather than about the
pipeline.
