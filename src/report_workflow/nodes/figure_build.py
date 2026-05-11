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
            _MATPLOTLIB_AVAILABLE = True
        except Exception:
            _MATPLOTLIB_AVAILABLE = False
    return _MATPLOTLIB_AVAILABLE


def _generate_bar(figure_id: str, title: str, data: dict, xlabel: str, ylabel: str,
                  width: float, height: float, dpi: int, output_path: Path) -> None:
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
        ax.bar([xi + offset for xi in x], values, bar_width * 0.9, label=s.get("name", f"Series {i}"))

    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    if labels:
        ax.set_xticks(x)
        ax.set_xticklabels(labels)
    if len(series) > 1:
        ax.legend()
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)


def _generate_line(figure_id: str, title: str, data: dict, xlabel: str, ylabel: str,
                   width: float, height: float, dpi: int, output_path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = data.get("labels", [])
    series = data.get("series", [])

    fig, ax = plt.subplots(figsize=(width, height), dpi=dpi)

    for i, s in enumerate(series):
        values = s.get("values", [])
        x_vals = range(len(labels)) if labels else range(len(values))
        ax.plot(x_vals, values, marker="o", linewidth=2, label=s.get("name", f"Series {i}"))

    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    if labels and len(labels) == len(range(len(labels))):
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels)
    if series:
        ax.legend()
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)


def _generate_scatter(figure_id: str, title: str, data: dict, xlabel: str, ylabel: str,
                      width: float, height: float, dpi: int, output_path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    x_vals = data.get("x", [])
    y_vals = data.get("y", [])

    fig, ax = plt.subplots(figsize=(width, height), dpi=dpi)
    ax.scatter(x_vals, y_vals, alpha=0.7, edgecolors="none")

    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)


def _generate_pie(figure_id: str, title: str, data: dict,
                  width: float, height: float, dpi: int, output_path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    labels = data.get("labels", [])
    series = data.get("series", [])
    values = series[0].get("values", []) if series else []

    fig, ax = plt.subplots(figsize=(width, height), dpi=dpi)
    ax.pie(values, labels=labels, autopct="%1.1f%%", startangle=140)
    ax.set_title(title)
    fig.tight_layout()
    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)


def _generate_table(figure_id: str, title: str, data: dict,
                   width: float, height: float, dpi: int, output_path: Path) -> None:
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
    fig.tight_layout()
    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)


def _generate_histogram(figure_id: str, title: str, data: dict, xlabel: str, ylabel: str,
                        width: float, height: float, dpi: int, output_path: Path) -> None:
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
    ax.hist(values, bins=bins, edgecolor="white", color="#4C78A8")
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel or "Frequency")
    ax.set_title(title)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)


def _generate_boxplot(figure_id: str, title: str, data: dict, xlabel: str, ylabel: str,
                      width: float, height: float, dpi: int, output_path: Path) -> None:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    series = _series_items(data)
    values = [_number_list(item.get("values", []), f"data.series[{index}].values") for index, item in enumerate(series)]
    labels = [str(item.get("name") or f"Series {index + 1}") for index, item in enumerate(series)]

    fig, ax = plt.subplots(figsize=(width, height), dpi=dpi)
    try:
        ax.boxplot(values, tick_labels=labels, patch_artist=True)
    except TypeError:
        ax.boxplot(values, labels=labels, patch_artist=True)
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)


def _generate_heatmap(figure_id: str, title: str, data: dict, xlabel: str, ylabel: str,
                      width: float, height: float, dpi: int, output_path: Path) -> None:
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
    image = ax.imshow(matrix, aspect="auto", cmap="viridis")
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
    fig.tight_layout()
    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)


def _generate_error_bar(figure_id: str, title: str, data: dict, xlabel: str, ylabel: str,
                        width: float, height: float, dpi: int, output_path: Path) -> None:
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
        )

    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    if len(series) > 1:
        ax.legend()
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)


def _generate_stacked_bar(figure_id: str, title: str, data: dict, xlabel: str, ylabel: str,
                          width: float, height: float, dpi: int, output_path: Path) -> None:
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
        ax.bar(x, values, bottom=bottom, label=item.get("name", f"Series {index + 1}"))
        bottom = [base + value for base, value in zip(bottom, values)]

    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.set_title(title)
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    if len(series) > 1:
        ax.legend()
    ax.grid(axis="y", alpha=0.3)
    fig.tight_layout()
    fig.savefig(output_path, dpi=dpi)
    plt.close(fig)


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
            if figure_type not in SUPPORTED_FIGURE_TYPES_SET:
                errors.append(
                    f"{figure_id}: unknown figure_type '{figure_type}'. "
                    f"Supported values: {SUPPORTED_FIGURE_TYPES_TEXT}"
                )
                continue
            if figure_type == "bar":
                _generate_bar(figure_id, title, data, xlabel, ylabel, width, height, dpi, output_path)
            elif figure_type == "line":
                _generate_line(figure_id, title, data, xlabel, ylabel, width, height, dpi, output_path)
            elif figure_type == "scatter":
                _generate_scatter(figure_id, title, data, xlabel, ylabel, width, height, dpi, output_path)
            elif figure_type == "pie":
                _generate_pie(figure_id, title, data, width, height, dpi, output_path)
            elif figure_type == "table":
                _generate_table(figure_id, title, data, width, height, dpi, output_path)
            elif figure_type == "histogram":
                _generate_histogram(figure_id, title, data, xlabel, ylabel, width, height, dpi, output_path)
            elif figure_type == "boxplot":
                _generate_boxplot(figure_id, title, data, xlabel, ylabel, width, height, dpi, output_path)
            elif figure_type == "heatmap":
                _generate_heatmap(figure_id, title, data, xlabel, ylabel, width, height, dpi, output_path)
            elif figure_type == "error_bar":
                _generate_error_bar(figure_id, title, data, xlabel, ylabel, width, height, dpi, output_path)
            elif figure_type == "stacked_bar":
                _generate_stacked_bar(figure_id, title, data, xlabel, ylabel, width, height, dpi, output_path)

            manifest_entries.append({
                "figure_id": figure_id,
                "figure_type": figure_type,
                "title": title,
                "path": str(output_path),
                "format": output_format,
                "section_id": section_id,
            })
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
    logger.info(f"[FIGURE_BUILD] Manifest written to {manifest_path} ({len(manifest_entries)} figures)")

    return state
