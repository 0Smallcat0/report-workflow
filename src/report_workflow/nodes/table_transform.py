"""Deterministic table transforms for figure recommendation.

The evidence ledger remains the source of truth. This module only builds
derived table views used by FIGURE_RECOMMEND when a chart would otherwise be
less readable than the underlying source data allows.
"""
from __future__ import annotations

import re
from typing import Any

import pandas as pd


COMPOSITION_TERMS = {
    "%",
    "allocation",
    "breakdown",
    "composition",
    "percent",
    "percentage",
    "proportion",
    "ratio",
    "share",
}

ADDITIVE_TERMS = {
    "amount",
    "budget",
    "cost",
    "count",
    "expense",
    "frequencies",
    "frequency",
    "observation",
    "observations",
    "participant",
    "participants",
    "quantity",
    "response",
    "responses",
    "revenue",
    "sales",
    "sum",
    "total",
    "units",
    "volume",
}

NON_ADDITIVE_TERMS = {
    "deviation",
    "distribution",
    "mean",
    "measurement",
    "median",
    "rate",
    "reading",
    "replicate",
    "replicates",
    "sample",
    "score",
    "sd",
    "standard deviation",
    "strength",
    "temperature",
    "voltage",
}

SERIES_HEADER_TERMS = {
    "category",
    "class",
    "component",
    "group",
    "segment",
    "series",
    "type",
}

TIME_HEADER_TERMS = {
    "date",
    "day",
    "month",
    "period",
    "quarter",
    "time",
    "week",
    "year",
}


def _clean(value: Any) -> str:
    return " ".join(str(value if value is not None else "").strip().split())


def _to_float(value: Any) -> float | None:
    text = _clean(value).replace(",", "")
    if not text:
        return None
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    text = text.rstrip("%")
    try:
        return float(text)
    except ValueError:
        return None


def _rows_shape(rows: list[list[Any]]) -> dict[str, int]:
    return {
        "rows": max(len(rows) - 1, 0),
        "columns": len(rows[0]) if rows else 0,
    }


def _normalize_rows(rows: list[list[Any]]) -> list[list[Any]]:
    width = max((len(row) for row in rows), default=0)
    if width == 0:
        return []
    return [row + [""] * (width - len(row)) for row in rows if any(_clean(cell) for cell in row)]


def _headers(rows: list[list[Any]]) -> list[str]:
    return [_clean(cell) or f"Column {index + 1}" for index, cell in enumerate(rows[0])] if rows else []


def _dataframe(rows: list[list[Any]]) -> pd.DataFrame:
    headers = _headers(rows)
    return pd.DataFrame(rows[1:], columns=headers)


def _column_values(rows: list[list[Any]], index: int) -> list[Any]:
    return [row[index] for row in rows[1:] if index < len(row)]


def _numeric_ratio(values: list[Any]) -> float:
    non_empty = [value for value in values if _clean(value)]
    if not non_empty:
        return 0.0
    numeric = [_to_float(value) for value in non_empty]
    return len([value for value in numeric if value is not None]) / len(non_empty)


def _is_numeric_column(rows: list[list[Any]], index: int) -> bool:
    return _numeric_ratio(_column_values(rows, index)) >= 0.75


def _text_contains(text: str, terms: set[str]) -> bool:
    normalized = re.sub(r"[^a-z0-9%]+", " ", text.casefold())
    tokens = set(normalized.split())
    for term in terms:
        normalized_term = re.sub(r"[^a-z0-9%]+", " ", term.casefold()).strip()
        if not normalized_term:
            continue
        if " " in normalized_term:
            if re.search(rf"(?<![a-z0-9%]){re.escape(normalized_term)}(?![a-z0-9%])", normalized):
                return True
        elif normalized_term in tokens:
            return True
    return False


def _is_time_header(header: str) -> bool:
    text = _clean(header).casefold()
    if _text_contains(text, TIME_HEADER_TERMS):
        return True
    if re.fullmatch(r"\d{4}", text):
        return True
    if re.fullmatch(r"\d{4}[-/]\d{1,2}(?:[-/]\d{1,2})?", text):
        return True
    if re.fullmatch(r"q[1-4]\s*\d{2,4}|\d{2,4}\s*q[1-4]", text):
        return True
    return text[:3] in {"jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"}


def _is_additive_measure(header: str, content: str, values: list[Any]) -> bool:
    numeric_values = [_to_float(value) for value in values if _to_float(value) is not None]
    if not numeric_values or any(value < 0 for value in numeric_values):
        return False
    text = f"{header} {content}".casefold()
    if _text_contains(text, NON_ADDITIVE_TERMS):
        return False
    return _text_contains(text, ADDITIVE_TERMS)


def _metadata(
    *,
    status: str,
    operations: list[str],
    input_rows: list[list[Any]],
    output_rows: list[list[Any]],
    evidence_ids: list[str],
    warnings: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "status": status,
        "operations": operations,
        "input_shape": _rows_shape(input_rows),
        "output_shape": _rows_shape(output_rows),
        "warnings": warnings or [],
        "source_evidence_ids": evidence_ids,
    }


def _with_rows(table: dict, rows: list[list[Any]], transform: dict[str, Any]) -> dict:
    variant = dict(table)
    variant["rows"] = rows
    variant["data_transform"] = transform
    return variant


def _group_by_sum(rows: list[list[Any]], content: str) -> tuple[list[list[Any]], list[str], list[str]]:
    headers = _headers(rows)
    if len(headers) < 2:
        return rows, [], []
    key_index = 0
    key_values = [_clean(value) for value in _column_values(rows, key_index)]
    if len(set(key_values)) == len(key_values):
        return rows, [], []

    numeric_indices = [
        index for index in range(1, len(headers))
        if _is_numeric_column(rows, index)
        and _is_additive_measure(headers[index], content, _column_values(rows, index))
    ]
    if not numeric_indices:
        return rows, [], []

    df = _dataframe(rows)
    key_header = headers[key_index]
    numeric_headers = [headers[index] for index in numeric_indices]
    for header in numeric_headers:
        df[header] = pd.to_numeric(df[header].map(_clean), errors="coerce").fillna(0.0)
    grouped = df.groupby(key_header, sort=False, dropna=False)[numeric_headers].sum().reset_index()
    output = [list(grouped.columns)]
    output.extend(grouped.astype(object).values.tolist())
    return output, ["group_by_sum"], []


def _pivot_long_series(rows: list[list[Any]], content: str) -> tuple[list[list[Any]], list[str], list[str]]:
    headers = _headers(rows)
    if len(headers) != 3:
        return rows, [], []
    if _is_numeric_column(rows, 0) or _is_numeric_column(rows, 1) or not _is_numeric_column(rows, 2):
        return rows, [], []
    if not (_text_contains(headers[1], SERIES_HEADER_TERMS) or _text_contains(content, SERIES_HEADER_TERMS)):
        return rows, [], []
    if not _is_additive_measure(headers[2], content, _column_values(rows, 2)):
        return rows, [], []

    df = _dataframe(rows)
    df[headers[0]] = df[headers[0]].map(_clean)
    df[headers[1]] = df[headers[1]].map(_clean)
    df[headers[2]] = pd.to_numeric(df[headers[2]].map(_clean), errors="coerce")
    df = df.dropna(subset=[headers[0], headers[1], headers[2]])
    key_order = [item for item in dict.fromkeys(df[headers[0]].tolist()) if item]
    series_order = [item for item in dict.fromkeys(df[headers[1]].tolist()) if item]
    if len(key_order) < 2 or len(series_order) < 2:
        return rows, [], []
    pivot = df.pivot_table(
        index=headers[0],
        columns=headers[1],
        values=headers[2],
        aggfunc="sum",
        fill_value=0.0,
        sort=False,
    ).reindex(index=key_order, columns=series_order, fill_value=0.0).reset_index()
    output = [list(pivot.columns)]
    output.extend(pivot.astype(object).values.tolist())
    return output, ["pivot"], []


def _wide_time_to_series(rows: list[list[Any]]) -> tuple[list[list[Any]], list[str], list[str]]:
    headers = _headers(rows)
    if len(headers) < 3 or len(rows) < 3:
        return rows, [], []
    time_headers = headers[1:]
    if not all(_is_time_header(header) for header in time_headers):
        return rows, [], []
    if not all(_is_numeric_column(rows, index) for index in range(1, len(headers))):
        return rows, [], []

    df = _dataframe(rows)
    label_header = headers[0]
    df[label_header] = df[label_header].map(_clean)
    df = df[df[label_header] != ""]
    for header in time_headers:
        df[header] = pd.to_numeric(df[header].map(_clean), errors="coerce").fillna(0.0)
    transposed = df.set_index(label_header)[time_headers].T.reset_index()
    transposed = transposed.rename(columns={"index": "Period"})
    output = [list(transposed.columns)]
    output.extend(transposed.astype(object).values.tolist())
    return output, ["wide_to_long"], []


def _normalize_percent(rows: list[list[Any]], content: str) -> tuple[list[list[Any]], list[str], list[str]]:
    headers = _headers(rows)
    if len(headers) != 2 or not _is_numeric_column(rows, 1):
        return rows, [], []
    if not _text_contains(" ".join(headers) + " " + content, COMPOSITION_TERMS):
        return rows, [], []
    values = [_to_float(row[1]) for row in rows[1:]]
    if any(value is None or value < 0 for value in values):
        return rows, [], []
    total = sum(value for value in values if value is not None)
    if total <= 0:
        return rows, [], ["Cannot normalize composition values because the total is zero."]
    if 99 <= total <= 101:
        return rows, [], []

    output = [[headers[0], f"{headers[1]} (%)"]]
    for row, value in zip(rows[1:], values):
        output.append([row[0], round(float(value) / total * 100, 6)])
    return output, ["normalize_percent"], []


def _sort_and_top_n(rows: list[list[Any]], content: str, max_categories: int) -> tuple[list[list[Any]], list[str], list[str]]:
    headers = _headers(rows)
    if len(headers) < 2 or not _is_numeric_column(rows, 1):
        return rows, [], []
    if _is_numeric_column(rows, 0) or _is_time_header(headers[0]):
        return rows, [], []
    category_values = [_clean(row[0]) for row in rows[1:]]
    if len([value for value in category_values if value]) <= 2:
        return rows, [], []

    numeric_values = [_to_float(row[1]) for row in rows[1:]]
    if any(value is None for value in numeric_values):
        return rows, [], []
    paired = list(zip(rows[1:], [float(value) for value in numeric_values if value is not None]))
    numeric_indices = [
        index for index in range(1, len(headers))
        if _is_numeric_column(rows, index)
    ]
    additive_indices = [
        index for index in numeric_indices
        if _is_additive_measure(headers[index], content, _column_values(rows, index))
    ]
    additive = 1 in additive_indices
    limit = max(max_categories, 2)
    if not additive and len(paired) <= limit:
        return rows, [], []
    paired.sort(key=lambda item: item[1], reverse=True)

    operations = ["sort_desc"]
    warnings: list[str] = []
    output_rows = [row for row, _ in paired]
    if len(paired) > limit:
        if not additive:
            return rows, [], []
        keep_count = limit - 1
        kept = paired[:keep_count]
        remainder = paired[keep_count:]
        if set(numeric_indices) != set(additive_indices):
            return rows, [], []
        other: list[Any] = ["Other"]
        for index in range(1, len(headers)):
            if index not in additive_indices:
                other.append("")
                continue
            values = [
                _to_float(row[index] if index < len(row) else "")
                for row, _ in remainder
            ]
            if any(value is None or value < 0 for value in values):
                return rows, [], []
            other.append(sum(float(value) for value in values if value is not None))
        output_rows = [row for row, _ in kept] + [other]
        operations.append("top_n")

    if output_rows == rows[1:]:
        return rows, [], []
    return [headers, *output_rows], operations, warnings


def build_table_variants(
    table: dict,
    *,
    max_bar_categories: int,
    max_pie_slices: int,
) -> list[dict]:
    """Return source and deterministic transformed variants for chart selection."""
    source_rows = _normalize_rows(table.get("rows", []))
    if len(source_rows) < 2:
        return []

    evidence_ids = [str(item) for item in table.get("evidence_ids", []) if item]
    variants = [
        _with_rows(
            table,
            source_rows,
            _metadata(
                status="source",
                operations=[],
                input_rows=source_rows,
                output_rows=source_rows,
                evidence_ids=evidence_ids,
            ),
        )
    ]

    content = str(table.get("content", ""))
    transformed = source_rows
    operations: list[str] = []
    warnings: list[str] = []

    for transform in (_wide_time_to_series,):
        transformed, new_ops, new_warnings = transform(transformed)
        operations.extend(new_ops)
        warnings.extend(new_warnings)
        if new_ops:
            break

    if not operations:
        transformed, new_ops, new_warnings = _pivot_long_series(transformed, content)
        operations.extend(new_ops)
        warnings.extend(new_warnings)

    if not operations:
        transformed, new_ops, new_warnings = _group_by_sum(transformed, content)
        operations.extend(new_ops)
        warnings.extend(new_warnings)

    transformed, new_ops, new_warnings = _normalize_percent(transformed, content)
    operations.extend(new_ops)
    warnings.extend(new_warnings)

    category_limit = max_pie_slices if "normalize_percent" in operations else max_bar_categories
    transformed, new_ops, new_warnings = _sort_and_top_n(transformed, content, category_limit)
    operations.extend(new_ops)
    warnings.extend(new_warnings)

    if operations and transformed != source_rows:
        variants.append(
            _with_rows(
                table,
                transformed,
                _metadata(
                    status="transformed",
                    operations=operations,
                    input_rows=source_rows,
                    output_rows=transformed,
                    evidence_ids=evidence_ids,
                    warnings=warnings,
                ),
            )
        )

    return variants
