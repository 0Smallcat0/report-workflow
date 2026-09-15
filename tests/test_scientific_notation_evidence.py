"""A figure printed in scientific notation supports the claim that states it.

Taiwan's product carbon-footprint database prints its factors as "6.058E-01
kgCO₂e/度". Both number extractors accept the notation, and then the value
parser rewrote the exponent on its own — float("E-01") — and raised, so the
number was skipped and a claim stating the database's own figure was blocked
with "evidence states: 6.058E-01".
"""
import unittest

from report_workflow.nodes.factuality_check import _check_content_overlap, _normalize_number_str


class ScientificNotationTests(unittest.TestCase):
    def test_the_value_parser_reads_the_notation(self):
        self.assertAlmostEqual(_normalize_number_str("6.058E-01"), 0.6058)
        self.assertAlmostEqual(_normalize_number_str("2.930E+00"), 2.93)
        self.assertEqual(_normalize_number_str("~1,234.5"), 1234.5)

    def test_a_claim_stating_the_decimal_is_supported_and_a_wrong_one_is_not(self):
        evidence = {"content": "6.058E-01 kgCO₂e/度(kwh)"}
        self.assertEqual(_check_content_overlap({"claim_text": "電力碳足跡為 0.6058 kgCO2e/度。"}, evidence), [])
        self.assertTrue(_check_content_overlap({"claim_text": "電力碳足跡為 0.7058 kgCO2e/度。"}, evidence))

    def test_a_subscript_digit_is_the_same_token_as_its_ascii_digit(self):
        # The unit a source prints with a subscript and the claim types with a
        # plain 2 is one term; a different unit is still missing.
        evidence = {"content": "2.930E+00 kgCO₂e/公升(L)"}
        self.assertEqual(_check_content_overlap({"claim_text": "車用汽油碳足跡為 2.930 kgCO2e/公升。"}, evidence), [])
        self.assertTrue(_check_content_overlap({"claim_text": "車用汽油碳足跡為 2.930 MJ/公升。"}, evidence))


if __name__ == "__main__":
    unittest.main()
