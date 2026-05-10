import json
import tempfile
import unittest
from pathlib import Path

from report_workflow.errors import QAHardBlockError
from report_workflow.nodes.agent_tasks import write_agent_task_briefs
from report_workflow.nodes.figure_build import run_figure_build
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

    def test_non_composition_category_values_do_not_become_pie(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            evidence = [{
                "evidence_id": "E1",
                "source_id": "scores",
                "source_file_name": "scores.csv",
                "granularity": "table",
                "content": "Material score comparison",
                "table_data": [
                    ["Material", "Score"],
                    ["A", "60"],
                    ["B", "40"],
                ],
            }]

            recommendations = recommend_figures_from_evidence(state, evidence)

            self.assertEqual(recommendations[0]["recommended_figure_type"], "bar")
            self.assertEqual(recommendations[0]["data_profile"]["columns"][1]["role"], "numeric_measure")

    def test_recommendation_includes_profile_candidates_and_warnings(self):
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

            rec = recommend_figures_from_evidence(state, evidence)[0]

            self.assertIn("data_profile", rec)
            self.assertIn("chart_candidates", rec)
            self.assertIn("selection_warnings", rec)
            self.assertEqual(rec["chart_candidates"][0]["figure_type"], "pie")
            self.assertEqual(rec["data_profile"]["summary"]["composition_value_column_count"], 1)

    def test_numeric_id_and_measure_recommend_table_not_scatter_or_line(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            evidence = [{
                "evidence_id": "E1",
                "source_id": "samples",
                "source_file_name": "samples.csv",
                "granularity": "table",
                "content": "Voltage readings by sample identifier",
                "table_data": [
                    ["Sample ID", "Voltage"],
                    ["1", "1.2"],
                    ["2", "1.4"],
                    ["3", "1.6"],
                ],
            }]

            rec = recommend_figures_from_evidence(state, evidence)[0]

            self.assertEqual(rec["recommended_figure_type"], "table")
            self.assertEqual(rec["data_profile"]["columns"][0]["role"], "id_like")
            self.assertIn("ID-like numeric columns", rec["selection_warnings"][0])

    def test_two_numeric_measure_columns_recommend_scatter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            evidence = [{
                "evidence_id": "E1",
                "source_id": "measurements",
                "source_file_name": "measurements.csv",
                "granularity": "table",
                "content": "Measurement relationship",
                "table_data": [
                    ["Temperature", "Pressure", "Efficiency"],
                    ["20", "100", "0.72"],
                    ["25", "120", "0.76"],
                    ["30", "135", "0.81"],
                ],
            }]

            recommendations = recommend_figures_from_evidence(state, evidence)

            self.assertEqual(recommendations[0]["recommended_figure_type"], "scatter")
            self.assertEqual(recommendations[0]["data_profile"]["summary"]["numeric_column_count"], 3)

    def test_parameter_value_unit_table_stays_table(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            evidence = [{
                "evidence_id": "E1",
                "source_id": "constants",
                "source_file_name": "constants.csv",
                "granularity": "table",
                "content": "Calculation constants",
                "table_data": [
                    ["Parameter", "Value", "Unit"],
                    ["Length", "12", "cm"],
                    ["Mass", "4.2", "kg"],
                    ["Time", "3", "s"],
                ],
            }]

            rec = recommend_figures_from_evidence(state, evidence)[0]

            self.assertEqual(rec["recommended_figure_type"], "table")
            self.assertTrue(rec["data_profile"]["summary"]["parameter_table"])

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


class AutoFigurePlanTests(unittest.TestCase):
    def test_agent_tasks_writes_starter_figure_plan_from_recommendations(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            run_figure_recommend_with_composition_data(state)

            write_agent_task_briefs(state)

            plan_path = run_dir_for(state) / "section_drafts" / "figure_plan.json"
            self.assertTrue(plan_path.exists())
            payload = json.loads(plan_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["generated_by"], "report_workflow.nodes.agent_tasks.auto_figure_plan")
            self.assertEqual(payload["source_recommendations_path"], state.output["figure_recommendations_path"])
            self.assertEqual(payload["generated_figure_count"], 1)
            self.assertEqual(len(payload["figures"]), 1)
            figure = payload["figures"][0]
            self.assertEqual(figure["figure_id"], "figrec_1")
            self.assertEqual(figure["figure_type"], "pie")
            self.assertEqual(figure["recommendation_id"], "figrec_1")
            self.assertEqual(figure["source_evidence_ids"], ["E1"])
            self.assertIn("chart_selection_reason", figure)
            self.assertEqual(state.output["auto_figure_plan_path"], str(plan_path))
            self.assertEqual(state.plan["auto_figure_plan_count"], 1)

            outline_task = run_dir_for(state) / "agent_tasks" / "02_outline_plan.md"
            self.assertIn("Starter Figure Plan", outline_task.read_text(encoding="utf-8"))

    def test_agent_tasks_preserves_existing_figure_plan(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            run_figure_recommend_with_composition_data(state)
            plan_path = run_dir_for(state) / "section_drafts" / "figure_plan.json"
            plan_path.parent.mkdir(parents=True, exist_ok=True)
            original = json.dumps({
                "manual": True,
                "figures": [{
                    "figure_id": "manual_fig",
                    "figure_type": "bar",
                    "title": "Manual chart",
                    "data": {"labels": ["A"], "series": [{"name": "Value", "values": [1]}]},
                }],
            }, indent=2)
            plan_path.write_text(original, encoding="utf-8")

            write_agent_task_briefs(state)

            self.assertEqual(plan_path.read_text(encoding="utf-8"), original)
            self.assertEqual(state.runtime["auto_figure_plan"]["status"], "preserved_existing")

    def test_agent_tasks_skips_starter_plan_without_valid_recommendations(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            run_dir = run_dir_for(state)
            recommendations_path = run_dir / "figure_recommendations.json"
            recommendations_path.write_text(json.dumps({
                "recommendation_count": 1,
                "recommendations": [{
                    "recommendation_id": "figrec_1",
                    "recommended_figure_type": "bar",
                }],
            }), encoding="utf-8")
            state.output["figure_recommendations_path"] = str(recommendations_path)

            write_agent_task_briefs(state)

            plan_path = run_dir / "section_drafts" / "figure_plan.json"
            self.assertFalse(plan_path.exists())
            self.assertEqual(state.runtime["auto_figure_plan"]["status"], "skipped_no_valid_figure_plans")

    def test_agent_tasks_skips_starter_plan_without_recommendations(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)

            write_agent_task_briefs(state)

            plan_path = run_dir_for(state) / "section_drafts" / "figure_plan.json"
            self.assertFalse(plan_path.exists())
            self.assertEqual(state.runtime["auto_figure_plan"]["status"], "skipped_no_recommendations")

    def test_generated_starter_plan_passes_audit_and_build_read_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            run_figure_recommend_with_composition_data(state)
            write_agent_task_briefs(state)

            audited = run_figure_plan_audit(state)
            audit_path = Path(audited.qa["figure_plan_audit_report_path"])
            audit_report = json.loads(audit_path.read_text(encoding="utf-8"))
            self.assertEqual(audit_report["status"], "passed")
            self.assertEqual(audit_report["figure_count"], 1)

            try:
                import matplotlib  # noqa: F401
            except Exception as exc:
                self.skipTest(f"matplotlib is not available: {exc}")

            built = run_figure_build(state)
            manifest_path = Path(built.output["figure_manifest_path"])
            self.assertTrue(manifest_path.exists())
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["generated_count"], 1)
            self.assertEqual(manifest["error_count"], 0)
            self.assertEqual(manifest["figures"][0]["figure_id"], "figrec_1")


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
