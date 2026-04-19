"""FINAL_PUBLISH node - deliver final output."""
import shutil
from pathlib import Path
from ..state import ReportState, WORKFLOW_RUNS_DIR
from ..errors import QAHardBlockError


def run_final_publish(state: ReportState) -> ReportState:
    """T16: FINAL_PUBLISH - copy final.docx and traceability_appendix.docx to output location."""
    if state.qa.get("qa_decision") != "pass":
        raise QAHardBlockError(f"Cannot publish without passing QA: {state.qa.get('qa_decision')}")

    final_docx = state.output.get("final_docx_path")
    if not final_docx or not Path(final_docx).exists():
        raise QAHardBlockError("Final DOCX is missing")

    output_dir = Path(state.output.get("output_dir") or (WORKFLOW_RUNS_DIR / state.job_id))
    output_dir.mkdir(parents=True, exist_ok=True)
    final_path = output_dir / "final.docx"

    shutil.copy2(final_docx, final_path)
    state.output["final_docx_path"] = str(final_path)

    # Publish traceability appendix as a separate document (not part of the report)
    appendix_docx = state.output.get("traceability_appendix_docx_path", "")
    if appendix_docx and Path(appendix_docx).exists():
        appendix_dest = output_dir / "traceability_appendix.docx"
        shutil.copy2(appendix_docx, appendix_dest)
        state.output["traceability_appendix_docx_path"] = str(appendix_dest)

    state.update_status("completed")

    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    state.checkpoint("FINAL_PUBLISH")

    return state
