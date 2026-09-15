"""The 2 of CO₂ stays on its line.

pdfplumber groups characters into lines by their top edge. A subscript set
5.8 pt below the letters beside it fell outside the 3 pt tolerance, so every
"CO₂e/km" in the ICCT white paper was read as "CO e/km" with the 2 on a line of
its own: 72 times in one 38-page report. A claim writing "63 g CO2e/km" shared
no term with its source and was blocked, and the stray digits read as figures.
"""
import unittest

from report_workflow.parsers.semi_structured_parser import _page_text


class FakePage:
    def __init__(self, chars):
        self.chars = chars

    def extract_text(self):
        return "page.extract_text"


def _char(text, x0, top, size=9.0, width=None):
    width = size * 0.5 if width is None else width
    return {
        "text": text, "x0": x0, "x1": x0 + width, "top": top, "bottom": top + size, "doctop": top,
        "upright": True, "size": size, "height": size, "width": width, "fontname": "Body",
        "matrix": (size, 0, 0, size, x0, 800 - top - size),
    }


def _line(text, x0, top, chars, scripts=None):
    """Lay out one line; ``scripts`` maps a character index to (top offset, size)."""
    x = x0
    for index, letter in enumerate(text):
        offset, size = (scripts or {}).get(index, (0.0, 9.0))
        width = 2.6 if size < 9 else 4.5
        chars.append(_char(letter, x, top + offset, size=size, width=width))
        x += width
    return chars


class InlineScriptTests(unittest.TestCase):
    def test_a_subscript_is_read_inside_its_word(self):
        chars = _line("63 g CO2e/km.", 10, 100, [], scripts={6: (5.8, 5.2)})
        _line("next line", 10, 113, chars)
        self.assertEqual(_page_text(FakePage(chars)).splitlines(), ["63 g CO2e/km.", "next line"])

    def test_a_superscript_footnote_mark_stays_with_its_word(self):
        chars = _line("sold in 20231 were", 10, 200, [], scripts={11: (-1.2, 5.2)})
        self.assertEqual(_page_text(FakePage(chars)), "sold in 20231 were")

    def test_small_text_away_from_the_body_is_left_where_it_is(self):
        chars = _line("Body text here", 10, 100, [])
        _line("0.5", 300, 40, chars, scripts={0: (0, 5.2), 1: (0, 5.2), 2: (0, 5.2)})
        self.assertEqual(_page_text(FakePage(chars)).splitlines(), ["0.5", "Body text here"])
        self.assertEqual(_page_text(FakePage(_line("No scripts", 10, 100, []))), "page.extract_text")


if __name__ == "__main__":
    unittest.main()
