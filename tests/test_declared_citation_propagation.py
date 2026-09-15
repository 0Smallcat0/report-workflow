"""A declared publication stays declared through the tool's own arithmetic.

Two gaps the first full course-report run exposed. A statistic the pipeline
computed over a declared dataset — the Ember grid-intensity table — lost the
citation and resolved to an [Sn] marker. And a declared white paper's own
bibliography (62 entries) and a news page's navigation links were read as
sources of the report, so the reference list of a 38-source report ran to 106.
"""
import json
import unittest
from datetime import datetime, timezone

from report_workflow.derived_evidence import build_requested_units, dataset_summary_units
from report_workflow.nodes.cited_sources import extract_cited_sources

CREATED_AT = datetime(2026, 9, 15, tzinfo=timezone.utc).isoformat()
EMBER = {"author": "Ember", "year": "2026", "title": "Lifecycle carbon intensity of electricity generation"}


def _source(source_id, file_name, rows, citation=None):
    entry = {
        "source_id": source_id, "file_name": file_name, "file_path": file_name, "file_type": "csv",
        "parsed_content": [{"block_type": "csv_row", "content": json.dumps(row, ensure_ascii=False)} for row in rows],
    }
    if citation:
        entry["citation"] = citation
    return entry


GRID = _source("g1", "grid.csv", [
    {"country": "Taiwan", "intensity": "633.21"},
    {"country": "Poland", "intensity": "588.60"},
    {"country": "France", "intensity": "41.44"},
], EMBER)
PARAMS = _source("p1", "params.csv", [
    {"name": "kwh_per_km", "value": "0.202"},
    {"name": "maintenance", "value": "4"},
])
REGISTRY = [GRID, PARAMS]


def _only(units, evidence_id):
    return next(unit for unit in units if unit["evidence_id"] == evidence_id)


class PropagationTests(unittest.TestCase):
    def test_summary_units_over_a_declared_dataset_carry_its_citation(self):
        units = dataset_summary_units(REGISTRY, CREATED_AT, zh=False)
        grid_units = [unit for unit in units if unit["source_file_name"] == "grid.csv"]
        self.assertTrue(grid_units)
        self.assertTrue(all(unit.get("citation") == EMBER for unit in grid_units))
        self.assertTrue(all("citation" not in unit for unit in units if unit["source_file_name"] == "params.csv"))

    def test_a_statistic_and_a_comparison_over_one_declared_dataset_are_cited_as_it(self):
        units, problems = build_requested_units(
            [
                {"id": "taiwan", "source": "grid.csv", "rows": "country=Taiwan", "op": "max", "column": "intensity"},
                {"id": "poland", "source": "grid.csv", "rows": "country=Poland", "op": "max", "column": "intensity"},
                {"id": "tw_over_pl", "op": "ratio", "numerator": "taiwan", "denominator": "poland", "decimals": 2},
            ],
            REGISTRY, CREATED_AT,
        )
        self.assertEqual(problems, [])
        for evidence_id in ("E_D_taiwan", "E_D_tw_over_pl"):
            with self.subTest(evidence_id=evidence_id):
                self.assertEqual(_only(units, evidence_id).get("citation"), EMBER)

    def test_a_formula_mixing_a_declared_dataset_with_project_data_is_not(self):
        units, problems = build_requested_units(
            [
                {"id": "pure", "op": "formula", "expr": "tw / 1000",
                 "inputs": {"tw": {"source": "grid.csv", "rows": "country=Taiwan", "column": "intensity"}}},
                {"id": "mixed", "op": "formula", "expr": "kwh * tw",
                 "inputs": {"kwh": {"source": "params.csv", "rows": "name=kwh_per_km", "column": "value"},
                            "tw": {"source": "grid.csv", "rows": "country=Taiwan", "column": "intensity"}}},
                {"id": "chained", "op": "formula", "expr": "mixed * 2", "inputs": {"mixed": "mixed"}},
            ],
            REGISTRY, CREATED_AT,
        )
        self.assertEqual(problems, [])
        self.assertEqual(_only(units, "E_D_pure").get("citation"), EMBER)
        self.assertNotIn("citation", _only(units, "E_D_mixed"))
        self.assertNotIn("citation", _only(units, "E_D_chained"))


class CitedSourcesTests(unittest.TestCase):
    def test_a_declared_publications_own_links_are_not_this_reports_sources(self):
        paper = {
            "source_id": "s1", "file_name": "icct.pdf", "citation": {"author": "Negri, M.", "year": "2025"},
            "parsed_content": [{"block_id": "page_40", "content": "Hill, N. (2020). https://ricardo.com/report.pdf"}],
        }
        notes = {
            "source_id": "s2", "file_name": "notes.md",
            "parsed_content": [{"block_id": "md_1", "content": "市場價格見 https://www.fastmarkets.com/prices/"}],
        }
        found = extract_cited_sources([paper, notes])
        self.assertEqual([row["source_file_name"] for row in found], ["notes.md"])


if __name__ == "__main__":
    unittest.main()
