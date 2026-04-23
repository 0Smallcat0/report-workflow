"""BASE_DOCUMENT_PARSE node - extract sections from a base document for revision.

Sits after SOURCE_PARSE.  Only runs when task_intent == 'revise_existing'.
base_document entries (artifact_role == 'base_document') are parsed into
section_id → markdown content mapping.  The result is stored in
state.sources['base_document_sections'] as a dict.

base_document is NOT evidence — it is the document being revised.
"""
import json
import re
from pathlib import Path

from ..state import ReportState, WORKFLOW_RUNS_DIR
from ..errors import QAHardBlockError
from ..artifact_contract import write_base_document_integrity


def _parse_docx_section(path: str) -> dict[str, str]:
    """Extract paragraphs from a .docx file as section_chunks.

    We avoid heavy dependencies by reading the docx XML directly via zipfile.
    Each top-level paragraph becomes a chunk; consecutive chunks with no
    heading are merged until a heading-1 is encountered (new section).
    """
    import zipfile

    sections: dict[str, str] = {}
    current_section_id = "preamble"
    current_lines: list[str] = []

    try:
        with zipfile.ZipFile(path, "r") as z:
            # Read document.xml
            with z.open("word/document.xml") as f:
                import xml.etree.ElementTree as ET

                tree = ET.parse(f)
                root = tree.getroot()
                ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

                for elem in root.iter():
                    if elem.tag.endswith("}p"):  # paragraph
                        # Extract text from paragraph
                        texts: list[str] = []
                        for t in elem.iter():
                            if t.tag.endswith("}t") and t.text:
                                texts.append(t.text)
                        line = "".join(texts).strip()
                        if not line:
                            continue

                        # Check if this is a heading
                        pPr = elem.find("w:pPr", ns)
                        style = None
                        if pPr is not None:
                            pStyle = pPr.find("w:pStyle", ns)
                            if pStyle is not None:
                                style = pStyle.get(f'{{{ns["w"]}}}val')

                        if style and style.startswith("Heading"):
                            # Flush current section
                            if current_lines:
                                sections[current_section_id] = "\n".join(current_lines)
                                current_lines = []
                            # Use the heading text as section id
                            heading_text = line.lower().replace(" ", "_")
                            current_section_id = heading_text[:48]
                        current_lines.append(line)
    except Exception as exc:
        raise QAHardBlockError(f"Failed to parse base document {path}: {exc}")

    # Flush last section
    if current_lines:
        sections[current_section_id] = "\n".join(current_lines)

    return sections


_NUMBERED_HEADING_RE = re.compile(r"^\s*\d+(?:\.\d+)*\.?\s+")


def _section_id_from_heading(heading: str) -> str:
    """Map a publication heading to the workflow's canonical section id."""
    normalized = _NUMBERED_HEADING_RE.sub("", heading).strip().lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")

    aliases = {
        "abstract": "abstract",
        "introduction": "introduction",
        "research_scope": "research_scope",
        "research_scope_and_design_framing": "research_scope",
        "scope": "research_scope",
        "scope_boundary": "research_scope",
        "design_framing": "research_scope",
        "methods": "methods",
        "method": "methods",
        "methodology": "methods",
        "results": "results",
        "findings": "results",
        "discussion": "discussion",
        "analysis": "discussion",
        "limitations": "limitations",
        "limitation": "limitations",
        "conclusion": "conclusion",
        "conclusions": "conclusion",
        "references": "references",
        "reference": "references",
        "bibliography": "references",
    }
    return aliases.get(normalized, normalized[:48] or "preamble")


def _parse_markdown_sections(path: str) -> dict[str, str]:
    """Extract section_id -> markdown content from a Markdown base document.

    The parser preserves the body markdown under each top-level section instead
    of flattening it. This is intentionally lightweight but strict enough for
    revise_existing: headings create section boundaries, while all tables,
    figures, lists, and subsection headings remain part of the section body.
    """
    text = Path(path).read_text(encoding="utf-8-sig")
    sections: dict[str, str] = {}

    heading_re = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
    all_matches = list(heading_re.finditer(text))
    if not all_matches:
        return {"preamble": text}
    matches = [match for match in all_matches if len(match.group(1)) <= 2]
    if not matches:
        matches = all_matches

    first = matches[0]
    preamble = text[:first.start()].strip()
    if preamble:
        sections["preamble"] = preamble

    # Treat the first H1 as front-matter/title unless it is the only heading
    # before section-level H2/H3 headings. Its content before the next heading
    # is still retained in preamble.
    for index, match in enumerate(matches):
        level = len(match.group(1))
        heading_text = match.group(2).strip()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        body = text[start:end].strip()

        if level == 1 and index == 0 and matches[1:]:
            title_block = f"# {heading_text}"
            if body:
                title_block += "\n\n" + body
            existing = sections.get("preamble", "")
            sections["preamble"] = "\n\n".join(part for part in (existing, title_block) if part).strip()
            continue

        section_id = _section_id_from_heading(heading_text)
        if section_id in sections and sections[section_id].strip():
            sections[section_id] = sections[section_id].rstrip() + "\n\n" + body
        else:
            sections[section_id] = body

    return sections


def run_base_document_parse(state: ReportState) -> ReportState:
    """T7b: BASE_DOCUMENT_PARSE - extract sections from base_document (if any).

    Only runs when state.spec["task_intent"] == "revise_existing".
    If no base_document is found, this node is a no-op.
    """
    task_intent = state.spec.get("task_intent", "new_draft")
    if task_intent != "revise_existing":
        # Skip — not a revision workflow
        return state

    source_registry = state.sources.get("source_registry", [])
    base_entries = [
        entry for entry in source_registry
        if entry.get("artifact_role") == "base_document"
    ]

    if not base_entries:
        raise QAHardBlockError(
            "revise_existing intent requires exactly one base_document source; "
            "none found in source_registry"
        )

    if len(base_entries) > 1:
        raise QAHardBlockError(
            f"revise_existing intent requires exactly one base_document; "
            f"found {len(base_entries)}: {[e['file_name'] for e in base_entries]}"
        )

    entry = base_entries[0]
    file_path = entry.get("file_path", "")
    file_type = entry.get("file_type", "")

    if file_type not in ("docx", "txt", "md"):
        raise QAHardBlockError(
            f"base_document must be .docx, .md, or .txt; got .{file_type}"
        )

    if file_type == "docx":
        sections = _parse_docx_section(file_path)
    elif file_type == "md":
        sections = _parse_markdown_sections(file_path)
    else:
        text = Path(file_path).read_text(encoding="utf-8")
        sections = {"preamble": text}

    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    run_dir.mkdir(parents=True, exist_ok=True)
    sections_path = run_dir / "base_document_sections.json"
    with open(sections_path, "w", encoding="utf-8") as f:
        json.dump(sections, f, indent=2)

    state.sources["base_document_sections"] = sections
    state.sources["base_document_sections_path"] = str(sections_path)
    write_base_document_integrity(state, sections, entry)
    return state
