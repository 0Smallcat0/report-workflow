"""FIGURE_PLAN_AUDIT node.

This module audits agent-authored figure plans against deterministic chart
recommendations.  Keeping it separate from figure recommendation avoids mixing
data-shape inference with downstream contract enforcement.
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
from .figure_recommend import (
    MAX_BAR_CATEGORIES,
    MAX_CATEGORY_LABEL_LENGTH,
    MAX_LINE_BAR_SERIES,
    MAX_LINE_SCATTER_POINTS,
    MAX_PIE_SLICES,
    MAX_STACKED_BAR_SERIES,
    MAX_TABLE_COLUMNS,
    MAX_TABLE_FIGURE_ROWS,
    recommend_figures_from_evidence,
)
from .figure_utils import (
    clean_text as _clean_text,
    to_float as _to_float,
    unit_signature as _unit_signature,
)
from .figure_types import (
    SUPPORTED_FIGURE_TYPES_SET,
    SUPPORTED_FIGURE_TYPES_TEXT,
    SUPPORTED_OUTPUT_FORMATS_SET,
    SUPPORTED_OUTPUT_FORMATS_TEXT,
)


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
    if not isinstance(payload, dict):
        return {"_load_error": "figure_plan.json must contain an object", "figures": []}, path
    return payload, path


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


def _generic_title(title: str, figure_id: str) -> bool:
    normalized = title.casefold()
    generic_titles = {
        "",
        "chart",
        "chart title",
        "figure",
        "figure title",
        "publication-safe chart title",
        "untitled",
        "todo",
        "tbd",
    }
    return normalized in generic_titles or normalized == figure_id.casefold()


def _label_has_unit(label: str) -> bool:
    text = label.casefold()
    if not text:
        return False
    unit_tokens = (
        "%",
        "(",
        ")",
        "/",
        "percent",
        "percentage",
        "share",
        "ratio",
        "rate",
        "count",
        "number",
        "score",
        "value",
        "index",
        "seconds",
        "second",
        "minutes",
        "minute",
        "hours",
        "hour",
        "days",
        "day",
        "voltage",
        "current",
        "temperature",
        "mass",
        "length",
        "distance",
        "time",
    )
    return any(token in text for token in unit_tokens)


def _label_values(data: dict) -> list[str]:
    labels = data.get("labels", [])
    if isinstance(labels, list):
        return [_clean_text(label) for label in labels]
    x_labels = data.get("x_labels", [])
    if isinstance(x_labels, list):
        return [_clean_text(label) for label in x_labels]
    rows = data.get("rows", [])
    if isinstance(rows, list):
        values = []
        for row in rows:
            if isinstance(row, list) and row:
                values.append(_clean_text(row[0]))
            elif isinstance(row, dict) and row:
                first_value = next(iter(row.values()))
                values.append(_clean_text(first_value))
        return values
    return []


def _series_values(data: dict) -> list[dict]:
    series = data.get("series", [])
    return [item for item in series if isinstance(item, dict)] if isinstance(series, list) else []


def _numeric_data_values(data: dict) -> list[float]:
    values: list[float] = []
    raw_values = data.get("values", [])
    if isinstance(raw_values, list):
        for value in raw_values:
            if isinstance(value, list):
                values.extend(number for item in value if (number := _to_float(item)) is not None)
            else:
                number = _to_float(value)
                if number is not None:
                    values.append(number)
    for item in _series_values(data):
        raw_series = item.get("values", [])
        if isinstance(raw_series, list):
            values.extend(number for value in raw_series if (number := _to_float(value)) is not None)
    return values


def _point_count(figure_type: str, data: dict) -> int:
    if figure_type == "scatter":
        x_vals = data.get("x", [])
        y_vals = data.get("y", [])
        return max(len(x_vals) if isinstance(x_vals, list) else 0, len(y_vals) if isinstance(y_vals, list) else 0)
    if figure_type == "histogram":
        values = data.get("values", [])
        return len(values) if isinstance(values, list) else 0
    if figure_type == "heatmap":
        values = data.get("values", [])
        if isinstance(values, list):
            return sum(len(row) for row in values if isinstance(row, list))
        return 0
    series = _series_values(data)
    if series:
        return max((len(item.get("values", []) or []) for item in series), default=0)
    return len(_label_values(data))


def _readability_issue(issue_type: str, figure: dict, index: int, detail: str, repair_hint: str, **extra: Any) -> dict:
    issue = {
        "severity": "warning",
        "type": issue_type,
        "figure_id": figure.get("figure_id", f"index_{index}"),
        "detail": detail,
        "repair_hint": repair_hint,
    }
    issue.update(extra)
    return issue


#: Two or more multi-character words joined by underscores — median_processing_
#: minutes, baseline_manual, setup_cost. Deliberately not one-character parts,
#: because C_D, T_in and Re_D are how engineering writes its own symbols and
#: flagging those would be worse than the leak this catches.
_IDENTIFIER_RE = re.compile(r"\b[A-Za-z0-9]{2,}_[A-Za-z0-9]{2,}(?:_[A-Za-z0-9]+)*\b")


def _identifier_like(text: str) -> list[str]:
    """Raw column names sitting where a reader expects prose."""
    return _IDENTIFIER_RE.findall(_clean_text(text or ""))


def _publication_text_issues(figure: dict, index: int) -> list[dict]:
    """Identifiers reaching the page through a figure's own text.

    The brief tells the author to translate data identifiers into plain
    language and to keep internal identifiers out of publication text, and the
    captions and prose obey it. The tables did not: a finished report went out
    with a column headed median_processing_minutes and a row labelled
    baseline_manual, sitting under a caption reading "Median processing time per
    note, manual baseline versus structured workflow (minutes)".

    Every readability rule beside this one is about charts, and a table is not a
    chart, so nothing looked at the part of a figure that is only words.
    """
    data = figure.get("data", {}) if isinstance(figure.get("data", {}), dict) else {}
    candidates: list[str] = [
        str(figure.get("title") or ""),
        str(figure.get("xlabel") or ""),
        str(figure.get("ylabel") or ""),
    ]
    candidates.extend(str(column) for column in (data.get("columns") or []))
    for row in (data.get("rows") or [])[:50]:
        if isinstance(row, (list, tuple)) and row:
            candidates.append(str(row[0]))
    candidates.extend(str(label) for label in _label_values(data))
    for item in _series_values(data):
        candidates.append(str(item.get("name", "")))

    found: list[str] = []
    for text in candidates:
        for token in _identifier_like(text):
            if token not in found:
                found.append(token)
    if not found:
        return []
    return [_readability_issue(
        "raw_identifier_in_figure_text",
        figure,
        index,
        "Figure text carries raw data identifiers where the reader expects "
        f"words: {', '.join(found[:5])}",
        "Rename these in the figure plan the way the caption already names "
        "them; the column name in the source stays as it is.",
        identifiers=found[:10],
    )]


def _chart_semantic_issues(figure: dict, index: int) -> list[dict]:
    figure_type = str(figure.get("figure_type") or "").strip().lower()
    data = figure.get("data", {}) if isinstance(figure.get("data", {}), dict) else {}
    issues: list[dict] = []
    numeric_values = _numeric_data_values(data)
    if figure_type in {"pie", "stacked_bar"} and any(value < 0 for value in numeric_values):
        issues.append(_readability_issue(
            "negative_composition_values",
            figure,
            index,
            "Composition charts cannot represent negative values without misleading part-to-whole semantics.",
            "Use a regular bar/line chart for signed values, split positive and negative components, or keep the data as a table.",
            severity="hard",
            negative_value_count=sum(1 for value in numeric_values if value < 0),
        ))

    if figure_type not in {"bar", "line", "error_bar", "stacked_bar"}:
        return issues
    series = _series_values(data)
    if len(series) < 2:
        return issues
    units_by_series: dict[str, str] = {}
    for item in series:
        name = _clean_text(item.get("name", ""))
        unit = _unit_signature(name)
        if unit:
            units_by_series[name or "<unnamed>"] = unit
    distinct_units = sorted(set(units_by_series.values()))
    if len(distinct_units) <= 1:
        return issues
    issues.append(_readability_issue(
        "mixed_units_same_axis",
        figure,
        index,
        "Multi-series chart places explicitly mixed units on one shared y-axis.",
        "Split the series into separate charts or keep the values as a table.",
        severity="hard",
        units=units_by_series,
    ))
    return issues


def _chart_readability_issues(figure: dict, index: int) -> list[dict]:
    figure_type = str(figure.get("figure_type") or "").strip().lower()
    figure_id = str(figure.get("figure_id") or f"index_{index}")
    title = _clean_text(figure.get("title", ""))
    data = figure.get("data", {}) if isinstance(figure.get("data", {}), dict) else {}
    labels = _label_values(data)
    series = _series_values(data)
    issues: list[dict] = []

    if _generic_title(title, figure_id):
        issues.append(_readability_issue(
            "missing_chart_title",
            figure,
            index,
            "Figure has no publication-safe title or uses a placeholder/generic title.",
            "Add a specific chart title that names the measured relationship or comparison.",
        ))

    if figure_type in {"bar", "line", "scatter", "histogram", "boxplot", "error_bar", "stacked_bar"}:
        xlabel = _clean_text(figure.get("xlabel", ""))
        ylabel = _clean_text(figure.get("ylabel", ""))
        if not xlabel:
            issues.append(_readability_issue(
                "missing_axis_label",
                figure,
                index,
                "Chart is missing an x-axis label.",
                "Set xlabel to the category, time, or independent variable represented on the x-axis.",
                axis="x",
            ))
        if not ylabel:
            issues.append(_readability_issue(
                "missing_axis_label",
                figure,
                index,
                "Chart is missing a y-axis label.",
                "Set ylabel to the measured value and include units when available.",
                axis="y",
            ))
        elif not _label_has_unit(ylabel):
            issues.append(_readability_issue(
                "unit_label_unclear",
                figure,
                index,
                "Y-axis label does not clearly state a unit or value scale.",
                "Add units or a clear scale term to ylabel, such as '(V)', '(%)', 'count', or 'score'.",
                axis="y",
            ))

    if figure_type in {"bar", "line", "error_bar"} and len(series) > MAX_LINE_BAR_SERIES:
        issues.append(_readability_issue(
            "too_many_data_points",
            figure,
            index,
            f"Chart has {len(series)} series; more than {MAX_LINE_BAR_SERIES} series is hard to read.",
            "Reduce the number of plotted series or split the chart into simpler figures.",
            series_count=len(series),
            threshold=MAX_LINE_BAR_SERIES,
        ))
    if figure_type in {"bar", "line", "stacked_bar", "error_bar"} and len(series) > 1:
        generic_names = {
            "",
            "series",
            "series 1",
            "series 2",
            "value",
            "values",
            "data",
        }
        missing = [
            _clean_text(item.get("name", ""))
            for item in series
            if _clean_text(item.get("name", "")).casefold() in generic_names
        ]
        if missing:
            issues.append(_readability_issue(
                "legend_label_missing",
                figure,
                index,
                "Multi-series chart has missing or generic legend labels.",
                "Give each series a meaningful name that matches the source evidence.",
            ))

    if figure_type == "stacked_bar" and len(series) > MAX_STACKED_BAR_SERIES:
        issues.append(_readability_issue(
            "too_many_data_points",
            figure,
            index,
            f"Stacked bar chart has {len(series)} series; more than {MAX_STACKED_BAR_SERIES} is hard to read.",
            "Reduce the number of stacked series or move the full breakdown to a table.",
            series_count=len(series),
            threshold=MAX_STACKED_BAR_SERIES,
        ))

    if figure_type in {"bar", "stacked_bar", "error_bar"} and len(labels) > MAX_BAR_CATEGORIES:
        issues.append(_readability_issue(
            "too_many_categories",
            figure,
            index,
            f"Chart has {len(labels)} categories; more than {MAX_BAR_CATEGORIES} is hard to scan.",
            "Group minor categories, switch to a table, or split the chart.",
            category_count=len(labels),
            threshold=MAX_BAR_CATEGORIES,
        ))

    if figure_type == "pie" and len(labels) > MAX_PIE_SLICES:
        issues.append(_readability_issue(
            "pie_too_many_categories",
            figure,
            index,
            f"Pie chart has {len(labels)} slices; more than {MAX_PIE_SLICES} is hard to read.",
            "Use a bar chart, group small slices, or keep exact values in a table.",
            category_count=len(labels),
            threshold=MAX_PIE_SLICES,
        ))

    if figure_type in {"line", "scatter", "histogram", "heatmap"}:
        points = _point_count(figure_type, data)
        if points > MAX_LINE_SCATTER_POINTS:
            issues.append(_readability_issue(
                "too_many_data_points",
                figure,
                index,
                f"Chart has {points} data points; more than {MAX_LINE_SCATTER_POINTS} may be unreadable at report scale.",
                "Downsample, aggregate, or use a table/appendix for dense data.",
                point_count=points,
                threshold=MAX_LINE_SCATTER_POINTS,
            ))

    if figure_type == "table":
        rows = data.get("rows", [])
        columns = data.get("columns", [])
        row_count = len(rows) if isinstance(rows, list) else 0
        column_count = len(columns) if isinstance(columns, list) else 0
        if row_count > MAX_TABLE_FIGURE_ROWS or column_count > MAX_TABLE_COLUMNS:
            issues.append(_readability_issue(
                "too_many_categories",
                figure,
                index,
                (
                    f"Table figure has {row_count} rows and {column_count} columns; "
                    f"recommended maximum is {MAX_TABLE_FIGURE_ROWS} rows and {MAX_TABLE_COLUMNS} columns."
                ),
                "Trim to the key values for the main report and move full detail to supplementary material.",
                row_count=row_count,
                column_count=column_count,
            ))

    long_labels = [label for label in labels if len(label) > MAX_CATEGORY_LABEL_LENGTH]
    if long_labels:
        issues.append(_readability_issue(
            "category_labels_too_long",
            figure,
            index,
            f"{len(long_labels)} category label(s) exceed {MAX_CATEGORY_LABEL_LENGTH} characters.",
            "Shorten labels or use a table when full category text must be preserved.",
            examples=long_labels[:3],
            threshold=MAX_CATEGORY_LABEL_LENGTH,
        ))

    return issues


def _transform_provenance_issues(figure: dict, rec: dict, index: int) -> list[dict]:
    rec_transform = rec.get("data_transform", {}) if isinstance(rec.get("data_transform", {}), dict) else {}
    if rec_transform.get("status") != "transformed":
        return []
    figure_transform = figure.get("data_transform", {}) if isinstance(figure.get("data_transform", {}), dict) else {}
    if figure_transform.get("status") == "transformed":
        return []
    if _selection_reason(figure):
        return []
    operations = ", ".join(str(item) for item in rec_transform.get("operations", []) or []) or "unknown"
    return [_readability_issue(
        "transformed_recommendation_without_provenance",
        figure,
        index,
        (
            "Figure is linked to a recommendation built from transformed source data, "
            "but the figure entry does not preserve data_transform metadata or explain the derived view."
        ),
        "Keep the recommendation's data_transform block in figure_plan.json or add chart_selection_reason for the manual edit.",
        recommendation_id=rec.get("recommendation_id"),
        operations=operations,
    )]


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
        if figure_type not in SUPPORTED_FIGURE_TYPES_SET:
            issue = {
                "severity": "hard",
                "type": "unsupported_figure_type",
                "figure_id": figure.get("figure_id", f"index_{index}"),
                "selected_figure_type": figure_type,
                "supported_figure_types": sorted(SUPPORTED_FIGURE_TYPES_SET),
                "detail": (
                    f"Figure selects unsupported figure_type {figure_type!r}. "
                    f"Supported values: {SUPPORTED_FIGURE_TYPES_TEXT}."
                ),
                "repair_hint": "Use a supported figure_type or remove the figure from figure_plan.json.",
            }
            issues.append(issue)
            hard_issues.append(issue)
            continue
        output_format = str(figure.get("output_format", "png")).strip().lower().lstrip(".") or "png"
        if output_format not in SUPPORTED_OUTPUT_FORMATS_SET:
            issue = {
                "severity": "hard",
                "type": "unsupported_output_format",
                "figure_id": figure.get("figure_id", f"index_{index}"),
                "selected_output_format": output_format,
                "supported_output_formats": sorted(SUPPORTED_OUTPUT_FORMATS_SET),
                "detail": (
                    f"Figure selects unsupported output_format {output_format!r}. "
                    f"Supported values: {SUPPORTED_OUTPUT_FORMATS_TEXT}."
                ),
                "repair_hint": "Use png or svg output_format, or omit output_format to use png.",
            }
            issues.append(issue)
            hard_issues.append(issue)
            continue
        issues.extend(_publication_text_issues(figure, index))
        semantic_issues = _chart_semantic_issues(figure, index)
        if semantic_issues:
            issues.extend(semantic_issues)
            hard_issues.extend(issue for issue in semantic_issues if issue.get("severity") == "hard")
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
            issues.extend(_chart_readability_issues(figure, index))
            continue

        matched_recommendations.add(str(rec.get("recommendation_id")))
        acceptable = {str(item).lower() for item in rec.get("acceptable_figure_types", []) or []}
        recommended = str(rec.get("recommended_figure_type") or "").lower()
        if recommended:
            acceptable.add(recommended)
        if figure_type in acceptable:
            issues.extend(_transform_provenance_issues(figure, rec, index))
            issues.extend(_chart_readability_issues(figure, index))
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
        issues.extend(_transform_provenance_issues(figure, rec, index))
        issues.extend(_chart_readability_issues(figure, index))

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
