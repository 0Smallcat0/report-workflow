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
from ..language import ZH_ORDINAL_PREFIX_RE
from ..parsers.source_text import read_source_text


def _drop_generated_toc(preamble: str) -> str:
    """Remove a table of contents this pipeline rendered into the base document.

    The front matter of a rendered report is title page, then the generated
    TOC, then the body. Reading that document back in captures both, and the
    next render adds its own TOC — so the scaffolding accumulates one copy per
    revision. The placeholder line is ours verbatim and safe to drop anywhere;
    the TOC title is an ordinary word, so it is only dropped when the
    placeholder follows it.
    """
    from .docx_render import _TOC_PLACEHOLDERS, _TOC_TITLES

    placeholders = set(_TOC_PLACEHOLDERS.values())
    titles = set(_TOC_TITLES.values())

    lines = preamble.split("\n")
    kept: list[str] = []
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped in placeholders:
            continue
        if stripped in titles:
            following = next(
                (nxt.strip() for nxt in lines[index + 1:] if nxt.strip()), ""
            )
            if following in placeholders:
                continue
        kept.append(line)
    return "\n".join(kept).strip()


def _extract_docx_media(archive, media_dir: Path) -> dict[str, str]:
    """Copy embedded images out of the archive and map relationship id to path.

    A figure is content the author put in the document. Reading only ``w:t``
    text nodes dropped every image, so revising a report deleted its charts and
    left their captions standing over nothing.
    """
    import re as _re

    try:
        rels_xml = archive.read("word/_rels/document.xml.rels").decode("utf-8")
    except KeyError:
        return {}

    targets = dict(
        _re.findall(r'Id="([^"]+)"[^>]*Target="(media/[^"]+)"', rels_xml)
    )
    if not targets:
        return {}

    media_dir.mkdir(parents=True, exist_ok=True)
    extracted: dict[str, str] = {}
    for rel_id, target in targets.items():
        member = f"word/{target}"
        try:
            payload = archive.read(member)
        except KeyError:
            continue
        out_path = media_dir / Path(target).name
        out_path.write_bytes(payload)
        extracted[rel_id] = str(out_path)
    return extracted


_DRAWING_BLIP_TAG = "{http://schemas.openxmlformats.org/drawingml/2006/main}blip"
_DRAWING_EMBED_ATTR = (
    "{http://schemas.openxmlformats.org/officeDocument/2006/relationships}embed"
)


_HEADING_ORDINAL_RE = re.compile(
    r"^\s*(?:\d+(?:\.\d+)*|[一二三四五六七八九十百]+|[IVXivx]+|[A-Za-z])"
    r"\s*[.、．)）:：]\s*"
)


def _section_id_for(heading: str, seen: dict[str, int]) -> str:
    """Address a section by what it is called, not by its number.

    The id was the heading slug, and a heading carries an ordinal the author
    maintains by hand. Inserting a missing methods section renumbered every
    heading below it, so "2. 結果" became "3. 結果" and a revision plan
    written against the first no longer resolved — the same section, the same
    words, a different identity. The number in a heading is a line number
    wearing a different hat.

    Two sections that read the same after the number comes off are told apart
    by which came first, so an id stays unique without depending on position.
    """
    stripped = _HEADING_ORDINAL_RE.sub("", heading).strip() or heading.strip()
    base = stripped.lower().replace(" ", "_")[:48] or "section"
    seen[base] = seen.get(base, 0) + 1
    return base if seen[base] == 1 else f"{base}_{seen[base]}"


def _docx_table_markdown(tbl) -> list[str]:
    """One DOCX table as Markdown pipe-table lines.

    A pipe table is the shape the rest of the pipeline already understands:
    evidence typing recognises it, the renderer styles it back into a real
    table, and a row keeps its header, so a number can still be checked
    against the column it came from.
    """
    rows: list[list[str]] = []
    for tr in tbl.iter():
        if not tr.tag.endswith("}tr"):
            continue
        cells: list[str] = []
        for tc in tr.iter():
            if not tc.tag.endswith("}tc"):
                continue
            texts = [t.text for t in tc.iter() if t.tag.endswith("}t") and t.text]
            cells.append(" ".join("".join(texts).split()))
        if cells:
            rows.append(cells)
    if len(rows) < 2:
        # A single row is not a table anyone can read as one; keep its text.
        return [" ".join(cell for cell in rows[0] if cell)] if rows else []

    width = max(len(row) for row in rows)
    lines = []
    for index, row in enumerate(rows):
        padded = row + [""] * (width - len(row))
        lines.append("| " + " | ".join(padded) + " |")
        if index == 0:
            lines.append("| " + " | ".join(["---"] * width) + " |")
    return lines


def _image_markdown_for_paragraph(paragraph, media_by_rel: dict[str, str]) -> str:
    """Markdown image links for every image embedded in one paragraph."""
    links: list[str] = []
    for blip in paragraph.iter(_DRAWING_BLIP_TAG):
        rel_id = blip.get(_DRAWING_EMBED_ATTR)
        target = media_by_rel.get(rel_id or "")
        if target:
            links.append(f"![]({target})")
    return " ".join(links)


def _parse_docx_section(
    path: str, media_dir: Path | None = None
) -> tuple[dict[str, str], dict[str, str]]:
    """Extract paragraphs from a .docx file as section_chunks.

    We avoid heavy dependencies by reading the docx XML directly via zipfile.
    Each top-level paragraph becomes a chunk; consecutive chunks with no
    heading are merged until a heading-1 is encountered (new section).

    Returns ``(sections, titles)``. The section id is a slug of the heading, so
    it cannot double as the heading itself — rendering the slug put an
    underscore through every numbered heading on the way back out
    ("1. 實驗目的" became "1._實驗目的"). The titles map keeps the heading text
    exactly as the document had it.

    When ``media_dir`` is given, embedded images are extracted there and each
    one is re-emitted as a markdown image link at the paragraph it occupied, so
    a revision keeps the figures the base document already had.
    """
    import zipfile

    sections: dict[str, str] = {}
    titles: dict[str, str] = {}
    section_id_counts: dict[str, int] = {}
    current_section_id = "preamble"
    current_lines: list[str] = []

    try:
        with zipfile.ZipFile(path, "r") as z:
            media_by_rel = _extract_docx_media(z, media_dir) if media_dir else {}
            # Read document.xml
            with z.open("word/document.xml") as f:
                import xml.etree.ElementTree as ET

                tree = ET.parse(f)
                root = tree.getroot()
                ns = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}

                # Paragraphs inside a table are emitted by the table branch
                # below. Without this, root.iter() reached them again on its
                # own and every cell became a line of its own: a six-row
                # measurement table left the document as twenty-one loose
                # lines, so "72.4" sat there with nothing saying it was the
                # effectiveness measured at 2.0 L/min. Revising your own
                # report destroyed the tables in it.
                cell_paragraphs: set = set()
                for elem in root.iter():
                    if elem.tag.endswith("}tbl"):
                        for para in elem.iter():
                            if para.tag.endswith("}p"):
                                cell_paragraphs.add(id(para))
                        table_lines = _docx_table_markdown(elem)
                        if table_lines:
                            current_lines.extend(table_lines)
                        continue
                    if elem.tag.endswith("}p") and id(elem) in cell_paragraphs:
                        continue
                    if elem.tag.endswith("}p"):  # paragraph
                        # Extract text from paragraph
                        texts: list[str] = []
                        for t in elem.iter():
                            if t.tag.endswith("}t") and t.text:
                                texts.append(t.text)
                        line = "".join(texts).strip()
                        if not line and media_by_rel:
                            # An image sits alone in its own paragraph, with no
                            # text to carry it. Re-emit it where it stood.
                            line = _image_markdown_for_paragraph(elem, media_by_rel)
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
                            # Slug for addressing, heading text for display.
                            current_section_id = _section_id_for(line, section_id_counts)
                            titles[current_section_id] = line
                        current_lines.append(line)
    except Exception as exc:
        raise QAHardBlockError(f"Failed to parse base document {path}: {exc}")

    # Flush last section
    if current_lines:
        sections[current_section_id] = "\n".join(current_lines)

    if "preamble" in sections:
        sections["preamble"] = _drop_generated_toc(sections["preamble"])

    return sections, titles


_NUMBERED_HEADING_RE = re.compile(r"^\s*\d+(?:\.\d+)*\.?\s+")


def _section_id_from_heading(heading: str) -> str:
    """Map a publication heading to the workflow's canonical section id.

    CJK characters are preserved: stripping to ``[a-z0-9]`` collapsed every
    Chinese heading to an empty slug, so a Chinese base document parsed into
    one giant ``preamble`` section (plus whatever Latin fragments survived,
    e.g. ``ai`` from a heading that mentioned AI) and revision targeting was
    impossible.
    """
    normalized = _NUMBERED_HEADING_RE.sub("", heading).strip()
    normalized = ZH_ORDINAL_PREFIX_RE.sub("", normalized).strip().lower()
    normalized = re.sub(r"[^a-z0-9㐀-鿿]+", "_", normalized).strip("_")

    zh_aliases = {
        "摘要": "abstract",
        "緒論": "introduction",
        "前言": "introduction",
        "引言": "introduction",
        "研究背景與動機": "introduction",
        "研究方法": "methods",
        "方法": "methods",
        "實驗方法": "methods",
        "結果": "results",
        "實驗結果": "results",
        "討論": "discussion",
        "結果與討論": "discussion",
        "研究限制": "limitations",
        "限制": "limitations",
        "結論": "conclusion",
        "參考文獻": "references",
        "附錄": "appendix",
    }
    if normalized in zh_aliases:
        return zh_aliases[normalized]

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
    text = read_source_text(path)
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


def _extract_markdown_section_titles(path: str) -> dict[str, str]:
    """Map section ids back to the base document's original heading text.

    The merged revision output previously rebuilt headings from slugs
    (``sid.replace("_", " ").title()``), which mangles every real heading —
    Chinese titles came back as space-separated slug words and aliased ids
    surfaced as English ("Introduction" for 「一、研究背景與動機」). The
    original text is authoritative; ids are only addressing.
    """
    text = read_source_text(path)
    heading_re = re.compile(r"^(#{1,6})\s+(.+?)\s*$", re.MULTILINE)
    all_matches = list(heading_re.finditer(text))
    matches = [match for match in all_matches if len(match.group(1)) <= 2]
    if not matches:
        matches = all_matches
    titles: dict[str, str] = {}
    for index, match in enumerate(matches):
        if len(match.group(1)) == 1 and index == 0 and matches[1:]:
            continue  # first H1 is the document title, kept in preamble
        heading_text = match.group(2).strip()
        section_id = _section_id_from_heading(heading_text)
        titles.setdefault(section_id, heading_text)
    return titles


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

    docx_titles: dict[str, str] = {}
    if file_type == "docx":
        sections, docx_titles = _parse_docx_section(
            file_path, media_dir=WORKFLOW_RUNS_DIR / state.job_id / "base_media"
        )
    elif file_type == "md":
        sections = _parse_markdown_sections(file_path)
    else:
        text = read_source_text(file_path)
        sections = {"preamble": text}

    if file_type == "md":
        titles = _extract_markdown_section_titles(file_path)
    elif file_type == "docx":
        titles = docx_titles
    else:
        # A .txt base document has no headings to recover, so the section id
        # is all there is; it is the whole file under "preamble" anyway.
        titles = {section_id: section_id for section_id in sections if section_id != "preamble"}

    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    run_dir.mkdir(parents=True, exist_ok=True)
    sections_path = run_dir / "base_document_sections.json"
    with open(sections_path, "w", encoding="utf-8") as f:
        # The revision brief sends the author here for section ids and for the
        # exact original_text a change must quote; escaped, a Chinese document
        # reads as \uXXXX and cannot be copied from. Its sibling titles file
        # one line down already wrote readable text. The sections hash is taken
        # over the parsed dict, so the encoding does not move it.
        json.dump(sections, f, indent=2, ensure_ascii=False)
    titles_path = run_dir / "base_document_titles.json"
    with open(titles_path, "w", encoding="utf-8") as f:
        json.dump(titles, f, indent=2, ensure_ascii=False)

    state.sources["base_document_sections"] = sections
    state.sources["base_document_sections_path"] = str(sections_path)
    state.sources["base_document_titles"] = titles
    write_base_document_integrity(state, sections, entry)
    return state
