"""Shared helpers for deterministic figure recommendation and audit nodes."""
from __future__ import annotations

import re
from typing import Any


UNIT_TERMS = {
    "%",
    "percent",
    "percentage",
    "ratio",
    "score",
    "count",
    "number",
    "v",
    "volt",
    "voltage",
    "a",
    "amp",
    "current",
    "w",
    "kw",
    "pa",
    "kpa",
    "bar",
    "c",
    "degc",
    "kg",
    "g",
    "m",
    "cm",
    "mm",
    "s",
    "sec",
    "min",
    "h",
    "hr",
}


def clean_text(value: Any) -> str:
    return " ".join(str(value if value is not None else "").strip().split())


def to_float(value: Any) -> float | None:
    text = clean_text(value)
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


def unit_signature(text: Any) -> str:
    normalized = clean_text(text).casefold()
    if not normalized:
        return ""
    paren_matches = re.findall(r"\(([^)]+)\)", normalized)
    explicit_parenthetical = bool(paren_matches)
    if paren_matches:
        normalized = paren_matches[-1]
    elif "%" in normalized:
        return "%"
    normalized = normalized.replace("\u00b0", "deg")
    # CJK unit words are units too: stripping every non-ASCII character made
    # "\u63a1\u8cfc\u6210\u672c(\u5143)" indistinguishable from a column carrying no unit at all.
    normalized = re.sub(r"[^a-z0-9%/\u4e00-\u9fff]+", " ", normalized).strip()
    if not normalized:
        return ""
    aliases = {
        "amps": "a",
        "ampere": "a",
        "amperes": "a",
        "current": "a",
        "volts": "v",
        "volt": "v",
        "voltage": "v",
        "percentage": "%",
        "percent": "%",
        "share": "%",
        "celsius": "degc",
        "temperature": "degc",
        "seconds": "s",
        "second": "s",
        "minutes": "min",
        "minute": "min",
        "hours": "h",
        "hour": "h",
        "counts": "count",
        "responses": "count",
    }
    tokens = normalized.split()
    symbol_units = {"v", "a", "w", "kw", "pa", "kpa", "c", "kg", "g", "m", "cm", "mm", "s", "h"}
    for token in tokens:
        token = aliases.get(token, token)
        if token in symbol_units and not explicit_parenthetical:
            continue
        if token in UNIT_TERMS:
            return token
    # A unit the vocabulary does not know is still a unit. "(kS/s)", "(bit)"
    # and "(元)" all fell through to "" — indistinguishable from a column with
    # no unit — so a sampling rate and a price read as the same unit and were
    # drawn on one shared y-axis. Comparing signatures only needs them to
    # differ, not to be recognized. Purely numeric parentheticals are skipped
    # so a "Revenue (2026)" style column is not mistaken for a unit.
    if explicit_parenthetical and tokens and not normalized.isdigit():
        return normalized
    return ""
