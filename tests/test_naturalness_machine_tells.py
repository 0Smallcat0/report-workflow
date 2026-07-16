"""Advisory machine-tell detection in the publication naturalness pass.

Snake_case field names and internal ids (figrec_*, *_source, ev_*) in
publication prose read as machine output. The detector surfaces them as
warnings for the authoring agent to repair; it must never scan fenced code
blocks and it must not block anything.
"""
import unittest

from report_workflow.nodes.publication_naturalness_pass import (
    detect_machine_tell_identifiers,
)


class MachineTellDetectionTests(unittest.TestCase):
    def test_snake_case_in_prose_is_reported(self):
        md = "The structured_workflow condition beat the baseline on median_processing_minutes."
        found = detect_machine_tell_identifiers(md)
        self.assertIn("structured_workflow", found)
        self.assertIn("median_processing_minutes", found)

    def test_internal_ids_are_reported(self):
        md = "See figrec_1 built from chart_source for details grounded in ev_time."
        found = detect_machine_tell_identifiers(md)
        self.assertIn("figrec_1", found)
        self.assertIn("chart_source", found)
        self.assertIn("ev_time", found)

    def test_clean_prose_reports_nothing(self):
        md = (
            "# Results\n\nMedian processing time fell from 28 to 20 minutes per "
            "note, and reviewer satisfaction rose from 71% to 84%.\n"
        )
        self.assertEqual(detect_machine_tell_identifiers(md), [])

    def test_fenced_code_blocks_are_not_scanned(self):
        md = "Prose before.\n\n```python\nresult = run_factuality_check_fa(rows)\n```\n\nProse after.\n"
        self.assertEqual(detect_machine_tell_identifiers(md), [])

    def test_duplicates_are_reported_once(self):
        md = "structured_workflow beat manual. structured_workflow also scaled."
        self.assertEqual(
            detect_machine_tell_identifiers(md).count("structured_workflow"), 1
        )


if __name__ == "__main__":
    unittest.main()
