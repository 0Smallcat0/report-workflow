"""OUTLINE_PLAN node - load and validate agent-produced outline.json."""
import json
from pathlib import Path

from ..derived_evidence import built_table_entries
from ..errors import AgentWorkRequired, QAHardBlockError
from ..prompt_questions import extract_questions
from ..runtime_support import run_dir_for, write_json_artifact
from ..state import ReportState
from ..artifact_contract import make_artifact_contract, validate_artifact_contract, write_artifact_contract
from .agent_tasks import missing_agent_artifacts, write_agent_task_briefs
from .section_contract import validate_required_outline_sections


def _outline_path(state: ReportState) -> Path:
    return run_dir_for(state) / "outline.json"


def _load_outline(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            payload = json.load(f)
    except json.JSONDecodeError as exc:
        raise QAHardBlockError(f"Malformed outline.json: {exc}") from exc
    if not isinstance(payload, dict):
        raise QAHardBlockError("outline.json must contain a JSON object")
    return payload


def _hoist_subsections(section_id: str, section: dict) -> None:
    """Fold a section's declared subsections into its own claim and figure lists.

    A report covering four independent topics — four product categories, four
    sites, four quarters — had one ``findings`` section to put them in, so the
    per-topic structure existed only inside the prose and no gate could see
    which claims belonged to which topic. Declaring subsections lets the
    outline say it. Everything downstream keeps reading ``claim_ids`` and
    ``figure_ids``, so the ids are hoisted here and the declaration is kept
    for the drafting brief and the rendered headings.
    """
    subsections = section.get("subsections")
    if subsections is None:
        return
    if not isinstance(subsections, list):
        raise QAHardBlockError(
            f"Outline section {section_id} subsections must be a list of objects"
        )

    claim_ids = list(section.get("claim_ids", []) or [])
    figure_ids = list(section.get("figure_ids", []) or [])
    seen_ids: set[str] = set()
    for index, subsection in enumerate(subsections):
        if not isinstance(subsection, dict):
            raise QAHardBlockError(
                f"Outline section {section_id} subsections[{index}] must be an object"
            )
        subsection_id = str(subsection.get("subsection_id") or "").strip()
        if not subsection_id:
            raise QAHardBlockError(
                f"Outline section {section_id} subsections[{index}] needs a subsection_id"
            )
        if subsection_id in seen_ids:
            raise QAHardBlockError(
                f"Outline section {section_id} repeats subsection_id {subsection_id!r}"
            )
        seen_ids.add(subsection_id)
        if not str(subsection.get("title") or "").strip():
            raise QAHardBlockError(
                f"Outline section {section_id} subsection {subsection_id!r} needs a title; "
                "it becomes the heading in the rendered document."
            )
        for key, collected in (("claim_ids", claim_ids), ("figure_ids", figure_ids)):
            values = subsection.get(key, []) or []
            if not isinstance(values, list):
                raise QAHardBlockError(
                    f"Outline section {section_id} subsection {subsection_id!r} {key} must be a list"
                )
            for value in values:
                if value not in collected:
                    collected.append(value)

    section["claim_ids"] = claim_ids
    if figure_ids:
        section["figure_ids"] = figure_ids


def _planned_figure_ids(state: ReportState) -> list[str] | None:
    """Figure ids declared in figure_plan.json, or None when there is no plan."""
    path = run_dir_for(state) / "section_drafts" / "figure_plan.json"
    if not path.exists():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise QAHardBlockError(f"Malformed section_drafts/figure_plan.json: {exc}") from exc
    if not isinstance(payload, dict):
        return None
    figures = payload.get("figures")
    if not isinstance(figures, list):
        return None
    return [
        str(figure.get("figure_id")).strip()
        for figure in figures
        if isinstance(figure, dict) and str(figure.get("figure_id") or "").strip()
    ]


def _validate_figure_plan_against_outline(state: ReportState, sections: dict) -> None:
    """Refuse an outline that disagrees with figure_plan.json.

    This used to surface only at POST_RENDER_VALIDATE — "expected 4 Word
    table(s), found 1" — which is after the DOCX has been rendered and the
    work of rendering it has been spent. The disagreement is visible here,
    before a single figure is built, and here it can name the entries.
    """
    planned = _planned_figure_ids(state)
    if planned is None:
        return

    used: list[str] = []
    for section in sections.values():
        if not isinstance(section, dict):
            continue
        for figure_id in section.get("figure_ids", []) or []:
            figure_id = str(figure_id).strip()
            if figure_id and figure_id not in used:
                used.append(figure_id)

    unused = [figure_id for figure_id in planned if figure_id not in used]
    dangling = [figure_id for figure_id in used if figure_id not in planned]

    problems: list[str] = []
    if unused:
        problems.append(
            "figure_plan.json plans figures no outline section uses: "
            + ", ".join(unused)
            + ". Delete those entries from section_drafts/figure_plan.json, or add each "
            "id to the figure_ids of the section that discusses it."
        )
    if dangling:
        problems.append(
            "outline figure_ids name figures that figure_plan.json does not define: "
            + ", ".join(dangling)
            + ". Add each one to section_drafts/figure_plan.json, or remove the id from "
            "the section's figure_ids."
        )
    if problems:
        raise QAHardBlockError("OUTLINE_PLAN: " + " ".join(problems))


#: How much an author has to write to drop a table the pipeline already built.
#: Long enough to be a reason ("the price axis is already carried at a coarser
#: cut by the band table") rather than a token ("n/a").
MIN_WAIVER_REASON_CHARS = 20

#: Where an outline records a deliberate decision not to place a built table.
WAIVER_KEY = "unused_derived_evidence"

#: A section that exists to say what would weaken the report needs more than one
#: sentence of it, or it is a disclaimer.
MIN_COUNTER_EVIDENCE_CLAIMS = 2


def _built_tables(state: ReportState) -> list[dict]:
    """Every cross tabulation already computed and citable, in ledger order."""
    ledger = Path(
        state.sources.get("evidence_ledger_path")
        or (run_dir_for(state) / "evidence_ledger.jsonl")
    )
    if not ledger.exists():
        return []
    rows: list[dict] = []
    for line in ledger.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return built_table_entries(rows)


def _figure_plan_evidence_ids(state: ReportState) -> set[str]:
    """Evidence a planned figure draws on — a table shown as a chart is used."""
    path = run_dir_for(state) / "section_drafts" / "figure_plan.json"
    if not path.exists():
        return set()
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return set()
    used: set[str] = set()
    for figure in (payload.get("figures") or []) if isinstance(payload, dict) else []:
        if not isinstance(figure, dict):
            continue
        for key in ("source_evidence_ids", "evidence_ids"):
            for evidence_id in figure.get(key) or []:
                used.add(str(evidence_id))
    return used


def _validate_derived_table_coverage(state: ReportState, outline: dict) -> None:
    """Refuse an outline that silently drops a table the pipeline already built.

    The cross tabulations are computed at intake whether or not anyone asks for
    them, and three acceptance runs of the same task placed four of the seven,
    then three, then two. Nothing failed: the tables were simply never mentioned,
    and the run that used two produced a document with six tables where the run
    that used four produced ten. A reader gets one run, not the average of
    three, so the run that loses five tables is the one the tool is judged on.

    Dropping one is a legitimate editorial decision — a crossing can be
    uninformative, or already carried at a better cut by another table. What was
    not legitimate was making that decision by omission. Here it has to be
    written down, and writing it down is enough: an author who has to name the
    reason usually finds there isn't one.
    """
    tables = _built_tables(state)
    if not tables:
        return

    cited: set[str] = set()
    for claim in (state.plan.get("claim_matrix") or {}).get("claims", []):
        if isinstance(claim, dict):
            cited.update(str(evidence_id) for evidence_id in claim.get("evidence_ids") or [])
    cited |= _figure_plan_evidence_ids(state)

    waived = outline.get(WAIVER_KEY) or {}
    if not isinstance(waived, dict):
        raise QAHardBlockError(
            f"OUTLINE_PLAN: outline.json '{WAIVER_KEY}' must be an object mapping "
            "each unused evidence id to the reason it is not used."
        )
    waived = {str(key): str(value or "").strip() for key, value in waived.items()}

    known = {table["evidence_id"]: table for table in tables}
    problems: list[str] = []

    unknown = sorted(set(waived) - set(known))
    if unknown:
        problems.append(
            f"'{WAIVER_KEY}' names ids that are not built tables: "
            + ", ".join(unknown)
            + ". Only the tables listed in the drafting brief can be waived."
        )

    short = sorted(
        evidence_id
        for evidence_id, reason in waived.items()
        if len(reason) < MIN_WAIVER_REASON_CHARS
    )
    if short:
        problems.append(
            "these waivers give no usable reason: "
            + ", ".join(short)
            + f". Each needs at least {MIN_WAIVER_REASON_CHARS} characters saying what "
            "the table would have added and why the report is better without it."
        )

    # One reason pasted across several tables is the omission this gate exists
    # to catch, wearing a sentence.
    reasons = [reason for reason in waived.values() if reason]
    repeated = sorted({reason for reason in reasons if reasons.count(reason) > 1})
    if repeated:
        problems.append(
            "the same waiver reason is reused for more than one table: "
            + "; ".join(f"{reason[:40]!r}" for reason in repeated)
            + ". Each table was dropped for its own reason, or it was not "
            "considered separately."
        )

    missing = [
        table
        for table in tables
        if table["evidence_id"] not in cited and table["evidence_id"] not in waived
    ]
    if missing:
        listed = "\n".join(
            f"  - {table['evidence_id']} ({table['origin']}): {table['description']}"
            for table in missing
        )
        problems.append(
            f"{len(missing)} table(s) are already built and cited by nothing:\n{listed}\n"
            "Place each one — have a claim cite its id, or a figure draw on it — or "
            f"record why not in outline.json:\n"
            f'  "{WAIVER_KEY}": {{"{missing[0]["evidence_id"]}": '
            '"<what this crossing would have shown, and why the report is better without it>"}'
        )

    if problems:
        raise QAHardBlockError("OUTLINE_PLAN: " + " ".join(problems))

    write_json_artifact(state, "derived_table_coverage.json", {
        "available": tables,
        "placed": sorted(evidence_id for evidence_id in known if evidence_id in cited),
        "waived": waived,
    })


def _flagged_sections(state: ReportState, flag: str) -> list[str]:
    """Sections whose blueprint entry turns a requirement on."""
    blueprint_sections = (state.plan.get("blueprint") or {}).get("sections") or {}
    return [
        section_id
        for section_id, spec in blueprint_sections.items()
        if isinstance(spec, dict) and spec.get(flag)
    ]


def _validate_counter_evidence(state: ReportState, sections: dict, claim_ids: set) -> None:
    """A counter-evidence section has to name the conclusion it weakens.

    The unassisted control opened its counter-evidence chapter by conceding that
    its own headline recommendation might be an artefact of which listings carry
    a sales figure. That is the paragraph a reader needs and the one no gate
    asked for, so a required section alone would buy a heading over a
    "limitations apply" sentence. Naming the claims is what makes it cost
    something: the author has to find a conclusion of theirs that the data does
    not fully carry.
    """
    for section_id in _flagged_sections(state, "requires_undermines"):
        section = sections.get(section_id)
        if not isinstance(section, dict):
            continue  # absence is the required-section check's business
        own = [str(claim_id) for claim_id in section.get("claim_ids") or []]
        if len(own) < MIN_COUNTER_EVIDENCE_CLAIMS:
            raise QAHardBlockError(
                f"OUTLINE_PLAN: section {section_id} carries {len(own)} claim(s); "
                f"at least {MIN_COUNTER_EVIDENCE_CLAIMS} are required. This section "
                "states what the evidence does not support — coverage that varies by "
                "band, a population the source under-samples, a figure resting on one "
                "row — and each of those is a claim of its own."
            )
        undermines = section.get("undermines")
        if not isinstance(undermines, list) or not undermines:
            raise QAHardBlockError(
                f"OUTLINE_PLAN: section {section_id} must declare 'undermines': the "
                "claim ids elsewhere in the report whose support this section "
                'qualifies. Example: "undermines": ["c7", "c12"]. A limitations '
                "section that weakens nothing is a disclaimer."
            )
        unknown = sorted(str(c) for c in undermines if str(c) not in claim_ids)
        if unknown:
            raise QAHardBlockError(
                f"OUTLINE_PLAN: section {section_id} 'undermines' names claims that do "
                f"not exist: {', '.join(unknown)}."
            )
        self_referential = sorted(str(c) for c in undermines if str(c) in own)
        if self_referential:
            raise QAHardBlockError(
                f"OUTLINE_PLAN: section {section_id} 'undermines' names its own claims: "
                f"{', '.join(self_referential)}. Name the conclusions elsewhere in the "
                "report that this section qualifies, not the qualifications themselves."
            )


def _validate_prompt_answers(state: ReportState, sections: dict) -> None:
    """The conclusion has to answer what the task statement asked.

    Extracted rather than declared, and answered by index rather than by text, so
    the questions cannot drift into ones the report happens to have answered. A
    task statement that asks for work rather than answers extracts nothing and
    this requires nothing.
    """
    questions = extract_questions(state.spec.get("user_prompt", ""))
    if not questions:
        return
    for section_id in _flagged_sections(state, "must_answer_prompt_questions"):
        section = sections.get(section_id)
        if not isinstance(section, dict):
            continue
        listed = "\n".join(f"  [{index}] {q}" for index, q in enumerate(questions))
        answers = section.get("answers")
        if not isinstance(answers, list):
            raise QAHardBlockError(
                f"OUTLINE_PLAN: the task statement asks {len(questions)} question(s), so "
                f"section {section_id} must declare 'answers' — one entry per question, "
                "binding it to the claim that answers it:\n"
                f"{listed}\n"
                '  "answers": [{"question_index": 0, "claim_ids": ["c12"]}, ...]'
            )
        own = {str(claim_id) for claim_id in section.get("claim_ids") or []}
        covered: dict[int, list[str]] = {}
        for position, answer in enumerate(answers):
            if not isinstance(answer, dict):
                raise QAHardBlockError(
                    f"OUTLINE_PLAN: section {section_id} answers[{position}] must be an "
                    'object like {"question_index": 0, "claim_ids": ["c12"]}.'
                )
            try:
                index = int(answer.get("question_index"))
            except (TypeError, ValueError):
                raise QAHardBlockError(
                    f"OUTLINE_PLAN: section {section_id} answers[{position}] needs an "
                    f"integer 'question_index' between 0 and {len(questions) - 1}."
                ) from None
            if not 0 <= index < len(questions):
                raise QAHardBlockError(
                    f"OUTLINE_PLAN: section {section_id} answers[{position}] has "
                    f"question_index {index}; the task statement asks "
                    f"{len(questions)} question(s):\n{listed}"
                )
            bound = [str(claim_id) for claim_id in answer.get("claim_ids") or []]
            outside = sorted(claim_id for claim_id in bound if claim_id not in own)
            if outside:
                raise QAHardBlockError(
                    f"OUTLINE_PLAN: section {section_id} answers question {index} with "
                    f"claims it does not carry: {', '.join(outside)}. The answer has to "
                    f"be stated in {section_id}, so its claims belong to that section's "
                    "claim_ids."
                )
            if not bound:
                raise QAHardBlockError(
                    f"OUTLINE_PLAN: section {section_id} answers question {index} with no "
                    "claim. A question is answered by a sentence the evidence carries, "
                    "not by a heading."
                )
            covered.setdefault(index, []).extend(bound)
        unanswered = [index for index in range(len(questions)) if index not in covered]
        if unanswered:
            missing = "\n".join(f"  [{index}] {questions[index]}" for index in unanswered)
            raise QAHardBlockError(
                f"OUTLINE_PLAN: section {section_id} leaves the task statement's "
                f"question(s) unanswered:\n{missing}\n"
                "Add an entry to 'answers' binding each to the claim that answers it. "
                "A report that never says which way the decision goes has not been "
                "written for the person who asked."
            )


def run_outline_plan(state: ReportState) -> ReportState:
    """T9: OUTLINE_PLAN - load agent-authored outline."""
    path = _outline_path(state)
    if not path.exists():
        write_agent_task_briefs(state)
        missing = missing_agent_artifacts(state, str(path))
        state.update_status("awaiting_agent_artifacts")
        raise AgentWorkRequired(f"Agent artifact required: {path}", missing)

    result = _load_outline(path)
    validate_artifact_contract(state, path, allow_missing=True)
    sections = result.get("sections", {})
    if not isinstance(sections, dict) or not sections:
        raise QAHardBlockError("outline.json must contain a non-empty sections object")

    if "results_mode" in result:
        # QA_GATE reads sections.results.results_mode. A top-level one is read
        # by nothing, so the run falls back to the blueprint default and the
        # author is never told their choice was dropped.
        raise QAHardBlockError(
            "outline.json sets 'results_mode' at the top level, where nothing reads it. "
            "Move it to sections.results.results_mode."
        )

    blueprint_sections = set((state.plan.get("blueprint") or {}).get("sections", {}).keys())
    allowed_sections = set(blueprint_sections)
    revise_mode = state.spec.get("task_intent") == "revise_existing"
    if revise_mode:
        # In revise_existing the document's shape is the *base document's*,
        # not the new-draft blueprint's: its parsed section ids are the valid
        # outline targets. Validating a revision outline against the blueprint
        # rejected every real base document whose headings differ from the
        # blueprint (any Chinese document, any custom structure).
        base_sections_path = run_dir_for(state) / "base_document_sections.json"
        if base_sections_path.exists():
            try:
                with open(base_sections_path, encoding="utf-8") as f:
                    base_sections = json.load(f)
                if isinstance(base_sections, dict):
                    allowed_sections.update(base_sections.keys())
            except json.JSONDecodeError:
                pass
    unknown_sections = sorted(section_id for section_id in sections if allowed_sections and section_id not in allowed_sections)
    if unknown_sections:
        raise QAHardBlockError(f"Outline references unknown sections: {', '.join(unknown_sections)}")
    if not revise_mode:
        # Blueprint-required sections apply to new drafts only; a revision
        # outline mirrors whatever sections the base document actually has.
        validate_required_outline_sections(state.plan.get("blueprint") or {}, sections)

    assigned_claims = set()
    for section_id, section in sections.items():
        if not isinstance(section, dict):
            raise QAHardBlockError(f"Outline section {section_id} must be an object")
        section.setdefault("section_id", section_id)
        _hoist_subsections(section_id, section)
        claim_ids = section.get("claim_ids", [])
        if not isinstance(claim_ids, list):
            raise QAHardBlockError(f"Outline section {section_id} claim_ids must be a list")
        assigned_claims.update(claim_ids)

    _validate_figure_plan_against_outline(state, sections)

    claim_ids = {claim.get("claim_id") for claim in state.plan.get("claim_matrix", {}).get("claims", [])}
    missing = sorted(claim_id for claim_id in claim_ids if claim_id and claim_id not in assigned_claims)
    if missing:
        raise QAHardBlockError(f"Outline did not assign claims: {', '.join(missing)}")

    unknown_claims = sorted(claim_id for claim_id in assigned_claims if claim_id not in claim_ids)
    if unknown_claims:
        raise QAHardBlockError(f"Outline references unknown claims: {', '.join(unknown_claims)}")

    if not revise_mode:
        # A revision inherits the base document's shape and its author's
        # decisions; these three ask what a *new* draft covers.
        _validate_derived_table_coverage(state, result)
        _validate_counter_evidence(state, sections, claim_ids)
        _validate_prompt_answers(state, sections)

    state.plan["outline"] = result
    state.plan["outline_path"] = write_json_artifact(state, "outline.json", result)
    write_artifact_contract(state.plan["outline_path"], make_artifact_contract(state))
    return state
