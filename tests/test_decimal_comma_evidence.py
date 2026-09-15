"""A German source's 24,2 t and 90.000 km are 24.2 and 90,000.

The VDI life-cycle factsheet states its results in continental notation. FE read
"24,2 t" as 242 and "90.000 km" as 90.0, so a report restating the study's
90,000 km break-even — the figure its comparison with ICCT's 17,000 km turns on
— could cite it only by printing "90.000 km" to readers who take it for ninety.
"""
import unittest

from report_workflow.nodes.factuality_check import _check_content_overlap, _decimal_comma_to_point

VDI = {"content": (
    "Nach einer angenommenen Laufleistung von 200.000 Kilometern schneiden das betrachtete Elektroauto "
    "mit eine Akkukapazität vom 62 kWh (24,2 t CO 2äq) und der Plug-in-Hybrid (24,8 t CO 2äq) am besten ab. "
    "Diesel (33 t CO 2äq) und Benziner (37,1 t CO 2äq) folgen. Der Vorteil des Elektroautos stellt sich bei 90.000 km ein."
)}


class DecimalCommaTests(unittest.TestCase):
    def test_a_text_committed_to_the_notation_is_read_in_it(self):
        self.assertEqual(_decimal_comma_to_point("24,2 t und 90.000 km"), "24.2 t und 90000 km")
        # English numbers keep their meaning, and one of them keeps the text English.
        self.assertEqual(_decimal_comma_to_point("1,250 units at 3.5%, 24,2"), "1,250 units at 3.5%, 24,2")

    def test_the_restated_figures_are_supported_and_a_misread_one_is_not(self):
        claim = "德國 VDI 的研究以 200,000 km 計算，62 kWh 電動車為 24.2 t CO2e、汽油車 37.1 t CO2e，電動車在 90,000 km 後才比汽油車有利。"
        self.assertEqual(_check_content_overlap({"claim_text": claim}, VDI), [])
        self.assertTrue(_check_content_overlap({"claim_text": "德國 VDI 的研究中，62 kWh 電動車為 242 t CO2e。"}, VDI))


if __name__ == "__main__":
    unittest.main()
