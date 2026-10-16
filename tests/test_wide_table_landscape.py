"""Eleven columns on a portrait page is four characters per column.

The shipped reference.docx is A4 with 1-inch margins, so the text column is
9026 twips. Pandoc emits every table at `tblW pct 5000`, so Word divides that
column evenly and an eleven-column table lands at 1.44 cm per column. A 9pt CJK
glyph is 3.2 mm. Four characters. A header such as 資金使用率 wraps to two
lines, so does most of the body, and the table stops being readable as a table.

Nothing in DOCX_RENDER looked at table width, so a reference doc could fix the
font and the borders and still hand back the same grey block. The fix is a
landscape section around the table, which is a page-layout decision and belongs
here rather than in the template.
"""
import re
import unittest
import zipfile
from pathlib import Path

from report_workflow.nodes.docx_render import (
    _LANDSCAPE_MIN_COLS,
    _page_geometry,
    _wrap_wide_tables,
)

_REFERENCE = (
    Path(__file__).resolve().parent.parent
    / "src" / "report_workflow" / "templates" / "reference.docx"
)


def _table(columns: int, label: str = "x") -> str:
    header = "| " + " | ".join(f"c{i}" for i in range(columns)) + " |"
    rule = "| " + " | ".join("---" for _ in range(columns)) + " |"
    row = "| " + " | ".join(label for _ in range(columns)) + " |"
    return "\n".join([header, rule, row])


def _orientations(md: str) -> list[str]:
    return [
        "landscape" if "landscape" in tag else "portrait"
        for tag in re.findall(r"<w:pgSz\b[^>]*/>", md)
    ]


class WideTableLandscapeTests(unittest.TestCase):
    def test_a_wide_table_is_bracketed_portrait_then_landscape(self):
        md = f"Lead sentence.\n\n{_table(_LANDSCAPE_MIN_COLS)}\n\nAfter.\n"
        out, flipped = _wrap_wide_tables(md, _REFERENCE)
        self.assertEqual(flipped, 1)
        # Portrait break closes the section above; landscape break closes the
        # table's own section. Reversing them silently rotates the whole rest
        # of the document.
        self.assertEqual(_orientations(out), ["portrait", "landscape"])

    def test_a_narrow_table_is_left_alone(self):
        md = f"Lead.\n\n{_table(_LANDSCAPE_MIN_COLS - 1)}\n\nAfter.\n"
        out, flipped = _wrap_wide_tables(md, _REFERENCE)
        self.assertEqual(flipped, 0)
        self.assertEqual(out, md)

    def test_wide_tables_separated_only_by_a_heading_share_one_section(self):
        # The case this was written for: two eleven-column tables with a lone
        # `### 4.3` between them put that heading in its own portrait section,
        # i.e. a near-empty portrait page between two landscape ones.
        md = (
            f"Lead.\n\n{_table(11, 'a')}\n\n### 4.3 Second lag\n\n"
            f"{_table(11, 'b')}\n\nAfter.\n"
        )
        out, flipped = _wrap_wide_tables(md, _REFERENCE)
        self.assertEqual(flipped, 1)
        self.assertEqual(_orientations(out), ["portrait", "landscape"])
        self.assertIn("### 4.3 Second lag", out)

    def test_prose_between_wide_tables_does_split_the_section(self):
        # A 24 cm measure holds ninety-odd CJK characters per line. Prose goes
        # back to the narrow column even at the cost of two more page flips.
        md = (
            f"Lead.\n\n{_table(11, 'a')}\n\nA paragraph explaining the table.\n\n"
            f"{_table(11, 'b')}\n\nAfter.\n"
        )
        out, flipped = _wrap_wide_tables(md, _REFERENCE)
        self.assertEqual(flipped, 2)
        self.assertEqual(
            _orientations(out), ["portrait", "landscape", "portrait", "landscape"]
        )

    def test_no_line_of_the_document_is_lost_or_duplicated(self):
        md = (
            f"# Title\n\nLead.\n\n{_table(11, 'a')}\n\n### Next\n\n"
            f"{_table(9, 'b')}\n\nClosing paragraph.\n"
        )
        out, _ = _wrap_wide_tables(md, _REFERENCE)
        stripped = re.sub(r"```\{=openxml\}.*?```", "", out, flags=re.DOTALL)
        self.assertEqual(
            [x for x in md.split("\n") if x.strip()],
            [x for x in stripped.split("\n") if x.strip()],
        )

    def test_the_landscape_section_keeps_the_template_paper_size(self):
        # A caller supplying `reference_docx_path` has already chosen a paper
        # size; a hard-coded A4 landscape break would change paper mid-document.
        width, height, margins = _page_geometry(_REFERENCE)
        out, _ = _wrap_wide_tables(f"{_table(11)}\n", _REFERENCE)
        land = [t for t in re.findall(r"<w:pgSz\b[^>]*/>", out) if "landscape" in t]
        self.assertEqual(len(land), 1)
        self.assertIn(f'w:w="{max(width, height)}"', land[0])
        self.assertIn(f'w:h="{min(width, height)}"', land[0])
        self.assertIn(f'w:left="{margins["left"]}"', out)

    def test_the_shipped_template_declares_the_geometry_we_read(self):
        # _page_geometry falls back to A4/1-inch when the reference doc says
        # nothing, which would hide a template that stopped declaring a page.
        with zipfile.ZipFile(_REFERENCE) as z:
            xml = z.read("word/document.xml").decode("utf-8")
        self.assertIn("<w:pgSz", xml)
        self.assertIn("<w:pgMar", xml)

    def test_a_missing_reference_doc_falls_back_instead_of_raising(self):
        width, height, margins = _page_geometry(Path("does-not-exist.docx"))
        self.assertEqual((width, height), (11906, 16838))
        self.assertEqual(margins["left"], 1440)


if __name__ == "__main__":
    unittest.main()
