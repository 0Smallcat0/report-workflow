"""Text past the 2,000th character of a block is text no claim can cite.

The PDF parser files a page as one block and the evidence row kept its first
2,000 characters. Measured on a 38-page ICCT white paper: 33 pages ran past
that, 38% of the text never reached the ledger, and the report's headline
figure — break-even "after about 17,000 km", at character 2,057 of page 3 — was
cut, so FE refused every sentence stating it. A long block is now cut into rows
that fit, between lines or sentences, keeping its page and line locators.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from report_workflow.nodes.evidence_normalize import (
    EVIDENCE_CONTENT_LIMIT,
    _expanded_blocks,
)
from report_workflow.run_workflow import prepare_workflow
from report_workflow.state import WORKFLOW_RUNS_DIR

FILLER = "Battery electric cars were compared with combustion cars over the vehicle lifetime in this section."
NEEDLE = "the higher production emissions are offset after about 17,000 km of use"


def _page_text() -> str:
    lines = [FILLER] * 20
    lines.insert(21, f"Although production emissions are higher, {NEEDLE}.")
    lines.extend([FILLER] * 6)
    return "\n".join(lines)


def _all_packages_present(name: str, *args, **kwargs):
    return object()


class SplittingTests(unittest.TestCase):
    def test_a_pdf_page_is_cut_into_rows_that_keep_every_line_and_the_page(self):
        text = _page_text()
        self.assertGreater(text.find(NEEDLE), EVIDENCE_CONTENT_LIMIT)
        chunks = _expanded_blocks([{"block_id": "page_3", "block_type": "paragraph", "content": text, "page_number": 3}])
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk["content"]) <= EVIDENCE_CONTENT_LIMIT for chunk in chunks))
        self.assertTrue(all(chunk["page_number"] == 3 for chunk in chunks))
        self.assertEqual("\n".join(chunk["content"] for chunk in chunks), text)
        self.assertEqual(sum(NEEDLE in chunk["content"] for chunk in chunks), 1)
        self.assertEqual(len({chunk["block_id"] for chunk in chunks}), len(chunks))

    def test_a_single_long_line_is_cut_between_sentences(self):
        line = " ".join([FILLER] * 40)
        chunks = _expanded_blocks([{"block_id": "md_1", "block_type": "paragraph", "content": line,
                                    "line_start": 7, "line_end": 7}])
        self.assertGreater(len(chunks), 1)
        for chunk in chunks:
            self.assertLessEqual(len(chunk["content"]), EVIDENCE_CONTENT_LIMIT)
            self.assertTrue(chunk["content"].endswith("section."))
            self.assertEqual((chunk["line_start"], chunk["line_end"]), (7, 7))

    def test_line_numbers_follow_the_lines_each_row_holds(self):
        text = _page_text()
        chunks = _expanded_blocks([{"block_id": "md_4", "block_type": "paragraph", "content": text,
                                    "line_start": 100, "line_end": 100 + text.count("\n")}])
        self.assertEqual(chunks[0]["line_start"], 100)
        self.assertEqual(chunks[-1]["line_end"], 100 + text.count("\n"))
        for before, after in zip(chunks, chunks[1:]):
            self.assertEqual(after["line_start"], before["line_end"] + 1)

    def test_a_block_that_fits_is_left_exactly_as_it_was(self):
        block = {"block_id": "md_2", "block_type": "paragraph", "content": FILLER, "line_start": 3, "line_end": 3,
                 "content_hash": "abc"}
        self.assertEqual(_expanded_blocks([block]), [block])


class LedgerTests(unittest.TestCase):
    def test_the_figure_past_the_old_cut_is_citable_evidence(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "white_paper.txt"
            source.write_text(_page_text().replace("\n", " "), encoding="utf-8")
            with patch("report_workflow.preflight.importlib.util.find_spec", side_effect=_all_packages_present):
                state = prepare_workflow("summarise the white paper", [str(source)], str(Path(tmpdir) / "out"),
                                         report_profile="custom")
            ledger = [
                json.loads(line)
                for line in (WORKFLOW_RUNS_DIR / state.job_id / "evidence_ledger.jsonl").read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            self.assertTrue(any(NEEDLE in row["content"] for row in ledger))
            self.assertTrue(all(len(row["content"]) <= EVIDENCE_CONTENT_LIMIT for row in ledger))


if __name__ == "__main__":
    unittest.main()
