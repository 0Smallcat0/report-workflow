"""OUTLINE_PLAN node - load and validate agent-produced outline.json."""
import json
from pathlib import Path

from ..errors import AgentWorkRequired, QAHardBlockError
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

    state.plan["outline"] = result
    state.plan["outline_path"] = write_json_artifact(state, "outline.json", result)
    write_artifact_contract(state.plan["outline_path"], make_artifact_contract(state))
    return state
