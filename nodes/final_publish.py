"""FINAL_PUBLISH node - deliver final output."""
import shutil
from datetime import datetime
from pathlib import Path
from ..state import ReportState, WORKFLOW_RUNS_DIR


def run_final_publish(state: ReportState) -> ReportState:
    """T16: FINAL_PUBLISH - copy final.docx to output location."""
    final_docx = state.output.get("final_docx_path")
    
    if final_docx and Path(final_docx).exists():
        run_dir = WORKFLOW_RUNS_DIR / state.job_id
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        final_path = run_dir / f"final_{timestamp}.docx"
        
        shutil.copy2(final_docx, final_path)
        state.output["final_docx_path"] = str(final_path)
    
    state.update_status("completed")
    
    # Write final state
    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    final_state_path = run_dir / "final_state.json"
    state.checkpoint("FINAL_PUBLISH")
    
    return state
