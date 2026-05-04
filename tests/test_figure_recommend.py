import json
import tempfile
import unittest
from pathlib import Path

from report_workflow.errors import QAHardBlockError
from report_workflow.nodes.figure_recommend import (
    audit_figure_plan,
    recommend_figures_from_evidence,
    run_figure_plan_audit,
    run_figure_recommend,
)
from report_workflow.state import ReportState, run_dir_for


def _state(tmpdir: str, profile: str = "engineering_lab_report") -> ReportState:
    state = ReportState.new("write report", [], str(Path(tmpdir) / "out"))
    state.spec["report_profile"] = profile
    state.plan["blueprint"] = {
        "sections": {"results": {}, "data": {}},
        "section_order": ["results", "data"],
    }
    return state


class FigureRecommendationTests(unittest.TestCase):
    def test_recommends_pie_for_composition_table(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            evidence = [{
                "evidence_id": "E1",
                "source_id": "composition",
                "source_file_name": "composition.csv",
                "granularity": "table",
                "content": "Segment share distribution",
                "table_data": [
                    ["Segment", "Share"],
                    ["Design", "60"],
                    ["Testing", "40"],
                ],
            }]

            recommendations = recommend_figures_from_evidence(state, evidence)

            self.assertEqual(recommendations[0]["recommended_figure_type"], "pie")
            self.assertIn("bar", recommendations[0]["acceptable_figure_types"])
            self.assertEqual(recommendations[0]["figure_plan"]["figure_type"], "pie")

    def test_recommends_line_for_time_series(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            evidence = [{
                "evidence_id": "E1",
                "source_id": "voltage",
                "source_file_name": "voltage.csv",
                "granularity": "table",
                "content": "Voltage over time",
                "table_data": [
                    ["Time", "Voltage"],
                    ["0", "1.2"],
                    ["1", "1.5"],
                    ["2", "1.7"],
                ],
            }]

            recommendations = recommend_figures_from_evidence(state, evidence)

            self.assertEqual(recommendations[0]["recommended_figure_type"], "line")
            self.assertEqual(recommendations[0]["figure_plan"]["data"]["labels"], ["0", "1", "2"])

    def test_recommends_bar_for_category_value_table(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            evidence = [{
                "evidence_id": "E1",
                "source_id": "materials",
                "source_file_name": "materials.csv",
                "granularity": "table",
                "content": "Material strength comparison",
                "table_data": [
                    ["Material", "Strength"],
                    ["A", "12"],
                    ["B", "18"],
                    ["C", "16"],
                ],
            }]

            recommendations = recommend_figures_from_evidence(state, evidence)

            self.assertEqual(recommendations[0]["recommended_figure_type"], "bar")

    def test_groups_csv_row_evidence_before_recommending(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            evidence = [
                {
                    "evidence_id": "E1",
                    "source_id": "measurements",
                    "source_file_name": "measurements.csv",
                    "granularity": "table_row",
                    "content": json.dumps({"Trial": "1", "Voltage": "1.2"}),
                    "table_data": [["Trial", "Voltage"], ["1", "1.2"]],
                },
                {
                    "evidence_id": "E2",
                    "source_id": "measurements",
                    "source_file_name": "measurements.csv",
                    "granularity": "table_row",
                    "content": json.dumps({"Trial": "2", "Voltage": "1.4"}),
                    "table_data": [["Trial", "Voltage"], ["2", "1.4"]],
                },
                {
                    "evidence_id": "E3",
                    "source_id": "measurements",
                    "source_file_name": "measurements.csv",
                    "granularity": "table_row",
                    "content": json.dumps({"Trial": "3", "Voltage": "1.6"}),
                    "table_data": [["Trial", "Voltage"], ["3", "1.6"]],
                },
            ]

            recommendations = recommend_figures_from_evidence(state, evidence)

            self.assertEqual(recommendations[0]["recommended_figure_type"], "line")
            self.assertEqual(recommendations[0]["evidence_ids"], ["E1", "E2", "E3"])


class FigurePlanAuditTests(unittest.TestCase):
    def test_audit_hard_blocks_unjustified_high_confidence_mismatch(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            run_figure_recommend_with_composition_data(state)
            run_dir = run_dir_for(state)
            draft_dir = run_dir / "section_drafts"
            draft_dir.mkdir(parents=True, exist_ok=True)
            (draft_dir / "figure_plan.json").write_text(json.dumps({
                "figures": [{
                    "figure_id": "figrec_1",
                    "figure_type": "line",
                    "recommendation_id": "figrec_1",
                    "source_evidence_ids": ["E1"],
                    "title": "Share trend",
                    "data": {"labels": ["Design", "Testing"], "series": [{"name": "Share", "values": [60, 40]}]},
                }]
            }), encoding="utf-8")

            with self.assertRaises(QAHardBlockError):
                run_figure_plan_audit(state)

    def test_audit_allows_justified_mismatch_but_reports_warning(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            run_figure_recommend_with_composition_data(state)
            run_dir = run_dir_for(state)
            draft_dir = run_dir / "section_drafts"
            draft_dir.mkdir(parents=True, exist_ok=True)
            plan = {
                "figures": [{
                    "figure_id": "figrec_1",
                    "figure_type": "line",
                    "recommendation_id": "figrec_1",
                    "source_evidence_ids": ["E1"],
                    "chart_selection_reason": "The source frames these shares as a sequential allocation path.",
                    "title": "Share sequence",
                    "data": {"labels": ["Design", "Testing"], "series": [{"name": "Share", "values": [60, 40]}]},
                }]
            }

            report = audit_figure_plan(
                state,
                json.loads(Path(state.output["figure_recommendations_path"]).read_text(encoding="utf-8"))["recommendations"],
                plan,
                draft_dir / "figure_plan.json",
            )

            self.assertEqual(report["status"], "passed_with_warnings")
            self.assertEqual(report["issues"][0]["type"], "chart_type_mismatch")

    def test_audit_hard_blocks_non_list_figures(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            run_dir = run_dir_for(state)

            report = audit_figure_plan(
                state,
                [],
                {"figures": {"figure_id": "fig_1"}},
                run_dir / "section_drafts" / "figure_plan.json",
            )

            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["hard_issues"][0]["type"], "malformed_figure_plan")

    def test_audit_hard_blocks_non_object_figure_entry(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            run_dir = run_dir_for(state)

            report = audit_figure_plan(
                state,
                [],
                {"figures": ["fig_1"]},
                run_dir / "section_drafts" / "figure_plan.json",
            )

            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["hard_issues"][0]["type"], "malformed_figure_entry")

    def test_run_figure_recommend_writes_report_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            run_figure_recommend_with_composition_data(state)

            path = Path(state.output["figure_recommendations_path"])
            self.assertTrue(path.exists())
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["recommendation_count"], 1)


def run_figure_recommend_with_composition_data(state: ReportState) -> None:
    run_dir = run_dir_for(state)
    evidence_path = run_dir / "evidence_ledger.jsonl"
    evidence_path.write_text(json.dumps({
        "evidence_id": "E1",
        "source_id": "composition",
        "source_file_name": "composition.csv",
        "granularity": "table",
        "content": "Segment share distribution",
        "table_data": [
            ["Segment", "Share"],
            ["Design", "60"],
            ["Testing", "40"],
        ],
    }) + "\n", encoding="utf-8")
    state.sources["evidence_ledger_path"] = str(evidence_path)
    run_figure_recommend(state)


if __name__ == "__main__":
    unittest.main()
