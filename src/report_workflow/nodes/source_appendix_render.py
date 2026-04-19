"""SOURCE_APPENDIX_RENDER node - render internal source appendix as separate traceability document.

Sits between PUBLICATION_STYLE_PASS and FINAL_PUBLISH in the render phase.

The internal_source_appendix.md contains [Source: ...] markers stripped from
body prose, organized as a traceability log. It is NOT part of the published
report — it is published as a separate traceability_appendix.docx.

Output: traceability_appendix.docx
"""
from pathlib import Path

from ..state import ReportState, WORKFLOW_RUNS_DIR
from ..errors import QAHardBlockError
from .docx_render import markdown_to_docx


def run_source_appendix_render(state: ReportState) -> ReportState:
    """T_NEW: SOURCE_APPENDIX_RENDER - render source appendix as separate docx.

    Position: After PUBLICATION_STYLE_PASS, before FINAL_PUBLISH.
    """
    source_appendix_path = state.citations.get("internal_source_appendix_path", "")
    if not source_appendix_path or not Path(source_appendix_path).exists():
        # No appendix = nothing to do
        state.output["traceability_appendix_docx_path"] = ""
        return state

    appendix_md = Path(source_appendix_path).read_text(encoding="utf-8")
    if not appendix_md.strip():
        state.output["traceability_appendix_docx_path"] = ""
        return state

    # Wrap the appendix content with a title page
    title_page = """# Internal Traceability Appendix

_This document is for internal traceability and audit purposes only._
_It is NOT part of the published academic report._

---

"""
    wrapped_md = title_page + appendix_md

    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    appendix_docx_path = run_dir / "traceability_appendix.docx"

    try:
        markdown_to_docx(wrapped_md, str(appendix_docx_path))
    except Exception as exc:
        # Don't hard-fail the whole render if appendix fails
        state.output["traceability_appendix_docx_path"] = ""
        state.runtime["warning"] = f"SOURCE_APPENDIX_RENDER failed: {exc}"
        return state

    state.output["traceability_appendix_docx_path"] = str(appendix_docx_path)
    return state
