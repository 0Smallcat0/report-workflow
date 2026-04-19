"""BLUEPRINT_PLAN node - load blueprint based on report family."""
import yaml
from pathlib import Path
from ..state import ReportState
from ..runtime_support import write_json_artifact

BLUEPRINTS_DIR = Path(__file__).parent.parent / "blueprints"


def run_blueprint_plan(state: ReportState) -> ReportState:
    """T4: BLUEPRINT_PLAN - load appropriate blueprint YAML."""
    report_family = state.spec.get("report_family", "academic_report")
    
    blueprint_map = {
        "academic_report": "academic_report.yaml",
        "work_report": "work_report.yaml",
        "hybrid_report": "hybrid_report.yaml",
    }
    
    blueprint_file = blueprint_map.get(report_family, "academic_report.yaml")
    blueprint_path = BLUEPRINTS_DIR / blueprint_file
    
    with open(blueprint_path, encoding="utf-8") as f:
        blueprint = yaml.safe_load(f)
    
    state.plan["blueprint"] = blueprint
    state.plan["blueprint_path"] = write_json_artifact(state, "blueprint.json", blueprint)
    return state
