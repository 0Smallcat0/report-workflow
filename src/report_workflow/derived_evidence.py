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


def select_rows(dataset: Dataset, expression: str | None) -> list[dict]:
    """The rows an expression names.

    ``category=攝影``, ``price>=100``, ``brand~DJI``, joined with ``&``. An
    empty expression is every row, which is the ordinary case for a sample
    size or a median.
    """
    text = (expression or "").strip()
    if not text or text == "*":
        return list(dataset.rows)
    rows = list(dataset.rows)
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
        rows = [row for row in rows if _row_matches(row, column, op, wanted)]
    return rows


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


def compute(dataset: Dataset, request: dict) -> dict:
    """Carry out one derivation and report how it was carried out.

    Returns ``{"value", "unit", "rows_used", "detail", "derivation"}``. The
    caller never supplies the value; that is the point.
    """
    op = str(request.get("op") or "").strip().lower()
    if op not in SUPPORTED_OPS:
        raise DerivationError(
            f"Operation {op!r} is not supported. Use one of: {', '.join(SUPPORTED_OPS)}"
        )
    rows_expression = str(request.get("rows") or "")
    rows = select_rows(dataset, rows_expression)
    column = str(request.get("column") or "").strip()
    if op != "count" and op != "share" and not column:
        raise DerivationError(f"Operation {op!r} needs a 'column'")
    if column and column not in dataset.columns:
        raise DerivationError(
            f"Column {column!r} is not in {dataset.file_name}. Its columns are: "
            f"{', '.join(dataset.columns[:12])}"
        )

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
        whole = select_rows(dataset, str(request.get("of") or ""))
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

    derivation = {
        "method": op,
        "source_file": dataset.file_name,
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
) -> dict:
    digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
    matched = derivation.get("rows_matched", len(dataset.rows))
    return {
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
        "derivation": derivation,
    }


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
        entries: list[tuple[str, dict]] = [_shape_text(dataset, zh)]
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
                entries.append(_numeric_text(dataset, column, numbers, zh))
                continue
            counts = _group_counts(dataset.rows, column)
            # A column whose values are nearly all distinct is a title or a
            # description, not a category. Its "distribution" is the column
            # reprinted with 1 beside every line, which tells a reader
            # nothing and buries the columns that do.
            if len(counts) > max(2, 0.9 * len(dataset.rows)):
                continue
            if 2 <= len(counts) <= MAX_CATEGORY_CARDINALITY:
                entries.append(_category_text(dataset, column, counts, zh))

        for index, (content, derivation) in enumerate(entries):
            digest = hashlib.sha256(content.encode("utf-8")).hexdigest()
            units.append(
                _unit_evidence(
                    dataset,
                    content,
                    derivation,
                    created_at,
                    evidence_id=f"E_{dataset.source_id}_{digest[:10]}",
                    block_id=f"summary_{index}",
                )
            )
    return units


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
            f"衍生統計(來源:{dataset.file_name}):{name}為 {rendered}。"
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
        f"Derived statistics from {dataset.file_name}: {name} is {rendered}. "
        f"Method: {op} applied to "
        f"{'the ' + column + ' column of ' if column else ''}"
        f"{result['rows_used']} rows selected by {scope}, out of "
        f"{len(dataset.rows)} in the file."
    )
    if result["detail"]:
        text += f" ({result['detail']})"
    return text


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
    for request in requests or []:
        if not isinstance(request, dict):
            problems.append({"id": "", "error": "Derivation entry is not an object"})
            continue
        request_id = str(request.get("id") or "").strip()
        if not request_id:
            problems.append({"id": "", "error": "Derivation is missing 'id'"})
            continue
        wanted = str(request.get("source") or "")
        candidates = [dataset for dataset in datasets if dataset.matches(wanted)]
        if not candidates:
            problems.append({
                "id": request_id,
                "error": (
                    f"No structured source matches {wanted!r}. Available: "
                    + (", ".join(dataset.file_name for dataset in datasets) or "(none)")
                ),
            })
            continue
        dataset = candidates[0]
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
                {**result["derivation"], "request_id": request_id},
                created_at,
                evidence_id=request_evidence_id(request_id),
                block_id=f"derived_request_{request_id}",
            )
        )
    return units, problems
