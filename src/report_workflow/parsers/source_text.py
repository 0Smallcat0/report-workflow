"""Reading a source file whose encoding is not necessarily UTF-8.

Every reader here opened its file as UTF-8, so a .csv saved by Excel on a
Traditional Chinese Windows machine — Big5/cp950, which is that machine's
default, not an exotic choice — failed at ingest with a raw codec error. A
pipeline that ships Chinese blueprints, CJK abstract scaling and GB/T citation
formatting could not open the file its Chinese users actually produce.

The order matters. UTF-8 is tried first so nothing already working changes, and
the BOM variant precedes it because Excel writes one. cp950 and gb18030 are
supersets of Big5 and GBK respectively, so each covers its family. There is no
catch-all last resort: latin-1 decodes any byte sequence and would turn an
unreadable file into silent mojibake, which is worse than refusing it.
"""
import re
from pathlib import Path

#: The line breaks an editor, ``grep -n`` and a text-mode ``readlines()`` count.
#: ``str.splitlines`` also breaks on form feed, vertical tab and five Unicode
#: separators; a PDF exported to text carries a form feed at every page break,
#: so each page moved every later line number one further from the line a
#: reader opens.
_LINE_BREAK_RE = re.compile(r"\r\n|\r|\n")

#: Tried in order. Traditional Chinese before Simplified only because this
#: project's users write Traditional; neither decodes the other's bytes
#: cleanly, so the order does not create ambiguity.
SOURCE_ENCODINGS = ("utf-8-sig", "utf-8", "cp950", "gb18030")


def read_source_text(file_path: str | Path) -> str:
    """Decode a source file, trying the encodings its author plausibly used."""
    raw = Path(file_path).read_bytes()
    for encoding in SOURCE_ENCODINGS:
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError(
        "could not decode the file as any of "
        f"{', '.join(SOURCE_ENCODINGS)}; re-save it as UTF-8"
    )


def split_source_lines(text: str) -> list[str]:
    """Lines numbered the way the reader's editor numbers them, endings kept.

    A government plan exported with pdftotext holds a form feed per page, and
    ``splitlines`` counted each as a line: text on line 908, with 39 page breaks
    above it, was cited as line 947, and a ``"lines": "950-971"`` selection kept
    the wrong passage and silently dropped the one it named.
    """
    lines: list[str] = []
    start = 0
    for match in _LINE_BREAK_RE.finditer(text):
        lines.append(text[start:match.end()])
        start = match.end()
    if start < len(text):
        lines.append(text[start:])
    return lines


def read_source_lines(file_path: str | Path) -> list[str]:
    """Decoded lines, each keeping its trailing newline as readlines() does."""
    return split_source_lines(read_source_text(file_path))
