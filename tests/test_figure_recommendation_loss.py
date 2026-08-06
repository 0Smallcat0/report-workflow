"""Dropping a recommended figure has to be visible.

A run produced four chart recommendations and one figure. The audit report
wrote `recommendation_count: 4` and `figure_count: 1` two lines apart, then
`issues: []` and `status: passed`. Three tables whose data had already been
extracted — 3×4, 5×3 and 4×5 — vanished with nothing anywhere recording that
they had ever existed.

Dropping a figure is a legitimate editorial call, so none of this blocks. But
the author has to be able to see what they are dropping, and the check that
could have told them fired only when *every* figure was dropped.
"""
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from report_workflow.nodes.figure_plan_audit import audit_figure_plan
from report_workflow.state import ReportState


def _state(tmpdir: str) -> ReportState:
    state = ReportState.new("write report", [], str(Path(tmpdir) / "out"))
    state.spec["report_profile"] = "business_report"
    state.plan["blueprint"] = {
        "sections": {"findings": {"section_type": "findings"}},
        "section_order": ["findings"],
    }
    return state


def _recommendation(index: int, title: str, rows: int, columns: int) -> dict:
    return {
        "recommendation_id": f"figrec_{index}",
        "recommended_figure_type": "table",
        "acceptable_figure_types": ["table"],
        "confidence": "medium",
        "evidence_ids": [f"E_{index}"],
        "table_shape": {"rows": rows, "columns": columns},
        "figure_plan": {
            "figure_id": str(index),
            "figure_type": "table",
            "title": title,
            "section_id": "findings",
            "output_format": "png",
            "data": {"columns": ["a", "b"], "rows": [["1", "2"]]},
            "source_evidence_ids": [f"E_{index}"],
        },
    }


def _plan(indexes: list[int]) -> dict:
    return {
        "figures": [
            {
                "figure_id": str(index),
                "figure_type": "table",
                "title": f"figure {index}",
                "section_id": "findings",
                "output_format": "png",
                "recommendation_id": f"figrec_{index}",
                "source_evidence_ids": [f"E_{index}"],
                "data": {"columns": ["a", "b"], "rows": [["1", "2"]]},
            }
            for index in indexes
        ]
    }


RECOMMENDATIONS = [
    _recommendation(1, "碳酸鋰價格走勢", 4, 2),
    _recommendation(2, "各製程回收成本", 3, 4),
    _recommendation(3, "分選準確率比較", 5, 3),
    _recommendation(4, "紙類到廠價差", 4, 5),
    _recommendation(5, "政策時程", 3, 3),
]


def _issue_types(report: dict) -> set[str]:
    return {issue.get("type") for issue in report["issues"]}


def _detail_for(report: dict, issue_type: str) -> str:
    return " ".join(
        issue.get("detail", "") for issue in report["issues"] if issue.get("type") == issue_type
    )


class PartialLossTests(unittest.TestCase):
    def test_dropping_three_of_five_is_reported_with_ids_and_titles(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            report = audit_figure_plan(
                _state(tmpdir), RECOMMENDATIONS, _plan([1, 2]), Path(tmpdir) / "figure_plan.json"
            )
            self.assertIn("recommendations_unused", _issue_types(report))
            detail = _detail_for(report, "recommendations_unused")
            for index in (3, 4, 5):
                with self.subTest(recommendation=index):
                    self.assertIn(f"figrec_{index}", detail)
            self.assertIn("分選準確率比較", detail)
            self.assertIn("紙類到廠價差", detail)
            self.assertIn("政策時程", detail)

    def test_the_shape_is_named_so_the_author_can_weigh_the_loss(self):
        """A 5×3 is a table worth keeping; an id alone says nothing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            report = audit_figure_plan(
                _state(tmpdir), RECOMMENDATIONS, _plan([1, 2]), Path(tmpdir) / "figure_plan.json"
            )
            self.assertIn("5×3", _detail_for(report, "recommendations_unused"))

    def test_partial_loss_is_a_warning_not_a_block(self):
        """An author is allowed to decide a table is not worth printing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            report = audit_figure_plan(
                _state(tmpdir), RECOMMENDATIONS, _plan([1, 2]), Path(tmpdir) / "figure_plan.json"
            )
            self.assertEqual(report["hard_issues"], [])
            self.assertEqual(report["status"], "passed_with_warnings")

    def test_using_every_recommendation_reports_nothing(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            report = audit_figure_plan(
                _state(tmpdir),
                RECOMMENDATIONS,
                _plan([1, 2, 3, 4, 5]),
                Path(tmpdir) / "figure_plan.json",
            )
            self.assertNotIn("recommendations_unused", _issue_types(report))

    def test_the_counts_and_the_verdict_agree(self):
        """The two numbers sat in the same report and disagreed with it."""
        with tempfile.TemporaryDirectory() as tmpdir:
            report = audit_figure_plan(
                _state(tmpdir), RECOMMENDATIONS, _plan([1, 2]), Path(tmpdir) / "figure_plan.json"
            )
            self.assertEqual(report["recommendation_count"], 5)
            self.assertEqual(report["figure_count"], 2)
            self.assertNotEqual(
                report["status"],
                "passed",
                "a report stating 5 recommendations and 2 figures cannot be a clean pass",
            )


class TotalLossTests(unittest.TestCase):
    """The all-or-nothing path predates this and must survive the rewrite."""

    def test_using_none_of_them_still_reports(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            report = audit_figure_plan(
                _state(tmpdir), RECOMMENDATIONS, {"figures": []}, Path(tmpdir) / "figure_plan.json"
            )
            self.assertIn("recommendations_unused", _issue_types(report))
            self.assertIn("figrec_1", _detail_for(report, "recommendations_unused"))


class DraftUsageTests(unittest.TestCase):
    """The same all-or-nothing shape lived in figure_quality as well."""

    def _issues(self, planned: list[str], used: list[str]) -> list[dict]:
        from report_workflow.nodes.figure_quality import _check_planned_figure_usage

        state = ReportState.new("write report", [], "out")
        recommendations = [
            {"recommendation_id": f"figrec_{fid}", "evidence_ids": [f"E_{fid}"]}
            for fid in planned
        ]
        figures = [
            {
                "figure_id": fid,
                "recommendation_id": f"figrec_{fid}",
                "source_evidence_ids": [f"E_{fid}"],
            }
            for fid in planned
        ]
        with unittest.mock.patch(
            "report_workflow.nodes.figure_quality._figure_recommendations_payload",
            return_value={"recommendations": recommendations},
        ), unittest.mock.patch(
            "report_workflow.nodes.figure_quality._planned_figures",
            return_value=figures,
        ):
            return _check_planned_figure_usage(state, "body text", used)

    def test_partial_draft_loss_is_reported(self):
        issues = self._issues(["1", "2", "3", "4"], ["1"])
        types = {issue["type"] for issue in issues}
        self.assertIn("recommended_figure_plan_partially_unused", types)
        detail = " ".join(
            issue["detail"]
            for issue in issues
            if issue["type"] == "recommended_figure_plan_partially_unused"
        )
        for figure_id in ("2", "3", "4"):
            self.assertIn(figure_id, detail)

    def test_total_draft_loss_keeps_its_own_message(self):
        issues = self._issues(["1", "2", "3"], [])
        types = {issue["type"] for issue in issues}
        self.assertIn("recommended_figure_plan_unused", types)
        self.assertNotIn("recommended_figure_plan_partially_unused", types)

    def test_using_all_of_them_reports_nothing(self):
        self.assertEqual(self._issues(["1", "2"], ["1", "2"]), [])


if __name__ == "__main__":
    unittest.main()
