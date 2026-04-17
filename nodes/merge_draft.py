"""MERGE_DRAFT node - concatenate sections in blueprint order."""
from pathlib import Path
from ..state import ReportState, WORKFLOW_RUNS_DIR


def run_merge_draft(state: ReportState) -> ReportState:
    """T11: MERGE_DRAFT - concatenate sections in blueprint order."""
    blueprint = state.plan.get("blueprint", {})
    section_order = blueprint.get("section_order", [])
    section_drafts = state.drafts.get("section_drafts", {})
    
    merged_sections = []
    
    for section_id in section_order:
        section_path = section_drafts.get(section_id)
        if section_path:
            try:
                with open(section_path) as f:
                    content = f.read()
                merged_sections.append(content)
            except Exception:
                pass
    
    merged_md = "\n\n".join(merged_sections)
    
    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    merged_path = run_dir / "merged_draft.md"
    with open(merged_path, "w") as f:
        f.write(merged_md)
    
    state.drafts["merged_draft_md"] = str(merged_path)
    return state
