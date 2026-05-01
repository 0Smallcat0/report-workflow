"""GUIDELINE_SELECT node - deterministic guideline selection."""
import json
from pathlib import Path
from ..state import ReportState
from ..state import WORKFLOW_RUNS_DIR
from ..runtime_support import write_json_artifact
from ..policies import get_policy

GUIDELINE_RULES_PATH = Path(__file__).parent.parent / "configs" / "guideline_rules.json"
GUIDELINES_DIR = Path(__file__).parent.parent / "guidelines"


def available_guidelines() -> set[str]:
    return {path.stem for path in GUIDELINES_DIR.glob("*.json")}


def run_guideline_select(state: ReportState) -> ReportState:
    """T3: GUIDELINE_SELECT - select guidelines based on keywords and report profile."""
    with open(GUIDELINE_RULES_PATH, encoding="utf-8-sig") as f:
        config = json.load(f)

    user_prompt = state.spec.get("user_prompt", "").lower()
    report_profile = state.spec.get("report_profile", "academic_paper")
    keywords = [str(keyword).lower() for keyword in state.spec.get("keywords", [])]
    search_text = " ".join([user_prompt, *keywords])
    available = available_guidelines()

    candidates = []
    matched_rule = None

    for rule in config.get("rules", []):
        condition = rule.get("condition", {})
        rule_keywords = condition.get("keywords", [])
        matched_keywords = [kw for kw in rule_keywords if kw.lower() in search_text]
        if matched_keywords:
            candidates = rule.get("selected_guidelines", [])
            matched_rule = {
                "id": rule.get("id", ""),
                "matched_keywords": matched_keywords,
            }
            break

    if not candidates:
        # ------------------------------------------------------------------
        # Per policy: some families require explicit --guidelines flag.
        # This prevents false-positive hard blocks from medical checklist
        # rules applied to non-clinical project reports.
        # ------------------------------------------------------------------
        policy = get_policy(report_profile)
        if policy.guideline.auto_select_allowed:
            candidates = config.get("defaults", {}).get(report_profile, [])
        else:
            candidates = []
        matched_rule = {
            "id": f"default:{report_profile}",
            "matched_keywords": [],
        }

    selected = [guideline for guideline in candidates if guideline in available]
    unavailable = [guideline for guideline in candidates if guideline not in available]

    state.spec["selected_guidelines"] = selected
    state.spec["guideline_selection"] = {
        "matched_rule": matched_rule,
        "candidate_guidelines": candidates,
        "selected_guidelines": selected,
        "unavailable_guidelines": unavailable,
        "available_guidelines": sorted(available),
    }

    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    run_dir.mkdir(parents=True, exist_ok=True)
    selection_path = run_dir / "guideline_selection.json"
    with open(selection_path, "w", encoding="utf-8") as f:
        json.dump(state.spec["guideline_selection"], f, indent=2)
    state.spec["guideline_selection_path"] = str(selection_path)
    state.spec["report_spec_path"] = write_json_artifact(state, "report_spec.json", state.spec)

    return state
