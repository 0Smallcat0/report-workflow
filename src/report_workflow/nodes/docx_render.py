"""DOCX_RENDER node - convert markdown to .docx."""
import json
import logging
import re
from pathlib import Path
from docx import Document
from docx.shared import Pt, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from ..state import ReportState, WORKFLOW_RUNS_DIR
from ..errors import QAHardBlockError
from ..runtime_support import PLACEHOLDER_TEXT
from ..policies import get_policy

logger = logging.getLogger(__name__)


def markdown_to_docx(md_text: str, output_path: str) -> None:
    """Convert markdown to DOCX using python-docx."""
    doc = Document()
    
    lines = md_text.split("\n")
    
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        
        if not line:
            doc.add_paragraph()
            i += 1
            continue
        
        # Headings
        if line.startswith("#### "):
            doc.add_heading(line[5:], level=4)
        elif line.startswith("### "):
            doc.add_heading(line[4:], level=3)
        elif line.startswith("## "):
            doc.add_heading(line[3:], level=2)
        elif line.startswith("# "):
            doc.add_heading(line[2:], level=1)
        # Bullet lists
        elif line.startswith("- ") or line.startswith("* "):
            doc.add_paragraph(line[2:], style="List Bullet")
        # Numbered lists
        elif re.match(r"^\d+\.\s", line):
            match = re.match(r"^(\d+)\.\s(.*)", line)
            if match:
                doc.add_paragraph(match.group(2), style="List Number")
        # Tables
        elif line.startswith("|") and i + 1 < len(lines) and lines[i + 1].strip().startswith("|"):
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                if not re.match(r"^\|[\s\-\|]+\|$", lines[i].strip()):
                    table_lines.append(lines[i].strip())
                i += 1
            if table_lines:
                num_cols = len(table_lines[0].split("|")) - 2
                table = doc.add_table(rows=len(table_lines), cols=num_cols)
                for row_idx, tline in enumerate(table_lines):
                    cells = [c.strip() for c in tline.split("|")[1:-1]]
                    for col_idx, cell in enumerate(cells):
                        if col_idx < num_cols:
                            table.rows[row_idx].cells[col_idx].text = cell
            continue
        # Regular paragraph
        else:
            para = doc.add_paragraph()
            parts = re.split(r'(\*\*[^*]+\*\*|\*[^*]+\*)', line)
            for part in parts:
                if part.startswith("**") and part.endswith("**"):
                    run = para.add_run(part[2:-2])
                    run.bold = True
                elif part.startswith("*") and part.endswith("*"):
                    run = para.add_run(part[1:-1])
                    run.italic = True
                else:
                    para.add_run(part)
        
        i += 1
    
    doc.save(output_path)


def run_docx_render(state: ReportState) -> ReportState:
    """T15: DOCX_RENDER - convert markdown to .docx."""
    qa_decision = state.qa.get("qa_decision")

    if qa_decision and qa_decision != "pass":
        raise QAHardBlockError(f"QA gate failed: {qa_decision}")

    # Select draft path per policy
    family = state.spec.get("report_family", "academic_report")
    policy = get_policy(family)

    if policy.citation.draft_prefer_marker_stripped:
        # Prefer publication_draft_md (marker-stripped, citation-bound)
        cited_md_path = state.drafts.get("publication_draft_md")
        if not cited_md_path or not Path(cited_md_path).exists():
            cited_md_path = state.drafts.get("merged_draft_cited_md")
    else:
        # Prefer publication_style_draft (style-polished) with fallbacks
        cited_md_path = state.drafts.get("publication_style_draft")
        if not cited_md_path or not Path(cited_md_path).exists():
            cited_md_path = state.drafts.get("merged_draft_cited_md")
        if not cited_md_path or not Path(cited_md_path).exists():
            cited_md_path = state.drafts.get("merged_draft_md")

    if not cited_md_path or not Path(cited_md_path).exists():
        raise QAHardBlockError("No merged draft found")

    with open(cited_md_path, encoding="utf-8") as f:
        md_content = f.read()

    if not md_content.strip():
        raise QAHardBlockError("Merged draft is empty")
    if PLACEHOLDER_TEXT in md_content:
        raise QAHardBlockError("Merged draft contains placeholder content")

    # Inject front matter at the top of the document
    front_matter_md = state.plan.get("front_matter_md", "")
    if front_matter_md:
        md_content = front_matter_md + "\n\n---\n\n" + md_content

    # Append publication reference list (from dual-layer citation system)
    pub_ref_list_path = state.citations.get("publication_reference_list_path", "")
    if pub_ref_list_path and Path(pub_ref_list_path).exists():
        with open(pub_ref_list_path, encoding="utf-8") as f:
            pub_ref_content = f.read()
        if pub_ref_content.strip():
            md_content = md_content.rstrip() + "\n\n" + pub_ref_content

    # NOTE: Internal Source Appendix is NO LONGER appended to the main document.
    # It is rendered as a SEPARATE traceability_appendix.docx by the
    # SOURCE_APPENDIX_RENDER node (in render_nodes before FINAL_PUBLISH).
    # This keeps the published report clean and separates internal traceability.

    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    final_docx_path = run_dir / "rendered_report.docx"
    
    try:
        markdown_to_docx(md_content, str(final_docx_path))
    except Exception as exc:
        logger.exception("[DOCX_RENDER] markdown_to_docx failed")
        state.runtime["error"] = f"DOCX_RENDER failed: {type(exc).__name__}: {exc}"
        raise QAHardBlockError(f"DOCX render failed: {exc}") from exc
    
    state.output["final_docx_path"] = str(final_docx_path)
    state.output["rendered_docx_path"] = str(final_docx_path)
    return state
