"""GUIDELINE_SELECT node - deterministic guideline selection."""
import json
from pathlib import Path
from ..state import ReportState

GUIDELINE_RULES_PATH = Path(__file__).parent.parent / "configs" / "guideline_rules.json"


def run_guideline_select(state: ReportState) -> ReportState:
    """T3: GUIDELINE_SELECT - select guidelines based on keywords and report family."""
    with open(GUIDELINE_RULES_PATH) as f:
        config = json.load(f)
    
    user_prompt = state.spec.get("user_prompt", "").lower()
    report_family = state.spec.get("report_family", "academic_report")
    keywords = state.spec.get("keywords", [])
    
    selected = []
    
    # Check rules
    for rule in config.get("rules", []):
        condition = rule.get("condition", {})
        rule_keywords = condition.get("keywords", [])
        if any(kw.lower() in user_prompt for kw in rule_keywords):
            selected = rule.get("selected_guidelines", [])
            break
    
    # Apply defaults
    if not selected:
        if report_family == "work_report":
            selected = config["defaults"].get("work_report", [])
        elif report_family == "hybrid_report":
            selected = config["defaults"].get("hybrid_report", [])
    
    state.spec["selected_guidelines"] = selected
    return state
