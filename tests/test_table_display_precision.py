"""A table shows each column at the precision a reader needs.

Found in the Word file of a Chinese LCA course report: the break-even table
printed 44,208.8 km and 105,311.6 km beside 3.7 years. A tenth of a kilometre
over a fifteen-year life is precision nobody measured, and the reviewer asked
for 約 44,200 km. A formula table had one ``decimals`` for every column, so
the kilometre column and the year column could not differ, and rounding the
recorded value would also have moved the evidence the prose is checked
against. A column now declares how it is shown; the recorded figure keeps its
places.
"""
import unittest
from datetime import datetime, timezone

from report_workflow.derived_evidence import build_requested_units
from report_workflow.nodes.source_tables import collect_source_tables, render_source_table

from tests.test_formula_derivations import REGISTRY as PARAMETER_REGISTRY, _source

CREATED_AT = datetime(2026, 9, 15, tzinfo=timezone.utc).isoformat()

SCENARIOS = [
    {"情境": "A", "gap": "3.572", "saving": "80.7984", "annual": "11896"},
    {"情境": "B", "gap": "3.572", "saving": "33.9178", "annual": "11896"},
    {"情境": "C", "gap": "4.425", "saving": "100", "annual": "11896"},
]

REGISTRY = PARAMETER_REGISTRY + [_source("b1", "breakeven.csv", SCENARIOS)]


def _breakeven_table(**column_display) -> dict:
    return {
        "id": "breakeven",
        "op": "formula",
        "source": "breakeven.csv",
        "row_label": "情境",
        "label": "碳平衡點",
        "decimals": 1,
        "formulas": [
            {"label": "碳平衡點", "expr": "gap * 1000000 / saving", "unit": "km",
             **({"display_decimals": column_display["km"]} if "km" in column_display else {})},
            {"label": "約需", "expr": "gap * 1000000 / saving / annual", "unit": "年",
             **({"display_decimals": column_display["years"]} if "years" in column_display else {})},
        ],
    }


def _rendered(request: dict) -> tuple[dict, str]:
    units, problems = build_requested_units([request], REGISTRY, CREATED_AT, zh=True)
    if problems:
        raise AssertionError(problems)
    unit = next(unit for unit in units if unit["evidence_id"] == "E_D_breakeven")
    table = collect_source_tables(units)["E_D_breakeven"]
    return unit, render_source_table(table, number=4, caption="臺灣各情境的碳平衡點", language="zh")


class ColumnDisplayTests(unittest.TestCase):
    def test_kilometres_round_to_hundreds_and_years_keep_one_place(self):
        unit, markdown = _rendered(_breakeven_table(km=-2, years=1))
        self.assertIn("| A | 44,200 | 3.7 |", markdown)
        self.assertIn("| B | 105,300 | 8.9 |", markdown)
        self.assertNotIn("44,208.8", markdown)

    def test_the_recorded_figure_keeps_its_places(self):
        unit, _markdown = _rendered(_breakeven_table(km=-2, years=1))
        self.assertEqual(unit["table_grid"]["rows"][0][:2], ["A", "44,208.8"])
        self.assertIn("44,208.8", unit["content"])

    def test_a_column_without_a_display_rule_prints_as_recorded(self):
        _unit, markdown = _rendered(_breakeven_table())
        self.assertIn("| A | 44,208.8 | 3.7 |", markdown)

    def test_a_half_rounds_away_from_zero_as_a_reader_expects(self):
        # Python's round() sends 44,250 to 44,200 (half to even). A reader
        # rounding the printed figure by hand writes 44,300.
        _unit, markdown = _rendered(_breakeven_table(km=-2, years=1))
        self.assertIn("| C | 44,300 | 3.7 |", markdown)

    def test_a_column_cannot_be_shown_more_precisely_than_it_was_recorded(self):
        units, problems = build_requested_units(
            [_breakeven_table(km=3)], REGISTRY, CREATED_AT, zh=True
        )
        self.assertTrue(problems, "a display finer than the recorded decimals was accepted")
        self.assertIn("display_decimals", str(problems[0]))


class ChainedPrecisionTests(unittest.TestCase):
    """A figure computed from an earlier figure used the earlier one's rounding.

    Found cross-checking the same report by hand: a grid intensity converted
    to the plug was recorded as 658.4 g CO2e/kWh (one place, as the prose
    states it), and the break-even distance computed from it came out
    50,902.6 km where the arithmetic on the exact 658.3593 gives 50,896.7 km.
    The rounding exists so that the evidence states what the prose may say;
    carried into the next formula it changes a result nobody rounded.
    """

    def test_a_formula_reads_an_earlier_formula_at_full_precision(self):
        units, problems = build_requested_units(
            [
                {"id": "third", "op": "formula", "expr": "kwh / kwh / 3",
                 "inputs": {"kwh": {"source": "lca_parameters.csv", "rows": "參數=電池容量", "column": "數值"}},
                 "decimals": 1, "label": "三分之一"},
                {"id": "whole", "op": "formula", "expr": "third * 3", "inputs": {"third": "third"},
                 "decimals": 4, "label": "乘回三倍"},
            ],
            REGISTRY, CREATED_AT, zh=True,
        )
        self.assertEqual(problems, [])
        third = next(unit for unit in units if unit["evidence_id"] == "E_D_third")
        whole = next(unit for unit in units if unit["evidence_id"] == "E_D_whole")
        self.assertIn("三分之一為 0.3", third["content"])
        self.assertIn("乘回三倍為 1.0000", whole["content"])


if __name__ == "__main__":
    unittest.main()
