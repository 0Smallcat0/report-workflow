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

When a reference DOCX is supplied:

- User-specified template mode wins.
- Otherwise default to `style_reference`.
- If the prompt asks to exactly match the format or cover, use `fixed_template`.
- The profile contract remains higher priority than prompt or template details.

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
  --profile engineering_lab_report

report-workflow validate --job-id <job_id>
report-workflow render --job-id <job_id>
```

Do not reintroduce `--family`, `--detail`, `report_family`, or profile subtype
state. This is a breaking-change migration.

## Agent Artifacts

Prepare writes task briefs under:

```text
output/<slug>--<job_id>/agent_tasks/
```

The agent must produce:

- `claim_matrix.json`
- `outline.json`
- `section_drafts/*.md`
- `sentence_map.jsonl`

Every evidence-backed claim must cite evidence from `evidence_ledger.jsonl`.
Draft sentences that use evidence must include `[CITE:<evidence_id>]`.

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

If a change touches profile behavior, also search for stale public names:

```powershell
rg "report_family|--family|report_profile_detail|--detail|academic_report|work_report|hybrid_report" README.md AGENT_ONBOARDING.md agent_skill src tests
```
