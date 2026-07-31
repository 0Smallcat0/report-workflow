"""Agent task brief generation for agent-skill-driven workflow stages."""
from __future__ import annotations

import json
from pathlib import Path

from ..state import ReportState
from ..language import detect_document_language, localized_section_title
from ..policies import get_policy
from ..runtime_support import run_dir_for
from ..artifact_contract import make_artifact_contract
from .corpus_build import _distinguishing_seed
from .figure_types import SUPPORTED_FIGURE_TYPES_TEXT


def agent_tasks_dir(state: ReportState) -> Path:
    path = run_dir_for(state) / "agent_tasks"
    path.mkdir(parents=True, exist_ok=True)
    state.runtime["agent_tasks_dir"] = str(path)
    return path


def _source_labels(entries: list[dict]) -> dict[str, str]:
    """Label sources so two files with the same basename can be told apart.

    Monthly exports arrive as 2024/月報.csv and 2025/月報.csv. The brief showed
    both as "月報.csv", so an author choosing between two rows of numbers had
    nothing to choose by — and citing the wrong year's row passes every gate,
    because the number does match the evidence it cites. Only the label
    changes; source_file_name still holds the file's actual name.
    """
    paths_by_name: dict[str, set[str]] = {}
    for entry in entries:
        paths_by_name.setdefault(entry.get("source_file_name", ""), set()).add(
            entry.get("source_file_path", "")
        )
    labels: dict[str, str] = {}
    for name, paths in paths_by_name.items():
        if len(paths) < 2:
            for path in paths:
                labels[path] = name
            continue
        # One parent folder was tried and, if that did not separate them, the
        # whole absolute path was printed. A student who keeps one folder per
        # experiment has 實驗一/data/量測.csv and 實驗二/data/量測.csv: the
        # parents are both "data", so every row of the evidence table carried a
        # 136-character path — in a table whose stated job is to keep the
        # agent's context small, and with the author's directory tree in it.
        #
        # The shortest tail that tells them apart is the same question source
        # ids answer, so it is answered in the same place rather than twice.
        siblings = [Path(path) for path in paths]
        for path in paths:
            labels[path] = _distinguishing_seed(Path(path), siblings)
    return labels


def _read_jsonl_compact_summary(path: str | None, limit: int = 20) -> str:
    """Build a compact evidence summary for task briefs.

    Returns a concise table-like string instead of full JSON,
    drastically reducing context consumption for the Agent.
    Each entry: evidence_id | source_file | evidence_type | quote (first 80 chars)
    """
    if not path or not Path(path).exists():
        return "(no evidence ledger found)"
    with open(path, encoding="utf-8") as f:
        entries = [json.loads(line) for line in f if line.strip()]
    labels = _source_labels(entries)
    rows = []
    total = 0
    for entry in entries:
        total += 1
        if len(rows) < limit:
            eid = entry.get("evidence_id", "?")
            src = labels.get(entry.get("source_file_path", ""), "") or entry.get("source_file_name", "?")
            etype = entry.get("evidence_type", "?")
            quote = (entry.get("quote", "") or "")[:80].replace("\n", " ")
            allowed = ", ".join(entry.get("allowed_claim_types", []))
            rows.append(f"  {eid} | {src} | {etype} | allowed:[{allowed}] | {quote}")
    header = f"Total evidence entries: {total} (showing first {min(total, limit)})\n"
    header += "  evidence_id | source_file | evidence_type | allowed_claim_types | quote_preview\n"
    header += "  " + "-" * 80 + "\n"
    return header + "\n".join(rows)


def _evidence_text_for_language(path: str | None) -> str:
    """What the sources say, for deciding the document's language.

    This decision used to read the summary table above instead — and that table
    is mostly this pipeline's own English: evidence ids, the words quantitative
    and qualitative, "allowed:[factual, statistical]", the column rules. On a
    Chinese lab report whose evidence is measurements, the scaffolding
    contributed 953 Latin characters against the content's 120, so the ratio
    came out 0.14 and the brief told the agent to write an English document.
    Measured on the content alone the same ledger is 0.56, which is Chinese.

    Every entry is read, not the first twenty the table shows, because which
    source happens to be attached first is not a fact about the document.
    """
    if not path or not Path(path).exists():
        return ""
    parts: list[str] = []
    with open(path, encoding="utf-8") as handle:
        for line in handle:
            if not line.strip():
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(entry, dict) or "_contract" in entry:
                continue
            parts.append(str(entry.get("content") or entry.get("quote") or ""))
    return "\n".join(parts)


def _read_figure_recommendation_summary(path: str | None, limit: int = 8) -> str:
    if not path or not Path(path).exists():
        return "(no figure recommendations generated)"
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        return f"(figure recommendation report could not be read: {exc})"
    recommendations = payload.get("recommendations", []) if isinstance(payload, dict) else []
    if not recommendations:
        return "(no table-shaped evidence required chart recommendations)"
    rows = []
    for rec in recommendations[:limit]:
        if not isinstance(rec, dict):
            continue
        candidates = rec.get("chart_candidates", []) or []
        candidate_summary = ",".join(
            f"{item.get('figure_type', '?')}:{item.get('score', '?')}"
            for item in candidates[:3]
            if isinstance(item, dict)
        ) or rec.get("recommended_figure_type", "?")
        warnings = "; ".join(rec.get("selection_warnings", []) or [])
        transform = rec.get("data_transform", {}) if isinstance(rec.get("data_transform", {}), dict) else {}
        operations = transform.get("operations", []) or []
        transform_summary = (
            f"{transform.get('status', 'source')}:{','.join(str(item) for item in operations)}"
            if operations else str(transform.get("status", "source"))
        )
        rows.append(
            (
                "  {rid} | recommended:{rtype} | candidates:{candidates} | acceptable:{acceptable} | "
                "confidence:{confidence} | transform:{transform} | evidence:{evidence} | warnings:{warnings} | {reason}"
            ).format(
                rid=rec.get("recommendation_id", "?"),
                rtype=rec.get("recommended_figure_type", "?"),
                candidates=candidate_summary,
                acceptable=",".join(rec.get("acceptable_figure_types", []) or []),
                confidence=rec.get("confidence", "?"),
                transform=transform_summary,
                evidence=",".join(rec.get("evidence_ids", []) or []),
                warnings=warnings[:120] if warnings else "none",
                reason=(rec.get("reason", "") or "")[:120],
            )
        )
    header = f"Total figure recommendations: {len(recommendations)} (showing first {min(len(recommendations), limit)})\n"
    header += "  recommendation_id | recommended_type | candidates | acceptable_types | confidence | transform | evidence_ids | warnings | reason\n"
    header += "  " + "-" * 100 + "\n"
    return header + "\n".join(rows)


def _figure_plan_is_valid(plan: object) -> bool:
    """Shared validity check so the starter plan and the brief's usage map
    number the same entries identically."""
    return (
        isinstance(plan, dict)
        and bool(plan.get("figure_id"))
        and bool(plan.get("figure_type"))
        and isinstance(plan.get("data"), dict)
    )


def _read_recommended_figure_usage_map(path: str | None, limit: int = 8) -> str:
    if not path or not Path(path).exists():
        return "(no recommended figure usage map available)"
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception as exc:
        return f"(recommended figure usage map could not be read: {exc})"
    recommendations = payload.get("recommendations", []) if isinstance(payload, dict) else []
    rows = []
    display_number = 0
    for rec in recommendations:
        if len(rows) >= limit:
            break
        if not isinstance(rec, dict):
            continue
        plan = rec.get("figure_plan", {})
        if not _figure_plan_is_valid(plan):
            continue
        # The starter figure plan renumbers figures 1..N in this same order,
        # so the brief must reference the renumbered ids, not figrec_N.
        display_number += 1
        figure_id = str(display_number)
        section_id = plan.get("section_id") or rec.get("section_id") or "results"
        evidence_ids = plan.get("source_evidence_ids") or rec.get("evidence_ids") or []
        if not isinstance(evidence_ids, list):
            evidence_ids = []
        recommended_type = rec.get("recommended_figure_type") or plan.get("figure_type") or "?"
        transform = rec.get("data_transform", {}) if isinstance(rec.get("data_transform", {}), dict) else {}
        operations = transform.get("operations", []) or []
        transform_note = (
            f"; use the deterministic transformed view `{', '.join(str(item) for item in operations)}`"
            if transform.get("status") == "transformed" and operations else ""
        )
        rows.append(
            (
                "- `{figure_id}` -> outline `sections.{section_id}.figure_ids`; "
                "draft `{section_id}.md`; place `[FIGURE:{figure_id}]` at the first paragraph "
                "that discusses evidence `{evidence}`; recommended chart `{recommended_type}`{transform_note}."
            ).format(
                figure_id=figure_id,
                section_id=section_id,
                evidence=", ".join(str(item) for item in evidence_ids) or "unknown",
                recommended_type=recommended_type,
                transform_note=transform_note,
            )
        )
    if not rows:
        return "(no recommendation entries contained usable figure_plan guidance)"
    header = "Recommended figure usage map:\n"
    return header + "\n".join(rows)


def _recommended_figure_plans(path: str | None) -> tuple[list[dict], str]:
    if not path or not Path(path).exists():
        return [], "skipped_no_recommendations"
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except Exception:
        return [], "skipped_unreadable_recommendations"
    recommendations = payload.get("recommendations", []) if isinstance(payload, dict) else []
    figures: list[dict] = []
    for recommendation in recommendations:
        if not isinstance(recommendation, dict):
            continue
        plan = recommendation.get("figure_plan")
        if not _figure_plan_is_valid(plan):
            continue
        figures.append(dict(plan))
    if not figures:
        return [], "skipped_no_valid_figure_plans"
    # Publication figure ids are 1..N; figrec_N stays in recommendation_id as
    # the audit link. Shipping figrec ids in the starter plan forced every
    # authoring pass to renumber by hand (and leaked "figrec_1" into captions
    # when it didn't).
    for number, plan in enumerate(figures, start=1):
        plan["figure_id"] = str(number)
    return figures, "ready"


def _write_auto_figure_plan(state: ReportState, recommendations_path: str | None) -> dict:
    run_dir = run_dir_for(state)
    plan_path = run_dir / "section_drafts" / "figure_plan.json"
    if plan_path.exists():
        info = {
            "status": "preserved_existing",
            "path": str(plan_path),
            "generated_figure_count": 0,
        }
        state.runtime["auto_figure_plan"] = info
        return info

    figures, status = _recommended_figure_plans(recommendations_path)
    if not figures:
        info = {
            "status": status,
            "path": str(plan_path),
            "generated_figure_count": 0,
        }
        state.runtime["auto_figure_plan"] = info
        return info

    plan_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated_by": "report_workflow.nodes.agent_tasks.auto_figure_plan",
        "source_recommendations_path": str(recommendations_path or ""),
        "generated_figure_count": len(figures),
        "figures": figures,
    }
    plan_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    info = {
        "status": "generated",
        "path": str(plan_path),
        "generated_figure_count": len(figures),
    }
    state.output["auto_figure_plan_path"] = str(plan_path)
    state.plan["auto_figure_plan_count"] = len(figures)
    state.runtime["auto_figure_plan"] = info
    return info


def _auto_figure_plan_guidance(info: dict) -> str:
    status = info.get("status")
    path = info.get("path", "")
    count = info.get("generated_figure_count", 0)
    if status == "generated":
        return (
            f"A starter figure plan has been generated at `{path}` with {count} recommended figure(s). "
            "You may adopt, edit, or delete it. It does not automatically insert figures into outline.json "
            "or section drafts; reference figures only where they fit the report narrative. "
            "If a figure includes data_transform metadata, keep that block unless you replace it with a specific "
            "chart_selection_reason for the manual derived view."
        )
    if status == "preserved_existing":
        return (
            f"An existing figure plan was found at `{path}` and was preserved unchanged. "
            "Review it against the deterministic recommendations before validation."
        )
    if status == "skipped_unreadable_recommendations":
        return "No starter figure plan was generated because the recommendation report could not be read."
    if status == "skipped_no_valid_figure_plans":
        return "No starter figure plan was generated because the recommendation report had no valid figure_plan entries."
    return "No starter figure plan was generated because there are no figure recommendations for this run."


READER_RUBRICS: dict[str, tuple[str, list[str]]] = {
    "engineering_lab_report": ("the course professor", [
        "Quantified comparison beats description: report the measured slope versus the theoretical slope, the fit quality (R²), and the error range against the acceptance threshold — not just 'close to theory'.",
        "The discussion explains mechanisms: why the measurements deviate, which error source dominates and roughly how much it contributes. Restating the numbers is not a discussion.",
        "Every figure and table earns its place: referenced from the prose, with the finding stated next to it.",
        "The conclusion answers the stated objective with numbers, and says whether the acceptance criteria were met.",
    ]),
    "academic_paper": ("a peer reviewer", [
        "The contribution is stated in one sentence, early; the reader should never wonder what is new.",
        "Claims are sized to the evidence; limitations are stated plainly instead of being discovered by the reviewer.",
        "The method section is reproducible from the text alone — parameters, data, and decision rules included.",
        "Results are quantified with their uncertainty; adjectives are not results.",
    ]),
    "proposal": ("the decision-maker", [
        "The ask, the cost, and the payoff are on the first page.",
        "Every number ties to a decision the reader must make; decoration numbers waste their time.",
        "Risks are listed with mitigations, honestly — a proposal with no risks reads as unexamined.",
        "The timeline is concrete enough to be held accountable to.",
    ]),
    "business_report": ("your manager", [
        "Conclusion first, supporting detail after; the reader decides in the first half page whether to keep reading.",
        "Each metric leads somewhere: a decision, an action, or an explicitly flagged risk.",
        "Next steps are explicit — owned and dated, not implied.",
    ]),
    "admissions_report": ("the admissions committee", [
        "Specific incidents beat adjectives: one concrete decision with its outcome outweighs a paragraph of self-description.",
        "Motivation, preparation, and goal read as one arc — each section sets up the next.",
        "Numbers anchor credibility: scores, scale, results, dates.",
    ]),
    "admissions_project_report": ("the admissions committee", [
        "The project reads problem → method → result → reflection, complete with numbers at each step.",
        "Design decisions are justified: what was chosen, what was rejected, and why.",
        "The reflection states what would be done differently — that is where maturity shows.",
    ]),
    "custom": ("the intended reader", [
        "Lead with the point; one idea per paragraph, each advancing the argument.",
        "Figures and tables are self-explanatory; the prose states the finding, not the mechanics.",
        "The ending tells the reader what to take away or do next.",
    ]),
}


def _reader_rubric_section(report_profile: str) -> str:
    """The 'what does a high grade look like' brief section.

    Traceability is the entry ticket; this is the part that aims the writing
    at a document the reader actually rates highly.
    """
    audience, bullets = READER_RUBRICS.get(report_profile) or READER_RUBRICS["custom"]
    lines = "\n".join(f"- {b}" for b in bullets)
    return (
        "## How the Reader Grades This\n\n"
        f"Traceable-to-evidence is the entry ticket, not the goal. The goal is a\n"
        f"document {audience} rates highly. Write toward these criteria, in the\n"
        "document's language:\n\n"
        f"{lines}\n\n"
    )


# Structure guidance distilled from published writing standards:
# - Kording & Mensh, "Ten simple rules for structuring papers",
#   PLOS Comput Biol 2017 (C-C-C at paper/abstract/paragraph scale)
# - Whitesides, "Whitesides' Group: Writing a Paper", Adv. Mater. 2004
#   (figures carry the results; prose explains them)
# - Minto, The Pyramid Principle (answer first; SCQA opening)
# - University lab-report rubrics (ASEE, WSU, NC State LabWrite):
#   discussion = result → quantitative comparison → mechanism → verdict
# - Graduate-admissions guidance (MIT EECS CommLab, Cornell Graduate
#   School): depth on 2-4 defining experiences over exhaustive listing
_STRUCTURE_RECIPES: dict[str, str] = {
    "engineering_lab_report": (
        "Discussion recipe (university lab rubrics): for each key result —\n"
        "state it, compare it quantitatively with theory (use the derived\n"
        "statistics), explain the mechanism behind the deviation, and give\n"
        "the verdict against the acceptance threshold. Close the discussion\n"
        "by saying whether the data support the model."
    ),
    "academic_paper": (
        "One paper, one central contribution (Kording & Mensh). Figures\n"
        "carry the results and prose explains them (Whitesides): build each\n"
        "results paragraph around its figure or table — state what it shows,\n"
        "then what it means."
    ),
    "proposal": (
        "Answer first (Minto's Pyramid Principle): the recommendation leads,\n"
        "then the two or three supports, then the evidence. Open the\n"
        "executive summary as SCQA — situation, complication, the question\n"
        "it raises, and your answer."
    ),
    "business_report": (
        "Answer first (Minto's Pyramid Principle): the conclusion leads,\n"
        "then the two or three supports, then the evidence. Open with\n"
        "SCQA — situation, complication, the question it raises, and your\n"
        "answer."
    ),
    "admissions_report": (
        "Depth over coverage (MIT EECS CommLab, Cornell): develop two to\n"
        "four defining experiences fully — situation, what you did, the\n"
        "result, and what it changed in you — instead of listing everything."
    ),
    "admissions_project_report": (
        "Depth over coverage (MIT EECS CommLab, Cornell): develop the\n"
        "project's defining decisions fully — the situation, the choice, the\n"
        "result, and what it taught you — instead of listing every task."
    ),
}


def _claim_role_rule(report_profile: str) -> str:
    """State the claim_role requirement for this run, not for a profile family.

    The brief said "**Academic reports**: every claim MUST have claim_role",
    but the gate fires on the run's own policy, and four profiles enforce it --
    engineering_lab_report, academic_paper, admissions_report, custom -- only
    one of which is an academic paper. An agent writing a lab report reads a
    rule addressed to somebody else, leaves the field out, and is hard-blocked
    at CLAIM_PLAN. The three profiles that do not enforce it were being told to
    obey a rule that never fires.
    """
    if get_policy(report_profile).claim.role_validation_required:
        return (
            f"- `claim_role` is required for `{report_profile}`: every claim must carry "
            "`primary`, `supporting`, or `background`.\n"
            "  - `primary`: core contribution claims, each directly supporting the thesis. "
            "At least 1, at most 3.\n"
            "  - `supporting`: evidence that backs a primary claim.\n"
            "  - `background`: context or prior work not central to the contribution."
        )
    return (
        f"- `claim_role` is optional for `{report_profile}`. Set it if it helps you keep "
        "the argument straight; nothing validates it for this profile."
    )


_RESULTS_MODE_PATH = "`outline.json` -> `sections.results.results_mode`"


_ABSTRACT_STRUCTURED = """```markdown
# Abstract

**Background:** [2-3 sentences on the problem context]

**Objective:** [1-2 sentences on the specific aim]

**Methods:** [3-5 sentences on what was done, past tense]

**Principal Findings:** [3-5 sentences on key results, including numbers when supported]

**Significance:** [1-2 sentences on why this matters]
```"""

_ABSTRACT_PLAIN = """```markdown
# Abstract

[Single continuous paragraph. No sub-headings. Covers background, objective,
methods, key findings, and significance in a flowing narrative.]
```"""


def _abstract_section(report_profile: str, blueprint: dict, document_language: str) -> str:
    """Give this run's abstract contract, not a lecture with carve-outs.

    The block named one profile that must use structured headings and one
    family that may use a paragraph, then stated "150-250 words" for everyone.
    Two profiles have no abstract section at all and were still told how to
    write one, including which gate would block it. Of the five that do, the
    word range was wrong for three, and two of them were never told which
    format they may use.
    """
    from .abstract_check import CJK_ABSTRACT_SCALE

    if "abstract" not in (blueprint.get("sections") or {}):
        return (
            "## Abstract\n\n"
            f"`{report_profile}` has no abstract section. Do not write one; "
            "the blueprint's section list is the whole document."
        )

    policy = get_policy(report_profile).abstract
    scale = CJK_ABSTRACT_SCALE if document_language == "zh" else 1
    unit = "characters" if document_language == "zh" else "words"
    low, high = policy.word_count_min * scale, policy.word_count_max * scale
    budget = f"at most {high} {unit}" if not low else f"{low}-{high} {unit}"

    if policy.structure_required:
        shape = (
            f"`{report_profile}` requires the structured headings below, exactly. "
            "A plain-paragraph abstract hard-blocks at METADATA_GATE.\n\n"
            f"{_ABSTRACT_STRUCTURED}"
        )
    elif policy.allow_plain_paragraph:
        shape = (
            f"`{report_profile}` accepts either shape. A plain paragraph is the "
            f"usual choice:\n\n{_ABSTRACT_PLAIN}\n\n"
            f"Structured headings are also accepted:\n\n{_ABSTRACT_STRUCTURED}"
        )
    else:
        shape = (
            f"`{report_profile}` expects the structured headings below.\n\n"
            f"{_ABSTRACT_STRUCTURED}"
        )

    return (
        f"## Abstract ({budget})\n\n"
        f"{shape}\n\n"
        f"**Length: {budget}**, counted after removing `[CITE:]` markers.\n"
        "**No trailing ellipses (`.....`), no incomplete sentences.**\n"
        "**No `[CITE:]`, `[Source:]`, or `[graphify:]` markers in the abstract.**\n"
        "The abstract still needs `claim_ids` in `outline.json`: it declares which "
        "claims it summarizes, and PLAN_LOCK hard-blocks an abstract whose "
        "`claim_ids` list is empty."
    )


def _results_mode_section(report_profile: str) -> str:
    """Describe results_mode where the workflow actually reads it.

    The brief said "include it in outline.json at the top level" and showed it
    there in the JSON shape. QA_GATE reads
    outline["sections"]["results"]["results_mode"], falling back to the
    blueprint. Measured: an outline carrying a top-level
    architectural_characterization behaves exactly like one that sets nothing,
    so an agent following the brief lost the setting without being told.
    """
    if not get_policy(report_profile).results.empirical_strict:
        return (
            "## results_mode\n\n"
            f"Not used by `{report_profile}`. If you set it anyway, it belongs in "
            f"{_RESULTS_MODE_PATH}."
        )
    return (
        f"## results_mode Selection (required for `{report_profile}`)\n\n"
        f"**Choose ONE and set it at {_RESULTS_MODE_PATH}.** That is where the "
        "workflow reads it; a `results_mode` at the top level of outline.json is "
        "read by nothing and the run falls back to the blueprint default.\n\n"
        "- `empirical`: Select when your evidence contains measured/quantitative data "
        "(numbers, percentages, performance metrics). Results section presents actual "
        "findings with statistical support.\n\n"
        "- `architectural_characterization`: Select when your evidence is "
        "structural/code analysis (graphs, dependency trees, module relationships, "
        "system descriptions). Results section characterizes architecture without "
        "claiming empirical performance superiority.\n\n"
        "**Do NOT mix modes**: If your evidence has both quantitative data AND "
        "architectural descriptions, pick the dominant mode based on what your claims "
        "actually argue."
    )


def _results_mode_rule(report_profile: str) -> str:
    if not get_policy(report_profile).results.empirical_strict:
        return f"- `results_mode` is not read for `{report_profile}`; leave it out."
    return (
        f"- Set `results_mode` at {_RESULTS_MODE_PATH}, not at the top level of the file."
    )


def _structure_guidance(report_profile: str) -> str:
    """Writing-structure discipline distilled from published standards."""
    paragraph_rule = (
        "Paragraph rule (Kording & Mensh, PLOS Comput Biol 2017): every\n"
        "paragraph is Context → Content → Conclusion. The first sentence\n"
        "states what the paragraph is about; the last states what the reader\n"
        "should remember. A run of parallel evidence sentences with no\n"
        "concluding sentence reads as a list, not an argument."
    )
    recipe = _STRUCTURE_RECIPES.get(report_profile, "")
    body = paragraph_rule if not recipe else f"{paragraph_rule}\n\n{recipe}"
    return f"## Structure Discipline (from published writing standards)\n\n{body}\n\n"


def _derived_stats_guidance(evidence_path: str) -> str:
    """List pre-computed derived statistics so the analysis can cite them."""
    if not evidence_path or not Path(evidence_path).exists():
        return ""
    lines: list[str] = []
    try:
        with open(evidence_path, encoding="utf-8") as f:
            for raw in f:
                try:
                    unit = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if isinstance(unit, dict) and unit.get("derivation"):
                    lines.append(f"- `{unit.get('evidence_id', '')}` — {unit.get('content', '')}")
    except OSError:
        return ""
    if not lines:
        return ""
    return (
        "## Derived Statistics (citable)\n\n"
        "The pipeline pre-computed these from the measurement data; they are\n"
        "regular evidence entries. Use them to make the analysis quantitative —\n"
        "slope versus theory, fit quality, error range — instead of leaving the\n"
        "discussion qualitative. Cite them like any other evidence id.\n\n"
        + "\n".join(lines)
        + "\n\n"
    )


def write_agent_task_briefs(state: ReportState) -> ReportState:
    """Write all task briefs required for the external agent authoring phase.

    For 'revise_existing', also writes 04_revision_plan.md.
    """
    tasks_dir = agent_tasks_dir(state)
    run_dir = run_dir_for(state)
    evidence_path = state.sources.get("evidence_ledger_path", "")
    evidence_summary = _read_jsonl_compact_summary(evidence_path)
    figure_recommendations_path = state.output.get("figure_recommendations_path", "")
    figure_recommendation_summary = _read_figure_recommendation_summary(figure_recommendations_path)
    recommended_figure_usage_map = _read_recommended_figure_usage_map(figure_recommendations_path)
    auto_figure_plan = _write_auto_figure_plan(state, figure_recommendations_path)
    auto_figure_plan_guidance = _auto_figure_plan_guidance(auto_figure_plan)
    reader_rubric = _reader_rubric_section(state.spec.get("report_profile", ""))
    structure_guidance = _structure_guidance(state.spec.get("report_profile", ""))
    claim_role_rule = _claim_role_rule(state.spec.get("report_profile", ""))
    results_mode_section = _results_mode_section(state.spec.get("report_profile", ""))
    results_mode_rule = _results_mode_rule(state.spec.get("report_profile", ""))
    derived_stats_guidance = _derived_stats_guidance(evidence_path)
    task_intent = state.spec.get("task_intent", "new_draft")
    contract = make_artifact_contract(state)
    contract_json = json.dumps(contract, indent=2)

    # Chinese-dominant evidence means a Chinese deliverable: tell the agent up
    # front, and show the canonical Chinese headings the pipeline will render
    # so the draft and the final document agree on language.
    document_language = detect_document_language(_evidence_text_for_language(evidence_path))
    abstract_section = _abstract_section(
        state.spec.get("report_profile", ""),
        state.plan.get("blueprint") or {},
        document_language,
    )
    language_guidance = ""
    if document_language == "zh":
        blueprint_sections = (state.plan.get("blueprint") or {}).get("sections", {}) or {}
        heading_lines = "\n".join(
            f"- `{sid}` → {localized_section_title(section, sid, 'zh')}"
            for sid, section in blueprint_sections.items()
        )
        language_guidance = f"""## Document Language

The source evidence is Chinese-dominant, so this is a Chinese document:
write all section prose in Chinese. The pipeline renders section headings
with the blueprint's Chinese titles automatically:

{heading_lines}

Do not mix English boilerplate sentences into the Chinese body text.
(Structural markers like `[CITE:...]` and `[FIGURE:...]` stay as-is.)

"""

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
  reserve `measured` wording for high-grade evidence (FD blocks it on
  medium-grade evidence even when that evidence is quantitative).
{claim_role_rule}

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
- Figure recommendations: `{figure_recommendations_path}`

## Required Output
Write `{run_dir / "outline.json"}` with this shape:

```json
{{
  "_contract": {contract_json},
  "paper_spine": {{
    "problem": "For academic_paper: the concrete problem or phenomenon.",
    "gap": "What prior work, current practice, or the source material leaves unresolved.",
    "objective": "The specific aim of this paper.",
    "contribution": "The main contribution the report can support with evidence.",
    "method_basis": "The reproducible method or analysis basis.",
    "main_limitation": "The main limitation that should temper the claim."
  }},
  "lab_spine": {{
    "experiment_purpose": "For engineering_lab_report: what the experiment is meant to determine.",
    "variables": "Independent/dependent/control variables and units.",
    "apparatus_procedure_basis": "Which apparatus and procedure support the measurements.",
    "measurement_basis": "Where measured/calculated values come from.",
    "uncertainty_limitations": "Known uncertainty, assumptions, or measurement limits."
  }},
  "sections": {{
    "results": {{
      "section_id": "results",
      "results_mode": "empirical" | "architectural_characterization",
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

{results_mode_section}

## Figure Recommendation Summary
Use this deterministic chart-selection guidance when deciding `figure_ids` and figure plans:

```
{figure_recommendation_summary}
```

## Starter Figure Plan
{auto_figure_plan_guidance}

## Recommended Figure Usage Map
{recommended_figure_usage_map}

## Hard Rules
- Assign every claim to at least one non-reference/non-appendix section.
- Use only section IDs defined by the blueprint.
- Use only claim IDs from `claim_matrix.json`.
{results_mode_rule}
- If `report_profile=academic_paper`, fill `paper_spine`; do not leave it as template text.
- If `report_profile=engineering_lab_report`, fill `lab_spine`; do not leave it as template text.
- The outline should create a real argument path: problem/gap/objective before methods, results before interpretation, and limitations before conclusion.
"""

    section_task = f"""# 03 Section Draft

## Inputs
- Blueprint: `{run_dir / "blueprint.json"}`
- Claim matrix: `{run_dir / "claim_matrix.json"}`
- Outline: `{run_dir / "outline.json"}`
- Evidence ledger: `{evidence_path}`
- Figure recommendations: `{figure_recommendations_path}`

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
- Use `wording_strength="hedged"` unless the linked evidence is high-grade.
  FD hard-blocks `measured` on medium-grade evidence, quantitative or not.
- Write one Markdown file for each required blueprint section, plus any optional section included in `outline.json`.
- **Publication text forbidden patterns** (hard blocks in the pipeline):
  - `[Source:]`, `[graphify:]`, `[Note:]`, or any internal workflow marker.
  - Evidence IDs, `.py` filenames, or internal workspace paths (e.g. `output/...`) in body text.
  - Any table containing "audit", "evidence", or "claim" in the header; these are internal artifacts.
  - **Write real content; do not use placeholder names** like `[Author Name]`, `[University]`, `[email@domain.com]`.

{abstract_section}

Only `cover`, `references`, and `appendix` may carry an empty `claim_ids` list
in `outline.json` — they hold front matter, sources, and raw material, not
assertions. A required `cover` section is still required in `outline.json`; it
just carries an empty `claim_ids` list.

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

{language_guidance}{reader_rubric}{structure_guidance}{derived_stats_guidance}## Prose Quality (applies to every profile)

The gates check grounding; they do not fix machine-sounding prose. These rules
keep the rendered document reading like it was written by a person:

1. **Translate data identifiers into plain language.** Column and field names
   are source metadata, not prose. Write "median processing time
   (12.4 minutes)", never `median_processing_minutes`; "the structured
   workflow condition", never `structured_workflow`. Snake_case or camelCase
   tokens in body text, headings, or captions are a defect.
2. **State the grounded numbers.** When evidence contains the value, write the
   value: "the error rate fell from 9.0% to 3.5%", not "the error rate was
   lower". A quantitative section with no numbers reads as evasive even when
   every claim is verified. Reuse the evidence's own figures and units so the
   content checks pass untouched.
3. **No internal identifiers in publication text.** Recommendation ids
   (`figrec_1`), evidence ids (`E001`), artifact filenames
   (`chart_source.csv`, `outline.json`), and run/job ids must never appear in
   body text or captions. Refer to figures as "Figure 1", to data by its
   real-world name ("the intake-time measurements").
4. **Captions describe the finding, not the mechanics.** "Figure 1: Median
   processing time per note, manual baseline vs structured workflow (minutes)"
   — not "Figure 1: Bar view of chart_source". A caption should tell the
   reader what is plotted, its units, and what comparison to see.
5. **Vary sentence openings; never repeat a template sentence.** If several
   figures or results need introducing, write a different lead-in for each,
   anchored to what that specific figure shows. Repeating one mechanical
   sentence with a swapped noun is an immediate machine-writing tell.

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
Strong scholarly methods prose should identify the data/source basis, procedure,
analysis parameters or software/instrument settings when applicable, and any
exclusions, transformations, calibration, or filtering that affects results.

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
Captions must be self-contained: a reader should understand what is plotted,
the data basis, units or value scale, and what the visual comparison means
without reading the surrounding paragraph first.

{auto_figure_plan_guidance}

If `{figure_recommendations_path}` contains recommendations, use them to avoid one-size-fits-all chart choices:
- Use the recommendation's `recommended_figure_type` unless you have a specific reason to choose an acceptable alternative.
- If the starter figure includes `data_transform`, preserve that metadata and chart data. Do not manually recompute group-by, pivot, wide-to-long, percent-of-total, sort, or top-N values unless you also explain the replacement in `chart_selection_reason`.
- Do not default all numeric data to line charts. Line charts are for ordered time/step trends.
- Composition/share data should normally use `pie` for a small whole-part split or `stacked_bar` for multi-series category breakdowns.
- Category/value comparisons should use `bar`.
- Two numeric variables should use `scatter`.
- One numeric distribution with enough observations should use `histogram`.
- Repeated numeric measurements by group should use `boxplot`.
- Matrix-shaped numeric evidence should use `heatmap`.
- Central values with SD/SE/CI/error columns should use `error_bar`.
- Exact measurement/calculation values should stay as a table.
- Error-bar charts must state what the bars mean (SD, SE, CI, or measurement uncertainty).
- Dense category labels, unclear units, or mixed units on one axis should be resolved before submission.

{recommended_figure_usage_map}

For every figure you keep from that map, put its ID in the named outline
`figure_ids` array and place the exact `[FIGURE:<figure_id>]` marker at the
first body paragraph that discusses the listed evidence. If a recommended
figure does not fit the narrative, remove it from `figure_plan.json` rather
than leaving an unused planned chart.

When you create `{run_dir / "section_drafts" / "figure_plan.json"}`, each generated chart should include:

```json
{{
  "figure_id": "1",
  "figure_type": "{SUPPORTED_FIGURE_TYPES_TEXT}",
  "recommendation_id": "figrec_1",
  "source_evidence_ids": ["evidence id(s) used for the chart"],
  "chart_selection_reason": "Why this chart type fits the evidence.",
  "title": "Publication-safe chart title",
  "section_id": "results"
}}
```

`FIGURE_PLAN_AUDIT` checks these fields. A high-confidence recommendation that is replaced with a mismatched chart type without `chart_selection_reason` can hard-block validation for strict figure-contract profiles.

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
    Pipeline-->>Agent: job_id + controlled next action
    Agent->>Pipeline: get_controlled_next_action()
    Agent->>Pipeline: submit_controlled_action()
    Agent->>Pipeline: submit_and_publish_report()
    Pipeline-->>Agent: rendered_report.docx
```
````

**FORBIDDEN:** Do NOT use ASCII art or box-drawing character diagrams.
These render poorly in DOCX and will be **hard-blocked** by the pre-render sanity gate.

## Project Identity

For academic `new_draft`, if `{run_dir / "project_identity_candidate.json"}` exists,
use it as read-only drafting context to keep the thesis from drifting into a
topic-adjacent report. Do not write `project_identity.json` during controlled
authoring; pass an explicit `project_identity` to `start_report_task` when a
fixed identity contract is required.
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
      "change_type": "replace|insert|delete|retitle|remove_section",
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
- `insert`: insert `new_text` after `original_text` (or at the end of the section if `original_text` is empty)
- `delete`: remove `original_text` from the section
- `retitle`: rename the section's heading to `new_text` (no `original_text` needed)
- `remove_section`: drop the whole section, heading included (no `original_text` needed)

## Editorial Changes (no claim linkage)

A change that only rewords, fixes punctuation, or retitles — without stating
any new fact — may set `"editorial": true` and omit `claim_ids`/`evidence_ids`.
A deterministic guard enforces the boundary: an editorial `new_text` may not
introduce numbers or quoted spans that the text it replaces did not already
contain; if it does, the plan hard-blocks and the change must be claim-linked
instead. `retitle` and `remove_section` are structural: they need no claims
either way and are recorded explicitly in the revision diff report.

## Hard Rules
- Every `replace`/`insert`/`delete` must link at least one `claim_id` and
  `evidence_id`, unless it is marked `"editorial": true` (wording-only).
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
5. Call `get_controlled_next_action` and complete whatever it still asks for.
6. Once nothing is outstanding, call `submit_and_publish_report(job_id="...")`.

A validated revision plan is not a publishable job. `revise_existing` requires
the same `claim_matrix.json`, `outline.json`, `section_drafts/*.md`, and
`sentence_map.jsonl` as a new draft; the plan is an additional artifact, not a
replacement for them.

`revision_plan.json` is the only surface that changes the **published text** —
the merged draft is built from the base document with your changes applied, so
section drafts are validated but do not become body content. Anything that must
appear in the revised document, a `[FIGURE:<id>]` placeholder included, belongs
in a change's `new_text`.

Do not edit `base_document_sections.json`, checkpoint files, or rendered markdown
artifacts directly.

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


def missing_agent_artifacts(state, fallback: str = "") -> list[str]:
    """Every artifact this run still needs, in the order the briefs ask for them.

    The blocking nodes each called write_agent_task_briefs — which computes the
    whole list one line above — and then overwrote it with the single path that
    happened to trip first. A run with four artifacts outstanding reported one,
    the author supplied it, ran again, and was told about the next: four round
    trips to learn four things that were all known at the first.

    It also degraded `status`, whose whole job is to say where the run is: after
    one failed validate it listed one requirement where it had listed four,
    because the exception's list was written back over the full one.
    """
    from pathlib import Path as _Path

    required = state.runtime.get("required_agent_artifacts") or []
    missing = [item for item in required if not _Path(item).exists()]
    if missing:
        return missing
    return [fallback] if fallback else []


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
