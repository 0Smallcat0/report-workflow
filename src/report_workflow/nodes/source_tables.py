"""Put a source's own tables back into the document.

Ingestion splits a table into one evidence row per line so each line can be
cited on its own. Nothing put them back. A source carrying four tables
produced a deliverable carrying none, and the author's only options were to
retype the numbers into the draft — unchecked by anything, which defeats the
whole ledger — or to route the table through the chart recommender, which
answers a different question and drops the table's provenance on the way.

So: rebuild the grid from the rows, let the author place it with a
``[TABLE:<table_id>]`` marker, and render it with the file and line span it
came from. The numbers in the document are then the numbers in the source,
by construction rather than by transcription.
"""
from __future__ import annotations

import re

from ..language import CJK_RE


#: A row's block_id is its table's id with ``_r<n>`` appended (``_r<t>_<n>``
#: for a table found inside prose), which is what makes the parent id
#: recoverable and therefore what makes the marker addressable.
_ROW_SUFFIX_RE = re.compile(r"_r(\d+)(?:_(\d+))?$")

TABLE_PLACEHOLDER_RE = re.compile(r"\[TABLE:\s*([^\]\s]+)(?:\s+([^\]]+))?\]", re.IGNORECASE)


def _row_order(block_id: str) -> tuple[int, int]:
    """Sort key that restores the source order of a table's rows."""
    match = _ROW_SUFFIX_RE.search(block_id or "")
    if not match:
        return (0, 0)
    first = int(match.group(1))
    if match.group(2):
        return (first, int(match.group(2)))
    return (0, first)


def table_id_for_row(row: dict) -> str | None:
    """The id of the table this evidence row came from, or None."""
    if row.get("block_type") != "table_row":
        return None
    block_id = str(row.get("block_id") or "")
    parent = _ROW_SUFFIX_RE.sub("", block_id)
    if not parent or parent == block_id:
        return None
    return parent


def collect_source_tables(evidence_ledger: list[dict]) -> dict[str, dict]:
    """Rebuild every table in the ledger, keyed by the id a marker names.

    Each entry carries the headers, the rows in source order, the file and
    span they came from, and the evidence ids that back them — everything a
    caption needs in order to be checkable.
    """
    grouped: dict[str, list[dict]] = {}
    for row in evidence_ledger or []:
        table_id = table_id_for_row(row)
        if not table_id:
            continue
        table_data = row.get("table_data")
        if not isinstance(table_data, list) or len(table_data) < 2:
            continue
        grouped.setdefault(table_id, []).append(row)

    tables: dict[str, dict] = {}
    for table_id, rows in grouped.items():
        rows.sort(key=lambda item: _row_order(str(item.get("block_id") or "")))
        headers = [str(cell) for cell in rows[0]["table_data"][0]]
        if not any(header.strip() for header in headers):
            continue
        body = [[str(cell) for cell in row["table_data"][1]] for row in rows]
        first = rows[0]
        tables[table_id] = {
            "table_id": table_id,
            "headers": headers,
            "rows": body,
            "source_file_name": str(first.get("source_file_name") or ""),
            "source_span": str(first.get("source_span") or ""),
            "evidence_ids": [str(row.get("evidence_id") or "") for row in rows],
        }
    return tables


def _escape(value: object) -> str:
    return str(value).replace("|", "\\|")


def provenance_line(table: dict, language: str) -> str:
    """Where this table came from, in the document's language."""
    locator = " ".join(
        part for part in (table.get("source_file_name"), table.get("source_span")) if part
    )
    if not locator:
        return ""
    return f"來源：{locator}" if language == "zh" else f"Source: {locator}"


#: An author-written table label at the head of a caption — "表 1：", "表1.",
#: "Table 2:" — which the renderer is about to write itself.
_LEADING_TABLE_LABEL_RE = re.compile(
    r"^\s*(?:(?:表|图|圖)\s*\d+|Table\s+\d+)\s*[：:.、．]\s*",
    re.IGNORECASE,
)


def render_source_table(
    table: dict,
    *,
    number: int,
    caption: str = "",
    language: str = "en",
) -> str:
    """One markdown table, captioned and attributed.

    The attribution is not decoration. A table whose numbers the reader cannot
    trace is the same problem as an uncited sentence, and this pipeline exists
    in order not to have that problem.
    """
    label = "表" if language == "zh" else "Table"
    title = " ".join(str(caption or "").split())
    # The renderer numbers the table, so an author who also wrote the number
    # into the caption got it twice ("表 1. 表 1：三條路線…"). Writing the
    # number is the natural thing to do — the caption reads as prose to the
    # author — so drop the redundant label rather than ask them to omit it.
    title = _LEADING_TABLE_LABEL_RE.sub("", title).strip()
    heading = f"{label} {number}. {title}".strip() if title else f"{label} {number}."

    header_row = "| " + " | ".join(_escape(cell) for cell in table["headers"]) + " |"
    separator = "|" + "|".join(" --- " for _ in table["headers"]) + "|"
    body = "\n".join(
        "| " + " | ".join(_escape(cell) for cell in row) + " |" for row in table["rows"]
    )

    parts = [heading, "", header_row, separator, body]
    source = provenance_line(table, language)
    if source:
        parts.extend(["", source])
    return "\n".join(parts)


def replace_table_placeholders(
    markdown: str,
    evidence_ledger: list[dict],
    *,
    start_number: int = 0,
) -> tuple[str, int, list[str]]:
    """Expand ``[TABLE:<id>]`` markers into the source's own tables.

    Returns the rewritten markdown, how many tables were placed, and the ids
    that named no table — those are reported rather than silently dropped,
    the way an unresolved figure id is.
    """
    tables = collect_source_tables(evidence_ledger)
    if not tables:
        unresolved = [
            match.group(1).strip() for match in TABLE_PLACEHOLDER_RE.finditer(markdown or "")
        ]
        return markdown, 0, unresolved

    language = "zh" if CJK_RE.search(markdown or "") else "en"
    placed = 0
    unresolved: list[str] = []
    number = start_number

    def replace(match: re.Match) -> str:
        nonlocal placed, number
        table_id = match.group(1).strip()
        table = tables.get(table_id)
        if table is None:
            unresolved.append(table_id)
            return match.group(0)
        placed += 1
        number += 1
        return render_source_table(
            table,
            number=number,
            caption=(match.group(2) or "").strip(),
            language=language,
        )

    return TABLE_PLACEHOLDER_RE.sub(replace, markdown), placed, unresolved


def resolvable_placeholder_count(markdown: str, evidence_ledger: list[dict]) -> int:
    """How many ``[TABLE:]`` markers in this draft name a real table."""
    tables = collect_source_tables(evidence_ledger)
    return sum(
        1
        for match in TABLE_PLACEHOLDER_RE.finditer(markdown or "")
        if match.group(1).strip() in tables
    )
