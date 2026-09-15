"""The part of a long source a report actually uses.

A report that cites one table of an 86-page white paper, or one article of a
400-page regulation, had two options: attach the whole document and let every
page enter the ledger — thousands of rows, every one a candidate the author has
to wade through and the gates have to scan — or hand-copy the passage into a
new file, losing the page numbers that make it checkable and adding a
transcription nobody verifies.

A source entry can instead name the span it uses: ``"pages": "80-86"`` for a
PDF, ``"lines": "5504-5526, 180-187"`` for a text file. Only blocks inside the
span are read, and they keep their real page and line numbers.
"""
from __future__ import annotations

import re

_RANGE_RE = re.compile(r"^\s*(\d+)\s*(?:[-–~]\s*(\d+))?\s*$")


class SourceSelectionError(ValueError):
    """A page or line selection that cannot be applied as written."""


def parse_ranges(value: object, where: str) -> list[tuple[int, int]]:
    """"80-86, 90" as [(80, 86), (90, 90)]; refuses anything else by name."""
    if isinstance(value, int) and not isinstance(value, bool):
        value = str(value)
    if isinstance(value, (list, tuple)):
        value = ",".join(str(item) for item in value)
    text = str(value or "").strip()
    if not text:
        raise SourceSelectionError(f"{where} is empty; give ranges such as \"80-86, 90\"")
    ranges: list[tuple[int, int]] = []
    for part in text.split(","):
        match = _RANGE_RE.match(part)
        if not match:
            raise SourceSelectionError(
                f"{where}: {part.strip()!r} is not a number or a range such as 80-86"
            )
        start = int(match.group(1))
        end = int(match.group(2) or start)
        if start < 1 or end < start:
            raise SourceSelectionError(f"{where}: range {part.strip()!r} runs backwards or starts below 1")
        ranges.append((start, end))
    return ranges


def normalize_selection(item: dict, where: str) -> dict | None:
    """The ``pages``/``lines`` a source entry names, validated, or None."""
    selection: dict[str, list[tuple[int, int]]] = {}
    for key in ("pages", "lines"):
        if item.get(key) is not None:
            selection[key] = parse_ranges(item.get(key), f"{where}.{key}")
    return selection or None


def _within(number: int, ranges: list) -> bool:
    return any(int(start) <= number <= int(end) for start, end in ranges)


def _overlaps(first: int, last: int, ranges: list) -> bool:
    return any(first <= int(end) and last >= int(start) for start, end in ranges)


def apply_selection(blocks: list[dict], selection: dict, file_name: str) -> list[dict]:
    """The blocks inside the selection, or an error saying why there are none."""
    kept = list(blocks)
    pages = selection.get("pages")
    if pages:
        if not any(block.get("page_number") is not None for block in blocks):
            raise SourceSelectionError(
                f"{file_name}: 'pages' selects pages of a PDF, and this file has no page "
                "numbers; select 'lines' instead"
            )
        kept = [block for block in kept if block.get("page_number") is not None
                and _within(int(block["page_number"]), pages)]
    lines = selection.get("lines")
    if lines:
        if not any(block.get("line_start") is not None for block in blocks):
            raise SourceSelectionError(
                f"{file_name}: 'lines' selects lines of a text file, and this file has no "
                "line numbers; select 'pages' instead"
            )
        kept = [
            block for block in kept
            if block.get("line_start") is not None
            and _overlaps(int(block["line_start"]), int(block.get("line_end") or block["line_start"]), lines)
        ]
    if not kept:
        described = ", ".join(
            f"{key} {', '.join(f'{start}-{end}' for start, end in value)}"
            for key, value in selection.items()
        )
        raise SourceSelectionError(
            f"{file_name}: the selection ({described}) contains no text; check the numbers "
            "against the document"
        )
    return kept


def describe(selection: dict) -> str:
    """"pages 80-86, 90" — for the registry record and error messages."""
    return "; ".join(
        f"{key} " + ", ".join(f"{start}-{end}" if start != end else f"{start}" for start, end in value)
        for key, value in selection.items()
    )
