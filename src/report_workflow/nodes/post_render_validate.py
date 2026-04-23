"""POST_RENDER_VALIDATE - structural QA for rendered DOCX."""
from __future__ import annotations

import json
import re
from pathlib import Path

from docx import Document

from ..errors import QAHardBlockError
from ..runtime_support import write_json_artifact
from ..state import ReportState


def _docx_text_with_tables(doc: Document) -> str:
    parts = [para.text for para in doc.paragraphs]
    for table in doc.tables:
        for row in table.rows:
            parts.append("\t".join(cell.text for cell in row.cells))
    return "\n".join(parts)


def _outline_figure_count(state: ReportState) -> int:
    outline = state.plan.get("outline", {}) or {}
    count = 0
    for section in (outline.get("sections") or {}).values():
        fids = section.get("figure_ids", []) or []
        if isinstance(fids, list):
            count += len(fids)
    return count


def _outline_figure_ids(state: ReportState) -> set[str]:
    outline = state.plan.get("outline", {}) or {}
    ids: set[str] = set()
    for section in (outline.get("sections") or {}).values():
        fids = section.get("figure_ids", []) or []
        if isinstance(fids, list):
            ids.update(str(fid).lower() for fid in fids if str(fid).strip())
    return ids


def _expected_figure_count(state: ReportState) -> int:
    manifest_path = state.output.get("figure_manifest_path", "")
    manifest_count = 0
    if manifest_path and Path(manifest_path).exists():
        try:
            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)
            manifest_count = int(manifest.get("generated_count", 0) or 0)
        except Exception:
            manifest_count = 0
    # Outline may declare figures even when no manifest was produced (e.g.
    # matplotlib unavailable, malformed figure_plan.json). Treat outline as an
    # additional upper bound so silently-missing figures surface at render time.
    return max(manifest_count, _outline_figure_count(state))


def _expected_table_count(state: ReportState) -> int:
    draft_path = state.drafts.get("publication_style_draft") or state.drafts.get("merged_draft_cited_md")
    if not draft_path or not Path(draft_path).exists():
        return 0
    markdown = Path(draft_path).read_text(encoding="utf-8")
    return len(re.findall(r"^\|.+\|\s*$\n^\|?\s*:?-{3,}", markdown, re.MULTILINE))


def run_post_render_validate(state: ReportState) -> ReportState:
    """Hard-block rendered DOCX defects that require manual repair."""
    docx_path = state.output.get("final_docx_path") or state.output.get("rendered_docx_path")
    if not docx_path or not Path(docx_path).exists():
        raise QAHardBlockError("POST_RENDER_VALIDATE: rendered DOCX is missing")

    doc = Document(docx_path)
    text = _docx_text_with_tables(doc)
    issues: list[str] = []

    expected_figures = _expected_figure_count(state)
    expected_tables = _expected_table_count(state)
    outline_figure_ids = _outline_figure_ids(state)
    if len(doc.inline_shapes) < expected_figures:
        issues.append(f"expected {expected_figures} embedded figure(s), found {len(doc.inline_shapes)}")
    if len(doc.tables) < expected_tables:
        issues.append(f"expected {expected_tables} Word table(s), found {len(doc.tables)}")
    reference_heading_count = sum(
        1 for para in doc.paragraphs
        if para.style.name.startswith("Heading") and para.text.strip().lower() == "references"
    )
    if reference_heading_count > 1:
        issues.append(f"duplicate References headings found: {reference_heading_count}")

    figure_caption_labels: set[str] = set()
    for para in doc.paragraphs:
        text = " ".join(para.text.split())
        match = re.match(r"^(Figure\s+\d+\.\s+[^.]+(?:\.)?)", text, re.IGNORECASE)
        if not match:
            continue
        label = match.group(1).lower()
        if label in figure_caption_labels:
            issues.append(f"duplicate figure caption label: {match.group(1)}")
            break
        figure_caption_labels.add(label)

    leakage_patterns = [
        (r"\[CITE:", "unresolved CITE marker"),
        (r"\[Source:", "unresolved Source marker"),
        (r"\[FIGURE:", "unresolved FIGURE marker (figure not rendered)"),
        (r"\[graphify:", "unresolved graphify marker"),
        (r"source_corpus|claim_matrix|evidence_ledger", "internal artifact leakage"),
        (r"Revise the existing academic report|Use revised_report\.md", "prompt residue"),
        (r"author@example\.com|Independent Researcher|\{\.Title\}", "template metadata leakage"),
        (r"Research Author|Research University|research@university\.edu", "generic research metadata leakage"),
        (r"traceability appendix|End of Main Report|Appendix E|Appendices A and B", "appendix leakage"),
    ]
    for pattern, label in leakage_patterns:
        if re.search(pattern, text, re.IGNORECASE):
            issues.append(label)

    front_paras = [para.text.strip() for para in doc.paragraphs if para.text.strip()][:8]
    front_text = "\n".join(front_paras)
    if "**" in front_text:
        issues.append("front matter contains leftover Markdown bold marker")
    if re.search(r"\[(?:Author Name|University|email@domain\.com|Your Name|INSERT .+?)\]", front_text, re.IGNORECASE):
        issues.append("front matter contains placeholder metadata")

    caption_ids: set[str] = set()
    mention_ids: set[str] = set()
    for para in doc.paragraphs:
        para_text = " ".join(para.text.split())
        caption_match = re.match(r"^Figure\s+(\d+|[a-z])[:.]\s+", para_text, re.IGNORECASE)
        if caption_match:
            caption_ids.add(caption_match.group(1).lower())
            continue
        mention_ids.update(m.group(1).lower() for m in re.finditer(r"\bFigure\s+(\d+|[a-z])\b", para_text, re.IGNORECASE))

    if mention_ids:
        missing_captions = sorted(mention_ids - caption_ids)
        if missing_captions:
            issues.append("figure references without matching captions: " + ", ".join(missing_captions))
        if len(doc.inline_shapes) == 0:
            issues.append("figure references present but no embedded figures found")
        undeclared = sorted(mention_ids - outline_figure_ids) if outline_figure_ids else sorted(mention_ids)
        if undeclared:
            issues.append("figure references not declared in outline/manifest: " + ", ".join(undeclared))

    report = {
        "job_id": state.job_id,
        "paragraph_count": len(doc.paragraphs),
        "table_count": len(doc.tables),
        "inline_shape_count": len(doc.inline_shapes),
        "expected_table_count": expected_tables,
        "expected_figure_count": expected_figures,
        "issues": issues,
        "status": "passed" if not issues else "failed",
    }
    state.runtime["post_render_validate_report_path"] = write_json_artifact(
        state, "post_render_validate_report.json", report
    )
    if issues:
        raise QAHardBlockError("POST_RENDER_VALIDATE: " + "; ".join(issues))
    return state
