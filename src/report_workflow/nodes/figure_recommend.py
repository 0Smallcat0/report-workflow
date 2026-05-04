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
    if any(term in text for term in COMPOSITION_TERMS):
        return True
    total = sum(values)
    return 99 <= total <= 101 or 0.99 <= total <= 1.01


def _unique_non_empty(values: list[str]) -> list[str]:
    seen: set[str] = set()
    unique: list[str] = []
    for value in values:
        clean = _clean_text(value)
        if clean and clean not in seen:
            seen.add(clean)
            unique.append(clean)
    return unique


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
        columns = [_column_values(rows, index) for index in range(len(headers))]
        numeric_indices = [index for index, values in enumerate(columns) if _is_numeric_column(values)]
        categorical_indices = [
            index
            for index, values in enumerate(columns)
            if index not in numeric_indices and 2 <= len(_unique_non_empty(values)) <= 12
        ]
        time_indices = [index for index, values in enumerate(columns) if _is_time_like(headers[index], values)]

        if not numeric_indices:
            if len(rows) - 1 <= MAX_TABLE_FIGURE_ROWS:
                recommendations.append(_make_recommendation(
                    state,
                    table,
                    len(recommendations) + 1,
                    "table",
                    ["table"],
                    "medium",
                    "Table-shaped evidence has no numeric column; preserve exact values as a table figure.",
                    {"columns": headers, "rows": rows[1:MAX_TABLE_FIGURE_ROWS + 1]},
                ))
            continue

        label_index = (time_indices or categorical_indices or [0])[0]
        y_indices = [index for index in numeric_indices if index != label_index] or numeric_indices[:1]

        if categorical_indices:
            cat_index = categorical_indices[0]
            value_index = y_indices[0]
            labels = _column_values(rows, cat_index)[:MAX_CHART_ROWS]
            values = _numeric_values(_column_values(rows, value_index)[:MAX_CHART_ROWS])
            if 2 <= len(_unique_non_empty(labels)) <= 6 and values and all(value >= 0 for value in values):
                if _is_composition_context(headers, values, table.get("content", "")):
                    recommendations.append(_make_recommendation(
                        state,
                        table,
                        len(recommendations) + 1,
                        "pie",
                        ["pie", "bar"],
                        "high",
                        "Categorical composition data with non-negative share/percentage values is best summarized as a pie chart; bar is acceptable for comparison emphasis.",
                        _series_payload(headers, rows, cat_index, [value_index]),
                        xlabel=headers[cat_index],
                        ylabel=headers[value_index],
                    ))
                    continue

        if time_indices and y_indices:
            x_index = time_indices[0]
            recommendations.append(_make_recommendation(
                state,
                table,
                len(recommendations) + 1,
                "line",
                ["line"],
                "high",
                "Ordered time/step data with numeric measurements should be shown as a line chart to preserve trend direction.",
                _series_payload(headers, rows, x_index, y_indices[:3]),
                xlabel=headers[x_index],
                ylabel=", ".join(headers[index] for index in y_indices[:3]),
            ))
            continue

        if len(numeric_indices) >= 2 and len(rows) - 1 >= 3:
            x_index, y_index = numeric_indices[:2]
            recommendations.append(_make_recommendation(
                state,
                table,
                len(recommendations) + 1,
                "scatter",
                ["scatter"],
                "medium",
                "Two numeric variables across multiple observations are suited to scatter plots for relationship inspection.",
                {
                    "x": [_to_float(row[x_index]) or 0 for row in rows[1:MAX_CHART_ROWS + 1]],
                    "y": [_to_float(row[y_index]) or 0 for row in rows[1:MAX_CHART_ROWS + 1]],
                },
                xlabel=headers[x_index],
                ylabel=headers[y_index],
            ))
            continue

        if categorical_indices:
            cat_index = categorical_indices[0]
            recommendations.append(_make_recommendation(
                state,
                table,
                len(recommendations) + 1,
                "bar",
                ["bar"],
                "high",
                "Categorical labels with numeric values should be compared with a bar chart.",
                _series_payload(headers, rows, cat_index, y_indices[:3]),
                xlabel=headers[cat_index],
                ylabel=", ".join(headers[index] for index in y_indices[:3]),
            ))
            continue

        recommendations.append(_make_recommendation(
            state,
            table,
            len(recommendations) + 1,
            "table",
            ["table"],
            "medium",
            "The table contains numeric data but no clear category, time, or two-variable relationship; preserve exact values as a table figure.",
            {"columns": headers, "rows": rows[1:MAX_TABLE_FIGURE_ROWS + 1]},
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
