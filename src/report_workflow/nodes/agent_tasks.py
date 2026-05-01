"""Agent task brief generation for agent-skill-driven workflow stages."""
from __future__ import annotations

import json
from pathlib import Path

from ..state import ReportState
from ..runtime_support import run_dir_for
from ..artifact_contract import make_artifact_contract


def agent_tasks_dir(state: ReportState) -> Path:
    path = run_dir_for(state) / "agent_tasks"
    path.mkdir(parents=True, exist_ok=True)
    state.runtime["agent_tasks_dir"] = str(path)
    return path


def _read_jsonl_preview(path: str | None, limit: int = 8) -> list[dict]:
    rows = []
    if not path or not Path(path).exists():
        return rows
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rows.append(json.loads(line))
            if len(rows) >= limit:
                break
    return rows


def _read_jsonl_compact_summary(path: str | None, limit: int = 20) -> str:
    """Build a compact evidence summary for task briefs.

    Returns a concise table-like string instead of full JSON,
    drastically reducing context consumption for the Agent.
    Each entry: evidence_id | source_file | evidence_type | quote (first 80 chars)
    """
    if not path or not Path(path).exists():
        return "(no evidence ledger found)"
    rows = []
    total = 0
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                total += 1
                if len(rows) < limit:
                    entry = json.loads(line)
                    eid = entry.get("evidence_id", "?")
                    src = entry.get("source_file_name", "?")
                    etype = entry.get("evidence_type", "?")
                    quote = (entry.get("quote", "") or "")[:80].replace("\n", " ")
                    allowed = ", ".join(entry.get("allowed_claim_types", []))
                    rows.append(f"  {eid} | {src} | {etype} | allowed:[{allowed}] | {quote}")
    header = f"Total evidence entries: {total} (showing first {min(total, limit)})\n"
    header += "  evidence_id | source_file | evidence_type | allowed_claim_types | quote_preview\n"
    header += "  " + "-" * 80 + "\n"
    return header + "\n".join(rows)


def write_agent_task_briefs(state: ReportState) -> ReportState:
    """Write all task briefs required for the external agent authoring phase.

    For 'revise_existing', also writes 04_revision_plan.md.
    """
    tasks_dir = agent_tasks_dir(state)
    run_dir = run_dir_for(state)
    evidence_path = state.sources.get("evidence_ledger_path", "")
    evidence_summary = _read_jsonl_compact_summary(evidence_path)
    task_intent = state.spec.get("task_intent", "new_draft")
    contract = make_artifact_contract(state)
    contract_json = json.dumps(contract, indent=2)

    if (
        task_intent == "new_draft"
        and state.spec.get("report_profile") == "academic_paper"
        and not state.spec.get("project_identity")
    ):
        candidate_path = run_dir / "project_identity_candidate.json"
        if not candidate_path.exists():
            candidate_path.write_text(
                json.dumps({
                    "required_terms": [],
                    "required_context_terms": [],
                    "forbidden_terms": [],
                    "canonical_title_terms": [],
                    "domain_context": "",
                    "author_metadata": {},
                    "source": "agent_must_review",
                }, indent=2),
                encoding="utf-8",
            )
        state.runtime["project_identity_candidate_path"] = str(candidate_path)

    claim_task = f"""# 01 Claim Plan

You are operating inside an agent/coding environment. Do not call any external API from the workflow code.

## Inputs
- Report spec: `{run_dir / "report_spec.json"}`
- Blueprint: `{run_dir / "blueprint.json"}`
- Evidence ledger: `{evidence_path}`

## Required Output
Write `{run_dir / "claim_matrix.json"}` with this shape:

```json
{{
  "_contract": {contract_json},
  "claims": [
    {{
      "claim_id": "c1",
      "claim_text": "Specific evidence-backed claim.",
      "claim_type": "factual|statistical|methodological|regulatory|qualitative|contextual",
      "risk_level": "low|medium|high",
      "status": "supported",
      "evidence_ids": ["evidence id from evidence_ledger.jsonl"],
      "requires_hedged_wording": false,
      "claim_role": "primary|supporting|background"
    }}
  ]
}}
```

## Artifact Contract
Keep `_contract` exactly aligned with this run. If you reuse artifacts from an older job,
run `remap_agent_artifacts(job_id="{state.job_id}", previous_job_id="<old>", write=true)`
instead of manually copying evidence IDs.

Do not edit `merged_draft.md`, checkpoint files, or `base_document_sections.json`.
For `new_draft`, the editable artifacts are `claim_matrix.json`, `outline.json`,
`section_drafts/*.md`, and `sentence_map.jsonl`.

## Hard Rules
- Every claim must have at least one `evidence_id`.
- Use only evidence IDs from `evidence_ledger.jsonl`.
- Do not use `blocked`, `unverified`, or `disputed` for publishable claims.
- Statistical claims require quantitative evidence.
- For internal project documents, use `factual`, `methodological`, or `qualitative`
  claims unless the evidence explicitly allows `statistical`.
- Mark medium-grade or qualitative source wording as hedged in `sentence_map.jsonl`;
  reserve `measured` wording for high-grade or quantitative evidence.
- **Academic reports**: Every claim MUST have a `claim_role` field with value `primary`, `supporting`, or `background`.
  - `primary`: Core contribution claims (max 3). Must directly support the thesis/contribution.
  - `supporting`: Evidence that backs a primary claim.
  - `background`: Context, definitions, or prior work not central to contribution.
  - At least 1 primary claim required. No more than 3 primary claims.

## Evidence Summary
(Full ledger at `{evidence_path}`; read individual entries as needed)
```
{evidence_summary}
```
"""

    outline_task = f"""# 02 Outline Plan

## Inputs
- Blueprint: `{run_dir / "blueprint.json"}`
- Claim matrix: `{run_dir / "claim_matrix.json"}`

## Required Output
Write `{run_dir / "outline.json"}` with this shape:

```json
{{
  "_contract": {contract_json},
  "results_mode": "empirical" | "architectural_characterization",
  "sections": {{
    "results": {{
      "section_id": "results",
      "goals": "What this section should accomplish.",
      "claim_ids": ["claim id from claim_matrix.json"],
      "paragraph_order": ["paragraph intent"],
      "figure_ids": []
    }}
  }}
}}
```

## Artifact Contract
Include the `_contract` block shown above. It lets the workflow catch stale
artifacts before QA_GATE.

Do not edit `merged_draft.md` directly. It is generated and will be overwritten.

## results_mode Selection (required for academic reports)

**Choose ONE and include it in outline.json at the top level:**

- `empirical`: Select when your evidence contains measured/quantitative data (numbers, percentages, performance metrics). Results section presents actual findings with statistical support.

- `architectural_characterization`: Select when your evidence is structural/code analysis (graphs, dependency trees, module relationships, system descriptions). Results section characterizes architecture without claiming empirical performance superiority.

**Do NOT mix modes**: If your evidence has both quantitative data AND architectural descriptions, pick the dominant mode based on what your claims actually argue.

## Hard Rules
- Assign every claim to at least one non-reference/non-appendix section.
- Use only section IDs defined by the blueprint.
- Use only claim IDs from `claim_matrix.json`.
- `results_mode` must be set; choose empirical or architectural_characterization.
"""

    section_task = f"""# 03 Section Draft

## Inputs
- Blueprint: `{run_dir / "blueprint.json"}`
- Claim matrix: `{run_dir / "claim_matrix.json"}`
- Outline: `{run_dir / "outline.json"}`
- Evidence ledger: `{evidence_path}`

## Required Outputs
- Markdown section files under `{run_dir / "section_drafts"}`
- Sentence map: `{run_dir / "sentence_map.jsonl"}`

Each sentence map line must be JSON:

```json
{{"_contract": {contract_json}}}
{{
  "sentence_id": "sent_0",
  "section_id": "results",
  "claim_ids": ["c1"],
  "evidence_ids": ["evidence id from evidence_ledger.jsonl"],
  "citation_ids": ["same evidence id used in [CITE:<id>]"],
  "wording_strength": "measured|hedged|weak",
  "draft_origin": "agent_draft"
}}
```

The first line of `sentence_map.jsonl` should be the `_contract` line shown above.
All following lines should be sentence entries.

Do not edit `merged_draft.md` directly. For `new_draft`, fix section files under
`section_drafts/`; the workflow rebuilds merged drafts from them.

## Hard Rules
- Every evidence-backed sentence must include `[CITE:<evidence_id>]` in the Markdown.
- Do not invent claims not present in `claim_matrix.json`.
- Do not write placeholder text such as "This section is under development".
- Use `wording_strength="hedged"` unless the linked evidence is high-grade or quantitative.
- Write one Markdown file for each required blueprint section, plus any optional section included in `outline.json`.
- **Publication text forbidden patterns** (hard blocks in the pipeline):
  - `[Source:]`, `[graphify:]`, `[Note:]`, or any internal workflow marker.
  - Evidence IDs, `.py` filenames, or internal workspace paths (e.g. `output/...`) in body text.
  - Any table containing "audit", "evidence", or "claim" in the header; these are internal artifacts.
  - **Write real content; do not use placeholder names** like `[Author Name]`, `[University]`, `[email@domain.com]`.

## Profile-Specific Abstract Template

**Two accepted formats** (choose one based on your report_profile):

### Option A: Structured Abstract (for journal submissions)

```markdown
# Abstract

**Background:** [2-3 sentences on the problem context]

**Objective:** [1-2 sentences on the specific aim]

**Methods:** [3-5 sentences on what was done, past tense]

**Principal Findings:** [3-5 sentences on key results, including numbers when supported]

**Significance:** [1-2 sentences on why this matters]

```

### Option B: Plain Paragraph (for admissions reports, project reports)

```markdown
# Abstract

[Single continuous paragraph, 150-250 words. No sub-headings needed.
Covers background, objective, methods, key findings, and significance
in a flowing narrative.]
```

**Word count: 150-250 words total unless the profile contract says otherwise.**
Count words after removing `[CITE:]` markers.
**No trailing ellipses (`.....`), no incomplete sentences.**
**No `[CITE:]`, `[Source:]`, or `[graphify:]` markers in the abstract.**

## Admissions-facing academic reports

If `report_profile=admissions_report` or `admissions_project_report`, prefer:
- Option B plain-paragraph abstract by default
- project-monograph tone rather than journal-template tone
- research narrative that foregrounds contribution, design choices, and research potential
- deterministic compilation / StrategyIR / AST / orthogonal quality gates as the spine
- LLM components as constrained supporting modules, not co-equal contributions

## Engineering lab reports

If `report_profile=engineering_lab_report`, preserve the lab handout contract:
- cover experiment purpose, theory, apparatus, procedure, results, discussion,
  conclusion/reflection, and references
- keep formulas, variables, parameters, units, and calculation assumptions traceable
- answer required discussion questions from the source handout
- reference figures and tables near the relevant result text
- avoid workflow, agent, or tool jargon in the report body

## Evidence Lookup

For large projects with many evidence entries, use the `query_evidence` tool
to look up specific evidence entries by ID instead of reading the full ledger:

```
query_evidence(job_id="<job_id>", evidence_ids=["E001", "E002"])
query_evidence(job_id="<job_id>", offset=20, limit=20)  # page 2
```

## Facts Freeze (Optional)

If a `facts_freeze.json` file exists in the run directory, its key-value pairs
are treated as **confirmed facts**. The pipeline will hard-block if any frozen
fact value is NOT found in the final document.

Example `facts_freeze.json`:
```json
{{
  "total_files": "388",
  "graph_nodes": "5,171",
  "top_hub": "Context (226 edges)"
}}
```

## Academic-Style Methods Protocol Guidance

Methods section describes **procedure** (what was done), NOT findings. Use past tense.

**GOOD (protocol style):**
- "We parsed the source code using an AST builder to extract function definitions..."
- "Centrality metrics were computed using NetworkX..."
- "Communities were detected via the Louvain algorithm..."

**BAD (results style):**
- "The parser extracted 226 edges from 30 source files showing a modular structure..."
- "NetworkX computed centrality metrics demonstrating the hub-like nature of..."

## Academic-Style Results Mode

If `results_mode` in `outline.json` is `empirical`: Present measured data, statistics, comparisons with numbers.

If `results_mode` is `architectural_characterization`: Describe structural properties, module relationships, and dependency patterns. Do NOT make empirical performance claims without evidence.

## Figure Guidance

Reference figures by their number in the body text at the natural point of discussion (e.g. "as shown in Figure 2"). Do NOT dump all figures at the end of the document. The rendering pipeline will embed each figure after its first reference.

**Use `mermaid` code fences for diagrams.** The pipeline auto-converts them to PNG images
if `mmdc` is installed. Examples:

````markdown
```mermaid
graph LR
    A[Source Files] --> B[AST Parser]
    B --> C[Graph Builder]
    C --> D[Community Detection]
```
````

````markdown
```mermaid
sequenceDiagram
    Agent->>Pipeline: start_report_task()
    Pipeline-->>Agent: job_id + task briefs
    Agent->>Pipeline: submit_claim_matrix()
    Agent->>Pipeline: submit_and_publish_report()
    Pipeline-->>Agent: rendered_report.docx
```
````

**FORBIDDEN:** Do NOT use ASCII art or box-drawing character diagrams.
These render poorly in DOCX and will be **hard-blocked** by the pre-render sanity gate.

## Project Identity

For academic `new_draft`, if `{run_dir / "project_identity.json"}` does not exist,
review `{run_dir / "project_identity_candidate.json"}` and write a confirmed
`project_identity.json` before final publication. Use it to keep the thesis from
drifting into a topic-adjacent report.
"""

    files: dict[str, str] = {
        "01_claim_plan.md": claim_task,
        "02_outline_plan.md": outline_task,
        "03_section_draft.md": section_task,
    }
    required_artifacts: list[str] = [
        str(run_dir / "claim_matrix.json"),
        str(run_dir / "outline.json"),
        str(run_dir / "section_drafts"),
        str(run_dir / "sentence_map.jsonl"),
    ]

    if task_intent == "revise_existing":
        base_sections_path = state.sources.get("base_document_sections_path", "")
        user_prompt_value = state.spec.get("user_prompt", "")
        revision_task = f"""# 04 Revision Plan

## Context
You are revising an existing document based on new evidence (source files).
The base document has been parsed into sections. You must produce a change manifest.

## Inputs
- Revision goal: `{user_prompt_value}`
- Base document sections: `{base_sections_path}`
  (section_id -> markdown content)
- Evidence ledger: `{evidence_path}`
- Claim matrix: `{run_dir / "claim_matrix.json"}`

## Required Output
Write `{run_dir / "revision_plan.json"}` with this shape:

```json
{{
  "changes": [
    {{
      "section_id": "results",
      "change_type": "replace|insert|delete",
      "original_text": "exact text from base document to change",
      "new_text": "replacement text",
      "claim_ids": ["c1"],
      "evidence_ids": ["e1"]
    }}
  ]
}}
```

## Change Types
- `replace`: swap `original_text` with `new_text` in the given section
- `insert`: insert `new_text` after `original_text` (or at section start if `original_text` is empty)
- `delete`: remove `original_text` from the section

## Hard Rules
- Every change must link to at least one `claim_id` and `evidence_id`.
- `claim_ids` must exist in `claim_matrix.json`.
- `evidence_ids` must exist in `evidence_ledger.jsonl`.
- Provide enough `original_text` for unambiguous matching (usually at least 40 characters).
- Do not repeat changes for the same text.
- **Two changes must NOT overlap**: if change A modifies "hello world" and
  change B modifies "world foo" in the same section, this is a conflict
  and will be hard-blocked.

## Validation Workflow

1. Write `revision_plan.json` following the schema above.
2. Call `submit_revision_plan(job_id="...")` to pre-validate:
   - Checks every `original_text` exists in the base document
   - Detects overlapping/conflicting changes
   - Returns a diff preview showing what each change would do
3. If validation fails, fix `revision_plan.json` and call again.
4. Optionally call `preview_revision_diff(job_id="...")` for a read-only preview.
5. Once validated, call `submit_and_publish_report(job_id="...")`.

Do not edit `base_document_sections.json`, checkpoint files, or rendered markdown
artifacts directly. For `revise_existing`, the only supported authoring surface is
`revision_plan.json`.

## Best Practices
- Modify 1-3 sections per revision plan. Large plans risk conflicts.
- Copy `original_text` exactly from the base document; even whitespace matters.
- If you need to rewrite an entire section (>70% change), consider `new_draft` mode instead.
"""
        files["04_revision_plan.md"] = revision_task
        required_artifacts.append(str(run_dir / "revision_plan.json"))

    for filename, content in files.items():
        (tasks_dir / filename).write_text(content, encoding="utf-8")

    state.runtime["agent_task_paths"] = {name: str(tasks_dir / name) for name in files}
    state.runtime["required_agent_artifacts"] = required_artifacts

    # Generate skeleton templates for section drafts
    _generate_section_skeletons(state, run_dir)

    return state


def _generate_section_skeletons(state: ReportState, run_dir: Path) -> None:
    """Create starter skeleton files for each required section.

    Gives the Agent a pre-formatted starting point with correct headings,
    placeholder paragraphs, and CITE examples, reducing format errors.
    """
    try:
        skeleton_dir = run_dir / "section_skeletons"
        skeleton_dir.mkdir(parents=True, exist_ok=True)

        # Read blueprint to get required sections
        blueprint_path = run_dir / "blueprint.json"
        if not blueprint_path.exists():
            return

        with open(blueprint_path, encoding="utf-8") as f:
            blueprint = json.load(f)

        sections = blueprint.get("sections", [])
        if not sections:
            return

        # Section-specific guidance
        section_hints = {
            "abstract": (
                "Write a concise summary of the entire report. "
                "No citations. 150-250 words."
            ),
            "introduction": (
                "Introduce the problem, motivation, and research questions. "
                "No raw results here. End with a paper organization paragraph."
            ),
            "methods": (
                "Describe what was done (past tense, protocol style). "
                "Do NOT include results or conclusions."
            ),
            "results": (
                "Present findings: data, measurements, observations. "
                "Do NOT interpret results here; save that for Discussion."
            ),
            "discussion": (
                "Interpret results, compare with related work. "
                "Address each primary claim from the claim matrix."
            ),
            "conclusion": (
                "Summarize contributions, acknowledge limitations, "
                "suggest future work."
            ),
            "references": (
                "List all cited references in APA format. "
                "Each entry on its own line."
            ),
        }

        for section in sections:
            # Handle both dict format ({"section_id": "...", "title": "..."})
            # and plain string format ("introduction")
            if isinstance(section, dict):
                sid = section.get("section_id", "")
                title = section.get("title", sid.replace("_", " ").title())
            else:
                sid = str(section)
                title = sid.replace("_", " ").title()

            if not sid:
                continue

            hint = section_hints.get(sid, "Write content for this section.")

            skeleton_content = f"""# {title}

<!-- {hint} -->

<!-- Replace this placeholder with your content. -->
<!-- Use [CITE:<evidence_id>] for every evidence-backed claim. -->

"""

            skeleton_path = skeleton_dir / f"{sid}.md"
            skeleton_path.write_text(skeleton_content, encoding="utf-8")

        state.runtime["section_skeletons_dir"] = str(skeleton_dir)
    except Exception:
        # Skeleton generation is non-critical; never crash the pipeline
        pass


def run_agent_task_briefs(state: ReportState) -> ReportState:
    """Prepare the run for external agent artifact authoring."""
    state = write_agent_task_briefs(state)
    state.update_status("awaiting_agent_artifacts")
    return state
