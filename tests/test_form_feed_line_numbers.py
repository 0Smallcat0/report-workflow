"""A line number points at the line a reader opens.

A PDF exported to text carries a form feed at every page break, and the parsers
split with ``str.splitlines``, which counts a form feed as a line. In the 2050
net-zero pathway, text on line 908 — 39 page breaks down — was cited as line 947, and a
``"lines": "950-971"`` selection kept the wrong passage while dropping the
2030/2035/2040 targets it had been chosen for — without an error, because the
passage it kept was not empty.
"""
import tempfile
import unittest
from pathlib import Path

from report_workflow.parsers.semi_structured_parser import parse_markdown, parse_txt
from report_workflow.parsers.source_text import split_source_lines
from report_workflow.source_selection import apply_selection

PAGED = (
    "Page one introduces the plan.\n"
    "\n"
    "\fPage two opens with the bus target for 2030.\n"
    "\n"
    "Page two continues with the car sales targets.\n"
)


def _block_starting(blocks: list[dict], text: str) -> dict:
    return next(block for block in blocks if text in block["content"])


class FormFeedLineNumberTests(unittest.TestCase):
    def test_a_form_feed_is_not_a_line(self):
        self.assertEqual(len(split_source_lines(PAGED)), 5)
        self.assertEqual(len(split_source_lines("a\r\n\r\nb\r\n")), 3)
        self.assertEqual(len(split_source_lines("a\rb")), 2)

    def test_text_and_markdown_blocks_carry_the_editor_line(self):
        for suffix, parser in ((".txt", parse_txt), (".md", parse_markdown)):
            with self.subTest(suffix=suffix), tempfile.TemporaryDirectory() as tmpdir:
                path = Path(tmpdir) / f"plan{suffix}"
                path.write_text(PAGED, encoding="utf-8")
                blocks = parser(str(path))["blocks"]
                self.assertEqual(_block_starting(blocks, "bus target")["line_start"], 3)
                self.assertEqual(_block_starting(blocks, "car sales")["line_start"], 5)

    def test_a_line_selection_keeps_the_passage_it_names(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "plan.txt"
            path.write_text(PAGED, encoding="utf-8")
            kept = apply_selection(parse_txt(str(path))["blocks"], {"lines": [(5, 5)]}, "plan.txt")
            self.assertEqual([block["content"] for block in kept], ["Page two continues with the car sales targets."])


if __name__ == "__main__":
    unittest.main()
