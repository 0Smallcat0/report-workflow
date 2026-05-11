# Agent Onboarding: Report Workflow

This is the conceptual entry point for agents using or modifying
`report-workflow`. For the full agent-tool execution contract, see
`agent_skill/agent_instructions.md`.

## What This Workflow Is

Report Workflow is a deterministic source-to-report pipeline. Given source files,
it produces a structured, evidence-linked, DOCX-ready report package.

The package does not call an LLM. The pipeline owns parsing, evidence
normalization, validation gates, rendering, checkpoints, and artifacts. The
external agent owns judgment, claim planning, outlining, and drafting.

## Core Model

The workflow has three phases:

1. **Prepare**: parse sources, normalize evidence, select/freeze a report profile,
   load a blueprint, and write agent task briefs.
2. **Author**: the agent writes `claim_matrix.json`, `outline.json`,
   `section_drafts/*.md`, and `sentence_map.jsonl`.
3. **Validate + Render**: the pipeline validates artifacts, resolves citations,
   checks factuality and profile contracts, renders DOCX, and packages outputs.
   Render validation writes `post_render_layout_manifest.json`, which records
   renderer choice, file size, paragraph/table/figure counts, headings, table
   previews, front-matter preview, related render QA reports, and issues.
   Publish packaging writes `final_qa_summary.json` and
   `final_qa_summary.md`, which consolidate QA gate, factuality, artifact lint,
   engineering audit, scholarly-quality review, chart visual-quality review, and
   render-layout evidence for delivery review.
   It also writes `template_style_map.json` and `template_style_map.md`, which
   explain renderer choice, reference DOCX application, key style definitions,
   rendered style usage, and template-fidelity warnings.
   Fixed-template metadata is audited through
   `template_field_fill_report.json` and `template_field_fill_report.md`.

The workflow intentionally separates deterministic validation from agent writing.

## Report Profiles

`report_profile` is the public report-shape contract. It replaces the old
family/detail/subtype model.

Built-in profiles:

| Profile | Purpose | Default Strictness |
| --- | --- | --- |
| `engineering_lab_report` | Engineering experiment reports, including Chinese engineering report rules | High |
| `academic_paper` | IMRaD academic papers, journal/thesis-style reports | High |
| `business_report` | Work/business reports | Medium |
| `proposal` | Project or business proposals | Medium |
| `admissions_report` | Admissions-facing scholarly reports | High |
| `admissions_project_report` | Admissions-facing project reports with relaxed publication metadata | Medium |
| `custom` | User-defined or mixed structures | Medium |

Profiles control sections, word-count expectations, front matter, citation style,
required figures/tables, tone, section contracts, and render QA. The DAG remains
stable; nodes derive behavior from profile policy.

## Engineering Lab Reports

`engineering_lab_report` is the first-class engineering profile. It includes:

- SOP/handout/lab-instruction parsing.
- Requirement matrix support.
- Formula, parameter, symbol, and unit audit expectations.
- Calculation audit expectations.
- Figure/table contracts.
- Chinese document rules for headings, symbols, units, and mojibake avoidance.
- Render QA for table compression, images, cover/template drift, and page layout.
- Published QA artifacts include a post-render layout manifest when rendering
  reaches `POST_RENDER_VALIDATE`.
- Validation writes `scholarly_quality_report.json` and
  `scholarly_quality_report.md` for review-grade checks of lab spine,
  reproducible method/procedure cues, figure/table scholarly expectations, and
  article-style language.
- Completed packages include `published/qa/final_qa_summary.json` and
  `published/qa/final_qa_summary.md` as the first QA files to inspect before
  reporting delivery readiness.
- Completed packages include `published/qa/template_style_map.json` and
  `published/qa/template_style_map.md` when users need to understand template
  and reference-DOCX style behavior.
- Completed packages include `published/qa/template_field_fill_report.json`
  and `published/qa/template_field_fill_report.md` when users need to verify
  cover or fixed-template field filling.

When a reference DOCX is supplied:

- User-specified template mode wins.
- Otherwise default to `style_reference`.
- If the prompt asks to exactly match the format or cover, use `fixed_template`.
- The profile contract remains higher priority than prompt or template details.
- Pass `template_fields` for fixed-template fields such as `course_name`,
  `student_id`, `instructor`, `lab_section`, `date`, or `department`.

## Key Files

- `src/report_workflow/profiles.py`: profile registry, aliases, inference, and
  reference-template mode selection.
- `src/report_workflow/blueprints/*.yaml`: profile-specific section structures.
- `src/report_workflow/policies/policy_pack.py`: profile policy objects used by
  validation gates.
- `src/report_workflow/nodes/intake.py`: intake, profile selection, and frozen
  `report_profile.json` creation.
- `src/report_workflow/nodes/blueprint_plan.py`: blueprint loading from the
  selected profile.
- `src/report_workflow/run_workflow.py`: prepare, validate, render node lists.
- `src/report_workflow/agent_wrapper.py`: agent-skill entry points.

## CLI

```powershell
report-workflow prepare `
  --prompt "write a lab report" `
  --source C:\path\to\source.txt `
  --output C:\path\to\out `
  --profile engineering_lab_report `
  --preflight-decisions C:\path\to\preflight_decisions.json

report-workflow validate --job-id <job_id>
report-workflow render --job-id <job_id>
```

Do not reintroduce `--family`, `--detail`, `report_family`, or profile subtype
state. This is a breaking-change migration.
CLI prepare requires the same explicit user preflight decision record as the
agent-skill entry point. Required dependencies must pass preflight in fact; a
recorded `install` or `installed` choice does not override a still-missing
dependency.

## Agent Artifacts

Prepare writes task briefs under:

```text
output/<slug>--<job_id>/agent_tasks/
```

The agent must produce:

- `claim_matrix.json`
- `outline.json`
- either `structured_drafts.json` or canonical `section_drafts/*.md` plus
  `sentence_map.jsonl`

Every evidence-backed claim must cite evidence from `evidence_ledger.jsonl`.
Draft sentences that use evidence must include `[CITE:<evidence_id>]`. When the
agent uses `structured_drafts.json`, the pipeline inserts citation markers and
writes `sentence_map.jsonl`.
Run `lint_agent_artifacts` after writing or editing these files to produce
`artifact_lint_report.json` with JSON paths and repair hints before full
validation.
For `engineering_lab_report`, run `run_engineering_audit` after drafts exist to
produce `engineering_audit_report.json` with extracted measurements,
claim/evidence unit-support checks, table-value support checks, unit notation
notes, missing-unit notes, and simple calculation checks.

## Validation Rules

Universal hard gates:

- Delivery mode is `fresh_doc`.
- Claims must cite existing evidence IDs.
- Non-publishable claim statuses block publication.
- Claim types must be allowed by their evidence.
- Sentence-map and citation placeholders must match.
- Unresolved citations hard-fail.
- Placeholder prose and fake metadata hard-fail.

Profile-specific gates may add stricter front matter, abstract, section-role,
reference, figure/table, or tone requirements.
For early format checks, `artifact_lint_report.json` centralizes missing files,
malformed JSON/JSONL, unknown section/claim/evidence IDs, and citation marker
drift.
For engineering reports, `engineering_audit_report.json` is the first place to
inspect unit and calculation traceability before editing final prose.

## Revision Mode

For `task_intent=revise_existing`, the pipeline reads
`base_document_sections.json` and `revision_plan.json`. Section drafts are not
merged into the final document in this mode.

If manually editing cached run artifacts, invalidate affected caches before
validating:

```powershell
report-workflow invalidate-cache --job-id <id> --sources --drafts
```

## Verification

Before claiming a change is complete, run:

```powershell
python -m compileall -q src tests
python -m unittest discover -s tests -v
```

If a change touches profile behavior, also run the documentation contract
tests that guard removed public selector examples:

```powershell
python -m unittest tests.test_roadmap_contracts.DocumentationContractTests -v
```
