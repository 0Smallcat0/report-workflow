"""FINAL_PUBLISH node - deliver final output."""
import shutil
import time
from pathlib import Path
from ..state import ReportState, run_dir_for
from ..errors import QAHardBlockError
from ..artifact_contract import find_repo_hygiene_issues


def _copy_with_retry(src: Path, dst: Path, max_retries: int = 3) -> None:
    """Copy file with retry on PermissionError (Windows file locking)."""
    if src.resolve() == dst.resolve():
        return

    last_error = None
    for attempt in range(max_retries):
        try:
            # First try to delete dst if it exists (Windows needs this for copy2)
            if dst.exists():
                try:
                    dst.unlink()
                except PermissionError:
                    pass  # File might be locked, try copy anyway
            shutil.copy2(src, dst)
            return
        except PermissionError as e:
            last_error = e
            if attempt < max_retries - 1:
                time.sleep(0.5 * (attempt + 1))  # Backoff: 0.5s, 1s, 1.5s
                continue
    raise QAHardBlockError(
        f"Failed to copy {src} to {dst} after {max_retries} attempts. "
        f"File may be locked by another process. "
        f"Last error: {last_error}",
        hint="Close any other programs that may have the file open, then try again."
    )


def run_final_publish(state: ReportState) -> ReportState:
    """T16: FINAL_PUBLISH - copy final.docx and traceability_appendix.docx to output location."""
    if state.qa.get("qa_decision") != "pass":
        raise QAHardBlockError(f"Cannot publish without passing QA: {state.qa.get('qa_decision')}")

    hygiene_issues = find_repo_hygiene_issues()
    if hygiene_issues:
        raise QAHardBlockError(
            "Repository root contains temporary repair scripts. Move scratch work under the run directory "
            "or delete these orphan files before publishing: " + ", ".join(hygiene_issues[:10])
        )

    final_docx = state.output.get("final_docx_path")
    if not final_docx or not Path(final_docx).exists():
        raise QAHardBlockError("Final DOCX is missing")

    output_dir = Path(state.output.get("output_dir") or run_dir_for(state))
    output_dir.mkdir(parents=True, exist_ok=True)
    final_path = output_dir / "final.docx"

    _copy_with_retry(Path(final_docx), final_path)
    state.output["final_docx_path"] = str(final_path)
    state.output["workflow_success"] = True
    state.output["published_report_path"] = str(final_path)

    # Publish traceability appendix as a separate document (not part of the report)
    appendix_docx = state.output.get("traceability_appendix_docx_path", "")
    if appendix_docx and Path(appendix_docx).exists():
        appendix_dest = output_dir / "traceability_appendix.docx"
        _copy_with_retry(Path(appendix_docx), appendix_dest)
        state.output["traceability_appendix_docx_path"] = str(appendix_dest)

    state.update_status("completed")

    run_dir = run_dir_for(state)
    state.checkpoint("FINAL_PUBLISH")

    return state
