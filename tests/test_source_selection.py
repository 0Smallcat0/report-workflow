"""A report that uses pages 80-86 of a white paper reads pages 80-86.

The alternatives were the whole document in the ledger — thousands of rows the
author wades through and the gates scan — or a hand-copied excerpt that loses
the page numbers a reader checks against. A source entry now names its span.
"""
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from report_workflow.agent_wrapper import _source_selection_map
from report_workflow.cli import _load_source_manifest
from report_workflow.errors import QAHardBlockError
from report_workflow.run_workflow import prepare_workflow
from report_workflow.source_selection import (
    SourceSelectionError,
    apply_selection,
    parse_ranges,
)
from report_workflow.state import WORKFLOW_RUNS_DIR

TEXT = "\n\n".join(f"Paragraph {n}: battery production emissions note number {n} for the white paper." for n in range(1, 13))


def _all_packages_present(name: str, *args, **kwargs):
    return object()


def _ledger(state) -> list[dict]:
    path = WORKFLOW_RUNS_DIR / state.job_id / "evidence_ledger.jsonl"
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class RangeTests(unittest.TestCase):
    def test_ranges_and_single_numbers(self):
        self.assertEqual(parse_ranges("80-86, 90", "pages"), [(80, 86), (90, 90)])
        self.assertEqual(parse_ranges([3, "5–7"], "pages"), [(3, 3), (5, 7)])

    def test_malformed_ranges_are_refused_by_name(self):
        for value in ("80 to 86", "9-3", "0", ""):
            with self.subTest(value=value), self.assertRaises(SourceSelectionError):
                parse_ranges(value, "source_files[2].pages")

    def test_pages_keep_only_blocks_on_those_pages(self):
        blocks = [{"block_id": f"page_{n}", "content": f"page {n}", "page_number": n} for n in range(1, 6)]
        kept = apply_selection(blocks, {"pages": [(2, 3)]}, "paper.pdf")
        self.assertEqual([block["page_number"] for block in kept], [2, 3])

    def test_lines_keep_blocks_that_overlap(self):
        blocks = [{"block_id": f"md_{n}", "content": "x", "line_start": n * 10, "line_end": n * 10 + 5} for n in range(1, 5)]
        kept = apply_selection(blocks, {"lines": [(24, 31)]}, "notes.txt")
        self.assertEqual([block["line_start"] for block in kept], [20, 30])

    def test_a_selection_the_file_cannot_have_is_named(self):
        text_blocks = [{"block_id": "md_1", "content": "x", "line_start": 1, "line_end": 2}]
        with self.assertRaises(SourceSelectionError) as caught:
            apply_selection(text_blocks, {"pages": [(1, 2)]}, "notes.txt")
        self.assertIn("select 'lines'", str(caught.exception))
        with self.assertRaises(SourceSelectionError) as empty:
            apply_selection(text_blocks, {"lines": [(90, 95)]}, "notes.txt")
        self.assertIn("contains no text", str(empty.exception))


class SurfaceAndLedgerTests(unittest.TestCase):
    def test_both_entry_points_carry_the_selection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "paper.txt"
            source.write_text(TEXT, encoding="utf-8")
            mapping = _source_selection_map([{"path": str(source), "lines": "5-9"}])
            self.assertEqual(mapping["paper.txt"], {"lines": [(5, 9)]})
            manifest = Path(tmpdir) / "sources.json"
            manifest.write_text(json.dumps([{"path": "paper.txt", "lines": "5-9"}]), encoding="utf-8")
            _files, _roles, _citations, selections = _load_source_manifest(str(manifest))
            self.assertEqual(selections["paper.txt"], {"lines": [(5, 9)]})

    def test_only_the_selected_lines_reach_the_ledger_with_their_real_numbers(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "paper.txt"
            source.write_text(TEXT, encoding="utf-8")
            with patch("report_workflow.preflight.importlib.util.find_spec", side_effect=_all_packages_present):
                state = prepare_workflow("summarise", [str(source)], str(Path(tmpdir) / "out"), report_profile="custom",
                                         source_selections=_source_selection_map([{"path": str(source), "lines": "5-9"}]))
            rows = [row for row in _ledger(state) if row["source_file_name"] == "paper.txt"]
            self.assertTrue(rows)
            self.assertTrue(all(5 <= row["line_start"] <= 9 for row in rows))
            self.assertEqual({row["content"].split(":")[0] for row in rows}, {"Paragraph 3", "Paragraph 4", "Paragraph 5"})
            registry = state.sources["source_registry"][0]
            self.assertEqual(registry["selection_applied"]["blocks_kept"], 3)

    def test_an_empty_selection_stops_prepare_with_the_reason(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            source = Path(tmpdir) / "paper.txt"
            source.write_text(TEXT, encoding="utf-8")
            with patch("report_workflow.preflight.importlib.util.find_spec", side_effect=_all_packages_present):
                with self.assertRaises(QAHardBlockError) as caught:
                    prepare_workflow("summarise", [str(source)], str(Path(tmpdir) / "out"), report_profile="custom",
                                     source_selections=_source_selection_map([{"path": str(source), "lines": "900-950"}]))
            self.assertIn("paper.txt: the selection (lines 900-950) contains no text", str(caught.exception))


if __name__ == "__main__":
    unittest.main()
