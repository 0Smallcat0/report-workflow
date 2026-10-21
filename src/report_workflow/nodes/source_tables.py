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
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation

from ..language import CJK_RE


#: A row's block_id is its table's id with ``_r<n>`` appended (``_r<t>_<n>``
#: for a table found inside prose), which is what makes the parent id
#: recoverable and therefore what makes the marker addressable.
_ROW_SUFFIX_RE = re.compile(r"_r(\d+)(?:_(\d+))?$")

#: A row of a structured source is its file's ``block_<n>``: the file is the
#: table, so its stem is the id a marker names.
_SHEET_ROW_RE = re.compile(r"^block_(\d+)$")
_SHEET_FILE_TYPES = frozenset({"csv", "tsv"})

TABLE_PLACEHOLDER_RE = re.compile(r"\[TABLE:\s*([^\]\s]+)(?:\s+([^\]]+))?\]", re.IGNORECASE)


def _row_order(block_id: str) -> tuple[int, int]:
    """Sort key that restores the source order of a table's rows."""
    match = _ROW_SUFFIX_RE.search(block_id or "")
    if not match:
        sheet = _SHEET_ROW_RE.match(block_id or "")
        return (0, int(sheet.group(1))) if sheet else (0, 0)
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
    if parent and parent != block_id:
        return parent
    # A CSV row has no parent block: the file itself is the table. Without
    # this, a parameter sheet the author built for the reader was the one
    # table [TABLE:] could not place.
    file_type = str(row.get("file_type") or "").lower().lstrip(".")
    if _SHEET_ROW_RE.match(block_id) and file_type in _SHEET_FILE_TYPES:
        stem = str(row.get("source_file_name") or "").rsplit(".", 1)[0].strip()
        return stem or None
    return None


def collect_source_tables(evidence_ledger: list[dict]) -> dict[str, dict]:
    """Rebuild every table in the ledger, keyed by the id a marker names.

    Each entry carries the headers, the rows in source order, the file and
    span they came from, and the evidence ids that back them — everything a
    caption needs in order to be checkable.
    """
    tables: dict[str, dict] = {}
    # A derived cross table is one ledger entry carrying a whole grid, not a
    # run of row entries: the pipeline computed it, so there is nothing to
    # reassemble. It is placed with the same marker, because from the author's
    # side "put this table here" is one act whichever way the grid was built.
    aliases: dict[str, dict] = {}
    for row in evidence_ledger or []:
        grid = row.get("table_grid")
        if not isinstance(grid, dict):
            continue
        headers = [str(cell) for cell in grid.get("headers") or []]
        body = [[str(cell) for cell in line] for line in grid.get("rows") or []]
        if not headers or not body:
            continue
        entry = {
            "table_id": str(row.get("table_id") or row.get("evidence_id") or ""),
            "headers": headers,
            "rows": body,
            "source_file_name": str(row.get("source_file_name") or ""),
            "source_span": str(row.get("source_span") or ""),
            "evidence_ids": [str(row.get("evidence_id") or "")],
            # Computed here, from a file or from a publication the author
            # declared; the attribution under the table has to say which.
            "computed": True,
            "citation": row.get("citation") if isinstance(row.get("citation"), dict) else None,
        }
        display = _column_display(row.get("derivation"), len(headers))
        if display:
            entry["display_decimals"] = display
        tables[entry["table_id"]] = entry
        request_id = (row.get("derivation") or {}).get("request_id")
        if request_id:
            aliases.setdefault(str(request_id), entry)

    grouped: dict[str, list[dict]] = {}
    for row in evidence_ledger or []:
        table_id = table_id_for_row(row)
        if not table_id:
            continue
        table_data = row.get("table_data")
        if not isinstance(table_data, list) or len(table_data) < 2:
            continue
        grouped.setdefault(table_id, []).append(row)

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
            "file_type": str(first.get("file_type") or ""),
            "evidence_ids": [str(row.get("evidence_id") or "") for row in rows],
            "citation": first.get("citation") if isinstance(first.get("citation"), dict) else None,
        }
    # The author registered the derivation under their own id, so that is what
    # they will reach for when placing it. The evidence id still works; the
    # short name only fills a slot nothing else claimed.
    for alias, entry in aliases.items():
        tables.setdefault(alias, entry)
    return tables


def _column_display(derivation: object, width: int) -> list[int | None]:
    """Per-column display places of a formula table, aligned with its headers.

    The first column is the row label; each formula is one column after it.
    Empty when no column declares a display rule, so a table nobody asked to
    round prints exactly as it was recorded.
    """
    if not isinstance(derivation, dict) or derivation.get("method") != "formula_table":
        return []
    formulas = derivation.get("formulas") or []
    places = [None] + [
        item.get("display_decimals") if isinstance(item, dict) else None for item in formulas
    ]
    if len(places) != width or all(value is None for value in places):
        return []
    return places


def _shown(cell: str, places: int | None) -> str:
    """A recorded cell rounded for the reader: half away from zero, grouped by thousands."""
    if places is None:
        return cell
    text = str(cell).strip().replace(",", "").replace("−", "-")
    try:
        value = Decimal(text)
    except InvalidOperation:
        return cell
    if not value.is_finite():
        return cell
    step = Decimal(1).scaleb(-places)
    rounded = (value / step).quantize(Decimal(1), rounding=ROUND_HALF_UP) * step
    return f"{rounded:,.{max(places, 0)}f}"


#: The text width of the shipped A4 portrait template, and what one display
#: column (half a CJK character) and a cell's side padding take of it, in cm.
#: The template prints tables at 12 pt; widths estimated for 10.5 pt text
#: left a unit header reading "電力係數 (g" / "CO2e/kWh" / ")".
TEXT_WIDTH_CM = 15.9
DISPLAY_COLUMN_CM = 0.212
CELL_PADDING_CM = 0.45
#: Dashes shared out across the columns. pandoc sizes pipe-table columns from
#: their dashes only once a table line is longer than 72 columns.
SEPARATOR_DASHES = 160


#: Display columns a bold Latin character of a header takes: "CO2e/kWh)"
#: measures 2.24 cm at 12 pt, where nine display columns allow 1.91 cm.
HEADER_LATIN_COLUMNS = 1.2


def _is_wide(char: str) -> bool:
    return bool(CJK_RE.match(char)) or "＀" <= char <= "￯"


def _display_width(text: str) -> int:
    return sum(2 if _is_wide(char) else 1 for char in str(text))


#: The longest run of Chinese characters kept on one line when the column
#: allows it: a short term such as 電池容量 or 油電混合車 printed split —
#: "電池容" / "量" — reads as two words. Longer runs wrap anywhere.
WHOLE_TERM_CHARACTERS = 5


def _atoms(text: str, latin_columns: float) -> list[tuple[float, bool]]:
    """A cell's text as the pieces a line breaks between: (display columns, follows a space)."""
    atoms: list[tuple[float, bool]] = []
    for index, word in enumerate(str(text).split()):
        spaced = index > 0
        pieces: list[tuple[str, bool]] = []
        for char in word:
            wide = _is_wide(char)
            if pieces and pieces[-1][1] == wide:
                pieces[-1] = (pieces[-1][0] + char, wide)
            else:
                pieces.append((char, wide))
        for piece, wide in pieces:
            if not wide:
                atoms.append((len(piece) * latin_columns, spaced))
            elif len(piece) <= WHOLE_TERM_CHARACTERS:
                atoms.append((2.0 * len(piece), spaced))
            else:
                atoms.extend((2.0, spaced and position == 0) for position in range(len(piece)))
            spaced = False
    return atoms


def _lines_at(text: str, units: float, latin_columns: float = 1.0) -> int:
    """The lines a cell fills at a width, broken the way a word processor breaks them."""
    lines, used = 1, 0.0
    for width, spaced in _atoms(text, latin_columns):
        gap = 1.0 if spaced and used else 0.0
        if used and used + gap + width > units + 1e-9:
            lines += 1
            used = 0.0
            gap = 0.0
        if not used and width > units + 1e-9:
            # Wider than the column: forced breaks inside it.
            extra = int(-(-width // units)) - 1
            lines += extra
            used = width - extra * units
            continue
        used += gap + width
    return lines


def _column_dashes(headers: list[str], rows: list[list[str]]) -> list[int]:
    """Dash counts that give each column the width its content needs.

    Every column used to get " --- ", which pandoc renders as equal widths: a
    parameter table gave the column of two-digit values as much room as the
    column of sentences beside it and ran to five pages. Proportional widths
    were the next failure — a column of "53.4" got 6% of the page, less than
    its own padding, and printed "53." over "4". Capping every wide column
    alike was the third: parameter names wrapped to make room for sources that
    wrapped anyway, and a unit header sized at half its length printed
    "電池容" / "量" / "(kWh)". So each column starts at the narrowest width that
    breaks nothing it should not — a number, a unit, a short term — and the
    room left goes, a column at a time, where it saves the most lines.
    """
    count = len(headers)
    cells = [[row[index] if index < len(row) else "" for row in rows] for index in range(count)]

    def piece(text: str, latin: float) -> float:
        return max((width for width, _spaced in _atoms(text, latin)), default=0.0)

    minimum: list[float] = []
    natural: list[float] = []
    for index, header in enumerate(headers):
        least = max([piece(header, HEADER_LATIN_COLUMNS), 2.0] + [piece(cell, 1.0) for cell in cells[index]])
        least = float(int(-(-least // 1)))
        longest = max([float(_display_width(cell)) for cell in cells[index]] + [least])
        two_lines = least
        while _lines_at(header, two_lines, HEADER_LATIN_COLUMNS) > 2:
            two_lines += 1
        minimum.append(least)
        natural.append(max(longest, two_lines))

    available = (TEXT_WIDTH_CM - count * CELL_PADDING_CM) / DISPLAY_COLUMN_CM
    measured: dict[tuple[int, float], tuple[int, ...]] = {}

    def column_lines(index: int, width: float) -> tuple[int, ...]:
        """The header's lines, then each row's, for one column at one width."""
        key = (index, width)
        if key not in measured:
            measured[key] = (_lines_at(headers[index], width, HEADER_LATIN_COLUMNS),
                             *(_lines_at(cell, width) for cell in cells[index]))
        return measured[key]

    def height(units: list[float]) -> float:
        columns = [column_lines(index, units[index]) for index in range(count)]
        lines_by_row = list(zip(*columns))
        # Row heights are what the page pays for; every wrapped cell still
        # breaks ties between layouts that are equally tall.
        tall = sum(max(row) for row in lines_by_row)
        return tall + 0.1 * sum(map(sum, columns))

    if sum(natural) <= available:
        units = natural
    elif sum(minimum) >= available:
        units = [value * available / sum(minimum) for value in minimum]
    else:
        units = list(minimum)
        budget = available - sum(units)
        current = height(units)
        while True:
            best = None
            for index in range(count):
                target = units[index]
                previous = column_lines(index, target)
                while target + 1 <= natural[index] and target + 1 - units[index] <= budget + 1e-9:
                    target += 1
                    lines = column_lines(index, target)
                    if lines == previous:
                        continue
                    previous = lines
                    trial = list(units)
                    trial[index] = target
                    value = height(trial)
                    gain = (current - value) / (target - units[index])
                    if gain > 1e-9 and (best is None or gain > best[0] + 1e-9):
                        best = (gain, index, target, value)
            if best is None:
                break
            _gain, index, target, current = best
            budget -= target - units[index]
            units[index] = target
        lacking = [max(0.0, natural[index] - units[index]) for index in range(count)]
        spread = sum(lacking)
        for index in range(count):
            units[index] += budget * (lacking[index] / spread if spread else 1 / count)
    widths = [value * DISPLAY_COLUMN_CM + CELL_PADDING_CM for value in units]
    total = sum(widths)
    return [max(3, round(width / total * SEPARATOR_DASHES)) for width in widths]


def _escape(value: object) -> str:
    return str(value).replace("|", "\\|")


#: The author's own sheets: a table read from one is compiled, and its rows
#: carry their own sources in their columns.
_OWN_SHEET_FILE_TYPES = frozenset({"csv", "tsv", "json"})
#: The author's own notes: compiled too, but the note and its lines are the
#: only route back to what the table was taken from, so they stay named.
_OWN_NOTE_FILE_TYPES = frozenset({"md", "txt"})


def provenance_line(table: dict, language: str, pointer: str | None = None) -> str:
    """Where this table came from, in the document's language.

    A computed table says it was computed and where its calculation is shown —
    the report's own appendix, or its entry in the calculation record; it used
    to print the worksheet it was computed from — "來源：taiwan_scenarios.csv
    (5 rows)，本報告計算" — a local file and a row count standing where a
    source belongs. A table read from the author's own sheet is 本研究整理.
    Only a table found inside a document keeps the document's locator, which
    is the one route a reader has to it.
    """
    zh = language == "zh"
    computed = bool(table.get("computed"))
    pointer = str(pointer or "").strip()
    if pointer:
        pointer = f"（{pointer}）" if zh else f" ({pointer})"
    calculated = "本研究計算" if zh else "calculated in this study"
    citation = table.get("citation") if isinstance(table.get("citation"), dict) else None
    if citation:
        # A table computed over a declared publication is that publication's
        # data. Printing the transcription's file name under it — "來源：
        # knobloch2020_table6_2015.csv (9 rows)" — attributed Knobloch et al.'s
        # figures to a CSV the reader has never seen.
        from ..source_citation import in_text_author

        author = in_text_author(citation)
        year = str(citation.get("year") or "").strip() or ("無日期" if zh else "n.d.")
        if CJK_RE.search(author):
            named = f"{author}（{year}）"
        else:
            named = f"{author} ({year})"
        if zh:
            return f"來源：{named}" + (f"，{calculated}{pointer}" if computed else "")
        return f"Source: {named}" + (f"; {calculated}{pointer}" if computed else "")

    if computed:
        return f"來源：{calculated}{pointer}" if zh else f"Source: {calculated}{pointer}"

    file_type = str(table.get("file_type") or "").lower().lstrip(".")
    if file_type in _OWN_SHEET_FILE_TYPES:
        return "來源：本研究整理" if zh else "Source: compiled in this study"

    file_name = str(table.get("source_file_name") or "").strip()
    span = str(table.get("source_span") or "").strip()
    if file_name and span.startswith(file_name):
        file_name = ""
    locator = " ".join(part for part in (file_name, span) if part)
    if file_type in _OWN_NOTE_FILE_TYPES:
        if not locator:
            return "來源：本研究整理" if zh else "Source: compiled in this study"
        return f"來源：本研究整理自 {locator}" if zh else f"Source: compiled in this study from {locator}"
    if not locator:
        return ""
    return f"來源：{locator}" if zh else f"Source: {locator}"


#: An author-written table label at the head of a caption — "表 1：", "表1.",
#: "Table 2:" — which the renderer is about to write itself. Also with no
#: punctuation at all, "表 2　基準情境…", which is how authoring.md's own
#: example writes it, so following the documentation printed "表 1. 表 1 …".
_LEADING_TABLE_LABEL_RE = re.compile(
    r"^\s*(?:(?:表|图|圖)\s*\d+|Table\s+\d+)(?:\s*[：:.、．]\s*|\s+)",
    re.IGNORECASE,
)


def render_source_table(
    table: dict,
    *,
    number: int,
    caption: str = "",
    language: str = "en",
    pointer: str | None = None,
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

    # A header is printed the way a caption writes it: 「年化報酬 (%) 平均」, not
    # 「年化報酬_pct 平均」. Only the separators change; the words are the
    # column's own.
    from .figure_recommend import _reader_label

    headers = [_reader_label(str(cell)) for cell in table["headers"]]
    header_row = "| " + " | ".join(_escape(cell) for cell in headers) + " |"
    display = table.get("display_decimals") or []
    shown_rows = [
        [_shown(cell, display[index] if index < len(display) else None) for index, cell in enumerate(row)]
        for row in table["rows"]
    ]
    separator = "|" + "|".join(f" {'-' * width} " for width in _column_dashes(headers, shown_rows)) + "|"
    body = "\n".join(
        "| " + " | ".join(_escape(cell) for cell in row) + " |" for row in shown_rows
    )

    parts = [heading, "", header_row, separator, body]
    source = provenance_line(table, language, pointer)
    if source:
        parts.extend(["", source])
    return "\n".join(parts)


def placed_table_numbers(markdown: str, evidence_ledger: list[dict]) -> dict[str, int]:
    """The number each placed table prints under, for every evidence id it shows.

    Counted the way ``replace_table_placeholders`` counts: markers in reading
    order, one number per marker that names a table. A sentence citing a row
    or a computed figure the document prints in a table can then point there.
    """
    tables = collect_source_tables(evidence_ledger)
    numbers: dict[str, int] = {}
    number = 0
    for match in TABLE_PLACEHOLDER_RE.finditer(markdown or ""):
        table = tables.get(match.group(1).strip())
        if table is None:
            continue
        number += 1
        for evidence_id in table.get("evidence_ids") or []:
            numbers.setdefault(str(evidence_id), number)
    return numbers


def replace_table_placeholders(
    markdown: str,
    evidence_ledger: list[dict],
    *,
    start_number: int = 0,
    pointers: dict[str, str] | None = None,
) -> tuple[str, int, list[str]]:
    """Expand ``[TABLE:<id>]`` markers into the source's own tables.

    Returns the rewritten markdown, how many tables were placed, and the ids
    that named no table — those are reported rather than silently dropped,
    the way an unresolved figure id is. ``pointers`` maps a computed table's
    evidence id to where CITATION_BIND says its calculation is shown.
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
        evidence_ids = table.get("evidence_ids") or []
        return render_source_table(
            table,
            number=number,
            caption=(match.group(2) or "").strip(),
            language=language,
            pointer=(pointers or {}).get(evidence_ids[0]) if evidence_ids else None,
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
