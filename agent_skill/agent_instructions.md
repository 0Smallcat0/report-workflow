# Report Workflow Agent Instructions

> **First time here?** Read `AGENT_ONBOARDING.md` (at the repo root) for a complete conceptual overview of what this workflow is, how it works, and why it is structured this way. This document assumes you have read the onboarding guide.

When you are asked to generate a report from source files using the `report_workflow` skill, follow this exact procedure:

## Step 1: Start the Workflow
1. Call the `start_report_task` tool with the user's `prompt`, a list of `source_files`, and an `output_dir`.
2. The tool will return a status of `awaiting_agent_artifacts` along with a `job_id` and a list of missing artifacts. The task briefs will be located in `~/.hermes/workflow_runs/<job_id>/agent_tasks/`.

## Step 2: Read Task Briefs
1. Read the following task briefs:
   - `01_claim_plan.md`
   - `02_outline_plan.md`
   - `03_section_draft.md`
2. The briefs contain precise instructions, JSON schemas, and Evidence Previews. You **MUST** strictly follow the JSON schema and the "Hard Rules" listed in the markdown.

## Step 3: Write Artifacts
Based on the task briefs, you must create and save the following files in the run directory (`~/.hermes/workflow_runs/<job_id>/`):
1. `claim_matrix.json`: Claims supported by evidence.
2. `outline.json`: Chapter allocation of claims.
3. `section_drafts/*.md`: Markdown files for each section.
4. `sentence_map.jsonl`: Sentence-level tracking.

## Step 4: Submit & Validate
1. Once **all artifacts** are saved, call the `submit_and_publish_report` tool with your `job_id`.
2. **If it fails (validation_failed)**: The tool will return a validation error message. Read the error message carefully. It means your artifacts violated a hard rule (e.g., missing evidence, invalid citation, missing sections). **Modify your JSON/MD files to fix the error**, and call `submit_and_publish_report` again.
3. **If it succeeds**: The tool will return the path to the final DOCX report. Provide this path to the user to conclude the task.

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
- **Internal markers**: `[Source:]`, `[graphify:]`, `[Note:]`, `[CITE:]` in main text prose. Use `[CITE:<evidence_id>]` ONLY in citation contexts.
- **Internal paths**: Evidence IDs (E001, E002), `.py` filenames, internal paths (e.g. `~/.hermes/...`, `D:\...`) in body text.
- **Internal tables**: Claim-Evidence Matrix tables, Community-to-Contribution Mapping tables, or any table with "Claim ID", "Evidence ID", "Status" column headers.
- **Placeholder metadata**: `[Author Name]`, `[University]`, `[email@domain.com]`. Use real values or leave blank.

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
- The pipeline embeds figures after their first in-text reference.

#### Abstract
- Use structured headings:
  ```
  ## Background:
  ## Objective:
  ## Methods:
  ## Principal Findings:
  ## Significance:
  ```
- Minimum 150 words. Maximum 220 words (ICMJE recommendation).
- No trailing ellipses (`...`), no incomplete sentences.
- No internal markers: `[CITE:]`, `[Source:]`, `[graphify:]`.

### Citation Format
- Use only `[CITE:<evidence_id>]` for evidence-backed claims in section drafts.
- Do NOT use bare `[Source:...]` or `[graphify:...]` — these are pipeline-internal markers that will not resolve and will hard-fail at CITATION_BIND.
- For figures from graph analysis, use `[CITE:<evidence_id>]` that points to the graph figure evidence.

### Section Role Boundaries
- Introduction: no raw results, no percentages, no "our results/findings"
- Methods: no conclusions, no "significant" findings
- Results: no interpretation ("suggests that", "indicates that"), no raw percentages without context
- Discussion: no raw numbers that belong in Results
