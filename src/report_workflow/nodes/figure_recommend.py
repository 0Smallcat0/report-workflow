"""FIGURE_RECOMMEND and FIGURE_PLAN_AUDIT nodes.

This module keeps chart choice deterministic and inspectable. It does not
author prose; it recommends chart types from table-shaped evidence and audits
agent-authored figure_plan.json against those recommendations.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..errors import QAHardBlockError
from ..policies import get_policy
from ..runtime_support import load_jsonl, write_json_artifact
from ..state import ReportState, run_dir_for


MAX_CHART_ROWS = 24
MAX_TABLE_FIGURE_ROWS = 12
MIN_CHART_ROWS = 2
NUMERIC_RATIO_THRESHOLD = 0.75

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
TEXT_MIXED_ROLE = "text/mixed"


def _clean_text(value: Any) -> str:
    return " ".join(str(value if value is not None else "").strip().split())


def _to_float(value: Any) -> float | None:
    text = _clean_text(value)
    if not text:
        return None
    text = text.replace(",", "")
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    text = text.rstrip("%")
    try:
        return float(text)
    except ValueError:
        return None


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
    if date_like / len(non_empty) >= 0.6:
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
        match = re.match(r"^(\d{4})[-/](\d{1,2})(?:[-/](\d{1,2}))?", value)
        if match:
            date_keys.append(tuple(int(part) for part in match.groups(default="1")))
            continue
        match = re.match(r"^(\d{1,2}):(\d{2})", value)
        if match:
            date_keys.append(tuple(int(part) for part in match.groups()))
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
    title = f"{figure_type.title()} view of {Path(str(title_source)).stem or title_source}"
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
        "figure_plan": figure_plan,
    }


def recommend_figures_from_evidence(state: ReportState, evidence: list[dict]) -> list[dict]:
    """Build chart recommendations from table-shaped evidence."""
    recommendations: list[dict] = []
    for table in _table_candidates(evidence):
        rows = table.get("rows", [])
        if len(rows) < 3:
            continue
        headers = [_clean_text(header) or f"Column {index + 1}" for index, header in enumerate(rows[0])]
        profile = _profile_table(headers, rows, table.get("content", ""))
        summary = profile["summary"]
        warnings = _selection_warnings(profile)
        categorical_indices = _indices_with_role(profile, "categorical")
        time_indices = _indices_with_role(profile, "time_like")
        numeric_indices = _indices_with_role(profile, "numeric_measure")
        composition_indices = _indices_with_role(profile, "composition_value")
        chart_candidates: list[dict] = []

        if summary.get("parameter_table") and len(rows) - 1 <= MAX_TABLE_FIGURE_ROWS:
            reason = (
                "Parameter, unit, formula, or calculation-shaped evidence should remain a table so exact values and units stay visible."
            )
            chart_candidates.append(_chart_candidate("table", 0.9, "high", reason))
            recommendations.append(_make_recommendation(
                state,
                table,
                len(recommendations) + 1,
                "table",
                ["table"],
                "high",
                reason,
                {"columns": headers, "rows": rows[1:MAX_TABLE_FIGURE_ROWS + 1]},
                data_profile=profile,
                chart_candidates=chart_candidates,
                selection_warnings=warnings,
            ))
            continue

        if summary.get("missing_ratio", 0) >= 0.25 and len(rows) - 1 <= MAX_TABLE_FIGURE_ROWS:
            reason = "High missing-value density makes a compact table safer than a potentially misleading chart."
            chart_candidates.append(_chart_candidate("table", 0.78, "medium", reason))
            recommendations.append(_make_recommendation(
                state,
                table,
                len(recommendations) + 1,
                "table",
                ["table"],
                "medium",
                reason,
                {"columns": headers, "rows": rows[1:MAX_TABLE_FIGURE_ROWS + 1]},
                data_profile=profile,
                chart_candidates=chart_candidates,
                selection_warnings=warnings,
            ))
            continue

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
                recommendations.append(_make_recommendation(
                    state,
                    table,
                    len(recommendations) + 1,
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
                ))
                continue

        if time_indices and numeric_indices:
            x_index = time_indices[0]
            y_indices = numeric_indices[:3]
            reason = "Ordered time/step data with numeric measurements should be shown as a line chart to preserve trend direction."
            chart_candidates.append(_chart_candidate("line", 0.92, "high", reason))
            recommendations.append(_make_recommendation(
                state,
                table,
                len(recommendations) + 1,
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
            ))
            continue

        if categorical_indices and (numeric_indices or composition_indices):
            cat_index = categorical_indices[0]
            y_indices = (numeric_indices or composition_indices)[:3]
            reason = "Categorical labels with numeric values should be compared with a bar chart."
            chart_candidates.append(_chart_candidate("bar", 0.88, "high", reason))
            recommendations.append(_make_recommendation(
                state,
                table,
                len(recommendations) + 1,
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
            ))
            continue

        if len(numeric_indices) >= 2 and len(rows) - 1 >= 3:
            x_index, y_index = numeric_indices[:2]
            reason = (
                "Two numeric measurement variables across multiple observations are suited "
                "to scatter plots for relationship inspection."
            )
            chart_candidates.append(_chart_candidate("scatter", 0.75, "medium", reason))
            recommendations.append(_make_recommendation(
                state,
                table,
                len(recommendations) + 1,
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
            ))
            continue

        if len(rows) - 1 <= MAX_TABLE_FIGURE_ROWS:
            reason = (
                "The evidence has no reliable category, ordered time, composition, or two-measure relationship; "
                "preserve exact values as a table figure."
            )
            chart_candidates.append(_chart_candidate("table", 0.7, "medium", reason))
            recommendations.append(_make_recommendation(
                state,
                table,
                len(recommendations) + 1,
                "table",
                ["table"],
                "medium",
                reason,
                {"columns": headers, "rows": rows[1:MAX_TABLE_FIGURE_ROWS + 1]},
                data_profile=profile,
                chart_candidates=chart_candidates,
                selection_warnings=warnings,
            ))

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


def _load_recommendations(state: ReportState) -> list[dict]:
    path = state.output.get("figure_recommendations_path")
    if path and Path(path).exists():
        try:
            payload = json.loads(Path(path).read_text(encoding="utf-8"))
            return [item for item in payload.get("recommendations", []) if isinstance(item, dict)]
        except Exception:
            return []
    evidence = load_jsonl(state.sources.get("evidence_ledger_path"))
    return recommend_figures_from_evidence(state, evidence)


def _load_figure_plan(state: ReportState) -> tuple[dict | None, Path]:
    path = run_dir_for(state) / "section_drafts" / "figure_plan.json"
    if not path.exists():
        return None, path
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        return {"_load_error": str(exc), "figures": []}, path
    return payload if isinstance(payload, dict) else {"_load_error": "figure_plan.json must contain an object", "figures": []}, path


def _figure_evidence_ids(figure: dict) -> set[str]:
    values: set[str] = set()
    for key in ("source_evidence_id", "evidence_id"):
        raw = figure.get(key)
        if raw:
            values.add(str(raw))
    for key in ("source_evidence_ids", "evidence_ids"):
        raw_list = figure.get(key) or []
        if isinstance(raw_list, list):
            values.update(str(item) for item in raw_list if item)
    return values


def _selection_reason(figure: dict) -> str:
    return _clean_text(
        figure.get("chart_selection_reason")
        or figure.get("selection_reason")
        or figure.get("reason")
        or ""
    )


def audit_figure_plan(state: ReportState, recommendations: list[dict], figure_plan: dict | None, plan_path: Path) -> dict:
    """Audit figure_plan.json chart choices against deterministic recommendations."""
    issues: list[dict] = []
    hard_issues: list[dict] = []
    recommendation_by_id = {str(rec.get("recommendation_id")): rec for rec in recommendations if rec.get("recommendation_id")}
    recommendations_by_evidence: dict[str, list[dict]] = {}
    for rec in recommendations:
        for evidence_id in rec.get("evidence_ids", []) or []:
            recommendations_by_evidence.setdefault(str(evidence_id), []).append(rec)

    if figure_plan is None:
        if recommendations:
            issues.append({
                "severity": "warning",
                "type": "recommendations_not_used",
                "detail": "figure_recommendations.json contains chart candidates, but section_drafts/figure_plan.json is missing.",
                "repair_hint": "Adopt a recommendation or document why the report should not include a chart.",
            })
        figures: list[dict] = []
    else:
        if figure_plan.get("_load_error"):
            issue = {
                "severity": "hard",
                "type": "malformed_figure_plan",
                "detail": str(figure_plan.get("_load_error")),
                "repair_hint": "Rewrite section_drafts/figure_plan.json as a JSON object with a figures array.",
            }
            issues.append(issue)
            hard_issues.append(issue)
        raw_figures = figure_plan.get("figures", [])
        if not isinstance(raw_figures, list):
            issue = {
                "severity": "hard",
                "type": "malformed_figure_plan",
                "detail": "figure_plan.json field 'figures' must be a list.",
                "repair_hint": "Rewrite section_drafts/figure_plan.json with a figures array.",
            }
            issues.append(issue)
            hard_issues.append(issue)
            figures = []
        else:
            figures = raw_figures

    strict_contract = get_policy(state.spec.get("report_profile", "academic_paper")).figure.figure_contract_required
    matched_recommendations: set[str] = set()

    for index, figure in enumerate(figures):
        if not isinstance(figure, dict):
            issue = {
                "severity": "hard",
                "type": "malformed_figure_entry",
                "figure_id": f"index_{index}",
                "detail": f"Figure entry at index {index} must be an object.",
                "repair_hint": "Each item in figure_plan.json figures must be a JSON object.",
            }
            issues.append(issue)
            hard_issues.append(issue)
            continue
        figure_type = str(figure.get("figure_type") or "").strip().lower()
        rec = recommendation_by_id.get(str(figure.get("recommendation_id") or ""))
        if rec is None:
            evidence_ids = _figure_evidence_ids(figure)
            for evidence_id in evidence_ids:
                if recommendations_by_evidence.get(evidence_id):
                    rec = recommendations_by_evidence[evidence_id][0]
                    break

        if rec is None:
            if figure.get("data") and not _selection_reason(figure):
                issues.append({
                    "severity": "warning",
                    "type": "unlinked_chart_selection",
                    "figure_id": figure.get("figure_id", f"index_{index}"),
                    "detail": "Figure has chart data but no recommendation_id/source_evidence_ids/chart_selection_reason.",
                    "repair_hint": "Link the figure to a recommendation or add chart_selection_reason.",
                })
            continue

        matched_recommendations.add(str(rec.get("recommendation_id")))
        acceptable = {str(item).lower() for item in rec.get("acceptable_figure_types", []) or []}
        recommended = str(rec.get("recommended_figure_type") or "").lower()
        if recommended:
            acceptable.add(recommended)
        if figure_type in acceptable:
            continue

        reason = _selection_reason(figure)
        severity = "warning"
        if strict_contract and rec.get("confidence") == "high" and not reason:
            severity = "hard"
        issue = {
            "severity": severity,
            "type": "chart_type_mismatch",
            "figure_id": figure.get("figure_id", f"index_{index}"),
            "selected_figure_type": figure_type,
            "recommended_figure_type": recommended,
            "acceptable_figure_types": sorted(acceptable),
            "recommendation_id": rec.get("recommendation_id"),
            "detail": (
                f"Figure selects {figure_type!r}, but deterministic chart analysis recommends "
                f"{recommended!r} for this evidence. Reason supplied: {reason or '<none>'}."
            ),
            "repair_hint": "Use the recommended chart type or add a specific chart_selection_reason for the deviation.",
        }
        issues.append(issue)
        if severity == "hard":
            hard_issues.append(issue)

    if recommendations and figures:
        unused_high_confidence = [
            rec.get("recommendation_id")
            for rec in recommendations
            if rec.get("confidence") == "high" and rec.get("recommendation_id") not in matched_recommendations
        ]
        if unused_high_confidence:
            issues.append({
                "severity": "warning",
                "type": "high_confidence_recommendations_unused",
                "recommendation_ids": unused_high_confidence,
                "detail": "High-confidence chart recommendations were not linked from figure_plan.json.",
                "repair_hint": "Use recommendation_id in figure_plan.json, or explain omission in the report workflow notes.",
            })

    return {
        "job_id": state.job_id,
        "status": "failed" if hard_issues else ("passed_with_warnings" if issues else "passed"),
        "figure_plan_path": str(plan_path),
        "recommendation_count": len(recommendations),
        "figure_count": len(figures),
        "issues": issues,
        "hard_issues": hard_issues,
    }


def run_figure_plan_audit(state: ReportState) -> ReportState:
    """Audit chart type choices before FIGURE_BUILD executes the plan."""
    recommendations = _load_recommendations(state)
    figure_plan, plan_path = _load_figure_plan(state)
    report = audit_figure_plan(state, recommendations, figure_plan, plan_path)
    path = write_json_artifact(state, "figure_plan_audit_report.json", report)
    state.qa["figure_plan_audit_report_path"] = path
    if report["hard_issues"]:
        details = "; ".join(issue.get("detail", "") for issue in report["hard_issues"][:3])
        raise QAHardBlockError(f"FIGURE_PLAN_AUDIT: {len(report['hard_issues'])} hard issue(s): {details}")
    return state
