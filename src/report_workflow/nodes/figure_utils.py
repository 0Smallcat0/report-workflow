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
    normalized = re.sub(r"[^a-z0-9%/]+", " ", normalized).strip()
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
    return ""
