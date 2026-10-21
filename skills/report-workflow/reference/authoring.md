# Authoring Reference

Detailed authoring guidance for `report-workflow`. The short controlled loop is
in `SKILL.md`; load this file for artifact shapes, evidence rules, source-role
boundaries, controlled-submission failure handling, and validation repair.

## Contents

- [Source Roles](#source-roles)
- [Authoring Artifacts](#authoring-artifacts)
- [Structured Drafts (Preferred New-Draft Path)](#structured-drafts-preferred-new-draft-path)
- [Evidence and Citation Rules](#evidence-and-citation-rules)
- [Draft Rules](#draft-rules)
- [Controlled Submission Details](#controlled-submission-details)
- [Reusing a Previous Run](#reusing-a-previous-run)
- [Validation Failure Repair](#validation-failure-repair)

## Source Roles

Valid `source_files` roles are `source_data` and `base_document`. Legacy string
paths are accepted for new drafts.

- Only `source_data` may support measured values, calculated results, experiment
  conditions, comparison groups, charts, or tables.
- When a scanned PDF or reference image must be manually transcribed, save the
  transcription as Markdown or text and pass it with `role: "source_data"`. The
  workflow treats `source_data` `.md` and `.txt` files as accepted internal
  project sources, even when named `source_notes.md`. Never use generated
  workflow artifacts as source evidence.
- If the user marks files as "reference only", do not pass them as `source_data`,
  do not let their measurements enter the evidence ledger, and do not cite or list
  them in the delivered report unless the user changes their role.
- When external references are needed for theory, standards, or reference data,
  keep them separate from experiment measurements. Cite the external source, use
  it only for the specific theory/property claim, and never use it to invent
  missing measured values or extra trial groups.

### Declaring what a source is a copy of

A source file is not a publication, so by default a `.md`, `.txt` or `.csv`
source is the report's own material: a sentence restating it carries no label in
the text, and nothing is guessed from its file name. Which row or paragraph
backs each sentence is in `published/traceability/client_readable_qa_note.md`.
A figure the pipeline computed is labelled `本研究計算` /
`calculated in this study` and points at an entry of the calculation record, a
document published beside the report (`published/calculation_record.docx`) that
gives the result, the formula and every input with its unit, the row it was read
from and its source — for a formula table, each row's value of a per-row input.
A figure the report places as a table is pointed at by its table number
(`本研究計算，表 5`). A figure computed from a declared publication names both:
`（Knobloch et al., 2020；本研究計算，表 4）`.

The record is complete rather than readable: it spells out every input of every
figure, program names included. When the report explains its calculations in an
appendix of its own, write that appendix for a reader — the formulas with their
symbols, a table of the parameters used only there, one complete worked example,
and for every other scenario only the parameters it changes and where its
results are shown — and give each derivation the section that explains it with
`"explained_in": "附錄 A.3"`. Sentences citing that figure, and the attribution of
a table computed by it, then point there instead of at the record. A section
with the `appendix` id is not numbered, and the references are placed before a
heading that starts with 附錄 or Appendix.

When the file is a transcription or excerpt of something published — a report,
a paper, a government announcement, a dataset — declare it, and the source is
cited author-year and listed in the references:

```json
{"path": "icct_2025_excerpt.md", "role": "source_data",
 "citation": {"author": "Negri, M., & Bieker, G.", "year": "2025",
              "title": "Life-cycle greenhouse gas emissions from passenger cars in the European Union",
              "publisher": "International Council on Clean Transportation",
              "url": "https://theicct.org/..."}}
```

- In-text citations are derived from `author`: one surname, two joined with `&`,
  three or more as `et al.`; a Chinese author gets full-width punctuation
  (`（經濟部能源署，2026）`). When the author cannot be split into surnames —
  `Tesla, Inc.` — the run refuses to start and asks for `in_text`.
- Articles take `container` (the journal), `volume`, `issue`, `pages` and `doi`;
  reports and web pages take `publisher` and `url`; `description` adds a bracketed
  label such as `Data set` or `Press release`. `reference` is used verbatim when
  the exact entry is already known.
- A missing `year` prints as `n.d.` (`無日期`); no field is ever filled in for you.
- The CLI takes the same objects from a JSON file: `--source-manifest sources.json`
  (relative paths resolve against the manifest's folder).

A long publication does not have to enter the ledger whole. Name the span the
report uses — `"pages": "80-86, 90"` for a PDF, `"lines": "5504-5526"` for a text
file — and only blocks inside it are read, keeping their real page and line
numbers; a selection that contains no text stops prepare with the reason. Prefer
this to hand-copying a passage into a new file, which loses the locators a reader
checks against.

For academic-style profiles, pass structured front matter when available:
`title`, `author_block`, `affiliation_block`, `correspondence`, and `keywords`.
`academic_paper` does not render without any of them, and keywords are never
inferred for it. A field `start_report`
was not given can still be supplied during the run as a top-level
`"front_matter": {"correspondence": "..."}` block in `outline.json` — values
the user gives you, never invented; `start_report` arguments take precedence.
For school/company fixed templates, pass `template_fields` such as `course_name`,
`student_id`, `instructor`, `lab_section`, `date`, or `department`. Use
`project_identity` when a report must preserve specific project terms, domain
context, forbidden terms, or author metadata.

## Authoring Artifacts

After prepare, read the task briefs in `agent_tasks/`:

- `01_claim_plan.md`
- `02_outline_plan.md`
- `03_section_draft.md`
- `04_revision_plan.md` (for `revise_existing`)

Write these artifacts in the run directory:

- `claim_matrix.json`
- `outline.json`
- `structured_drafts.json` (preferred low-drift draft input)
- `section_drafts/*.md`
- `sentence_map.jsonl`

Every authored artifact must include the `_contract` block from the brief.
Optionally call `lint_artifacts` after edits for fast read-only feedback; it
writes `artifact_lint_report.json` with severity, artifact name, JSON path,
message, and repair hint.

## Structured Drafts (Preferred New-Draft Path)

`structured_drafts.json` may replace manual section Markdown and sentence-map
authoring for new drafts:

```json
{
  "sections": {
    "results": {
      "sentences": [
        {
          "text": "The pilot program enrolled 42 participants.",
          "claim_ids": ["c1"],
          "evidence_ids": ["E001"],
          "wording_strength": "hedged"
        }
      ]
    }
  }
}
```

The keys under `sections` are this run's blueprint section ids, the ones the
outline brief lists — `results` above is only an example. Profiles differ:
`engineering_lab_report` writes its results under `results_discussion`, and
`business_report` under `findings`.

When validation sees `structured_drafts.json` and the canonical draft files are
missing, the pipeline writes `section_drafts/*.md`, inserts `[CITE:]` markers from
`evidence_ids`, and writes `sentence_map.jsonl`.

A flat `sentences` list renders one paragraph per sentence. To write a paragraph
of several sentences, group them under `paragraphs`; each sentence keeps its own
claims and citations, and Chinese sentences are joined without a space:

```json
{"sections": {"results": {"paragraphs": [
  {"sentences": [
    {"text": "電動車出廠時比汽油車多排 3.6 t CO2e。", "claim_ids": ["c3"], "evidence_ids": ["E_D_production_gap_t"]},
    {"text": "差距幾乎全部來自電池。", "claim_ids": ["c3"], "evidence_ids": ["E_D_stage_breakdown"]}
  ]},
  {"sentences": [{"text": "[TABLE:E_D_stage_breakdown 表 2　基準情境的階段組成]"}]}
]}}}
```

A heading, a `[TABLE:]` or `[FIGURE:]` marker, or an image is a paragraph of its
own; set inside a paragraph with other sentences it is refused.

Use manual `section_drafts/*.md` plus `sentence_map.jsonl` only when the draft
needs direct Markdown control or when repairing generated canonical drafts.

**Do not open a section draft with its `section_id`.** The file is named
`section_drafts/<section_id>.md` because the coverage check against
`section_order` reads that name, but `executive_summary` is a key, not a title.
Write the real heading — `# 執行摘要`, `# Executive Summary` — or no heading at
all, since the pipeline renders the blueprint's own title above the section
either way. A draft opening with `# executive_summary` puts that string into
the delivered document, between the rendered heading and the first paragraph.

## What the Outline Must Account For

`OUTLINE_PLAN` refuses the outline until the built tables are accounted for. The
outline brief lists them, filled in with this run's ids, before you write it; the
other two headings below are written into the prose, not gated.

**Every cross tabulation the pipeline built.** They are computed at intake and
listed in the brief. Each is either placed — a claim cites its id, or a figure
draws on it — or waived by name:

```json
"unused_derived_evidence": {
  "E_28767e63_1af1b725ea": "the sales axis repeats the price-band table at a cut the argument does not use"
}
```

Any reason will do as long as there is one. A minimum length and a
no-duplicate-reasons rule were tried and removed — the delivered document was
byte-identical with and without them, so they were measuring compliance. What
remains is that dropping a table is a decision someone made in words; leaving one
unmentioned is not available.

**What would weaken the report.** A blueprint section may set
`counter_evidence` — `business_report`'s `limitations` does. That section carries
at least two claims of its own, and each of them names, in the prose, the
conclusion it qualifies and the figure that qualifies it. A section that weakens
nothing is a disclaimer.

**The questions the task statement asked.** When a section sets
`must_answer_prompt_questions` and the statement asks something, the brief lists
the questions against that section. Answer them there, in sentences. There is no
id mapping to fill in: an earlier version required `answers` by index and
`undermines` by claim id, and neither ever reached the page.

## Evidence and Citation Rules

- Every publishable claim needs at least one valid `evidence_id`.
- Do not mark publishable claims as `blocked`, `unverified`, or `disputed`.
- Statistical claims require quantitative evidence.
- Every evidence-backed sentence must include `[CITE:<evidence_id>]`.
- `sentence_map.jsonl` citation IDs must match the Markdown `[CITE:]` markers.
- For sentences supported by multiple entries, emit separate markers such as
  `[CITE:E001] [CITE:E002]`. Legacy `[CITE:E001,E002]` is accepted by validation,
  but newly generated drafts should emit separate markers.
- Use hedged wording for medium-grade or qualitative evidence.
- A direction asserted over a computed group table has to be the direction the
  whole table has. Quoting two rows of a fifteen-row table and writing 「愈高
  的組別，價格中位數也愈高」 is blocked by FT when the column's ordered group
  pairs and its two ends both disagree; the block prints the real ordering, so
  the repair is to state the relation the table does have, name the subset the
  claim is about, or drop the direction. Every number in such a sentence can be
  real and the sentence still wrong — that is the case this gate exists for.
- Do not cite internal workflow files, evidence ledgers, claim matrices,
  traceability appendices, generated task briefs, or workflow metadata.
- Use `query_evidence(job_id=..., query="...")` for relevance-ranked browsing when
  the ledger is large; use `evidence_ids=[...]` for exact lookups instead of
  loading the whole ledger into context.

## Draft Rules

Do not edit generated files such as `merged_draft.md`, `publication_draft.md`,
`base_document_sections.json`, publication outputs, checkpoint JSON, or the
harness manifest as an authoring shortcut. Edit only the agent-owned artifacts
allowed by the current harness stage, then rerun validation.

Avoid in body prose:

- placeholder text such as `This section is under development`
- `[Source:]`, `[graphify:]`, `[Note:]`, or other internal markers
- raw evidence IDs outside `[CITE:]`
- internal file paths
- ASCII-art diagrams; use Mermaid or real image assets instead (see
  [figures.md](figures.md))
- snake_case/camelCase data identifiers (`median_processing_minutes`,
  `structured_workflow`) — translate every column or field name into plain
  language with units: "median processing time (minutes)"
- recommendation ids (`figrec_1`) or dataset filenames (`chart_source`) in
  body text or figure captions — captions must describe the finding and its
  units ("Figure 1: Median processing time per note, manual baseline vs
  structured workflow (minutes)"), not the mechanics of the chart
- one template sentence repeated for several figures or results with only a
  noun swapped — vary each lead-in around what that specific figure shows

State grounded numbers instead of writing around them: when the evidence
contains the value, put it in the sentence ("the error rate fell from 9.0% to
3.5%"), reusing the evidence's own figures and units so the content checks
pass. A quantitative section with no numbers reads as evasive even when every
claim is verified.

Optional: a `facts_freeze.json` in the run directory (`{"total_files": "388"}`)
lists confirmed facts; render hard-blocks if any frozen value is missing from
the document.

## Document Language

Write body prose in the language of the source evidence. When the evidence is
Chinese-dominant, the `03_section_draft.md` brief says so and lists the
canonical Chinese section headings; the pipeline detects the document language
deterministically and renders section headings from the blueprint's localized
titles (`title_zh`), so do not hand-translate headings or mix English
boilerplate sentences into a Chinese document. English documents keep the
blueprint's English titles unchanged.

For `academic_paper` and `engineering_lab_report`, make Methods/Procedure
reproducible: name the source or sample basis, procedure, parameters or
instrument/software settings, and supported inclusion, exclusion, calibration,
normalization, or transform rules. In academic introductions, explicitly signal
the problem or gap, objective, and contribution before moving to results.

## Controlled Submission Details

Preferred sequence:

1. Call `get_next_action(job_id=...)`.
2. Read the returned `task_brief_path` and `read_first_paths`.
3. Edit only files listed in `allowed_write_paths`.
4. Call `submit_action(job_id=...)`.
5. Repeat until the returned `status` is `completed`.

Failure returns:

- `validation_failed`: repair only the returned `allowed_repair_paths` using
  `repair_context`.
- `scope_violation`: a file owned by a *later* stage was written early; remove
  it (or restore it) and retry the same stage. Do not manually advance stages by
  editing `harness_manifest.json`. Changing a file an *earlier* stage already
  accepted — fixing the claim matrix during the outline stage because lint
  named it — is not a violation: the run goes back to that stage, validates it
  again, and says so in `note`; submit again for each later stage.
- A failure routed back to an earlier stage (a publish failure goes to the
  earliest stage that owns part of the fix) opens every artifact from that stage
  onward for repair, and keeps the later artifacts you already wrote: fix the
  claim and the sentence together, then submit stage by stage. After a
  `publish_report` failure you may also edit first and call `submit_action`
  afterwards; the run re-opens at the stage that owns what you changed.
- `blocked_non_author_repair`: the failure is outside the current controlled
  authoring surface. Inspect the returned evidence paths; it needs a workflow,
  source, environment, or deterministic-code fix, not edits to read-only workflow
  artifacts or the harness manifest.

For `engineering_lab_report`, call `audit_engineering_report` after drafts exist.
Call `publish_report` when the controlled harness reaches the publish
stage or all required artifacts are already present.

## Reusing a Previous Run

If you reuse artifacts from an older run, call
`remap_agent_artifacts(job_id=..., previous_job_id=...)` first in dry-run mode,
then rerun with `write=True` only after the mapping is reasonable. The write
copies the files this run does not have yet from the earlier run; under the
controlled workflow only the open stage's files are copied, and
`files_deferred` names the rest with the stage that accepts them - call it again
with `write=True` when that stage opens. Pass `previous_workspace_root` when the
earlier run was started with a different `output_dir`. Do not manually edit
evidence IDs.

## Validation Failure Repair

Read the gate name and fix the canonical source artifact:

- Artifact shape or ID drift: run `lint_artifacts`, then edit the JSON path
  or file named in `artifact_lint_report.json`.
- Claim or evidence-support failures: edit `claim_matrix.json` or improve
  `evidence_ledger.jsonl` content. Do not edit checkpoint JSON.
- Citation failures: edit section drafts and `sentence_map.jsonl`.
- Section contract failures: edit `outline.json` or the relevant section draft.
- Engineering unit/calculation findings: inspect `engineering_audit_report.json`
  before changing claim text.
- Factuality failures: delete stale `factuality_report.json`, rerun validate, then
  inspect the fresh report.
- Render failures: fix Markdown structure, tables, figures, or template artifacts,
  rerun validation, then render.
