"""Structured parser for CSV, XLSX, JSON files."""
import csv
import json
import tomllib

# What people type in a cell they have not filled in yet. Deliberately does not
# include "0" or "false" — those are results, not absences — nor "?" , which a
# survey may well use as a real answer code.
PLACEHOLDER_CELL_VALUES = frozenset({
    "", "-", "--", "---", "—", "–", "n/a", "n.a.", "na", "nil",
    "null", "none", "nan", "tbd", "待填", "無", "无", "未測", "未测",
})


def is_placeholder_value(value: object) -> bool:
    """True when a cell holds a stand-in rather than a value."""
    return str(value).strip().lower() in PLACEHOLDER_CELL_VALUES


def _disambiguate_headers(headers: list[str]) -> list[str]:
    """Make repeated column names distinct, keeping the first as written.

    An instrument export names every thermocouple "Temperature (°C)".
    DictReader keys rows by name, so the second and third readings overwrote
    the first and left the row holding one temperature out of three — data
    the source contained, destroyed at ingestion, with the table then
    reported as having four columns instead of six. pandas already renames
    duplicates for .xlsx, so only the CSV path lost them.
    """
    seen: dict[str, int] = {}
    out: list[str] = []
    for header in headers:
        name = str(header)
        seen[name] = seen.get(name, 0) + 1
        out.append(name if seen[name] == 1 else f"{name} [{seen[name]}]")
    return out


def _cell_count(row) -> int:
    filled = 0
    for cell in row:
        text = str(cell).strip()
        if text and text.lower() != "nan":
            filled += 1
    return filled


def _leading_noise_rows(rows: list) -> int:
    """How many rows sit above a table's real header.

    A monthly export opens with its own name in A1 and a blank line under it.
    Read as the header, that title became the first column's name, the other
    columns became Unnamed, and the real header — 月份, 不良率(%), 產量(件) —
    was demoted to a citable data row, taking the unit out of the column name
    that the unit checks read. In CSV it was worse: a one-cell header truncated
    every data row to one column and the other two measurements were gone.

    A title fills one cell and a spacer none, while any header worth the name
    spans at least two, so only leading rows holding at most one value are
    skipped, and only when the row directly below them is the widest in the
    table. A header with a blank corner cell still holds two or more values and
    is never passed over.
    """
    widest = max((_cell_count(row) for row in rows), default=0)
    if widest < 2:
        return 0
    skipped = 0
    for row in rows[:5]:
        if _cell_count(row) <= 1 and skipped + 1 < len(rows):
            skipped += 1
            continue
        break
    if not skipped or _cell_count(rows[skipped]) != widest:
        return 0
    return skipped


def parse_csv(file_path: str) -> list[dict]:
    """Parse CSV file with the standard library."""
    import io

    from .source_text import read_source_text

    rows = list(csv.reader(io.StringIO(read_source_text(file_path), newline="")))
    if not rows:
        return []
    rows = rows[_leading_noise_rows(rows):]
    headers = _disambiguate_headers(rows[0])
    return [
        dict(zip(headers, row))
        for row in rows[1:]
        if any(str(cell).strip() for cell in row)
    ]


def parse_xlsx(file_path: str) -> list[dict]:
    """Parse XLSX file using pandas — every sheet, not only the first.

    A workbook that keeps one year per tab had its other tabs read by nobody:
    those rows never reached the ledger and nothing said they existed. When
    more than one sheet holds data each record carries the name of the sheet it
    came from, because rows reading 1.8 and 4.2 with no way to tell which year
    is the confusion that gets the wrong one cited. A single-sheet workbook —
    the ordinary case — is parsed exactly as before, with no added key.
    """
    import pandas as pd

    book = pd.read_excel(file_path, sheet_name=None, header=None)
    sheets: list[tuple[str, list[dict]]] = []
    for name, raw in book.items():
        if raw.empty:
            continue
        skip = _leading_noise_rows(raw.values.tolist())
        frame = pd.read_excel(file_path, sheet_name=name, header=skip)
        records = frame.to_dict(orient="records")
        if records:
            sheets.append((str(name), records))

    if len(sheets) <= 1:
        return sheets[0][1] if sheets else []

    combined: list[dict] = []
    for name, records in sheets:
        for record in records:
            key = "sheet"
            suffix = 2
            while key in record:
                key = f"sheet [{suffix}]"
                suffix += 1
            combined.append({key: name, **record})
    return combined


def parse_json(file_path: str) -> list[dict]:
    """Parse JSON file."""
    from .source_text import read_source_text

    data = json.loads(read_source_text(file_path))
    if isinstance(data, list):
        return data
    elif isinstance(data, dict):
        return [data]
    return []


def parse_toml(file_path: str) -> list[dict]:
    """Parse TOML files such as pyproject.toml."""
    with open(file_path, "rb") as f:
        data = tomllib.load(f)
    if isinstance(data, dict):
        return [data]
    return []


def parse_structured(file_path: str, file_type: str) -> dict:
    """Parse structured file and return content blocks."""
    try:
        if file_type == "csv":
            records = parse_csv(file_path)
        elif file_type == "xlsx":
            records = parse_xlsx(file_path)
        elif file_type == "json":
            records = parse_json(file_path)
        elif file_type == "toml":
            records = parse_toml(file_path)
        else:
            return {"blocks": [], "error": f"Unsupported file type: {file_type}"}

        blocks = []
        content_lines = []
        for i, record in enumerate(records):
            line = json.dumps(record, ensure_ascii=False)
            headers = [str(key) for key in record.keys()]
            values = [str(value) for value in record.values()]
            # A row exported before anyone filled it in carries column names and
            # nothing else. It used to become an evidence entry all the same, so
            # an untouched export could clear the "at least 5 evidence entries"
            # bar with five rows of dashes. Note "0" is a measurement, not a
            # blank — only the placeholders below count as absent.
            if values and all(is_placeholder_value(value) for value in values):
                continue
            content_lines.append(line)
            blocks.append({
                "block_id": f"block_{i}",
                "block_type": "table_row",
                "content": line,
                "page_number": None,
                "table_data": [headers, values] if headers or values else None
            })

        return {
            "blocks": blocks,
            "raw_content": "\n".join(content_lines),
            "success": True
        }
    except Exception as e:
        return {"blocks": [], "error": str(e), "success": False}
