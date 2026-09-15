"""A calculation the report states, computed on this side of the line.

A life-cycle comparison is arithmetic over cited parameters: production
emissions plus battery size times a factor, plus a per-kilometre figure times a
mileage; a break-even distance is one difference divided by another. None of it
is a statistic over rows, so none of it was expressible — the author's choice
was a side script whose output entered the run as a CSV nobody could check, or
a number typed into prose where FE blocks it. The formula is the author's; the
operands are read from the sources and the value is computed here.
"""
import json
import unittest
from datetime import datetime, timezone

from report_workflow.derived_evidence import build_requested_units, evaluate_formula, DerivationError

CREATED_AT = datetime(2026, 9, 15, tzinfo=timezone.utc).isoformat()

PARAMETERS = [
    {"參數": "電動車車體製造", "數值": "6.5", "單位": "t CO2e"},
    {"參數": "電池容量", "數值": "53.4", "單位": "kWh"},
    {"參數": "電池製造係數", "數值": "80", "單位": "kg CO2e/kWh"},
    {"參數": "汽油車車體製造", "數值": "7.2", "單位": "t CO2e"},
    {"參數": "年行駛里程", "數值": "11,896", "單位": "km"},
]

SCENARIOS = [
    {"情境": "A", "grid": "467", "fuel": "2.2906"},
    {"情境": "B", "grid": "605.8", "fuel": "2.930"},
]


def _source(source_id: str, file_name: str, rows: list[dict]) -> dict:
    return {
        "source_id": source_id,
        "file_name": file_name,
        "file_path": file_name,
        "file_type": "csv",
        "parsed_content": [
            {"block_type": "csv_row", "content": json.dumps(row, ensure_ascii=False)}
            for row in rows
        ],
    }


REGISTRY = [
    _source("p1", "lca_parameters.csv", PARAMETERS),
    _source("s1", "scenarios.csv", SCENARIOS),
]


def _cell(name: str) -> dict:
    return {"source": "lca_parameters.csv", "rows": f"參數={name}", "column": "數值"}


def _only(units: list[dict], evidence_id: str) -> dict:
    matches = [unit for unit in units if unit["evidence_id"] == evidence_id]
    assert len(matches) == 1, [unit["evidence_id"] for unit in units]
    return matches[0]


class ScalarFormulaTests(unittest.TestCase):
    def test_the_value_is_computed_from_cells_read_from_the_source(self):
        units, problems = build_requested_units(
            [{
                "id": "bev_production",
                "op": "formula",
                "expr": "body + kwh * factor / 1000",
                "inputs": {"body": _cell("電動車車體製造"), "kwh": _cell("電池容量"), "factor": _cell("電池製造係數")},
                "unit": "t CO2e",
                "decimals": 2,
                "label": "電動車製造排放",
                "expect": 10.77,
            }],
            REGISTRY,
            CREATED_AT,
            zh=True,
        )
        self.assertEqual(problems, [])
        unit = _only(units, "E_D_bev_production")
        self.assertIn("電動車製造排放為 10.77 t CO2e", unit["content"])
        # Every operand is stated with where it was read, so a reader can redo it.
        self.assertIn("kwh = 53.4（lca_parameters.csv 中 參數=電池容量 的 數值）", unit["content"])
        self.assertIn("body + kwh * factor / 1000", unit["content"])
        self.assertIn("參數=電池容量", unit["content"])
        operands = unit["derivation"]["operands"]
        self.assertEqual(operands["kwh"]["value"], 53.4)
        self.assertEqual(unit["derivation"]["method"], "formula")

    def test_every_operand_is_printed_with_the_places_it_was_used_with(self):
        units, problems = build_requested_units(
            [
                {"id": "direct_factor", "op": "formula", "expr": "fuel", "decimals": 4,
                 "inputs": {"fuel": {"source": "scenarios.csv", "rows": "情境=A", "column": "fuel"}}},
                {"id": "per_year", "op": "formula", "source": "scenarios.csv", "row_label": "情境", "decimals": 0,
                 "formulas": [{"label": "fuel emissions", "expr": "gd * annual", "unit": "kg"}],
                 "inputs": {"gd": "direct_factor", "annual": _cell("年行駛里程")}},
                {"id": "body_share", "op": "formula", "expr": "body / 13", "decimals": 3,
                 "inputs": {"body": _cell("電動車車體製造")}},
            ],
            REGISTRY,
            CREATED_AT,
            zh=True,
        )
        self.assertEqual(problems, [])
        content = _only(units, "E_D_per_year")["content"]
        # The operand line is there to be redone: 2.2906 * 11,896 = 27,249, and
        # "gd = 2.29" beside that cell gave a reader 27,242.
        self.assertIn("gd = 2.2906（", content)
        self.assertIn("A | 27,249", content)
        self.assertIn("body = 6.5（", _only(units, "E_D_body_share")["content"])

    def test_a_later_formula_can_use_an_earlier_one(self):
        units, problems = build_requested_units(
            [
                {"id": "life_km", "op": "formula", "expr": "annual * 15",
                 "inputs": {"annual": _cell("年行駛里程")}, "unit": "km"},
                {"id": "gap", "op": "formula", "expr": "(ev - ice) / km * 1000",
                 "inputs": {"ev": _cell("電動車車體製造"), "ice": _cell("汽油車車體製造"), "km": "life_km"},
                 "decimals": 4},
            ],
            REGISTRY,
            CREATED_AT,
        )
        self.assertEqual(problems, [])
        self.assertIn("178,440", _only(units, "E_D_life_km")["content"])
        self.assertEqual(_only(units, "E_D_gap")["derivation"]["operands"]["km"]["value"], 178440.0)

    def test_an_expectation_that_disagrees_is_reported_not_published(self):
        units, problems = build_requested_units(
            [{"id": "wrong", "op": "formula", "expr": "a * 2", "inputs": {"a": _cell("電池容量")}, "expect": 100}],
            REGISTRY,
            CREATED_AT,
        )
        self.assertEqual(units, [])
        self.assertIn("106.8", problems[0]["error"])


class FormulaTableTests(unittest.TestCase):
    def test_one_request_evaluates_every_row_and_places_as_a_table(self):
        units, problems = build_requested_units(
            [{
                "id": "use_phase",
                "op": "formula",
                "source": "scenarios.csv",
                "row_label": "情境",
                "formulas": [
                    {"label": "電動車", "expr": "kwh100 / 100 * grid", "unit": "g/km"},
                    {"label": "汽油車", "expr": "l100 / 100 * fuel * 1000", "unit": "g/km"},
                ],
                "inputs": {
                    "kwh100": {"source": "lca_parameters.csv", "rows": "參數=電池容量", "column": "數值"},
                    "l100": _cell("電池製造係數"),
                },
                "decimals": 1,
            }],
            REGISTRY,
            CREATED_AT,
        )
        self.assertEqual(problems, [])
        unit = _only(units, "E_D_use_phase")
        grid = unit["table_grid"]
        self.assertEqual(grid["headers"], ["情境", "電動車 (g/km)", "汽油車 (g/km)"])
        rows = {row[0]: row[1:] for row in grid["rows"]}
        self.assertEqual(rows["A"], [f"{0.534 * 467:,.1f}", f"{0.8 * 2.2906 * 1000:,.1f}"])
        self.assertEqual(unit["table_id"], "E_D_use_phase")

    def test_a_second_table_reads_the_same_row_of_the_first(self):
        units, problems = build_requested_units(
            [
                {"id": "per_km", "op": "formula", "source": "scenarios.csv", "row_label": "情境",
                 "formulas": [{"label": "g/km", "expr": "grid * 0.2"}], "inputs": {}, "decimals": 1},
                {"id": "lifetime", "op": "formula", "source": "scenarios.csv", "row_label": "情境",
                 "formulas": [{"label": "t", "expr": "per_km * km / 1000000"}],
                 "inputs": {"per_km": {"table": "per_km", "column": "g/km"},
                            "km": {"source": "lca_parameters.csv", "rows": "參數=年行駛里程", "column": "數值"}},
                 "decimals": 3},
            ],
            REGISTRY,
            CREATED_AT,
        )
        self.assertEqual(problems, [])
        rows = {row[0]: row[1:] for row in _only(units, "E_D_lifetime")["table_grid"]["rows"]}
        self.assertEqual(rows["A"], [f"{round(467 * 0.2, 1) * 11896 / 1e6:.3f}"])
        self.assertEqual(rows["B"], [f"{round(605.8 * 0.2, 1) * 11896 / 1e6:.3f}"])

    def test_a_ratio_can_read_a_cell_the_formula_table_produced(self):
        units, problems = build_requested_units(
            [
                {"id": "t", "op": "formula", "source": "scenarios.csv", "row_label": "情境",
                 "formulas": [{"label": "ev", "expr": "grid * 2"}], "inputs": {}, "decimals": 1},
                {"id": "b_over_a", "op": "ratio", "source": "t", "column": "ev",
                 "numerator_group": "B", "denominator_group": "A", "decimals": 3},
            ],
            REGISTRY,
            CREATED_AT,
        )
        self.assertEqual(problems, [])
        self.assertIn(f"{605.8 / 467:.3f}", _only(units, "E_D_b_over_a")["content"])


class RefusalTests(unittest.TestCase):
    """Each of these used to be a way for a typo to mint a figure."""

    def _problem(self, request: dict) -> str:
        units, problems = build_requested_units([request], REGISTRY, CREATED_AT)
        self.assertEqual(units, [])
        self.assertEqual(len(problems), 1)
        return problems[0]["error"]

    def test_an_undeclared_name_is_refused(self):
        message = self._problem({"id": "x", "op": "formula", "expr": "kwh * factr", "inputs": {"kwh": _cell("電池容量")}})
        self.assertIn("factr", message)

    def test_a_declared_input_nothing_uses_is_refused(self):
        message = self._problem({"id": "x", "op": "formula", "expr": "kwh * 2",
                                 "inputs": {"kwh": _cell("電池容量"), "kWh": _cell("電池容量")}})
        self.assertIn("kWh", message)

    def test_only_arithmetic_runs(self):
        for expr in ("__import__('os').getcwd()", "kwh.real", "max(kwh, 1)", "[kwh]", "kwh if kwh else 1"):
            with self.subTest(expr=expr):
                message = self._problem({"id": "x", "op": "formula", "expr": expr, "inputs": {"kwh": _cell("電池容量")}})
                self.assertIn("not allowed", message)

    def test_division_by_zero_is_named(self):
        with self.assertRaises(DerivationError):
            evaluate_formula("a / (b - b)", {"a": 1.0, "b": 2.0})

    def test_an_input_must_read_exactly_one_cell(self):
        message = self._problem({"id": "x", "op": "formula", "expr": "v",
                                 "inputs": {"v": {"source": "lca_parameters.csv", "rows": "單位~t", "column": "數值"}}})
        self.assertIn("selects 2 rows", message)

    def test_a_bare_number_is_not_an_input(self):
        message = self._problem({"id": "x", "op": "formula", "expr": "v * 2", "inputs": {"v": 53.4}})
        self.assertIn("bare number", message)

    def test_a_text_cell_is_not_a_number(self):
        message = self._problem({"id": "x", "op": "formula", "expr": "v",
                                 "inputs": {"v": {"source": "lca_parameters.csv", "rows": "參數=電池容量", "column": "單位"}}})
        self.assertIn("not a number", message)


if __name__ == "__main__":
    unittest.main()
