"""BASE_DOCUMENT_PARSE node - extract sections from a base document for revision.

Sits after SOURCE_PARSE.  Only runs when task_intent == 'revise_existing'.
base_document entries (artifact_role == 'base_document') are parsed into
section_id → markdown content mapping.  The result is stored in
state.sources['base_document_sections'] as a dict.

base_document is NOT evidence — it is the document being revised.
"""
import json
from pathlib import Path

from ..state import ReportState, WORKFLOW_RUNS_DIR
from ..errors import QAHardBlockError


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

    if file_type not in ("docx", "txt"):
        raise QAHardBlockError(
            f"base_document must be .docx or .txt; got .{file_type}"
        )

    if file_type == "docx":
        sections = _parse_docx_section(file_path)
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
    return state
