"""FIGURE_BUILD node - generate figures from agent-authored figure_plan.json.

Sits between SECTION_DRAFT and REVISION_APPLY / MERGE_DRAFT in the validate phase.
The agent produces figure_plan.json (spec + data); this node executes matplotlib
to render the actual figure files.

Output: figures/<job_id>/ directory + figure_manifest.json
"""
import json
import logging
from pathlib import Path

from ..state import ReportState, WORKFLOW_RUNS_DIR

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Schema for figure_plan.json (what the agent must produce)
# ------------------------------------------------------------------
# {
#   "figures": [
#     {
#       "figure_id": "fig_1",
#       "figure_type": "bar" | "line" | "scatter" | "pie" | "table",
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
#         "columns": ["Label", "Value"] (for table)
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
        figure_id = fig.get("figure_id", f"fig_{len(manifest_entries) + 1}")
        figure_type = fig.get("figure_type", "bar")
        title = fig.get("title", figure_id)
        xlabel = fig.get("xlabel", "")
        ylabel = fig.get("ylabel", "")
        data = fig.get("data", {})
        output_format = fig.get("output_format", "png").lower()
        width = float(fig.get("width", 8))
        height = float(fig.get("height", 6))
        dpi = int(fig.get("dpi", 150))
        section_id = fig.get("section_id", "")

        # Sanitise filename
        safe_id = figure_id.replace(" ", "_").replace("/", "_")
        output_path = figures_dir / f"{safe_id}.{output_format}"

        try:
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
            else:
                errors.append(f"{figure_id}: unknown figure_type '{figure_type}'")
                continue

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
