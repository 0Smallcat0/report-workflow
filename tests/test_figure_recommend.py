import json
import tempfile
import unittest
from pathlib import Path

from report_workflow.errors import QAHardBlockError
from report_workflow.nodes.agent_tasks import write_agent_task_briefs
from report_workflow.nodes.figure_build import _figure_visual_quality_issues, run_figure_build
from report_workflow.nodes.figure_recommend import (
    MAX_TABLE_FIGURE_ROWS,
    recommend_figures_from_evidence,
    run_figure_recommend,
)
from report_workflow.nodes.figure_plan_audit import audit_figure_plan, run_figure_plan_audit
from report_workflow.state import ReportState, run_dir_for


def _state(tmpdir: str, profile: str = "engineering_lab_report") -> ReportState:
    state = ReportState.new("write report", [], str(Path(tmpdir) / "out"))
    state.spec["report_profile"] = profile
    state.plan["blueprint"] = {
        "sections": {"results": {}, "data": {}},
        "section_order": ["results", "data"],
    }
    return state


class HeaderTermMatchingTests(unittest.TestCase):
    """A Chinese header used to normalise to nothing before matching.

    `_header_contains` stripped everything outside `[a-z0-9%#]`, so 試次 became
    the empty string and matched no term at all — the same way `unit_signature`
    once lost CJK. A trial counter therefore never registered as an identifier,
    entered the measure candidates, and became a chart axis: serial number
    against a set point, with the measurement left off the plot.
    """

    def test_chinese_run_counters_are_identifiers(self):
        from report_workflow.nodes.figure_recommend import ID_HEADER_TERMS, _header_contains

        for header in ("試次", "試驗編號", "序號", "編號"):
            self.assertTrue(_header_contains(header, ID_HEADER_TERMS), header)

    def test_english_run_counters_are_identifiers(self):
        from report_workflow.nodes.figure_recommend import ID_HEADER_TERMS, _header_contains

        for header in ("Trial", "Trial No.", "Run ID", "Index"):
            self.assertTrue(_header_contains(header, ID_HEADER_TERMS), header)

    def test_measurements_are_not_identifiers(self):
        from report_workflow.nodes.figure_recommend import ID_HEADER_TERMS, _header_contains

        # 次數 is a count, which is a measurement; "Industrial" merely contains
        # "trial" and a Latin term keeps its word boundaries.
        for header in ("流量 (L/min)", "壓降 (kPa)", "次數", "Industrial Output", "不良率(%)"):
            self.assertFalse(_header_contains(header, ID_HEADER_TERMS), header)

    def test_a_run_counter_does_not_become_an_axis(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            recommendation = recommend_figures_from_evidence(state, [{
                "evidence_id": "E1", "source_id": "p", "source_file_name": "pressure.txt",
                "granularity": "table", "content": "pressure sweep",
                "table_data": [
                    ["試次", "流量", "壓降 (kPa)"],
                    ["1", "4", "12.4"], ["2", "8", "38.1"],
                    ["3", "10", "57.6"], ["4", "12", "79.2"],
                ],
            }])[0]
            plan = recommendation["figure_plan"]
            self.assertNotIn("試次", plan["xlabel"])
            self.assertNotIn("試次", plan["ylabel"])
            self.assertIn("壓降", plan["ylabel"])
            self.assertTrue(
                any("ID-like" in w for w in recommendation["selection_warnings"]),
                recommendation["selection_warnings"],
            )


class HeldConstantColumnTests(unittest.TestCase):
    """Controlled variables are constants, and a constant is not a relationship.

    Holding the two inlet temperatures fixed is standard experimental practice,
    so they sit in the file ahead of the columns the report is actually about.
    Positional axis selection used to plot the first of them and produce a
    scatter of six identical points.
    """

    TABLE = [
        ["流量 (L/min)", "冷側入口 (°C)", "冷側出口 (°C)", "實測有效度"],
        ["2", "25.0", "49.8", "0.709"],
        ["4", "25.0", "48.1", "0.660"],
        ["6", "25.0", "46.3", "0.609"],
        ["8", "25.0", "43.5", "0.529"],
        ["10", "25.0", "41.2", "0.463"],
        ["12", "25.0", "39.4", "0.411"],
    ]

    def _recommend(self, table_data):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            return recommend_figures_from_evidence(state, [{
                "evidence_id": "E1",
                "source_id": "phe",
                "source_file_name": "data.csv",
                "granularity": "table",
                "content": "heat exchanger effectiveness sweep",
                "table_data": table_data,
            }])

    def test_constant_column_is_never_an_axis(self):
        plan = self._recommend(self.TABLE)[0]["figure_plan"]
        self.assertNotIn("冷側入口", plan["ylabel"])
        self.assertNotIn("冷側入口", plan["xlabel"])
        self.assertGreater(len(set(plan["data"]["y"])), 1)

    def test_exclusion_is_reported_not_silent(self):
        warnings = self._recommend(self.TABLE)[0]["selection_warnings"]
        self.assertTrue(
            any("冷側入口 (°C)" in warning for warning in warnings),
            f"dropped column should be named in selection_warnings: {warnings}",
        )

    def test_all_constant_measures_fall_back_instead_of_vanishing(self):
        flat = [
            ["設定點", "讀值 A", "讀值 B"],
            ["1", "25.0", "60.0"],
            ["2", "25.0", "60.0"],
            ["3", "25.0", "60.0"],
            ["4", "25.0", "60.0"],
        ]
        self.assertTrue(self._recommend(flat))


class MonthlyTrendChartTests(unittest.TestCase):
    """A monthly table carrying one "%" column is a trend, not a composition."""

    TABLE = [
        ["月份", "投產數", "不良數", "不良率(%)", "主要不良類型"],
        ["2026-01", "12480", "312", "2.50", "尺寸超差"],
        ["2026-02", "10260", "267", "2.60", "尺寸超差"],
        ["2026-03", "13150", "382", "2.90", "尺寸超差"],
        ["2026-04", "12890", "425", "3.30", "尺寸超差"],
        ["2026-07", "13080", "275", "2.10", "表面刮傷"],
    ]

    def _recommend(self, table_data):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            return recommend_figures_from_evidence(state, [{
                "evidence_id": "E1",
                "source_id": "defects",
                "source_file_name": "defects.csv",
                "granularity": "table",
                "content": "monthly defect rate",
                "table_data": table_data,
            }])

    def test_ordered_time_column_is_not_stacked(self):
        recommendation = self._recommend(self.TABLE)[0]
        self.assertNotEqual(recommendation["recommended_figure_type"], "stacked_bar")

    def test_counts_beside_a_percentage_count_as_mixed_units(self):
        recommendation = self._recommend(self.TABLE)[0]
        self.assertTrue(
            recommendation["data_profile"]["summary"]["mixed_measure_units"]
        )
        self.assertEqual(recommendation["recommended_figure_type"], "table")

    def test_single_unit_trend_still_charts_as_a_line(self):
        single_unit = [[row[0], row[3]] for row in self.TABLE]
        recommendation = self._recommend(single_unit)[0]
        self.assertFalse(
            recommendation["data_profile"]["summary"]["mixed_measure_units"]
        )
        self.assertEqual(recommendation["recommended_figure_type"], "line")


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

            # The point of this test is the grouping: three csv_row units from
            # one file become a single recommendation carrying all three ids.
            self.assertEqual(len(recommendations), 1)
            self.assertEqual(recommendations[0]["evidence_ids"], ["E1", "E2", "E3"])
            # "Trial" is a run counter, and the selection rules say ID-like
            # numeric columns are excluded from trend and relationship charts.
            # It used to slip through the English-only term list and serve as an
            # axis; with it excluded only Voltage remains, and one measure with
            # nothing to plot it against stays a table.
            self.assertEqual(recommendations[0]["recommended_figure_type"], "table")

    def test_recommends_histogram_for_single_numeric_distribution(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            evidence = [{
                "evidence_id": "E1",
                "source_id": "measurements",
                "source_file_name": "measurements.csv",
                "granularity": "table",
                "content": "Measurement distribution across observations",
                "table_data": [["Reading"]] + [[str(value)] for value in [10, 11, 12, 11, 13, 14, 13, 12, 15, 16]],
            }]

            rec = recommend_figures_from_evidence(state, evidence)[0]

            self.assertEqual(rec["recommended_figure_type"], "histogram")
            self.assertEqual(rec["figure_plan"]["data"]["values"][0], 10)
            self.assertIn("histogram", rec["acceptable_figure_types"])

    def test_recommends_boxplot_for_grouped_repeated_measurements(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            evidence = [{
                "evidence_id": "E1",
                "source_id": "groups",
                "source_file_name": "groups.csv",
                "granularity": "table",
                "content": "Replicate measurement distribution by material",
                "table_data": [
                    ["Material", "Strength"],
                    ["A", "12"],
                    ["A", "14"],
                    ["A", "13"],
                    ["B", "18"],
                    ["B", "19"],
                    ["B", "17"],
                ],
            }]

            rec = recommend_figures_from_evidence(state, evidence)[0]

            self.assertEqual(rec["recommended_figure_type"], "boxplot")
            self.assertEqual([series["name"] for series in rec["figure_plan"]["data"]["series"]], ["A", "B"])

    def test_recommends_heatmap_for_matrix_shaped_table(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            evidence = [{
                "evidence_id": "E1",
                "source_id": "matrix",
                "source_file_name": "matrix.csv",
                "granularity": "table",
                "content": "Correlation matrix values",
                "table_data": [
                    ["Metric", "A", "B", "C"],
                    ["A", "1.0", "0.4", "0.2"],
                    ["B", "0.4", "1.0", "0.7"],
                    ["C", "0.2", "0.7", "1.0"],
                ],
            }]

            rec = recommend_figures_from_evidence(state, evidence)[0]

            self.assertEqual(rec["recommended_figure_type"], "heatmap")
            self.assertEqual(rec["figure_plan"]["data"]["x_labels"], ["A", "B", "C"])
            self.assertEqual(rec["figure_plan"]["data"]["y_labels"], ["A", "B", "C"])

    def test_recommends_error_bar_for_value_with_uncertainty_column(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            evidence = [{
                "evidence_id": "E1",
                "source_id": "uncertainty",
                "source_file_name": "uncertainty.csv",
                "granularity": "table",
                "content": "Mean response with standard deviation",
                "table_data": [
                    ["Sample", "Mean", "SD"],
                    ["A", "10.2", "0.4"],
                    ["B", "11.8", "0.7"],
                    ["C", "9.9", "0.3"],
                ],
            }]

            rec = recommend_figures_from_evidence(state, evidence)[0]

            self.assertEqual(rec["recommended_figure_type"], "error_bar")
            series = rec["figure_plan"]["data"]["series"][0]
            self.assertEqual(series["values"], [10.2, 11.8, 9.9])
            self.assertEqual(series["errors"], [0.4, 0.7, 0.3])

    def test_recommends_stacked_bar_for_composition_breakdown_series(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            evidence = [{
                "evidence_id": "E1",
                "source_id": "allocation",
                "source_file_name": "allocation.csv",
                "granularity": "table",
                "content": "Budget allocation breakdown share by phase",
                "table_data": [
                    ["Phase", "Design", "Build", "Test"],
                    ["Q1", "40", "35", "25"],
                    ["Q2", "20", "50", "30"],
                    ["Q3", "30", "45", "25"],
                ],
            }]

            rec = recommend_figures_from_evidence(state, evidence)[0]

            self.assertEqual(rec["recommended_figure_type"], "stacked_bar")
            self.assertIn("bar", rec["acceptable_figure_types"])
            self.assertEqual(len(rec["figure_plan"]["data"]["series"]), 3)

    def test_distribution_language_without_composition_does_not_recommend_stacked_bar(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            evidence = [{
                "evidence_id": "E1",
                "source_id": "distribution",
                "source_file_name": "distribution.csv",
                "granularity": "table",
                "content": "Score distribution by material and test condition",
                "table_data": [
                    ["Material", "Strength", "Elasticity"],
                    ["A", "12", "4"],
                    ["B", "18", "6"],
                    ["C", "16", "5"],
                ],
            }]

            rec = recommend_figures_from_evidence(state, evidence)[0]

            self.assertEqual(rec["recommended_figure_type"], "bar")
            self.assertNotEqual(rec["figure_plan"]["figure_type"], "stacked_bar")

    def test_group_by_sum_transform_for_duplicate_additive_categories(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            evidence = [{
                "evidence_id": "E1",
                "source_id": "regional_sales",
                "source_file_name": "regional_sales.csv",
                "granularity": "table",
                "content": "Regional sales count by region",
                "table_data": [
                    ["Region", "Sales count"],
                    ["North", "10"],
                    ["North", "15"],
                    ["South", "8"],
                ],
            }]

            rec = recommend_figures_from_evidence(state, evidence)[0]

            self.assertEqual(rec["recommended_figure_type"], "bar")
            self.assertEqual(rec["data_transform"]["status"], "transformed")
            self.assertIn("group_by_sum", rec["data_transform"]["operations"])
            self.assertEqual(rec["figure_plan"]["data"]["labels"], ["North", "South"])
            self.assertEqual(rec["figure_plan"]["data"]["series"][0]["values"], [25.0, 8.0])
            self.assertEqual(rec["figure_plan"]["data_transform"]["source_evidence_ids"], ["E1"])

    def test_long_key_series_value_table_pivots_before_chart_selection(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            evidence = [{
                "evidence_id": "E1",
                "source_id": "monthly_sales",
                "source_file_name": "monthly_sales.csv",
                "granularity": "table",
                "content": "Sales amount by month and segment",
                "table_data": [
                    ["Month", "Segment", "Sales"],
                    ["2026-01", "A", "10"],
                    ["2026-01", "B", "5"],
                    ["2026-02", "A", "12"],
                    ["2026-02", "B", "7"],
                ],
            }]

            rec = recommend_figures_from_evidence(state, evidence)[0]

            self.assertEqual(rec["recommended_figure_type"], "line")
            self.assertIn("pivot", rec["data_transform"]["operations"])
            self.assertEqual(rec["figure_plan"]["data"]["labels"], ["2026-01", "2026-02"])
            self.assertEqual([series["name"] for series in rec["figure_plan"]["data"]["series"]], ["A", "B"])
            self.assertEqual(rec["figure_plan"]["data"]["series"][1]["values"], [5.0, 7.0])

    def test_wide_time_columns_become_line_series(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            evidence = [{
                "evidence_id": "E1",
                "source_id": "wide_years",
                "source_file_name": "wide_years.csv",
                "granularity": "table",
                "content": "Revenue and cost by year",
                "table_data": [
                    ["Metric", "2024", "2025", "2026"],
                    ["Revenue", "10", "12", "15"],
                    ["Cost", "7", "8", "9"],
                ],
            }]

            rec = recommend_figures_from_evidence(state, evidence)[0]

            self.assertEqual(rec["recommended_figure_type"], "line")
            self.assertIn("wide_to_long", rec["data_transform"]["operations"])
            self.assertEqual(rec["figure_plan"]["data"]["labels"], ["2024", "2025", "2026"])
            self.assertEqual([series["name"] for series in rec["figure_plan"]["data"]["series"]], ["Revenue", "Cost"])

    def test_composition_counts_normalize_to_percent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            evidence = [{
                "evidence_id": "E1",
                "source_id": "composition_counts",
                "source_file_name": "composition_counts.csv",
                "granularity": "table",
                "content": "Response composition by segment",
                "table_data": [
                    ["Segment", "Responses"],
                    ["A", "3"],
                    ["B", "7"],
                ],
            }]

            rec = recommend_figures_from_evidence(state, evidence)[0]

            self.assertEqual(rec["recommended_figure_type"], "pie")
            self.assertIn("normalize_percent", rec["data_transform"]["operations"])
            self.assertEqual(rec["figure_plan"]["data"]["series"][0]["values"], [30.0, 70.0])
            self.assertIn("%", rec["figure_plan"]["ylabel"])
            self.assertIn("Data were deterministically transformed", rec["figure_plan"]["chart_selection_reason"])

    def test_fraction_composition_scales_to_percent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            evidence = [{
                "evidence_id": "E1",
                "source_id": "fraction_share",
                "source_file_name": "fraction_share.csv",
                "granularity": "table",
                "content": "Segment share distribution",
                "table_data": [
                    ["Segment", "Share"],
                    ["Design", "0.3"],
                    ["Testing", "0.7"],
                ],
            }]

            rec = recommend_figures_from_evidence(state, evidence)[0]

            self.assertEqual(rec["recommended_figure_type"], "pie")
            self.assertIn("scale_fraction_to_percent", rec["data_transform"]["operations"])
            self.assertEqual(rec["figure_plan"]["data"]["series"][0]["values"], [30.0, 70.0])
            self.assertEqual(rec["data_transform"]["percent_scale"]["input_scale"], "fraction_0_1")

    def test_percent_composition_does_not_double_normalize(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            evidence = [{
                "evidence_id": "E1",
                "source_id": "percent_share",
                "source_file_name": "percent_share.csv",
                "granularity": "table",
                "content": "Segment share percentage",
                "table_data": [
                    ["Segment", "Share (%)"],
                    ["Design", "30"],
                    ["Testing", "70"],
                ],
            }]

            rec = recommend_figures_from_evidence(state, evidence)[0]

            self.assertEqual(rec["recommended_figure_type"], "pie")
            self.assertNotIn("normalize_percent", rec["data_transform"]["operations"])
            self.assertNotIn("scale_fraction_to_percent", rec["data_transform"]["operations"])
            self.assertEqual(rec["figure_plan"]["data"]["series"][0]["values"], [30, 70])

    def test_negative_composition_values_do_not_recommend_pie(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            evidence = [{
                "evidence_id": "E1",
                "source_id": "negative_share",
                "source_file_name": "negative_share.csv",
                "granularity": "table",
                "content": "Segment share distribution",
                "table_data": [
                    ["Segment", "Share"],
                    ["Gain", "120"],
                    ["Loss", "-20"],
                ],
            }]

            rec = recommend_figures_from_evidence(state, evidence)[0]

            self.assertNotEqual(rec["recommended_figure_type"], "pie")
            self.assertIn("negative", " ".join(rec["selection_warnings"]).lower())

    def test_negative_stacked_parts_do_not_recommend_stacked_bar(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            evidence = [{
                "evidence_id": "E1",
                "source_id": "mixed_parts",
                "source_file_name": "mixed_parts.csv",
                "granularity": "table",
                "content": "Allocation breakdown by phase",
                "table_data": [
                    ["Phase", "Revenue", "Adjustment"],
                    ["Q1", "100", "-20"],
                    ["Q2", "80", "10"],
                ],
            }]

            rec = recommend_figures_from_evidence(state, evidence)[0]

            self.assertNotEqual(rec["recommended_figure_type"], "stacked_bar")
            self.assertIn("negative", " ".join(rec["selection_warnings"]).lower())

    def test_mixed_unit_series_recommends_table(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            evidence = [{
                "evidence_id": "E1",
                "source_id": "mixed_units",
                "source_file_name": "mixed_units.csv",
                "granularity": "table",
                "content": "Voltage and current by condition",
                "table_data": [
                    ["Condition", "Voltage (V)", "Current (A)"],
                    ["Idle", "5", "0.2"],
                    ["Load", "4.8", "0.5"],
                ],
            }]

            rec = recommend_figures_from_evidence(state, evidence)[0]

            self.assertEqual(rec["recommended_figure_type"], "table")
            self.assertTrue(rec["data_profile"]["summary"]["mixed_measure_units"])
            self.assertIn("mixed units", rec["reason"].lower())

    def test_large_mixed_unit_time_series_recommends_table(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            rows = [["Date", "Voltage (V)", "Current (A)"]]
            rows.extend([
                [f"2026-01-{index:02d}", str(4.5 + index / 10), str(0.1 + index / 100)]
                for index in range(1, 15)
            ])
            evidence = [{
                "evidence_id": "E1",
                "source_id": "mixed_units_long",
                "source_file_name": "mixed_units_long.csv",
                "granularity": "table",
                "content": "Voltage and current by date",
                "table_data": rows,
            }]

            rec = recommend_figures_from_evidence(state, evidence)[0]

            self.assertEqual(rec["recommended_figure_type"], "table")
            self.assertTrue(rec["data_profile"]["summary"]["mixed_measure_units"])
            self.assertEqual(len(rec["figure_plan"]["data"]["rows"]), MAX_TABLE_FIGURE_ROWS)
            self.assertIn("sharing one y-axis", rec["reason"])

    def test_unsorted_iso_dates_are_sorted_for_line_chart(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            evidence = [{
                "evidence_id": "E1",
                "source_id": "dates",
                "source_file_name": "dates.csv",
                "granularity": "table",
                "content": "Temperature by date",
                "table_data": [
                    ["Date", "Temperature (C)"],
                    ["2026-03-01", "22"],
                    ["2026-01-01", "18"],
                    ["2026-02-01", "20"],
                ],
            }]

            rec = recommend_figures_from_evidence(state, evidence)[0]

            self.assertEqual(rec["recommended_figure_type"], "line")
            self.assertIn("sort_time_asc", rec["data_transform"]["operations"])
            self.assertEqual(rec["figure_plan"]["data"]["labels"], ["2026-01-01", "2026-02-01", "2026-03-01"])

    def test_month_labels_are_sorted_for_line_chart(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            evidence = [{
                "evidence_id": "E1",
                "source_id": "months",
                "source_file_name": "months.csv",
                "granularity": "table",
                "content": "Temperature by month",
                "table_data": [
                    ["Month", "Temperature (C)"],
                    ["Mar", "22"],
                    ["Jan", "18"],
                    ["February", "20"],
                ],
            }]

            rec = recommend_figures_from_evidence(state, evidence)[0]

            self.assertEqual(rec["recommended_figure_type"], "line")
            self.assertIn("sort_time_asc", rec["data_transform"]["operations"])
            self.assertEqual(rec["figure_plan"]["data"]["labels"], ["Jan", "February", "Mar"])

    def test_month_year_labels_are_sorted_for_line_chart(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            evidence = [{
                "evidence_id": "E1",
                "source_id": "month_year",
                "source_file_name": "month_year.csv",
                "granularity": "table",
                "content": "Temperature by month",
                "table_data": [
                    ["Month", "Temperature (C)"],
                    ["Jan 2026", "18"],
                    ["Dec 2025", "16"],
                    ["Feb-26", "20"],
                ],
            }]

            rec = recommend_figures_from_evidence(state, evidence)[0]

            self.assertEqual(rec["recommended_figure_type"], "line")
            self.assertIn("sort_time_asc", rec["data_transform"]["operations"])
            self.assertEqual(rec["figure_plan"]["data"]["labels"], ["Dec 2025", "Jan 2026", "Feb-26"])

    def test_ambiguous_dates_are_not_sorted_and_warn(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            evidence = [{
                "evidence_id": "E1",
                "source_id": "ambiguous_dates",
                "source_file_name": "ambiguous_dates.csv",
                "granularity": "table",
                "content": "Temperature by date",
                "table_data": [
                    ["Date", "Temperature (C)"],
                    ["03/01/26", "22"],
                    ["01/01/26", "18"],
                    ["02/01/26", "20"],
                ],
            }]

            rec = recommend_figures_from_evidence(state, evidence)[0]

            self.assertEqual(rec["recommended_figure_type"], "table")
            self.assertNotIn("sort_time_asc", rec["data_transform"]["operations"])
            self.assertIn("date", " ".join(rec["selection_warnings"]).lower())

    def test_large_ambiguous_dates_recommend_table(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            rows = [["Date", "Temperature (C)"]]
            rows.extend([[f"{index:02d}/01/26", str(18 + index)] for index in range(1, 14)])
            evidence = [{
                "evidence_id": "E1",
                "source_id": "ambiguous_dates_long",
                "source_file_name": "ambiguous_dates_long.csv",
                "granularity": "table",
                "content": "Temperature by date",
                "table_data": rows,
            }]

            rec = recommend_figures_from_evidence(state, evidence)[0]

            self.assertEqual(rec["recommended_figure_type"], "table")
            self.assertEqual(len(rec["figure_plan"]["data"]["rows"]), MAX_TABLE_FIGURE_ROWS)
            self.assertIn("date", " ".join(rec["selection_warnings"]).lower())

    def test_large_category_table_uses_sorted_top_n_with_other_bucket(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            rows = [["Category", "Sales"]] + [[f"C{index}", str(15 - index)] for index in range(1, 15)]
            evidence = [{
                "evidence_id": "E1",
                "source_id": "category_sales",
                "source_file_name": "category_sales.csv",
                "granularity": "table",
                "content": "Sales amount by category",
                "table_data": rows,
            }]

            rec = recommend_figures_from_evidence(state, evidence)[0]

            labels = rec["figure_plan"]["data"]["labels"]
            values = rec["figure_plan"]["data"]["series"][0]["values"]
            self.assertEqual(rec["recommended_figure_type"], "bar")
            self.assertEqual(rec["data_transform"]["operations"], ["sort_desc", "top_n"])
            self.assertEqual(len(labels), 12)
            self.assertEqual(labels[-1], "Other")
            self.assertEqual(values[:3], [14.0, 13.0, 12.0])
            self.assertEqual(values[-1], 6.0)

    def test_large_stacked_bar_top_n_other_bucket_preserves_each_series(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            rows = [["Category", "A amount", "B amount"]] + [
                [f"C{index}", str(20 - index), str(index)]
                for index in range(1, 15)
            ]
            evidence = [{
                "evidence_id": "E1",
                "source_id": "allocation",
                "source_file_name": "allocation.csv",
                "granularity": "table",
                "content": "Allocation breakdown amount by category",
                "table_data": rows,
            }]

            rec = recommend_figures_from_evidence(state, evidence)[0]

            self.assertEqual(rec["recommended_figure_type"], "stacked_bar")
            self.assertEqual(rec["data_transform"]["operations"], ["sort_desc", "top_n"])
            labels = rec["figure_plan"]["data"]["labels"]
            series = rec["figure_plan"]["data"]["series"]
            self.assertEqual(labels[-1], "Other")
            self.assertEqual(series[0]["values"][-1], 21.0)
            self.assertEqual(series[1]["values"][-1], 39.0)
            self.assertEqual(sum(series[0]["values"]), sum(20 - index for index in range(1, 15)))
            self.assertEqual(sum(series[1]["values"]), sum(range(1, 15)))

    def test_large_response_composition_top_n_keeps_other_bucket(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            values = [200, 180, 160, 140, 120, 80, 50, 30, 20, 10, 5, 3, 1, 1]
            rows = [["Segment", "Responses"]] + [[f"S{index}", str(value)] for index, value in enumerate(values, 1)]
            evidence = [{
                "evidence_id": "E1",
                "source_id": "response_composition",
                "source_file_name": "response_composition.csv",
                "granularity": "table",
                "content": "Response composition by segment",
                "table_data": rows,
            }]

            rec = recommend_figures_from_evidence(state, evidence)[0]

            labels = rec["figure_plan"]["data"]["labels"]
            chart_values = rec["figure_plan"]["data"]["series"][0]["values"]
            self.assertEqual(rec["recommended_figure_type"], "pie")
            self.assertEqual(rec["data_transform"]["operations"], ["normalize_percent", "sort_desc", "top_n"])
            self.assertEqual(len(labels), 6)
            self.assertEqual(labels[-1], "Other")
            self.assertAlmostEqual(sum(chart_values), 100.0, places=5)

    def test_non_additive_repeated_measurements_do_not_group_by_sum(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            evidence = [{
                "evidence_id": "E1",
                "source_id": "strength",
                "source_file_name": "strength.csv",
                "granularity": "table",
                "content": "Replicate measurement distribution by material",
                "table_data": [
                    ["Material", "Strength"],
                    ["A", "12"],
                    ["A", "14"],
                    ["B", "18"],
                    ["B", "19"],
                ],
            }]

            rec = recommend_figures_from_evidence(state, evidence)[0]

            self.assertEqual(rec["recommended_figure_type"], "boxplot")
            self.assertEqual(rec["data_transform"]["status"], "source")
            self.assertNotIn("group_by_sum", rec["data_transform"]["operations"])

    def test_non_additive_score_summary_does_not_match_sum_term(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            evidence = [{
                "evidence_id": "E1",
                "source_id": "score_summary",
                "source_file_name": "score_summary.csv",
                "granularity": "table",
                "content": "Score summary by group",
                "table_data": [
                    ["Group", "Score"],
                    ["A", "4"],
                    ["A", "5"],
                    ["B", "7"],
                    ["B", "8"],
                ],
            }]

            rec = recommend_figures_from_evidence(state, evidence)[0]

            self.assertEqual(rec["recommended_figure_type"], "boxplot")
            self.assertEqual(rec["data_transform"]["status"], "source")
            self.assertNotIn("group_by_sum", rec["data_transform"]["operations"])


class HumanFigureTitleTests(unittest.TestCase):
    def test_title_uses_series_and_axis_labels(self):
        from report_workflow.nodes.figure_recommend import _human_figure_title
        title = _human_figure_title(
            "bar", "Effort hours", "Phase",
            {"series": [{"name": "Effort hours", "values": [1.0]}]},
            "chart_source.csv", "",
        )
        self.assertEqual(title, "Effort hours by Phase")

    def test_title_chinese_labels_use_chinese_grouping(self):
        from report_workflow.nodes.figure_recommend import _human_figure_title
        title = _human_figure_title(
            "bar", "誤報率 (%)", "階段",
            {"series": [{"name": "誤報率 (%)", "values": [18.0, 5.0]}]},
            "效能數據.csv", "",
        )
        self.assertEqual(title, "誤報率 (%)(依階段)")

    def test_title_falls_back_to_source_stem_without_labels(self):
        from report_workflow.nodes.figure_recommend import _human_figure_title
        title = _human_figure_title("bar", "", "", {}, "chart_source.csv", "")
        self.assertEqual(title, "Bar view of chart_source")


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
            self.assertEqual(figure["figure_id"], "1")
            self.assertEqual(figure["figure_type"], "pie")
            self.assertEqual(figure["recommendation_id"], "figrec_1")
            self.assertEqual(figure["source_evidence_ids"], ["E1"])
            self.assertIn("chart_selection_reason", figure)
            self.assertEqual(state.output["auto_figure_plan_path"], str(plan_path))
            self.assertEqual(state.plan["auto_figure_plan_count"], 1)

            outline_task = run_dir_for(state) / "agent_tasks" / "02_outline_plan.md"
            outline_text = outline_task.read_text(encoding="utf-8")
            self.assertIn("Starter Figure Plan", outline_text)
            self.assertIn("Recommended Figure Usage Map", outline_text)
            self.assertIn("sections.results.figure_ids", outline_text)
            self.assertIn("[FIGURE:1]", outline_text)

            section_task = run_dir_for(state) / "agent_tasks" / "03_section_draft.md"
            section_text = section_task.read_text(encoding="utf-8")
            self.assertIn("Recommended figure usage map", section_text)
            self.assertIn("evidence `E1`", section_text)

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
            self.assertEqual(manifest["figures"][0]["figure_id"], "1")


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

    def test_audit_reports_chart_readability_warnings(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            run_figure_recommend_with_composition_data(state)
            recommendations = json.loads(
                Path(state.output["figure_recommendations_path"]).read_text(encoding="utf-8")
            )["recommendations"]
            labels = [
                f"Very long category label that should be shortened {index}"
                for index in range(13)
            ]
            plan = {
                "figures": [
                    {
                        "figure_id": "figrec_1",
                        "figure_type": "bar",
                        "recommendation_id": "figrec_1",
                        "source_evidence_ids": ["E1"],
                        "title": "Chart Title",
                        "xlabel": "",
                        "ylabel": "Metric",
                        "data": {
                            "labels": labels,
                            "series": [
                                {"name": "Series 1", "values": list(range(13))},
                                {"name": "Series 2", "values": list(range(13))},
                                {"name": "Series 3", "values": list(range(13))},
                                {"name": "Series 4", "values": list(range(13))},
                            ],
                        },
                    },
                    {
                        "figure_id": "manual_pie",
                        "figure_type": "pie",
                        "chart_selection_reason": "Manual composition comparison.",
                        "title": "Segment split",
                        "data": {
                            "labels": [f"S{index}" for index in range(7)],
                            "series": [{"name": "Share", "values": [1, 1, 1, 1, 1, 1, 1]}],
                        },
                    },
                ]
            }

            report = audit_figure_plan(
                state,
                recommendations,
                plan,
                run_dir_for(state) / "section_drafts" / "figure_plan.json",
            )

            issue_types = {issue["type"] for issue in report["issues"]}
            self.assertEqual(report["status"], "passed_with_warnings")
            self.assertIn("missing_chart_title", issue_types)
            self.assertIn("missing_axis_label", issue_types)
            self.assertIn("unit_label_unclear", issue_types)
            self.assertIn("legend_label_missing", issue_types)
            self.assertIn("category_labels_too_long", issue_types)
            self.assertIn("too_many_categories", issue_types)
            self.assertIn("too_many_data_points", issue_types)
            self.assertIn("pie_too_many_categories", issue_types)

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

    def test_audit_hard_blocks_negative_pie_values(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir, profile="custom")
            run_dir = run_dir_for(state)
            plan = {
                "figures": [{
                    "figure_id": "bad_pie",
                    "figure_type": "pie",
                    "chart_selection_reason": "Manual signed composition.",
                    "title": "Signed share",
                    "data": {
                        "labels": ["Gain", "Loss"],
                        "series": [{"name": "Share", "values": [120, -20]}],
                    },
                }]
            }

            report = audit_figure_plan(state, [], plan, run_dir / "section_drafts" / "figure_plan.json")

            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["hard_issues"][0]["type"], "negative_composition_values")

    def test_audit_hard_blocks_negative_stacked_bar_values(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir, profile="custom")
            run_dir = run_dir_for(state)
            plan = {
                "figures": [{
                    "figure_id": "bad_stack",
                    "figure_type": "stacked_bar",
                    "chart_selection_reason": "Manual signed stack.",
                    "title": "Signed components",
                    "xlabel": "Quarter",
                    "ylabel": "Share percent",
                    "data": {
                        "labels": ["Q1", "Q2"],
                        "series": [
                            {"name": "Positive", "values": [80, 90]},
                            {"name": "Negative", "values": [-10, -20]},
                        ],
                    },
                }]
            }

            report = audit_figure_plan(state, [], plan, run_dir / "section_drafts" / "figure_plan.json")

            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["hard_issues"][0]["type"], "negative_composition_values")

    def test_audit_accepts_supported_new_figure_types(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            run_dir = run_dir_for(state)
            plan = {
                "figures": [
                    {
                        "figure_id": "hist",
                        "figure_type": "histogram",
                        "chart_selection_reason": "Distribution view.",
                        "title": "Reading distribution",
                        "xlabel": "Reading",
                        "ylabel": "Frequency count",
                        "data": {"values": [1, 2, 2, 3, 4, 4, 5]},
                    },
                    {
                        "figure_id": "box",
                        "figure_type": "boxplot",
                        "chart_selection_reason": "Grouped spread view.",
                        "title": "Strength spread",
                        "xlabel": "Material",
                        "ylabel": "Strength value",
                        "data": {"series": [{"name": "A", "values": [1, 2, 3]}, {"name": "B", "values": [2, 3, 4]}]},
                    },
                    {
                        "figure_id": "heat",
                        "figure_type": "heatmap",
                        "chart_selection_reason": "Matrix intensity view.",
                        "title": "Correlation matrix",
                        "xlabel": "Column",
                        "ylabel": "Row",
                        "data": {"x_labels": ["A", "B"], "y_labels": ["A", "B"], "values": [[1, 0.2], [0.2, 1]]},
                    },
                    {
                        "figure_id": "err",
                        "figure_type": "error_bar",
                        "chart_selection_reason": "Uncertainty view.",
                        "title": "Mean with SD",
                        "xlabel": "Sample",
                        "ylabel": "Mean value",
                        "data": {"labels": ["A", "B"], "series": [{"name": "Mean", "values": [1, 2], "errors": [0.1, 0.2]}]},
                    },
                    {
                        "figure_id": "stack",
                        "figure_type": "stacked_bar",
                        "chart_selection_reason": "Composition view.",
                        "title": "Phase allocation",
                        "xlabel": "Phase",
                        "ylabel": "Share percent",
                        "data": {
                            "labels": ["Q1", "Q2"],
                            "series": [{"name": "A", "values": [40, 30]}, {"name": "B", "values": [60, 70]}],
                        },
                    },
                ]
            }

            report = audit_figure_plan(state, [], plan, run_dir / "section_drafts" / "figure_plan.json")

            self.assertEqual(report["hard_issues"], [])

    def test_audit_uses_stacked_bar_specific_series_limit(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            run_dir = run_dir_for(state)
            series = [
                {"name": "A", "values": [10, 20]},
                {"name": "B", "values": [20, 30]},
                {"name": "C", "values": [30, 20]},
                {"name": "D", "values": [40, 30]},
            ]
            report = audit_figure_plan(
                state,
                [],
                {
                    "figures": [{
                        "figure_id": "stack",
                        "figure_type": "stacked_bar",
                        "chart_selection_reason": "Composition view.",
                        "title": "Phase allocation",
                        "xlabel": "Phase",
                        "ylabel": "Share (%)",
                        "data": {"labels": ["Q1", "Q2"], "series": series},
                    }]
                },
                run_dir / "section_drafts" / "figure_plan.json",
            )

            self.assertEqual(report["hard_issues"], [])
            self.assertFalse(
                any(
                    issue.get("type") == "too_many_data_points" and issue.get("threshold") == 3
                    for issue in report["issues"]
                )
            )

    def test_audit_accepts_transformed_starter_plan(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            run_dir = run_dir_for(state)
            evidence_path = run_dir / "evidence_ledger.jsonl"
            evidence_path.write_text(json.dumps({
                "evidence_id": "E1",
                "source_id": "regional_sales",
                "source_file_name": "regional_sales.csv",
                "granularity": "table",
                "content": "Regional sales count by region",
                "table_data": [
                    ["Region", "Sales count"],
                    ["North", "10"],
                    ["North", "15"],
                    ["South", "8"],
                ],
            }) + "\n", encoding="utf-8")
            state.sources["evidence_ledger_path"] = str(evidence_path)
            run_figure_recommend(state)
            write_agent_task_briefs(state)

            audited = run_figure_plan_audit(state)
            report = json.loads(Path(audited.qa["figure_plan_audit_report_path"]).read_text(encoding="utf-8"))

            self.assertEqual(report["hard_issues"], [])
            self.assertEqual(report["status"], "passed")

    def test_audit_warns_when_transformed_plan_metadata_is_removed(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            evidence = [{
                "evidence_id": "E1",
                "source_id": "regional_sales",
                "source_file_name": "regional_sales.csv",
                "granularity": "table",
                "content": "Regional sales amount by region",
                "table_data": [
                    ["Region", "Sales"],
                    ["North", "10"],
                    ["North", "15"],
                    ["South", "8"],
                ],
            }]
            rec = recommend_figures_from_evidence(state, evidence)[0]
            plan = {
                "figures": [{
                    "figure_id": rec["figure_plan"]["figure_id"],
                    "figure_type": rec["figure_plan"]["figure_type"],
                    "recommendation_id": rec["recommendation_id"],
                    "source_evidence_ids": ["E1"],
                    "title": rec["figure_plan"]["title"],
                    "xlabel": rec["figure_plan"]["xlabel"],
                    "ylabel": rec["figure_plan"]["ylabel"],
                    "data": rec["figure_plan"]["data"],
                }]
            }

            report = audit_figure_plan(state, [rec], plan, run_dir_for(state) / "section_drafts" / "figure_plan.json")

            self.assertEqual(report["hard_issues"], [])
            self.assertIn(
                "transformed_recommendation_without_provenance",
                {issue["type"] for issue in report["issues"]},
            )

    def test_audit_hard_blocks_unsupported_figure_type(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            run_dir = run_dir_for(state)

            report = audit_figure_plan(
                state,
                [],
                {"figures": [{"figure_id": "bad", "figure_type": "radar", "data": {}}]},
                run_dir / "section_drafts" / "figure_plan.json",
            )

            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["hard_issues"][0]["type"], "unsupported_figure_type")

    def test_audit_hard_blocks_unsupported_output_format(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            run_dir = run_dir_for(state)

            report = audit_figure_plan(
                state,
                [],
                {
                    "figures": [{
                        "figure_id": "bad_format",
                        "figure_type": "bar",
                        "output_format": "pdf",
                        "data": {"labels": ["A", "B"], "series": [{"name": "Value", "values": [1, 2]}]},
                    }]
                },
                run_dir / "section_drafts" / "figure_plan.json",
            )

            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["hard_issues"][0]["type"], "unsupported_output_format")

    def test_audit_hard_blocks_unexplained_mixed_unit_multi_series(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            run_dir = run_dir_for(state)

            report = audit_figure_plan(
                state,
                [],
                {
                    "figures": [{
                        "figure_id": "mixed_units",
                        "figure_type": "bar",
                        "chart_selection_reason": "Both are instrument readings for the same conditions.",
                        "title": "Voltage and current",
                        "xlabel": "Condition",
                        "ylabel": "Value",
                        "data": {
                            "labels": ["Idle", "Load"],
                            "series": [
                                {"name": "Voltage (V)", "values": [5, 4.8]},
                                {"name": "Current (A)", "values": [0.2, 0.5]},
                            ],
                        },
                    }]
                },
                run_dir / "section_drafts" / "figure_plan.json",
            )

            self.assertEqual(report["status"], "failed")
            self.assertEqual(report["hard_issues"][0]["type"], "mixed_units_same_axis")

    def test_run_figure_recommend_writes_report_path(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            run_figure_recommend_with_composition_data(state)

            path = Path(state.output["figure_recommendations_path"])
            self.assertTrue(path.exists())
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["recommendation_count"], 1)


class ExpandedFigureBuildTests(unittest.TestCase):
    def test_builds_all_new_supported_figure_types(self):
        try:
            import matplotlib  # noqa: F401
        except Exception as exc:
            self.skipTest(f"matplotlib is not available: {exc}")

        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            run_dir = run_dir_for(state)
            draft_dir = run_dir / "section_drafts"
            draft_dir.mkdir(parents=True, exist_ok=True)
            (draft_dir / "figure_plan.json").write_text(json.dumps({
                "figures": [
                    {
                        "figure_id": "hist",
                        "figure_type": "histogram",
                        "title": "Reading distribution",
                        "xlabel": "Reading",
                        "ylabel": "Frequency count",
                        "data": {"values": [1, 2, 2, 3, 4, 4, 5], "bins": 4},
                    },
                    {
                        "figure_id": "box",
                        "figure_type": "boxplot",
                        "title": "Grouped spread",
                        "xlabel": "Group",
                        "ylabel": "Measured value",
                        "data": {"series": [{"name": "A", "values": [1, 2, 3]}, {"name": "B", "values": [2, 3, 4]}]},
                    },
                    {
                        "figure_id": "heat",
                        "figure_type": "heatmap",
                        "title": "Matrix intensity",
                        "xlabel": "Column",
                        "ylabel": "Row",
                        "data": {"x_labels": ["A", "B"], "y_labels": ["R1", "R2"], "values": [[1, 2], [3, 4]]},
                    },
                    {
                        "figure_id": "err",
                        "figure_type": "error_bar",
                        "title": "Mean with error",
                        "xlabel": "Sample",
                        "ylabel": "Mean value",
                        "data": {"labels": ["A", "B"], "series": [{"name": "Mean", "values": [1, 2], "errors": [0.1, 0.2]}]},
                    },
                    {
                        "figure_id": "stack",
                        "figure_type": "stacked_bar",
                        "title": "Composition",
                        "xlabel": "Phase",
                        "ylabel": "Share percent",
                        "data": {
                            "labels": ["Q1", "Q2"],
                            "series": [{"name": "A", "values": [40, 30]}, {"name": "B", "values": [60, 70]}],
                        },
                    },
                ]
            }), encoding="utf-8")

            built = run_figure_build(state)
            manifest_path = Path(built.output["figure_manifest_path"])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

            self.assertEqual(manifest["generated_count"], 5)
            self.assertEqual(manifest["error_count"], 0)
            for entry in manifest["figures"]:
                path = Path(entry["path"])
                self.assertTrue(path.exists(), entry)
                self.assertGreater(path.stat().st_size, 0, entry)

    def test_build_sanitizes_figure_path_and_rejects_bad_format(self):
        try:
            import matplotlib  # noqa: F401
        except Exception as exc:
            self.skipTest(f"matplotlib is not available: {exc}")

        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            run_dir = run_dir_for(state)
            draft_dir = run_dir / "section_drafts"
            draft_dir.mkdir(parents=True, exist_ok=True)
            (draft_dir / "figure_plan.json").write_text(json.dumps({
                "figures": [
                    {
                        "figure_id": "..\\outside/report",
                        "figure_type": "bar",
                        "title": "Escaped path attempt",
                        "xlabel": "Category",
                        "ylabel": "Value count",
                        "output_format": "png",
                        "data": {"labels": ["A", "B"], "series": [{"name": "Value", "values": [1, 2]}]},
                    },
                    {
                        "figure_id": "bad_format",
                        "figure_type": "bar",
                        "title": "Bad format",
                        "xlabel": "Category",
                        "ylabel": "Value count",
                        "output_format": "pdf",
                        "data": {"labels": ["A", "B"], "series": [{"name": "Value", "values": [1, 2]}]},
                    },
                ]
            }), encoding="utf-8")

            built = run_figure_build(state)
            manifest_path = Path(built.output["figure_manifest_path"])
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

            self.assertEqual(manifest["generated_count"], 1)
            self.assertEqual(manifest["error_count"], 1)
            self.assertIn("unsupported output_format", manifest["errors"][0])
            output_path = Path(manifest["figures"][0]["path"])
            self.assertEqual(output_path.parent, run_dir / "figures")
            self.assertEqual(output_path.name, "outside_report.png")

    def test_build_writes_visual_quality_report_with_review_issues(self):
        try:
            import matplotlib  # noqa: F401
        except Exception as exc:
            self.skipTest(f"matplotlib is not available: {exc}")

        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            run_dir = run_dir_for(state)
            draft_dir = run_dir / "section_drafts"
            draft_dir.mkdir(parents=True, exist_ok=True)
            (draft_dir / "figure_plan.json").write_text(json.dumps({
                "figures": [
                    {
                        "figure_id": "crowded_bar",
                        "figure_type": "bar",
                        "title": "Crowded labels",
                        "xlabel": "Category",
                        "ylabel": "Value count",
                        "width": 2,
                        "height": 1.6,
                        "data": {
                            "labels": [f"Very long category label {index}" for index in range(8)],
                            "series": [{"name": "Value", "values": list(range(8))}],
                        },
                    },
                    {
                        "figure_id": "dense_heat",
                        "figure_type": "heatmap",
                        "title": "Dense heatmap",
                        "xlabel": "Column",
                        "ylabel": "Row",
                        "width": 2,
                        "height": 1.5,
                        "data": {
                            "x_labels": [f"C{index}" for index in range(18)],
                            "y_labels": [f"R{index}" for index in range(18)],
                            "values": [[row + col for col in range(18)] for row in range(18)],
                        },
                    },
                ]
            }), encoding="utf-8")

            built = run_figure_build(state)
            report_path = Path(built.qa["figure_visual_quality_report_path"])
            report = json.loads(report_path.read_text(encoding="utf-8"))
            manifest = json.loads(Path(built.output["figure_manifest_path"]).read_text(encoding="utf-8"))

            self.assertEqual(report["status"], "review")
            issue_types = {issue["type"] for issue in report["issues"]}
            self.assertTrue({"tick_label_overlap", "dense_heatmap"} & issue_types)
            self.assertTrue(all("visual_quality_status" in entry for entry in manifest["figures"]))

    def test_build_writes_visual_quality_pass_for_clean_chart(self):
        try:
            import matplotlib  # noqa: F401
        except Exception as exc:
            self.skipTest(f"matplotlib is not available: {exc}")

        with tempfile.TemporaryDirectory() as tmpdir:
            state = _state(tmpdir)
            run_dir = run_dir_for(state)
            draft_dir = run_dir / "section_drafts"
            draft_dir.mkdir(parents=True, exist_ok=True)
            (draft_dir / "figure_plan.json").write_text(json.dumps({
                "figures": [{
                    "figure_id": "clean_bar",
                    "figure_type": "bar",
                    "title": "Clean comparison",
                    "xlabel": "Category",
                    "ylabel": "Value count",
                    "width": 6,
                    "height": 4,
                    "data": {"labels": ["A", "B"], "series": [{"name": "Value", "values": [1, 2]}]},
                }]
            }), encoding="utf-8")

            built = run_figure_build(state)
            report = json.loads(Path(built.qa["figure_visual_quality_report_path"]).read_text(encoding="utf-8"))

            self.assertEqual(report["status"], "passed")
            self.assertEqual(report["issues"], [])

    def test_visual_quality_draw_failure_returns_review_issue(self):
        class BrokenCanvas:
            def draw(self):
                raise RuntimeError("draw failed")

        class BrokenFigure:
            canvas = BrokenCanvas()

        issues = _figure_visual_quality_issues(BrokenFigure(), object(), "broken", "bar", {})

        self.assertEqual(issues[0]["type"], "visual_quality_check_failed")
        self.assertEqual(issues[0]["severity"], "review")
        self.assertEqual(issues[0]["figure_id"], "broken")
        self.assertEqual(issues[0]["error_type"], "RuntimeError")


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
