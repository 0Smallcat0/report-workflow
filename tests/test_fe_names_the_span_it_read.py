"""When FE refuses a number, it says which words it read that number from.

FE refused a claim with "Claim number '1'組 is not stated in the evidence" and
stopped there. When the figure is written in digits the author can find it; when
it comes from a Chinese numeral there is nothing in the claim that looks like
"1", and the repair depends on guessing which characters the gate had read.

The sibling gate in the same tool already does this well — "Maximum 3 primary
claims allowed for academic_paper, found 5. Move extra claims to supporting or
background." names the limit, the actual, and the fix. This brings FE's number
refusal up to that standard.
"""
import unittest

from report_workflow.nodes.factuality_check import claim_number_source_text


class ClaimNumberSourceTextTests(unittest.TestCase):
    def test_a_chinese_numeral_is_located(self):
        span = claim_number_source_text("那一批共有 83 筆交易", "1", "批")
        self.assertIn("一批", span)

    def test_a_digit_is_located(self):
        span = claim_number_source_text("單筆平均是 2.14 個百分點", "2.14", "個")
        self.assertIn("2.14", span)

    def test_a_number_the_claim_does_not_contain_yields_nothing(self):
        self.assertEqual(claim_number_source_text("單筆平均是 2.14 個百分點", "99", "件"), "")

    def test_the_span_is_short_enough_to_read(self):
        span = claim_number_source_text(
            "滯後 60 分鐘、持有 5 交易日時，固定持有的單筆平均淨收益為 0.98 個百分點。",
            "0.98", "個",
        )
        self.assertTrue(span)
        self.assertLessEqual(len(span), 40, "a whole sentence is not a location")


if __name__ == "__main__":
    unittest.main()
