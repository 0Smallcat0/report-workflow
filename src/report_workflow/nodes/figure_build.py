"""FIGURE_BUILD node - generate figures from agent-authored figure_plan.json.

Sits between SECTION_DRAFT and REVISION_APPLY / MERGE_DRAFT in the validate phase.
The agent produces figure_plan.json (spec + data); this node executes matplotlib
to render the actual figure files.

Output: figures/<job_id>/ directory + figure_manifest.json
"""
import json
import logging
import re
from pathlib import Path
from typing import Any

from ..state import ReportState, WORKFLOW_RUNS_DIR
from .figure_types import (
    SUPPORTED_FIGURE_TYPES_SET,
    SUPPORTED_FIGURE_TYPES_TEXT,
    SUPPORTED_OUTPUT_FORMATS_SET,
    SUPPORTED_OUTPUT_FORMATS_TEXT,
)

logger = logging.getLogger(__name__)

_SAFE_FILENAME_CHARS = re.compile(r"[^A-Za-z0-9._-]+")
_COLORBLIND_SAFE_PALETTE = (
    "#0072B2",
    "#D55E00",
    "#009E73",
    "#CC79A7",
    "#F0E442",
    "#56B4E9",
    "#E69F00",
    "#000000",
)


def _palette_color(index: int) -> str:
    return _COLORBLIND_SAFE_PALETTE[index % len(_COLORBLIND_SAFE_PALETTE)]


def _configure_cjk_fonts(matplotlib_module: Any) -> None:
    """Prepend CJK-capable fonts so Chinese titles/labels render as text.

    matplotlib's default DejaVu Sans has no CJK glyphs, so every Chinese
    character in a chart title, axis label, or legend renders as a tofu box.
    Missing font names in the list are skipped, so this is safe cross-platform:
    Windows resolves Microsoft JhengHei, Linux/macOS resolve a Noto/PingFang
    variant when installed, and everything else falls back to DejaVu Sans.
    """
    preferred = [
        "Microsoft JhengHei",
        "Microsoft YaHei",
        "PingFang TC",
        "Noto Sans CJK TC",
        "Noto Sans CJK SC",
        "SimHei",
        "DejaVu Sans",
    ]
    current = list(matplotlib_module.rcParams.get("font.sans-serif", []))
    matplotlib_module.rcParams["font.sans-serif"] = preferred + [
        name for name in current if name not in preferred
    ]
    # CJK fonts often lack U+2212; use ASCII hyphen for minus signs.
    matplotlib_module.rcParams["axes.unicode_minus"] = False

# ------------------------------------------------------------------
# Schema for figure_plan.json (what the agent must produce)
# ------------------------------------------------------------------
# {
#   "figures": [
#     {
#       "figure_id": "fig_1",
#       "figure_type": "bar" | "line" | "scatter" | "pie" | "table" |
#                      "histogram" | "boxplot" | "heatmap" |
#                      "error_bar" | "stacked_bar",
#       "title": "Chart Title",
#       "xlabel": "X Axis Label",     (optional)
#       "ylabel": "Y Axis Label",     (optional)
#       "data": {
#         "labels": ["A", "B", "C"],  (for bar/pie/line)
#         "series": [                  (for bar/line/scatter)
#           {"name": "Series 1", "values": [10, 20, 30]}
#         ],
#         "x": [1, 2, 3],             (for scatter - x values)
#         "y": [10, 20, 30],           (for scatter - y values)
#         "rows": [["A", 10], ...],   (for table)
#         "columns": ["Label", "Value"], (for table)
#         "values": [1, 2, 3],        (for histogram)
#         "bins": 8,                  (optional for histogram)
#         "x_labels": ["A", "B"],     (for heatmap)
#         "y_labels": ["R1", "R2"],   (for heatmap)
#         "values": [[1, 2], [3, 4]]  (for heatmap)
#       },
#       "output_format": "png" | "svg",  (default: png)
#       "width": 8,                       (optional, inches)
#       "height": 6,                     (optional, inches)
#       "dpi": 150,                      (optional)
#       "section_id": "results"          (which section this figure belongs to)
#     }
#   ]
# }

# ------------------------------------------------------------------
# matplotlib generation helpers
# ------------------------------------------------------------------

_MATPLOTLIB_AVAILABLE = None


def _as_number(value: Any, label: str) -> float:
    if value is None or value == "":
        raise ValueError(f"{label} contains an empty value")
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{label} contains non-numeric value {value!r}") from exc


def _number_list(values: Any, label: str) -> list[float]:
    if not isinstance(values, list) or not values:
        raise ValueError(f"{label} must be a non-empty list of numbers")
    return [_as_number(value, label) for value in values]


def _output_format(value: Any) -> str:
    output_format = str(value if value is not None else "png").strip().lower().lstrip(".")
    if not output_format:
        output_format = "png"
    if output_format not in SUPPORTED_OUTPUT_FORMATS_SET:
        raise ValueError(
            f"unsupported output_format {output_format!r}; "
            f"supported values: {SUPPORTED_OUTPUT_FORMATS_TEXT}"
        )
    return output_format


def _safe_figure_file_stem(figure_id: Any, fallback: str) -> str:
    text = str(figure_id if figure_id is not None else fallback).strip() or fallback
    safe = _SAFE_FILENAME_CHARS.sub("_", text).strip("._")
    return safe or fallback


def _series_items(data: dict, label: str = "data.series") -> list[dict]:
    series = data.get("series", [])
    if not isinstance(series, list) or not series:
        raise ValueError(f"{label} must be a non-empty list")
    items = [item for item in series if isinstance(item, dict)]
    if len(items) != len(series):
        raise ValueError(f"{label} entries must be objects")
    return items


def _labels_for_count(data: dict, count: int, label: str = "data.labels") -> list[str]:
    labels = data.get("labels", [])
    if labels:
        if not isinstance(labels, list):
            raise ValueError(f"{label} must be a list")
        if len(labels) != count:
            raise ValueError(f"{label} length must match plotted value count")
        return [str(item) for item in labels]
    return [str(index + 1) for index in range(count)]


def _check_matplotlib() -> bool:
    global _MATPLOTLIB_AVAILABLE
    if _MATPLOTLIB_AVAILABLE is None:
        try:
            import matplotlib
            matplotlib.use("Agg")  # non-interactive backend
            _configure_cjk_fonts(matplotlib)  # rcParams persist process-wide
            _MATPLOTLIB_AVAILABLE = True
        except Exception:
            _MATPLOTLIB_AVAILABLE = False
    return _MATPLOTLIB_AVAILABLE


def _bbox_overlap(a: Any, b: Any) -> bool:
    return bool(a and b and a.overlaps(b))


def _text_bboxes(texts: list[Any], renderer: Any) -> list[Any]:
    bboxes = []
    for text in texts:
        if not text.get_visible() or not str(text.get_text()).strip():
            continue
        try:
            bbox = text.get_window_extent(renderer=renderer)
        except Exception:
            continue
        if bbox.width > 0 and bbox.height > 0:
            bboxes.append(bbox)
    return bboxes


def _visual_issue(issue_type: str, figure_id: str, detail: str, repair_hint: str, **extra: Any) -> dict:
    issue = {
        "severity": "review",
        "type": issue_type,
        "figure_id": figure_id,
        "detail": detail,
        "repair_hint": repair_hint,
    }
    issue.update(extra)
    return issue


def _overlapping_text_issue(axis: str, bboxes: list[Any], figure_id: str) -> dict | None:
    for left_index, left in enumerate(bboxes):
        for right in bboxes[left_index + 1:]:
            if _bbox_overlap(left, right):
                return _visual_issue(
                    "tick_label_overlap",
                    figure_id,
                    f"{axis}-axis tick labels overlap in the rendered chart.",
                    "Increase figure size, rotate or shorten labels, reduce categories, or use a table.",
                    axis=axis,
                )
    return None


def _dense_heatmap_issue(fig: Any, ax: Any, figure_id: str, data: dict) -> dict | None:
    values = data.get("values", [])
    if not isinstance(values, list) or not values:
        return None
    row_count = len(values)
    column_count = max((len(row) for row in values if isinstance(row, list)), default=0)
    if row_count == 0 or column_count == 0:
        return None
    axis_box = ax.get_window_extent()
    cell_width = axis_box.width / max(column_count, 1)
    cell_height = axis_box.height / max(row_count, 1)
    if row_count * column_count <= 100 and cell_width >= 12 and cell_height >= 10:
        return None
    return _visual_issue(
        "dense_heatmap",
        figure_id,
        (
            f"Heatmap has {row_count} rows and {column_count} columns at about "
            f"{cell_width:.1f}x{cell_height:.1f} pixels per cell."
        ),
        "Split the heatmap, aggregate rows/columns, use top-N, or keep exact values in a table.",
        row_count=row_count,
        column_count=column_count,
        cell_width_px=round(cell_width, 1),
        cell_height_px=round(cell_height, 1),
    )


def _figure_visual_quality_issues(fig: Any, ax: Any, figure_id: str, figure_type: str, data: dict) -> list[dict]:
    try:
        fig.canvas.draw()
        renderer = fig.canvas.get_renderer()
    except Exception as exc:
        return [_visual_issue(
            "visual_quality_check_failed",
            figure_id,
            "Visual quality checks could not inspect the rendered figure canvas.",
            "Review the generated chart manually and investigate the matplotlib canvas/rendering error.",
            error_type=type(exc).__name__,
            error_message=str(exc),
        )]

    issues: list[dict] = []
    x_issue = _overlapping_text_issue("x", _text_bboxes(ax.get_xticklabels(), renderer), figure_id)
    if x_issue:
        issues.append(x_issue)
    y_issue = _overlapping_text_issue("y", _text_bboxes(ax.get_yticklabels(), renderer), figure_id)
    if y_issue:
        issues.append(y_issue)

    legend = ax.get_legend()
    if legend is not None:
        try:
            if _bbox_overlap(legend.get_window_extent(renderer=renderer), ax.get_window_extent(renderer=renderer)):
                issues.append(_visual_issue(
                    "legend_overlaps_plot_area",
                    figure_id,
                    "Legend overlaps the plotted data area.",
                    "Move the legend outside the axes, shorten legend labels, or split the chart.",
                ))
        except Exception:
            pass

    fig_box = fig.bbox
    text_artists = [ax.title, ax.xaxis.label, ax.yaxis.label]
    for bbox in _text_bboxes(text_artists, renderer):
        if bbox.x0 < fig_box.x0 or bbox.y0 < fig_box.y0 or bbox.x1 > fig_box.x1 or bbox.y1 > fig_box.y1:
            issues.append(_visual_issue(
                "axis_text_clipped",
                figure_id,
                "Title or axis label extends outside the figure bounds.",
                "Increase figure size or shorten the title/axis label.",
            ))
            break

    if figure_type == "heatmap":
        issue = _dense_heatmap_issue(fig, ax, figure_id, data)
        if issue:
            issues.append(issue)
    return issues


def _legend_outside(ax: Any) -> None:
    ax.legend(loc="center left", bbox_to_anchor=(1.02, 0.5), borderaxespad=0.0)


def _save_figure(fig: Any, ax: Any, figure_id: str, figure_type: str, data: dict, output_path: Path, dpi: int) -> list[dict]:
    try:
        fig.tight_layout()
    except Exception:
        pass
    issues = _figure_visual_quality_issues(fig, ax, figure_id, figure_type, data)
    fig.savefig(output_path, dpi=dpi, bbox_inches="tight")
    return issues


def _generate_bar(figure_id: str, title: str, data: dict, xlabel: str, ylabel: str,
                  width: float, height: float, dpi: int, output_path: Path) -> list[dict]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = data.get("labels", [])
    series = data.get("series", [])

    fig, ax = plt.subplots(figsize=(width, height), dpi=dpi)
    x = range(len(labels))
    bar_width = 0.6 / max(len(series), 1)

    for i, s in enumerate(series):
        values = s.get("values", [])
        offset = (i - len(series) / 2 + 0.5) * bar_width
        ax.bar(
            [xi + offset for xi in x],
            values,
            bar_width * 0.9,
            label=s.get("name", f"Series {i}"),
            color=_palette_color(i),
        )

    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    if labels:
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
    if len(series) > 1:
        _legend_outside(ax)
    ax.grid(axis="y", alpha=0.3)
    issues = _save_figure(fig, ax, figure_id, "bar", data, output_path, dpi)
    plt.close(fig)
    return issues


def _generate_line(figure_id: str, title: str, data: dict, xlabel: str, ylabel: str,
                   width: float, height: float, dpi: int, output_path: Path) -> list[dict]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = data.get("labels", [])
    series = data.get("series", [])

    fig, ax = plt.subplots(figsize=(width, height), dpi=dpi)

    for i, s in enumerate(series):
        values = s.get("values", [])
        x_vals = range(len(labels)) if labels else range(len(values))
        ax.plot(
            x_vals,
            values,
            marker="o",
            linewidth=2,
            label=s.get("name", f"Series {i}"),
            color=_palette_color(i),
        )

    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    if labels and len(labels) == len(range(len(labels))):
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels)
    if len(series) > 1:
        _legend_outside(ax)
    ax.grid(alpha=0.3)
    issues = _save_figure(fig, ax, figure_id, "line", data, output_path, dpi)
    plt.close(fig)
    return issues


def _generate_scatter(figure_id: str, title: str, data: dict, xlabel: str, ylabel: str,
                      width: float, height: float, dpi: int, output_path: Path) -> list[dict]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    x_vals = data.get("x", [])
    y_vals = data.get("y", [])

    fig, ax = plt.subplots(figsize=(width, height), dpi=dpi)
    ax.scatter(x_vals, y_vals, alpha=0.75, edgecolors="none", color=_palette_color(0))

    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(alpha=0.3)
    issues = _save_figure(fig, ax, figure_id, "scatter", data, output_path, dpi)
    plt.close(fig)
    return issues


def _generate_pie(figure_id: str, title: str, data: dict,
                  width: float, height: float, dpi: int, output_path: Path) -> list[dict]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = data.get("labels", [])
    series = data.get("series", [])
    values = series[0].get("values", []) if series else []

    fig, ax = plt.subplots(figsize=(width, height), dpi=dpi)
    ax.pie(
        values,
        labels=labels,
        autopct="%1.1f%%",
        startangle=140,
        colors=[_palette_color(index) for index, _ in enumerate(values)],
    )
    ax.set_title(title)
    issues = _save_figure(fig, ax, figure_id, "pie", data, output_path, dpi)
    plt.close(fig)
    return issues


def _generate_table(figure_id: str, title: str, data: dict,
                   width: float, height: float, dpi: int, output_path: Path) -> list[dict]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import matplotlib.table

    rows = data.get("rows", [])
    columns = data.get("columns", [])

    fig, ax = plt.subplots(figsize=(width, height), dpi=dpi)
    ax.axis("off")

    table = matplotlib.table.table(
        ax, cellText=rows, colLabels=columns,
        loc="center", cellLoc="center"
    )
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1.2, 1.8)
    ax.set_title(title, pad=20)
    issues = _save_figure(fig, ax, figure_id, "table", data, output_path, dpi)
    plt.close(fig)
    return issues


def _generate_histogram(figure_id: str, title: str, data: dict, xlabel: str, ylabel: str,
                        width: float, height: float, dpi: int, output_path: Path) -> list[dict]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    values = _number_list(data.get("values", []), "data.values")
    bins_raw = data.get("bins", min(10, max(5, round(len(values) ** 0.5))))
    try:
        bins = max(1, int(bins_raw))
    except (TypeError, ValueError):
        bins = min(10, max(5, round(len(values) ** 0.5)))

    fig, ax = plt.subplots(figsize=(width, height), dpi=dpi)
    ax.hist(values, bins=bins, edgecolor="white", color=_palette_color(0))
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel or "Frequency")
    ax.set_title(title)
    ax.grid(axis="y", alpha=0.3)
    issues = _save_figure(fig, ax, figure_id, "histogram", data, output_path, dpi)
    plt.close(fig)
    return issues


def _generate_boxplot(figure_id: str, title: str, data: dict, xlabel: str, ylabel: str,
                      width: float, height: float, dpi: int, output_path: Path) -> list[dict]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    series = _series_items(data)
    values = [_number_list(item.get("values", []), f"data.series[{index}].values") for index, item in enumerate(series)]
    labels = [str(item.get("name") or f"Series {index + 1}") for index, item in enumerate(series)]

    fig, ax = plt.subplots(figsize=(width, height), dpi=dpi)
    try:
        box = ax.boxplot(values, tick_labels=labels, patch_artist=True)
    except TypeError:
        box = ax.boxplot(values, labels=labels, patch_artist=True)
    for index, patch in enumerate(box.get("boxes", [])):
        patch.set_facecolor(_palette_color(index))
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(axis="y", alpha=0.3)
    issues = _save_figure(fig, ax, figure_id, "boxplot", data, output_path, dpi)
    plt.close(fig)
    return issues


def _generate_heatmap(figure_id: str, title: str, data: dict, xlabel: str, ylabel: str,
                      width: float, height: float, dpi: int, output_path: Path) -> list[dict]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    raw_values = data.get("values", [])
    if not isinstance(raw_values, list) or not raw_values:
        raise ValueError("data.values must be a non-empty 2D list")
    matrix = [_number_list(row, f"data.values[{index}]") for index, row in enumerate(raw_values)]
    width_count = len(matrix[0])
    if any(len(row) != width_count for row in matrix):
        raise ValueError("data.values rows must have equal length")

    x_labels = data.get("x_labels", [])
    y_labels = data.get("y_labels", [])
    if x_labels and (not isinstance(x_labels, list) or len(x_labels) != width_count):
        raise ValueError("data.x_labels length must match heatmap column count")
    if y_labels and (not isinstance(y_labels, list) or len(y_labels) != len(matrix)):
        raise ValueError("data.y_labels length must match heatmap row count")

    fig, ax = plt.subplots(figsize=(width, height), dpi=dpi)
    image = ax.imshow(matrix, aspect="auto", cmap="cividis")
    fig.colorbar(image, ax=ax, label=str(data.get("colorbar_label") or ""))
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    if x_labels:
        ax.set_xticks(range(width_count))
        ax.set_xticklabels([str(item) for item in x_labels])
    if y_labels:
        ax.set_yticks(range(len(matrix)))
        ax.set_yticklabels([str(item) for item in y_labels])
    issues = _save_figure(fig, ax, figure_id, "heatmap", data, output_path, dpi)
    plt.close(fig)
    return issues


def _generate_error_bar(figure_id: str, title: str, data: dict, xlabel: str, ylabel: str,
                        width: float, height: float, dpi: int, output_path: Path) -> list[dict]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    series = _series_items(data)
    first_values = _number_list(series[0].get("values", []), "data.series[0].values")
    labels = _labels_for_count(data, len(first_values))
    x = list(range(len(labels)))

    fig, ax = plt.subplots(figsize=(width, height), dpi=dpi)
    offset_step = 0.12 if len(series) > 1 else 0
    for index, item in enumerate(series):
        values = _number_list(item.get("values", []), f"data.series[{index}].values")
        errors = _number_list(item.get("errors", []), f"data.series[{index}].errors")
        if len(values) != len(labels) or len(errors) != len(labels):
            raise ValueError("error_bar values, errors, and labels must have matching lengths")
        offset = (index - (len(series) - 1) / 2) * offset_step
        ax.errorbar(
            [position + offset for position in x],
            values,
            yerr=errors,
            fmt="o-",
            capsize=4,
            linewidth=1.8,
            label=item.get("name", f"Series {index + 1}"),
            color=_palette_color(index),
        )

    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    if len(series) > 1:
        _legend_outside(ax)
    ax.grid(axis="y", alpha=0.3)
    issues = _save_figure(fig, ax, figure_id, "error_bar", data, output_path, dpi)
    plt.close(fig)
    return issues


def _generate_stacked_bar(figure_id: str, title: str, data: dict, xlabel: str, ylabel: str,
                          width: float, height: float, dpi: int, output_path: Path) -> list[dict]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    series = _series_items(data)
    first_values = _number_list(series[0].get("values", []), "data.series[0].values")
    labels = _labels_for_count(data, len(first_values))
    x = list(range(len(labels)))
    bottom = [0.0 for _ in labels]

    fig, ax = plt.subplots(figsize=(width, height), dpi=dpi)
    for index, item in enumerate(series):
        values = _number_list(item.get("values", []), f"data.series[{index}].values")
        if len(values) != len(labels):
            raise ValueError("stacked_bar series values and labels must have matching lengths")
        ax.bar(
            x,
            values,
            bottom=bottom,
            label=item.get("name", f"Series {index + 1}"),
            color=_palette_color(index),
        )
        bottom = [base + value for base, value in zip(bottom, values)]

    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    if len(series) > 1:
        _legend_outside(ax)
    ax.grid(axis="y", alpha=0.3)
    issues = _save_figure(fig, ax, figure_id, "stacked_bar", data, output_path, dpi)
    plt.close(fig)
    return issues


# ------------------------------------------------------------------
# Main node
# ------------------------------------------------------------------

def run_figure_build(state: ReportState) -> ReportState:
    """T14: FIGURE_BUILD - generate figures from agent-authored figure_plan.json.

    Reads: figure_plan.json (written by agent alongside section_drafts)
    Writes: figures/<job_id>/*.png|svg + figure_manifest.json
    Soft skip: if matplotlib not available or figure_plan.json not found.
    """
    if not _check_matplotlib():
        logger.warning(
            "[FIGURE_BUILD] matplotlib not available; skipping figure generation. "
            "Install with: pip install matplotlib Pillow"
        )
        state.output["figure_manifest_path"] = ""
        return state

    # Locate figure_plan.json — agent writes it alongside section_drafts
    run_dir = WORKFLOW_RUNS_DIR / state.job_id
    section_drafts_dir = run_dir / "section_drafts"
    figure_plan_path = section_drafts_dir / "figure_plan.json"

    if not figure_plan_path.exists():
        logger.info("[FIGURE_BUILD] No figure_plan.json found; skipping.")
        state.output["figure_manifest_path"] = ""
        return state

    try:
        with open(figure_plan_path, encoding="utf-8") as f:
            plan = json.load(f)
    except Exception as exc:
        logger.warning(f"[FIGURE_BUILD] Failed to parse figure_plan.json: {exc}; skipping.")
        state.output["figure_manifest_path"] = ""
        return state

    figures: list[dict] = plan.get("figures", [])
    if not figures:
        logger.info("[FIGURE_BUILD] figure_plan has no figures; skipping.")
        state.output["figure_manifest_path"] = ""
        return state

    # Output directory
    figures_dir = run_dir / "figures"
    figures_dir.mkdir(parents=True, exist_ok=True)

    manifest_entries: list[dict] = []
    errors: list[str] = []
    visual_figure_reports: list[dict] = []
    visual_issues: list[dict] = []

    for fig in figures:
        figure_id = str(fig.get("figure_id") or f"fig_{len(manifest_entries) + 1}").strip()
        figure_type = str(fig.get("figure_type", "bar")).strip().lower()
        title = fig.get("title", figure_id)
        xlabel = fig.get("xlabel", "")
        ylabel = fig.get("ylabel", "")
        data = fig.get("data", {})
        width = float(fig.get("width", 8))
        height = float(fig.get("height", 6))
        dpi = int(fig.get("dpi", 150))
        section_id = fig.get("section_id", "")

        try:
            output_format = _output_format(fig.get("output_format", "png"))
            safe_id = _safe_figure_file_stem(figure_id, f"fig_{len(manifest_entries) + 1}")
            output_path = figures_dir / f"{safe_id}.{output_format}"
            figure_visual_issues: list[dict] = []
            if figure_type not in SUPPORTED_FIGURE_TYPES_SET:
                errors.append(
                    f"{figure_id}: unknown figure_type '{figure_type}'. "
                    f"Supported values: {SUPPORTED_FIGURE_TYPES_TEXT}"
                )
                continue
            if figure_type == "bar":
                figure_visual_issues = _generate_bar(figure_id, title, data, xlabel, ylabel, width, height, dpi, output_path)
            elif figure_type == "line":
                figure_visual_issues = _generate_line(figure_id, title, data, xlabel, ylabel, width, height, dpi, output_path)
            elif figure_type == "scatter":
                figure_visual_issues = _generate_scatter(figure_id, title, data, xlabel, ylabel, width, height, dpi, output_path)
            elif figure_type == "pie":
                figure_visual_issues = _generate_pie(figure_id, title, data, width, height, dpi, output_path)
            elif figure_type == "table":
                columns = data.get("columns") or []
                rows = data.get("rows") or []
                if columns and rows:
                    # Native Word table: no PNG. DOCX_RENDER turns this entry
                    # into a markdown pipe table, so the document gets a real,
                    # selectable table that follows the reference template's
                    # table style — a rasterized table does neither.
                    manifest_entries.append({
                        "figure_id": figure_id,
                        "figure_type": figure_type,
                        "title": title,
                        "path": "",
                        "render_mode": "native_table",
                        "format": "docx_table",
                        "section_id": section_id,
                        "data": {"columns": columns, "rows": rows},
                        "visual_quality_status": "passed",
                        "visual_quality_issue_count": 0,
                    })
                    visual_figure_reports.append({
                        "figure_id": figure_id,
                        "figure_type": figure_type,
                        "path": "",
                        "status": "passed",
                        "issue_count": 0,
                        "issues": [],
                    })
                    logger.info(f"[FIGURE_BUILD] {figure_id}: native docx table ({len(rows)} rows)")
                    continue
                figure_visual_issues = _generate_table(figure_id, title, data, width, height, dpi, output_path)
            elif figure_type == "histogram":
                figure_visual_issues = _generate_histogram(figure_id, title, data, xlabel, ylabel, width, height, dpi, output_path)
            elif figure_type == "boxplot":
                figure_visual_issues = _generate_boxplot(figure_id, title, data, xlabel, ylabel, width, height, dpi, output_path)
            elif figure_type == "heatmap":
                figure_visual_issues = _generate_heatmap(figure_id, title, data, xlabel, ylabel, width, height, dpi, output_path)
            elif figure_type == "error_bar":
                figure_visual_issues = _generate_error_bar(figure_id, title, data, xlabel, ylabel, width, height, dpi, output_path)
            elif figure_type == "stacked_bar":
                figure_visual_issues = _generate_stacked_bar(figure_id, title, data, xlabel, ylabel, width, height, dpi, output_path)

            visual_status = "review" if figure_visual_issues else "passed"
            manifest_entries.append({
                "figure_id": figure_id,
                "figure_type": figure_type,
                "title": title,
                "path": str(output_path),
                "format": output_format,
                "section_id": section_id,
                "visual_quality_status": visual_status,
                "visual_quality_issue_count": len(figure_visual_issues),
            })
            visual_figure_reports.append({
                "figure_id": figure_id,
                "figure_type": figure_type,
                "path": str(output_path),
                "status": visual_status,
                "issue_count": len(figure_visual_issues),
                "issues": figure_visual_issues,
            })
            visual_issues.extend(figure_visual_issues)
            logger.info(f"[FIGURE_BUILD] Generated {output_path}")

        except Exception as exc:
            errors.append(f"{figure_id}: {exc}")
            logger.warning(f"[FIGURE_BUILD] Failed to generate {figure_id}: {exc}")

    # Write manifest
    manifest = {
        "job_id": state.job_id,
        "generated_count": len(manifest_entries),
        "error_count": len(errors),
        "errors": errors,
        "figures": manifest_entries,
    }
    manifest_path = run_dir / "figure_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, default=str)

    state.output["figure_manifest_path"] = str(manifest_path)
    visual_report = {
        "job_id": state.job_id,
        "status": "review" if visual_issues else "passed",
        "generated_count": len(manifest_entries),
        "issue_count": len(visual_issues),
        "issues": visual_issues,
        "figures": visual_figure_reports,
    }
    visual_report_path = run_dir / "figure_visual_quality_report.json"
    with open(visual_report_path, "w", encoding="utf-8") as f:
        json.dump(visual_report, f, indent=2, default=str)
    state.qa["figure_visual_quality_report_path"] = str(visual_report_path)
    state.output["figure_visual_quality_report_path"] = str(visual_report_path)
    logger.info(f"[FIGURE_BUILD] Manifest written to {manifest_path} ({len(manifest_entries)} figures)")

    return state
