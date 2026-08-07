"""Statistics over a table, made citable.

A ledger of one row per record answers "what does this product cost" and
cannot answer "what does the category cost", which is the only question a
market report asks. Measured on a real run: 544 products, 473 reviews, 1,561
evidence rows — and the number of ledger rows stating the sample size, the
median price, a share, or a concentration index was zero. Every gate worked
exactly as designed, and the report came out with 26 numbers in it where an
unassisted write-up of the same three files had 703.

The cost is not the blocked claims. It is the sentences that were never
drafted: an author who knows each claim needs an evidence id stops reaching
for the figure long before any gate sees it. So the repair is not a looser
gate — it is evidence that says what a reader wants to know.

Two ways in:

* Every structured source gets summary units at prepare time: how many rows,
  how many values per column, min/median/mean/max of the numeric columns, and
  the group counts and shares of the categorical ones. Nobody has to ask.
* An author who needs something else registers it — a row filter, an
  operation, an id. The value is computed here, from the rows, and the author
  never supplies it. That is what makes it checkable: an ``expect`` that
  disagrees with the data is reported with both numbers.

The derivation travels with the evidence: which file, which rows, which
columns, which operation. A reader who doubts a figure can redo it.
"""
from __future__ import annotations

import hashlib
import json
import re
import statistics
import unicodedata

#: Currency marks sitting around a number in a real export. "$71.99" is a
#: price; a parser that reads it as text and skips the cell makes every price
#: in the file invisible to every gate downstream.
_CURRENCY_CHARS = "$€£¥₩＄￥￡"
_NUMBER_CLEAN_RE = re.compile(
    r"^[\s{chars}]*(?:US|NT|HK|AU|CA|RMB|CNY|USD|EUR|GBP|JPY|TWD|NTD)?[\s{chars}]*".format(
        chars=re.escape(_CURRENCY_CHARS)
    ),
    re.IGNORECASE,
)

_ROW_BLOCK_TYPES = frozenset({"csv_row", "table_row", "data_row"})

#: Columns whose values identify a record rather than measure it. The mean of
#: a product id is a number with no meaning, and publishing it as a citable
#: statistic is worse than having no statistic.
_ID_COLUMN_RE = re.compile(
    r"(?:^|[_\s-])(?:id|ids|asin|sku|upc|ean|isbn|uuid|guid|key|index|idx)(?:$|[_\s-])"
    r"|^(?:id|asin|sku|url|link|image|img|photo|thumbnail)"
    r"|(?:url|link|image|img|photo|thumbnail|src|href)$",
    re.IGNORECASE,
)

#: How many groups a distribution names before it stops being a distribution
#: and starts being the column reprinted.
MAX_GROUPS_LISTED = 15
#: How many groups a cross table shows before the tail folds into one "other"
#: row. A table longer than this is read by scrolling, not by looking.
MAX_GROUPS_IN_TABLE = 15
#: How many cross tables one source gets without anybody asking. Every
#: categorical column crossed with every numeric one is a combinatorial
#: explosion in a ledger the author has to read.
MAX_AUTO_CROSS_TABLES = 6
#: How many numeric columns an automatic cross table averages over.
MAX_AUTO_MEASURE_COLUMNS = 4
#: More distinct values than this and the column is a label, not a category.
MAX_CATEGORY_CARDINALITY = 60
#: Wide exports exist; a summary of 300 columns is not a summary.
MAX_COLUMNS_SUMMARIZED = 40
#: Share of non-empty cells that must parse as numbers before a column is
#: treated as numeric. A mixed column gets no statistics rather than
#: statistics over the half that happened to parse.
NUMERIC_COLUMN_THRESHOLD = 0.6

SUPPORTED_OPS = (
    "count", "sum", "mean", "median", "min", "max",
    "distinct", "share", "hhi", "top_share",
)


class DerivationError(ValueError):
    """A derivation request that cannot be carried out as written."""


# ----------------------------------------------------------------------
# Reading the rows
# ----------------------------------------------------------------------

_MISSING_TOKENS = {"-", "--", "n/a", "na", "nan", "none", "null"}


def parse_number(value: object) -> float | None:
    """A cell as a number, or None when it does not state one.

    Currency prefixes, thousands separators and a trailing percent sign are
    notation, not content. A price column written "$71.99" holds prices.
    """
    text = unicodedata.normalize("NFKC", str(value if value is not None else "")).strip()
    if not text:
        return None
    text = _NUMBER_CLEAN_RE.sub("", text).strip().rstrip("%").strip()
    text = text.replace(",", "").replace(" ", "")
    if not text or text.casefold() in _MISSING_TOKENS:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _currency_unit(values: list[str]) -> str:
    """The currency a column is written in, when it states one at all."""
    marks = {
        mark
        for value in values
        for mark in _CURRENCY_CHARS
        if mark in unicodedata.normalize("NFKC", str(value))
    }
    if len(marks) != 1:
        return ""
    return {"$": "USD", "€": "EUR", "£": "GBP", "¥": "JPY", "₩": "KRW"}.get(marks.pop(), "")


def _is_percent_column(header: str, values: list[str]) -> bool:
    if "%" in str(header) or "％" in str(header):
        return True
    filled = [value for value in values if str(value).strip()]
    return bool(filled) and all("%" in str(value) for value in filled)


class Dataset:
    """One structured source, read back as rows."""

    def __init__(self, entry: dict, rows: list[dict]):
        self.source_id = str(entry.get("source_id") or "")
        self.file_name = str(entry.get("file_name") or "")
        self.file_path = str(entry.get("file_path") or "")
        self.file_type = str(entry.get("file_type") or "")
        self.rows = rows
        seen: list[str] = []
        for row in rows:
            for key in row:
                if key not in seen:
                    seen.append(key)
        self.columns = seen
        #: Set when this frame is two files joined. The evidence still records
        #: the left file as its source, because that is where the rows live;
        #: the label is what the reader is told the figure was computed over.
        self.join_label = ""

    @property
    def display_name(self) -> str:
        return self.join_label or self.file_name

    def column_values(self, column: str) -> list[str]:
        return [str(row.get(column, "")) for row in self.rows]

    def matches(self, name: str) -> bool:
        candidate = (name or "").strip().casefold()
        if not candidate:
            return True
        return candidate in {
            self.file_name.casefold(),
            self.source_id.casefold(),
            self.file_name.rsplit(".", 1)[0].casefold(),
        }


def structured_datasets(source_registry: list[dict]) -> list[Dataset]:
    """Every supplied source that is a table, read back as records."""
    datasets: list[Dataset] = []
    for entry in source_registry or []:
        rows: list[dict] = []
        for block in entry.get("parsed_content") or []:
            if not isinstance(block, dict):
                continue
            if block.get("block_type") not in _ROW_BLOCK_TYPES:
                continue
            try:
                record = json.loads(str(block.get("content") or ""))
            except (ValueError, TypeError):
                continue
            if isinstance(record, dict):
                rows.append(record)
        if len(rows) >= 2:
            datasets.append(Dataset(entry, rows))
    return datasets


# ----------------------------------------------------------------------
# Row filters
# ----------------------------------------------------------------------

_FILTER_RE = re.compile(r"^\s*(?P<col>[^!=<>~]+?)\s*(?P<op>!=|>=|<=|=|>|<|~)\s*(?P<val>.*?)\s*$")


def _row_matches(row: dict, column: str, op: str, wanted: str) -> bool:
    raw = row.get(column)
    text = "" if raw is None else str(raw).strip()
    if op in {"=", "!="}:
        hit = text.casefold() == wanted.casefold()
        return hit if op == "=" else not hit
    if op == "~":
        return wanted.casefold() in text.casefold()
    left, right = parse_number(text), parse_number(wanted)
    if left is None or right is None:
        return False
    if op == ">":
        return left > right
    if op == ">=":
        return left >= right
    if op == "<":
        return left < right
    return left <= right


def filter_rows(rows: list[dict], dataset: Dataset, expression: str | None) -> list[dict]:
    """The subset of ``rows`` an expression names.

    Taking the rows as an argument rather than reading them off the dataset is
    what lets one measure run inside a group: the same filter that means "the
    listings under four stars" over a whole file has to mean "the listings
    under four stars *in this price band*" inside a cross table, and a filter
    that quietly reached past its group would put the file's number in every
    row of the table.
    """
    text = (expression or "").strip()
    if not text or text == "*":
        return list(rows)
    selected = list(rows)
    for clause in text.split("&"):
        match = _FILTER_RE.match(clause)
        if not match:
            raise DerivationError(
                f"Row filter {clause.strip()!r} is not of the form "
                "column=value, column>=number, or column~text"
            )
        column = match.group("col").strip()
        if column not in dataset.columns:
            raise DerivationError(
                f"Row filter names column {column!r}, which {dataset.file_name} "
                f"does not have. Its columns are: {', '.join(dataset.columns[:12])}"
            )
        op, wanted = match.group("op"), match.group("val")
        selected = [row for row in selected if _row_matches(row, column, op, wanted)]
    return selected


def select_rows(dataset: Dataset, expression: str | None) -> list[dict]:
    """The rows of one dataset an expression names.

    ``category=攝影``, ``price>=100``, ``brand~DJI``, joined with ``&``. An
    empty expression is every row, which is the ordinary case for a sample
    size or a median.
    """
    return filter_rows(dataset.rows, dataset, expression)


# ----------------------------------------------------------------------
# Operations
# ----------------------------------------------------------------------


def _numbers(rows: list[dict], column: str) -> list[float]:
    parsed = (parse_number(row.get(column)) for row in rows)
    return [value for value in parsed if value is not None]


def _group_counts(rows: list[dict], column: str) -> list[tuple[str, int]]:
    counts: dict[str, int] = {}
    for row in rows:
        key = str(row.get(column, "")).strip()
        if not key:
            continue
        counts[key] = counts.get(key, 0) + 1
    return sorted(counts.items(), key=lambda item: (-item[1], item[0]))


def format_number(value: float) -> str:
    """Thousands-separated, and no more precise than the value warrants."""
    if abs(value - round(value)) < 1e-9 and abs(value) < 1e15:
        return f"{round(value):,}"
    if abs(value) >= 1:
        return f"{value:,.2f}"
    return f"{value:.4g}"


def _check_op(dataset: Dataset, request: dict) -> tuple[str, str]:
    """The (op, column) a request names, or the reason it cannot be carried out."""
    op = str(request.get("op") or "").strip().lower()
    if op not in SUPPORTED_OPS:
        raise DerivationError(
            f"Operation {op!r} is not supported. Use one of: {', '.join(SUPPORTED_OPS)}"
        )
    column = str(request.get("column") or "").strip()
    if op != "count" and op != "share" and not column:
        raise DerivationError(f"Operation {op!r} needs a 'column'")
    if column and column not in dataset.columns:
        raise DerivationError(
            f"Column {column!r} is not in {dataset.display_name}. Its columns are: "
            f"{', '.join(dataset.columns[:12])}"
        )
    return op, column


def _op_value(
    op: str,
    rows: list[dict],
    universe: list[dict],
    dataset: Dataset,
    column: str,
    request: dict,
) -> tuple[float, str, str]:
    """One operation over one row set: ``(value, unit, detail)``.

    ``universe`` is what a share is a share *of* when the request names no
    denominator. Over a whole file that is the file; inside a cross table it is
    the group, so "the share under four stars" is read per band rather than
    silently repeating the file-wide figure in every row.

    Raises when the selected rows state nothing, which the grouped path reads
    as an empty cell rather than as a failed run.
    """
    unit = ""
    detail = ""
    if op == "count":
        value = float(
            sum(1 for row in rows if str(row.get(column, "")).strip())
            if column
            else len(rows)
        )
    elif op == "distinct":
        value = float(len({
            str(row.get(column, "")).strip()
            for row in rows
            if str(row.get(column, "")).strip()
        }))
    elif op in {"sum", "mean", "median", "min", "max"}:
        numbers = _numbers(rows, column)
        if not numbers:
            raise DerivationError(
                f"Column {column!r} holds no numbers in the {len(rows)} selected row(s)"
            )
        value = float({
            "sum": sum,
            "mean": statistics.fmean,
            "median": statistics.median,
            "min": min,
            "max": max,
        }[op](numbers))
        unit = _currency_unit(dataset.column_values(column))
        if not unit and _is_percent_column(column, dataset.column_values(column)):
            unit = "%"
        detail = f"{len(numbers)} of {len(rows)} selected rows carry a number"
    elif op == "share":
        whole = filter_rows(universe, dataset, str(request.get("of") or ""))
        if not whole:
            raise DerivationError("Share has no denominator: the 'of' selection is empty")
        value = len(rows) / len(whole) * 100
        unit = "%"
        detail = f"{len(rows)} of {len(whole)}"
    elif op == "hhi":
        counts = _group_counts(rows, column)
        total = sum(count for _name, count in counts)
        if not total:
            raise DerivationError(f"Column {column!r} is empty in the selected rows")
        value = sum((count / total * 100) ** 2 for _name, count in counts)
        detail = f"{len(counts)} groups over {total} rows"
    else:  # top_share — the CR-k concentration ratio
        k = max(1, int(request.get("k") or 5))
        counts = _group_counts(rows, column)
        total = sum(count for _name, count in counts)
        if not total:
            raise DerivationError(f"Column {column!r} is empty in the selected rows")
        value = sum(count for _name, count in counts[:k]) / total * 100
        unit = "%"
        detail = "top " + ", ".join(name for name, _count in counts[:k])
    return value, unit, detail


def compute(dataset: Dataset, request: dict) -> dict:
    """Carry out one derivation and report how it was carried out.

    Returns ``{"value", "unit", "rows_used", "detail", "derivation"}``. The
    caller never supplies the value; that is the point.
    """
    op, column = _check_op(dataset, request)
    rows_expression = str(request.get("rows") or "")
    rows = select_rows(dataset, rows_expression)
    value, unit, detail = _op_value(
        op, rows, dataset.rows, dataset, column, request
    )

    derivation = {
        "method": op,
        "source_file": dataset.display_name,
        "row_filter": rows_expression or "*",
        "rows_matched": len(rows),
        "rows_total": len(dataset.rows),
        "input_columns": [column] if column else list(dataset.columns[:12]),
    }
    if op == "top_share":
        derivation["k"] = max(1, int(request.get("k") or 5))
    if op == "share":
        derivation["denominator_filter"] = str(request.get("of") or "*")
    return {
        "value": value,
        "unit": unit,
        "rows_used": len(rows),
        "detail": detail,
        "derivation": derivation,
    }


# ----------------------------------------------------------------------
# Two files, joined
# ----------------------------------------------------------------------


def _stem(file_name: str) -> str:
    return _ID_SAFE_RE.sub("_", str(file_name or "").rsplit(".", 1)[0]).strip("_") or "right"


def join_datasets(left: Dataset, right: Dataset, spec: dict) -> Dataset:
    """Two tables on one key, as one frame of rows.

    The strongest finding of a market study is usually the one no single file
    states: the products table holds the price and the reviews table holds what
    buyers said, and "which price band do buyers rate worst" lives in neither
    until they are joined. Without this the sentence is simply not written —
    not blocked, not hedged, not written.

    Rows that find no partner are dropped, and *how many* were dropped is
    recorded rather than swallowed: a hundred reviews that cannot be traced to
    a listing is itself a limitation the report should state.
    """
    how = str(spec.get("how") or "inner").strip().lower()
    if how != "inner":
        raise DerivationError(
            f"Join type {how!r} is not supported yet; use \"inner\""
        )
    left_key = str(spec.get("left_on") or spec.get("on") or "").strip()
    right_key = str(spec.get("right_on") or spec.get("on") or "").strip()
    if not left_key or not right_key:
        raise DerivationError(
            "A join needs 'on' (the key both files share), or 'left_on' and 'right_on'"
        )
    for key, dataset in ((left_key, left), (right_key, right)):
        if key not in dataset.columns:
            raise DerivationError(
                f"Join key {key!r} is not in {dataset.file_name}. Its columns are: "
                f"{', '.join(dataset.columns[:12])}"
            )

    # A name that exists on both sides is renamed rather than overwritten. A
    # silent overwrite would put the products table's rating in a column the
    # request thinks holds the review's, and the number would be wrong in a way
    # no gate could see.
    suffix = _stem(right.file_name)
    renamed = {
        column: f"{column}__{suffix}"
        for column in right.columns
        if column in left.columns and column != right_key
    }

    index: dict[str, list[dict]] = {}
    for row in right.rows:
        key = str(row.get(right_key, "")).strip()
        if key:
            index.setdefault(key, []).append(row)

    rows: list[dict] = []
    left_matched = 0
    keys_hit: set[str] = set()
    for row in left.rows:
        key = str(row.get(left_key, "")).strip()
        partners = index.get(key) or []
        if not partners:
            continue
        left_matched += 1
        keys_hit.add(key)
        for partner in partners:
            merged = dict(row)
            for column, value in partner.items():
                merged[renamed.get(column, column)] = value
            rows.append(merged)

    right_matched = sum(len(index[key]) for key in keys_hit)
    frame = Dataset(
        {
            "source_id": left.source_id,
            "file_name": left.file_name,
            "file_path": left.file_path,
            "file_type": left.file_type,
        },
        rows,
    )
    frame.join_label = f"{left.file_name} ⋈ {right.file_name}"
    frame.join_info = {
        "join": how,
        "join_key": left_key if left_key == right_key else f"{left_key}={right_key}",
        "left_file": left.file_name,
        "right_file": right.file_name,
        "left_rows": len(left.rows),
        "right_rows": len(right.rows),
        "joined_rows": len(rows),
        "left_unmatched": len(left.rows) - left_matched,
        "right_unmatched": len(right.rows) - right_matched,
        "renamed_columns": renamed,
    }
    return frame


def resolve_frame(request: dict, datasets: list[Dataset]) -> Dataset:
    """The rows one request runs over: a file, or two of them joined."""
    wanted = request.get("source")
    names = [str(name or "") for name in (wanted if isinstance(wanted, list) else [wanted])]
    available = ", ".join(dataset.file_name for dataset in datasets) or "(none)"
    picked: list[Dataset] = []
    for name in names:
        candidates = [dataset for dataset in datasets if dataset.matches(name)]
        if not candidates:
            raise DerivationError(
                f"No structured source matches {name!r}. Available: {available}"
            )
        picked.append(candidates[0])

    join_spec = request.get("join")
    if len(picked) == 1:
        if join_spec:
            raise DerivationError(
                "A 'join' needs two file names in 'source', for example "
                '"source": ["reviews.csv", "products.csv"]'
            )
        return picked[0]
    if len(picked) != 2:
        raise DerivationError(
            "'source' takes one file name, or two to join them"
        )
    if not isinstance(join_spec, dict):
        raise DerivationError(
            "Two sources need a 'join' saying which key connects them, for "
            'example "join": {"on": "asin", "how": "inner"}'
        )
    return join_datasets(picked[0], picked[1], join_spec)


# ----------------------------------------------------------------------
# Grouped tables: one request, N rows, one evidence entry
# ----------------------------------------------------------------------


def _bucket_edges(buckets: object) -> list[float]:
    if not isinstance(buckets, (list, tuple)) or len(buckets) < 2:
        raise DerivationError(
            "group_by.buckets must list at least two boundaries, for example "
            "[0, 30, 50, 100, 200, 400]"
        )
    edges = [parse_number(bucket) for bucket in buckets]
    if any(edge is None for edge in edges):
        raise DerivationError("group_by.buckets must all be numbers")
    values = [float(edge) for edge in edges]  # type: ignore[arg-type]
    if any(later <= earlier for earlier, later in zip(values, values[1:])):
        raise DerivationError("group_by.buckets must increase")
    return values


def _band_label(low: float, high: float | None) -> str:
    if high is None:
        return f"{format_number(low)}+"
    return f"{format_number(low)}–{format_number(high)}"


def _bucket_groups(
    rows: list[dict], column: str, edges: list[float]
) -> tuple[list[tuple[str, list[dict]]], int]:
    """Rows in author-chosen bands, plus how many fell outside every band.

    The boundaries are the author's. Where to cut a price axis is an analytical
    judgement — the bands are the finding, not an input to it — and a tool that
    guesses them is wrong in a way the reader cannot see.
    """
    groups: list[tuple[str, list[dict]]] = [
        (_band_label(low, high), []) for low, high in zip(edges, edges[1:])
    ]
    groups.append((_band_label(edges[-1], None), []))
    outside = 0
    for row in rows:
        value = parse_number(row.get(column))
        if value is None or value < edges[0]:
            outside += 1
            continue
        index = len(edges) - 1
        for position, (low, high) in enumerate(zip(edges, edges[1:])):
            if low <= value < high:
                index = position
                break
        groups[index][1].append(row)
    return groups, outside


def _category_groups(
    rows: list[dict], column: str, top: int, zh: bool
) -> tuple[list[tuple[str, list[dict]]], int]:
    buckets: dict[str, list[dict]] = {}
    empty = 0
    for row in rows:
        key = str(row.get(column, "")).strip()
        if not key:
            empty += 1
            continue
        buckets.setdefault(key, []).append(row)
    ordered = sorted(buckets.items(), key=lambda item: (-len(item[1]), item[0]))
    if len(ordered) <= top:
        return ordered, empty
    head = ordered[:top]
    tail = ordered[top:]
    spilled = [row for _name, group in tail for row in group]
    label = (
        f"其他（{len(tail)} 組）" if zh else f"Other ({len(tail)} groups)"
    )
    return head + [(label, spilled)], empty


def _measure_label(measure: dict, zh: bool) -> str:
    label = str(measure.get("label") or "").strip()
    if label:
        return label
    op = str(measure.get("op") or "").strip().lower()
    column = str(measure.get("column") or "").strip()
    rows_expression = str(measure.get("rows") or "").strip()
    if zh:
        names = {
            "count": "筆數", "sum": "總和", "mean": "平均", "median": "中位數",
            "min": "最小值", "max": "最大值", "distinct": "相異值數",
            "share": "佔比", "hhi": "HHI", "top_share": "前段佔比",
        }
        base = f"{column} {names.get(op, op)}" if column else names.get(op, op)
        return f"{base}（{rows_expression}）" if rows_expression else base
    base = f"{op} of {column}" if column else op
    return f"{base} where {rows_expression}" if rows_expression else base


#: Operations whose result is continuous, so a cell that lands on a round
#: number still states two decimals. The content check refuses a claim with
#: more decimal places than its evidence, so a mean printed as "4" silently
#: forbids writing "4.0" — the author's arithmetic is right and the sentence is
#: blocked anyway.
_CONTINUOUS_OPS = frozenset({"mean", "median", "share"})


def _render_cell(value: float | None, unit: str, *, fixed: bool = False) -> str:
    if value is None:
        return "—"
    text = f"{value:,.2f}" if fixed else format_number(value)
    if unit == "%":
        return f"{text}%"
    return f"{text} {unit}" if unit else text


def _integer_band_members(edges: list[float], zh: bool) -> list[str]:
    """What each half-open band actually contains, when the column is integral.

    A band cut at [1, 3) over star ratings is labelled 1-3 and holds 1 and 2.
    An author who reads the table writes 「1-2 星」, which is correct, and the
    content check refused it: the digit 2 appears nowhere in the evidence. The
    same sentence passed when it cited a table whose column header happened to
    spell the range out -- same fact, same words, opposite verdict depending on
    a header. So the membership is stated, and the figure the author will reach
    for is in the text.

    Only for integral columns. Spelling a price band as "0 to 29" when the data
    holds 29.99 would be a statement about the band that is false about the
    data.
    """
    members: list[str] = []
    for low, high in zip(edges, edges[1:]):
        first, last = int(low), int(high) - 1
        if last < first:
            members.append(f"{first}")
        elif last == first:
            members.append(f"{first}")
        else:
            members.append(f"{first} 至 {last}" if zh else f"{first} to {last}")
    last_edge = int(edges[-1])
    members.append(f"{last_edge} 及以上" if zh else f"{last_edge} and above")
    return members


def _column_is_integral(frame: Dataset, column: str) -> bool:
    numbers = [
        value for value in (parse_number(cell) for cell in frame.column_values(column))
        if value is not None
    ]
    return bool(numbers) and all(abs(value - round(value)) < 1e-9 for value in numbers)


def compute_group_table(frame: Dataset, request: dict, zh: bool = False) -> dict:
    """One grouped table: a row per group, a column per measure.

    The scalar operations answer one question each, so a six-band table with
    three columns took eighteen registrations to build — and a real run
    registered 117 of them to produce three tables. The shape of the request
    was the cost, not the analysis: this returns the whole table from one
    request, and the ledger records it as one entry.
    """
    spec = request.get("group_by")
    if not isinstance(spec, dict):
        raise DerivationError(
            "A grouped derivation needs 'group_by', for example "
            '{"column": "price", "buckets": [0, 30, 50, 100, 200, 400]}'
        )
    column = str(spec.get("column") or "").strip()
    if not column:
        raise DerivationError("group_by needs a 'column'")
    if column not in frame.columns:
        raise DerivationError(
            f"group_by column {column!r} is not in {frame.display_name}. Its "
            f"columns are: {', '.join(frame.columns[:12])}"
        )
    measures = request.get("measures")
    if not isinstance(measures, list) or not measures:
        raise DerivationError(
            "A grouped derivation needs 'measures', a list of operations — one "
            'per output column, for example [{"op": "count"}, '
            '{"op": "mean", "column": "rating"}]'
        )
    measures = [measure for measure in measures if isinstance(measure, dict)]
    if not measures:
        raise DerivationError("'measures' entries must be objects")

    rows_expression = str(request.get("rows") or "")
    scoped = select_rows(frame, rows_expression)

    buckets = spec.get("buckets")
    if buckets is not None:
        edges = _bucket_edges(buckets)
        groups, outside = _bucket_groups(scoped, column, edges)
        grouping = "buckets"
    else:
        top = int(spec.get("top") or MAX_GROUPS_IN_TABLE)
        groups, outside = _category_groups(scoped, column, max(1, top), zh)
        grouping = "categories"
        edges = []
    if not groups or all(not members for _label, members in groups):
        raise DerivationError(
            f"Grouping {frame.display_name} by {column!r} produced no rows. "
            f"{outside} of {len(scoped)} selected row(s) hold no usable value there."
        )

    checked = [(_check_op(frame, measure), measure) for measure in measures]
    headers = [str(spec.get("label") or column)] + [
        _measure_label(measure, zh) for _pair, measure in checked
    ]
    # The unit of a column is a property of the column, not of the group, so it
    # is settled once over the whole selection. Deriving it per cell let one
    # empty band drop the currency from that row alone, and a table where the
    # same quantity is written two ways reads as two quantities.
    def _universe(op: str, measure: dict, members: list[dict]) -> list[dict]:
        """What a share in this cell is a share of.

        A share with no numerator filter can only mean "this group as a
        fraction of the whole" -- taken against the group it is 100% in every
        row, which is a column of noise. A share that *does* filter is a rate
        inside the group: the point of "% under four stars by price band" is
        that each band is measured against itself.
        """
        if op == "share" and not str(measure.get("rows") or "").strip():
            return scoped
        return members

    units: list[str] = []
    for (op, measure_column), measure in checked:
        try:
            _value, unit, _detail = _op_value(
                op,
                filter_rows(scoped, frame, str(measure.get("rows") or "")),
                scoped,
                frame,
                measure_column,
                measure,
            )
        except DerivationError:
            unit = ""
        units.append(unit)

    def measured(members: list[dict]) -> list[str]:
        cells: list[str] = []
        for index, ((op, measure_column), measure) in enumerate(checked):
            selected = filter_rows(members, frame, str(measure.get("rows") or ""))
            try:
                value, _unit, _detail = _op_value(
                    op, selected, _universe(op, measure, members), frame,
                    measure_column, measure,
                )
            except DerivationError:
                value = None
            cells.append(_render_cell(value, units[index], fixed=op in _CONTINUOUS_OPS))
        return cells

    body = [[label, *measured(members)] for label, members in groups]
    if request.get("total_row", True):
        covered = [row for _label, members in groups for row in members]
        body.append(["合計" if zh else "All", *measured(covered)])

    covered_rows = sum(len(members) for _label, members in groups)
    derivation = {
        "method": "group_table",
        "source_file": frame.display_name,
        "row_filter": rows_expression or "*",
        "rows_matched": covered_rows,
        "rows_total": len(frame.rows),
        "input_columns": [column]
        + [str(measure.get("column") or "") for measure in measures if measure.get("column")],
        "group_by": column,
        "grouping": grouping,
        "groups": len(groups),
        "rows_ungrouped": outside,
        "measures": [
            {
                "op": op,
                "column": measure_column,
                "rows": str(measure.get("rows") or "*"),
                "label": header,
            }
            for ((op, measure_column), measure), header in zip(checked, headers[1:])
        ],
    }
    if grouping == "buckets":
        derivation["buckets"] = edges
        if _column_is_integral(frame, column):
            derivation["band_members"] = _integer_band_members(edges, zh)
    join_info = getattr(frame, "join_info", None)
    if join_info:
        derivation["join"] = join_info

    return {
        "headers": headers,
        "rows": body,
        "derivation": derivation,
        "groups": len(groups),
        "rows_ungrouped": outside,
    }


def _group_table_text(frame: Dataset, request: dict, table: dict, zh: bool) -> str:
    """The table as evidence text, with every cell readable in place.

    Written as a grid rather than a sentence because a gate reads it the same
    way a person does — looking for the number — and a paragraph that buries
    eighteen figures in prose is checkable by neither.
    """
    derivation = table["derivation"]
    label = str(request.get("label") or "").strip()
    grid = [" | ".join(row) for row in [table["headers"], *table["rows"]]]
    ungrouped = derivation.get("rows_ungrouped", 0)
    join_info = derivation.get("join") or {}
    # A band cut at [1, 3) is labelled 1-3 and holds 1 and 2. An author
    # reading the table writes 「1-2 星」, correctly, and the content check
    # refused it for a digit 2 the evidence never spelled out. So the
    # membership is stated, and the figure they will reach for is there.
    members = derivation.get("band_members") or []
    membership = ""
    if members:
        pairs = ", ".join(
            f"{label}={member}"
            for label, member in zip([row[0] for row in table["rows"]], members)
        )
        membership = (
            f"各組實際涵蓋的值：{pairs}。" if zh
            else f"Each band covers: {pairs}. "
        )
    if zh:
        head = (
            f"衍生統計(來源:{frame.display_name}):"
            f"{label or derivation['group_by'] + ' 分組表'}。"
            f"依 {derivation['group_by']} 分為 {derivation['groups']} 組，"
            f"涵蓋 {derivation['rows_matched']} 筆資料列"
            f"（全檔 {derivation['rows_total']} 筆）。"
        )
        if ungrouped:
            head += f"另有 {ungrouped} 筆在該欄無可用值，未列入分組。"
        if join_info:
            head += (
                f"本表由 {join_info['left_file']} 與 {join_info['right_file']} "
                f"以 {join_info['join_key']} 內接而成，"
                f"接得 {join_info['joined_rows']} 筆；"
                f"{join_info['left_file']} 有 {join_info['left_unmatched']} 筆、"
                f"{join_info['right_file']} 有 {join_info['right_unmatched']} 筆接不上。"
            )
    else:
        head = (
            f"Derived statistics from {frame.display_name}: "
            f"{label or derivation['group_by'] + ' breakdown'}. "
            f"Grouped by {derivation['group_by']} into {derivation['groups']} "
            f"groups covering {derivation['rows_matched']} of "
            f"{derivation['rows_total']} rows."
        )
        if ungrouped:
            head += f" A further {ungrouped} row(s) hold no usable value there."
        if join_info:
            head += (
                f" Built by inner-joining {join_info['left_file']} to "
                f"{join_info['right_file']} on {join_info['join_key']}, giving "
                f"{join_info['joined_rows']} joined row(s); "
                f"{join_info['left_unmatched']} row(s) of "
                f"{join_info['left_file']} and {join_info['right_unmatched']} of "
                f"{join_info['right_file']} found no partner."
            )
    return head + membership + "\n" + "\n".join(grid)


# ----------------------------------------------------------------------
# Evidence units
# ----------------------------------------------------------------------


def _unit_evidence(
    dataset: Dataset,
    content: str,
    derivation: dict,
    created_at: str,
    *,
    evidence_id: str,
    block_id: str,
    origin: str = "auto",
    table: dict | None = None,
) -> dict:
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    matched = derivation.get("rows_matched", len(dataset.rows))
    unit = {
        "evidence_id": evidence_id,
        "source_id": dataset.source_id,
        "source_file_name": dataset.file_name,
        "source_file_path": dataset.file_path,
        "file_type": dataset.file_type,
        "source_role": "source_data",
        "granularity": "dataset",
        "evidence_type": "quantitative",
        "content": content,
        "quote": content[:200],
        "source_span": f"{dataset.file_name} ({matched} rows)",
        "line_start": None,
        "line_end": None,
        "content_hash": digest[:16],
        "provenance_score": 0.75,
        "evidence_grade": "high",
        "allowed_claim_types": ["factual", "statistical"],
        "block_id": block_id,
        # Not a row block type on purpose: a derived statistic is a statement
        # about the whole selection, so the single-row rules in the factuality
        # checker must not apply to it.
        "block_type": "derived_statistic",
        "page_number": None,
        "requires_hedged_wording": False,
        "first_hand_account": False,
        "contains_methodology": True,
        "contains_citations": False,
        "claimed_reproducibility": True,
        "topic_tags": ["statistical"],
        "cross_references": [],
        "created_at": created_at,
        "last_used": None,
        # Who asked for this. The whole point of the grouped and joined shapes
        # is that the tool does the aggregating, so "how many of these did the
        # author have to register by hand" is the measurement that says whether
        # it worked; without the field it cannot be counted.
        "origin": origin,
        "derivation": derivation,
    }
    if table:
        # A grid a [TABLE:] marker can place in the document, so a table the
        # pipeline computed reaches the reader as a table rather than as a
        # paragraph the author retypes -- retyped numbers being backed by
        # nothing, which is the failure this ledger exists to prevent.
        unit["table_grid"] = {"headers": table["headers"], "rows": table["rows"]}
        unit["table_id"] = evidence_id
    return unit


def _shape_text(dataset: Dataset, zh: bool) -> tuple[str, dict]:
    filled = [
        (column, sum(1 for row in dataset.rows if str(row.get(column, "")).strip()))
        for column in dataset.columns[:MAX_COLUMNS_SUMMARIZED]
    ]
    if zh:
        parts = "、".join(f"{column} {count} 筆" for column, count in filled)
        # Worded the way an author writes it, not the way a schema reads. A
        # summary phrased only as "本檔共 N 筆資料列" shares no vocabulary with
        # "本樣本共收錄 N 筆商品", and the term check then refuses the claim it
        # exists to support.
        text = (
            f"衍生統計(來源:{dataset.file_name}):本樣本共收錄 {len(dataset.rows)} 筆資料列，"
            f"總筆數 {len(dataset.rows)} 筆，欄位 {len(dataset.columns)} 個。"
            f"各欄有值筆數為 {parts}。"
        )
    else:
        parts = ", ".join(f"{column} {count}" for column, count in filled)
        text = (
            f"Derived statistics from {dataset.file_name}: the file holds "
            f"{len(dataset.rows)} data rows across {len(dataset.columns)} columns. "
            f"Non-empty value counts by column: {parts}."
        )
    return text, {
        "method": "row_count",
        "source_file": dataset.file_name,
        "row_filter": "*",
        "rows_matched": len(dataset.rows),
        "rows_total": len(dataset.rows),
        "input_columns": [column for column, _count in filled],
    }


def _numeric_text(
    dataset: Dataset,
    column: str,
    numbers: list[float],
    zh: bool,
) -> tuple[str, dict]:
    values = dataset.column_values(column)
    unit = _currency_unit(values)
    if not unit and _is_percent_column(column, values):
        unit = "%"
    suffix = "%" if unit == "%" else (f" {unit}" if unit else "")

    def rendered(value: float) -> str:
        return f"{format_number(value)}{suffix}"

    ordered = sorted(numbers)
    lower = ordered[len(ordered) // 4]
    upper = ordered[(3 * len(ordered)) // 4] if len(ordered) >= 4 else ordered[-1]
    if zh:
        text = (
            f"衍生統計(來源:{dataset.file_name}):{column} 欄共 {len(numbers)} 筆數值，"
            f"最小值 {rendered(min(numbers))}，第一四分位 {rendered(lower)}，"
            f"中位數 {rendered(statistics.median(numbers))}，"
            f"平均數 {rendered(statistics.fmean(numbers))}，"
            f"第三四分位 {rendered(upper)}，最大值 {rendered(max(numbers))}。"
        )
    else:
        text = (
            f"Derived statistics from {dataset.file_name}: the {column} column holds "
            f"{len(numbers)} values, ranging from {rendered(min(numbers))} to "
            f"{rendered(max(numbers))}, with a first quartile of {rendered(lower)}, "
            f"a median of {rendered(statistics.median(numbers))}, a mean of "
            f"{rendered(statistics.fmean(numbers))}, and a third quartile of "
            f"{rendered(upper)}."
        )
    return text, {
        "method": "column_summary_stats",
        "source_file": dataset.file_name,
        "row_filter": "*",
        "rows_matched": len(numbers),
        "rows_total": len(dataset.rows),
        "input_columns": [column],
        "unit": unit,
    }


def _category_text(
    dataset: Dataset,
    column: str,
    counts: list[tuple[str, int]],
    zh: bool,
) -> tuple[str, dict]:
    total = sum(count for _name, count in counts)
    listed = counts[:MAX_GROUPS_LISTED]
    hhi = sum((count / total * 100) ** 2 for _name, count in counts)
    cr5 = sum(count for _name, count in counts[:5]) / total * 100
    if zh:
        parts = "、".join(
            f"{name} {count} 筆({count / total * 100:.1f}%)" for name, count in listed
        )
        text = (
            f"衍生統計(來源:{dataset.file_name}):{column} 欄共 {len(counts)} 個相異值、"
            f"{total} 筆有值資料列。分布為 {parts}。"
            f"前五大合計佔 {cr5:.1f}%，以此欄計算的 HHI 為 {hhi:.0f}。"
        )
    else:
        parts = ", ".join(
            f"{name} {count} ({count / total * 100:.1f}%)" for name, count in listed
        )
        text = (
            f"Derived statistics from {dataset.file_name}: the {column} column has "
            f"{len(counts)} distinct values across {total} non-empty rows. "
            f"Distribution: {parts}. The top five account for {cr5:.1f}% and the "
            f"HHI computed on this column is {hhi:.0f}."
        )
    return text, {
        "method": "group_counts",
        "source_file": dataset.file_name,
        "row_filter": "*",
        "rows_matched": total,
        "rows_total": len(dataset.rows),
        "input_columns": [column],
        "groups_listed": len(listed),
        "groups_total": len(counts),
    }


def dataset_summary_units(
    source_registry: list[dict],
    created_at: str,
    zh: bool = False,
) -> list[dict]:
    """Summary statistics for every structured source, as ledger entries.

    One unit for the shape of the file, one per numeric column, one per
    categorical column. These exist whether or not anybody asks, because the
    author who most needs them is the one who does not yet know the ledger
    cannot answer the question they are about to stop asking.
    """
    units: list[dict] = []
    for dataset in structured_datasets(source_registry):
        shape_content, shape_derivation = _shape_text(dataset, zh)
        entries: list[tuple[str, dict, dict | None]] = [
            (shape_content, shape_derivation, None)
        ]
        for column in dataset.columns[:MAX_COLUMNS_SUMMARIZED]:
            if _ID_COLUMN_RE.search(str(column)):
                continue
            values = dataset.column_values(column)
            filled = [value for value in values if str(value).strip()]
            if not filled:
                continue
            parsed = [parse_number(value) for value in filled]
            numbers = [number for number in parsed if number is not None]
            if len(numbers) >= 2 and len(numbers) / len(filled) >= NUMERIC_COLUMN_THRESHOLD:
                numeric_content, numeric_derivation = _numeric_text(
                    dataset, column, numbers, zh
                )
                entries.append((numeric_content, numeric_derivation, None))
                continue
            counts = _group_counts(dataset.rows, column)
            # A column whose values are nearly all distinct is a title or a
            # description, not a category. Its "distribution" is the column
            # reprinted with 1 beside every line, which tells a reader
            # nothing and buries the columns that do.
            if len(counts) > max(2, 0.9 * len(dataset.rows)):
                continue
            if 2 <= len(counts) <= MAX_CATEGORY_CARDINALITY:
                category_content, category_derivation = _category_text(
                    dataset, column, counts, zh
                )
                entries.append((category_content, category_derivation, None))

        entries.extend(_auto_cross_tables(dataset, zh))

        for index, (content, derivation, table) in enumerate(entries):
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            units.append(
                _unit_evidence(
                    dataset,
                    content,
                    derivation,
                    created_at,
                    evidence_id=f"E_{dataset.source_id}_{digest[:10]}",
                    block_id=f"summary_{index}",
                    origin="auto",
                    table=table,
                )
            )
    return units


def _column_kinds(dataset: Dataset) -> tuple[list[str], list[str]]:
    """(categorical columns, numeric columns) worth crossing with each other."""
    categorical: list[tuple[int, int, str]] = []
    numeric: list[str] = []
    for column in dataset.columns[:MAX_COLUMNS_SUMMARIZED]:
        if _ID_COLUMN_RE.search(str(column)):
            continue
        values = dataset.column_values(column)
        filled = [value for value in values if str(value).strip()]
        if not filled:
            continue
        parsed = [parse_number(value) for value in filled]
        numbers = [number for number in parsed if number is not None]
        if len(numbers) >= 2 and len(numbers) / len(filled) >= NUMERIC_COLUMN_THRESHOLD:
            numeric.append(column)
            continue
        counts = _group_counts(dataset.rows, column)
        # A column with a value per row is a title, not a category, and a
        # 544-row "breakdown" is the file reprinted.
        if not 2 <= len(counts) <= MAX_CATEGORY_CARDINALITY:
            continue
        if len(counts) > max(2, 0.5 * len(dataset.rows)):
            continue
        # A column filled in for a handful of rows describes those rows, not
        # the file. Crossing `seller` — stated on 11 listings out of 544 — puts
        # a table of eleven ones in front of the author as if it were a market
        # structure.
        if len(filled) < 0.05 * len(dataset.rows):
            continue
        categorical.append((-len(filled), len(counts), column))
    return [column for _filled, _groups, column in sorted(categorical)], numeric


def _auto_cross_tables(
    dataset: Dataset, zh: bool
) -> list[tuple[str, dict, dict]]:
    """The cross tabulations nobody had to ask for.

    An unassisted write-up of the same three files built thirteen tables by
    hand, every one of them a group-by; the tool offered single-column
    statistics and the author had to register a hundred-odd derivations before
    the first table existed. So the obvious crossings — each category column
    against the numeric ones — are computed at intake, and the author starts
    with material instead of with bricks.

    Bins are not guessed. A numeric column is averaged inside a category, never
    cut into bands the author did not choose.
    """
    categorical, numeric = _column_kinds(dataset)
    if not categorical:
        return []
    measures: list[dict] = [
        {"op": "count", "label": "筆數" if zh else "rows"},
        {"op": "share", "label": "佔比" if zh else "share of rows"},
    ]
    # Mean and median for the first two numeric columns, median alone after
    # that. A table wide enough to need landscape orientation is not read, and
    # the median is the figure a market write-up quotes.
    for position, column in enumerate(numeric[:MAX_AUTO_MEASURE_COLUMNS]):
        if position < 2:
            measures.append({
                "op": "mean",
                "column": column,
                "label": f"{column} 平均" if zh else f"mean {column}",
            })
        measures.append({
            "op": "median",
            "column": column,
            "label": f"{column} 中位數" if zh else f"median {column}",
        })

    tables: list[tuple[str, dict, dict]] = []
    for column in categorical[:MAX_AUTO_CROSS_TABLES]:
        request = {
            "group_by": {"column": column},
            "measures": measures,
            "label": (
                f"{column} 分組交叉表" if zh else f"{column} breakdown"
            ),
        }
        try:
            table = compute_group_table(dataset, request, zh=zh)
        except DerivationError:
            continue
        table["derivation"]["origin"] = "auto"
        tables.append((
            _group_table_text(dataset, request, table, zh),
            table["derivation"],
            table,
        ))
    return tables


# ----------------------------------------------------------------------
# Author-requested derivations
# ----------------------------------------------------------------------

_ID_SAFE_RE = re.compile(r"[^A-Za-z0-9_]+")


def request_evidence_id(request_id: str) -> str:
    """The id a registered derivation will have, before it is computed.

    Predictable on purpose: an author writes ``[CITE:E_D_photo_count]`` into a
    draft, and the pipeline has to produce exactly that id or the citation
    they were told to write does not resolve.
    """
    return "E_D_" + _ID_SAFE_RE.sub("_", str(request_id or "").strip())[:48]


def _request_text(request: dict, dataset: Dataset, result: dict, zh: bool) -> str:
    label = str(request.get("label") or "").strip()
    op = str(request.get("op")).lower()
    column = str(request.get("column") or "")
    rows_expression = result["derivation"]["row_filter"]
    value = format_number(result["value"])
    unit = result["unit"]
    rendered = f"{value}%" if unit == "%" else (f"{value} {unit}".strip() if unit else value)
    if zh:
        scope = "全部資料列" if rows_expression == "*" else rows_expression
        name = label or f"{column or '資料列'} 的 {op}"
        text = (
            f"衍生統計(來源:{dataset.display_name}):{name}為 {rendered}。"
            f"計算方式:對 {scope} 共 {result['rows_used']} 筆"
            f"（全檔 {len(dataset.rows)} 筆）"
            f"{'的 ' + column + ' 欄' if column else ''}施以 {op} 運算。"
        )
        if result["detail"]:
            text += f"（{result['detail']}）"
        return text
    scope = "all rows" if rows_expression == "*" else rows_expression
    name = label or f"{op} of {column or 'rows'}"
    text = (
        f"Derived statistics from {dataset.display_name}: {name} is {rendered}. "
        f"Method: {op} applied to "
        f"{'the ' + column + ' column of ' if column else ''}"
        f"{result['rows_used']} rows selected by {scope}, out of "
        f"{len(dataset.rows)} in the file."
    )
    if result["detail"]:
        text += f" ({result['detail']})"
    return text


_FILTER_COLUMN_RE = re.compile(r"^\s*([^!=<>~]+?)\s*(?:!=|>=|<=|=|>|<|~)")


def _filter_columns(expression: str) -> list[str]:
    """The columns a row filter names, in the order it names them."""
    columns: list[str] = []
    for clause in str(expression or "").split("&"):
        match = _FILTER_COLUMN_RE.match(clause)
        if match:
            column = match.group(1).strip()
            if column and column not in columns:
                columns.append(column)
    return columns


def _source_key(request: dict) -> tuple:
    source = request.get("source")
    return tuple(str(name or "") for name in source) if isinstance(source, list) else (str(source or ""),)


#: How many one-cell derivations of the same shape it takes before they are a
#: table being typed out by hand.
BRICK_LAYING_THRESHOLD = 3


def brick_laying_problems(requests: list[dict]) -> dict[str, str]:
    """Scalar derivations that are one table, registered one cell at a time.

    The grouped form exists so a six-band table costs one request. An
    acceptance run registered 47 derivations anyway, 41 of them scalars, and
    six of those were mean-and-negative-rate over three price bands -- a two by
    three table, spelled out. Nothing was wrong with any of them, which is why
    nothing stopped it: the author gets a working number every time and never
    finds out the table was one call away.

    A hint would not have been read. So the same shape three times over is
    refused, with the request that replaces it written out in the refusal.
    """
    families: dict[tuple, list[dict]] = {}
    for request in requests or []:
        if not isinstance(request, dict) or request.get("group_by") is not None:
            continue
        op = str(request.get("op") or "").strip().lower()
        rows_expression = str(request.get("rows") or "").strip()
        if not op or not rows_expression:
            continue
        key = (_source_key(request), op, str(request.get("column") or ""))
        families.setdefault(key, []).append(request)

    problems: dict[str, str] = {}
    for (source, op, column), members in families.items():
        filters = {str(member.get("rows") or "").strip() for member in members}
        if len(filters) < BRICK_LAYING_THRESHOLD:
            continue
        shared = [
            candidate
            for candidate in _filter_columns(next(iter(filters)))
            if all(candidate in _filter_columns(other) for other in filters)
        ]
        if not shared:
            continue
        group_column = shared[0]
        ids = sorted(str(member.get("id") or "") for member in members)
        measure = {"op": op}
        if column:
            measure["column"] = column
        replacement = {
            "id": f"{op}_by_{_ID_SAFE_RE.sub('_', group_column)}",
            "source": list(source) if len(source) > 1 else source[0],
            "group_by": {"column": group_column},
            "measures": [measure],
        }
        numeric = all(
            any(
                symbol in clause
                for symbol in (">=", "<=", ">", "<")
            )
            for expression in filters
            for clause in expression.split("&")
            if group_column in clause
        )
        note = (
            " Because these filters cut a numeric range, give group_by a"
            ' "buckets" list with the edges you want; a categorical column'
            " needs no buckets."
            if numeric
            else ""
        )
        message = (
            f"{len(members)} derivations apply {op}"
            + (f" to {column!r}" if column else "")
            + f" over different slices of {group_column!r}: "
            + ", ".join(ids)
            + ". That is one grouped table typed out one cell at a time, and it"
            " costs a registration per cell for the rest of the report. Replace"
            " them with a single request, which returns every row at once and"
            " can be placed in the document with a [TABLE:] marker:\n"
            + json.dumps(replacement, ensure_ascii=False, indent=2)
            + note
            + " Add more entries to 'measures' for the other columns you were"
            " about to register separately."
        )
        for member in members:
            problems[str(member.get("id") or "")] = message
    return problems


def build_requested_units(
    requests: list[dict],
    source_registry: list[dict],
    created_at: str,
    zh: bool = False,
) -> tuple[list[dict], list[dict]]:
    """Compute every registered derivation. Returns ``(units, problems)``.

    A request that cannot be carried out is reported rather than skipped: an
    author who asks for a figure and silently gets nothing writes the sentence
    anyway.
    """
    datasets = structured_datasets(source_registry)
    units: list[dict] = []
    problems: list[dict] = []
    bricks = brick_laying_problems(requests)
    for request in requests or []:
        if not isinstance(request, dict):
            problems.append({"id": "", "error": "Derivation entry is not an object"})
            continue
        request_id = str(request.get("id") or "").strip()
        if not request_id:
            problems.append({"id": "", "error": "Derivation is missing 'id'"})
            continue
        if request_id in bricks:
            problems.append({"id": request_id, "error": bricks[request_id]})
            continue
        try:
            dataset = resolve_frame(request, datasets)
        except DerivationError as error:
            problems.append({"id": request_id, "error": str(error)})
            continue

        if request.get("group_by") is not None or request.get("measures") is not None:
            try:
                table = compute_group_table(dataset, request, zh=zh)
            except DerivationError as error:
                problems.append({"id": request_id, "error": str(error)})
                continue
            units.append(
                _unit_evidence(
                    dataset,
                    _group_table_text(dataset, request, table, zh),
                    {
                        **table["derivation"],
                        "request_id": request_id,
                        "origin": "requested",
                    },
                    created_at,
                    evidence_id=request_evidence_id(request_id),
                    block_id=f"derived_request_{request_id}",
                    origin="requested",
                    table=table,
                )
            )
            continue

        try:
            result = compute(dataset, request)
        except DerivationError as error:
            problems.append({"id": request_id, "error": str(error)})
            continue
        expect = request.get("expect")
        if expect is not None:
            expected = parse_number(expect)
            tolerance = abs(result["value"]) * 0.005 + 1e-9
            if expected is None or abs(expected - result["value"]) > tolerance:
                problems.append({
                    "id": request_id,
                    "error": (
                        f"Registered derivation expects {expect}, but applying "
                        f"{request.get('op')} to those rows gives "
                        f"{format_number(result['value'])}"
                    ),
                })
                continue
        units.append(
            _unit_evidence(
                dataset,
                _request_text(request, dataset, result, zh),
                {
                    **result["derivation"],
                    "request_id": request_id,
                    "origin": "requested",
                },
                created_at,
                evidence_id=request_evidence_id(request_id),
                block_id=f"derived_request_{request_id}",
                origin="requested",
            )
        )
    return units, problems
