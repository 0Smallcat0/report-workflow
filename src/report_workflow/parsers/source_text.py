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
from pathlib import Path

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


def read_source_lines(file_path: str | Path) -> list[str]:
    """Decoded lines, each keeping its trailing newline as readlines() does."""
    return read_source_text(file_path).splitlines(keepends=True)
