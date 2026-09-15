"""An emission intensity is a mass per something, whatever gas it names.

"633.21 g CO2e/kWh", "kgCO₂e/度", a column headed "(g CO2e/kWh)": the unit
reader stopped at the space or at the digit of CO2, so the prose came out "g",
the glued form "kgCO", and the header "gco2e/kwh" — three spellings of one unit
that never matched each other, and every correct claim restating a grid factor
or a per-kilometre figure from its source was blocked.
"""
import json
import unittest

from report_workflow.nodes.factuality_check import _check_content_overlap


class EmissionIntensityUnitTests(unittest.TestCase):
    def test_a_glued_gas_and_a_per_prefix_name_the_same_unit(self):
        evidence = {"content": "6.058E-01 kgCO₂e/度(kwh)"}
        self.assertEqual(_check_content_overlap({"claim_text": "電力碳足跡為每度 0.6058 kg CO2e。"}, evidence), [])
        self.assertTrue(_check_content_overlap({"claim_text": "電力碳足跡為每度 0.6058 g CO2e。"}, evidence))

    def test_a_bracketed_column_unit_meets_the_prose_unit(self):
        row = {"content": json.dumps({"國家或地區": "臺灣", "生命週期碳強度 (g CO2e/kWh)": "633.21"}, ensure_ascii=False),
               "block_type": "csv_row"}
        self.assertEqual(_check_content_overlap({"claim_text": "臺灣電網的生命週期碳強度為 633.21 g CO2e/kWh。"}, row), [])
        self.assertTrue(_check_content_overlap({"claim_text": "臺灣電網的生命週期碳強度為 633.21 g CO2e/km。"}, row))

    def test_a_per_kilometre_figure_in_prose_keeps_its_denominator(self):
        evidence = {"content": "BEVs had estimated life-cycle GHG emissions of 63 g CO₂e/km."}
        self.assertEqual(_check_content_overlap({"claim_text": "純電動車為 63 g CO2e/km。"}, evidence), [])
        self.assertTrue(_check_content_overlap({"claim_text": "純電動車為 63 g CO2e/kWh。"}, evidence))


if __name__ == "__main__":
    unittest.main()
