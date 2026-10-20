"""The reference list of a finished document, as one string per reference.

``report-workflow check-references`` takes a draft written anywhere -- by hand,
by ChatGPT, by Deep Research -- so it reads the formats such a draft arrives
in: .docx, .md, .txt, and .bib. Only the reference section is read when the
document has one; a file with no such heading is taken to be the list itself.
"""
from __future__ import annotations

import re
from pathlib import Path

_HEADING_RE = re.compile(
    r"^\s*(?:#+\s*)?(?:\d+[.)]?\s*)?"
    r"(references|reference list|bibliography|works cited|literature cited|sources|"
    r"參考文獻|参考文献|參考資料|参考资料|引用文獻|文獻)\s*:?\s*$",
    re.IGNORECASE,
)
_NEXT_SECTION_RE = re.compile(r"^\s*(#+\s+\S|appendix\b|附錄|附录)", re.IGNORECASE)
_MARKER_RE = re.compile(r"^\s*(?:\[\d+\]|\d+[.)]\s|[-*•]\s)")


def _docx_paragraphs(path: Path) -> list[tuple[str, bool]]:
    from docx import Document

    paragraphs = []
    for paragraph in Document(str(path)).paragraphs:
        style = (paragraph.style.name or "").lower() if paragraph.style is not None else ""
        paragraphs.append((paragraph.text, style.startswith("heading") or style == "title"))
    return paragraphs


def _bib_entries(text: str) -> list[str]:
    """One citation-shaped string per BibTeX entry: authors (year). title. doi."""

    entries = []
    for body in re.split(r"(?m)^\s*@", text)[1:]:
        fields = {
            key.lower(): " ".join(value.replace("{", "").replace("}", "").split())
            for key, value in re.findall(r"(\w+)\s*=\s*[{\"](.*?)[}\"]\s*,?\s*$", body, flags=re.M | re.S)
        }
        if not fields.get("title"):
            continue
        # BibTeX writes "Family, Given"; a reference writes the given name first.
        names = [name.strip() for name in fields.get("author", "").split(" and ") if name.strip()]
        authors = ", ".join(" ".join(reversed(name.split(",", 1))).strip() for name in names)
        parts = [f"{authors} ({fields['year']})." if fields.get("year") else f"{authors}.", f"{fields['title']}."]
        venue = fields.get("journal") or fields.get("booktitle") or fields.get("publisher")
        if venue:
            parts.append(f"{venue}.")
        if fields.get("doi"):
            parts.append(f"doi:{fields['doi']}")
        elif fields.get("eprint") and "arxiv" in (fields.get("archiveprefix", "") + fields.get("journal", "")).lower():
            parts.append(f"arXiv:{fields['eprint']}")
        entries.append(" ".join(part for part in parts if part.strip(" .")))
    return entries


def extract_references(path: str | Path) -> list[str]:
    """Every reference in the document's reference section, in order."""

    path = Path(path)
    suffix = path.suffix.lower()
    if suffix == ".bib":
        return _bib_entries(path.read_text(encoding="utf-8", errors="replace"))
    if suffix == ".docx":
        lines = _docx_paragraphs(path)
    else:
        lines = [(line, False) for line in path.read_text(encoding="utf-8", errors="replace").splitlines()]

    start = next((i + 1 for i, (text, _) in enumerate(lines) if _HEADING_RE.match(text)), 0)
    section: list[str] = []
    for text, is_heading in lines[start:]:
        if start and section and (is_heading or _NEXT_SECTION_RE.match(text)):
            break
        section.append(text)

    numbered = any(_MARKER_RE.match(line) for line in section)
    references: list[str] = []
    current: list[str] = []

    def flush() -> None:
        if current:
            joined = " ".join(" ".join(current).split())
            joined = _MARKER_RE.sub("", joined, count=1).strip()
            if len(joined) >= 15:
                references.append(joined)
            current.clear()

    for line in section:
        if not line.strip():
            flush()
        elif numbered and _MARKER_RE.match(line):
            flush()
            current.append(line)
        elif numbered or suffix == ".docx":
            # A wrapped line continues the numbered entry; a .docx paragraph
            # is one entry.
            if suffix == ".docx":
                flush()
            current.append(line)
        else:
            current.append(line)
            if not _continues(line):
                flush()
    flush()
    return references


def _continues(line: str) -> bool:
    """A plain-text line that ends mid-reference (hyphenated or without a closing stop)."""

    stripped = line.rstrip()
    return stripped.endswith(("-", ",", "&", "and")) and not re.search(r"https?://\S+$", stripped)
