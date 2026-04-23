"""POST_RENDER_REPAIR - repair common DOCX rendering defects after DOCX_RENDER."""
from __future__ import annotations

from pathlib import Path

from docx import Document

from ..errors import QAHardBlockError
from ..runtime_support import write_json_artifact
from ..state import ReportState
from .docx_render import _repair_missing_figures, _style_tables_post_render


def _remove_duplicate_figure_captions(doc: Document) -> int:
    seen: set[str] = set()
    removed = 0
    paragraphs = list(doc.paragraphs)
    for index, para in enumerate(paragraphs):
        text = " ".join(para.text.split())
        if not text.lower().startswith("figure "):
            continue
        if para.style.name == "Image Caption" and index + 1 < len(paragraphs):
            next_text = " ".join(paragraphs[index + 1].text.split())
            if next_text.startswith(text):
                para._element.getparent().remove(para._element)
                removed += 1
                continue
        if text in seen:
            para._element.getparent().remove(para._element)
            removed += 1
        else:
            seen.add(text)
    return removed


def run_post_render_repair(state: ReportState) -> ReportState:
    """Repair missing figures, duplicate captions, and table styling."""
    docx_path = state.output.get("final_docx_path") or state.output.get("rendered_docx_path")
    if not docx_path or not Path(docx_path).exists():
        raise QAHardBlockError("POST_RENDER_REPAIR: rendered DOCX is missing")

    draft_path = state.drafts.get("publication_style_draft") or state.drafts.get("merged_draft_cited_md")
    draft_text = Path(draft_path).read_text(encoding="utf-8") if draft_path and Path(draft_path).exists() else ""

    inserted = _repair_missing_figures(docx_path, draft_text)
    _style_tables_post_render(docx_path)

    doc = Document(docx_path)
    duplicate_captions_removed = _remove_duplicate_figure_captions(doc)
    if duplicate_captions_removed:
        doc.save(docx_path)

    report = {
        "job_id": state.job_id,
        "figures_inserted": inserted,
        "duplicate_captions_removed": duplicate_captions_removed,
        "status": "passed",
    }
    state.runtime["post_render_repair_report_path"] = write_json_artifact(
        state, "post_render_repair_report.json", report
    )
    return state
