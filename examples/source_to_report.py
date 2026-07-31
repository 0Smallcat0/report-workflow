"""Two source files and one sentence in, a finished DOCX out.

This is the whole path the tool exists for. It runs offline, with no LLM and no
API key, on three ordinary files that ship next to this script:

    examples/data/pilot_results.csv   -- a five-column measurement table
    examples/data/monthly_medians.csv -- six months of one measure
    examples/data/pilot_brief.md      -- the notes a colleague would hand you

and one sentence of intent ("write a business report for the operations
manager..."). Out comes `published/report.docx` with a table of contents, page
numbers, a real Word table, a chart drawn from the monthly figures, and a QA
pack recording why every sentence was allowed to ship.

Three phases, and the middle one is not this package's job:

  1. PREPARE   -- the pipeline parses your files into an evidence ledger and
                  writes task briefs. Deterministic; no model involved.
  2. AUTHOR    -- *your agent* reads the ledger and writes the claims, the
                  outline, and the prose. This script does that part with a
                  fixed script instead of a model, so the example runs offline
                  and produces the same document every time. In real use this
                  is Claude Code, Codex, or whatever agent you drive it with.
  3. VALIDATE  -- the pipeline checks every claim against the ledger, resolves
     + RENDER     citations, and only then renders and packages the DOCX.

Run:
    python examples/source_to_report.py
    python examples/source_to_report.py --output /somewhere/else

To point it at your own material, change SOURCES and PROMPT below. Everything
after that is the same three calls.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from report_workflow.run_workflow import prepare_workflow, render_workflow, validate_workflow
from report_workflow.state import run_dir_for

HERE = Path(__file__).resolve().parent

# --- 1. What you bring -------------------------------------------------------
SOURCES = [
    HERE / "data" / "pilot_results.csv",
    HERE / "data" / "monthly_medians.csv",
    HERE / "data" / "pilot_brief.md",
]
PROMPT = (
    "write a business report for the operations manager on the document intake "
    "pilot: what changed, what it costs, and whether to adopt it"
)
PROFILE = "business_report"


# --- 2. What your agent brings ----------------------------------------------
# Everything from here to `author()` is the judgment an agent supplies: which
# claims are worth making, which evidence backs each one, and how the prose
# reads. It is scripted here so the example needs no model. The one rule it
# cannot bend is the pipeline's: a sentence may only assert what its cited
# evidence actually says.


def _pick(rows: list[dict[str, Any]], *terms: str) -> str:
    """Return the id of the ledger entry that mentions all of `terms`."""
    for row in rows:
        content = str(row.get("content") or "")
        if all(term.lower() in content.lower() for term in terms):
            return str(row["evidence_id"])
    raise SystemExit(
        f"No evidence entry mentions {terms!r}. The sources changed; update the "
        f"claims in {Path(__file__).name} to match what the ledger now contains."
    )


def _claims(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    measurement = _pick(rows, "Structured workflow", "20.0")
    trend = _pick(rows, "28.4")
    method = _pick(rows, "42 client notes", "processed twice")
    cost = _pick(rows, "4,800")
    limit = _pick(rows, "supports the finding rather")
    return [
        {
            "claim_id": "c_measurement",
            "claim_text": (
                "Across the same 42 notes the structured workflow cut the median from "
                "28.0 to 20.0 minutes per note, rework from 7.5% to 4.1%, and raised "
                "reviewer satisfaction from 71% to 84%."
            ),
            "claim_type": "statistical",
            "claim_role": "primary",
            "status": "supported",
            "evidence_ids": [measurement],
            "topic_tags": ["pilot outcome"],
        },
        {
            "claim_id": "c_trend",
            "claim_text": (
                "The desk's monthly median fell from 28.4 minutes per note in January "
                "to 20.0 in June as the structured workflow was phased in."
            ),
            "claim_type": "statistical",
            "claim_role": "supporting",
            "status": "supported",
            "evidence_ids": [trend],
            "topic_tags": ["rollout"],
        },
        {
            "claim_id": "c_method",
            "claim_text": (
                "The same 42 client notes were processed twice, by the same two "
                "reviewers in the same week, with no change to the intake form."
            ),
            "claim_type": "factual",
            "claim_role": "supporting",
            "status": "supported",
            "evidence_ids": [method],
            "topic_tags": ["method"],
        },
        {
            "claim_id": "c_cost",
            "claim_text": (
                "Adoption costs a one-off USD 4,800 for template work and two "
                "onboarding sessions, and takes about six weeks to pay back in speed."
            ),
            "claim_type": "factual",
            "claim_role": "supporting",
            "status": "supported",
            "evidence_ids": [cost],
            "topic_tags": ["cost"],
        },
        {
            "claim_id": "c_limit",
            "claim_text": (
                "Satisfaction came from the two reviewers who ran the pilot, so it "
                "supports the finding rather than carrying it."
            ),
            "claim_type": "factual",
            "claim_role": "background",
            "status": "supported",
            "evidence_ids": [limit],
            "topic_tags": ["limitation"],
        },
    ]


def _sentence(text: str, claim_ids: list[str], claims: list[dict[str, Any]]) -> dict[str, Any]:
    by_id = {str(claim["claim_id"]): claim for claim in claims}
    evidence_ids = [eid for cid in claim_ids for eid in by_id[cid]["evidence_ids"]]
    return {
        "text": text,
        "claim_ids": claim_ids,
        "evidence_ids": evidence_ids,
        "citation_ids": evidence_ids,
        "wording_strength": "hedged",
    }


# Conclusion first, because that is what this reader rewards -- the pipeline
# says so in the authoring brief it writes for the business_report profile.
PROSE: dict[str, tuple[str, list[str]]] = {
    "executive_summary": (
        "The structured workflow is worth adopting at the intake desk. Across the "
        "same 42 notes the structured workflow cut the median from 28.0 to 20.0 "
        "minutes per note, rework from 7.5% to 4.1%, and raised reviewer "
        "satisfaction from 71% to 84%. Adoption costs a one-off USD 4,800 for "
        "template work and two onboarding sessions, and takes about six weeks to "
        "pay back in speed. The evidence is one desk over one week, so the "
        "recommendation is to adopt at this desk and re-measure before extending.",
        ["c_measurement", "c_cost", "c_limit"],
    ),
    "findings": (
        "The comparison was designed so that the workflow was the only thing that "
        "differed. The same 42 client notes were processed twice, by the same two "
        "reviewers in the same week, with no change to the intake form. Across the "
        "same 42 notes the structured workflow cut the median from 28.0 to 20.0 "
        "minutes per note, rework from 7.5% to 4.1%, and raised reviewer "
        "satisfaction from 71% to 84%. The time saving and the rework drop point "
        "the same way, which is what makes the result usable for a scheduling "
        "decision rather than merely encouraging.",
        ["c_method", "c_measurement"],
    ),
    "recommendations": (
        "Adopt the structured workflow at this desk and budget for the ramp. "
        "Adoption costs a one-off USD 4,800 for template work and two onboarding "
        "sessions, and takes about six weeks to pay back in speed. Hold the "
        "decision to this desk for now: satisfaction came from the two reviewers "
        "who ran the pilot, so it supports the finding rather than carrying it. "
        "Re-measure after the first full quarter before extending to a desk with a "
        "different note format.",
        ["c_cost", "c_limit"],
    ),
}


# One lead-in and one caption per exhibit kind. The pipeline decides which kind
# it plans from the shape of your data -- mixed units become a table rather than
# a chart with two incompatible y-axes.
# The lead-in sentence is the author's; the caption underneath is not. The
# renderer numbers each exhibit and captions it from the title in the figure
# plan, so writing a caption in the prose as well prints it twice.
EXHIBITS: dict[str, tuple[str, list[str]]] = {
    "Table": (
        "sets the two conditions side by side, with the note counts the medians rest on.",
        ["c_measurement"],
    ),
    "Figure": (
        "traces the monthly median through the phase-in, which is where the "
        "six-week ramp is visible.",
        ["c_trend"],
    ),
}
EXHIBIT_TITLES = {
    "table": "Intake desk pilot, manual baseline versus structured workflow",
    "line": "Median minutes per note by month during the phase-in",
}


def author(state: Any) -> dict[str, Any]:
    """Write the three artifacts an agent owes the pipeline."""
    run_dir = run_dir_for(state)
    ledger = Path(state.sources["evidence_ledger_path"])
    rows = [json.loads(line) for line in ledger.read_text(encoding="utf-8").splitlines() if line.strip()]
    claims = _claims(rows)
    claim_ids = [str(claim["claim_id"]) for claim in claims]

    # The pipeline already proposed charts from the data; whatever it planned
    # must appear in the prose, so pick them up and place them in Key Findings.
    plan_path = run_dir / "section_drafts" / "figure_plan.json"
    plan = json.loads(plan_path.read_text(encoding="utf-8")) if plan_path.exists() else {}
    figures = [f for f in plan.get("figures", []) if isinstance(f, dict) and f.get("figure_id")]
    for figure in figures:
        figure["section_id"] = "findings"
        human_title = EXHIBIT_TITLES.get(str(figure.get("figure_type")))
        if human_title:
            figure["title"] = human_title
    if figures:
        plan["figures"] = figures
        plan_path.write_text(json.dumps(plan, indent=2), encoding="utf-8")
    figure_ids = [str(figure["figure_id"]) for figure in figures]

    blueprint = state.plan.get("blueprint") or {}
    sections: dict[str, Any] = {}
    outline_sections: dict[str, Any] = {}
    for section_id in blueprint.get("section_order", []):
        spec = blueprint.get("sections", {}).get(section_id, {})
        # An optional section you have nothing to put in still renders as a bare
        # numbered heading, so leave it out of the outline rather than in it.
        if not spec.get("required", True) and section_id not in PROSE:
            continue
        title = spec.get("title") or section_id.replace("_", " ").title()
        sentences = []
        if section_id in PROSE:
            text, cited = PROSE[section_id]
            sentences.append(_sentence(text, cited, claims))
        if section_id == "findings":
            # A table-type exhibit renders as a real Word table and is numbered
            # "Table 1", not "Figure 1" -- calling it the wrong thing is a hard
            # block, because then the prose points at an image that is not there.
            counters = {"Table": 0, "Figure": 0}
            for figure in figures:
                label = "Table" if str(figure.get("figure_type")) == "table" else "Figure"
                counters[label] += 1
                lead, cited = EXHIBITS[label]
                # The placeholder gets a paragraph of its own; left inline, the
                # exhibit and its caption land inside the lead-in sentence.
                sentences.append(_sentence(
                    f"{label} {counters[label]} {lead}\n\n[FIGURE:{figure['figure_id']}]",
                    cited,
                    claims,
                ))
        sections[section_id] = {"title": title, "sentences": sentences}
        outline_sections[section_id] = {
            "section_id": section_id,
            "title": title,
            "claim_ids": claim_ids,
            "figure_ids": figure_ids if section_id == "findings" else [],
        }

    (run_dir / "claim_matrix.json").write_text(
        json.dumps({"claims": claims}, indent=2), encoding="utf-8")
    (run_dir / "outline.json").write_text(json.dumps({
        "thesis_statement": (
            "The structured workflow is worth adopting at the intake desk, on "
            "evidence bounded to that desk."
        ),
        "sections": outline_sections,
    }, indent=2), encoding="utf-8")
    (run_dir / "structured_drafts.json").write_text(
        json.dumps({"generated_by": "examples.source_to_report", "sections": sections}, indent=2),
        encoding="utf-8")
    return {"claims": len(claims), "evidence": len(rows), "figures": len(figure_ids)}


# --- 3. Run the three phases -------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--output", default="examples_out",
                        help="where the run directory goes (default: ./examples_out)")
    args = parser.parse_args()
    workspace = Path(args.output).expanduser().resolve()

    print(f"\n[1/3] PREPARE  parsing {len(SOURCES)} source files")
    state = prepare_workflow(
        user_prompt=PROMPT,
        uploaded_files=[str(path) for path in SOURCES],
        output_dir=str(workspace),
        report_profile=PROFILE,
        enable_research=False,
        enable_notebook_sync=False,
    )
    print(f"        job {state.job_id} -> {run_dir_for(state)}")

    print("\n[2/3] AUTHOR   writing claims, outline, and prose (your agent's job)")
    counts = author(state)
    print(f"        {counts['evidence']} evidence entries -> {counts['claims']} claims, "
          f"{counts['figures']} figure(s)")

    print("\n[3/3] VALIDATE + RENDER")
    validate_workflow(state.job_id, workspace_root=str(workspace))
    rendered = render_workflow(state.job_id, workspace_root=str(workspace))

    published = Path(rendered.output["published_dir"])
    docx = published / "report.docx"
    print(f"\n{'=' * 74}")
    print(f"qa_decision : {rendered.qa.get('qa_decision')}")
    print(f"report      : {docx}")
    print(f"QA pack     : {published / 'qa'}")
    print(f"{'=' * 74}")
    print("Every claim in that document is linked to material from your own")
    print("source files. Open traceability/client_readable_qa_note.md to read")
    print("what backs each one.")
    return 0 if docx.exists() else 1


if __name__ == "__main__":
    raise SystemExit(main())
