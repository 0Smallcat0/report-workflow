"""Defects found writing three reports through the consolidated usability work.

Each was met by an author following the brief from start_report to
publish_report; the run record is in
benchmarks/evidence/usability_consolidated_2026-10-21/README.md.
"""
from __future__ import annotations

import tempfile
import unittest

from report_workflow.state import ReportState


class OutlineShapeShowsOnlyWhatIsReadTests(unittest.TestCase):
    def _blueprint(self, profile):
        from report_workflow.nodes import blueprint_plan

        state = ReportState.new("x", [], tempfile.mkdtemp())
        state.spec["report_profile"] = profile
        return blueprint_plan.run_blueprint_plan(state).plan["blueprint"]

    def test_a_memo_outline_shape_has_no_results_mode(self):
        # The quant memo brief showed results_mode in the JSON shape and then
        # said "results_mode is not read for quant_research_memo; leave it out".
        from report_workflow.nodes.agent_tasks import outline_brief_sections_block

        block = outline_brief_sections_block(self._blueprint("quant_research_memo"), "quant_research_memo")
        self.assertNotIn("results_mode", block)
        lab = outline_brief_sections_block(self._blueprint("engineering_lab_report"), "engineering_lab_report")
        self.assertIn('"results_mode"', lab)



class TableHeadersReadAsWordsTests(unittest.TestCase):
    def test_a_placed_table_prints_its_headers_without_underscores(self):
        # The quant memo's two tables printed 「年化報酬_pct 平均」 in every header.
        from report_workflow.nodes.source_tables import render_source_table

        table = {
            "table_id": "E1",
            "headers": ["組合", "年化報酬_pct 平均", "review_count"],
            "rows": [["低波動", "8.53", "3"]],
            "source_file_name": "bt.csv",
            "computed": True,
        }
        rendered = render_source_table(table, number=1, caption="x", language="zh")
        self.assertIn("| 組合 | 年化報酬 (%) 平均 | review count |", rendered)
        self.assertNotIn("_pct", rendered)


if __name__ == "__main__":
    unittest.main()
