"""BLUEPRINT_PLAN node - load blueprint based on report profile."""
import yaml
from pathlib import Path
from ..profiles import get_profile
from ..state import ReportState
from ..runtime_support import write_json_artifact

BLUEPRINTS_DIR = Path(__file__).parent.parent / "blueprints"


def run_blueprint_plan(state: ReportState) -> ReportState:
    """T4: BLUEPRINT_PLAN - load appropriate blueprint YAML."""
    profile = get_profile(state.spec.get("report_profile", "academic_paper"))
    blueprint_file = profile.blueprint_file
    blueprint_path = BLUEPRINTS_DIR / blueprint_file
    
    with open(blueprint_path, encoding="utf-8") as f:
        blueprint = yaml.safe_load(f)

    # ------------------------------------------------------------------
    # Propagate structured front matter from spec into blueprint.
    # CLI args (--title, --author, --affiliation, --correspondence,
    # --keyword) are stored in spec["front_matter"] but the blueprint's
    # front_matter template is all empty strings.  Without this merge,
    # validate's METADATA_GATE reads empty values from
    # plan["blueprint"]["front_matter"] and fails for academic reports.
    # ------------------------------------------------------------------
    spec_fm = state.spec.get("front_matter") or {}
    if spec_fm:
        bp_fm = blueprint.get("front_matter") or {}
        for key in ("title", "short_title", "author_block", "affiliation_block",
                    "correspondence", "keywords", "acknowledgements", "funding",
                    "conflict_note"):
            if spec_fm.get(key) and not bp_fm.get(key):
                bp_fm[key] = spec_fm[key]
        blueprint["front_matter"] = bp_fm

    state.plan["blueprint"] = blueprint
    state.plan["blueprint_path"] = write_json_artifact(state, "blueprint.json", blueprint)
    return state


def results_section_id(blueprint: dict | None) -> str:
    """The blueprint section that carries `results_mode` for this profile.

    The brief, the outline check and QA_GATE all said `sections.results`, but
    `engineering_lab_report` has no `results` section — its section is
    `results_discussion`. An author who did exactly what the brief said was
    refused with "Outline references unknown sections: results", and one who
    put it on `results_discussion` instead had the setting silently ignored.
    """
    sections = (blueprint or {}).get("sections") or {}
    if "results" in sections or not sections:
        return "results"
    for section_id in (blueprint or {}).get("section_order") or list(sections):
        if str(section_id).startswith("results"):
            return str(section_id)
    return "results"
