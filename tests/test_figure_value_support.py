"""A chart is held to what the prose beside it is held to.

FIGURE_BUILD draws the numbers written into figure_plan.json. Every claim had
to find its number in the ledger, but nothing compared a figure's plotted
values with the evidence it cites, so a bar chart could plot any number under a
real evidence id — found while charting a life-cycle scenario table.
"""
import json
import tempfile
import unittest
from pathlib import Path

from report_workflow.nodes.figure_plan_audit import audit_figure_plan
from report_workflow.state import ReportState, run_dir_for

TABLE = {
    "evidence_id": "E_D_stage_breakdown",
    "source_file_name": "stage_rows.csv",
    "content": "衍生計算(來源:stage_rows.csv):階段組成。\n車種 | 車體 (t CO2e) | 電池 (t CO2e)\n汽油車 | 7.2 | 0.0\n電動車 | 6.5 | 4.3",
    "table_grid": {"headers": ["車種", "車體 (t CO2e)", "電池 (t CO2e)"], "rows": [["汽油車", "7.2", "0.0"], ["電動車", "6.5", "4.3"]]},
}
FACTOR_ROW = {
    "evidence_id": "E_cfp",
    "source_file_name": "electricity_cfp.txt",
    "content": "6.058E-01 kgCO₂e/度(kwh)",
}
CHANGE_ROW = {
    "evidence_id": "E_gap",
    "source_file_name": "knobloch.csv",
    "content": "瑞典 | 75.7 | 253.8 | -70.2",
}


def _state(tmpdir: str) -> ReportState:
    state = ReportState.new("write report", [], str(Path(tmpdir) / "out"))
    state.spec["report_profile"] = "custom"
    ledger = run_dir_for(state) / "evidence_ledger.jsonl"
    ledger.parent.mkdir(parents=True, exist_ok=True)
    ledger.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in (TABLE, FACTOR_ROW, CHANGE_ROW)) + "\n", encoding="utf-8")
    state.sources["evidence_ledger_path"] = str(ledger)
    return state


def _audit(tmpdir: str, figure: dict) -> dict:
    state = _state(tmpdir)
    base = {"figure_id": "1", "title": "階段組成", "xlabel": "車種", "ylabel": "排放 (t CO2e)", "section_id": "results",
            "chart_selection_reason": "Composition of each vehicle's total."}
    plan = {"figures": [{**base, **figure}]}
    return audit_figure_plan(state, [], plan, run_dir_for(state) / "section_drafts" / "figure_plan.json")


def _types(report: dict) -> set[str]:
    return {issue["type"] for issue in report["hard_issues"]}


class FigureValueSupportTests(unittest.TestCase):
    def test_values_read_from_the_cited_table_pass(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            report = _audit(tmpdir, {
                "figure_type": "stacked_bar", "source_evidence_ids": ["E_D_stage_breakdown"],
                "data": {"labels": ["汽油車", "電動車"], "series": [{"name": "車體", "values": [7.2, 6.5]}, {"name": "電池", "values": [0, 4.3]}]},
            })
            self.assertNotIn("figure_value_not_in_evidence", _types(report))

    def test_a_value_the_evidence_does_not_state_is_blocked_by_value(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            report = _audit(tmpdir, {
                "figure_type": "stacked_bar", "source_evidence_ids": ["E_D_stage_breakdown"],
                "data": {"labels": ["汽油車", "電動車"], "series": [{"name": "車體", "values": [7.2, 6.5]}, {"name": "電池", "values": [0, 3.1]}]},
            })
            issue = next(item for item in report["hard_issues"] if item["type"] == "figure_value_not_in_evidence")
            self.assertEqual(issue["unsupported_values"], [3.1])
            self.assertIn("3.1", issue["detail"])

    def test_scientific_notation_signs_and_table_figures_are_read(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            report = _audit(tmpdir, {
                "figure_type": "bar", "source_evidence_ids": ["E_cfp", "E_gap"],
                "data": {"labels": ["電力碳足跡", "瑞典差距"], "series": [{"name": "數值", "values": [0.6058, -70.2]}]},
            })
            self.assertEqual(_types(report), set())
            flipped = _audit(tmpdir, {
                "figure_type": "bar", "source_evidence_ids": ["E_gap"],
                "data": {"labels": ["瑞典差距"], "series": [{"name": "數值", "values": [70.2]}]},
            })
            self.assertIn("figure_value_not_in_evidence", _types(flipped))

    def test_an_evidence_id_the_ledger_lacks_is_named(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            report = _audit(tmpdir, {
                "figure_type": "bar", "source_evidence_ids": ["E_missing"],
                "data": {"labels": ["a"], "series": [{"name": "數值", "values": [1]}]},
            })
            self.assertIn("figure_evidence_not_in_ledger", _types(report))


if __name__ == "__main__":
    unittest.main()
