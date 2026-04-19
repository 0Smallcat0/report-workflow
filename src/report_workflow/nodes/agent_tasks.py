"""Agent task brief generation for agent-skill-driven workflow stages."""
from __future__ import annotations

import json
from pathlib import Path

from ..state import ReportState
from ..runtime_support import run_dir_for


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


def write_agent_task_briefs(state: ReportState) -> ReportState:
    """Write all task briefs required for the external agent authoring phase.

    For 'revise_existing', also writes 04_revision_plan.md.
    """
    tasks_dir = agent_tasks_dir(state)
    run_dir = run_dir_for(state)
    evidence_path = state.sources.get("evidence_ledger_path", "")
    evidence_preview = json.dumps(_read_jsonl_preview(evidence_path), indent=2, ensure_ascii=False)
    task_intent = state.spec.get("task_intent", "new_draft")

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

## Hard Rules
- Every claim must have at least one `evidence_id`.
- Use only evidence IDs from `evidence_ledger.jsonl`.
- Do not use `blocked`, `unverified`, or `disputed` for publishable claims.
- Statistical claims require quantitative evidence.
- **Academic reports**: Every claim MUST have a `claim_role` field with value `primary`, `supporting`, or `background`.
  - `primary`: Core contribution claims (max 3). Must directly support the thesis/contribution.
  - `supporting`: Evidence that backs a primary claim.
  - `background`: Context, definitions, or prior work not central to contribution.
  - At least 1 primary claim required. No more than 3 primary claims.

## Evidence Preview
```json
{evidence_preview}
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

## results_mode Selection (required for academic reports)

**Choose ONE and include it in outline.json at the top level:**

- `empirical`: Select when your evidence contains measured/quantitative data (numbers, percentages, performance metrics). Results section presents actual findings with statistical support.

- `architectural_characterization`: Select when your evidence is structural/code analysis (graphs, dependency trees, module relationships, system descriptions). Results section characterizes architecture without claiming empirical performance superiority.

**Do NOT mix modes**: If your evidence has both quantitative data AND architectural descriptions, pick the dominant mode based on what your claims actually argue.

## Hard Rules
- Assign every claim to at least one non-reference/non-appendix section.
- Use only section IDs defined by the blueprint.
- Use only claim IDs from `claim_matrix.json`.
- `results_mode` must be set — choose empirical or architectural_characterization.
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

## Hard Rules
- Every evidence-backed sentence must include `[CITE:<evidence_id>]` in the Markdown.
- Do not invent claims not present in `claim_matrix.json`.
- Do not write placeholder text such as "This section is under development".
- Write one Markdown file for each required blueprint section, plus any optional section included in `outline.json`.
- **Academic reports — forbidden patterns** (hard blocks in the pipeline):
  - `[Source:]`, `[graphify:]`, `[Note:]`, or any internal workflow marker.
  - Evidence IDs, `.py` filenames, or internal paths (e.g. `~/.hermes/...`) in body text.
  - Any table containing "audit", "evidence", or "claim" in the header — these are internal artifacts.
  - **Write real content; do not use placeholder names** like `[Author Name]`, `[University]`, `[email@domain.com]`.

## Academic Reports — Abstract Template (MANDATORY structure)

The abstract MUST use exactly these 5 headings with colons:

```markdown
# Abstract

**Background:** [2-3 sentences on the problem context]

**Objective:** [1-2 sentences on the specific aim]

**Methods:** [3-5 sentences on what was done — past tense]

**Principal Findings:** [3-5 sentences on key results — can include numbers]

**Significance:** [1-2 sentences on why this matters]

```

**Word count: 180–220 words total.** Count words after removing `[CITE:]` markers.
**No trailing ellipses (`.....`), no incomplete sentences.**
**No `[CITE:]`, `[Source:]`, or `[graphify:]` markers in the abstract.**

## Academic Reports — Methods Protocol Guidance

Methods section describes **procedure** (what was done), NOT findings. Use past tense.

**GOOD (protocol style):**
- "We parsed the source code using an AST builder to extract function definitions..."
- "Centrality metrics were computed using NetworkX..."
- "Communities were detected via the Louvain algorithm..."

**BAD (results style):**
- "The parser extracted 226 edges from 30 source files showing a modular structure..."
- "NetworkX computed centrality metrics demonstrating the hub-like nature of..."

## Academic Reports — Results Mode

If `results_mode` in `outline.json` is `empirical`: Present measured data, statistics, comparisons with numbers.

If `results_mode` is `architectural_characterization`: Describe structural properties, module relationships, dependency patterns — do NOT make empirical performance claims without evidence.

## Academic Reports — Figures

Reference figures by their number in the body text at the natural point of discussion (e.g. "as shown in Figure 2"). Do NOT dump all figures at the end of the document. The rendering pipeline will embed each figure after its first reference.
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
  (section_id → markdown content)
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
- Provide enough `original_text` for unambiguous matching (≥20 characters).
- Do not repeat changes for the same text.
"""
        files["04_revision_plan.md"] = revision_task
        required_artifacts.append(str(run_dir / "revision_plan.json"))

    for filename, content in files.items():
        (tasks_dir / filename).write_text(content, encoding="utf-8")

    state.runtime["agent_task_paths"] = {name: str(tasks_dir / name) for name in files}
    state.runtime["required_agent_artifacts"] = required_artifacts
    return state


def run_agent_task_briefs(state: ReportState) -> ReportState:
    """Prepare the run for external agent artifact authoring."""
    state = write_agent_task_briefs(state)
    state.update_status("awaiting_agent_artifacts")
    return state
