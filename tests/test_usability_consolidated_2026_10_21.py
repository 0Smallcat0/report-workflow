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


if __name__ == "__main__":
    unittest.main()
