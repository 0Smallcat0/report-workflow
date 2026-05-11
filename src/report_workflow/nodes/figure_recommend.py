"""FIGURE_RECOMMEND node.

This module keeps chart choice deterministic and inspectable. It does not
author prose; it recommends chart types from table-shaped evidence.
"""
from __future__ import annotations

import re
from pathlib import Path
from typing import Any

from ..runtime_support import load_jsonl, write_json_artifact
from ..state import ReportState
from .figure_utils import (
    clean_text as _clean_text,
    to_float as _to_float,
    unit_signature as _unit_signature,
)
from .table_transform import _time_sort_key, build_table_variants


MAX_CHART_ROWS = 24
MAX_TABLE_FIGURE_ROWS = 12
MIN_CHART_ROWS = 2
MIN_DISTRIBUTION_POINTS = 8
NUMERIC_RATIO_THRESHOLD = 0.75
MAX_PIE_SLICES = 6
MAX_BAR_CATEGORIES = 12
MAX_LINE_SCATTER_POINTS = 50
MAX_TABLE_COLUMNS = 6
MAX_CATEGORY_LABEL_LENGTH = 35
MAX_LINE_BAR_SERIES = 3
MAX_STACKED_BAR_SERIES = 6
MAX_HEATMAP_ROWS = 16
MAX_HEATMAP_COLUMNS = 12

TIME_HEADER_TERMS = {
    "time",
    "date",
    "day",
    "week",
    "month",
    "year",
    "period",
    "step",
    "trial",
    "run",
    "sample",
    "iteration",
    "timestamp",
}
COMPOSITION_TERMS = {
    "share",
    "percent",
    "percentage",
    "%",
    "ratio",
    "proportion",
    "composition",
    "distribution",
    "breakdown",
    "allocation",
}
STACKED_BAR_TERMS = {
    "share",
    "percent",
    "percentage",
    "%",
    "ratio",
    "proportion",
    "composition",
    "breakdown",
    "allocation",
}
ID_HEADER_TERMS = {
    "id",
    "identifier",
    "index",
    "record id",
    "row id",
    "serial",
    "no",
    "sample id",
    "sample number",
    "specimen id",
    "specimen number",
}
PARAMETER_TABLE_TERMS = {
    "parameter",
    "variable",
    "symbol",
    "formula",
    "constant",
    "calculation",
}
ERROR_HEADER_TERMS = {
    "error",
    "err",
    "sd",
    "std",
    "standard deviation",
    "se",
    "sem",
    "standard error",
    "ci",
    "confidence interval",
    "uncertainty",
    "margin",
    "deviation",
}
MATRIX_TERMS = {
    "matrix",
    "heatmap",
    "grid",
    "correlation",
    "confusion",
    "intensity",
}
GROUPED_DISTRIBUTION_TERMS = {
    "boxplot",
    "box plot",
    "distribution",
    "replicate",
    "replicates",
    "sample",
    "samples",
    "variation",
    "spread",
}
TEXT_MIXED_ROLE = "text/mixed"


def _rows_from_table_data(table_data: Any) -> list[list[str]]:
    if not isinstance(table_data, list):
        return []
    rows: list[list[str]] = []
    for row in table_data:
        if isinstance(row, list):
            rows.append([_clean_text(cell) for cell in row])
        elif isinstance(row, dict):
            if not rows:
                rows.append([_clean_text(key) for key in row.keys()])
            rows.append([_clean_text(value) for value in row.values()])
    width = max((len(row) for row in rows), default=0)
    if width == 0:
        return []
    normalized = [row + [""] * (width - len(row)) for row in rows]
    return [row for row in normalized if any(cell for cell in row)]


def _table_candidates(evidence: list[dict]) -> list[dict]:
    full_tables: list[dict] = []
    row_groups: dict[tuple[str, str, tuple[str, ...]], dict] = {}

    for entry in evidence:
        rows = _rows_from_table_data(entry.get("table_data"))
        if len(rows) < 2:
            continue

        evidence_id = str(entry.get("evidence_id") or "")
        source_id = str(entry.get("source_id") or entry.get("source_file_name") or "")
        source_file_name = str(entry.get("source_file_name") or "")
        granularity = str(entry.get("granularity") or entry.get("block_type") or "")

        if len(rows) > 2 or granularity == "table":
            full_tables.append({
                "source_id": source_id,
                "source_file_name": source_file_name,
                "evidence_ids": [evidence_id] if evidence_id else [],
                "rows": rows,
                "content": str(entry.get("content") or ""),
            })
            continue

        headers = tuple(rows[0])
        key = (source_id, source_file_name, headers)
        group = row_groups.setdefault(key, {
            "source_id": source_id,
            "source_file_name": source_file_name,
            "evidence_ids": [],
            "rows": [list(headers)],
            "content": "",
        })
        if evidence_id:
            group["evidence_ids"].append(evidence_id)
        group["rows"].append(rows[1])
        group["content"] = (group["content"] + "\n" + str(entry.get("content") or "")).strip()

    grouped_tables = [group for group in row_groups.values() if len(group.get("rows", [])) >= 3]
    return full_tables + grouped_tables


def _column_values(rows: list[list[str]], index: int) -> list[str]:
    return [row[index] for row in rows[1:] if index < len(row)]


def _numeric_values(values: list[str]) -> list[float]:
    return [number for value in values if (number := _to_float(value)) is not None]


def _is_numeric_column(values: list[str]) -> bool:
    non_empty = [value for value in values if _clean_text(value)]
    if len(non_empty) < MIN_CHART_ROWS:
        return False
    return len(_numeric_values(non_empty)) / len(non_empty) >= NUMERIC_RATIO_THRESHOLD


def _is_time_like(header: str, values: list[str]) -> bool:
    lowered = header.casefold()
    if any(term in lowered for term in TIME_HEADER_TERMS):
        return True
    non_empty = [_clean_text(value) for value in values if _clean_text(value)]
    if not non_empty:
        return False
    date_like = sum(1 for value in non_empty if re.search(r"\d{4}[-/]\d{1,2}|\d{1,2}:\d{2}", value))
    parsed_time_like = sum(1 for value in non_empty if _time_sort_key(value) is not None)
    if max(date_like, parsed_time_like) / len(non_empty) >= 0.6:
        return True
    return False


def _is_composition_context(headers: list[str], values: list[float], content: str) -> bool:
    text = " ".join(headers + [content]).casefold()
    total = sum(values)
    has_composition_terms = any(term in text for term in COMPOSITION_TERMS)
    total_is_composition_like = 99 <= total <= 101 or 0.99 <= total <= 1.01
    return has_composition_terms and total_is_composition_like


def _unique_non_empty(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        clean = _clean_text(value)
        if clean and clean not in seen:
            seen.add(clean)
            unique.append(clean)
    return unique


def _header_contains(header: str, terms: set[str]) -> bool:
    normalized = re.sub(r"[^a-z0-9%#]+", " ", header.casefold()).strip()
    if not normalized:
        return False
    for term in terms:
        term_norm = re.sub(r"[^a-z0-9%#]+", " ", term.casefold()).strip()
        if not term_norm:
            continue
        if " " in term_norm:
            if term_norm in normalized:
                return True
            continue
        if re.search(rf"(^|\s){re.escape(term_norm)}(\s|$)", normalized):
            return True
    return False


def _is_ordered_values(values: list[str]) -> bool:
    non_empty = [_clean_text(value) for value in values if _clean_text(value)]
    if len(non_empty) < MIN_CHART_ROWS:
        return False

    numbers = [_to_float(value) for value in non_empty]
    if all(number is not None for number in numbers):
        numeric_values = [float(number) for number in numbers if number is not None]
        deltas = [b - a for a, b in zip(numeric_values, numeric_values[1:])]
        if not deltas:
            return False
        return (all(delta >= 0 for delta in deltas) or all(delta <= 0 for delta in deltas)) and any(
            delta != 0 for delta in deltas
        )

    date_keys: list[tuple[int, ...]] = []
    for value in non_empty:
        key = _time_sort_key(value)
        if key is not None:
            date_keys.append(key)
            continue
        return False
    deltas = [
        (b > a) - (b < a)
        for a, b in zip(date_keys, date_keys[1:])
    ]
    return bool(deltas) and (all(delta >= 0 for delta in deltas) or all(delta <= 0 for delta in deltas)) and any(
        delta != 0 for delta in deltas
    )


def _numeric_values_for_rows(rows: list[list[str]], index: int, limit: int = MAX_CHART_ROWS) -> list[float]:
    values: list[float] = []
    for row in rows[1:limit + 1]:
        number = _to_float(row[index] if index < len(row) else "")
        if number is not None:
            values.append(number)
    return values


def _is_parameter_table(headers: list[str], content: str) -> bool:
    text = " ".join(headers + [content]).casefold()
    return any(term in text for term in PARAMETER_TABLE_TERMS)


def _profile_table(headers: list[str], rows: list[list[str]], content: str) -> dict:
    data_rows = rows[1:]
    total_cells = max(len(data_rows) * len(headers), 1)
    missing_cells = 0
    columns: list[dict] = []

    for index, header in enumerate(headers):
        values = _column_values(rows, index)
        non_empty = [_clean_text(value) for value in values if _clean_text(value)]
        missing = max(len(data_rows) - len(non_empty), 0)
        missing_cells += missing
        numeric_values = _numeric_values(non_empty)
        numeric_ratio = len(numeric_values) / len(non_empty) if non_empty else 0.0
        negative_count = len([value for value in numeric_values if value < 0])
        unique_values = _unique_non_empty(values)
        unique_count = len(unique_values)
        ordered = _is_ordered_values(values)

        id_like = _header_contains(header, ID_HEADER_TERMS)
        numeric_column = len(non_empty) >= MIN_CHART_ROWS and numeric_ratio >= NUMERIC_RATIO_THRESHOLD
        time_like = not id_like and _is_time_like(header, values) and ordered
        categorical = (
            not numeric_column
            and not time_like
            and not id_like
            and 2 <= unique_count <= 12
            and (missing / max(len(data_rows), 1)) < 0.5
        )

        if id_like:
            role = "id_like"
        elif time_like:
            role = "time_like"
        elif numeric_column:
            role = "numeric_measure"
        elif categorical:
            role = "categorical"
        else:
            role = TEXT_MIXED_ROLE

        columns.append({
            "index": index,
            "header": header,
            "role": role,
            "missing_ratio": round(missing / max(len(data_rows), 1), 3),
            "numeric_ratio": round(numeric_ratio, 3),
            "unique_count": unique_count,
            "ordered": ordered,
            "unit_signature": _unit_signature(header),
            "negative_value_count": negative_count,
        })

    composition_total: float | None = None
    for column in columns:
        if column["role"] != "numeric_measure":
            continue
        values = _numeric_values_for_rows(rows, int(column["index"]))
        if values and all(value >= 0 for value in values) and _is_composition_context(headers, values, content):
            column["role"] = "composition_value"
            composition_total = round(sum(values), 6)

    role_counts: dict[str, int] = {}
    for column in columns:
        role_counts[column["role"]] = role_counts.get(column["role"], 0) + 1
    measure_units = sorted({
        str(column.get("unit_signature") or "")
        for column in columns
        if column.get("role") == "numeric_measure" and column.get("unit_signature")
    })
    negative_numeric_value_count = sum(int(column.get("negative_value_count", 0) or 0) for column in columns)

    return {
        "summary": {
            "rows": len(data_rows),
            "columns": len(headers),
            "missing_ratio": round(missing_cells / total_cells, 3),
            "numeric_column_count": role_counts.get("numeric_measure", 0),
            "categorical_column_count": role_counts.get("categorical", 0),
            "time_like_column_count": role_counts.get("time_like", 0),
            "id_like_column_count": role_counts.get("id_like", 0),
            "composition_value_column_count": role_counts.get("composition_value", 0),
            "composition_total": composition_total,
            "parameter_table": _is_parameter_table(headers, content),
            "measure_unit_signatures": measure_units,
            "mixed_measure_units": len(measure_units) > 1,
            "negative_numeric_value_count": negative_numeric_value_count,
        },
        "columns": columns,
    }


def _indices_with_role(profile: dict, role: str) -> list[int]:
    return [int(column["index"]) for column in profile.get("columns", []) if column.get("role") == role]


def _chart_candidate(figure_type: str, score: float, confidence: str, reason: str) -> dict:
    return {
        "figure_type": figure_type,
        "score": round(score, 2),
        "confidence": confidence,
        "reason": reason,
    }


def _selection_warnings(profile: dict) -> list[str]:
    summary = profile.get("summary", {})
    warnings: list[str] = []
    if summary.get("missing_ratio", 0) >= 0.25:
        warnings.append("Table has substantial missing values; preserve exact values unless a visual mapping is clearly justified.")
    if summary.get("id_like_column_count", 0):
        warnings.append("ID-like numeric columns were excluded from trend and relationship chart selection.")
    if summary.get("numeric_column_count", 0) == 0 and summary.get("composition_value_column_count", 0) == 0:
        warnings.append("No reliable numeric measure column was detected.")
    if summary.get("mixed_measure_units"):
        warnings.append("Multiple numeric measure columns have mixed units; avoid plotting them on one shared y-axis.")
    if summary.get("negative_numeric_value_count", 0):
        warnings.append("Negative numeric values were detected; whole-part charts such as pie or stacked bar were excluded.")
    return warnings


def _section_for_recommendation(state: ReportState) -> str:
    outline_sections = (state.plan.get("outline") or {}).get("sections") or {}
    for section_id in ("results", "data", "results_discussion", "findings"):
        if section_id in outline_sections:
            return section_id
    blueprint = state.plan.get("blueprint") or {}
    for section_id in ("results", "data", "results_discussion", "findings"):
        if section_id in blueprint.get("sections", {}):
            return section_id
    return "results"


def _series_payload(headers: list[str], rows: list[list[str]], label_index: int, numeric_indices: list[int]) -> dict:
    labels = [_clean_text(row[label_index]) for row in rows[1:MAX_CHART_ROWS + 1]]
    series = []
    for index in numeric_indices:
        values = []
        for row in rows[1:MAX_CHART_ROWS + 1]:
            number = _to_float(row[index] if index < len(row) else "")
            values.append(number if number is not None else 0)
        series.append({"name": headers[index], "values": values})
    return {"labels": labels, "series": series}


def _contains_terms(headers: list[str], content: str, terms: set[str]) -> bool:
    text = " ".join(headers + [content]).casefold()
    return any(term in text for term in terms)


def _error_indices(headers: list[str], numeric_indices: list[int]) -> list[int]:
    return [index for index in numeric_indices if _header_contains(headers[index], ERROR_HEADER_TERMS)]


def _non_error_numeric_indices(headers: list[str], numeric_indices: list[int]) -> list[int]:
    error_index_set = set(_error_indices(headers, numeric_indices))
    return [index for index in numeric_indices if index not in error_index_set]


def _all_values_non_negative(rows: list[list[str]], numeric_indices: list[int]) -> bool:
    for index in numeric_indices:
        values = _numeric_values_for_rows(rows, index)
        if not values or any(value < 0 for value in values):
            return False
    return True


def _row_totals_are_composition_like(rows: list[list[str]], numeric_indices: list[int]) -> bool:
    totals: list[float] = []
    for row in rows[1:MAX_CHART_ROWS + 1]:
        values = []
        for index in numeric_indices:
            number = _to_float(row[index] if index < len(row) else "")
            if number is None:
                values = []
                break
            values.append(number)
        if values:
            totals.append(sum(values))
    if not totals:
        return False
    return all(99 <= total <= 101 or 0.99 <= total <= 1.01 for total in totals)


def _grouped_numeric_series(rows: list[list[str]], group_index: int, value_index: int) -> list[dict]:
    grouped: dict[str, list[float]] = {}
    for row in rows[1:MAX_CHART_ROWS + 1]:
        label = _clean_text(row[group_index] if group_index < len(row) else "")
        value = _to_float(row[value_index] if value_index < len(row) else "")
        if label and value is not None:
            grouped.setdefault(label, []).append(value)
    return [
        {"name": label, "values": values}
        for label, values in grouped.items()
        if len(values) >= 2
    ]


def _numeric_column_series(headers: list[str], rows: list[list[str]], numeric_indices: list[int]) -> list[dict]:
    series: list[dict] = []
    for index in numeric_indices:
        values = _numeric_values_for_rows(rows, index)
        if len(values) >= MIN_CHART_ROWS:
            series.append({"name": headers[index], "values": values})
    return series


def _heatmap_payload(headers: list[str], rows: list[list[str]], label_index: int, numeric_indices: list[int]) -> dict:
    values: list[list[float]] = []
    y_labels: list[str] = []
    for row in rows[1:MAX_HEATMAP_ROWS + 1]:
        row_values: list[float] = []
        for index in numeric_indices[:MAX_HEATMAP_COLUMNS]:
            number = _to_float(row[index] if index < len(row) else "")
            if number is None:
                row_values = []
                break
            row_values.append(number)
        if row_values:
            y_labels.append(_clean_text(row[label_index] if label_index < len(row) else ""))
            values.append(row_values)
    return {
        "x_labels": [headers[index] for index in numeric_indices[:MAX_HEATMAP_COLUMNS]],
        "y_labels": y_labels,
        "values": values,
    }


def _error_bar_payload(
    headers: list[str],
    rows: list[list[str]],
    label_index: int,
    value_index: int,
    error_index: int,
) -> dict:
    labels: list[str] = []
    values: list[float] = []
    errors: list[float] = []
    for row in rows[1:MAX_CHART_ROWS + 1]:
        label = _clean_text(row[label_index] if label_index < len(row) else "")
        value = _to_float(row[value_index] if value_index < len(row) else "")
        error = _to_float(row[error_index] if error_index < len(row) else "")
        if label and value is not None and error is not None:
            labels.append(label)
            values.append(value)
            errors.append(abs(error))
    return {
        "labels": labels,
        "series": [{"name": headers[value_index], "values": values, "errors": errors}],
    }


def _make_recommendation(
    state: ReportState,
    table: dict,
    rec_index: int,
    figure_type: str,
    acceptable_types: list[str],
    confidence: str,
    reason: str,
    data: dict,
    xlabel: str = "",
    ylabel: str = "",
    data_profile: dict | None = None,
    chart_candidates: list[dict] | None = None,
    selection_warnings: list[str] | None = None,
) -> dict:
    rec_id = f"figrec_{rec_index}"
    title_source = table.get("source_file_name") or table.get("source_id") or "source data"
    data_transform = table.get("data_transform") if isinstance(table.get("data_transform"), dict) else None
    transform_operations = data_transform.get("operations", []) if data_transform else []
    transform_status = data_transform.get("status", "source") if data_transform else "source"
    transform_label = ""
    if transform_status == "transformed" and transform_operations:
        transform_label = " after " + ", ".join(str(item).replace("_", " ") for item in transform_operations)
        reason = (
            f"{reason} Data were deterministically transformed before plotting "
            f"({', '.join(str(item) for item in transform_operations)}); derived chart values remain tied "
            "to the source evidence IDs."
        )
        if any(item == "normalize_percent" for item in transform_operations):
            if not ylabel:
                ylabel = "Percent of total (%)"
            elif "%" not in ylabel and "percent" not in ylabel.casefold():
                ylabel = f"{ylabel} (%)"
    title = f"{figure_type.title()} view of {Path(str(title_source)).stem or title_source}{transform_label}"
    section_id = _section_for_recommendation(state)
    figure_plan = {
        "figure_id": rec_id,
        "figure_type": figure_type,
        "title": title,
        "xlabel": xlabel,
        "ylabel": ylabel,
        "data": data,
        "output_format": "png",
        "section_id": section_id,
        "recommendation_id": rec_id,
        "source_evidence_ids": table.get("evidence_ids", []),
        "chart_selection_reason": reason,
    }
    if data_transform:
        figure_plan["data_transform"] = data_transform
    return {
        "recommendation_id": rec_id,
        "source_id": table.get("source_id", ""),
        "source_file_name": table.get("source_file_name", ""),
        "evidence_ids": table.get("evidence_ids", []),
        "recommended_figure_type": figure_type,
        "acceptable_figure_types": acceptable_types,
        "confidence": confidence,
        "reason": reason,
        "section_id": section_id,
        "table_shape": {"rows": max(len(table.get("rows", [])) - 1, 0), "columns": len(table.get("rows", [[]])[0])},
        "data_profile": data_profile or {},
        "chart_candidates": chart_candidates or [
            _chart_candidate(figure_type, 1.0, confidence, reason)
        ],
        "selection_warnings": selection_warnings or [],
        "data_transform": data_transform or {
            "status": "source",
            "operations": [],
            "input_shape": {"rows": max(len(table.get("rows", [])) - 1, 0), "columns": len(table.get("rows", [[]])[0])},
            "output_shape": {"rows": max(len(table.get("rows", [])) - 1, 0), "columns": len(table.get("rows", [[]])[0])},
            "warnings": [],
            "source_evidence_ids": table.get("evidence_ids", []),
        },
        "figure_plan": figure_plan,
    }


def _recommend_single_table(state: ReportState, table: dict, rec_index: int) -> dict | None:
    """Build one chart recommendation from one source or transformed table view."""
    rows = table.get("rows", [])
    if len(rows) < 3:
        return None
    headers = [_clean_text(header) or f"Column {index + 1}" for index, header in enumerate(rows[0])]
    profile = _profile_table(headers, rows, table.get("content", ""))
    summary = profile["summary"]
    data_transform = table.get("data_transform") if isinstance(table.get("data_transform"), dict) else {}
    warnings = _selection_warnings(profile) + list(data_transform.get("warnings", []) or [])
    categorical_indices = _indices_with_role(profile, "categorical")
    time_indices = _indices_with_role(profile, "time_like")
    numeric_indices = _indices_with_role(profile, "numeric_measure")
    composition_indices = _indices_with_role(profile, "composition_value")
    error_indices = _error_indices(headers, numeric_indices)
    measure_indices = _non_error_numeric_indices(headers, numeric_indices)
    chart_candidates: list[dict] = []

    if summary.get("parameter_table") and len(rows) - 1 <= MAX_TABLE_FIGURE_ROWS:
        reason = (
            "Parameter, unit, formula, or calculation-shaped evidence should remain a table so exact values and units stay visible."
        )
        chart_candidates.append(_chart_candidate("table", 0.9, "high", reason))
        return _make_recommendation(
            state,
            table,
            rec_index,
            "table",
            ["table"],
            "high",
            reason,
            {"columns": headers, "rows": rows[1:MAX_TABLE_FIGURE_ROWS + 1]},
            data_profile=profile,
            chart_candidates=chart_candidates,
            selection_warnings=warnings,
        )

    if summary.get("missing_ratio", 0) >= 0.25 and len(rows) - 1 <= MAX_TABLE_FIGURE_ROWS:
        reason = "High missing-value density makes a compact table safer than a potentially misleading chart."
        chart_candidates.append(_chart_candidate("table", 0.78, "medium", reason))
        return _make_recommendation(
            state,
            table,
            rec_index,
            "table",
            ["table"],
            "medium",
            reason,
            {"columns": headers, "rows": rows[1:MAX_TABLE_FIGURE_ROWS + 1]},
            data_profile=profile,
            chart_candidates=chart_candidates,
            selection_warnings=warnings,
        )

    if any("Time/date labels" in warning for warning in warnings):
        reason = (
            "Time/date labels could not be deterministically parsed or sorted, so exact source order should remain visible."
        )
        chart_candidates.append(_chart_candidate("table", 0.82, "medium", reason))
        return _make_recommendation(
            state,
            table,
            rec_index,
            "table",
            ["table"],
            "medium",
            reason,
            {"columns": headers, "rows": rows[1:MAX_TABLE_FIGURE_ROWS + 1]},
            data_profile=profile,
            chart_candidates=chart_candidates,
            selection_warnings=warnings,
        )

    if summary.get("mixed_measure_units"):
        reason = (
            "Numeric measure columns use mixed units; keep them as a table or split them into separate charts "
            "instead of sharing one y-axis."
        )
        chart_candidates.append(_chart_candidate("table", 0.91, "high", reason))
        return _make_recommendation(
            state,
            table,
            rec_index,
            "table",
            ["table"],
            "high",
            reason,
            {"columns": headers, "rows": rows[1:MAX_TABLE_FIGURE_ROWS + 1]},
            data_profile=profile,
            chart_candidates=chart_candidates,
            selection_warnings=warnings,
        )

    label_indices = (categorical_indices or time_indices)
    if label_indices and error_indices and measure_indices:
        label_index = label_indices[0]
        value_index = measure_indices[0]
        error_index = error_indices[0]
        payload = _error_bar_payload(headers, rows, label_index, value_index, error_index)
        if payload["labels"] and len(payload["labels"]) >= MIN_CHART_ROWS:
            reason = (
                "Category or ordered observations with a central value and explicit error, SD, SE, CI, "
                "or uncertainty column should be shown with error bars."
            )
            chart_candidates.append(_chart_candidate("error_bar", 0.93, "high", reason))
            chart_candidates.append(_chart_candidate(
                "bar",
                0.62,
                "low",
                "Bar can show central values, but it hides uncertainty unless the error column is rendered.",
            ))
            return _make_recommendation(
                state,
                table,
                rec_index,
                "error_bar",
                ["error_bar"],
                "high",
                reason,
                payload,
                xlabel=headers[label_index],
                ylabel=headers[value_index],
                data_profile=profile,
                chart_candidates=chart_candidates,
                selection_warnings=warnings,
            )

    if (
        _contains_terms(headers, table.get("content", ""), MATRIX_TERMS)
        and (categorical_indices or _indices_with_role(profile, TEXT_MIXED_ROLE))
        and len(measure_indices) >= 2
        and len(rows) - 1 <= MAX_HEATMAP_ROWS
    ):
        label_index = (categorical_indices or _indices_with_role(profile, TEXT_MIXED_ROLE))[0]
        payload = _heatmap_payload(headers, rows, label_index, measure_indices)
        if payload["values"] and len(payload["values"][0]) >= 2:
            reason = (
                "Matrix-shaped numeric evidence is suited to a heatmap so row/column intensity patterns are visible."
            )
            chart_candidates.append(_chart_candidate("heatmap", 0.9, "high", reason))
            chart_candidates.append(_chart_candidate(
                "table",
                0.68,
                "medium",
                "A table remains acceptable when exact cell values matter more than pattern visibility.",
            ))
            return _make_recommendation(
                state,
                table,
                rec_index,
                "heatmap",
                ["heatmap", "table"],
                "high",
                reason,
                payload,
                xlabel="Columns",
                ylabel="Rows",
                data_profile=profile,
                chart_candidates=chart_candidates,
                selection_warnings=warnings,
            )

    if (
        categorical_indices
        and len(measure_indices) >= 2
        and len(measure_indices) <= MAX_STACKED_BAR_SERIES
        and _all_values_non_negative(rows, measure_indices)
        and (
            _contains_terms(headers, table.get("content", ""), STACKED_BAR_TERMS)
            or _row_totals_are_composition_like(rows, measure_indices)
        )
    ):
        cat_index = categorical_indices[0]
        reason = (
            "Categorical rows with multiple non-negative part or composition series should be shown as a stacked bar."
        )
        chart_candidates.append(_chart_candidate("stacked_bar", 0.91, "high", reason))
        chart_candidates.append(_chart_candidate(
            "bar",
            0.65,
            "medium",
            "Grouped bars remain acceptable when direct series-by-series comparison matters more than total composition.",
        ))
        return _make_recommendation(
            state,
            table,
            rec_index,
            "stacked_bar",
            ["stacked_bar", "bar", "table"],
            "high",
            reason,
            _series_payload(headers, rows, cat_index, measure_indices),
            xlabel=headers[cat_index],
            ylabel=", ".join(headers[index] for index in measure_indices),
            data_profile=profile,
            chart_candidates=chart_candidates,
            selection_warnings=warnings,
        )

    if categorical_indices and len(measure_indices) == 1:
        cat_index = categorical_indices[0]
        value_index = measure_indices[0]
        grouped_series = _grouped_numeric_series(rows, cat_index, value_index)
        if len(grouped_series) >= 2:
            reason = (
                "Repeated numeric measurements within categorical groups should be shown as a boxplot to compare spread."
            )
            chart_candidates.append(_chart_candidate("boxplot", 0.86, "high", reason))
            chart_candidates.append(_chart_candidate(
                "bar",
                0.55,
                "low",
                "Bar charts hide within-group spread unless values have already been aggregated.",
            ))
            return _make_recommendation(
                state,
                table,
                rec_index,
                "boxplot",
                ["boxplot", "table"],
                "high",
                reason,
                {"series": grouped_series},
                xlabel=headers[cat_index],
                ylabel=headers[value_index],
                data_profile=profile,
                chart_candidates=chart_candidates,
                selection_warnings=warnings,
            )

    if (
        not categorical_indices
        and not time_indices
        and len(measure_indices) >= 2
        and len(rows) - 1 >= MIN_DISTRIBUTION_POINTS
        and _contains_terms(headers, table.get("content", ""), GROUPED_DISTRIBUTION_TERMS)
    ):
        grouped_series = _numeric_column_series(headers, rows, measure_indices[:MAX_LINE_BAR_SERIES])
        if len(grouped_series) >= 2:
            reason = (
                "Multiple comparable numeric measurement columns with repeated observations should be shown as a boxplot."
            )
            chart_candidates.append(_chart_candidate("boxplot", 0.82, "medium", reason))
            return _make_recommendation(
                state,
                table,
                rec_index,
                "boxplot",
                ["boxplot", "table"],
                "medium",
                reason,
                {"series": grouped_series},
                xlabel="Series",
                ylabel=", ".join(headers[index] for index in measure_indices[:MAX_LINE_BAR_SERIES]),
                data_profile=profile,
                chart_candidates=chart_candidates,
                selection_warnings=warnings,
            )

    if categorical_indices and composition_indices:
        cat_index = categorical_indices[0]
        value_index = composition_indices[0]
        labels = _column_values(rows, cat_index)[:MAX_CHART_ROWS]
        values = _numeric_values_for_rows(rows, value_index)
        if 2 <= len(_unique_non_empty(labels)) <= 6 and len(values) == len([label for label in labels if _clean_text(label)]):
            reason = (
                "Categorical composition data with non-negative values summing near 1 or 100 "
                "is best summarized as a pie chart; bar is acceptable for comparison emphasis."
            )
            chart_candidates.append(_chart_candidate("pie", 0.95, "high", reason))
            chart_candidates.append(_chart_candidate(
                "bar",
                0.78,
                "medium",
                "Bar remains acceptable when comparing segment magnitudes is more important than whole-part perception.",
            ))
            return _make_recommendation(
                state,
                table,
                rec_index,
                "pie",
                ["pie", "bar"],
                "high",
                reason,
                _series_payload(headers, rows, cat_index, [value_index]),
                xlabel=headers[cat_index],
                ylabel=headers[value_index],
                data_profile=profile,
                chart_candidates=chart_candidates,
                selection_warnings=warnings,
            )

    if time_indices and numeric_indices:
        x_index = time_indices[0]
        y_indices = measure_indices[:3]
        if not y_indices:
            return None
        reason = "Ordered time/step data with numeric measurements should be shown as a line chart to preserve trend direction."
        chart_candidates.append(_chart_candidate("line", 0.92, "high", reason))
        return _make_recommendation(
            state,
            table,
            rec_index,
            "line",
            ["line"],
            "high",
            reason,
            _series_payload(headers, rows, x_index, y_indices),
            xlabel=headers[x_index],
            ylabel=", ".join(headers[index] for index in y_indices),
            data_profile=profile,
            chart_candidates=chart_candidates,
            selection_warnings=warnings,
        )

    if categorical_indices and (measure_indices or composition_indices):
        cat_index = categorical_indices[0]
        y_indices = (measure_indices or composition_indices)[:3]
        reason = "Categorical labels with numeric values should be compared with a bar chart."
        chart_candidates.append(_chart_candidate("bar", 0.88, "high", reason))
        return _make_recommendation(
            state,
            table,
            rec_index,
            "bar",
            ["bar"],
            "high",
            reason,
            _series_payload(headers, rows, cat_index, y_indices),
            xlabel=headers[cat_index],
            ylabel=", ".join(headers[index] for index in y_indices),
            data_profile=profile,
            chart_candidates=chart_candidates,
            selection_warnings=warnings,
        )

    if len(measure_indices) >= 2 and len(rows) - 1 >= 3:
        x_index, y_index = measure_indices[:2]
        reason = (
            "Two numeric measurement variables across multiple observations are suited "
            "to scatter plots for relationship inspection."
        )
        chart_candidates.append(_chart_candidate("scatter", 0.75, "medium", reason))
        return _make_recommendation(
            state,
            table,
            rec_index,
            "scatter",
            ["scatter"],
            "medium",
            reason,
            {
                "x": [_to_float(row[x_index]) or 0 for row in rows[1:MAX_CHART_ROWS + 1]],
                "y": [_to_float(row[y_index]) or 0 for row in rows[1:MAX_CHART_ROWS + 1]],
            },
            xlabel=headers[x_index],
            ylabel=headers[y_index],
            data_profile=profile,
            chart_candidates=chart_candidates,
            selection_warnings=warnings,
        )

    if not categorical_indices and not time_indices and len(measure_indices) == 1 and len(rows) - 1 >= MIN_DISTRIBUTION_POINTS:
        value_index = measure_indices[0]
        values = _numeric_values_for_rows(rows, value_index, limit=MAX_LINE_SCATTER_POINTS)
        if len(values) >= MIN_DISTRIBUTION_POINTS:
            reason = (
                "A single numeric measurement column with enough observations and no safer category/time mapping "
                "is suited to a histogram for distribution shape."
            )
            chart_candidates.append(_chart_candidate("histogram", 0.78, "medium", reason))
            return _make_recommendation(
                state,
                table,
                rec_index,
                "histogram",
                ["histogram", "table"],
                "medium",
                reason,
                {"values": values, "bins": min(10, max(5, round(len(values) ** 0.5)))},
                xlabel=headers[value_index],
                ylabel="Frequency count",
                data_profile=profile,
                chart_candidates=chart_candidates,
                selection_warnings=warnings,
            )

    if len(rows) - 1 <= MAX_TABLE_FIGURE_ROWS:
        reason = (
            "The evidence has no reliable category, ordered time, composition, or two-measure relationship; "
            "preserve exact values as a table figure."
        )
        chart_candidates.append(_chart_candidate("table", 0.7, "medium", reason))
        return _make_recommendation(
            state,
            table,
            rec_index,
            "table",
            ["table"],
            "medium",
            reason,
            {"columns": headers, "rows": rows[1:MAX_TABLE_FIGURE_ROWS + 1]},
            data_profile=profile,
            chart_candidates=chart_candidates,
            selection_warnings=warnings,
        )

    return None


def _recommendation_score(recommendation: dict) -> float:
    candidates = recommendation.get("chart_candidates", []) or []
    top_score = 0.0
    if candidates and isinstance(candidates[0], dict):
        try:
            top_score = float(candidates[0].get("score", 0) or 0)
        except (TypeError, ValueError):
            top_score = 0.0
    transform = recommendation.get("data_transform", {}) if isinstance(recommendation.get("data_transform", {}), dict) else {}
    if transform.get("status") == "transformed":
        top_score += 0.03
        output_shape = transform.get("output_shape", {}) if isinstance(transform.get("output_shape", {}), dict) else {}
        if int(output_shape.get("rows", 0) or 0) <= MAX_BAR_CATEGORIES:
            top_score += 0.02
    top_score -= 0.01 * len(recommendation.get("selection_warnings", []) or [])
    return top_score


def recommend_figures_from_evidence(state: ReportState, evidence: list[dict]) -> list[dict]:
    """Build chart recommendations from table-shaped evidence."""
    recommendations: list[dict] = []
    for table in _table_candidates(evidence):
        variants = build_table_variants(
            table,
            max_bar_categories=MAX_BAR_CATEGORIES,
            max_pie_slices=MAX_PIE_SLICES,
        )
        candidates = [
            rec for variant in variants
            if (rec := _recommend_single_table(state, variant, len(recommendations) + 1)) is not None
        ]
        if not candidates:
            continue
        recommendations.append(max(candidates, key=_recommendation_score))

    return recommendations


def _write_recommendation_report(state: ReportState, recommendations: list[dict]) -> str:
    report = {
        "job_id": state.job_id,
        "status": "available" if recommendations else "no_table_chart_candidates",
        "recommendation_count": len(recommendations),
        "recommendations": recommendations,
    }
    return write_json_artifact(state, "figure_recommendations.json", report)


def run_figure_recommend(state: ReportState) -> ReportState:
    """Recommend chart types from parsed table evidence before agent authoring."""
    evidence = load_jsonl(state.sources.get("evidence_ledger_path"))
    recommendations = recommend_figures_from_evidence(state, evidence)
    path = _write_recommendation_report(state, recommendations)
    state.output["figure_recommendations_path"] = path
    state.plan["figure_recommendation_count"] = len(recommendations)
    return state
