"""Thousands separators in FE (2026-11-18, batch 1 item B)."""
import unittest

from report_workflow.nodes.factuality_check import _check_content_overlap


def _fe(claim, evidence):
    return _check_content_overlap(
        {"claim_id": "c1", "claim_text": claim, "claim_type": "factual", "evidence_ids": ["E1"]},
        {"evidence_id": "E1", "content": evidence, "granularity": "paragraph", "source_file_name": "a.pdf"},
    )


class ThousandsSeparator(unittest.TestCase):
    def test_comma_and_plain_are_the_same_number(self):
        self.assertEqual(_fe("累積虧損 3,668 億元", "累積虧損 3668 億元"), [])
        self.assertEqual(_fe("累積虧損 3668 億元", "累積虧損 3,668 億元"), [])
        self.assertEqual(_fe("累積虧損 -3,668 億元", "累積虧損 -3668 億元"), [])

    def test_sign_is_still_significant(self):
        self.assertNotEqual(_fe("成長 3,668 億元", "成長 -3668 億元"), [])


if __name__ == "__main__":
    unittest.main()
