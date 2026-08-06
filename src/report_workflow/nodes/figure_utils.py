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


#: Decorations a real report puts around a number. A price table writes
#: "~80,000–85,000", a market figure arrives as "**US$ 12.4bn**", a footnote
#: rides along as "<sup>2</sup>". Every one of those made the cell unparseable,
#: and a column of unparseable cells is reported as "no reliable numeric
#: measure column" — so a textbook time series was recommended as a table.
#: Footnote markers are dropped with their content. Stripping only the tags
#: glued the marker onto the figure: "12.5<sup>2</sup>" parsed as 12.52, a
#: wrong number reported with full confidence, which is worse than no number.
_FOOTNOTE_RE = re.compile(r"<(sup|sub)\b[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_MARKUP_RE = re.compile(r"<[^>]+>|\*\*|__|`")
#: "2022-11" is a month; "80,000-85,000" is a span. A hyphen alone cannot tell
#: them apart, so a date-shaped cell is never read as a range.
_DATE_LIKE_RE = re.compile(r"^\d{1,4}\s*-\s*\d{1,2}(\s*-\s*\d{1,2})?$")
_APPROX_RE = re.compile(r"^(?:[~≈∼～]|about|approx\.?|approximately|約|约|大約|大约|近)\s*", re.IGNORECASE)
_CURRENCY_RE = re.compile(r"(?:us|nt|hk|rmb|cn)?\s*[$€£¥₩﷼]|\busd\b|\btwd\b|\bcny\b|\brmb\b|元|美元|新臺幣|新台币", re.IGNORECASE)
#: Only the ratio marks. Magnitude suffixes (bn, k, 萬) are deliberately not
#: stripped: dropping the suffix would read "12.4bn" as 12.4, which is not a
#: tolerant parse but a wrong one. An unrecognised cell is reported as
#: unparsed, and that is the honest outcome.
_TRAILING_UNIT_RE = re.compile(r"[%‰]")
#: Range separators. The ASCII hyphen is deliberately absent: "2022-11" is a
#: month, not a span from 2022 to 11, and reading it as one would invent data.
#: It is admitted below only under a narrower test.
_RANGE_SEP_RE = re.compile(r"\s*(?:–|—|~|∼|～|\bto\b|至)\s*", re.IGNORECASE)
_HYPHEN_RE = re.compile(r"(?<=[\d%\s])\s*-\s*(?=[\d\s])")
_NUMBER_RE = re.compile(r"^[-+]?\d+(?:\.\d+)?$")

#: A stated tolerance: "5 ± 0.3", "±5%". A measured value written with its
#: uncertainty is the most credible kind of number a report carries, and it
#: was the one shape the parser refused — so an engineering table of readings
#: read as having no numeric column at all.
_TOLERANCE_RE = re.compile(r"^(?P<value>[^±]*?)\s*±\s*(?P<tolerance>.+)$")

#: A unit written after the number: "417/噸", "USD/t", "kg". Stripped for
#: parsing and reported back, so a caption can say what the axis is in. The
#: number keeps its magnitude — nothing here multiplies or converts, because a
#: parser that silently rescales is worse than one that gives up.
_TRAILING_UNIT_TEXT_RE = re.compile(
    r"\s*/?\s*(?:[A-Za-z%°µμ一-鿿][A-Za-z0-9%°/µμ一-鿿.]*)$"
)

#: Suffixes that scale the number rather than name what it measures. These are
#: refused, not stripped: reading "12.4bn" as 12.4 is a wrong number published
#: with full confidence, which is worse than reporting the cell as unreadable.
#: "m" is here for the same reason — million and metre are both plausible and
#: guessing between them is how a chart comes out a millionfold wrong.
_MAGNITUDE_SUFFIXES = frozenset({
    "b", "bn", "bil", "billion", "m", "mn", "mil", "million",
    "k", "thousand", "t", "tn", "trillion",
    "萬", "万", "億", "亿", "兆", "千", "百萬", "百万", "十億", "十亿",
})


class Measure:
    """A number parsed out of a table cell, and how sure that reading is.

    ``is_range`` marks a value that was written as a span and is being carried
    as its midpoint. A midpoint is a summary of the cell, not the cell's own
    figure, so anything that publishes or grades the number needs to know the
    difference — the flag travels with the value rather than being discarded
    at the parse site.
    """

    __slots__ = ("value", "low", "high", "is_range", "is_approximate", "tolerance", "unit")

    def __init__(self, value: float, *, low: float | None = None, high: float | None = None,
                 is_range: bool = False, is_approximate: bool = False,
                 tolerance: float | None = None, unit: str = "") -> None:
        self.value = value
        self.low = low if low is not None else value
        self.high = high if high is not None else value
        self.is_range = is_range
        self.is_approximate = is_approximate
        self.tolerance = tolerance
        self.unit = unit

    @property
    def is_uncertain(self) -> bool:
        """True when the cell itself said the figure is not exact.

        A range midpoint, an approximation marker and a stated tolerance are
        three ways of saying the same thing, and a chart drawn from any of
        them owes its reader that qualification in the caption.
        """
        return self.is_range or self.is_approximate or self.tolerance is not None

    def as_dict(self) -> dict:
        return {
            "value": self.value,
            "low": self.low,
            "high": self.high,
            "is_range": self.is_range,
            "is_approximate": self.is_approximate,
            "tolerance": self.tolerance,
            "unit": self.unit,
        }

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return (
            f"Measure({self.value!r}, is_range={self.is_range}, "
            f"is_approximate={self.is_approximate}, tolerance={self.tolerance!r})"
        )


def _strip_decorations(text: str) -> tuple[str, bool, str]:
    """Remove markup, currency and unit noise.

    Returns the bare number text, whether the cell hedged it, and the unit it
    was written in. The unit is returned rather than discarded so a caption
    can name it: an axis labelled only "value" is what the old behaviour of
    throwing it away produced.
    """
    text = _MARKUP_RE.sub("", _FOOTNOTE_RE.sub("", text)).strip()
    approximate = False
    while True:
        stripped = _APPROX_RE.sub("", text).strip()
        if stripped == text:
            break
        text, approximate = stripped, True
    text = _CURRENCY_RE.sub("", text).strip()

    unit = ""
    ratio = _TRAILING_UNIT_RE.search(text)
    if ratio:
        unit = ratio.group(0)
        text = _TRAILING_UNIT_RE.sub("", text).strip()

    # A trailing word is a unit only when a number precedes it. Without that
    # test "n/a" and "見附錄" would parse to their own leftovers rather than
    # being reported as cells holding no figure.
    while True:
        match = _TRAILING_UNIT_TEXT_RE.search(text)
        if not match or not re.search(r"\d", text[: match.start()]):
            break
        token = match.group(0).strip()
        # A denominator is never a magnitude: "USD/t" is per tonne, and
        # refusing it as "trillion" would throw away a perfectly ordinary
        # price column.
        if not token.startswith("/") and token.casefold() in _MAGNITUDE_SUFFIXES:
            # Leave it attached so the cell fails to parse and is reported.
            break
        unit = (token + " " + unit).strip()
        text = text[: match.start()].strip()

    return text.strip(), approximate, unit


def _plain_number(text: str) -> float | None:
    text = text.replace(",", "").replace("　", "").strip()
    if text.startswith("(") and text.endswith(")"):
        text = "-" + text[1:-1]
    if not _NUMBER_RE.match(text):
        return None
    return float(text)


def parse_measure(value: Any) -> Measure | None:
    """Parse one table cell into a number, tolerating how people write them.

    Returns None when the cell states no single quantity; use
    ``unparsed_reason`` for the explanation to show the author.
    """
    raw = clean_text(value)
    if not raw:
        return None

    text, approximate, unit = _strip_decorations(raw)
    if not text:
        return None

    # "5 ± 0.3" is a reading and its uncertainty; "±5%" is an uncertainty on
    # its own, which is a real column in an engineering table (an error
    # column) and is read as the magnitude 5 with that magnitude as its own
    # tolerance, so the column is numeric rather than being thrown away.
    tolerance_match = _TOLERANCE_RE.match(text)
    if tolerance_match:
        stated = _plain_number(_strip_decorations(tolerance_match.group("tolerance"))[0])
        centre_text = tolerance_match.group("value").strip()
        centre = _plain_number(_strip_decorations(centre_text)[0]) if centre_text else None
        if stated is not None:
            if centre is None:
                return Measure(stated, tolerance=stated, is_approximate=approximate, unit=unit)
            return Measure(
                centre,
                low=centre - abs(stated),
                high=centre + abs(stated),
                tolerance=abs(stated),
                is_approximate=approximate,
                unit=unit,
            )

    direct = _plain_number(text)
    if direct is not None:
        return Measure(direct, is_approximate=approximate, unit=unit)

    parts = _RANGE_SEP_RE.split(text)
    if len(parts) != 2 and not _DATE_LIKE_RE.match(text):
        hyphenated = _HYPHEN_RE.split(text)
        parts = hyphenated if len(hyphenated) == 2 else parts
    if len(parts) == 2:
        low = _plain_number(_strip_decorations(parts[0])[0])
        high = _plain_number(_strip_decorations(parts[1])[0])
        if low is not None and high is not None:
            if low > high:
                low, high = high, low
            return Measure((low + high) / 2, low=low, high=high,
                           is_range=True, is_approximate=approximate, unit=unit)
    return None


def unparsed_reason(value: Any) -> str:
    """Why this cell yielded no number, in words an author can act on."""
    raw = clean_text(value)
    if not raw:
        return "cell is empty"
    text, _approximate, _unit = _strip_decorations(raw)
    if not re.search(r"\d", text):
        return "no digits in cell"
    if len(_RANGE_SEP_RE.split(text)) > 2:
        return "more than two values in one cell"
    match = _TRAILING_UNIT_TEXT_RE.search(text)
    token = match.group(0).strip() if match else ""
    if token and not token.startswith("/") and token.casefold() in _MAGNITUDE_SUFFIXES:
        return (
            f"magnitude suffix {match.group(0).strip()!r} is ambiguous; "
            "write the full number or move the scale into the column header"
        )
    return "digits present but not a number or a range"


def to_float(value: Any) -> float | None:
    measure = parse_measure(value)
    return None if measure is None else measure.value


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
