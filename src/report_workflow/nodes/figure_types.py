"""Shared figure type contract for recommendation, audit, and rendering."""
from __future__ import annotations


SUPPORTED_FIGURE_TYPES = (
    "bar",
    "line",
    "scatter",
    "pie",
    "table",
    "histogram",
    "boxplot",
    "heatmap",
    "error_bar",
    "stacked_bar",
)

SUPPORTED_FIGURE_TYPES_SET = set(SUPPORTED_FIGURE_TYPES)
SUPPORTED_FIGURE_TYPES_TEXT = " | ".join(SUPPORTED_FIGURE_TYPES)

SUPPORTED_OUTPUT_FORMATS = ("png", "svg")
SUPPORTED_OUTPUT_FORMATS_SET = set(SUPPORTED_OUTPUT_FORMATS)
SUPPORTED_OUTPUT_FORMATS_TEXT = " | ".join(SUPPORTED_OUTPUT_FORMATS)
